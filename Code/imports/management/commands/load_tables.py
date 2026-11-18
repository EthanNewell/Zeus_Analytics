from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from analysis.services import run_analysis
from imports.services import import_table


class Command(BaseCommand):
    help = "Import every .xlsx/.csv indicator table from a folder through the normal import path, then run the analysis."

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument(
            "--user", required=True, help="Existing user with import and analysis permissions"
        )

    def handle(self, folder, user, **options):
        actor = get_user_model().objects.filter(username=user).first()
        if actor is None:
            raise CommandError(f"User {user} not found")
        files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in {".xlsx", ".csv"})
        if not files:
            raise CommandError("No .xlsx or .csv files in the folder")
        failed = False
        for path in files:
            result = import_table(
                actor=actor, uploaded_file=SimpleUploadedFile(path.name, path.read_bytes())
            )
            if result.errors:
                failed = True
                for error in result.errors:
                    self.stderr.write(
                        f"{path.name}: строка {error.row}, {error.field}: {error.message}"
                    )
            else:
                self.stdout.write(f"{path.name}: {len(result.case_ids)} объектов")
        if failed:
            raise CommandError("Some files were rejected; nothing from them was saved")
        run = run_analysis(actor=actor)
        self.stdout.write(
            self.style.SUCCESS(
                f"Analysis: {run.records_count} records, {run.triggered_count} triggered, "
                f"agreement with research marks {run.agreed_count}/{run.compared_count}, {run.duration_ms} ms"
            )
        )
