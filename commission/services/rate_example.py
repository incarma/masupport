# commission/services/rate_example.py
import logging
import os

from django.db import transaction

from commission.models import RateExample

logger = logging.getLogger(__name__)

_ALLOWED_INSURERS = {
    RateExample.TYPE_LIFE:    set(RateExample.LIFE_INSURERS),
    RateExample.TYPE_NONLIFE: set(RateExample.NONLIFE_INSURERS),
}


class RateExampleService:

    @staticmethod
    def _validate_file(uploaded_file) -> str:
        """오류 메시지 반환. 정상이면 빈 문자열."""
        if not uploaded_file:
            return "파일을 선택해 주세요."
        ext = os.path.splitext(uploaded_file.name or "")[1].lower()
        if ext not in RateExample.ALLOWED_EXTENSIONS:
            return "허용되지 않는 파일 형식입니다. (허용: PDF, XLS, XLSX)"
        if uploaded_file.content_type not in RateExample.ALLOWED_MIME_TYPES:
            return "파일 Content-Type이 허용되지 않습니다."
        if uploaded_file.size > RateExample.MAX_FILE_SIZE:
            return "파일 크기가 20MB를 초과합니다."
        return ""

    @staticmethod
    @transaction.atomic
    def create(*, insurer_type, category, insurer, uploaded_file, actor) -> dict:
        """
        Returns {"ok": True, "instance": RateExample}
             or {"ok": False, "message": str}
        뷰에서 직접 ORM 접근 금지 — 반드시 이 메서드 경유.
        """
        if insurer_type not in (RateExample.TYPE_LIFE, RateExample.TYPE_NONLIFE):
            return {"ok": False, "message": "손생 구분 값이 올바르지 않습니다."}
        if category not in (RateExample.CAT_CONV, RateExample.CAT_PAY):
            return {"ok": False, "message": "구분 값이 올바르지 않습니다."}
        if insurer not in _ALLOWED_INSURERS.get(insurer_type, set()):
            return {"ok": False, "message": "선택된 보험사가 허용 목록에 없습니다."}

        err = RateExampleService._validate_file(uploaded_file)
        if err:
            return {"ok": False, "message": err}

        instance = RateExample.objects.create(
            insurer_type=insurer_type,
            category=category,
            insurer=insurer,
            file=uploaded_file,
            original_name=uploaded_file.name,
            uploaded_by=actor,
        )
        
        # ── 정규화 처리 ─────────────────────────────────────────────
        # 현재 지원 대상: 생명보험 / 환산률·수정률 / ABL / xlsx
        # import를 함수 내부에 두어 models/services 순환 import 위험을 줄인다.
        normalized_count = 0
        try:
            from commission.services.rate_example_normalizer import normalize_rate_example

            normalized_count = normalize_rate_example(instance)
        except Exception:
            logger.exception(
                "RateExample normalize failed: insurer_type=%s category=%s insurer=%s file=%s",
                insurer_type,
                category,
                insurer,
                getattr(uploaded_file, "name", ""),
            )
            raise

        return {
            "ok": True,
            "instance": instance,
            "normalized_count": normalized_count,
        }

    @staticmethod
    @transaction.atomic
    def delete(instance, actor) -> None:
        """
        파일 물리 삭제 + DB 레코드 삭제.
        conversion_rows는 FK CASCADE로 함께 삭제된다.
        """
        if instance.file:
            try:
                instance.file.delete(save=False)
            except Exception:
                logger.exception(
                    "RateExample file delete failed: pk=%s", instance.pk
                )
        instance.delete()

    @staticmethod
    def list_all():
        return (
            RateExample.objects
            .select_related("uploaded_by")
            .order_by("-created_at")
        )
