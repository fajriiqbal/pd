import zipfile

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import CustomUser
from academics.models import AcademicYear, SchoolClass, StudyGroup

from .models import (
    PromotionRun,
    StudentDocument,
    StudentAlumniDocument,
    StudentAlumniValidation,
    StudentMutationRecord,
    StudentProfile,
)

BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class BackupRestoreUploadForm(forms.Form):
    backup_file = forms.FileField(
        label="File backup ZIP",
        help_text="Pilih file .zip hasil backup dari menu backup & restore.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "accept": ".zip",
            }
        ),
    )
    confirm_restore = forms.BooleanField(
        label="Saya paham restore akan mengganti data saat ini",
        required=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900",
            }
        ),
    )

    def clean_backup_file(self):
        uploaded_file = self.cleaned_data["backup_file"]
        if not zipfile.is_zipfile(uploaded_file):
            raise ValidationError("File backup harus berupa ZIP yang valid.")
        uploaded_file.seek(0)
        return uploaded_file


class StudentImportUploadForm(forms.Form):
    excel_file = forms.FileField(
        label="File Excel siswa",
        help_text="Gunakan file .xlsx dengan beberapa sheet, misalnya Kelas 7 - 7A, Kelas 7 - 7B, dan seterusnya.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "accept": ".xlsx",
            }
        ),
    )
    default_password = forms.CharField(
        label="Password default akun baru",
        help_text="Password ini hanya dipakai untuk akun siswa baru yang terbentuk dari hasil import.",
        widget=forms.PasswordInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "placeholder": "Contoh: siswa12345",
            }
        ),
    )


class StudentRecordForm(forms.ModelForm):
    full_name = forms.CharField(
        label="Nama lengkap",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama lengkap siswa"}),
    )
    username = forms.CharField(
        label="Username login",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Username akun siswa"}),
    )
    email = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "opsional@email.com"}),
    )
    phone_number = forms.CharField(
        label="Nomor HP",
        required=False,
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "08xxxxxxxxxx"}),
    )
    password = forms.CharField(
        label="Password login",
        required=False,
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Isi untuk password akun"}),
        help_text="Wajib diisi saat membuat siswa baru. Kosongkan saat edit bila tidak ingin mengubah password.",
    )
    is_school_active = forms.BooleanField(
        label="Akun sekolah aktif",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        help_text="Nonaktifkan bila akun login siswa tidak boleh digunakan.",
    )

    class Meta:
        model = StudentProfile
        fields = [
            "nis",
            "nisn",
            "gender",
            "birth_place",
            "birth_date",
            "address",
            "father_name",
            "father_nik",
            "father_birth_place",
            "father_birth_date",
            "father_education",
            "father_job",
            "mother_name",
            "mother_nik",
            "mother_birth_place",
            "mother_birth_date",
            "mother_education",
            "mother_job",
            "guardian_name",
            "family_status",
            "special_needs",
            "disability_notes",
            "kip_number",
            "class_name",
            "study_group",
            "entry_year",
            "is_active",
        ]
        widgets = {
            "nis": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Kosongkan agar diisi otomatis"}),
            "nisn": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor Induk Siswa Nasional"}),
            "gender": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "birth_place": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Tempat lahir"}),
            "birth_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "address": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Alamat lengkap siswa"}),
            "father_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama ayah kandung"}),
            "father_nik": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "NIK ayah"}),
            "father_birth_place": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Tempat lahir ayah"}),
            "father_birth_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "father_education": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Pendidikan ayah"}),
            "father_job": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Pekerjaan ayah"}),
            "mother_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama ibu kandung"}),
            "mother_nik": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "NIK ibu"}),
            "mother_birth_place": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Tempat lahir ibu"}),
            "mother_birth_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "mother_education": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Pendidikan ibu"}),
            "mother_job": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Pekerjaan ibu"}),
            "guardian_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama wali / orang tua"}),
            "family_status": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "special_needs": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Tidak ada"}),
            "disability_notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Tidak ada"}),
            "kip_number": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor KIP/PIP bila ada"}),
            "class_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: 7A atau XI Keagamaan"}),
            "study_group": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "entry_year": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 2000}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["study_group"].queryset = StudyGroup.objects.select_related(
            "academic_year",
            "school_class",
        ).order_by("-academic_year__start_date", "school_class__level_order", "name")
        self.fields["family_status"].required = False
        self.fields["family_status"].choices = [("", "Pilih status keluarga")] + list(StudentProfile.FamilyStatus.choices)
        self.fields["family_status"].help_text = "Gunakan status ini untuk menandai kondisi keluarga siswa secara lebih rapi."
        self.fields["father_birth_date"].required = False
        self.fields["mother_birth_date"].required = False

        if self.instance.pk:
            user = self.instance.user
            self.fields["full_name"].initial = user.full_name
            self.fields["username"].initial = user.username
            self.fields["email"].initial = user.email
            self.fields["phone_number"].initial = user.phone_number
            self.fields["is_school_active"].initial = user.is_school_active
        else:
            self.fields["is_school_active"].initial = True
            self.fields["is_active"].initial = True

        self.fields["nis"].help_text = "Kosongkan agar sistem mengisi otomatis dari NSM + 2 digit tahun angkatan + nomor urut 4 digit."

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = CustomUser.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise ValidationError("Username ini sudah digunakan.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not self.instance.pk and not password:
            raise ValidationError("Password wajib diisi untuk siswa baru.")
        return password

    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user if profile.pk else CustomUser(role=CustomUser.Role.STUDENT)

        user.full_name = self.cleaned_data["full_name"]
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.is_school_active = self.cleaned_data["is_school_active"]
        user.role = CustomUser.Role.STUDENT

        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)

        if commit:
            user.save()

        profile.user = user
        if profile.study_group_id:
            profile.class_name = profile.study_group.name

        if profile.family_status is None:
            profile.family_status = ""

        if commit:
            profile.save()

        return profile


class StudentDocumentForm(forms.ModelForm):
    class Meta:
        model = StudentDocument
        fields = ["document_type", "title", "file", "notes"]
        widgets = {
            "document_type": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "title": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Scan KK"}),
            "file": forms.ClearableFileInput(attrs={"class": BASE_INPUT_CLASS}),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Catatan tambahan opsional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document_type"].choices = [("", "Pilih jenis berkas")] + list(StudentDocument.DocumentType.choices)


class PromotionStartForm(forms.ModelForm):
    source_academic_year = forms.ModelChoiceField(
        label="Tahun ajaran asal",
        queryset=AcademicYear.objects.none(),
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    target_academic_year = forms.ModelChoiceField(
        label="Tahun ajaran tujuan",
        queryset=AcademicYear.objects.none(),
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    source_school_class = forms.ModelChoiceField(
        label="Kelas asal",
        queryset=SchoolClass.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
        help_text="Kosongkan bila ingin memproses semua kelas pada tahun ajaran asal.",
    )
    source_study_group = forms.ModelChoiceField(
        label="Rombel asal",
        queryset=StudyGroup.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
        help_text="Opsional. Pilih bila hanya ingin memproses satu rombel.",
    )

    class Meta:
        model = PromotionRun
        fields = ["source_academic_year", "target_academic_year", "source_school_class", "source_study_group"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_academic_year"].queryset = AcademicYear.objects.order_by("-start_date")
        self.fields["target_academic_year"].queryset = AcademicYear.objects.order_by("-start_date")
        self.fields["target_academic_year"].help_text = "Boleh sama dengan tahun ajaran asal jika yang diproses adalah kelas terminal seperti kelas 9."
        self.fields["source_school_class"].queryset = SchoolClass.objects.filter(
            study_groups__students__isnull=False,
        ).distinct().order_by("level_order", "name")
        self.fields["source_study_group"].queryset = StudyGroup.objects.filter(
            students__isnull=False,
        ).select_related("academic_year", "school_class").distinct().order_by(
            "-academic_year__start_date",
            "school_class__level_order",
            "name",
        )

    def clean(self):
        cleaned_data = super().clean()
        source_year = cleaned_data.get("source_academic_year")
        target_year = cleaned_data.get("target_academic_year")
        school_class = cleaned_data.get("source_school_class")
        study_group = cleaned_data.get("source_study_group")

        if source_year and target_year and source_year == target_year:
            terminal_class = school_class or (study_group.school_class if study_group else None)
            if not terminal_class:
                self.add_error("target_academic_year", "Pilih kelas terminal jika ingin memakai tahun ajaran yang sama.")
            else:
                next_class_exists = SchoolClass.objects.filter(
                    level_order__gt=terminal_class.level_order,
                    is_active=True,
                ).exists()
                if next_class_exists:
                    self.add_error("target_academic_year", "Tahun ajaran tujuan harus berbeda, kecuali untuk kelas terminal seperti kelas 9.")

        if study_group and source_year and study_group.academic_year_id != source_year.id:
            self.add_error("source_study_group", "Rombel asal harus sesuai tahun ajaran asal.")

        if study_group and school_class and study_group.school_class_id != school_class.id:
            self.add_error("source_study_group", "Rombel asal harus sesuai kelas asal.")

        return cleaned_data


class StudentAlumniDocumentForm(forms.ModelForm):
    class Meta:
        model = StudentAlumniDocument
        fields = ["document_type", "title", "file", "notes"]
        widgets = {
            "document_type": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "title": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Scan ijazah asli"}),
            "file": forms.ClearableFileInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Keterangan tambahan opsional"}),
        }


class StudentAlumniValidationForm(forms.ModelForm):
    class Meta:
        model = StudentAlumniValidation
        fields = [
            "government_name",
            "government_nisn",
            "government_birth_date",
            "government_father_name",
            "diploma_name",
            "family_card_name",
            "birth_certificate_name",
            "notes",
        ]
        labels = {
            "government_name": "Nama sistem",
            "government_nisn": "NISN sistem",
            "government_birth_date": "Tanggal lahir sistem",
            "government_father_name": "Nama ayah sistem",
            "diploma_name": "Nama ijazah",
            "family_card_name": "Nama KK",
            "birth_certificate_name": "Nama akta",
            "notes": "Catatan",
        }
        widgets = {
            "government_name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama dari sistem pemerintah / referensi resmi"}
            ),
            "government_nisn": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "NISN dari sistem"}
            ),
            "government_birth_date": forms.DateInput(
                attrs={"class": BASE_INPUT_CLASS, "type": "date"}
            ),
            "government_father_name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama ayah dari sistem"}
            ),
            "diploma_name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama pada ijazah"}
            ),
            "family_card_name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama pada KK"}
            ),
            "birth_certificate_name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama pada akta kelahiran"}
            ),
            "notes": forms.Textarea(
                attrs={"class": BASE_INPUT_CLASS, "rows": 4, "placeholder": "Catatan validasi, misalnya perbedaan ejaan atau perbaikan data"}
            ),
        }


class StudentMutationRecordForm(forms.ModelForm):
    class Meta:
        model = StudentMutationRecord
        fields = [
            "student",
            "direction",
            "mutation_date",
            "origin_school_name",
            "origin_school_npsn",
            "destination_school_name",
            "destination_school_npsn",
            "origin_study_group",
            "destination_study_group",
            "reason",
            "notes",
            "supporting_document",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "direction": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "mutation_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "origin_school_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama sekolah asal"}),
            "origin_school_npsn": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "NPSN sekolah asal"}),
            "destination_school_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama sekolah tujuan"}),
            "destination_school_npsn": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "NPSN sekolah tujuan"}),
            "origin_study_group": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "destination_study_group": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "reason": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Alasan mutasi"}),
            "notes": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Catatan tambahan"}),
            "supporting_document": forms.ClearableFileInput(
                attrs={"class": BASE_INPUT_CLASS, "accept": ".pdf,.jpg,.jpeg,.png"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = StudentProfile.objects.select_related("user").order_by("user__full_name")
        self.fields["origin_study_group"].queryset = StudyGroup.objects.select_related(
            "academic_year",
            "school_class",
        ).order_by("-academic_year__start_date", "school_class__level_order", "name")
        self.fields["destination_study_group"].queryset = StudyGroup.objects.select_related(
            "academic_year",
            "school_class",
        ).order_by("-academic_year__start_date", "school_class__level_order", "name")

    def clean(self):
        cleaned_data = super().clean()
        direction = cleaned_data.get("direction")
        if direction == StudentMutationRecord.Direction.INBOUND and not cleaned_data.get("origin_school_name"):
            self.add_error("origin_school_name", "Sekolah asal wajib diisi untuk mutasi masuk.")
        if direction == StudentMutationRecord.Direction.OUTBOUND and not cleaned_data.get("destination_school_name"):
            self.add_error("destination_school_name", "Sekolah tujuan wajib diisi untuk mutasi keluar.")
        return cleaned_data
