import shutil
from io import BytesIO
from pathlib import Path
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicYear, SchoolClass, StudyGroup
from accounts.models import ActivityLog, CustomUser

from .import_utils import build_student_import_preview, execute_student_import
from .models import (
    PromotionRun,
    PromotionRunItem,
    StudentDocument,
    StudentAlumniArchive,
    StudentAlumniDocument,
    StudentAlumniValidation,
    StudentMutationRecord,
    StudentEnrollment,
    StudentProfile,
)


try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - dependency is required in runtime too
    Workbook = None


class StudentImportUtilsTests(TestCase):
    def setUp(self):
        AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-07-01",
            end_date="2026-06-30",
            is_active=True,
        )

    def _build_workbook_file(self, sheet_title, headers, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_title
        sheet.append(headers)

        for row in rows:
            sheet.append(row)

        file_obj = BytesIO()
        workbook.save(file_obj)
        file_obj.seek(0)
        file_obj.name = "import-siswa.xlsx"
        return file_obj

    def test_import_create_supports_common_header_variants(self):
        uploaded_file = self._build_workbook_file(
            sheet_title="Kelas 7 - 7B",
            headers=["NIS", "Nama Siswa", "NISN", "JK", "Tgl. Lahir", "Kelas/Rombel", "No. HP"],
            rows=[["1002", "Siti Aminah", "99887766", "P", "2013-02-01", "Kelas 7 - 7B", "08123456789"]],
        )

        preview = build_student_import_preview(uploaded_file, "rahasia123")

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"]["create_count"], 1)
        self.assertEqual(preview["summary"]["error_count"], 0)

        result = execute_student_import(preview)

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 0)

        student = StudentProfile.objects.select_related("user", "study_group", "study_group__school_class").get(
            nis="1002"
        )
        self.assertEqual(student.user.full_name, "Siti Aminah")
        self.assertEqual(student.user.phone_number, "08123456789")
        self.assertEqual(student.study_group.name, "7B")
        self.assertEqual(student.study_group.school_class.name, "Kelas 7")

    def test_import_create_allows_new_student_without_nis(self):
        uploaded_file = self._build_workbook_file(
            sheet_title="Kelas 8 - 8A",
            headers=["Nama Lengkap", "NISN", "Jenis Kelamin", "Tanggal Lahir"],
            rows=[["Ahmad Tanpa NIS", "88776655", "L", "2012-05-10"]],
        )

        preview = build_student_import_preview(uploaded_file, "rahasia123")

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"]["create_count"], 1)
        self.assertEqual(preview["summary"]["error_count"], 0)

        result = execute_student_import(preview)

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 0)

        student = StudentProfile.objects.select_related("user").get(nisn="88776655")
        self.assertIsNone(student.nis)
        self.assertEqual(student.user.full_name, "Ahmad Tanpa NIS")

    def test_import_update_keeps_existing_nis_when_row_matches_by_nisn(self):
        user = CustomUser.objects.create_user(
            username="siswa-lama",
            password="rahasia123",
            full_name="Nama Lama",
            role=CustomUser.Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=user,
            nis="1001",
            nisn="55667788",
            gender=StudentProfile.Gender.MALE,
            class_name="Kelas 7 - 7A",
            entry_year=2025,
            is_active=True,
        )

        uploaded_file = self._build_workbook_file(
            sheet_title="Kelas 7 - 7A",
            headers=["Nama Lengkap", "NISN", "Jenis Kelamin", "Tanggal Lahir", "Alamat"],
            rows=[["Nama Baru", "55667788", "L", "2012-04-12", "Alamat Baru"]],
        )

        preview = build_student_import_preview(uploaded_file, "rahasia123")

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"]["update_count"], 1)
        self.assertEqual(preview["summary"]["error_count"], 0)

        result = execute_student_import(preview)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["failed"], 0)

        student = StudentProfile.objects.select_related("user").get(nisn="55667788")
        self.assertEqual(student.nis, "1001")
        self.assertEqual(student.user.full_name, "Nama Baru")
        self.assertEqual(student.address, "Alamat Baru")


class StudentListAndBulkDeleteTests(TestCase):
    def setUp(self):
        self.operator = CustomUser.objects.create_user(
            username="operator",
            password="rahasia123",
            full_name="Operator",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.operator)

        self.academic_year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-07-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.school_class_7 = SchoolClass.objects.create(name="Kelas 7", level_order=7)
        self.school_class_8 = SchoolClass.objects.create(name="Kelas 8", level_order=8)
        self.group_7a = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class_7,
            name="7A",
        )
        self.group_8a = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class_8,
            name="8A",
        )
        self.student_7a = self._create_student(
            username="siswa-7a",
            full_name="Siswa Kelas Tujuh",
            nis="7001",
            nisn="700100",
            study_group=self.group_7a,
            is_active=True,
        )
        self.student_8a_without_nis = self._create_student(
            username="siswa-8a",
            full_name="Siswa Tanpa NIS",
            nis=None,
            nisn="800100",
            study_group=self.group_8a,
            is_active=False,
        )

    def _create_student(self, username, full_name, nis, nisn, study_group, is_active):
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
            class_name=study_group.name,
            study_group=study_group,
            entry_year=2025,
            is_active=is_active,
        )

    def test_student_list_filters_by_class_status_and_missing_nis(self):
        response = self.client.get(
            reverse("students:list"),
            {
                "class": str(self.school_class_8.id),
                "status": "inactive",
                "nis_status": "missing",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Siswa Tanpa NIS")
        self.assertNotContains(response, "Siswa Kelas Tujuh")

    def test_student_list_rombel_options_follow_selected_class_and_show_student_totals(self):
        group_7b = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=self.school_class_7,
            name="7B",
        )
        self._create_student(
            username="siswa-7b",
            full_name="Siswa Kelas Tujuh B",
            nis="7002",
            nisn="700200",
            study_group=group_7b,
            is_active=True,
        )

        response = self.client.get(reverse("students:list"), {"class": str(self.school_class_7.id)})
        html = response.content.decode()
        select_start = html.index('id="study-group-filter"')
        select_end = html.index("</select>", select_start)
        study_group_select_html = html[select_start:select_end]

        def option_html(option_value):
            marker = f'value="{option_value}"'
            marker_index = study_group_select_html.index(marker)
            option_start = study_group_select_html.rfind("<option", 0, marker_index)
            option_end = study_group_select_html.find("</option>", marker_index) + len("</option>")
            return study_group_select_html[option_start:option_end]

        group_7a_option = option_html(self.group_7a.id)
        group_7b_option = option_html(group_7b.id)
        group_8a_option = option_html(self.group_8a.id)

        self.assertIn("7A - 1 siswa", " ".join(group_7a_option.split()))
        self.assertIn("7B - 1 siswa", " ".join(group_7b_option.split()))
        self.assertNotIn("hidden disabled", group_7a_option)
        self.assertNotIn("hidden disabled", group_7b_option)
        self.assertIn("hidden disabled", group_8a_option)

    def test_student_list_ignores_study_group_that_does_not_match_selected_class(self):
        response = self.client.get(
            reverse("students:list"),
            {
                "class": str(self.school_class_7.id),
                "study_group": str(self.group_8a.id),
            },
        )

        self.assertEqual(response.context["study_group_id"], "")
        self.assertContains(response, "Siswa Kelas Tujuh")
        self.assertNotContains(response, "Siswa Tanpa NIS")

    def test_promotion_workflow_creates_draft_and_executes_student_move(self):
        target_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
        )
        target_group_8a = StudyGroup.objects.create(
            academic_year=target_year,
            school_class=self.school_class_8,
            name="8A",
        )

        response = self.client.post(
            reverse("students:promotion_create"),
            {
                "source_academic_year": str(self.academic_year.id),
                "target_academic_year": str(target_year.id),
                "source_school_class": str(self.school_class_7.id),
                "source_study_group": "",
            },
        )

        promotion_run = PromotionRun.objects.get()
        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        self.assertEqual(self.client.get(reverse("students:promotion_list")).status_code, 200)
        detail_response = self.client.get(reverse("students:promotion_detail", args=[promotion_run.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Preview kenaikan kelas")
        self.assertContains(detail_response, "8A")
        item = promotion_run.items.get()
        self.assertEqual(item.student, self.student_7a)
        self.assertEqual(item.action, PromotionRunItem.Action.PROMOTE)
        self.assertEqual(item.target_study_group, target_group_8a)

        response = self.client.post(
            reverse("students:promotion_execute", args=[promotion_run.pk]),
            {
                f"action_{item.pk}": PromotionRunItem.Action.PROMOTE,
                f"target_group_{item.pk}": str(target_group_8a.pk),
                f"notes_{item.pk}": "Naik sesuai rombel paralel.",
            },
        )

        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        self.student_7a.refresh_from_db()
        promotion_run.refresh_from_db()
        self.assertEqual(self.student_7a.study_group, target_group_8a)
        self.assertEqual(self.student_7a.class_name, "8A")
        self.assertEqual(promotion_run.status, PromotionRun.Status.EXECUTED)

        source_enrollment = StudentEnrollment.objects.get(
            student=self.student_7a,
            academic_year=self.academic_year,
        )
        target_enrollment = StudentEnrollment.objects.get(
            student=self.student_7a,
            academic_year=target_year,
        )
        self.assertEqual(source_enrollment.study_group, self.group_7a)
        self.assertEqual(target_enrollment.study_group, target_group_8a)
        self.assertEqual(target_enrollment.previous_enrollment, source_enrollment)

    def test_promotion_workflow_graduates_last_class_without_target_group(self):
        self.student_8a_without_nis.is_active = True
        self.student_8a_without_nis.save(update_fields=["is_active"])
        target_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
        )

        response = self.client.post(
            reverse("students:promotion_create"),
            {
                "source_academic_year": str(self.academic_year.id),
                "target_academic_year": str(target_year.id),
                "source_school_class": str(self.school_class_8.id),
                "source_study_group": "",
            },
        )

        promotion_run = PromotionRun.objects.get()
        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        item = promotion_run.items.get()
        self.assertEqual(item.action, PromotionRunItem.Action.GRADUATE)
        self.assertIsNone(item.target_study_group)

        response = self.client.post(
            reverse("students:promotion_execute", args=[promotion_run.pk]),
            {
                f"action_{item.pk}": PromotionRunItem.Action.GRADUATE,
                f"target_group_{item.pk}": "",
                f"notes_{item.pk}": "Lulus.",
            },
        )

        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        self.student_8a_without_nis.refresh_from_db()
        self.assertFalse(self.student_8a_without_nis.is_active)
        self.assertIsNone(self.student_8a_without_nis.study_group)

        target_enrollment = StudentEnrollment.objects.get(
            student=self.student_8a_without_nis,
            academic_year=target_year,
        )
        self.assertEqual(target_enrollment.status, StudentEnrollment.Status.GRADUATED)
        alumni = StudentAlumniArchive.objects.get(student=self.student_8a_without_nis)
        self.assertEqual(alumni.full_name, "Siswa Tanpa NIS")
        self.assertEqual(alumni.graduation_status, StudentAlumniArchive.GraduationStatus.GRADUATED)

    def test_promotion_history_can_be_deleted_from_list(self):
        target_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-07-01",
            end_date="2027-06-30",
        )
        promotion_run = PromotionRun.objects.create(
            source_academic_year=self.academic_year,
            target_academic_year=target_year,
            created_by=self.operator,
            status=PromotionRun.Status.EXECUTED,
            summary={"total": 1},
        )
        item = PromotionRunItem.objects.create(
            promotion_run=promotion_run,
            student=self.student_7a,
            source_study_group=self.group_7a,
            target_study_group=self.group_8a,
            action=PromotionRunItem.Action.PROMOTE,
        )

        response = self.client.post(reverse("students:promotion_delete", args=[promotion_run.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Riwayat kenaikan kelas 2025/2026 ke 2026/2027 berhasil dihapus.")
        self.assertFalse(PromotionRun.objects.filter(pk=promotion_run.pk).exists())
        self.assertFalse(PromotionRunItem.objects.filter(pk=item.pk).exists())

    def test_promotion_workflow_allows_same_year_graduation_for_terminal_class(self):
        school_class_9 = SchoolClass.objects.create(name="Kelas 9", level_order=9)
        group_9a = StudyGroup.objects.create(
            academic_year=self.academic_year,
            school_class=school_class_9,
            name="9A",
        )
        user = CustomUser.objects.create_user(
            username="siswa-9a",
            password="rahasia123",
            full_name="Siswa Kelas Sembilan",
            role=CustomUser.Role.STUDENT,
        )
        student_9a = StudentProfile.objects.create(
            user=user,
            nis="9001",
            nisn="900100",
            gender=StudentProfile.Gender.FEMALE,
            class_name="9A",
            study_group=group_9a,
            entry_year=2023,
            is_active=True,
        )

        response = self.client.post(
            reverse("students:promotion_create"),
            {
                "source_academic_year": str(self.academic_year.id),
                "target_academic_year": str(self.academic_year.id),
                "source_school_class": str(school_class_9.id),
                "source_study_group": "",
            },
        )

        promotion_run = PromotionRun.objects.get()
        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        item = promotion_run.items.get()
        self.assertEqual(item.action, PromotionRunItem.Action.GRADUATE)

        response = self.client.post(
            reverse("students:promotion_execute", args=[promotion_run.pk]),
            {
                f"action_{item.pk}": PromotionRunItem.Action.GRADUATE,
                f"target_group_{item.pk}": "",
                f"notes_{item.pk}": "Kelulusan semester 2.",
            },
        )

        self.assertRedirects(response, reverse("students:promotion_detail", args=[promotion_run.pk]))
        student_9a.refresh_from_db()
        self.assertFalse(student_9a.is_active)
        self.assertIsNone(student_9a.study_group)
        self.assertEqual(StudentEnrollment.objects.filter(student=student_9a).count(), 1)
        enrollment = StudentEnrollment.objects.get(student=student_9a)
        self.assertEqual(enrollment.status, StudentEnrollment.Status.GRADUATED)
        alumni = StudentAlumniArchive.objects.get(student=student_9a)
        self.assertEqual(alumni.graduation_year, 2026)
        self.assertEqual(alumni.class_name, "9A")

    def test_alumni_pages_render_and_accept_documents(self):
        graduation_year = 2026
        alumni = StudentAlumniArchive.objects.create(
            student=self.student_7a,
            full_name=self.student_7a.user.full_name,
            nis=self.student_7a.nis or "",
            nisn=self.student_7a.nisn or "",
            gender=self.student_7a.gender,
            class_name=self.student_7a.class_name,
            entry_year=self.student_7a.entry_year,
            graduation_year=graduation_year,
        )

        response = self.client.get(reverse("students:alumni_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Arsip alumni")

        detail_response = self.client.get(reverse("students:alumni_detail", args=[alumni.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.student_7a.user.full_name)

        doc_file = SimpleUploadedFile("ijazah.pdf", b"pdf-data", content_type="application/pdf")
        upload_response = self.client.post(
            reverse("students:alumni_document_add", args=[alumni.pk]),
            {
                "document_type": StudentAlumniDocument.DocumentType.DIPLOMA,
                "title": "Scan ijazah",
                "notes": "Berkas final",
                "file": doc_file,
            },
        )
        self.assertRedirects(upload_response, reverse("students:alumni_detail", args=[alumni.pk]))
        self.assertEqual(alumni.documents.count(), 1)

    def test_alumni_pages_are_admin_only(self):
        alumni = StudentAlumniArchive.objects.create(
            student=self.student_7a,
            full_name=self.student_7a.user.full_name,
            nis=self.student_7a.nis or "",
            nisn=self.student_7a.nisn or "",
            gender=self.student_7a.gender,
            class_name=self.student_7a.class_name,
            entry_year=self.student_7a.entry_year,
            graduation_year=2026,
        )

        self.client.logout()
        self.client.force_login(self.student_7a.user)

        list_response = self.client.get(reverse("students:alumni_list"))
        detail_response = self.client.get(reverse("students:alumni_detail", args=[alumni.pk]))
        validation_response = self.client.get(reverse("students:alumni_validation_list"))

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(validation_response.status_code, 403)

    def test_alumni_validation_updates_status_and_lists_alumni(self):
        alumni = StudentAlumniArchive.objects.create(
            student=self.student_7a,
            full_name=self.student_7a.user.full_name,
            nis=self.student_7a.nis or "",
            nisn=self.student_7a.nisn or "",
            gender=self.student_7a.gender,
            class_name=self.student_7a.class_name,
            entry_year=self.student_7a.entry_year,
            graduation_year=2026,
        )

        response = self.client.post(
            reverse("students:alumni_validation_update", args=[alumni.pk]),
            {
                "government_name": "Siswa Kelas Tujuh",
                "diploma_name": "Siswa Kelas Tujuh",
                "family_card_name": "Siswa Kelas Tujuh",
                "birth_certificate_name": "Siswa Kelas Tujuh",
                "notes": "Semua identik",
            },
        )

        self.assertRedirects(response, reverse("students:alumni_detail", args=[alumni.pk]))
        validation = StudentAlumniValidation.objects.get(alumni=alumni)
        self.assertEqual(validation.status, StudentAlumniValidation.Status.MATCH)

        list_response = self.client.get(reverse("students:alumni_validation_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, self.student_7a.user.full_name)

    def test_student_mutation_outbound_creates_archive_and_disables_student(self):
        response = self.client.post(
            reverse("students:mutation_add"),
            {
                "student": str(self.student_7a.pk),
                "direction": StudentMutationRecord.Direction.OUTBOUND,
                "mutation_date": "2026-04-23",
                "origin_school_name": "MTs Asal",
                "origin_school_npsn": "12345678",
                "destination_school_name": "MTs Tujuan",
                "destination_school_npsn": "87654321",
                "origin_study_group": str(self.group_7a.pk),
                "destination_study_group": "",
                "reason": "Pindah domisili keluarga",
                "notes": "Berkas diterima lengkap",
            },
        )

        self.assertRedirects(response, reverse("students:detail", args=[self.student_7a.pk]))
        self.student_7a.refresh_from_db()
        self.assertFalse(self.student_7a.is_active)
        self.assertIsNone(self.student_7a.study_group)

        mutation = StudentMutationRecord.objects.get(student=self.student_7a)
        self.assertEqual(mutation.direction, StudentMutationRecord.Direction.OUTBOUND)
        alumni = StudentAlumniArchive.objects.get(student=self.student_7a)
        self.assertEqual(alumni.graduation_status, StudentAlumniArchive.GraduationStatus.TRANSFERRED)

    def test_bulk_delete_removes_selected_students_and_their_users(self):
        response = self.client.post(
            reverse("students:bulk_delete"),
            {"selected_students": [str(self.student_8a_without_nis.pk)]},
        )

        self.assertRedirects(response, reverse("students:list"))
        self.assertFalse(StudentProfile.objects.filter(pk=self.student_8a_without_nis.pk).exists())
        self.assertFalse(CustomUser.objects.filter(username="siswa-8a").exists())
        self.assertTrue(StudentProfile.objects.filter(pk=self.student_7a.pk).exists())

    def test_student_edit_page_uses_tabbed_profile_layout(self):
        response = self.client.get(reverse("students:edit", args=[self.student_7a.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data siswa")
        self.assertContains(response, "Data orang tua")
        self.assertContains(response, "Data alamat")
        self.assertContains(response, "Upload berkas")
        self.assertContains(response, "Status keluarga")

    def test_student_document_upload_and_delete_workflow(self):
        file_obj = SimpleUploadedFile("kk.pdf", b"file-data", content_type="application/pdf")
        upload_response = self.client.post(
            reverse("students:edit", args=[self.student_7a.pk]),
            {
                "form_type": "upload-berkas",
                "document_type": "kk",
                "title": "Scan KK",
                "notes": "Dokumen keluarga",
                "file": file_obj,
            },
        )

        self.assertRedirects(upload_response, reverse("students:edit", args=[self.student_7a.pk]))
        self.assertEqual(self.student_7a.documents.count(), 1)

        document = self.student_7a.documents.get()
        delete_response = self.client.post(
            reverse("students:attachment_delete", args=[self.student_7a.pk, document.pk])
        )

        self.assertRedirects(delete_response, reverse("students:edit", args=[self.student_7a.pk]))
        self.assertEqual(self.student_7a.documents.count(), 0)
        self.assertTrue(ActivityLog.objects.filter(module="Berkas Siswa", action="upload").exists())
        self.assertTrue(ActivityLog.objects.filter(module="Berkas Siswa", action="delete").exists())


class StudentBackupRestoreTests(TestCase):
    def setUp(self):
        self.media_root = Path(__file__).resolve().parents[1] / "media" / ".tmp_test_media"
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)

        self.operator = CustomUser.objects.create_user(
            username="operator-backup",
            password="rahasia123",
            full_name="Operator Backup",
            role=CustomUser.Role.ADMIN,
        )
        self.client.force_login(self.operator)

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
        )
        student_user = CustomUser.objects.create_user(
            username="backup-siswa",
            password="rahasia123",
            full_name="Siswa Backup",
            role=CustomUser.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            user=student_user,
            nis="7009",
            nisn="700900",
            gender=StudentProfile.Gender.MALE,
            class_name=self.study_group.name,
            study_group=self.study_group,
            entry_year=2025,
            is_active=True,
        )
        document_path = self.media_root / "student_documents" / "dokumen-scan.txt"
        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_bytes(b"backup-content")
        self.document = StudentDocument.objects.create(
            student=self.student,
            document_type=StudentDocument.DocumentType.OTHER,
            title="Scan Dokumen",
            file="student_documents/dokumen-scan.txt",
        )

    def test_backup_download_contains_database_and_media(self):
        response = self.client.post(reverse("students:backup_restore"), {"action": "download"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        archive = zipfile.ZipFile(BytesIO(response.content))
        members = set(archive.namelist())
        self.assertIn("data.json", members)
        self.assertIn("manifest.json", members)
        self.assertIn("media/student_documents/dokumen-scan.txt", members)

    def test_restore_roundtrip_rebuilds_database_and_media(self):
        download_response = self.client.post(reverse("students:backup_restore"), {"action": "download"})
        backup_file = SimpleUploadedFile(
            "pdm-backup.zip",
            download_response.content,
            content_type="application/zip",
        )

        restore_response = self.client.post(
            reverse("students:backup_restore"),
            {
                "action": "restore",
                "backup_file": backup_file,
                "confirm_restore": "on",
            },
        )

        self.assertEqual(restore_response.status_code, 302)
        self.assertEqual(StudentProfile.objects.count(), 1)
        self.assertEqual(StudentDocument.objects.count(), 1)
        restored_student = StudentProfile.objects.select_related("user").get(nis="7009")
        self.assertEqual(restored_student.user.full_name, "Siswa Backup")
        self.assertTrue((self.media_root / "student_documents" / "dokumen-scan.txt").exists())
