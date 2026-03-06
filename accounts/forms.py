# django_ma/accounts/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError

from .constants import ACCOUNT_LOCKED_MESSAGE


# =============================================================================
# Excel Upload Form
# =============================================================================

class ExcelUploadForm(forms.Form):
    """
    Excel 업로드 공용 폼 (.xlsx)
    """
    file = forms.FileField(label="Select an Excel file (.xlsx)")


# =============================================================================
# Login Form (활성 사용자만 로그인 허용)
# =============================================================================

class ActiveOnlyAuthenticationForm(AuthenticationForm):
    """
    비활성화(is_active=False) 계정 로그인 차단
    """

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)

        # ✅ 방어적 가드: 잠긴 계정은 어떤 로그인 뷰를 타더라도 인증 완료 금지
        if getattr(user, "is_locked", False):
            raise ValidationError(ACCOUNT_LOCKED_MESSAGE, code="locked")

        if not getattr(user, "is_active", True):
            raise ValidationError("비활성화된 계정입니다.", code="inactive")


# =============================================================================
# Password Change Form (정책 강화: 동일 비밀번호 변경 금지)
# =============================================================================
class StrictPasswordChangeForm(PasswordChangeForm):
    """
    ✅ 동일 비밀번호로 변경 시도를 차단하는 PasswordChangeForm 확장
    - 서버 검증(필수): JS 우회 여부와 무관하게 동일 비밀번호 변경은 실패해야 함
    - 기존 Django validators(길이/복잡도/유사성 등) 흐름은 그대로 유지
    """
    SAME_PASSWORD_ERROR = "현재 비밀번호와 동일한 비밀번호로 변경할 수 없습니다."

    def clean(self):
        cleaned = super().clean()
        new_pw = cleaned.get("new_password1")
        # old_password는 이미 기본 검증(현재 비밀번호 일치 여부)을 거친 뒤이며,
        # 동일 비밀번호 금지 정책만 추가로 적용합니다.
        if new_pw and getattr(self, "user", None) and self.user.check_password(new_pw):
            self.add_error("new_password1", ValidationError(self.SAME_PASSWORD_ERROR, code="password_no_change"))
        return cleaned