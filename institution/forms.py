from django import forms

from .models import SchoolIdentity


BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class SchoolIdentityForm(forms.ModelForm):
    class Meta:
        model = SchoolIdentity
        fields = [
            "institution_name",
            "npsn",
            "nsm",
            "legal_name",
            "address",
            "village",
            "district",
            "regency",
            "province",
            "postal_code",
            "phone_number",
            "email",
            "website",
            "principal_name",
            "principal_nip",
            "operator_name",
            "operator_phone",
            "letter_footer",
        ]
        widgets = {
            "institution_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: MTs Sunan Kalijaga Tulung"}),
            "npsn": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor Pokok Sekolah Nasional"}),
            "nsm": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor Statistik Madrasah"}),
            "legal_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama lembaga resmi bila berbeda"}),
            "address": forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 3, "placeholder": "Alamat lengkap madrasah"}),
            "village": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Desa / kelurahan"}),
            "district": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Kecamatan"}),
            "regency": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Kabupaten / kota"}),
            "province": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Provinsi"}),
            "postal_code": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Kode pos"}),
            "phone_number": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor telepon madrasah"}),
            "email": forms.EmailInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Email resmi madrasah"}),
            "website": forms.URLInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "https://..." }),
            "principal_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama kepala madrasah"}),
            "principal_nip": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "NIP kepala madrasah"}),
            "operator_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama operator"}),
            "operator_phone": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nomor operator"}),
            "letter_footer": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Contoh: Melayani dengan cepat dan tepat"}),
        }

