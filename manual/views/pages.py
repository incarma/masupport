# django_ma/manual/views/pages.py

from __future__ import annotations

from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import grade_required, not_inactive_required
from audit.constants import ACTION
from audit.services import log_action

from ..forms import ManualForm
from ..models import Manual
from ..utils import ensure_default_section, manual_accessible_or_denied, filter_manuals_for_user


@grade_required("superuser", "head", "leader", "basic")
def redirect_to_manual(request):
    return redirect("manual:manual_list")


@not_inactive_required
def manual_list(request):
    """
    매뉴얼 목록
    - 직원전용(is_published=False)은 superuser만 노출
    - 관리자전용(admin_only=True)은 superuser/head만 노출
    """
    qs = Manual.objects.all()
    qs = filter_manuals_for_user(qs, request.user)

    qs = qs.order_by("sort_order", "-updated_at")
    return render(request, "manual/manual_list.html", {"manuals": qs})


@not_inactive_required
def manual_detail(request, pk):
    """
    매뉴얼 상세
    - 접근권한 체크(서버에서 최종 판단)
    - 섹션 0개면 기본 섹션 생성
    - sections -> blocks -> attachments prefetch
    """
    manual = get_object_or_404(Manual, pk=pk)

    denied = manual_accessible_or_denied(request, manual)
    if denied:
        return denied

    ensure_default_section(manual)

    sections = (
        manual.sections
        .prefetch_related("blocks", "blocks__attachments")
        .order_by("sort_order", "created_at")
    )
    return render(request, "manual/manual_detail.html", {"m": manual, "sections": sections})


@grade_required("superuser")
def manual_create(request):
    """superuser 전용: 폼 기반 생성(관리용)"""
    if request.method == "POST":
        form = ManualForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.author = request.user
            obj.save()
            log_action(request, ACTION.MANUAL_CREATE, obj=obj, meta={"title": obj.title})
            return redirect("manual:manual_detail", pk=obj.pk)
    else:
        form = ManualForm()

    return render(request, "manual/manual_form.html", {"form": form, "mode": "create"})


@grade_required("superuser")
def manual_edit(request, pk):
    """superuser 전용: 폼 기반 수정(관리용)"""
    obj = get_object_or_404(Manual, pk=pk)

    if request.method == "POST":
        form = ManualForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            log_action(request, ACTION.MANUAL_UPDATE, obj=obj, meta={"title": obj.title})
            return redirect("manual:manual_detail", pk=obj.pk)
    else:
        form = ManualForm(instance=obj)

    return render(request, "manual/manual_form.html", {"form": form, "mode": "edit", "m": obj})


def rules_home(request):
    return render(request, "manual/rules_home.html")
