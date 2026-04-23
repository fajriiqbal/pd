from django import forms

from teachers.models import TeacherProfile

from .curriculum import get_subject_preset, subject_preset_choices
from .models import AcademicYear, ClassSubject, GradeBook, SchoolClass, StudyGroup, Subject


BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: 2026/2027"}),
            "start_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }


class SchoolClassForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["name", "level_order", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Kelas 7 atau XI Keagamaan"}),
            "level_order": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1}),
            "description": forms.Textarea(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "rows": 3,
                    "placeholder": "Keterangan singkat kelas atau jenjang ini",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }


class StudyGroupForm(forms.ModelForm):
    class Meta:
        model = StudyGroup
        fields = [
            "academic_year",
            "school_class",
            "name",
            "homeroom_teacher",
            "capacity",
            "room_name",
            "notes",
            "is_active",
        ]
        widgets = {
            "academic_year": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "school_class": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: 7A atau XI Keagamaan 1"}),
            "homeroom_teacher": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "capacity": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1}),
            "room_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Ruang A1"}),
            "notes": forms.Textarea(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "rows": 4,
                    "placeholder": "Catatan tambahan untuk rombel ini",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.order_by("-start_date")
        self.fields["school_class"].queryset = SchoolClass.objects.order_by("level_order", "name")
        self.fields["homeroom_teacher"].queryset = TeacherProfile.objects.select_related("user").filter(
            is_active=True
        ).order_by("user__full_name")


class SubjectForm(forms.ModelForm):
    preset_subject = forms.ChoiceField(
        choices=subject_preset_choices,
        required=False,
        label="Pilih dari katalog",
        help_text="Pilih K13 atau Kurikulum Merdeka agar detail mapel terisi otomatis. Biarkan manual untuk mapel khusus madrasah.",
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS, "data-subject-preset-select": "true"}),
    )

    class Meta:
        model = Subject
        fields = ["curriculum", "name", "code", "category", "description", "sort_order", "is_active"]
        widgets = {
            "curriculum": forms.Select(attrs={"class": BASE_INPUT_CLASS, "data-curriculum-select": "true"}),
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Al-Qur'an Hadis"}),
            "code": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: QH"}),
            "category": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "description": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Keterangan singkat mapel"}),
            "sort_order": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    field_order = ["curriculum", "preset_subject", "name", "code", "category", "description", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["curriculum"].required = False
        self.fields["name"].required = False
        self.fields["category"].required = False
        self.fields["sort_order"].required = False
        self.order_fields(self.field_order)

    def clean(self):
        cleaned_data = super().clean()
        preset_key = cleaned_data.get("preset_subject")
        preset = get_subject_preset(preset_key) if preset_key else None

        if preset:
            cleaned_data["curriculum"] = preset["curriculum"]
            for field_name in ["name", "code", "category", "description", "sort_order"]:
                if not cleaned_data.get(field_name):
                    cleaned_data[field_name] = preset[field_name]
            for field_name in ["curriculum", "name", "category", "sort_order"]:
                if field_name in self.errors:
                    del self.errors[field_name]

        if not cleaned_data.get("curriculum"):
            cleaned_data["curriculum"] = Subject.Curriculum.SHARED
        if not cleaned_data.get("name"):
            self.add_error("name", "Nama mata pelajaran wajib diisi atau pilih dari katalog.")
        if not cleaned_data.get("category"):
            cleaned_data["category"] = Subject.Category.GENERAL
        if not cleaned_data.get("sort_order"):
            cleaned_data["sort_order"] = 1

        return cleaned_data


class ClassSubjectForm(forms.ModelForm):
    class Meta:
        model = ClassSubject
        fields = ["school_class", "subject", "teacher", "minimum_score", "weekly_hours", "notes", "is_active"]
        widgets = {
            "school_class": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "subject": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "teacher": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "minimum_score": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100}),
            "weekly_hours": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0}),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Catatan kurikulum opsional"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = SchoolClass.objects.order_by("level_order", "name")
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True).order_by("sort_order", "name")
        self.fields["teacher"].queryset = TeacherProfile.objects.select_related("user").filter(
            is_active=True
        ).order_by("user__full_name")


class GradeBookForm(forms.ModelForm):
    class Meta:
        model = GradeBook
        fields = ["academic_year", "study_group", "class_subject", "semester", "notes"]
        widgets = {
            "academic_year": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "study_group": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "class_subject": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "semester": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "notes": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Ledger nilai semester ganjil"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.order_by("-start_date")
        self.fields["study_group"].queryset = StudyGroup.objects.select_related(
            "academic_year",
            "school_class",
        ).order_by("-academic_year__start_date", "school_class__level_order", "name")
        self.fields["class_subject"].queryset = ClassSubject.objects.select_related(
            "school_class",
            "subject",
            "teacher__user",
        ).filter(is_active=True).order_by(
            "school_class__level_order",
            "subject__sort_order",
            "subject__name",
        )
