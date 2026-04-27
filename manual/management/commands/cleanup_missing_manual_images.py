# django_ma/management/commands/cleanup_missing_manual_images.py

from django.core.management.base import BaseCommand

from manual.models import ManualBlock


class Command(BaseCommand):
    help = "존재하지 않는 이미지 파일을 참조하는 ManualBlock.image 값을 정리합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다. 생략 시 dry-run만 수행합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])

        qs = ManualBlock.objects.exclude(image="").exclude(image__isnull=True)

        total = qs.count()
        missing = 0
        cleaned = 0

        self.stdout.write(
            self.style.WARNING(
                f"ManualBlock missing image cleanup 시작: total={total}, "
                f"mode={'APPLY' if apply_changes else 'DRY-RUN'}"
            )
        )

        for b in qs.iterator(chunk_size=200):
            if not b.image.storage.exists(b.image.name):
                missing += 1
                self.stdout.write(f"- missing block_id={b.id}, file={b.image.name}")

                if apply_changes:
                    b.image = None
                    b.save(update_fields=["image"])
                    cleaned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: total={total}, missing={missing}, cleaned={cleaned}, applied={apply_changes}"
            )
        )