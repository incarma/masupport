# commission/views/api_rate_example.py
import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from board.services.attachments import open_fileresponse_from_fieldfile
from commission.models import RateExample
from commission.services.rate_example import RateExampleService
from commission.views.utils_json import _json_error, _json_ok

logger = logging.getLogger(__name__)


# ── 업로드 ─────────────────────────────────────────────────────────────────
# superuser 고정 — 페이지 권한이 head로 확장되어도 이 데코레이터는 변경 금지
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_upload(request):
    result = RateExampleService.create(
        insurer_type=request.POST.get("insurer_type", "").strip(),
        category=request.POST.get("category", "").strip(),
        insurer=request.POST.get("insurer", "").strip(),
        # KB 생명보험 환산률/수정률 전용 상품 구분.
        # 현재 지원값: general(일반상품), health(건강보험: UI만 활성화, 정규화는 추후)
        product_kind=request.POST.get("product_kind", "").strip(),
        # 정규화 데이터 저장 방식:
        # - replace: 기존 데이터 삭제 후 새 데이터 적재
        # - append: 기존 데이터 유지 후 새 데이터 추가
        normalize_mode=request.POST.get("normalize_mode", "replace").strip() or "replace",
        uploaded_file=request.FILES.get("file"),
        actor=request.user,
    )
    if not result["ok"]:
        return _json_error(result["message"])

    instance = result["instance"]
    normalized_count = result.get("normalized_count", 0)
    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_UPLOAD,
            obj=instance,
            meta={
                "insurer_type": instance.insurer_type,
                "insurer": instance.insurer,
                "category": instance.category,
                "original_name": instance.original_name,
                "normalized_count": normalized_count,
                "product_kind": result.get("product_kind", ""),
                "normalize_mode": result.get("normalize_mode", "replace"),
            },
            success=True,
        )
    except Exception:
        logger.exception("rate_example upload audit log failed")

    return _json_ok(
        "파일이 등록되었습니다.",
        data={"normalized_count": normalized_count},
    )


# ── 다운로드 ────────────────────────────────────────────────────────────────
# superuser 고정 — 변경 금지
@login_required
@grade_required("superuser", forbidden_template=None)
def rate_example_download(request, pk):
    example = get_object_or_404(RateExample, pk=pk)
    try:
        response = open_fileresponse_from_fieldfile(
            example.file,
            original_name=example.original_name or "",
        )
    except Exception:
        logger.exception("rate_example download failed: pk=%s", pk)
        try:
            log_action(
                request,
                ACTION.COMMISSION_RATE_EXAMPLE_DOWNLOAD,
                obj=example,
                success=False,
                reason="file_not_found",
            )
        except Exception:
            logger.exception("rate_example download audit log failed (error path): pk=%s", pk)
        return _json_error("파일을 찾을 수 없습니다.", status=404)

    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_DOWNLOAD,
            obj=example,
            success=True,
        )
    except Exception:
        logger.exception("rate_example download audit log failed")

    return response


# ── 삭제 ────────────────────────────────────────────────────────────────────
# superuser 고정 — 변경 금지
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_delete(request, pk):
    example = get_object_or_404(RateExample, pk=pk)
    RateExampleService.delete(example, actor=request.user)

    try:
        log_action(
            request,
            ACTION.COMMISSION_RATE_EXAMPLE_DELETE,
            meta={"pk": pk},
            success=True,
        )
    except Exception:
        logger.exception("rate_example delete audit log failed")

    return _json_ok("삭제되었습니다.")
