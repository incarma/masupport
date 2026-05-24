# django_ma/commission/views/collect_notice_export.py
from __future__ import annotations

"""
Collect Notice Export View

역할:
- collect_notice.html / collect_notice.js에서 전송한 multipart FormData 수신
- 권한 검증 후 서버 openpyxl xlsx 생성 또는 LibreOffice PDF 변환 서비스 호출
- xlsx/pdf attachment 응답 반환

보안:
- superuser 전용
- CSRF 검증 유지
- 파일 URL 직접 노출 없음
- 결과 파일은 HttpResponse attachment로만 제공
"""

import logging
import json
from dataclasses import dataclass
from typing import Any, Literal

from django.http import HttpResponse
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from commission.services.collect_notice_excel import (
    NoticeSourceFile,
    build_collect_notice_pdf,
    build_collect_notice_excel,
)
from commission.views._excel_export import XLSX_MIME
from commission.views.utils_json import _json_error, _set_attachment_filename

logger = logging.getLogger(__name__)
PDF_MIME = "application/pdf"
PDF_MAGIC = b"%PDF"
CollectNoticeOutput = Literal["xlsx", "pdf"]


@dataclass(frozen=True)
class CollectNoticeExportRequest:
    """
    collect_notice export FormData 파싱 결과.

    JS 계약:
    - target_emp_id / target_name / target_branch
    - title_year / title_month
    - file_yms[] / notice_files[]
    - manual_rows(JSON string)
    - output: xlsx | pdf
    - no_mask: "1" → 마스킹 안 함, 그 외 → 마스킹 (기본값)
    """

    target_emp_id: str
    target_name: str
    target_branch: str
    title_year: str
    title_month: str
    file_yms: list[str]
    files: list[Any]
    manual_rows: list[dict[str, Any]]
    output: CollectNoticeOutput
    mask_pii: bool


def _parse_manual_rows(raw: str) -> list[dict[str, Any]]:
    """manual_rows JSON 문자열을 list[dict]로 파싱한다."""
    try:
        data = json.loads((raw or "[]").strip() or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("수기 입력 데이터 형식이 올바르지 않습니다.") from exc

    if not isinstance(data, list):
        raise ValueError("수기 입력 데이터는 배열 형식이어야 합니다.")

    return data


def _parse_output(raw: str) -> CollectNoticeOutput:
    """출력 형식을 xlsx/pdf 중 하나로 정규화한다."""
    output = ((raw or "xlsx").strip().lower() or "xlsx")
    if output not in {"xlsx", "pdf"}:
        raise ValueError("출력 형식이 올바르지 않습니다.")
    return output  # type: ignore[return-value]


def _parse_export_request(request) -> CollectNoticeExportRequest:
    """
    multipart FormData를 View 내부 DTO로 변환한다.

    이 helper는 HTTP 응답을 만들지 않고 ValueError만 발생시킨다.
    """
    target_emp_id = (request.POST.get("target_emp_id") or "").strip()
    target_name = (request.POST.get("target_name") or "").strip()
    target_branch = (request.POST.get("target_branch") or "").strip()
    title_year = (request.POST.get("title_year") or "").strip()
    title_month = (request.POST.get("title_month") or "").strip()
    file_yms = [(ym or "").strip() for ym in request.POST.getlist("file_yms")]
    files = list(request.FILES.getlist("notice_files"))
    output = _parse_output(request.POST.get("output") or "xlsx")
    manual_rows = _parse_manual_rows(request.POST.get("manual_rows") or "[]")
    mask_pii = (request.POST.get("no_mask") or "0").strip() != "1"

    if not target_emp_id:
        raise ValueError("대상자를 먼저 선택해주세요.")
    if not files and not manual_rows:
        raise ValueError("내역 파일 또는 수기 입력 행을 1개 이상 추가해주세요.")
    if len(file_yms) != len(files):
        raise ValueError("파일 기준 연월 정보와 파일 개수가 일치하지 않습니다.")

    return CollectNoticeExportRequest(
        target_emp_id=target_emp_id,
        target_name=target_name,
        target_branch=target_branch,
        title_year=title_year,
        title_month=title_month,
        file_yms=file_yms,
        files=files,
        manual_rows=manual_rows,
        output=output,
        mask_pii=mask_pii,
    )


def _build_sources(file_yms: list[str], files: list[Any]) -> list[NoticeSourceFile]:
    """서비스에 전달할 NoticeSourceFile 목록 생성."""
    return [
        NoticeSourceFile(ym=ym, file=file)
        for ym, file in zip(file_yms, files)
    ]


def _build_notice_result(parsed: CollectNoticeExportRequest):
    """
    output 값에 따라 xlsx/pdf 생성 서비스를 호출한다.

    반환:
    - result: NoticeWorkbookResult | NoticePdfResult
    - content_type: response content type
    """
    sources = _build_sources(parsed.file_yms, parsed.files)

    kwargs = {
        "target_name": parsed.target_name,
        "target_branch": parsed.target_branch,
        "title_year": parsed.title_year,
        "title_month": parsed.title_month,
        "sources": sources,
        "manual_rows": parsed.manual_rows,
        "mask_pii": parsed.mask_pii,
    }

    if parsed.output == "pdf":
        return build_collect_notice_pdf(**kwargs), PDF_MIME

    return build_collect_notice_excel(**kwargs), XLSX_MIME


def _is_invalid_pdf_result(*, output: str, content: bytes) -> bool:
    """PDF 요청인 경우 PDF magic byte를 검증한다."""
    return output == "pdf" and not content.startswith(PDF_MAGIC)


def _attachment_response(
    *,
    content: bytes,
    content_type: str,
    filename: str,
    row_count: int,
    output: str,
) -> HttpResponse:
    """bytes 결과를 collect_notice attachment response로 변환한다."""
    resp = HttpResponse(content, content_type=content_type)
    _set_attachment_filename(resp, filename)
    resp["X-Collect-Notice-Row-Count"] = str(row_count)
    resp["X-Collect-Notice-Output"] = output
    return resp


@require_POST
@grade_required("superuser", forbidden_template=None)
def collect_notice_export_excel(request):
    """
    환수내역 안내자료 서버 생성 API.

    요청 FormData:
    - target_emp_id: 대상자 사번
    - target_name: 대상자명
    - target_branch: 대상자 소속/지점 표시명
    - title_year: 제목 기준 연도
    - title_month: 제목 기준 월
    - file_yms[]: 각 파일의 기준 연월(YYYY-MM)
    - notice_files[]: 원본 엑셀 파일들
    - manual_rows: 수기 입력 행 JSON 문자열
    - output: xlsx | pdf

    응답:
    - 성공: xlsx/pdf attachment
    - 실패: {"ok": false, "message": "..."}
    """
    try:
        parsed = _parse_export_request(request)
        result, content_type = _build_notice_result(parsed)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except RuntimeError as exc:
        logger.warning(
            "[collect_notice_export_excel] runtime export failed output=%s target_emp_id=%s reason=%s",
            request.POST.get("output") or "xlsx",
            request.POST.get("target_emp_id") or "",
            exc,
        )
        return _json_error(str(exc), status=503)
    except Exception:
        logger.exception(
            "[collect_notice_export_excel] export failed target_emp_id=%s title=%s-%s files=%s",
            request.POST.get("target_emp_id") or "",
            request.POST.get("title_year") or "",
            request.POST.get("title_month") or "",
            len(request.FILES.getlist("notice_files")),
        )
        return _json_error("환수내역 안내자료 생성 중 오류가 발생했습니다.", status=500)

    if _is_invalid_pdf_result(output=parsed.output, content=result.content):
        logger.error(
            "[collect_notice_export_excel] invalid pdf bytes target_emp_id=%s filename=%s size=%s",
            parsed.target_emp_id,
            result.filename,
            len(result.content or b""),
        )
        return _json_error(
            "PDF 변환 결과가 올바르지 않습니다. LibreOffice 변환 상태를 확인해주세요.",
            status=500,
        )

    return _attachment_response(
        content=result.content,
        content_type=content_type,
        filename=result.filename,
        row_count=result.row_count,
        output=parsed.output,
    )