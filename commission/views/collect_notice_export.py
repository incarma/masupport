# django_ma/commission/views/collect_notice_export.py
from __future__ import annotations

"""
Collect Notice Excel Export View

역할:
- collect_notice.html / collect_notice.js에서 전송한 multipart FormData 수신
- 권한 검증 후 서버 openpyxl 생성 서비스 호출
- xlsx attachment 응답 반환

보안:
- superuser 전용
- CSRF 검증 유지
- 파일 URL 직접 노출 없음
- 결과 파일은 HttpResponse attachment로만 제공
"""

import logging

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


@require_POST
@grade_required("superuser", forbidden_template=None)
def collect_notice_export_excel(request):
    """
    환수내역 안내자료 엑셀 서버 생성 API.

    요청 FormData:
    - target_emp_id: 대상자 사번
    - target_name: 대상자명
    - target_branch: 대상자 소속/지점 표시명
    - title_year: 제목 기준 연도
    - title_month: 제목 기준 월
    - file_yms[]: 각 파일의 기준 연월(YYYY-MM)
    - notice_files[]: 원본 엑셀 파일들

    응답:
    - 성공: xlsx attachment
    - 실패: {"ok": false, "message": "..."}
    """
    target_emp_id = (request.POST.get("target_emp_id") or "").strip()
    target_name = (request.POST.get("target_name") or "").strip()
    target_branch = (request.POST.get("target_branch") or "").strip()
    title_year = (request.POST.get("title_year") or "").strip()
    title_month = (request.POST.get("title_month") or "").strip()

    file_yms = request.POST.getlist("file_yms")
    files = request.FILES.getlist("notice_files")
    output = (request.POST.get("output") or "xlsx").strip().lower()

    if not target_emp_id:
        return _json_error("대상자를 먼저 선택해주세요.", status=400)

    if not files:
        return _json_error("내역 파일을 1개 이상 선택해주세요.", status=400)

    if len(file_yms) != len(files):
        return _json_error("파일 기준 연월 정보와 파일 개수가 일치하지 않습니다.", status=400)

    sources = [
        NoticeSourceFile(ym=(ym or "").strip(), file=file)
        for ym, file in zip(file_yms, files)
    ]

    try:
        if output == "pdf":
            result = build_collect_notice_pdf(
                target_name=target_name,
                target_branch=target_branch,
                title_year=title_year,
                title_month=title_month,
                sources=sources,
            )
            content_type = "application/pdf"
        else:
            result = build_collect_notice_excel(
                target_name=target_name,
                target_branch=target_branch,
                title_year=title_year,
                title_month=title_month,
                sources=sources,
            )
            content_type = XLSX_MIME
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except RuntimeError as exc:
        logger.warning(
            "[collect_notice_export_excel] runtime export failed output=%s target_emp_id=%s reason=%s",
            output,
            target_emp_id,
            exc,
        )
        return _json_error(str(exc), status=503)
    except Exception:
        logger.exception(
            "[collect_notice_export_excel] export failed target_emp_id=%s title=%s-%s files=%s",
            target_emp_id,
            title_year,
            title_month,
            len(files),
        )
        return _json_error("환수내역 엑셀 생성 중 오류가 발생했습니다.", status=500)

    resp = HttpResponse(result.content, content_type=content_type)
    _set_attachment_filename(resp, result.filename)
    resp["X-Collect-Notice-Row-Count"] = str(result.row_count)
    return resp