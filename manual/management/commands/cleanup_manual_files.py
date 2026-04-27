# django_ma/manual/management/commands/cleanup_manual_files.py
# =============================================================================
# Manual file cleanup command
# -----------------------------------------------------------------------------
# 목적:
# - Manual 앱에서 DB는 파일을 참조하지만 실제 storage에는 파일이 없는 경우를 점검한다.
# - ManualBlock.image 누락 참조는 --apply 시 DB 값을 비운다.
# - ManualBlockAttachment.file 누락은 자동 삭제하지 않고 목록만 출력한다.
#
# 사용:
#   python manage.py cleanup_manual_files
#   python manage.py cleanup_manual_files --apply
#
# 운영 원칙:
# - 기본은 dry-run이다.
# - 첨부파일 row 삭제는 자료 손실 가능성이 있어 자동 처리하지 않는다.
# - 이미지 누락은 화면 깨짐 방지를 위해 --apply 시 참조만 제거한다.
# =============================================================================

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from manual.models import ManualBlock, ManualBlockAttachment
from audit.services import log_action
from audit.constants import ACTION


class Command(BaseCommand):
    help = "Manual 앱의 누락 파일 참조를 점검하고, --apply 시 ManualBlock.image 누락 참조를 정리합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다. 생략 시 dry-run만 수행합니다.",
        )
        parser.add_argument(
            "--delete-missing-attachments",
            action="store_true",
            help=(
                "storage에 없는 ManualBlockAttachment row를 삭제합니다. "
                "반드시 --apply와 함께 사용해야 실제 삭제됩니다."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="실제 삭제를 강제 실행합니다. (안전 가드)",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        delete_missing_attachments = bool(options["delete_missing_attachments"])
        force = bool(options["force"])

        if apply_changes and delete_missing_attachments and not force:
            self.stdout.write(
                self.style.ERROR(
                    "❌ 실제 삭제는 --force 옵션이 필요합니다. (운영 안전 가드)"
                )
            )
            return

        if delete_missing_attachments and not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "--delete-missing-attachments가 지정되었지만 --apply가 없어 dry-run으로만 실행합니다."
                )
            )

        self.stdout.write(
            self.style.WARNING(
                "Manual file cleanup 시작: "
                f"mode={'APPLY' if apply_changes else 'DRY-RUN'}, "
                f"delete_missing_attachments={delete_missing_attachments}"
            )
        )

        image_result = self._cleanup_missing_block_images(apply_changes=apply_changes)
        attachment_result = self._cleanup_missing_attachments(
            apply_changes=apply_changes,
            delete_missing_attachments=delete_missing_attachments,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Manual file cleanup 완료: "
                f"image_total={image_result['total']}, "
                f"image_missing={image_result['missing']}, "
                f"image_cleaned={image_result['cleaned']}, "
                f"attachment_total={attachment_result['total']}, "
                f"attachment_missing={attachment_result['missing']}, "
                f"attachment_deleted={attachment_result['deleted']}, "
                f"applied={apply_changes}"
            )
        )

    def _cleanup_missing_block_images(self, *, apply_changes: bool) -> dict[str, int]:
        """
        ManualBlock.image 정합성 점검.

        - storage에 실제 파일이 없으면 missing으로 기록한다.
        - --apply 시 image 필드만 None 처리한다.
        """
        qs = ManualBlock.objects.exclude(image="").exclude(image__isnull=True)

        total = qs.count()
        missing = 0
        cleaned = 0

        for block in qs.iterator(chunk_size=200):
            if block.image.storage.exists(block.image.name):
                continue

            missing += 1
            self.stdout.write(
                f"- missing image block_id={block.id}, file={block.image.name}"
            )

            if apply_changes:
                block.image = None
                block.save(update_fields=["image"])
                cleaned += 1

        return {"total": total, "missing": missing, "cleaned": cleaned}

    def _cleanup_missing_attachments(
        self,
        *,
        apply_changes: bool,
        delete_missing_attachments: bool,
    ) -> dict[str, int]:
        """
        ManualBlockAttachment.file 정합성 점검.

        - 기본 동작은 누락 첨부파일 목록 출력만 수행한다.
        - 실제 row 삭제는 --apply --delete-missing-attachments가 모두 있을 때만 수행한다.
        - delete() 호출을 사용해 모델 delete/signal 기반 파일 정리 정책과 충돌하지 않도록 한다.
        """
        qs = ManualBlockAttachment.objects.exclude(file="").exclude(file__isnull=True)

        total = qs.count()
        missing = 0
        deleted = 0

        for attachment in qs.iterator(chunk_size=200):
            if attachment.file.storage.exists(attachment.file.name):
                continue

            missing += 1
            self.stdout.write(
                f"- missing attachment attachment_id={attachment.id}, "
                f"block_id={attachment.block_id}, file={attachment.file.name}"
            )

            if apply_changes and delete_missing_attachments:
                attachment_id = attachment.id
                block_id = attachment.block_id
                file_name = attachment.file.name

                with transaction.atomic():
                    # ✅ Audit 로그 (중요)
                    log_action(
                        request=None,  # system job
                        action=ACTION.MANUAL_ATTACHMENT_DELETE,
                        obj=attachment,
                        meta={
                            "reason": "missing_file_cleanup",
                            "block_id": block_id,
                            "file": file_name,
                            "timestamp": timezone.now().isoformat(),
                        },
                    )

                    attachment.delete()

                deleted += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  deleted attachment_id={attachment_id}, "
                        f"block_id={block_id}, file={file_name}"
                    )
                )

        return {"total": total, "missing": missing, "deleted": deleted}