# Sistem Manajemen Data Madrasah

Proyek ini adalah fondasi aplikasi manajemen data madrasah berbasis Django, Python, dan Tailwind CSS. Fokus awalnya meliputi:

- Data siswa
- Data guru
- Akun siswa
- Akun guru
- Dashboard ringkas untuk memantau data utama

Struktur proyek sudah disiapkan agar mudah dikembangkan ke modul berikutnya seperti kelas, wali kelas, absensi, nilai, mata pelajaran, pembayaran, alumni, dan surat menyurat.

## Fitur Awal

- Custom user model dengan peran `admin`, `guru`, dan `siswa`
- Modul data siswa
- Modul data guru
- Halaman daftar akun
- Dashboard dengan ringkasan jumlah data
- Tampilan dasar menggunakan Tailwind CSS melalui CDN agar setup awal lebih ringan
- Django admin yang sudah dikustom ringan untuk memudahkan input data awal

## Struktur Aplikasi

```text
madrasah_management/
├── manage.py
├── requirements.txt
├── madrasah_management/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── accounts/
├── students/
├── teachers/
├── dashboard/
├── templates/
└── static/
```

## Cara Menjalankan

Pastikan Python 3.11+ sudah terpasang. Untuk Python 3.14, gunakan Django 5.2.x karena seri ini sudah mendukung Python 3.14.

1. Buat virtual environment

```powershell
python -m venv .venv
```

2. Aktifkan virtual environment

```powershell
.venv\Scripts\Activate.ps1
```

3. Install dependency

```powershell
pip install -r requirements.txt
```

4. Migrasi database

```powershell
python manage.py makemigrations
python manage.py migrate
```

5. Buat akun admin

```powershell
python manage.py createsuperuser
```

6. Jalankan server

```powershell
python manage.py runserver
```

Buka `http://127.0.0.1:8000/`.

## Roadmap Pengembangan yang Direkomendasikan

- Modul kelas dan rombongan belajar
- Modul mata pelajaran
- Modul jadwal pelajaran
- Modul absensi siswa dan guru
- Modul nilai rapor
- Modul wali murid
- Modul pembayaran SPP atau administrasi
- Modul arsip dokumen siswa
- Modul alumni
- Modul cetak laporan PDF

## Catatan

Tailwind CSS saat ini dipakai lewat CDN supaya proyek cepat dimulai tanpa Node.js. Jika nanti Anda ingin versi produksi yang lebih rapi, kita bisa upgrade ke build Tailwind penuh dengan `tailwind.config.js`, `npm`, dan pipeline static asset Django.

## Deploy ke Hosting via GitHub

Panduan paling mudah untuk produksi adalah memakai GitHub sebagai source code, lalu hubungkan ke hosting seperti Render atau Railway.

1. Push project ini ke repository GitHub.
2. Buat database PostgreSQL di hosting.
3. Set environment variable berikut:
   - `SECRET_KEY`
   - `DEBUG=False`
   - `ALLOWED_HOSTS=domain-hosting-kamu`
   - `DATABASE_URL=...`
4. Jalankan perintah build/migration di hosting:

```powershell
python manage.py migrate
python manage.py collectstatic --noinput
```

5. Start command:

```powershell
gunicorn madrasah_management.wsgi:application
```

Catatan:
- File `.env.example` sudah disiapkan sebagai referensi.
- `Procfile` juga sudah tersedia untuk hosting yang membacanya otomatis.
