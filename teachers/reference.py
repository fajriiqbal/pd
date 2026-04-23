from __future__ import annotations

import re
from html import unescape
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

SEARCH_ENDPOINTS = (
    "https://sekolah.data.kemendikdasmen.go.id/sekolah?keyword={query}",
    "https://sekolah.data.kemendikdasmen.go.id/sekolah?q={query}",
    "https://sekolah.data.kemendikdasmen.go.id/sekolah?search={query}",
    "https://sekolah.data.kemendikdasmen.go.id/sekolah?nama={query}",
    "https://sekolah.data.kemendikdasmen.go.id/sekolah?npsn={query}",
    "https://referensi.data.kemdikbud.go.id/pendidikan/npsn/{query}",
    "https://referensi.data.kemdikbud.go.id/tabs.php?npsn={query}",
    "https://referensi.data.kemendikdasmen.go.id/pendidikan/npsn/{query}",
    "https://referensi.data.kemendikdasmen.go.id/tabs.php?npsn={query}",
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MadrasahManagement/1.0; +https://example.local)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_text(url: str) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=12) as response:
        data = response.read()
        headers = getattr(response, "headers", None)
        charset = "utf-8"
        if headers is not None:
            get_charset = getattr(headers, "get_content_charset", None)
            if callable(get_charset):
                charset = get_charset() or "utf-8"
    return data.decode(charset, errors="replace")


def _strip_tags(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|br|td|th)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _extract_value(text: str, label: str) -> str:
    pattern = rf"{re.escape(label)}\s*[:：]\s*(.+?)(?=\s+[A-Z][A-Za-z0-9/().\- ]+\s*[:：]|\n|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return " ".join(match.group(1).split()).strip(" -·")


def _extract_first(patterns: Iterable[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = " ".join(match.group(1).split()).strip()
            if value:
                return value
    return ""


def _normalize_school_name(name: str) -> str:
    return " ".join(name.split()).strip()


def _guess_level(name: str, raw_level: str) -> str:
    value = " ".join((raw_level or "").split()).strip()
    if value:
        return value

    upper_name = name.upper()
    for prefix in ("TK", "KB", "PAUD", "RA", "SD", "MI", "SMP", "MTs", "SMA", "MA", "SMK", "SLB"):
        if upper_name.startswith(prefix.upper()):
            return prefix.upper()
    return ""


def _extract_profile_links(html_text: str, base_url: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r'href=["\']([^"\']*profil[^"\']*)["\']', html_text, re.IGNORECASE):
        href = unescape(match.group(1)).strip()
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        links.append(urljoin(base_url, href))
    return links


def _parse_profile_page(html_text: str, source_url: str) -> dict:
    text = _strip_tags(html_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = " \n ".join(lines)

    name = _extract_first(
        [
            r"^#\s*([^\n]+)",
            r"####\s*([^\n]+)",
            r"Nama\s*[:：]\s*([^\n]+)",
        ],
        joined,
    )
    npsn = _extract_value(joined, "NPSN")
    status = _extract_value(joined, "Status Sekolah")
    address = _extract_value(joined, "Alamat")
    village = _extract_value(joined, "Desa/Kelurahan")
    level = _guess_level(name, _extract_value(joined, "Bentuk Pendidikan"))

    if not name:
        title_match = re.search(r"<title>\s*([^<]+?)\s*\|\s*", html_text, re.IGNORECASE)
        if title_match:
            name = _normalize_school_name(title_match.group(1))

    if not name:
        name = _extract_first([r"Nama Satuan Pendidikan\s*[:：]\s*([^\n]+)"], joined)

    if not address:
        address = _extract_value(joined, "Alamat")

    return {
        "name": _normalize_school_name(name),
        "npsn": npsn.strip(),
        "status": status.strip(),
        "address": address.strip(),
        "village": village.strip(),
        "level": level.strip(),
        "source_url": source_url,
    }


def _parse_table_style_results(lines: list[str], base_url: str) -> list[dict]:
    lowered = [line.lower() for line in lines]
    if "npsn" not in lowered or ("nama satuan pendidikan" not in " ".join(lowered) and "nama" not in lowered):
        return []

    npsn = ""
    npsn_index = -1
    for index, line in enumerate(lines):
        if re.fullmatch(r"\d{6,12}", line.strip()):
            npsn = line.strip()
            npsn_index = index
            break

    if not npsn or npsn_index < 0:
        return []

    remaining = [line.strip() for line in lines[npsn_index + 1 :] if line.strip()]

    def take_next_text(items: list[str]) -> str:
        for candidate in items:
            lower = candidate.lower()
            if lower in {"no", "npsn", "nama", "nama satuan pendidikan", "alamat", "kelurahan", "status"}:
                continue
            if re.fullmatch(r"\d+", candidate):
                continue
            return candidate
        return ""

    name = take_next_text(remaining)
    address = take_next_text(remaining[remaining.index(name) + 1 :] if name and name in remaining else remaining[1:]) if remaining else ""
    village = take_next_text(remaining[remaining.index(address) + 1 :] if address and address in remaining else remaining[2:]) if remaining else ""
    status = take_next_text(remaining[remaining.index(village) + 1 :] if village and village in remaining else remaining[3:]) if remaining else ""

    if not (name and npsn):
        return []

    return [
        {
            "name": _normalize_school_name(name),
            "npsn": npsn,
            "status": _normalize_school_name(status),
            "address": _normalize_school_name(address),
            "village": _normalize_school_name(village),
            "level": "",
            "source_url": base_url,
        }
    ]


def _parse_search_results(html_text: str, base_url: str) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()

    link_candidates = _extract_profile_links(html_text, base_url)
    if link_candidates:
        for link in link_candidates:
            if link in seen:
                continue
            seen.add(link)
            try:
                profile_html = _fetch_text(link)
            except (HTTPError, URLError, TimeoutError, OSError):
                continue
            profile = _parse_profile_page(profile_html, link)
            if profile.get("name") and profile.get("npsn"):
                results.append(profile)
            if len(results) >= 12:
                return results
        return results

    text = _strip_tags(html_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    table_results = _parse_table_style_results(lines, base_url)
    if table_results:
        return table_results

    block_pattern = re.compile(
        r"NPSN\s*[:：]?\s*(?P<npsn>\d{6,12}).{0,260}?"
        r"(?:Nama Satuan Pendidikan|Nama|Sekolah)\s*[:：]?\s*(?P<name>[^|\\n]{3,120}).{0,260}?"
        r"Alamat\s*[:：]?\s*(?P<address>[^|\\n]{3,200})"
        r"(?:.{0,120}?Kelurahan\s*[:：]?\s*(?P<village>[^|\\n]{2,120}))?"
        r"(?:.{0,120}?Status\s*[:：]?\s*(?P<status>[^|\\n]{2,80}))?",
        re.IGNORECASE | re.DOTALL,
    )
    for match in block_pattern.finditer(text):
        item = {
            "name": _normalize_school_name(match.group("name") or ""),
            "npsn": (match.group("npsn") or "").strip(),
            "status": _normalize_school_name(match.group("status") or ""),
            "address": _normalize_school_name(match.group("address") or ""),
            "village": _normalize_school_name(match.group("village") or ""),
            "level": "",
            "source_url": base_url,
        }
        if item["name"] and item["npsn"]:
            results.append(item)

    return results


def _candidate_urls(query: str) -> list[str]:
    encoded = quote_plus(query.strip())
    urls: list[str] = []
    for template in SEARCH_ENDPOINTS:
        urls.append(template.format(query=encoded))
    return urls


def search_school_reference(query: str, limit: int = 10) -> list[dict]:
    query = " ".join((query or "").split()).strip()
    if not query:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    numeric_only = query.isdigit()

    for url in _candidate_urls(query if numeric_only else query):
        try:
            html_text = _fetch_text(url)
        except (HTTPError, URLError, TimeoutError, OSError):
            continue

        parsed = _parse_search_results(html_text, url)
        for item in parsed:
            npsn = item.get("npsn") or ""
            if npsn and npsn in seen:
                continue
            if npsn:
                seen.add(npsn)
            results.append(item)
            if len(results) >= limit:
                return results

    return results
