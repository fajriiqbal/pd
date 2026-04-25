from django import forms
from django.utils import timezone

from academics.models import StudyGroup
from institution.models import SchoolIdentity

from .models import ExamSession


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
        if not self.is_bound:
            self.fields["exam_date"].initial = timezone.localdate()
