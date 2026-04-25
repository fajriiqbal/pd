import json

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, SchoolClass, StudyGroup
from accounts.models import CustomUser
from institution.models import SchoolIdentity
from students.models import StudentProfile

from .models import ExamScheduleItem, ExamSession


class ExamMenuTests(TestCase):
    def setUp(self):
        self.operator = CustomUser.objects.create_user(
            username="operator",
            password="rahasia123",
            full_name="Operator",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.operator)

        self.school_identity = SchoolIdentity.objects.create(
            institution_name="MTs Sunan Kalijaga",
            npsn="12345678",
            address="Jl. Pendidikan No. 1",
            district="Kedungwaru",
            regency="Tulungagung",
            province="Jawa Timur",
            principal_name="Ahmad Suyuti",
            principal_nip="197001012000031001",
        )

        self.academic_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(name="Kelas 9", level_order=9)
        self.group = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class,
            name="9A",
            room_name="Ruang 1",
        )
        self.student = self._create_student("siswa-1", "Siswa Satu", "9001", "900100")
        self.session = ExamSession.objects.create(
            name="PAS Ganjil",
            academic_year=self.academic_year,
            semester=ExamSession.Semester.ODD,
            start_date="2026-11-10",
            end_date="2026-11-20",
            is_active=True,
        )
        ExamScheduleItem.objects.create(
            session=self.session,
            exam_date="2026-11-10",
            title="IPA",
            item_type=ExamScheduleItem.ItemType.EXAM,
            start_time="07:30",
            end_time="09:00",
            sort_order=1,
        )
        ExamScheduleItem.objects.create(
            session=self.session,
            exam_date="2026-11-10",
            title="Istirahat",
            item_type=ExamScheduleItem.ItemType.BREAK,
            start_time="09:00",
            end_time="09:30",
            sort_order=2,
        )

    def _create_student(self, username, full_name, nis, nisn):
        user = CustomUser.objects.create_user(
            username=username,
            password="rahasia123",
            full_name=full_name,
            role=CustomUser.Role.STUDENT,
        )
        return StudentProfile.objects.create(
            user=user,
            nis=nis,
            nisn=nisn,
            gender=StudentProfile.Gender.MALE,
            class_name="9A",
            study_group=self.group,
            entry_year=2024,
            is_active=True,
        )

    def test_overview_is_available_for_admin(self):
        response = self.client.get(reverse("exams:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Menu ujian")
        self.assertContains(response, "Kartu ujian")

    def test_overview_is_available_for_teacher(self):
        teacher = CustomUser.objects.create_user(
            username="guru-ujian",
            password="rahasia123",
            full_name="Guru Ujian",
            role=CustomUser.Role.TEACHER,
        )
        self.client.force_login(teacher)
        response = self.client.get(reverse("exams:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Menu ujian")

    def test_print_cards_shows_selected_student(self):
        response = self.client.get(
            reverse("exams:cards"),
            {
                "session": str(self.session.pk),
                "study_group": str(self.group.pk),
                "exam_date": "2026-11-10",
                "print": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kartu Ujian")
        self.assertContains(response, "Siswa Satu")
        self.assertContains(response, "PAS Ganjil")
        self.assertContains(response, "Jadwal Ujian")
        self.assertContains(response, "IPA")
        self.assertContains(response, "07:30 - 09:00")

    def test_schedule_list_renders_exam_timeline(self):
        response = self.client.get(reverse("exams:schedule_list"), {"session": str(self.session.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jadwal ujian")
        self.assertContains(response, "IPA")
        self.assertContains(response, "Istirahat")

    def test_schedule_generate_can_preview_and_save_exact_result(self):
        payload = {
            "session": str(self.session.pk),
            "start_date": "2026-11-10",
            "day_count": 6,
            "sessions_per_day": 2,
            "exam_start_time": "07:30",
            "exam_end_time": "12:00",
            "exam_duration_minutes": 90,
            "break_minutes": 30,
            "subjects_text": "IPA\nMatematika\nBahasa Indonesia",
            "action": "generate",
        }
        preview_response = self.client.post(reverse("exams:schedule_generate"), payload)

        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Preview jadwal")

        preview_rows = preview_response.context["preview_rows"]
        self.assertEqual(len(preview_rows), 18)
        self.assertEqual(sum(1 for row in preview_rows if row["item_type"] == ExamScheduleItem.ItemType.BREAK), 6)

        save_payload = dict(payload)
        save_payload["action"] = "save"
        save_payload["preview_payload"] = preview_response.context["preview_json"]

        save_response = self.client.post(reverse("exams:schedule_generate"), save_payload, follow=True)

        self.assertEqual(save_response.status_code, 200)
        self.assertContains(save_response, "Jadwal ujian otomatis berhasil disimpan.")
        self.assertEqual(ExamScheduleItem.objects.filter(session=self.session).count(), 18)
        self.assertEqual(
            ExamScheduleItem.objects.filter(session=self.session, item_type=ExamScheduleItem.ItemType.BREAK).count(),
            6,
        )

    def test_schedule_generate_supports_three_sessions_per_day_with_longer_window(self):
        payload = {
            "session": str(self.session.pk),
            "start_date": "2026-11-10",
            "day_count": 6,
            "sessions_per_day": 3,
            "exam_start_time": "07:30",
            "exam_end_time": "13:00",
            "exam_duration_minutes": 60,
            "break_minutes": 30,
            "subjects_text": "IPA\nMatematika\nBahasa Indonesia\nBahasa Inggris",
            "action": "generate",
        }
        response = self.client.post(reverse("exams:schedule_generate"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview jadwal")
        preview_rows = response.context["preview_rows"]
        self.assertEqual(len(preview_rows), 30)
        self.assertEqual(sum(1 for row in preview_rows if row["item_type"] == ExamScheduleItem.ItemType.EXAM), 18)
        self.assertEqual(sum(1 for row in preview_rows if row["item_type"] == ExamScheduleItem.ItemType.BREAK), 12)
