from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import CustomUser
from academics.models import ClassSubject, SchoolClass, Subject

from .models import TeacherAdditionalTask, TeacherArchive, TeacherEducationHistory, TeacherMutationRecord, TeacherProfile

BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class TeacherRecordForm(forms.ModelForm):
    full_name = forms.CharField(
        label="Nama lengkap",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama lengkap guru"}),
    )
    username = forms.CharField(
        label="Username login",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Username akun guru"}),
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
        help_text="Wajib diisi saat membuat guru baru. Kosongkan saat edit bila tidak ingin mengubah password.",
    )
    is_school_active = forms.BooleanField(
        label="Akun sekolah aktif",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        help_text="Nonaktifkan bila akun login guru tidak boleh digunakan.",
    )

    class Meta:
        model = TeacherProfile
        fields = [
            "nip",
            "nik",
            "nuptk",
            "subject",
            "task",
            "placement",
            "total_jtm",
            "gender",
            "birth_place",
            "birth_date",
            "address",
            "hire_date",
            "madrasah_email",
            "employment_status",
            "is_active",
        ]
        widgets = {
            "nip": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor Induk Pegawai"}),
            "nik": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor Induk Kependudukan"}),
            "nuptk": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor NUPTK"}),
            "subject": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Fikih, Matematika"}),
            "task": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Guru Mapel / Wali Kelas"}),
            "placement": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: MTs / MA / Kampus 1"}),
            "total_jtm": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0}),
            "gender": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "birth_place": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Tempat lahir"}),
            "birth_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "address": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Alamat lengkap guru"}),
            "hire_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "madrasah_email": forms.EmailInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "akun@madrasah.id"}),
            "employment_status": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            raise ValidationError("Password wajib diisi untuk guru baru.")
        return password

    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user if profile.pk else CustomUser(role=CustomUser.Role.TEACHER)

        user.full_name = self.cleaned_data["full_name"]
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.is_school_active = self.cleaned_data["is_school_active"]
        user.role = CustomUser.Role.TEACHER

        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)

        if commit:
            user.save()

        profile.user = user
        if commit:
            profile.save()

        return profile


class TeacherImportUploadForm(forms.Form):
    excel_file = forms.FileField(
        label="File Excel guru",
        help_text="Gunakan file .xlsx dengan header seperti template data guru.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "accept": ".xlsx",
            }
        ),
    )
    default_password = forms.CharField(
        label="Password default akun baru",
        help_text="Dipakai jika kolom Password Awal di Excel kosong.",
        widget=forms.PasswordInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "placeholder": "Contoh: guru12345",
            }
        ),
    )


class TeacherAdditionalTaskForm(forms.ModelForm):
    class Meta:
        model = TeacherAdditionalTask
        fields = [
            "teacher",
            "name",
            "task_type",
            "description",
            "hours_per_week",
            "start_date",
            "end_date",
            "is_active",
        ]
        widgets = {
            "teacher": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Pembina OSIS"}),
            "task_type": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "description": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Keterangan singkat tugas"}),
            "hours_per_week": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0}),
            "start_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = TeacherProfile.objects.select_related("user").filter(
            is_active=True
        ).order_by("user__full_name")
        if not self.instance.pk:
            self.fields["is_active"].initial = True

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Tanggal selesai tidak boleh sebelum tanggal mulai.")
        return cleaned_data


class TeacherTeachingAssignmentForm(forms.ModelForm):
    class Meta:
        model = ClassSubject
        fields = ["teacher", "school_class", "subject", "minimum_score", "weekly_hours", "notes", "is_active"]
        widgets = {
            "teacher": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "school_class": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "subject": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "minimum_score": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100}),
            "weekly_hours": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0}),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Catatan kurikulum opsional"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].required = True
        self.fields["teacher"].queryset = TeacherProfile.objects.select_related("user").filter(
            is_active=True
        ).order_by("user__full_name")
        self.fields["school_class"].queryset = SchoolClass.objects.filter(is_active=True).order_by(
            "level_order",
            "name",
        )
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True).order_by(
            "curriculum",
            "sort_order",
            "name",
        )
        if not self.instance.pk:
            self.fields["is_active"].initial = True


class TeacherEducationHistoryForm(forms.ModelForm):
    reference_query = forms.CharField(
        label="Cari sekolah/madrasah",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "placeholder": "Cari nama sekolah, madrasah, atau NPSN",
                "autocomplete": "off",
                "data-school-search-input": "true",
            }
        ),
        help_text="Ketik kata kunci lalu pilih hasil dari daftar nasional.",
    )

    class Meta:
        model = TeacherEducationHistory
        fields = [
            "degree_level",
            "institution_name",
            "institution_npsn",
            "institution_level",
            "institution_status",
            "institution_address",
            "institution_source_url",
            "major",
            "graduation_year",
            "certificate_number",
            "certificate_file",
            "notes",
            "is_highest_degree",
        ]
        widgets = {
            "degree_level": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "institution_name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "placeholder": "Pilih dari hasil pencarian sekolah/madrasah",
                    "data-school-name": "true",
                }
            ),
            "institution_npsn": forms.HiddenInput(),
            "institution_level": forms.HiddenInput(),
            "institution_status": forms.HiddenInput(),
            "institution_address": forms.HiddenInput(),
            "institution_source_url": forms.HiddenInput(),
            "major": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Pendidikan Agama Islam"}),
            "graduation_year": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1950, "max": 2100}),
            "certificate_number": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor ijazah"}),
            "certificate_file": forms.ClearableFileInput(
                attrs={"class": BASE_INPUT_CLASS, "accept": ".pdf,.jpg,.jpeg,.png"}
            ),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Keterangan tambahan"}),
            "is_highest_degree": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            "institution_npsn",
            "institution_level",
            "institution_status",
            "institution_address",
            "institution_source_url",
            "certificate_file",
        ]:
            self.fields[field_name].required = False


class TeacherMutationRecordForm(forms.ModelForm):
    class Meta:
        model = TeacherMutationRecord
        fields = [
            "teacher",
            "direction",
            "mutation_date",
            "origin_school_name",
            "destination_school_name",
            "origin_placement",
            "destination_placement",
            "exit_status",
            "reason",
            "notes",
            "supporting_document",
        ]
        widgets = {
            "teacher": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "direction": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "mutation_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "origin_school_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama sekolah/madrasah asal"}),
            "destination_school_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama sekolah/madrasah tujuan"}),
            "origin_placement": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Penempatan awal"}),
            "destination_placement": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Penempatan tujuan"}),
            "exit_status": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "reason": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Alasan mutasi"}),
            "notes": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Catatan tambahan"}),
            "supporting_document": forms.ClearableFileInput(
                attrs={"class": BASE_INPUT_CLASS, "accept": ".pdf,.jpg,.jpeg,.png"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = TeacherProfile.objects.select_related("user").order_by("user__full_name")
        if not self.instance.pk:
            self.fields["exit_status"].required = False

    def clean(self):
        cleaned_data = super().clean()
        direction = cleaned_data.get("direction")
        if direction == TeacherMutationRecord.Direction.INBOUND and not cleaned_data.get("origin_school_name"):
            self.add_error("origin_school_name", "Sekolah asal wajib diisi untuk mutasi masuk.")
        if direction == TeacherMutationRecord.Direction.OUTBOUND:
            if not cleaned_data.get("destination_school_name"):
                self.add_error("destination_school_name", "Sekolah tujuan wajib diisi untuk mutasi keluar.")
            if not cleaned_data.get("exit_status"):
                self.add_error("exit_status", "Status keluar wajib diisi untuk guru yang keluar.")
        return cleaned_data
