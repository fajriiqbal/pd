from django import forms
from django.utils import timezone

from academics.models import StudyGroup
from institution.models import SchoolIdentity

from .models import ExamScheduleItem, ExamSession


BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class ExamSessionForm(forms.ModelForm):
    class Meta:
        model = ExamSession
        fields = ["name", "academic_year", "semester", "start_date", "end_date", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: PAS Semester Ganjil 2026/2027"}),
            "academic_year": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "semester": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "start_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 4, "placeholder": "Keterangan singkat sesi ujian"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }


class ExamScheduleItemForm(forms.ModelForm):
    class Meta:
        model = ExamScheduleItem
        fields = [
            "session",
            "exam_date",
            "title",
            "item_type",
            "start_time",
            "end_time",
            "description",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "session": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "exam_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "title": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: IPA"}),
            "item_type": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "start_time": forms.TimeInput(attrs={"class": BASE_INPUT_CLASS, "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": BASE_INPUT_CLASS, "type": "time"}),
            "description": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Ruang 1"}),
            "sort_order": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }


class ExamScheduleGenerateForm(forms.Form):
    session = forms.ModelChoiceField(
        queryset=ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name"),
        label="Sesi ujian",
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    start_date = forms.DateField(
        label="Tanggal mulai",
        widget=forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
    )
    day_count = forms.IntegerField(
        label="Jumlah hari",
        min_value=1,
        max_value=14,
        initial=6,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1, "max": 14}),
    )
    sessions_per_day = forms.IntegerField(
        label="Mapel per hari",
        min_value=1,
        max_value=4,
        initial=2,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1, "max": 4}),
    )
    exam_start_time = forms.TimeField(
        label="Jam mulai",
        initial="07:30",
        widget=forms.TimeInput(attrs={"class": BASE_INPUT_CLASS, "type": "time"}),
    )
    exam_duration_minutes = forms.IntegerField(
        label="Durasi mapel (menit)",
        min_value=30,
        max_value=240,
        initial=90,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 30, "max": 240}),
    )
    break_minutes = forms.IntegerField(
        label="Istirahat (menit)",
        min_value=5,
        max_value=120,
        initial=30,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 5, "max": 120}),
    )
    subjects_text = forms.CharField(
        label="Daftar mata pelajaran",
        widget=forms.Textarea(
            attrs={
                "class": BASE_INPUT_CLASS,
                "rows": 8,
                "placeholder": "Tulis satu mapel per baris.\nContoh:\nIPA\nMatematika\nBahasa Indonesia\n...",
            }
        ),
        help_text="Satu baris satu mata pelajaran. Sistem akan mengacak urutannya saat generate.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_session = ExamSession.objects.filter(is_active=True).select_related("academic_year").first()
        if active_session and not self.is_bound:
            self.fields["session"].initial = active_session.pk
            self.fields["start_date"].initial = active_session.start_date
        if not self.is_bound:
            self.fields["subjects_text"].initial = "IPA\nMatematika\nBahasa Indonesia\nBahasa Inggris\nFiqih\nAkidah Akhlak\nSKI\nQur'an Hadis\nIPS\nPKN\nSeni Budaya\nPenjaskes"


class ExamPrintForm(forms.Form):
    session = forms.ModelChoiceField(
        queryset=ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name"),
        label="Sesi ujian",
        required=False,
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    study_group = forms.ModelChoiceField(
        queryset=StudyGroup.objects.select_related("academic_year", "school_class").filter(is_active=True).order_by(
            "school_class__level_order",
            "name",
        ),
        label="Rombel",
        required=False,
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    exam_date = forms.DateField(
        label="Tanggal cetak",
        required=False,
        widget=forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
    )
    room_name = forms.CharField(
        label="Ruang",
        required=False,
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Ruang 1"}),
    )
    supervisor_name = forms.CharField(
        label="Pengawas",
        required=False,
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama pengawas"}),
    )
    schedule_session = forms.ModelChoiceField(
        queryset=ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name"),
        label="Sesi jadwal",
        required=False,
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_session = ExamSession.objects.filter(is_active=True).select_related("academic_year").first()
        if active_session and not self.is_bound:
            self.fields["session"].initial = active_session.pk
        active_group = StudyGroup.objects.filter(is_active=True).select_related("academic_year", "school_class").order_by(
            "school_class__level_order",
            "name",
        ).first()
        if active_group and not self.is_bound:
            self.fields["study_group"].initial = active_group.pk
            self.fields["room_name"].initial = active_group.room_name

        school_identity = SchoolIdentity.objects.first()
        if school_identity and not self.is_bound:
            self.fields["supervisor_name"].initial = school_identity.principal_name
        if active_session and not self.is_bound:
            self.fields["schedule_session"].initial = active_session.pk
        if not self.is_bound:
            self.fields["exam_date"].initial = timezone.localdate()
