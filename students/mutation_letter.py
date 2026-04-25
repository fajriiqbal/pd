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


QR_VERSION = 3
QR_ECC_LEVEL = "H"
QR_SIZE = 29
QR_DATA_CODEWORDS = 26
QR_ECC_CODEWORDS = 44

QR_ECC_BITS = {
    "L": 0b01,
    "M": 0b00,
    "Q": 0b11,
    "H": 0b10,
}


def _gf_tables():
    exp = [0] * 512
    log = [0] * 256
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


GF_EXP, GF_LOG = _gf_tables()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def _poly_mul(p1, p2):
    result = [0] * (len(p1) + len(p2) - 1)
    for i, a in enumerate(p1):
        for j, b in enumerate(p2):
            result[i + j] ^= _gf_mul(a, b)
    return result


def _rs_generator(degree):
    generator = [1]
    for i in range(degree):
        generator = _poly_mul(generator, [1, GF_EXP[i]])
    return generator


RS_GENERATOR = _rs_generator(QR_ECC_CODEWORDS)


def _qr_encode_payload(payload):
    payload_bytes = payload.encode("ascii")
    if len(payload_bytes) > QR_DATA_CODEWORDS:
        raise MutationLetterError("Kode verifikasi terlalu panjang untuk QR versi surat ini.")

    bits = []

    def push_bits(value, length):
        for i in range(length - 1, -1, -1):
            bits.append((value >> i) & 1)

    push_bits(0b0100, 4)
    push_bits(len(payload_bytes), 8)
    for byte in payload_bytes:
        push_bits(byte, 8)

    capacity_bits = QR_DATA_CODEWORDS * 8
    remaining = capacity_bits - len(bits)
    push_bits(0, min(4, remaining))
    while len(bits) % 8 != 0:
        bits.append(0)

    data_bytes = []
    for i in range(0, len(bits), 8):
        chunk = 0
        for bit in bits[i:i + 8]:
            chunk = (chunk << 1) | bit
        data_bytes.append(chunk)

    pad_bytes = [0xEC, 0x11]
    pad_index = 0
    while len(data_bytes) < QR_DATA_CODEWORDS:
        data_bytes.append(pad_bytes[pad_index % 2])
        pad_index += 1

    msg = data_bytes + [0] * QR_ECC_CODEWORDS
    for i in range(QR_DATA_CODEWORDS):
        factor = msg[i]
        if factor == 0:
            continue
        for j, coeff in enumerate(RS_GENERATOR):
            msg[i + j] ^= _gf_mul(coeff, factor)

    ecc = msg[-QR_ECC_CODEWORDS:]
    return data_bytes + ecc


def _qr_mask(mask, row, col):
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return ((row // 2) + (col // 3)) % 2 == 0
    if mask == 5:
        return ((row * col) % 2) + ((row * col) % 3) == 0
    if mask == 6:
        return ((((row * col) % 2) + ((row * col) % 3)) % 2) == 0
    if mask == 7:
        return ((((row + col) % 2) + ((row * col) % 3)) % 2) == 0
    return False


def _qr_format_bits(mask):
    data = (QR_ECC_BITS[QR_ECC_LEVEL] << 3) | mask
    value = data << 10
    poly = 0x537
    for i in range(14, 9, -1):
        if value & (1 << i):
            value ^= poly << (i - 10)
    remainder = value & 0x3FF
    return ((data << 10) | remainder) ^ 0x5412


def _qr_base_matrix():
    matrix = [[None for _ in range(QR_SIZE)] for _ in range(QR_SIZE)]

    def reserve(row, col, value):
        matrix[row][col] = value

    def finder(top, left):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr = top + r
                cc = left + c
                if rr < 0 or rr >= QR_SIZE or cc < 0 or cc >= QR_SIZE:
                    continue
                if 0 <= r <= 6 and 0 <= c <= 6 and (r in {0, 6} or c in {0, 6} or (2 <= r <= 4 and 2 <= c <= 4)):
                    reserve(rr, cc, 1)
                else:
                    reserve(rr, cc, 0)

    finder(0, 0)
    finder(0, QR_SIZE - 7)
    finder(QR_SIZE - 7, 0)

    for i in range(8, QR_SIZE - 8):
        reserve(6, i, i % 2 == 0)
        reserve(i, 6, i % 2 == 0)

    alignment_center = 22
    for r in range(-2, 3):
        for c in range(-2, 3):
            rr = alignment_center + r
            cc = alignment_center + c
            if 0 <= rr < QR_SIZE and 0 <= cc < QR_SIZE and matrix[rr][cc] is None:
                if r in {-2, 2} or c in {-2, 2} or (r == 0 and c == 0):
                    reserve(rr, cc, 1)
                else:
                    reserve(rr, cc, 0)

    reserve(QR_SIZE - 8, 8, 1)

    # Format information areas are reserved here; values are filled later.
    for c in range(0, 6):
        reserve(8, c, 0)
    reserve(8, 7, 0)
    reserve(8, 8, 0)
    reserve(7, 8, 0)
    for r in range(5, -1, -1):
        reserve(r, 8, 0)

    for r in range(QR_SIZE - 1, QR_SIZE - 8, -1):
        reserve(r, 8, 0)
    for c in range(QR_SIZE - 8, QR_SIZE):
        reserve(8, c, 0)

    return matrix


def _qr_place_format_bits(matrix, mask):
    bits = _qr_format_bits(mask)
    bit_values = [(bits >> i) & 1 for i in range(14, -1, -1)]

    positions = []
    positions.extend((8, c) for c in range(0, 6))
    positions.append((8, 7))
    positions.append((8, 8))
    positions.append((7, 8))
    positions.extend((r, 8) for r in range(5, -1, -1))

    for (row, col), bit in zip(positions, bit_values):
        matrix[row][col] = bit

    mirror_positions = []
    mirror_positions.extend((r, 8) for r in range(QR_SIZE - 1, QR_SIZE - 8, -1))
    mirror_positions.extend((8, c) for c in range(QR_SIZE - 8, QR_SIZE))
    for (row, col), bit in zip(mirror_positions, bit_values):
        matrix[row][col] = bit


def _qr_place_data(matrix, codewords, mask):
    bits = []
    for byte in codewords:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)

    bit_index = 0
    col = QR_SIZE - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        row_range = range(QR_SIZE - 1, -1, -1) if upward else range(QR_SIZE)
        for row in row_range:
            for current_col in (col, col - 1):
                if matrix[row][current_col] is not None:
                    continue
                bit = bits[bit_index] if bit_index < len(bits) else 0
                if _qr_mask(mask, row, current_col):
                    bit ^= 1
                matrix[row][current_col] = bit
                bit_index += 1
        upward = not upward
        col -= 2


def _qr_penalty(matrix):
    size = len(matrix)
    total = 0

    # Rule 1: rows and columns with five or more same-color modules.
    for row in matrix:
        run_color = row[0]
        run_length = 1
        for value in row[1:]:
            if value == run_color:
                run_length += 1
            else:
                if run_length >= 5:
                    total += 3 + (run_length - 5)
                run_color = value
                run_length = 1
        if run_length >= 5:
            total += 3 + (run_length - 5)

    for col in range(size):
        run_color = matrix[0][col]
        run_length = 1
        for row in range(1, size):
            value = matrix[row][col]
            if value == run_color:
                run_length += 1
            else:
                if run_length >= 5:
                    total += 3 + (run_length - 5)
                run_color = value
                run_length = 1
        if run_length >= 5:
            total += 3 + (run_length - 5)

    # Rule 2: blocks of 2x2 same color.
    for row in range(size - 1):
        for col in range(size - 1):
            value = matrix[row][col]
            if value == matrix[row][col + 1] == matrix[row + 1][col] == matrix[row + 1][col + 1]:
                total += 3

    # Rule 3: finder-like patterns.
    patterns = ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1])
    for row in matrix:
        for i in range(size - 10):
            window = row[i:i + 11]
            if window in patterns:
                total += 40
    for col in range(size):
        column = [matrix[row][col] for row in range(size)]
        for i in range(size - 10):
            window = column[i:i + 11]
            if window in patterns:
                total += 40

    # Rule 4: proportion of dark modules.
    dark_modules = sum(value for row in matrix for value in row)
    percent = (dark_modules * 100) / (size * size)
    total += int(abs(percent - 50) // 5) * 10
    return total


def _build_qr_matrix(payload):
    codewords = _qr_encode_payload(payload)
    best_matrix = None
    best_penalty = None
    for mask in range(8):
        matrix = _qr_base_matrix()
        _qr_place_data(matrix, codewords, mask)
        _qr_place_format_bits(matrix, mask)
        penalty = _qr_penalty(matrix)
        if best_penalty is None or penalty < best_penalty:
            best_matrix = matrix
            best_penalty = penalty
    return best_matrix


def _draw_qr_matrix(x, y, size, matrix):
    module_count = len(matrix)
    module_size = size / float(module_count)
    commands = [
        b"1 1 1 rg",
        f"{x:.2f} {y:.2f} {size:.2f} {size:.2f} re f".encode("ascii"),
        b"0 0 0 rg",
    ]

    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            if not value:
                continue
            module_x = x + col_index * module_size
            module_y = y + (module_count - 1 - row_index) * module_size
            commands.append(
                f"{module_x:.2f} {module_y:.2f} {module_size:.2f} {module_size:.2f} re f".encode("ascii")
            )

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


def _build_content(mutation, headmaster, verification_code, issue_date, logo_exists, qr_matrix):
    lines = []
    page_height = A4_HEIGHT

    def text(x, y, value, size=11, bold=False, align="left"):
        font = "/F2" if bold else "/F1"
        escaped = _pdf_text(value)
        return f"BT {font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {escaped.decode('latin-1')} Tj ET".encode("latin-1")

    def centered(x_center, y, value, size=11, bold=False):
        return text(x_center, y, value, size=size, bold=bold, align="center")

    def line(x1, y1, x2, y2, width=1):
        return f"{width} w 0 0 0 RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S".encode("ascii")

    if logo_exists:
        lines.append(b"q")
        lines.append(f"66 0 0 66 44 {page_height - 96:.2f} cm /Logo Do Q".encode("ascii"))

    # Header
    lines.append(centered(297.64, page_height - 46, SCHOOL_NAME, size=18, bold=True))
    lines.append(centered(297.64, page_height - 67, f"{SCHOOL_LOCATION}", size=14, bold=True))
    lines.append(centered(297.64, page_height - 83, "Jalan sesuai data madrasah", size=8))
    lines.append(centered(297.64, page_height - 95, "Email / Telp: sesuai data madrasah", size=8))
    lines.append(line(44, page_height - 108, 551, page_height - 108, width=1))

    # Title
    lines.append(centered(297.64, page_height - 144, "SURAT MUTASI SISWA", size=15, bold=True))
    lines.append(centered(297.64, page_height - 162, f"Nomor: {verification_code}", size=10))

    # Main body box
    box_left = 44
    box_top = page_height - 188
    box_right = 551
    box_bottom = 292
    lines.append(f"0.92 g {box_left:.2f} {box_bottom:.2f} {box_right - box_left:.2f} {box_top - box_bottom:.2f} re f".encode("ascii"))
    lines.append(line(box_left, box_bottom, box_right, box_bottom, width=0.8))
    lines.append(line(box_left, box_top, box_right, box_top, width=0.8))
    lines.append(line(box_left, box_bottom, box_left, box_top, width=0.8))
    lines.append(line(box_right, box_bottom, box_right, box_top, width=0.8))

    intro_y = box_top - 26
    lines.append(text(60, intro_y, "Yang bertanda tangan di bawah ini:", size=10, bold=True))
    lines.append(text(60, intro_y - 18, f"Nama pejabat  : {headmaster.teacher_name}", size=10))
    lines.append(text(60, intro_y - 34, f"Jabatan       : {headmaster.task_name}", size=10))
    lines.append(text(60, intro_y - 50, f"NIP           : {headmaster.nip or '-'}", size=10))
    lines.append(text(60, intro_y - 70, "Menerangkan dengan sebenarnya bahwa:", size=10))

    student_lines = [
        ("Nama siswa", mutation.student.user.full_name),
        ("NIS", mutation.student.nis or "-"),
        ("NISN", mutation.student.nisn or "-"),
        ("TTL", f"{mutation.student.birth_place or '-'}, {_id_text(mutation.student.birth_date) if mutation.student.birth_date else '-'}"),
        ("Jenis kelamin", mutation.student.get_gender_display()),
        ("Kelas / Rombel", mutation.student.class_name or (mutation.student.study_group.name if mutation.student.study_group_id else "-")),
        ("Sekolah asal", mutation.origin_school_name or "-"),
        ("NPSN asal", mutation.origin_school_npsn or "-"),
        ("Sekolah tujuan", mutation.destination_school_name or "-"),
        ("NPSN tujuan", mutation.destination_school_npsn or "-"),
        ("Alasan mutasi", mutation.reason or "-"),
        ("Tanggal mutasi", _id_text(mutation.mutation_date)),
    ]
    label_x = 60
    value_x = 170
    current_y = intro_y - 88
    for label, value in student_lines:
        lines.append(text(label_x, current_y, f"{label}", size=10, bold=True))
        for part_index, part in enumerate(_wrap_text(str(value), limit=54)):
            lines.append(text(value_x, current_y, part, size=10))
            current_y -= 14
        current_y -= 2

    closing_y = current_y - 6
    lines.append(text(60, closing_y, "Surat ini dibuat berdasarkan data mutasi pada sistem madrasah.", size=10))
    lines.append(text(60, closing_y - 14, "Gunakan QR code di bawah sebagai verifikasi keaslian surat.", size=10))

    # Signature block
    sig_left = 344
    sig_right = 548
    sig_top = 262
    qr_size = 84
    qr_left = sig_left + ((sig_right - sig_left) - qr_size) / 2
    qr_bottom = 144

    lines.append(text(sig_left, sig_top, f"Tulung, {_id_text(issue_date)}", size=10))
    lines.append(text(sig_left, sig_top - 16, "Kepala Madrasah", size=10))

    # QR with centered logo
    white_pad = 6
    lines.append(f"1 1 1 rg {qr_left - white_pad:.2f} {qr_bottom - white_pad:.2f} {qr_size + white_pad * 2:.2f} {qr_size + white_pad * 2:.2f} re f".encode("ascii"))
    lines.append(_draw_qr_matrix(qr_left, qr_bottom, qr_size, qr_matrix))

    if logo_exists:
        logo_box = 26
        logo_left = qr_left + (qr_size - logo_box) / 2
        logo_bottom = qr_bottom + (qr_size - logo_box) / 2
        lines.append(f"1 1 1 rg {logo_left - 2:.2f} {logo_bottom - 2:.2f} {logo_box + 4:.2f} {logo_box + 4:.2f} re f".encode("ascii"))
        lines.append(b"q")
        lines.append(f"{logo_box:.2f} 0 0 {logo_box:.2f} {logo_left:.2f} {logo_bottom:.2f} cm /Logo Do Q".encode("ascii"))

    lines.append(text(sig_left, 126, headmaster.teacher_name, size=11, bold=True))
    lines.append(text(sig_left, 110, f"NIP. {headmaster.nip or '-'}", size=10))
    lines.append(text(sig_left, 96, f"Kode verifikasi: {verification_code}", size=8))

    return b"\n".join(lines)


def _build_pdf_bytes(mutation):
    headmaster = _get_headmaster_info()
    issue_date = timezone.localdate()
    verification_code = _build_code(mutation)
    logo_path = _find_logo_path()
    logo_exists = logo_path is not None
    qr_matrix = _build_qr_matrix(verification_code)

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
    content_stream = _build_content(mutation, headmaster, verification_code, issue_date, logo_exists, qr_matrix)
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
