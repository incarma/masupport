# django_ma/management/commands/cleanup_missing_manual_images.py
# [DEPRECATED] cleanup_manual_files --apply 를 사용할 것

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "[DEPRECATED] python manage.py cleanup_manual_files --apply 를 사용하세요."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다. 생략 시 dry-run만 수행합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])

        self.stdout.write(
            self.style.WARNING(
                "이 명령은 deprecated입니다. "
                "python manage.py cleanup_manual_files --apply 를 사용하세요."
            )
        )

        from manual.management.commands.cleanup_manual_files import Command as CleanupCmd

        cmd = CleanupCmd()
        cmd.stdout = self.stdout
        cmd.stderr = self.stderr
        cmd.style = self.style

        result = cmd._cleanup_missing_block_images(apply_changes=apply_changes)

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: total={result['total']}, missing={result['missing']}, "
                f"cleaned={result['cleaned']}, applied={apply_changes}"
            )
        )
