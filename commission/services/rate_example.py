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
    def create(
        *,
        insurer_type,
        category,
        insurer,
        uploaded_file,
        actor,
        product_kind: str = "",
        normalize_mode: str = "replace",
    ) -> dict:
        """
        Returns {"ok": True, "instance": RateExample}
             or {"ok": False, "message": str}
        뷰에서 직접 ORM 접근 금지 — 반드시 이 메서드 경유.
        """
        if insurer_type not in (RateExample.TYPE_LIFE, RateExample.TYPE_NONLIFE):
            return {"ok": False, "message": "손생 구분 값이 올바르지 않습니다."}
        if category not in (RateExample.CAT_CONV, RateExample.CAT_PAY):
            return {"ok": False, "message": "구분 값이 올바르지 않습니다."}
        # pay 업로드는 보험사 단위가 아니라 전사(全社) 단일 파일이므로
        # insurer=""로 수신되며 허용 목록 검증 대상이 아니다.
        if category != RateExample.CAT_PAY:
            if insurer not in _ALLOWED_INSURERS.get(insurer_type, set()):
                return {"ok": False, "message": "선택된 보험사가 허용 목록에 없습니다."}
        
        # ─────────────────────────────────────────────────────
        # 정규화 데이터 저장 방식 검증
        # - replace: 기존 방식 유지
        # - append: 기존 row를 삭제하지 않고 새 row만 추가
        # ─────────────────────────────────────────────────────
        normalize_mode = (normalize_mode or "replace").strip()
        if normalize_mode not in {"replace", "append"}:
            return {
                "ok": False,
                "message": "기존 데이터 초기화 여부 값이 올바르지 않습니다.",
            }
        
        # ─────────────────────────────────────────────────────
        # KB 생명보험 환산율/수정률 상품 구분 검증
        # - DB 모델 추가 없이 업로드 분기값으로만 사용
        # - 현재 지원: 일반상품, 건강보험
        # ─────────────────────────────────────────────────────
        if (
            insurer_type == RateExample.TYPE_LIFE
            and category == RateExample.CAT_CONV
            and insurer == "KB"
        ):
            if product_kind not in {"general", "health"}:
                return {
                    "ok": False,
                    "message": "KB 상품 구분 값이 올바르지 않습니다.",
                }

        else:
            product_kind = ""

        # ── category=pay 전용 강제 정규화 ────────────────────────────────────
        # 지급률 파일은 보험사 선택 없이 업로드하므로 서버에서 항목을 강제 초기화한다.
        # product_kind/normalize_mode는 클라이언트가 전달하더라도 무시한다.
        if category == RateExample.CAT_PAY:
            insurer        = ""
            product_kind   = ""
            normalize_mode = "replace"  # 지급률은 항상 전체 교체
        
        # ─────────────────────────────────────────────────────
        # KDB/교보/농협/동양/라이나/메트 생명보험 환산율/수정률
        # - 별도 상품 구분 없이 보험사 선택만으로 정규화한다.
        # - product_kind는 빈 값으로 고정한다.
        # ─────────────────────────────────────────────────────
        if (
            insurer_type == RateExample.TYPE_LIFE
            and category == RateExample.CAT_CONV
            and insurer in {"KDB", "교보", "농협", "동양", "라이나", "메트"}
        ):
            product_kind = ""

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
        # 현재 지원 대상: 생명보험 / 환산율·수정률 / ABL / xlsx
        # import를 함수 내부에 두어 models/services 순환 import 위험을 줄인다.
        normalized_count = 0
        try:
            from commission.services.rate_example_normalizer import normalize_rate_example

            normalized_count = normalize_rate_example(
                instance,
                product_kind=product_kind,
                normalize_mode=normalize_mode,
            )
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
            "product_kind": product_kind,
            "normalize_mode": normalize_mode,
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
