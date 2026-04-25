# partner/views/pages.py
# ------------------------------------------------------------
# ✅ Pages(렌더링) 전용
# ------------------------------------------------------------

from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.decorators import login_required

from accounts.decorators import grade_required
from partner.models import SubAdminTemp

from .context import build_manage_context
from .constants import BRANCH_PARTS


def _accounts_search_url() -> str:
    """
    accounts 검색 API URL name이 환경/리팩터에 따라 달라져도 partner 페이지가 죽지 않게 방어.
    (commission/pages.py의 _accounts_search_url()와 동일한 후보 세트로 맞춤)
    """
    candidates = (
        # ✅ current SSOT
        "accounts:api_search_user",
        # ✅ older/legacy
        "accounts:api_accounts_search_user",
        "api_accounts_search_user",
        "api_search_user",
        # ✅ explicit legacy alias (있을 수도 있음)
        "accounts:search_user_legacy",
        "search_user_legacy",
    )
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/api/accounts/search-user/"


@login_required
@grade_required("superuser", "head", "leader", "basic")
def redirect_to_join(request):
    return redirect("partner:join_form")


@login_required
@grade_required("superuser", "head", "leader")
def manage_calculate(request):
    # ✅ Efficiency(지점효율)
    return build_manage_context(
        request=request,
        page_kind="efficiency",
        template_name="partner/manage_calculate.html",
        fetch_name="partner:efficiency_fetch",
        save_name="partner:efficiency_save",
        delete_name="partner:efficiency_delete_row",
        update_process_name="partner:efficiency_update_process_date",
        boot_key="ManageefficiencyBoot",
        extra_context={
            "search_user_url": _accounts_search_url(),
            "efficiency_confirm_groups_url": reverse("partner:efficiency_confirm_groups"),
        },
    )


@login_required
@grade_required("superuser", "head", "leader")
def manage_rate(request):
    user = request.user
    subadmin_info = SubAdminTemp.objects.filter(user=user).first()
    return build_manage_context(
        request=request,
        page_kind="rate",
        template_name="partner/manage_rate.html",
        fetch_name="partner:rate_fetch",
        save_name="partner:rate_save",
        delete_name="partner:rate_delete",
        update_process_name="partner:rate_update_process_date",
        boot_key="ManageRateBoot",
        extra_context={"subadmin_info": subadmin_info},
    )


@login_required
@grade_required("superuser", "head")
def manage_tables(request):
    return render(request, "partner/manage_tables.html")


@login_required
@grade_required("superuser", "head", "leader")
def manage_charts(request):
    # ✅ Structure(편제변경)
    user = request.user
    subadmin_info = SubAdminTemp.objects.filter(user=user).first()
    selected_branch = user.branch if getattr(user, "grade", "") == "head" and user.branch else None

    return build_manage_context(
        request=request,
        page_kind="structure",
        template_name="partner/manage_charts.html",
        fetch_name="partner:structure_fetch",
        save_name="partner:structure_save",
        delete_name="partner:structure_delete",
        update_process_name="partner:structure_update_process_date",
        boot_key="ManageStructureBoot",
        extra_context={
            "branches": sorted(list(BRANCH_PARTS.keys())),
            "selected_branch": selected_branch,
            "subadmin_info": subadmin_info,
            "search_user_url": _accounts_search_url(),
        },
    )


@login_required
@grade_required("superuser", "head", "leader", "basic")
def join_form(request):
    return render(request, "partner/join_form.html")
