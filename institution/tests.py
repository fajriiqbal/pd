from io import BytesIO

from PIL import Image
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import CustomUser

from .models import SchoolIdentity


def build_sample_png():
    buffer = BytesIO()
    image = Image.new("RGB", (1, 1), color=(31, 41, 55))
    image.save(buffer, format="PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")


class SchoolIdentitySetupTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="operator",
            password="testpass123",
            full_name="Operator Madrasah",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.user)

    def test_dashboard_redirects_to_identity_setup_when_missing(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("institution:setup"), response.url)

    def test_setup_view_saves_single_identity_record(self):
        response = self.client.post(
            reverse("institution:setup"),
            data={
                "next": reverse("dashboard:home"),
                "logo": build_sample_png(),
                "institution_name": "MTs Sunan Kalijaga",
                "npsn": "12345678",
                "nsm": "MTs123456",
                "legal_name": "MTs Sunan Kalijaga Tulung",
                "address": "Jl. Pendidikan No. 1",
                "village": "Tulung",
                "district": "Kedungwaru",
                "regency": "Tulungagung",
                "province": "Jawa Timur",
                "postal_code": "66215",
                "phone_number": "08123456789",
                "email": "admin@mts.example",
                "website": "https://mts.example",
                "principal_name": "Ahmad Suyuti",
                "principal_nip": "197001012000031001",
                "operator_name": "Siti Aminah",
                "operator_phone": "08129876543",
                "letter_footer": "Melayani dengan cepat dan tepat",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))
        self.assertEqual(SchoolIdentity.objects.count(), 1)
        identity = SchoolIdentity.objects.first()
        self.assertTrue(identity.is_complete)
        self.assertEqual(identity.institution_name, "MTs Sunan Kalijaga")
        self.assertTrue(identity.logo)
