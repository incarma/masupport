# django_ma/accounts/admin.py
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Iterable, Optional

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from openpyxl import Workbook

from .constants import (
    CACHE_ERROR_PREFIX,
    CACHE_PROGRESS_PREFIX,
    CACHE_RESULT_PATH_PREFIX,
    CACHE_STATUS_PREFIX,
    CACHE_TIMEOUT_SECONDS,
    EXCEL_CONTENT_TYPE,
    ADMIN_ACTION_RESET_PASSWORD_AND_UNLOCK,
    cache_key,
)
from .custom_admin import custom_admin_site
from .forms import ExcelUploadForm
from .models import CustomUser
from .tasks import process_users_excel_task
from audit.constants import ACTION
from audit.services import log_action

# =============================================================================
# Settings / Constants
# =============================================================================

TEMPLATE_REL_PATH = "accounts/excel/양식_계정관리.xlsx"
TEMPLATE_DOWNLOAD_NAME = "양식_계정관리.xlsx"

EXPORT_SELECTED_FILENAME = "selected_custom_users.xlsx"
EXPORT_ALL_FILENAME = "all_custom_users.xlsx"

DEFAULT_BATCH_SIZE = 500

SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-z가-힣._-]+")

GRADE_DISPLAY = {
    "superuser": "Superuser",
    "main_admin": "Main Admin",
    "sub_admin": "Sub Admin",
    "basic": "Basic",
    "resign": "Resign",
    "inactive": "Inactive",
}


# =============================================================================
# Cache helpers (constants 기반)
# =============================================================================
def _init_upload_cache(task_id: str) -> None:
    cache.set(cache_key(CACHE_PROGRESS_PREFIX, task_id), 0, timeout=CACHE_TIMEOUT_SECONDS)
    cache.set(cache_key(CACHE_STATUS_PREFIX, task_id), "PENDING", timeout=CACHE_TIMEOUT_SECONDS)
    cache.delete(cache_key(CACHE_ERROR_PREFIX, task_id))
    cache.delete(cache_key(CACHE_RESULT_PATH_PREFIX, task_id))


# =============================================================================
# File helpers
# =============================================================================
def _get_upload_temp_dir() -> Path:
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    default_dir = media_root / "upload_temp"
    temp_dir = Path(getattr(settings, "UPLOAD_TEMP_DIR", default_dir))
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _sanitize_filename(name: str, fallback: str = "upload.xlsx") -> str:
    raw = (name or "").strip() or fallback
    return SAFE_FILENAME_PATTERN.sub("_", raw)


def _save_uploaded_file_to_disk(uploaded_file, *, task_id: str) -> Path:
    temp_dir = _get_upload_temp_dir()
    safe_name = _sanitize_filename(getattr(uploaded_file, "name", "") or "upload.xlsx")
    save_path = temp_dir / f"accounts_upload_{task_id}_{safe_name}"

    with open(save_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    return save_path


def _file_response_or_404(abs_path: str | Path, *, download_name: Optional[str] = None) -> FileResponse:
    p = Path(abs_path)
    if not p.exists() or not p.is_file():
        raise Http404("파일을 찾을 수 없습니다.")
    fh = open(p, "rb")
    return FileResponse(fh, as_attachment=True, filename=(download_name or p.name))


# =============================================================================
# Excel export
# =============================================================================
def _build_users_export_workbook(users: Iterable[CustomUser]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Users"

    headers = [
        "ID",
        "Name",
        "Branch",
        "Channel",
        "Division",
        "Part",
        "Grade",
        "Status",
        "입사일",
        "퇴사일",
        "Is Staff",
        "Is Active",
    ]
    ws.append(headers)

    for u in users:
        ws.append(
            [
                u.id,
                u.name,
                u.branch,
                u.channel,
                u.division,
                u.part,
                GRADE_DISPLAY.get(u.grade, u.grade),
                u.status,
                u.enter.strftime("%Y-%m-%d") if u.enter else "",
                u.quit.strftime("%Y-%m-%d") if u.quit else "",
                bool(u.is_staff),
                bool(u.is_active),
            ]
        )

    return wb


def export_users_as_excel(users: Iterable[CustomUser], filename: str) -> HttpResponse:
    wb = _build_users_export_workbook(users)
    response = HttpResponse(content_type=EXCEL_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


def export_selected_users_to_excel(modeladmin, request, queryset):
    return export_users_as_excel(queryset, EXPORT_SELECTED_FILENAME)


def export_all_users_excel_view(request: HttpRequest) -> HttpResponse:
    return export_users_as_excel(CustomUser.objects.all(), EXPORT_ALL_FILENAME)


# =============================================================================
# Admin extra views (Excel upload)
# =============================================================================
def upload_users_from_excel_view(request: HttpRequest) -> HttpResponse:
    template_name = "admin/accounts/customuser/upload_excel.html"
    incoming_task_id = (request.GET.get("task_id") or request.POST.get("task_id") or "").strip()

    if request.method != "POST":
        return render(request, template_name, {"form": ExcelUploadForm(), "task_id": incoming_task_id})

    form = ExcelUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            template_name,
            {"form": form, "task_id": incoming_task_id, "error": "폼이 유효하지 않습니다."},
        )

    excel_file = request.FILES.get("file")
    if not excel_file:
        return render(
            request,
            template_name,
            {"form": form, "task_id": incoming_task_id, "error": "파일이 첨부되지 않았습니다."},
        )

    task_id = uuid.uuid4().hex

    try:
        save_path = _save_uploaded_file_to_disk(excel_file, task_id=task_id)
    except Exception as e:
        return render(
            request,
            template_name,
            {"form": ExcelUploadForm(), "task_id": incoming_task_id, "error": f"파일 저장 실패: {e}"},
        )

    _init_upload_cache(task_id)

    # tasks.py에서도 동일 constants 사용 (cache_key/prefix 통일)
    process_users_excel_task.delay(task_id, str(save_path), DEFAULT_BATCH_SIZE)

    return render(
        request,
        template_name,
        {"form": ExcelUploadForm(), "task_id": task_id, "message": "업로드 작업을 시작했습니다. 진행률을 확인하세요."},
    )


def upload_users_result_view(request: HttpRequest, task_id: str) -> FileResponse:
    result_path = cache.get(cache_key(CACHE_RESULT_PATH_PREFIX, task_id))
    if not result_path:
        raise Http404("결과 파일을 찾을 수 없습니다.")
    return _file_response_or_404(result_path)


def upload_excel_template_view(request: HttpRequest) -> FileResponse:
    abs_path = finders.find(TEMPLATE_REL_PATH)
    if not abs_path:
        raise Http404("업로드 양식 파일을 찾을 수 없습니다.")

    p = Path(abs_path)
    if not p.exists():
        raise Http404("업로드 양식 파일을 찾을 수 없습니다.")

    fh = open(p, "rb")
    return FileResponse(
        fh,
        content_type=EXCEL_CONTENT_TYPE,
        as_attachment=True,
        filename=TEMPLATE_DOWNLOAD_NAME,
    )


# =============================================================================
# Admin forms (✅ username 제거: USERNAME_FIELD='id' 대응)
# =============================================================================
class CustomUserCreationAdminForm(UserCreationForm):
    """
    CustomUser는 USERNAME_FIELD='id' 입니다.
    기본 UserAdmin add_view는 username을 기대할 수 있으므로,
    admin에서 사용할 creation form을 명시하여 FieldError를 방지합니다.
    """

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            "id",
            "name",
            "channel",
            "division",
            "part",
            "branch",
            "grade",
            "status",
            "enter",
            "quit",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


class CustomUserChangeAdminForm(UserChangeForm):
    """변경 폼도 명시(fields)해서 커스텀 유저 스키마와 정확히 맞춥니다."""

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = (
            "id",
            "name",
            "regist",
            "birth",
            "channel",
            "division",
            "part",
            "branch",
            "grade",
            "status",
            "enter",
            "quit",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
            "password",
        )


# =============================================================================
# Admin registration
# =============================================================================
@admin.register(CustomUser)
@admin.register(CustomUser, site=custom_admin_site)
class CustomUserAdmin(UserAdmin):
    model = CustomUser

    actions = [export_selected_users_to_excel]
    change_list_template = "admin/accounts/customuser/change_list.html"

    # ✅ add_view / change_view에서 username을 요구하지 않도록 폼 지정
    add_form = CustomUserCreationAdminForm
    form = CustomUserChangeAdminForm

    actions = [export_selected_users_to_excel, "clear_must_change_password", "reset_password_and_unlock_accounts"]

    list_display = (
        "id",
        "name",
        "channel",
        "division",
        "part",
        "branch",
        "grade",
        "status",
        "is_locked",
        "login_fail_count",
        "locked_at",
        "last_login_fail_at",
        "enter",
        "quit",
        "is_staff",
        "is_active",
    )
    search_fields = ("id", "name", "channel", "division", "part", "branch", "grade", "status")
    ordering = ("id", "name", "channel", "division", "part", "branch")

    list_filter = ("grade", "status", "channel", "division", "part", "branch", "must_change_password", "is_locked")

    @admin.action(description=ADMIN_ACTION_RESET_PASSWORD_AND_UNLOCK)
    def reset_password_and_unlock_accounts(self, request, queryset):
        """
        Lockout 운영 복구 동선(권장):
        - 표준 초기 비밀번호(incar+사원번호)로 초기화
        - 잠금 해제
        - 실패 횟수 0으로 초기화
        - must_change_password=True로 강제 비밀번호 변경 유도
        """
        req_grade = (getattr(request.user, "grade", "") or "").strip()
        if not (request.user.is_superuser or req_grade in {"superuser", "head"}):
            self.message_user(request, "이 작업은 superuser 또는 main_admin만 수행할 수 있습니다.", level=messages.ERROR)
            return

        now = timezone.now()
        changed = 0

        for selected in queryset:
            with transaction.atomic():
                target = CustomUser.objects.select_for_update().get(pk=selected.pk)
                was_locked = bool(getattr(target, "is_locked", False))

                target.set_password(f"incar{target.id}")
                target.is_locked = False
                target.login_fail_count = 0
                target.lock_cleared_at = now
                target.lock_cleared_by = request.user
                target.password_reset_by_admin_at = now
                target.must_change_password = True
                target.must_change_password_set_at = now
                target.must_change_password_cleared_at = None
                target.save(
                    update_fields=[
                        "password",
                        "is_locked",
                        "login_fail_count",
                        "lock_cleared_at",
                        "lock_cleared_by",
                        "password_reset_by_admin_at",
                        "must_change_password",
                        "must_change_password_set_at",
                        "must_change_password_cleared_at",
                    ]
                )

                try:
                    log_action(
                        request,
                        ACTION.ACCOUNTS_PASSWORD_RESET_UNLOCK,
                        obj=target,
                        meta={"user_id": target.id, "was_locked": was_locked},
                        success=True,
                    )
                except Exception:
                    # audit 실패가 관리자 복구 자체를 막으면 안 됨
                    pass

                changed += 1

        self.message_user(request, f"{changed}명의 사용자 비밀번호를 초기화하고 잠금을 해제했습니다.", level=messages.SUCCESS)

    @admin.action(description="(Phase3) 선택 사용자 must_change_password 해제")
    def clear_must_change_password(self, request, queryset):
        """
        운영 비상 동선:
        - 강제 정책 적용 실패/문의 폭주 시, 특정 사용자만 빠르게 해제할 수 있어야 합니다.
        - (주의) '비번이 안전해졌다'는 의미는 아니므로, 현장 SOP에 따라 사용하세요.
        """
        queryset.update(must_change_password=False)
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        req_grade = (getattr(request.user, "grade", "") or "").strip()
        if not (request.user.is_superuser or req_grade in {"superuser", "head"}):
            actions.pop("reset_password_and_unlock_accounts", None)
        return actions

    def get_readonly_fields(self, request, obj=None):
        # ✅ 수정 화면에서만 id를 잠금
        if obj:  # change_view
            return ("id", "must_change_password_set_at", "must_change_password_cleared_at",
                    "locked_at", "last_login_fail_at", "lock_cleared_at", "lock_cleared_by",
                    "password_reset_by_admin_at")
        return ()  # add_view에서는 입력 가능

    fieldsets = (
        (None, {"fields": ("id", "password")}),
        (
            "Personal Info",
            {"fields": ("name", "regist", "birth", "channel", "division", "part", "branch", "grade", "status", "enter", "quit")},
        ),
        (
            "Phase 4 (Account Lockout)",
            {
                "fields": (
                    "login_fail_count",
                    "is_locked",
                    "locked_at",
                    "last_login_fail_at",
                    "lock_reason",
                    "lock_cleared_at",
                    "lock_cleared_by",
                    "password_reset_by_admin_at",
                )
            },
        ),
        ("Phase 3 (Force Password Change)", {"fields": ("must_change_password", "must_change_password_set_at", "must_change_password_cleared_at")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )

    # ✅ 사용자 추가 화면에서 UserAdmin 기본 add_fieldsets(username 포함) 대체
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "id",
                    "name",
                    "regist",
                    "birth",
                    "channel",
                    "division",
                    "part",
                    "branch",
                    "grade",
                    "status",
                    "enter",
                    "quit",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # 운영 정책: 퇴사일이 있으면 상태 "퇴사"로 동기화
        if getattr(obj, "quit", None):
            obj.status = "퇴사"
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("export-all/", self.admin_site.admin_view(export_all_users_excel_view), name="export_all_users_excel"),
            path("upload-excel/", self.admin_site.admin_view(upload_users_from_excel_view), name="upload_users_excel"),
            path("upload-template/", self.admin_site.admin_view(upload_excel_template_view), name="upload_excel_template"),
            path(
                "upload-result/<str:task_id>/",
                self.admin_site.admin_view(upload_users_result_view),
                name="upload_users_result",
            ),
        ]
        return custom_urls + urls
