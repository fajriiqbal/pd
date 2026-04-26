from unittest.mock import patch

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, RombelTeachingAssignment, SchoolClass, StudyGroup, Subject
from accounts.models import CustomUser
from institution.models import SchoolIdentity

from .import_utils import build_teacher_import_preview, execute_teacher_import
from .models import TeacherArchive, TeacherEducationHistory, TeacherMutationRecord, TeacherProfile


try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None


class TeacherImportUtilsTests(TestCase):
    def _build_workbook_file(self, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Data Guru"
        sheet.append(
            [
                "Nama Lengkap",
                "NIK",
                "NUPTK",
                "Status Kepegawaian",
                "NIP",
                "Jenis Kelamin",
                "Tempat Lahir",
                "Tanggal Lahir",
                "Nomor Handphone",
                "Email",
                "Email Akun Madrasah Digital",
                "Password Awal",
                "Tugas",
                "Mata Pelajaran",
                "Penempatan",
                "Total JTM",
            ]
        )
        for row in rows:
            sheet.append(row)

        file_obj = BytesIO()
        workbook.save(file_obj)
        file_obj.seek(0)
        file_obj.name = "import-guru.xlsx"
        return file_obj

    def test_import_create_uses_teacher_template_columns(self):
        uploaded_file = self._build_workbook_file(
            [
                [
                    "Ustadz Ahmad",
                    "3201010101010001",
                    "1234567890123456",
                    "Honorer",
                    "",
                    "L",
                    "Bandung",
                    "1988-05-12",
                    "081234567890",
                    "ahmad@example.com",
                    "ahmad@madrasah.test",
                    "awal12345",
                    "Guru Mapel",
                    "Fikih",
                    "MTs",
                    24,
                ]
            ]
        )

        preview = build_teacher_import_preview(uploaded_file, "default123")

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"]["create_count"], 1)
        self.assertEqual(preview["summary"]["error_count"], 0)

        result = execute_teacher_import(preview)

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 0)

        teacher = TeacherProfile.objects.select_related("user").get(nik="3201010101010001")
        self.assertEqual(teacher.user.full_name, "Ustadz Ahmad")
        self.assertEqual(teacher.user.email, "ahmad@example.com")
        self.assertEqual(teacher.user.phone_number, "081234567890")
        self.assertEqual(teacher.madrasah_email, "ahmad@madrasah.test")
        self.assertEqual(teacher.employment_status, TeacherProfile.EmploymentStatus.HONORARY)
        self.assertEqual(teacher.subject, "Fikih")
        self.assertEqual(teacher.task, "Guru Mapel")
        self.assertEqual(teacher.placement, "MTs")
        self.assertEqual(teacher.total_jtm, 24)
        self.assertEqual(teacher.birth_place, "Bandung")
        self.assertEqual(str(teacher.birth_date), "1988-05-12")
        self.assertIsNone(teacher.nip)

    def test_import_update_matches_existing_teacher_by_nuptk(self):
        user = CustomUser.objects.create_user(
            username="guru-lama",
            password="awal12345",
            full_name="Nama Lama",
            role=CustomUser.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            user=user,
            nuptk="9999888877776666",
            gender=TeacherProfile.Gender.FEMALE,
            employment_status=TeacherProfile.EmploymentStatus.PERMANENT,
            subject="Bahasa Indonesia",
            is_active=True,
        )
        uploaded_file = self._build_workbook_file(
            [
                [
                    "Nama Baru",
                    "",
                    "9999888877776666",
                    "Tetap",
                    "19880101",
                    "P",
                    "Garut",
                    "1990-01-01",
                    "089999999999",
                    "baru@example.com",
                    "baru@madrasah.test",
                    "",
                    "Wali Kelas",
                    "Sejarah",
                    "MA",
                    18,
                ]
            ]
        )

        preview = build_teacher_import_preview(uploaded_file, "default123")

        self.assertEqual(preview["summary"]["update_count"], 1)
        self.assertEqual(preview["summary"]["error_count"], 0)

        result = execute_teacher_import(preview)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["failed"], 0)

        teacher = TeacherProfile.objects.select_related("user").get(nuptk="9999888877776666")
        self.assertEqual(teacher.user.full_name, "Nama Baru")
        self.assertEqual(teacher.nip, "19880101")
        self.assertEqual(teacher.subject, "Sejarah")


class TeacherProfileViewTests(TestCase):
    def setUp(self):
        SchoolIdentity.objects.update_or_create(
            pk=1,
            defaults={
                "institution_name": "MTs Sunan Kalijaga",
                "npsn": "12345678",
                "address": "Jl. Pendidikan No. 1",
                "district": "Kedungwaru",
                "regency": "Tulungagung",
                "province": "Jawa Timur",
                "principal_name": "Ahmad Suyuti",
                "principal_nip": "197001012000031001",
            },
        )
        self.operator = CustomUser.objects.create_user(
            username="operator-guru",
            password="rahasia123",
            full_name="Operator Guru",
            role=CustomUser.Role.ADMIN,
        )
        self.teacher_user = CustomUser.objects.create_user(
            username="guru-profil",
            password="rahasia123",
            full_name="Guru Profil",
            role=CustomUser.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, gender=TeacherProfile.Gender.MALE)
        self.academic_year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-07-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(name="Kelas 7", level_order=7)
        self.study_group = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class,
            name="7A",
            is_active=True,
        )
        self.subject = Subject.objects.create(name="Fikih", code="FK", category=Subject.Category.RELIGION)
        self.client.force_login(self.operator)

    def test_teacher_edit_page_renders_profile_sections(self):
        RombelTeachingAssignment.objects.create(
            study_group=self.study_group,
            subject=self.subject,
            teacher=self.teacher,
            weekly_hours=6,
            minimum_score=75,
        )
        response = self.client.get(reverse("teachers:edit", args=[self.teacher.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data Diri")
        self.assertContains(response, "Data Pendidikan")
        self.assertContains(response, "Data Pengajar")
        self.assertContains(response, "7A")
        self.assertContains(response, "Fikih")

    def test_teaching_assignment_list_uses_rombel_data(self):
        RombelTeachingAssignment.objects.create(
            study_group=self.study_group,
            subject=self.subject,
            teacher=self.teacher,
            weekly_hours=6,
            minimum_score=75,
        )
        response = self.client.get(reverse("teachers:teaching_assignments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mapel diajar per rombel")
        self.assertContains(response, "7A")
        self.assertContains(response, "rombel aktif")

    def test_teaching_assignment_update_returns_to_selected_teacher(self):
        assignment = RombelTeachingAssignment.objects.create(
            study_group=self.study_group,
            subject=self.subject,
            teacher=self.teacher,
            weekly_hours=6,
            minimum_score=75,
        )

        response = self.client.post(
            f"{reverse('teachers:teaching_assignment_edit', args=[assignment.pk])}?teacher={self.teacher.pk}",
            {
                "teacher": str(self.teacher.pk),
                "study_group": str(self.study_group.pk),
                "subject": str(self.subject.pk),
                "minimum_score": 75,
                "weekly_hours": 6,
                "notes": "",
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('teachers:teaching_assignments')}?teacher={self.teacher.pk}",
        )

    def test_teacher_education_add_creates_history(self):
        scan_file = SimpleUploadedFile("ijazah-s1.pdf", b"fake-pdf-data", content_type="application/pdf")
        response = self.client.post(
            reverse("teachers:education_add", args=[self.teacher.pk]),
            {
                "degree_level": TeacherEducationHistory.DegreeLevel.S1,
                "institution_name": "UIN Bandung",
                "institution_npsn": "12345678",
                "institution_status": "NEGERI",
                "institution_level": "S1",
                "institution_address": "Bandung, Jawa Barat",
                "institution_source_url": "https://referensi.data.kemdikbud.go.id/tabs.php?npsn=12345678",
                "major": "Pendidikan Agama Islam",
                "graduation_year": 2020,
                "certificate_number": "IJZ-2020-001",
                "notes": "Lulus tepat waktu",
                "is_highest_degree": "on",
                "certificate_file": scan_file,
            },
        )

        self.assertRedirects(response, reverse("teachers:edit", args=[self.teacher.pk]))
        history = TeacherEducationHistory.objects.get(teacher=self.teacher, institution_name="UIN Bandung")
        self.assertTrue(history.is_highest_degree)
        self.assertEqual(history.institution_npsn, "12345678")
        self.assertTrue(history.certificate_file.name.startswith("teacher_diplomas/"))
        self.assertTrue(history.certificate_file.name.endswith(".pdf"))

    @patch("teachers.reference.urlopen")
    def test_school_reference_search_api_returns_results(self, mock_urlopen):
        html = """
            <html><body>
                <table>
                    <tr><th>No</th><th>NPSN</th><th>Nama Satuan Pendidikan</th><th>Alamat</th><th>Kelurahan</th><th>Status</th></tr>
                    <tr><td>1</td><td>12345678</td><td>SDN 1 Contoh</td><td>Jl. Melati</td><td>Kelurahan A</td><td>NEGERI</td></tr>
                </table>
            </body></html>
        """

        class DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return html.encode("utf-8")

        mock_urlopen.return_value = DummyResponse()

        response = self.client.get(reverse("teachers:school_reference_search"), {"q": "contoh"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["npsn"], "12345678")
        self.assertEqual(payload["results"][0]["name"], "SDN 1 Contoh")

    def test_teacher_mutation_outbound_creates_archive_and_disables_teacher(self):
        response = self.client.post(
            reverse("teachers:mutation_add"),
            {
                "teacher": str(self.teacher.pk),
                "direction": TeacherMutationRecord.Direction.OUTBOUND,
                "mutation_date": "2026-04-23",
                "origin_school_name": "MTs Asal",
                "destination_school_name": "MTs Baru",
                "origin_placement": "Kampus 1",
                "destination_placement": "Kampus 2",
                "exit_status": TeacherArchive.ExitStatus.PENSIONED,
                "reason": "Memasuki masa pensiun",
                "notes": "Disetujui pimpinan",
            },
        )

        self.assertRedirects(response, reverse("teachers:edit", args=[self.teacher.pk]))
        self.teacher.refresh_from_db()
        self.teacher_user.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertFalse(self.teacher.user.is_school_active)

        mutation = TeacherMutationRecord.objects.get(teacher=self.teacher)
        self.assertEqual(mutation.direction, TeacherMutationRecord.Direction.OUTBOUND)
        archive = TeacherArchive.objects.get(teacher=self.teacher)
        self.assertEqual(archive.exit_status, TeacherArchive.ExitStatus.PENSIONED)
