import datetime as _dt
import zlib
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone

from teachers.utils import get_headmaster_teacher


A4_WIDTH = 595.28
A4_HEIGHT = 841.89

SCHOOL_NAME = "MADRASAH TSANAWIYAH SUNAN KALIJAGA"
SCHOOL_LOCATION = "TULUNG"
SCHOOL_TAGLINE = "Surat Mutasi Siswa"
VERIFICATION_PREFIX = "MUT"

CODE39_PATTERNS = {
    "0": "nnnwwnwnn",
    "1": "wnnwnnnnw",
    "2": "nnwwnnnnw",
    "3": "wnwwnnnnn",
    "4": "nnnwwnnnw",
    "5": "wnnwwnnnn",
    "6": "nnwwwnnnn",
    "7": "nnnwnnwnw",
    "8": "wnnwnnwnn",
    "9": "nnwwnnwnn",
    "A": "wnnnnwnnw",
    "B": "nnwnnwnnw",
    "C": "wnwnnwnnn",
    "D": "nnnnwwnnw",
    "E": "wnnnwwnnn",
    "F": "nnwnwwnnn",
    "G": "nnnnnwwnw",
    "H": "wnnnnwwnn",
    "I": "nnwnnwwnn",
    "J": "nnnnwwwnn",
    "K": "wnnnnnnww",
    "L": "nnwnnnnww",
    "M": "wnwnnnnwn",
    "N": "nnnnwnnww",
    "O": "wnnnwnnwn",
    "P": "nnwnwnnwn",
    "Q": "nnnnnnwww",
    "R": "wnnnnnwwn",
    "S": "nnwnnnwwn",
    "T": "nnnnwnwwn",
    "U": "wwnnnnnnw",
    "V": "nwwnnnnnw",
    "W": "wwwnnnnnn",
    "X": "nwnnwnnnw",
    "Y": "wwnnwnnnn",
    "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw",
    ".": "wwnnnnwnn",
    " ": "nwwnnnwnn",
    "*": "nwnnwnwnn",
    "$": "nwnwnwnnn",
    "/": "nwnwnnnwn",
    "+": "nwnnnwnwn",
    "%": "nnnwnwnwn",
}


class MutationLetterError(ValueError):
    pass


@dataclass
class HeadmasterInfo:
    teacher_name: str
    nip: str
    task_name: str


def _pdf_text(text):
    raw = (text or "").encode("latin-1", "replace")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + raw + b")"


def _id_text(value):
    if isinstance(value, _dt.date):
        months = [
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ]
        return f"{value.day:02d} {months[value.month - 1]} {value.year}"
    return str(value)


def _wrap_text(text, limit=90):
    words = str(text or "").split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _escape_code39(value):
    normalized = (value or "").upper().strip()
    allowed = set(CODE39_PATTERNS)
    invalid = [char for char in normalized if char not in allowed]
    if invalid:
        raise MutationLetterError(
            f"Kode verifikasi hanya mendukung karakter Code39. Karakter bermasalah: {', '.join(sorted(set(invalid)))}"
        )
    return normalized


def _code39_units(value):
    encoded = f"*{_escape_code39(value)}*"
    total = 0
    for index, char in enumerate(encoded):
        total += sum(3 if token == "w" else 1 for token in CODE39_PATTERNS[char])
        if index < len(encoded) - 1:
            total += 1
    return encoded, total


def _draw_code39(x, y, width, height, value):
    encoded, units = _code39_units(value)
    scale = width / float(units)
    narrow = scale
    wide = scale * 3
    cursor = x
    commands = [b"0 0 0 rg"]

    for index, char in enumerate(encoded):
        pattern = CODE39_PATTERNS[char]
        for pattern_index, token in enumerate(pattern):
            segment_width = wide if token == "w" else narrow
            if pattern_index % 2 == 0:
                commands.append(f"{cursor:.2f} {y:.2f} {segment_width:.2f} {height:.2f} re f".encode("ascii"))
            cursor += segment_width
        if index < len(encoded) - 1:
            cursor += narrow
    return b"\n".join(commands)


def _png_to_rgb_bytes(path):
    raw = Path(path).read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise MutationLetterError("Logo surat harus berformat PNG.")

    width = height = None
    color_type = None
    bit_depth = None
    chunks = []
    i = 8
    while i < len(raw):
        length = int.from_bytes(raw[i:i + 4], "big")
        chunk_type = raw[i + 4:i + 8]
        data = raw[i + 8:i + 8 + length]
        i += 12 + length
        if chunk_type == b"IHDR":
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth = data[8]
            color_type = data[9]
        elif chunk_type == b"IDAT":
            chunks.append(data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None:
        raise MutationLetterError("Logo PNG tidak valid.")
    if bit_depth != 8 or color_type != 6:
        raise MutationLetterError("Logo PNG harus berwarna RGBA 8-bit.")

    decompressed = zlib.decompress(b"".join(chunks))
    bytes_per_pixel = 4
    row_length = width * bytes_per_pixel
    rows = []
    previous_row = bytearray(row_length)
    offset = 0

    def paeth(a, b, c):
        p = a + b - c
        pa = abs(p - a)
        pb = abs(p - b)
        pc = abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    for _ in range(height):
        filter_type = decompressed[offset]
        offset += 1
        current = bytearray(decompressed[offset:offset + row_length])
        offset += row_length

        if filter_type == 1:
            for idx in range(bytes_per_pixel, row_length):
                current[idx] = (current[idx] + current[idx - bytes_per_pixel]) & 0xFF
        elif filter_type == 2:
            for idx in range(row_length):
                current[idx] = (current[idx] + previous_row[idx]) & 0xFF
        elif filter_type == 3:
            for idx in range(row_length):
                left = current[idx - bytes_per_pixel] if idx >= bytes_per_pixel else 0
                up = previous_row[idx]
                current[idx] = (current[idx] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for idx in range(row_length):
                left = current[idx - bytes_per_pixel] if idx >= bytes_per_pixel else 0
                up = previous_row[idx]
                up_left = previous_row[idx - bytes_per_pixel] if idx >= bytes_per_pixel else 0
                current[idx] = (current[idx] + paeth(left, up, up_left)) & 0xFF
        elif filter_type != 0:
            raise MutationLetterError("Filter PNG logo tidak didukung.")

        rgb_row = bytearray()
        for idx in range(0, row_length, 4):
            red, green, blue, alpha = current[idx:idx + 4]
            rgb_row.extend(
                (
                    (red * alpha + 255 * (255 - alpha)) // 255,
                    (green * alpha + 255 * (255 - alpha)) // 255,
                    (blue * alpha + 255 * (255 - alpha)) // 255,
                )
            )
        rows.append(bytes(rgb_row))
        previous_row = current

    rgb_data = b"".join(rows)
    return width, height, zlib.compress(rgb_data)


def _find_logo_path():
    candidates = [
        finders.find("img/mutasi-logo.png"),
        Path(settings.BASE_DIR) / "static" / "img" / "mutasi-logo.png",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _get_headmaster_info():
    teacher = get_headmaster_teacher()
    if not teacher:
        raise MutationLetterError(
            "Data kepala madrasah belum ditemukan. Tambahkan tugas tambahan guru dengan tipe Pimpinan/Kepala Madrasah."
        )

    task = teacher.additional_tasks.filter(is_active=True, task_type="pimpinan").order_by("-start_date", "-created_at").first()
    task_name = task.name if task else "Kepala Madrasah"
    return HeadmasterInfo(
        teacher_name=teacher.user.full_name,
        nip=teacher.nip or "",
        task_name=task_name or "Kepala Madrasah",
    )


def _build_code(mutation):
    return f"{VERIFICATION_PREFIX}-{mutation.pk:05d}-{mutation.mutation_date:%Y%m%d}"


def _build_content(mutation, headmaster, verification_code, issue_date, logo_exists):
    lines = []
    page_width = A4_WIDTH
    page_height = A4_HEIGHT

    def text(x, y, value, size=11, bold=False, align="left"):
        font = "/F2" if bold else "/F1"
        escaped = _pdf_text(value)
        if align == "center":
            return f"BT {font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {escaped.decode('latin-1')} Tj ET".encode("latin-1")
        if align == "right":
            return f"BT {font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {escaped.decode('latin-1')} Tj ET".encode("latin-1")
        return f"BT {font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {escaped.decode('latin-1')} Tj ET".encode("latin-1")

    # Header
    if logo_exists:
        lines.append(b"q")
        lines.append(f"74 0 0 74 44 {page_height - 108:.2f} cm /Logo Do Q".encode("ascii"))

    lines.append(text(130, page_height - 48, SCHOOL_NAME, size=18, bold=True))
    lines.append(text(130, page_height - 70, f"{SCHOOL_LOCATION}", size=14, bold=True))
    lines.append(text(130, page_height - 88, "Jalan sesuai data madrasah", size=9))
    lines.append(text(130, page_height - 102, "Email / Telp: sesuai data madrasah", size=9))
    lines.append(b"0 0 0 RG 1 w 44 %.2f m 551 %.2f l S" % (page_height - 114, page_height - 114))

    # Title block
    lines.append(text(0, page_height - 150, "SURAT MUTASI SISWA", size=15, bold=True, align="center"))
    lines.append(text(0, page_height - 168, f"Nomor: {verification_code}", size=10, align="center"))

    body_y = page_height - 204
    paragraphs = [
        "Yang bertanda tangan di bawah ini Kepala Madrasah Tsanawiyah Sunan Kalijaga Tulung, menerangkan bahwa:",
        f"Nama siswa    : {mutation.student.user.full_name}",
        f"NIS           : {mutation.student.nis or '-'}",
        f"NISN          : {mutation.student.nisn or '-'}",
        f"TTL           : {mutation.student.birth_place or '-'}, {_id_text(mutation.student.birth_date) if mutation.student.birth_date else '-'}",
        f"Jenis kelamin  : {mutation.student.get_gender_display()}",
        f"Kelas / Rombel : {mutation.student.class_name or (mutation.student.study_group.name if mutation.student.study_group_id else '-')}",
        f"Mutasi dari    : {mutation.origin_school_name or '-'}",
        f"Tujuan mutasi  : {mutation.destination_school_name or '-'}",
        f"Alasan mutasi  : {mutation.reason or '-'}",
        f"Tanggal mutasi : {_id_text(mutation.mutation_date)}",
    ]

    lines.append(text(44, body_y, "Dengan ini dinyatakan:", size=11, bold=True))
    body_y -= 20
    for paragraph in paragraphs:
        for part in _wrap_text(paragraph, limit=84):
            lines.append(text(58, body_y, part, size=10))
            body_y -= 16
        body_y -= 2

    closing = [
        "Surat ini dibuat berdasarkan data mutasi siswa pada sistem madrasah dan dipergunakan sebagaimana mestinya.",
        "Apabila diperlukan verifikasi keaslian, gunakan barcode di bawah tanda tangan kepala madrasah.",
    ]
    body_y -= 8
    for paragraph in closing:
        for part in _wrap_text(paragraph, limit=92):
            lines.append(text(44, body_y, part, size=10))
            body_y -= 16

    # Signature block
    sig_y = 120
    lines.append(text(360, sig_y + 70, f"Tulung, {_id_text(issue_date)}", size=10))
    lines.append(text(360, sig_y + 54, headmaster.task_name, size=10))
    lines.append(text(360, sig_y + 38, "", size=10))
    lines.append(text(360, sig_y + 22, "", size=10))
    lines.append(text(360, sig_y + 6, "", size=10))
    lines.append(text(360, sig_y - 10, headmaster.teacher_name, size=10, bold=True))
    if headmaster.nip:
        lines.append(text(360, sig_y - 26, f"NIP. {headmaster.nip}", size=10))
    else:
        lines.append(text(360, sig_y - 26, "NIP. -", size=10))

    # Barcode block
    barcode_x = 44
    barcode_y = 58
    barcode_width = 195
    barcode_height = 36
    lines.append(_draw_code39(barcode_x, barcode_y, barcode_width, barcode_height, verification_code))
    lines.append(text(barcode_x, barcode_y - 14, verification_code, size=8))
    lines.append(text(barcode_x, barcode_y - 28, "Barcode verifikasi surat", size=8))

    return b"\n".join(lines)


def _build_pdf_bytes(mutation):
    headmaster = _get_headmaster_info()
    issue_date = timezone.localdate()
    verification_code = _build_code(mutation)
    logo_path = _find_logo_path()
    logo_exists = logo_path is not None

    objects = []

    def add_object(data):
        objects.append(data)
        return len(objects)

    font_regular_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    logo_id = None
    if logo_exists and logo_path:
        width, height, compressed_rgb = _png_to_rgb_bytes(logo_path)
        image_dict = (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(compressed_rgb)} >>"
        ).encode("ascii")
        logo_id = add_object(image_dict + b"\nstream\n" + compressed_rgb + b"\nendstream")
    content_stream = _build_content(mutation, headmaster, verification_code, issue_date, logo_exists)
    content_id = add_object(f"<< /Length {len(content_stream)} >>".encode("ascii") + b"\nstream\n" + content_stream + b"\nendstream")

    resources_parts = [
        f"/Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >>",
    ]
    if logo_id:
        resources_parts.append(f"/XObject << /Logo {logo_id} 0 R >>")
    resources = f"<< {' '.join(resources_parts)} >>".encode("ascii")

    page_parts = [
        "/Type /Page",
        "/Parent 0 0 R",
        f"/MediaBox [0 0 {A4_WIDTH:.2f} {A4_HEIGHT:.2f}]",
        f"/Resources {resources.decode('ascii')}",
        f"/Contents {content_id} 0 R",
    ]
    page_dict = f"<< {' '.join(page_parts)} >>".encode("ascii")
    page_id = add_object(page_dict)

    pages_dict = f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode("ascii")
    pages_id = add_object(pages_dict)

    # Fix parent reference in the page object.
    objects[page_id - 1] = (
        f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {A4_WIDTH:.2f} {A4_HEIGHT:.2f}] "
        f"/Resources {resources.decode('ascii')} /Contents {content_id} 0 R >>"
    ).encode("ascii")

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    output = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current = len(output[0])
    for index, obj in enumerate(objects, start=1):
        offsets.append(current)
        chunk = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        output.append(chunk)
        current += len(chunk)

    xref_offset = sum(len(part) for part in output)
    xref_lines = [b"xref\n", f"0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return b"".join(output + xref_lines + [trailer])


def build_student_mutation_letter_pdf(mutation):
    if mutation.direction != mutation.Direction.OUTBOUND:
        raise MutationLetterError("Surat mutasi PDF hanya tersedia untuk mutasi keluar.")

    pdf_bytes = _build_pdf_bytes(mutation)
    filename = f"surat-mutasi-{mutation.student.nis or mutation.student.pk}-{mutation.pk}.pdf"
    return pdf_bytes, filename

