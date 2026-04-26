import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from students.models import PromotionRun, PromotionRunItem
from students.models import StudentProfile
from teachers.models import TeacherProfile
from institution.models import SchoolIdentity

from .models import AcademicYear, ClassSubject, GradeBook, PbmScheduleSlot, StudentGrade, SchoolClass, StudyGroup, Subject


class AcademicDetailViewTests(TestCase):
    def setUp(self):
        self.operator = CustomUser.objects.create_user(
            username="operator-akademik",
            password="rahasia123",
            full_name="Operator Akademik",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.operator)

        SchoolIdentity.objects.create(
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
            capacity=32,
            room_name="Ruang A1",
        )
        student_user = CustomUser.objects.create_user(
            username="siswa-7a",
            password="rahasia123",
            full_name="Siswa Kelas Tujuh",
            role=CustomUser.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            user=student_user,
            nis="7001",
            nisn="700100",
            gender=StudentProfile.Gender.MALE,
            class_name=self.study_group.name,
            study_group=self.study_group,
            entry_year=2025,
            is_active=True,
        )
        homeroom_user = CustomUser.objects.create_user(
            username="guru-wali",
            password="rahasia123",
            full_name="Guru Wali",
            role=CustomUser.Role.TEACHER,
        )
        self.homeroom_teacher = TeacherProfile.objects.create(
            user=homeroom_user,
            gender=TeacherProfile.Gender.FEMALE,
            birth_place="Kota",
            birth_date="1990-01-01",
            address="Alamat guru wali",
        )
        self.study_group.homeroom_teacher = self.homeroom_teacher
        self.study_group.save(update_fields=["homeroom_teacher"])
        other_teacher_user = CustomUser.objects.create_user(
            username="guru-bukan-wali",
            password="rahasia123",
            full_name="Guru Bukan Wali",
            role=CustomUser.Role.TEACHER,
        )
        self.other_teacher = TeacherProfile.objects.create(
            user=other_teacher_user,
            gender=TeacherProfile.Gender.MALE,
            birth_place="Kota",
            birth_date="1991-01-01",
            address="Alamat guru lain",
        )

    def test_overview_shows_view_links_for_class_and_study_group(self):
        response = self.client.get(reverse("academics:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("academics:class_detail", args=[self.school_class.pk]))
        self.assertContains(response, reverse("academics:group_detail", args=[self.study_group.pk]))

    def test_class_detail_renders_professional_summary(self):
        response = self.client.get(reverse("academics:class_detail", args=[self.school_class.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pusat kelas")
        self.assertContains(response, "Raport kelas")
        self.assertContains(response, "7A")
        self.assertContains(response, "1")

    def test_study_group_detail_renders_student_and_academic_tools(self):
        response = self.client.get(reverse("academics:group_detail", args=[self.study_group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pusat rombel")
        self.assertContains(response, "Siswa Kelas Tujuh")
        self.assertContains(response, "Raport rombel")
        self.assertContains(response, "Ledger nilai")
        self.assertContains(response, "Edit siswa")

    def test_study_group_detail_blocks_non_homeroom_teacher(self):
        self.client.logout()
        self.client.force_login(self.other_teacher.user)

        response = self.client.get(reverse("academics:group_detail", args=[self.study_group.pk]))

        self.assertEqual(response.status_code, 403)

    def test_homeroom_teacher_can_access_group_detail(self):
        self.client.logout()
        self.client.force_login(self.homeroom_teacher.user)

        response = self.client.get(reverse("academics:group_detail", args=[self.study_group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit siswa")

    def test_subject_ledger_report_and_student_academic_detail_workflow(self):
        subject = Subject.objects.create(name="Fikih", code="FK", category=Subject.Category.RELIGION)
        class_subject = ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            minimum_score=75,
            weekly_hours=2,
        )

        response = self.client.get(reverse("academics:subject_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fikih")

        response = self.client.post(
            reverse("academics:ledger_add"),
            {
                "academic_year": str(self.academic_year.pk),
                "study_group": str(self.study_group.pk),
                "class_subject": str(class_subject.pk),
                "semester": GradeBook.Semester.ODD,
                "notes": "Ledger ganjil",
            },
        )

        grade_book = GradeBook.objects.get()
        self.assertRedirects(response, reverse("academics:ledger_detail", args=[grade_book.pk]))
        grade = StudentGrade.objects.get(grade_book=grade_book, student=self.student)

        response = self.client.post(
            reverse("academics:ledger_detail", args=[grade_book.pk]),
            {
                f"knowledge_{grade.pk}": "88",
                f"skill_{grade.pk}": "90",
                f"attitude_{grade.pk}": StudentGrade.Attitude.A,
                f"notes_{grade.pk}": "Aktif berdiskusi.",
                "action": "lock",
            },
        )

        self.assertRedirects(response, reverse("academics:ledger_detail", args=[grade_book.pk]))
        grade.refresh_from_db()
        grade_book.refresh_from_db()
        self.assertEqual(grade.final_score, 89)
        self.assertEqual(grade_book.status, GradeBook.Status.LOCKED)

        report_response = self.client.get(reverse("academics:group_report", args=[self.study_group.pk]))
        self.assertEqual(report_response.status_code, 200)
        self.assertContains(report_response, "Raport 7A")
        self.assertContains(report_response, "89")

        student_response = self.client.get(reverse("students:detail", args=[self.student.pk]))
        self.assertEqual(student_response.status_code, 200)
        self.assertContains(student_response, "Profil akademik")
        self.assertContains(student_response, "Fikih")
        self.assertContains(student_response, "89")

    def test_subject_can_be_created_from_curriculum_catalog(self):
        response = self.client.post(
            reverse("academics:subject_add"),
            {
                "curriculum": Subject.Curriculum.K13,
                "preset_subject": "k13-fikih",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("academics:subject_list"))
        subject = Subject.objects.get(code="FK-K13")
        self.assertEqual(subject.name, "Fikih")
        self.assertEqual(subject.curriculum, Subject.Curriculum.K13)
        self.assertEqual(subject.category, Subject.Category.RELIGION)

    def test_curriculum_dashboard_shows_workflow_summary(self):
        subject = Subject.objects.create(name="Matematika", code="MTK", category=Subject.Category.GENERAL)
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=4,
        )

        response = self.client.get(reverse("academics:curriculum"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kurikulum")
        self.assertContains(response, "Struktur kurikulum")
        self.assertContains(response, "Matematika")
        self.assertContains(response, "Beban guru")

    def test_curriculum_structure_page_lists_subject_rows(self):
        subject = Subject.objects.create(name="IPA", code="IPA", category=Subject.Category.GENERAL)
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            teacher=self.homeroom_teacher,
            minimum_score=78,
            weekly_hours=4,
        )

        response = self.client.get(reverse("academics:curriculum_structure"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Struktur Kurikulum")
        self.assertContains(response, "IPA")
        self.assertContains(response, "Guru Wali")
        self.assertContains(response, "78")

    def test_pbm_schedule_list_groups_slots_by_class_and_day(self):
        subject = Subject.objects.create(name="Bahasa Indonesia", code="BIN", category=Subject.Category.GENERAL)
        class_subject = ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=4,
        )
        PbmScheduleSlot.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class,
            day_of_week=PbmScheduleSlot.DayOfWeek.MONDAY,
            lesson_order=1,
            start_time="07:30",
            end_time="08:10",
            class_subject=class_subject,
            room_name="Ruang A1",
        )

        response = self.client.get(reverse("academics:pbm_schedule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jadwal PBM")
        self.assertContains(response, "Senin")
        self.assertContains(response, "Bahasa Indonesia")
        self.assertContains(response, "Ruang A1")

    def test_pbm_schedule_generator_builds_preview(self):
        subject_a = Subject.objects.create(name="Matematika", code="MTK", category=Subject.Category.GENERAL)
        subject_b = Subject.objects.create(name="IPA", code="IPA", category=Subject.Category.GENERAL)
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject_a,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=2,
        )
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject_b,
            teacher=self.other_teacher,
            minimum_score=75,
            weekly_hours=2,
        )

        response = self.client.post(
            reverse("academics:pbm_schedule_generate"),
            {
                "academic_year": str(self.academic_year.pk),
                "school_class": str(self.school_class.pk),
                "start_time": "07:30",
                "end_time": "10:30",
                "lesson_duration_minutes": 40,
                "break_after_lessons": 2,
                "break_duration_minutes": 30,
                "randomize": "on",
                "overwrite_existing": "on",
                "action": "generate",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview jadwal")
        self.assertContains(response, "Generate ulang")
        self.assertContains(response, "Istirahat")
        self.assertContains(response, "Matematika")
        self.assertContains(response, "IPA")

    def test_pbm_schedule_generator_can_save_preview(self):
        subject = Subject.objects.create(name="Bahasa Inggris", code="BIG", category=Subject.Category.GENERAL)
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=3,
        )

        self.client.post(
            reverse("academics:pbm_schedule_generate"),
            {
                "academic_year": str(self.academic_year.pk),
                "school_class": str(self.school_class.pk),
                "start_time": "07:30",
                "end_time": "11:00",
                "lesson_duration_minutes": 40,
                "break_after_lessons": 2,
                "break_duration_minutes": 30,
                "randomize": "on",
                "overwrite_existing": "on",
                "action": "generate",
            },
        )
        preview = self.client.session.get("pbm_schedule_preview")
        self.assertIsNotNone(preview)

        response = self.client.post(
            reverse("academics:pbm_schedule_generate"),
            {
                "preview_token": preview["token"],
                "action": "save",
            },
        )

        self.assertRedirects(response, reverse("academics:pbm_schedule_list"))
        self.assertTrue(
            PbmScheduleSlot.objects.filter(
                academic_year=self.academic_year,
                school_class=self.school_class,
            ).exists()
        )

    def test_curriculum_teacher_hours_page_lists_teacher_totals(self):
        subject_a = Subject.objects.create(name="Matematika", code="MTK", category=Subject.Category.GENERAL)
        subject_b = Subject.objects.create(name="IPA", code="IPA", category=Subject.Category.GENERAL)
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject_a,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=4,
        )
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject_b,
            teacher=self.homeroom_teacher,
            minimum_score=75,
            weekly_hours=3,
        )

        response = self.client.get(reverse("academics:curriculum_teacher_hours"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rekap Jam PBM")
        self.assertContains(response, "Guru Wali")
        self.assertContains(response, "7")
        self.assertContains(response, "Matematika")
        self.assertContains(response, "IPA")

    def test_new_academic_year_can_clone_previous_study_groups(self):
        target_school_class = SchoolClass.objects.create(name="Kelas 8", level_order=8)

        response = self.client.post(
            reverse("academics:year_add"),
            {
                "name": "2026/2027",
                "start_date": "2026-07-01",
                "end_date": "2027-06-30",
                "is_active": "on",
                "clone_study_groups": "on",
            },
        )

        self.assertRedirects(response, reverse("academics:year_list"))
        target_year = AcademicYear.objects.get(name="2026/2027")
        cloned_group = StudyGroup.objects.get(academic_year=target_year, name="8A")

        self.assertEqual(cloned_group.school_class, target_school_class)
        self.assertEqual(cloned_group.homeroom_teacher, self.homeroom_teacher)
        self.assertEqual(cloned_group.capacity, self.study_group.capacity)
        self.assertEqual(cloned_group.room_name, self.study_group.room_name)
        self.assertEqual(cloned_group.notes, self.study_group.notes)
        self.assertTrue(cloned_group.is_active)

    def test_year_list_disables_delete_action_when_year_still_has_study_groups(self):
        response = self.client.get(reverse("academics:year_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("academics:year_delete", args=[self.academic_year.pk]))
        self.assertContains(response, 'title="Tidak bisa dihapus karena masih memiliki rombel"')
        self.assertContains(response, "Hapus")

    def test_active_year_delete_is_blocked_before_protected_error(self):
        response = self.client.post(reverse("academics:year_delete", args=[self.academic_year.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tahun ajaran aktif tidak bisa dihapus")
        self.assertTrue(AcademicYear.objects.filter(pk=self.academic_year.pk).exists())

    def test_year_delete_is_blocked_when_used_by_promotion_run(self):
        target_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
        )
        PromotionRun.objects.create(
            source_academic_year=self.academic_year,
            target_academic_year=target_year,
            created_by=self.operator,
        )

        response = self.client.post(reverse("academics:year_delete", args=[target_year.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "masih dipakai oleh proses kenaikan kelas")
        self.assertTrue(AcademicYear.objects.filter(pk=target_year.pk).exists())

    def test_study_group_delete_is_blocked_when_used_by_promotion_items(self):
        target_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
        )
        target_group = StudyGroup.objects.create(
            academic_year=target_year,
            school_class=self.school_class,
            name="7B",
            capacity=32,
        )
        promotion_run = PromotionRun.objects.create(
            source_academic_year=self.academic_year,
            target_academic_year=target_year,
            created_by=self.operator,
        )
        PromotionRunItem.objects.create(
            promotion_run=promotion_run,
            student=self.student,
            source_study_group=self.study_group,
            target_study_group=target_group,
            action=PromotionRunItem.Action.PROMOTE,
        )

        response = self.client.post(reverse("academics:group_delete", args=[target_group.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "masih dipakai data lain")
        self.assertTrue(StudyGroup.objects.filter(pk=target_group.pk).exists())


class SubjectApiTests(TestCase):
    def setUp(self):
        self.operator = CustomUser.objects.create_user(
            username="operator-api",
            password="rahasia123",
            full_name="Operator API",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.operator)

    def test_subject_api_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("api_subject_list"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Autentikasi diperlukan.")

    def test_subject_api_lists_and_filters_subjects(self):
        Subject.objects.create(name="Fikih", code="FK", category=Subject.Category.RELIGION, sort_order=2)
        Subject.objects.create(name="Matematika", code="MTK", category=Subject.Category.GENERAL, sort_order=1)

        response = self.client.get(reverse("api_subject_list"), {"q": "fik"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], "Fikih")
        self.assertEqual(payload["results"][0]["curriculum"], Subject.Curriculum.SHARED)
        self.assertEqual(payload["results"][0]["category_label"], "Keagamaan")

    def test_subject_api_creates_subject_with_defaults(self):
        response = self.client.post(
            reverse("api_subject_list"),
            data=json.dumps(
                {
                    "name": "Akidah Akhlak",
                    "code": "AA",
                    "category": Subject.Category.RELIGION,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Akidah Akhlak")
        self.assertEqual(payload["curriculum"], Subject.Curriculum.SHARED)
        self.assertTrue(payload["is_active"])
        self.assertEqual(payload["sort_order"], 1)
        self.assertTrue(Subject.objects.filter(name="Akidah Akhlak", code="AA").exists())

    def test_subject_api_rejects_invalid_payload(self):
        response = self.client.post(
            reverse("api_subject_list"),
            data=json.dumps({"name": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])

    def test_subject_api_updates_subject(self):
        subject = Subject.objects.create(name="Bahasa Arab", code="BA", category=Subject.Category.RELIGION)

        response = self.client.patch(
            reverse("api_subject_detail", args=[subject.pk]),
            data=json.dumps(
                {
                    "description": "Mapel bahasa Arab dasar",
                    "is_active": False,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        subject.refresh_from_db()
        self.assertEqual(subject.description, "Mapel bahasa Arab dasar")
        self.assertFalse(subject.is_active)

    def test_subject_api_deletes_subject_when_unused(self):
        subject = Subject.objects.create(name="Seni Budaya", code="SB")

        response = self.client.delete(reverse("api_subject_detail", args=[subject.pk]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())

    def test_subject_api_rejects_delete_when_used_by_class(self):
        subject = Subject.objects.create(name="Quran Hadis", code="QH", category=Subject.Category.RELIGION)
        school_class = SchoolClass.objects.create(name="Kelas 8", level_order=8)
        ClassSubject.objects.create(school_class=school_class, subject=subject)

        response = self.client.delete(reverse("api_subject_detail", args=[subject.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())

    def test_subject_api_returns_category_choices(self):
        response = self.client.get(reverse("api_subject_categories"))

        self.assertEqual(response.status_code, 200)
        self.assertIn({"value": Subject.Category.RELIGION, "label": "Keagamaan"}, response.json()["results"])
