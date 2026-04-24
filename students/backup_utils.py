import json
import uuid
import shutil
import zipfile
from io import BytesIO, StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone


BACKUP_FILENAME_PREFIX = "pdm-backup"
BACKUP_EXCLUDED_MODELS = [
    "admin.LogEntry",
    "auth.Group",
    "auth.Permission",
    "contenttypes.ContentType",
    "sessions.Session",
]


def _iter_media_files():
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return

    for path in media_root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(media_root)
        if "import_cache" in relative_path.parts:
            continue
        yield path, relative_path


def build_backup_archive():
    backup_buffer = StringIO()
    call_command(
        "dumpdata",
        format="json",
        indent=2,
        natural_foreign=True,
        natural_primary=True,
        exclude=BACKUP_EXCLUDED_MODELS,
        stdout=backup_buffer,
    )

    generated_at = timezone.localtime(timezone.now())
    manifest = {
        "app": "madrasah_management",
        "generated_at": generated_at.isoformat(),
        "generated_at_label": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "backup_file": f"{BACKUP_FILENAME_PREFIX}-{generated_at:%Y%m%d-%H%M%S}.zip",
        "contains": ["database", "media"],
        "excluded": BACKUP_EXCLUDED_MODELS,
    }

    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("data.json", backup_buffer.getvalue())

        for media_path, relative_path in _iter_media_files():
            archive.write(media_path, arcname=str(Path("media") / relative_path))

    archive_buffer.seek(0)
    return archive_buffer.getvalue(), manifest


def restore_backup_archive(uploaded_file):
    temp_base_dir = Path(settings.MEDIA_ROOT).parent / ".tmp_backup_restore"
    temp_base_dir.mkdir(exist_ok=True)

    temp_dir_path = temp_base_dir / f"restore-{uuid.uuid4().hex}"
    temp_dir_path.mkdir(parents=True, exist_ok=False)

    try:
        archive_path = temp_dir_path / "backup.zip"

        with archive_path.open("wb") as target:
            for chunk in uploaded_file.chunks():
                target.write(chunk)

        with zipfile.ZipFile(archive_path) as archive:
            members = set(archive.namelist())
            if "data.json" not in members:
                raise ValueError("Backup tidak valid: file data.json tidak ditemukan.")
            for member_name in members:
                member_path = Path(member_name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("Backup tidak valid: struktur file ZIP tidak aman.")
            archive.extractall(temp_dir_path)

        data_path = temp_dir_path / "data.json"
        media_source = temp_dir_path / "media"
        media_root = Path(settings.MEDIA_ROOT)

        if media_root.exists():
            shutil.rmtree(media_root)
        media_root.mkdir(parents=True, exist_ok=True)

        call_command("flush", interactive=False, verbosity=0)
        call_command("loaddata", str(data_path), verbosity=0)

        restored_media_count = 0
        if media_source.exists():
            for source_path in media_source.rglob("*"):
                if not source_path.is_file():
                    continue
                relative_path = source_path.relative_to(media_source)
                destination_path = media_root / relative_path
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)
                restored_media_count += 1
        return {
            "restored_media_count": restored_media_count,
        }
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)
