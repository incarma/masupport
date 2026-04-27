# django_ma/manual/management/commands/sanitize_manual_blocks.py
# =============================================================================
# ManualBlock.content sanitize 백필 command
# -----------------------------------------------------------------------------
# 목적:
# - sanitize_quill_html() 적용 이전에 저장된 과거 Quill HTML을 정리한다.
# - script / iframe / javascript: / 이벤트 핸들러 속성 등 실행성 HTML을 제거한다.
#
# 기본 동작:
# - dry-run 모드가 기본값이다.
# - 실제 DB 반영은 반드시 --apply 옵션을 명시해야 한다.
#
# 사용 예:
#   python manage.py sanitize_manual_blocks
#   python manage.py sanitize_manual_blocks --apply
#   python manage.py sanitize_manual_blocks --apply --batch-size 200
# =============================================================================

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from manual.models import ManualBlock
from manual.utils.sanitize import sanitize_quill_html


class Command(BaseCommand):
    help = "Sanitize existing ManualBlock.content values using manual.utils.sanitize.sanitize_quill_html."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 sanitized content를 저장합니다. 생략 시 dry-run만 수행합니다.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="한 번에 처리할 ManualBlock 개수입니다. 기본값: 200",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        batch_size = int(options["batch_size"] or 200)

        if batch_size <= 0:
            self.stderr.write(self.style.ERROR("--batch-size는 1 이상이어야 합니다."))
            return

        qs = (
            ManualBlock.objects
            .exclude(content="")
            .order_by("id")
            .values_list("id", "content")
        )

        total = qs.count()
        scanned = 0
        changed = 0

        self.stdout.write(
            self.style.WARNING(
                f"ManualBlock.content sanitize 시작: total={total}, "
                f"mode={'APPLY' if apply_changes else 'DRY-RUN'}, batch_size={batch_size}"
            )
        )

        buffer: list[ManualBlock] = []

        for block_id, content in qs.iterator(chunk_size=batch_size):
            scanned += 1
            safe_content = sanitize_quill_html(content)

            if safe_content == content:
                continue

            changed += 1

            if apply_changes:
                buffer.append(ManualBlock(id=block_id, content=safe_content))

                if len(buffer) >= batch_size:
                    self._bulk_update(buffer)
                    buffer.clear()

            if changed <= 20:
                self.stdout.write(
                    f"- 변경 대상 block_id={block_id}, "
                    f"before_len={len(content or '')}, after_len={len(safe_content or '')}"
                )

        if apply_changes and buffer:
            self._bulk_update(buffer)

        self.stdout.write(
            self.style.SUCCESS(
                f"ManualBlock.content sanitize 완료: scanned={scanned}, changed={changed}, "
                f"applied={apply_changes}"
            )
        )

    @staticmethod
    def _bulk_update(blocks: list[ManualBlock]) -> None:
        """
        content만 bulk_update한다.
        updated_at 자동 갱신은 발생하지 않는다.
        보안 백필 성격상 사용자-facing 수정일 변경을 피하기 위한 의도적 선택이다.
        """
        with transaction.atomic():
            ManualBlock.objects.bulk_update(blocks, ["content"])