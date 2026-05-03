# board/views/worktasks.py
"""
WorkTask 뷰 레이어.

보안 원칙 (worktask.md §7):
    - 모든 뷰에 @grade_required("superuser") 적용
    - ORM 직접 호출 금지 → board.services.worktasks 경유 필수
    - 첨부 다운로드: 소유자 검증 후 FileResponse (RFC5987 파일명)
    - AJAX 응답: {"ok": true/false, ...} 규약

⚠️ 절대 수정 주의: 첨부 다운로드 권한 체크 로직 (worktask.md §17)
"""

from __future__ import annotations

import logging
import urllib.parse
import calendar
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.http import (
    FileResponse,
    Http404,
    HttpResponseForbidden,
    HttpResponseServerError,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models.functions import Trim

from accounts.decorators import grade_required
from accounts.models import CustomUser
from board.forms import WorkTaskCommentForm
from board.models import WorkCategory, WorkTask, WorkTaskAttachment, WorkTaskComment
from board.services.holidays import get_holidays_between, resolve_next_business_day
from board.services import worktasks as wt_svc
from board.services.comments import handle_comments_actions

logger = logging.getLogger(__name__)


# =============================================================================
# 지점 옵션 유틸
# =============================================================================

def _get_worktask_branch_options(request) -> list[str]:
    """
    WorkTask 지점 선택 옵션.
    - superuser: 활성 사용자 CustomUser.branch 전체 distinct
    - 그 외: 본인 branch만 노출
    """
    user = request.user

    if getattr(user, "grade", "") == "superuser":
        qs = CustomUser.objects.filter(is_active=True)
        part = (getattr(user, "part", "") or "").strip()
        channel = (getattr(user, "channel", "") or "").strip()
        if part:
            qs = qs.filter(part=part)
        elif channel:
            qs = qs.filter(channel=channel)

        return list(
            qs
            .annotate(branch_name=Trim("branch"))
            .exclude(branch_name="")
            .values_list("branch_name", flat=True)
            .distinct()
            .order_by("branch_name")
        )

    branch = (getattr(user, "branch", "") or "").strip()
    return [branch] if branch else []


# =============================================================================
# JSON 응답 헬퍼 — 규약: {"ok": true/false, ...}
# =============================================================================

def _ok(**kwargs) -> JsonResponse:
    return JsonResponse({"ok": True,  **kwargs})

def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=status)


# =============================================================================
# YM 유틸
# =============================================================================

def _today_ym() -> str:
    d = timezone.localdate()
    return f"{d.year}-{d.month:02d}"


def _adjacent_yms(ym: str) -> tuple[str, str]:
    """이전달/다음달 YM ('YYYY-MM') 반환."""
    try:
        y, m = int(ym[:4]), int(ym[5:7])
    except (ValueError, IndexError):
        d = timezone.localdate()
        y, m = d.year, d.month

    pm, py = (m - 1, y) if m > 1  else (12, y - 1)
    nm, ny = (m + 1, y) if m < 12 else (1,  y + 1)
    return f"{py}-{pm:02d}", f"{ny}-{nm:02d}"


def _month_range_from_ym(ym: str) -> tuple[date, date]:
    try:
        y, m = int(ym[:4]), int(ym[5:7])
    except (ValueError, IndexError):
        d = timezone.localdate()
        y, m = d.year, d.month

    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _week_range_containing(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


# =============================================================================
# 목록
# =============================================================================

@grade_required("superuser")
def worktask_list(request):
    """
    업무 항목 목록.

    Boot 패턴 (worktask.md §7.2):
        id="worktaskListBoot" data-* 로 URL 주입.
        JS는 dataset 만 읽는다.
    필터: ym(귀속월) / status / category
    """
    ym       = request.GET.get("ym",       _today_ym())
    status   = request.GET.get("status",   "")
    category = request.GET.get("category", "")
    branch   = request.GET.get("branch",   "")
    keyword  = request.GET.get("keyword",  "")
    cal_view = request.GET.get("cal_view", "week")
    cal_anchor_raw = request.GET.get("cal_anchor", "")

    # 서비스 경유 (소유자 격리 보장)
    qs = wt_svc.get_user_queryset(request.user)
    qs = wt_svc.apply_filters(qs, {
        "ym": ym, "status": status, "category": category,
        "branch": branch, "keyword": keyword
    })
    qs = qs.order_by("priority", "due_date", "-created_at")

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    categories     = WorkCategory.objects.filter(is_active=True).order_by("sort_order")
    status_choices = WorkTask.STATUS_CHOICES
    prev_ym, next_ym = _adjacent_yms(ym)
    today = timezone.localdate()
    business_today = resolve_next_business_day(today)

    try:
        ay, am, ad = map(int, cal_anchor_raw.split("-"))
        calendar_anchor = date(ay, am, ad)
    except (ValueError, TypeError):
        # 오늘이 주말/공휴일이면 기본 캘린더 기준일도 다음 영업일로 보정한다.
        # 그래야 사용자가 주말/공휴일에 접속해도 당일 미완료 업무가 화면에 보인다.
        calendar_anchor = business_today

    if cal_view not in ("week", "month"):
        cal_view = "week"

    month_start, month_end = _month_range_from_ym(ym)
    week_start, week_end = _week_range_containing(calendar_anchor)
    view_month_start, view_month_end = _month_range_from_ym(
        f"{calendar_anchor.year}-{calendar_anchor.month:02d}"
    )

    calendar_range_start = min(view_month_start, week_start)
    calendar_range_end = max(view_month_end, week_end)

    # 공휴일은 WorkTask 소유자 스코프와 별개인 공통 캘린더 데이터다.
    # 외부 API를 View에서 직접 호출하지 않고 DB 캐시만 조회한다.
    calendar_holidays = get_holidays_between(
        calendar_range_start,
        calendar_range_end,
    )

    calendar_items = wt_svc.build_calendar_payload(
        request.user,
        range_start=calendar_range_start,
        range_end=calendar_range_end,
        today=today,
        business_today=business_today,
    )

    return render(request, "board/worktask_list.html", {
        "page_obj":      page_obj,
        "ym":            ym,
        "prev_ym":       prev_ym,
        "next_ym":       next_ym,
        "status":        status,
        "category":      category,
        "branch":        branch,
        "categories":    categories,
        "branch_options": _get_worktask_branch_options(request),
        "status_choices": status_choices,
        "keyword": keyword,
        "calendar_items": calendar_items,
        "calendar_today": business_today.isoformat(),
        "calendar_real_today": today.isoformat(),
        "calendar_anchor": calendar_anchor.isoformat(),
        "calendar_view": cal_view,
        "calendar_week_start": week_start.isoformat(),
        "calendar_week_end": week_end.isoformat(),
        "calendar_month_start": view_month_start.isoformat(),
        "calendar_month_end": view_month_end.isoformat(),
        "calendar_holidays": calendar_holidays,
    })


# =============================================================================
# 등록
# =============================================================================

@grade_required("superuser")
def worktask_create(request):
    """
    업무 항목 등록.
    owner=request.user 는 서비스에서 강제 주입 (뷰에서 직접 지정 금지).
    """
    categories = WorkCategory.objects.filter(is_active=True).order_by("sort_order")

    if request.method == "POST":
        data = _extract_post_data(request)
        try:
            task = wt_svc.create_task(request.user, data)
            for f in request.FILES.getlist("attachments"):
                wt_svc.save_attachment(task, f, request.user)
            return redirect("board:worktasks:worktask_detail", pk=task.pk)
        except Exception:
            logger.exception("WorkTask 생성 실패: user=%s", request.user.pk)
            return render(request, "board/worktask_create.html", {
                "categories": categories,
                "branch_options": _get_worktask_branch_options(request),
                "error":      "저장 중 오류가 발생했습니다. 다시 시도해 주세요.",
                "post_data":  request.POST,
            })

    return render(request, "board/worktask_create.html", {
        "categories": categories,
        "branch_options": _get_worktask_branch_options(request),
    })


# =============================================================================
# 상세
# =============================================================================

@grade_required("superuser")
def worktask_detail(request, pk: int):
    """
    업무 항목 상세.
    get_user_task → owner != request.user 이면 404.
    """
    task         = wt_svc.get_user_task(request.user, pk)

    if request.method == "POST":
        handled = handle_comments_actions(
            request=request,
            obj=task,
            comment_model=WorkTaskComment,
            fk_field="task",
            redirect_detail_name="board:worktasks:worktask_detail",
        )
        if handled:
            return handled
        return redirect("board:worktasks:worktask_detail", pk=task.pk)

    attachments  = task.attachments.all()
    related_users = task.related_users.all()

    return render(request, "board/worktask_detail.html", {
        "task":          task,
        "attachments":   attachments,
        "related_users": related_users,
        "comments":      task.comments.order_by("-created_at"),
        "form":          WorkTaskCommentForm(),
    })


# =============================================================================
# 수정
# =============================================================================

@grade_required("superuser")
def worktask_edit(request, pk: int):
    """
    업무 항목 수정.
    get_user_task → owner != request.user 이면 404.
    """
    task       = wt_svc.get_user_task(request.user, pk)
    categories = WorkCategory.objects.filter(is_active=True).order_by("sort_order")

    if request.method == "POST":
        data = _extract_post_data(request)
        try:
            wt_svc.update_task(task, data)
            # 신규 첨부
            for f in request.FILES.getlist("attachments"):
                wt_svc.save_attachment(task, f, request.user)
            # 첨부 삭제 (delete_att_<id> 체크박스)
            for key in request.POST:
                if key.startswith("delete_att_"):
                    try:
                        att_id = int(key.split("_")[-1])
                        att = get_object_or_404(WorkTaskAttachment, pk=att_id, task=task)
                        wt_svc.delete_attachment(att, request.user)
                    except (ValueError, Http404):
                        pass
            return redirect("board:worktasks:worktask_detail", pk=task.pk)
        except Exception:
            logger.exception("WorkTask 수정 실패: pk=%s user=%s", pk, request.user.pk)
            return render(request, "board/worktask_edit.html", {
                "task":       task,
                "categories": categories,
                "attachments": task.attachments.all(),
                "branch_options": _get_worktask_branch_options(request),
                "error":      "저장 중 오류가 발생했습니다. 다시 시도해 주세요.",
            })

    return render(request, "board/worktask_edit.html", {
        "task":        task,
        "categories":  categories,
        "attachments": task.attachments.all(),
        "branch_options": _get_worktask_branch_options(request),
    })


# =============================================================================
# AJAX: 완료 처리
# =============================================================================

@require_POST
@grade_required("superuser")
def worktask_done(request, pk: int):
    """
    완료 처리 AJAX (POST).
    성공: {"ok": true, "status": "done", "status_display": "완료"}
    """
    task = wt_svc.get_user_task(request.user, pk)
    if task.status != WorkTask.STATUS_DONE:
        wt_svc.mark_done(task)
    return _ok(status=task.status, status_display=task.get_status_display_label())


# =============================================================================
# AJAX: 건너뜀 처리
# =============================================================================

@require_POST
@grade_required("superuser")
def worktask_skip(request, pk: int):
    """
    건너뜀 처리 AJAX (POST).
    성공: {"ok": true, "status": "skipped", "status_display": "건너뜀"}
    """
    task = wt_svc.get_user_task(request.user, pk)
    if task.status != WorkTask.STATUS_SKIPPED:
        wt_svc.mark_skipped(task)
    return _ok(status=task.status, status_display=task.get_status_display_label())


# =============================================================================
# 첨부파일 보안 다운로드 — 핵심 보안 뷰
# =============================================================================

@grade_required("superuser")
def worktask_att_download(request, att_id: int):
    """
    첨부파일 보안 다운로드 (worktask.md §7.4 체크리스트).

    체크 순서:
        ① superuser 여부          → @grade_required("superuser") 로 보장
        ② att.task.owner == user  → 소유자 격리 검증 (403)
        ③ FileResponse             → RFC5987 한글 파일명
        ④ 파일 핸들 close          → Django FileResponse 가 자동 close

    ❌ att.file.url 직접 노출 절대 금지
    """
    att = get_object_or_404(WorkTaskAttachment, pk=att_id)

    # ② 소유자 격리
    if att.task.owner_id != request.user.pk:
        logger.warning(
            "WorkTaskAttachment 소유자 불일치: att_pk=%s task_owner=%s requester=%s",
            att_id, att.task.owner_id, request.user.pk,
        )
        return HttpResponseForbidden("접근 권한이 없습니다.")

    # ③ RFC5987 파일명 (한글 깨짐 방지)
    ascii_name   = att.original_name.encode("ascii", "ignore").decode("ascii") or "download"
    encoded_name = urllib.parse.quote(att.original_name, safe="")
    disposition  = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{encoded_name}"
    )

    # ④ 파일 열기 (Django FileResponse 가 close 보장)
    try:
        fh = att.file.open("rb")
    except Exception:
        logger.exception("첨부파일 열기 실패: att_pk=%s path=%r", att_id, att.file.name)
        return HttpResponseServerError("파일을 열 수 없습니다.")

    response = FileResponse(fh, as_attachment=True)
    response["Content-Disposition"] = disposition
    return response


# =============================================================================
# 알림 폴링 API
# =============================================================================

@grade_required("superuser")
def worktask_notify_check(request):
    """
    미완료 알림 폴링 API (GET).

    응답: {"ok": true, "count": N, "items": [{pk, title, due_date, days_left}, ...]}
    마감 임박(notify_days_before 이내) 미완료 항목 목록 반환.
    """
    today = timezone.localdate()
    qs    = wt_svc.get_user_queryset(request.user).filter(
        due_date__isnull=False,
        status__in=[WorkTask.STATUS_PENDING, WorkTask.STATUS_IN_PROGRESS],
    )

    items = []
    for task in qs:
        days_left = (task.due_date - today).days
        if days_left <= task.notify_days_before:
            items.append({
                "pk":       task.pk,
                "title":    task.title,
                "due_date": task.due_date.isoformat(),
                "days_left": days_left,
            })

    return _ok(count=len(items), items=items)


# =============================================================================
# AJAX: 상태 해제 (완료/건너뜀 → 대기)
# =============================================================================

@require_POST
@grade_required("superuser")
def worktask_reset(request, pk: int):
    """
    완료/건너뜀 상태를 대기(pending)로 초기화 AJAX (POST).
    성공: {"ok": true, "status": "pending", "status_display": "대기"}
    """
    task = wt_svc.get_user_task(request.user, pk)
    wt_svc.mark_pending(task)
    return _ok(status=task.status, status_display=task.get_status_display_label())


# =============================================================================
# AJAX: 인라인 필드 업데이트 (목록 셀 편집)
# =============================================================================

@require_POST
@grade_required("superuser")
def worktask_inline_update(request, pk: int):
    """
    목록 페이지 인라인 셀 편집 AJAX (POST).

    POST body (JSON):
        field : "category" | "priority" | "start_date" | "due_date" | "status"
        value : 새 값 (문자열)

    성공: {"ok": true, "field": ..., "value": ..., "display": ...}
    """
    import json
    from datetime import date as _date

    task = wt_svc.get_user_task(request.user, pk)

    try:
        body  = json.loads(request.body)
        field = body.get("field", "").strip()
        value = body.get("value", "")
    except (json.JSONDecodeError, AttributeError):
        return _err("잘못된 요청입니다.")

    ALLOWED_FIELDS = {"category", "priority", "start_date", "due_date", "status"}
    if field not in ALLOWED_FIELDS:
        return _err(f"수정 불가 필드: {field}")

    # 필드별 값 변환 및 검증
    if field == "category":
        from board.models import WorkCategory
        try:
            cat = WorkCategory.objects.get(code=value, is_active=True)
        except WorkCategory.DoesNotExist:
            return _err("존재하지 않는 분류입니다.")
        task.category = cat
        task.save(update_fields=["category", "updated_at"])
        return _ok(field=field, value=cat.code, display=cat.label)

    elif field == "priority":
        if value not in (WorkTask.PRIORITY_HIGH, WorkTask.PRIORITY_MID, WorkTask.PRIORITY_LOW):
            return _err("잘못된 우선순위 값입니다.")
        task.priority = value
        task.save(update_fields=["priority", "updated_at"])
        display = dict(WorkTask.PRIORITY_CHOICES).get(value, value)
        return _ok(field=field, value=value, display=display)
    
    elif field == "status":
        status_map = dict(WorkTask.STATUS_CHOICES)
        if value not in status_map:
            return _err("잘못된 상태 값입니다.")
        task.status = value
        task.save(update_fields=["status", "updated_at"])
        return _ok(field=field, value=value, display=status_map.get(value, value))

    elif field in ("start_date", "due_date"):
        if value:
            try:
                y, m, d = map(int, value.split("-"))
                parsed = _date(y, m, d)
            except (ValueError, TypeError):
                return _err("날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)")
        else:
            parsed = None
        setattr(task, field, parsed)
        task.save(update_fields=[field, "updated_at"])
        display = parsed.strftime("%m/%d") if parsed else "—"
        return _ok(field=field, value=value, display=display)

    return _err("처리할 수 없는 요청입니다.")


# =============================================================================
# AJAX: 삭제 처리
# =============================================================================

@require_POST
@grade_required("superuser")
def worktask_delete(request, pk: int):
    """
    WorkTask 삭제 AJAX (POST).

    소유자 격리: get_user_task → owner != request.user 이면 404.
    성공 시 목록 redirect URL 반환.
    """
    task = wt_svc.get_user_task(request.user, pk)
    task.delete()
    logger.info("WorkTask deleted: pk=%s owner=%s", pk, request.user.pk)
    return _ok(redirect_url=f"/board/worktasks/")


# =============================================================================
# 내부 헬퍼 — POST 데이터 추출
# =============================================================================

def _extract_post_data(request) -> dict:
    """
    POST 데이터에서 WorkTask 필드값 안전 추출.
    related_users → User 인스턴스 리스트로 변환.
    숫자 필드 → 안전 변환.
    """
    from accounts.models import CustomUser

    post = request.POST

    def _int_or(key: str, default):
        try:
            return int(post.get(key, ""))
        except (ValueError, TypeError):
            return default

    # 관련인물 pk 목록 → User 인스턴스
    uid_list = post.getlist("related_users")
    related  = list(CustomUser.objects.filter(pk__in=uid_list)) if uid_list else []

    # 날짜 안전 파싱 헬퍼
    def _parse_date(key: str):
        raw = post.get(key, "").strip()
        if not raw:
            return None
        try:
            y, m, d = map(int, raw.split("-"))
            return date(y, m, d)
        except (ValueError, TypeError):
            return None

    start_date = _parse_date("start_date")
    due_date   = _parse_date("due_date")

    return {
        "category_id":         post.get("category", "").strip() or None,
        "title":               post.get("title", "").strip(),
        "description":         post.get("description", "").strip(),
        "start_date":          start_date,
        "due_date":            due_date,
        "calendar_span_mode":   post.get("calendar_span_mode") == "1",
        "recurrence_type":     post.get("recurrence_type", WorkTask.RECURRENCE_NONE),
        "recurrence_day":      _int_or("recurrence_day", None),
        "status":              post.get("status", WorkTask.STATUS_PENDING),
        "priority":            post.get("priority", WorkTask.PRIORITY_MID),
        "related_users":       related,
        "family_branches":     post.getlist("family_branches"),
    }