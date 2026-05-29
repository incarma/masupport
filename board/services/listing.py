# django_ma/board/services/listing.py
# =========================================================
# Listing Services
# - 목록 공통 필터/검색/페이지네이션 (Post/Task 공용)
# - 기능 영향 최소화를 위해 기존 로직 1:1로 이동
# =========================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest
from django.utils.dateparse import parse_date

from ..constants import PER_PAGE_CHOICES

User = get_user_model()


# ---------------------------------------------------------
# ✅ 공용 UI: 담당자 목록
# ---------------------------------------------------------
def get_handlers() -> List[str]:
    """담당자 목록: superuser의 name만 노출(기존 정책 유지)"""
    return list(
        User.objects
        .filter(grade="superuser")
        .exclude(name__isnull=True)
        .exclude(name__exact="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )


# ---------------------------------------------------------
# ✅ QueryString / Paging
# ---------------------------------------------------------
def get_per_page(request: HttpRequest, default: int = 10) -> int:
    raw = str(request.GET.get("per_page", "")).strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return n if n in PER_PAGE_CHOICES else default


def build_query_string_without_page(request: HttpRequest) -> str:
    q = request.GET.copy()
    q.pop("page", None)
    return q.urlencode()


def paginate(request: HttpRequest, qs: QuerySet, *, default_per_page: int = 10):
    per_page = get_per_page(request, default=default_per_page)
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    return page_obj, per_page


# ---------------------------------------------------------
# ✅ Date range
# ---------------------------------------------------------
def parse_date_range(request: HttpRequest) -> Tuple[str, str, Optional[Any], Optional[Any]]:
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    return date_from_raw, date_to_raw, date_from, date_to


# ---------------------------------------------------------
# ✅ 검색/필터
# ---------------------------------------------------------
def apply_keyword_filter(
    qs: QuerySet,
    keyword: str,
    search_type: str,
    *,
    title_field: str,
    content_field: str,
    user_name_field: str,
) -> QuerySet:
    """검색 타입(title/content/title_content/user_name)에 따른 keyword 필터"""
    if not keyword:
        return qs

    if search_type == "title":
        return qs.filter(**{f"{title_field}__icontains": keyword})
    if search_type == "content":
        return qs.filter(**{f"{content_field}__icontains": keyword})
    if search_type == "title_content":
        return qs.filter(
            Q(**{f"{title_field}__icontains": keyword}) |
            Q(**{f"{content_field}__icontains": keyword})
        )
    if search_type == "user_name":
        return qs.filter(**{f"{user_name_field}__icontains": keyword})

    # fallback
    return qs.filter(**{f"{title_field}__icontains": keyword})


def apply_common_list_filters(
    qs: QuerySet,
    *,
    date_from,
    date_to,
    selected_category: str,
    selected_handler: str,
    selected_status: str,
    category_field: str = "category",
    handler_field: str = "handler",
    status_field: str = "status",
    created_field: str = "created_at",
) -> QuerySet:
    """게시판 목록 공용 필터(기간/카테고리/담당자/상태)"""
    if date_from:
        qs = qs.filter(**{f"{created_field}__date__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{created_field}__date__lte": date_to})

    if selected_category and selected_category != "전체":
        qs = qs.filter(**{f"{category_field}__iexact": selected_category})

    if selected_handler != "전체":
        qs = qs.filter(**{handler_field: selected_handler})

    if selected_status != "전체":
        qs = qs.filter(**{status_field: selected_status})

    return qs


# ---------------------------------------------------------
# ✅ Request param bundle (SSOT)
# ---------------------------------------------------------
@dataclass(frozen=True)
class ListParams:
    keyword: str
    search_type: str
    selected_handler: str
    selected_status: str
    selected_category: str
    date_from_raw: str
    date_to_raw: str
    date_from: Optional[Any]
    date_to: Optional[Any]


def read_list_params(request: HttpRequest) -> ListParams:
    keyword = (request.GET.get("keyword") or "").strip()
    search_type = (request.GET.get("search_type") or "title").strip()

    selected_handler = (request.GET.get("handler") or "전체").strip()
    selected_status = (request.GET.get("status") or "전체").strip()
    selected_category = (request.GET.get("category") or "전체").strip()

    date_from_raw, date_to_raw, date_from, date_to = parse_date_range(request)

    return ListParams(
        keyword=keyword,
        search_type=search_type,
        selected_handler=selected_handler,
        selected_status=selected_status,
        selected_category=selected_category,
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------
# ✅ Post / Task 기본 쿼리셋 빌더
# ---------------------------------------------------------

def _build_user_channel_subquery() -> Subquery:
    """
    Post.user_id → CustomUser.channel 서브쿼리.
    emp_id 필드 존재 여부에 따라 OR 매칭 적용한다.
    """
    try:
        User._meta.get_field("emp_id")
        has_emp_id = True
    except FieldDoesNotExist:
        has_emp_id = False

    if has_emp_id:
        return Subquery(
            User.objects
            .filter(Q(id=OuterRef("user_id")) | Q(emp_id=OuterRef("user_id")))
            .values("channel")[:1]
        )
    return Subquery(
        User.objects.filter(id=OuterRef("user_id")).values("channel")[:1]
    )


def get_post_base_qs() -> QuerySet:
    """
    Post 목록 기본 쿼리셋.
    comment_count, user_channel(부문) annotate 포함.
    visibility 필터는 apply_post_visibility()로 별도 적용한다.
    """
    from ..models import Post
    return (
        Post.objects.annotate(
            comment_count=Count("comments", distinct=True),
            user_channel=Coalesce(_build_user_channel_subquery(), Value("")),
        )
        .order_by("-created_at")
    )


def apply_post_visibility(qs: QuerySet, user) -> QuerySet:
    """
    Post 목록 visibility 정책 적용 (board/policies.py 목록 레벨).
    superuser → 전체, head → 본인+지점, leader → 본인.
    """
    grade = (getattr(user, "grade", "") or "").strip()
    if grade == "superuser":
        return qs

    user_key = (
        getattr(user, "emp_id", None)
        or getattr(user, "user_id", None)
        or user.id
    )
    my_id = str(user_key or "")
    legacy_pk = str(getattr(user, "id", "") or "")

    mine_q = Q(user_id=my_id)
    if legacy_pk and legacy_pk != my_id:
        mine_q = mine_q | Q(user_id=legacy_pk)

    if grade == "head":
        my_branch = (getattr(user, "branch", "") or "").strip()
        return qs.filter(mine_q | Q(user_branch__iexact=my_branch))

    return qs.filter(mine_q)


def get_task_base_qs() -> QuerySet:
    """Task 목록 기본 쿼리셋 (comment_count annotate 포함)."""
    from ..models import Task
    return (
        Task.objects.annotate(comment_count=Count("comments", distinct=True))
        .order_by("-created_at")
    )
