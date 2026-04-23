import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from teachers.models import TeacherProfile
from students.models import StudentProfile


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="operator-dashboard",
            password="rahasia123",
            full_name="Operator Dashboard",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.user)
        student_user = CustomUser.objects.create_user(
            username="siswa-cari",
            password="rahasia123",
            full_name="Siswa Cari",
            role=CustomUser.Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=student_user,
            nis="9009",
            nisn="99009900",
            gender=StudentProfile.Gender.MALE,
            class_name="9A",
            entry_year=2025,
            is_active=True,
        )
        teacher_user = CustomUser.objects.create_user(
            username="guru-cari",
            password="rahasia123",
            full_name="Guru Cari",
            role=CustomUser.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            user=teacher_user,
            gender=TeacherProfile.Gender.MALE,
            birth_place="Kota",
            birth_date="1990-01-01",
            address="Alamat guru",
        )

    def test_login_redirect_shows_briefing_popup(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": self.user.username, "password": "rahasia123"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prioritas kerja hari ini")
        self.assertContains(response, "Selamat datang, Operator Dashboard")

    def test_workflow_page_renders_steps(self):
        response = self.client.get(reverse("dashboard:workflow"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flow pengerjaan semester")
        self.assertContains(response, "Tetapkan tahun ajaran aktif")
        self.assertContains(response, "Finalisasi ledger dan cek akun")

    def test_health_endpoint_returns_live_status(self):
        response = self.client.get(reverse("dashboard:health"))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user"], self.user.username)
        self.assertIn("checked_at", payload)

    def test_dashboard_home_shows_social_and_compliance_sections(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoring sosial & bantuan")
        self.assertContains(response, "Siswa yatim")
        self.assertContains(response, "Upload kartu KIP/PIP")
        self.assertContains(response, "Kesehatan data")
        self.assertContains(response, "Kelengkapan data inti")

    def test_global_search_returns_matching_student(self):
        response = self.client.get(reverse("dashboard:search"), {"q": "Siswa Cari"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cari data lintas modul")
        self.assertContains(response, "Siswa Cari")

    def test_admin_sidebar_shows_admin_modules(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Akun Pengguna")
        self.assertContains(response, "Data Guru")
        self.assertContains(response, "Data Siswa")

    def test_teacher_sidebar_is_limited(self):
        self.client.logout()
        teacher = CustomUser.objects.get(username="guru-cari")
        self.client.force_login(teacher)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil Saya")
        self.assertContains(response, "Mapel diajar")
        self.assertNotContains(response, "Data siswa")
        self.assertNotContains(response, "Akun Pengguna")

    def test_student_sidebar_is_limited(self):
        self.client.logout()
        student = CustomUser.objects.get(username="siswa-cari")
        self.client.force_login(student)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil Saya")
        self.assertNotContains(response, "Alumni")
        self.assertNotContains(response, "Akun Pengguna")
