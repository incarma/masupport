# django_ma/commission/views/pages.py
from __future__ import annotations

from typing import Tuple

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.decorators import grade_required
from accounts.models import CustomUser
from commission.models import ApprovalPending, DepositUploadLog, EfficiencyPayExcess, CollectRecord, CollectUploadLog, RateExample
from commission.upload_handlers.registry import supported_upload_types
from commission.services.collect import (
    get_available_yms,
    get_available_parts,
    get_available_bizmoons,
    date_to_ym,
)
from commission.services.rate_example import RateExampleService

from .constants import EXCESS_THRESHOLD

# =============================================================================
# UI order (fixed)
# =============================================================================

UPLOAD_TYPES_ORDER = [
    "최종지급액",
    "환수지급예상",
    "보증증액",
    "보증보험",
    "기타채권",
    "통산생보",
    "통산손보",
    "응당생보",
    "응당손보",
]

# =============================================================================
# Shared helpers (SSOT)
# =============================================================================


def _list_parts_excluding_centers() -> list[str]:
    qs = (
        CustomUser.objects.exclude(part__isnull=True)
        .exclude(part__exact="")
        .exclude(part__icontains="센터")
        .values_list("part", flat=True)
        .distinct()
        .order_by("part")
    )
    return list(qs)


def _ym_from_year_month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _parse_year_month(request) -> Tuple[int, int]:
    """
    GET year/month 파싱:
    - 없으면 현재 날짜 기반
    - month 범위 방어 (1~12)
    """
    today = timezone.localdate()
    raw_year = (request.GET.get("year") or "").strip()
    raw_month = (request.GET.get("month") or "").strip()

    year = int(raw_year) if raw_year.isdigit() else today.year
    month = int(raw_month) if raw_month.isdigit() else today.month

    if month < 1:
        month = 1
    elif month > 12:
        month = 12
    return year, month


def _year_options(selected_year: int, back_years: int = 5) -> list[int]:
    """
    연도 드롭다운 옵션:
    - 현재연도 기준 최근 back_years년 + 현재 포함
    - 사용자가 과거/미래 연도를 직접 GET으로 넣어도 옵션에 포함되게 방어
    """
    base_year = timezone.localdate().year
    years = list(range(base_year, base_year - back_years - 1, -1))
    if selected_year not in years:
        years.append(selected_year)
        years = sorted(set(years), reverse=True)
    return years


def _month_options() -> list[int]:
    return list(range(1, 13))


def _accounts_search_url() -> str:
    """
    Accounts 사용자 검색 API URL (SSOT + 안전 fallback)

    배포/브랜치마다 url name이 달라질 수 있어 reverse 실패(=500) 방지를 위해:
      1) 여러 후보 name을 순차 reverse 시도
      2) 전부 실패하면 하드코딩 경로로 fallback
    """
    candidates = (
        "accounts:api_search_user",
        "accounts:search_user_legacy",
        "accounts:api_accounts_search_user",
        "api_accounts_search_user",
        "api_search_user",
        "search_user_legacy",
    )
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/api/accounts/search-user/"


# =============================================================================
# Redirect
# =============================================================================


def redirect_to_deposit(request):
    return redirect("commission:deposit_home")


# =============================================================================
# Deposit Home
# =============================================================================


@grade_required("staff", "admin", "superuser")
def deposit_home(request):
    parts = _list_parts_excluding_centers()

    supported = set(supported_upload_types())
    upload_types = [x for x in UPLOAD_TYPES_ORDER if x in supported]

    logs = (
        DepositUploadLog.objects.filter(part__in=parts, upload_type__in=upload_types).only("part", "upload_type", "uploaded_at")
    )

    upload_dates: dict[str, dict[str, str]] = {p: {} for p in parts}
    for row in logs:
        ts = getattr(row, "uploaded_at", None)
        upload_dates[row.part][row.upload_type] = ts.strftime("%Y-%m-%d") if ts else "-"

    # 템플릿에서 키 존재를 기대하므로 빈 값도 채워줌
    for p in parts:
        for ut in upload_types:
            upload_dates[p].setdefault(ut, "-")

    ctx = {
        "parts": parts,
        "upload_types": upload_types,
        "upload_dates": upload_dates,
        "supported_upload_types": upload_types,
        "accounts_search_url": _accounts_search_url(),
    }
    return render(request, "commission/deposit_home.html", ctx)


# =============================================================================
# Approval Home (수수료결재)
# =============================================================================


@grade_required("staff", "admin", "superuser")
def approval_home(request):
    """
    ✅ approval_home.html이 기대하는 키(SSOT)
      - years, months
      - selected_year, selected_month
      - parts, selected_part
      - selected_ym (YYYY-MM)
      - pending_rows, efficiency_rows (둘 다 select_related('user'))

    GET 컨트롤: year/month/part
    """
    parts = _list_parts_excluding_centers()

    year, month = _parse_year_month(request)
    selected_ym = _ym_from_year_month(year, month)

    selected_part = (request.GET.get("part") or "").strip()
    if selected_part and selected_part not in parts:
        selected_part = ""

    # -------------------------------------------------------------------------
    # 1) Pending (approval_flag='N' + 유자격 조건)
    # -------------------------------------------------------------------------
    pending_qs = (
        ApprovalPending.objects.select_related("user").filter(
            ym=selected_ym,
            user__isnull=False,
            approval_flag="N",
            user__regist__in=["손생등록", "손보등록", "생보등록"],
        )
    )

    # -------------------------------------------------------------------------
    # 2) Efficiency excess (threshold 이상)
    # -------------------------------------------------------------------------
    efficiency_qs = (
        EfficiencyPayExcess.objects.select_related("user").filter(
            ym=selected_ym,
            user__isnull=False,
            pay_amount_sum__gt=EXCESS_THRESHOLD,
        )
    )

    if selected_part:
        pending_qs = pending_qs.filter(user__part=selected_part)
        efficiency_qs = efficiency_qs.filter(user__part=selected_part)

    pending_rows = pending_qs.order_by("user__part", "user__branch", "user__name", "user__id")
    efficiency_rows = efficiency_qs.order_by("user__part", "user__branch", "user__name", "user__id")

    ctx = {
        # controls options
        "years": _year_options(year, back_years=5),
        "months": _month_options(),
        # selected values
        "selected_year": year,
        "selected_month": month,
        "parts": parts,
        "selected_part": selected_part,
        # reference key
        "selected_ym": selected_ym,
        # rows
        "pending_rows": pending_rows,
        "efficiency_rows": efficiency_rows,
        # common
        "accounts_search_url": _accounts_search_url(),
    }
    return render(request, "commission/approval_home.html", ctx)


# =============================================================================
# Support Home (현재 미사용)
# =============================================================================
@grade_required("staff", "admin", "superuser")
def support_home(request):
    # 미사용이면 안전하게 deposit으로 보냄
    return redirect("commission:deposit_home")


##############################################################################
# [Step 7] commission/views/pages.py — collect_home 뷰 추가
# 파일 최하단에 아래 코드를 추가한다.
############################################################################## 
@grade_required("superuser", "head", "leader")
def collect_home(request):
    """
    환수관리(Collect Home) 페이지 뷰 — Step 7
 
    [컨텍스트]
    - available_yms  : 업로드된 월도 목록 (최신순, 드롭다운용)
    - parts          : 부서 목록 (CollectRecord 기반)
    - bizmoons       : 부문 목록 (CollectRecord 기반)
    - default_ym     : 기본 선택 월도 (가장 최신, 없으면 현재 월도)
    - current_user_id: 로그인 사용자 사번 (피드백 버튼 노출 판단용)
    - accounts_search_url: 사용자 검색 API URL (search_user_modal 연계)
    - last_upload_log: 최근 업로드 이력 (없으면 None)
 
    [SSOT 재사용]
    - _accounts_search_url(): 기존 deposit/approval 공용 함수
    - API URL은 템플릿에서 {% url %} 태그로 직접 주입 (dataset 규약)
    """
    available_yms = get_available_yms()
    parts         = get_available_parts()
    bizmoons      = get_available_bizmoons()
 
    # 기본 월도: 가장 최신 업로드 월도, 없으면 현재 월도
    default_ym = available_yms[0] if available_yms else date_to_ym(timezone.localdate())
 
    # 최근 업로드 이력 (업로드 현황 표시용)
    last_upload_log = CollectUploadLog.objects.first()
 
    ctx = {
        "available_yms":    available_yms,
        "parts":            parts,
        "bizmoons":         bizmoons,
        "default_ym":       default_ym,
        "current_user_id":  str(request.user.id),
        "accounts_search_url": _accounts_search_url(),
        "last_upload_log":  last_upload_log,
        "current_user_grade": str(request.user.grade),
    }
    return render(request, "commission/collect_home.html", ctx)


# =============================================================================
# Collect Notice (환수내역 안내자료 제작) — superuser 전용
# =============================================================================

from datetime import date as _date  # noqa: E402  (파일 하단 local import — 순환 참조 없음)


@grade_required("superuser")
def collect_notice(request):
    """
    환수내역 안내자료 제작 페이지.

    [설계 원칙]
    - superuser 전용 (@grade_required 단독 적용 — login_required는 grade_required 내부에서 처리)
    - 파일 처리는 100% 클라이언트(SheetJS + ExcelJS)에서 전담 → 서버 업로드/저장 없음
    - 비즈니스 로직 없음 → 서비스 레이어 호출 없음
    - audit 로그 미적용 (서버 전송 없음, 추후 확장 가능)

    [컨텍스트]
    - accounts_search_url : 대상자 검색 모달 연동 (collect_home과 동일 SSOT 재사용)
    - current_year        : 기준 연월 셀렉트 초기값 세팅용 (JS에서 data-current-year로 읽음)
    """
    ctx = {
        "accounts_search_url": _accounts_search_url(),  # 기존 SSOT 함수 재사용
        "current_year": _date.today().year,
    }
    return render(request, "commission/collect_notice.html", ctx)


# =============================================================================
# Rate Example Home (예시표) — superuser 전용
# =============================================================================

@login_required
@grade_required("superuser")   # head 확장 시 이 줄만 수정
def rate_example_home(request):
    """
    예시표 목록 페이지.
    현재: superuser 전용.
    추후 head 확장 시: @grade_required("superuser", "head") 로만 수정.
    업로드/다운로드/삭제 API 뷰(api_rate_example.py)는 superuser 고정이므로
    이 파일 수정만으로 분리가 완성된다.
    """
    examples = RateExampleService.list_all()
    context = {
        "examples":         examples,
        "life_insurers":    RateExample.LIFE_INSURERS,
        "nonlife_insurers": RateExample.NONLIFE_INSURERS,
        "upload_url":       reverse("commission:rate_example_upload"),
        "conversion_list_url": reverse("commission:rate_example_conversion_list"),
        "is_superuser":     request.user.grade == "superuser",
    }
    return render(request, "commission/rate_example_home.html", context)