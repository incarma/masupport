# django_ma/commission/views/api_collect.py
"""
환수관리(Collect) 도메인 API 뷰 — Step 6

[원칙]
- 인증: @login_required + @grade_required("superuser") 모든 엔드포인트 적용
- 비즈니스 로직: commission.services.collect 서비스만 호출 (직접 ORM 금지)
- JSON 응답: utils_json._json_ok / _json_error (SSOT)
- 피드백 수정·삭제: 서비스 반환 None/False → _json_error status=403
- Audit 로그: 피드백 생성·수정·삭제 시 log_action 연동
- 업로드: 기존 upload_excel 뷰(registry 기반) 재사용 — 별도 엔드포인트 없음

[엔드포인트 목록]
GET  /commission/collect/api/list/            → api_collect_list
GET  /commission/collect/api/ym-list/         → api_collect_ym_list
GET  /commission/collect/api/feedback/        → api_collect_feedback_list
POST /commission/collect/api/feedback/create/ → api_collect_feedback_create
POST /commission/collect/api/feedback/update/ → api_collect_feedback_update
POST /commission/collect/api/feedback/delete/ → api_collect_feedback_delete
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import grade_required
from audit.constants import ACTION
from audit.services import log_action
from commission.views.utils_json import _json_ok, _json_error
import commission.services.collect as svc

logger = logging.getLogger(__name__)


# =============================================================================
# 내부 헬퍼
# =============================================================================

def _parse_json_body(request) -> tuple[dict, str | None]:
    """
    요청 body를 JSON으로 파싱한다.
    성공: (data_dict, None)
    실패: ({}, 에러 메시지)
    """
    try:
        return json.loads(request.body or "{}"), None
    except (json.JSONDecodeError, ValueError) as exc:
        return {}, f"요청 형식이 잘못되었습니다: {exc}"


# =============================================================================
# API: 탭별 환수 목록 조회
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_GET
def api_collect_list(request):
    """
    [GET] /commission/collect/api/list/

    파라미터 (QueryString):
        tab     : "all" | "new" | "long3" | "long6" | "long12" (기본: "all")
        ym      : "202603" YYYYMM 형식 (필수)
        part    : 부서 문자열 (빈 문자열 = 전체)
        bizmoon : 부문 문자열 (빈 문자열 = 전체)

    응답:
        {"ok": true, "data": {"rows": [...], "tab": "...", "ym": "..."}}
    """
    tab     = request.GET.get("tab",     "all").strip()
    ym      = request.GET.get("ym",      "").strip()
    part    = request.GET.get("part",    "").strip()
    bizmoon = request.GET.get("bizmoon", "").strip()

    # ym 필수 + 형식 검증
    if not ym:
        return _json_error("월도를 선택해주세요.")
    if len(ym) != 6 or not ym.isdigit():
        return _json_error("월도 형식이 올바르지 않습니다. (예: 202603)")

    try:
        rows = svc.get_collect_list(ym, tab, part=part, bizmoon=bizmoon, user=request.user)
        return _json_ok("조회 완료", data={"rows": rows, "tab": tab, "ym": ym})

    except ValueError as exc:
        logger.warning("[api_collect_list] ValueError tab=%s ym=%s: %s", tab, ym, exc)
        return _json_error(str(exc))
    except Exception:
        logger.exception("[api_collect_list] 예외 발생 tab=%s ym=%s", tab, ym)
        return _json_error("조회 중 오류가 발생했습니다.")


# =============================================================================
# API: 업로드된 월도 목록 조회 (드롭다운용)
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_GET
def api_collect_ym_list(request):
    """
    [GET] /commission/collect/api/ym-list/

    CollectRecord에 존재하는 월도 목록을 최신순으로 반환한다.
    월도 드롭다운 옵션 생성에 사용.

    응답:
        {"ok": true, "data": {"yms": ["202604", "202603", ...]}}
    """
    try:
        yms = svc.get_available_yms()
        return _json_ok("조회 완료", data={"yms": yms})
    except Exception:
        logger.exception("[api_collect_ym_list] 예외 발생")
        return _json_error("월도 목록 조회 중 오류가 발생했습니다.")


# =============================================================================
# API: 피드백 목록 조회
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_GET
def api_collect_feedback_list(request):
    """
    [GET] /commission/collect/api/feedback/

    파라미터 (QueryString):
        emp_id : 대상자 사번 (필수)

    응답:
        {"ok": true, "data": {"feedbacks": [...], "emp_id": "..."}}
    """
    emp_id = request.GET.get("emp_id", "").strip()
    if not emp_id:
        return _json_error("대상자 사번을 입력해주세요.")

    try:
        feedbacks = svc.get_feedbacks(emp_id)
        return _json_ok("조회 완료", data={"feedbacks": feedbacks, "emp_id": emp_id})
    except Exception:
        logger.exception("[api_collect_feedback_list] 예외 발생 emp_id=%s", emp_id)
        return _json_error("피드백 조회 중 오류가 발생했습니다.")


# =============================================================================
# API: 피드백 생성
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_POST
def api_collect_feedback_create(request):
    """
    [POST] /commission/collect/api/feedback/create/

    Body (JSON):
        {"emp_id": "사번", "content": "피드백 내용"}

    응답:
        {"ok": true, "data": {"feedback_id": 123}}
    """
    body, err = _parse_json_body(request)
    if err:
        return _json_error(err)

    emp_id  = str(body.get("emp_id",  "")).strip()
    content = str(body.get("content", "")).strip()
    date_input_str = str(body.get("date_input", "")).strip()
    department     = str(body.get("department", "")).strip()
    manager        = str(body.get("manager",    "")).strip()

    if not emp_id:
        return _json_error("대상자 사번을 입력해주세요.")
    if not content:
        return _json_error("피드백 내용을 입력해주세요.")
    
    # date_input 파싱 (YYYY-MM-DD 형식, 빈 값이면 None)
    from datetime import date as _date
    date_input = None
    if date_input_str:
        try:
            date_input = _date.fromisoformat(date_input_str)
        except ValueError:
            return _json_error("입력일 형식이 올바르지 않습니다. (YYYY-MM-DD)")

    try:
        fb = svc.create_feedback(
            author=request.user,
            emp_id=emp_id,
            content=content,
            date_input=date_input,
            department=department,
            manager=manager,
        )
        # Audit 로그 — 생성 성공
        log_action(
            request,
            ACTION.COLLECT_FEEDBACK_CREATE,
            meta={"emp_id": emp_id, "feedback_id": fb.id},
            success=True,
        )
        return _json_ok("저장 완료", data={"feedback_id": fb.id})

    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        logger.exception(
            "[api_collect_feedback_create] 예외 발생 emp_id=%s author=%s",
            emp_id, request.user.id,
        )
        log_action(
            request,
            ACTION.COLLECT_FEEDBACK_CREATE,
            meta={"emp_id": emp_id},
            success=False,
        )
        return _json_error("피드백 저장 중 오류가 발생했습니다.")


# =============================================================================
# API: 피드백 수정 (본인만)
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_POST
def api_collect_feedback_update(request):
    """
    [POST] /commission/collect/api/feedback/update/

    Body (JSON):
        {"feedback_id": 123, "content": "수정된 내용"}

    응답:
        {"ok": true}              — 성공
        {"ok": false} + 403      — 권한 없음 (서비스 레이어 판정)
    """
    body, err = _parse_json_body(request)
    if err:
        return _json_error(err)

    feedback_id = body.get("feedback_id")
    content     = str(body.get("content", "")).strip()

    if not feedback_id:
        return _json_error("feedback_id가 필요합니다.")
    if not content:
        return _json_error("피드백 내용을 입력해주세요.")

    try:
        result = svc.update_feedback(
            feedback_id=int(feedback_id),
            author=request.user,
            content=content,
        )
        if result is None:
            # 서비스 레이어 권한 판정: 본인 아님 또는 존재하지 않음
            log_action(
                request,
                ACTION.COLLECT_FEEDBACK_UPDATE,
                meta={"feedback_id": feedback_id},
                success=False,
            )
            return _json_error("권한이 없습니다.", status=403)

        # Audit 로그 — 수정 성공
        log_action(
            request,
            ACTION.COLLECT_FEEDBACK_UPDATE,
            meta={"feedback_id": result.id},
            success=True,
        )
        return _json_ok("수정 완료")

    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        logger.exception(
            "[api_collect_feedback_update] 예외 발생 feedback_id=%s author=%s",
            feedback_id, request.user.id,
        )
        return _json_error("피드백 수정 중 오류가 발생했습니다.")


# =============================================================================
# API: 피드백 삭제 (본인만)
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_POST
def api_collect_feedback_delete(request):
    """
    [POST] /commission/collect/api/feedback/delete/

    Body (JSON):
        {"feedback_id": 123}

    응답:
        {"ok": true}              — 성공
        {"ok": false} + 403      — 권한 없음 (서비스 레이어 판정)
    """
    body, err = _parse_json_body(request)
    if err:
        return _json_error(err)

    feedback_id = body.get("feedback_id")
    if not feedback_id:
        return _json_error("feedback_id가 필요합니다.")

    try:
        success = svc.delete_feedback(
            feedback_id=int(feedback_id),
            author=request.user,
        )
        if not success:
            # 서비스 레이어 권한 판정: 본인 아님 또는 존재하지 않음
            log_action(
                request,
                ACTION.COLLECT_FEEDBACK_DELETE,
                meta={"feedback_id": feedback_id},
                success=False,
            )
            return _json_error("권한이 없습니다.", status=403)

        # Audit 로그 — 삭제 성공
        log_action(
            request,
            ACTION.COLLECT_FEEDBACK_DELETE,
            meta={"feedback_id": feedback_id},
            success=True,
        )
        return _json_ok("삭제 완료")

    except Exception:
        logger.exception(
            "[api_collect_feedback_delete] 예외 발생 feedback_id=%s author=%s",
            feedback_id, request.user.id,
        )
        return _json_error("피드백 삭제 중 오류가 발생했습니다.")
    

# =============================================================================
# API: 드랍다운 피드백 저장
# =============================================================================

@login_required
@grade_required("superuser", "head", "leader")
@require_POST
def api_collect_dropdown_feedback_save(request):
    """
    [POST] /commission/collect/api/dropdown-feedback/save/

    Body (JSON):
        {
            "emp_id":        "사번",
            "ym":            "202603",
            "feedback_type": "branch" | "hq",
            "value":         "입금예정" | "상위차감" | ...
        }

    권한:
        - feedback_type="branch" → head, leader만 저장 가능
        - feedback_type="hq"     → superuser만 저장 가능
    """
    body, err = _parse_json_body(request)
    if err:
        return _json_error(err)

    emp_id        = str(body.get("emp_id",        "")).strip()
    ym            = str(body.get("ym",            "")).strip()
    feedback_type = str(body.get("feedback_type", "")).strip()
    value         = str(body.get("value",         "")).strip()

    if not emp_id:
        return _json_error("대상자 사번을 입력해주세요.")
    if not ym:
        return _json_error("월도를 입력해주세요.")
    if feedback_type not in ("branch", "hq"):
        return _json_error("피드백 구분이 올바르지 않습니다.")

    # 권한 검증 (서버 최종 판정)
    grade = getattr(request.user, "grade", "")
    if feedback_type == "hq" and grade != "superuser":
        return _json_error("본사 피드백은 superuser만 저장할 수 있습니다.", status=403)
    if feedback_type == "branch" and grade not in ("head", "leader"):
        return _json_error("영업가족 피드백은 head 또는 leader만 저장할 수 있습니다.", status=403)

    try:
        fb = svc.save_dropdown_feedback(
            author=request.user,
            emp_id=emp_id,
            ym=ym,
            feedback_type=feedback_type,
            value=value,
        )
        log_action(
            request,
            ACTION.COLLECT_FEEDBACK_CREATE,
            meta={
                "emp_id": emp_id,
                "ym": ym,
                "feedback_type": feedback_type,
                "value": value,
                "feedback_id": fb.id,
            },
            success=True,
        )
        return _json_ok("저장 완료", data={"feedback_id": fb.id, "value": fb.value})

    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        logger.exception(
            "[api_collect_dropdown_feedback_save] 예외 emp_id=%s ym=%s type=%s",
            emp_id, ym, feedback_type,
        )
        return _json_error("저장 중 오류가 발생했습니다.")