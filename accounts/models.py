# django_ma/accounts/models.py

from __future__ import annotations

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone


# =============================================================================
# 1) Custom User Manager
# =============================================================================
class CustomUserManager(BaseUserManager):
    """
    CustomUser 생성 로직을 한 곳에서 일관되게 관리합니다.

    - create_user: 일반 사용자 생성
    - create_superuser: 관리자 생성
    """

    def create_user(self, id: str, password: str | None = None, **extra_fields):
        """
        일반 사용자 생성.
        - id(사원번호)는 필수
        - name은 실무에서 필수값이므로 누락 시 ValidationError
        """
        if not id:
            raise ValueError("ID(사원번호)는 반드시 입력되어야 합니다.")

        # name은 REQUIRED_FIELDS로도 관리되지만, create_user 직접 호출 시 누락될 수 있어 안전장치 추가
        name = (extra_fields.get("name") or "").strip()
        if not name:
            raise ValidationError("name(성명)은 반드시 입력되어야 합니다.")

        user = self.model(id=id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, id: str, password: str | None = None, **extra_fields):
        """
        Django superuser 생성.
        """
        extra_fields.setdefault("grade", "superuser")
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_active", True)

        return self.create_user(id=id, password=password, **extra_fields)


# =============================================================================
# 2) Custom User Model
#    조직 위계: channel(부문) > division(총괄) > part(부서) > branch(지점)
# =============================================================================
class CustomUser(AbstractBaseUser, PermissionsMixin):
    # -------------------------------------------------------------------------
    # 권한 등급
    # -------------------------------------------------------------------------
    GRADE_CHOICES = [
        ("superuser", "Superuser"),
        ("head", "Head"),
        ("leader", "Leader"),
        ("basic", "Basic"),
        ("resign", "Resign"),
        ("inactive", "Inactive"),
    ]

    # -------------------------------------------------------------------------
    # 기본 식별/개인정보
    # -------------------------------------------------------------------------
    id = models.CharField(max_length=30, unique=True, primary_key=True)  # 사원번호 (USERNAME_FIELD)
    name = models.CharField(max_length=100)

    regist = models.CharField(max_length=50, blank=True, null=True)
    birth = models.DateField("생년월일", blank=True, null=True)
    enter = models.DateField("입사일자", blank=True, null=True)
    quit = models.DateField("퇴사일자", blank=True, null=True)

    # -------------------------------------------------------------------------
    # 조직 정보 (위계)
    # -------------------------------------------------------------------------
    channel = models.CharField(max_length=10, blank=True, default="", verbose_name="부문")
    division = models.CharField(max_length=30, blank=True, default="", verbose_name="총괄")
    part = models.CharField(max_length=10, blank=True, default="", verbose_name="부서")
    branch = models.CharField(max_length=100, blank=True, default="", verbose_name="지점")

    # -------------------------------------------------------------------------
    # 권한/상태
    # -------------------------------------------------------------------------
    grade = models.CharField(max_length=20, choices=GRADE_CHOICES, default="basic")
    status = models.CharField(max_length=20, default="재직")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # ⚠️ PermissionsMixin에도 is_superuser가 존재하는 것이 일반적입니다.
    # 이 필드가 이미 DB/마이그레이션에 존재하는 프로젝트라면 호환을 위해 유지합니다.
    # (새 프로젝트라면 PermissionsMixin의 is_superuser를 그대로 쓰는 것이 정석입니다.)
    is_superuser = models.BooleanField(default=False)

    # -------------------------------------------------------------------------
    # Phase 4 (Account Lockout)
    #
    # ✅ login_fail_count:
    # - 연속 로그인 실패 횟수
    # - 로그인 성공 시 0으로 초기화
    #
    # ✅ is_locked:
    # - True이면 관리자 비밀번호 초기화 전까지 로그인 불가
    # -------------------------------------------------------------------------
    login_fail_count = models.PositiveIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(blank=True, null=True)
    last_login_fail_at = models.DateTimeField(blank=True, null=True)
    lock_reason = models.CharField(max_length=50, blank=True, default="")
    lock_cleared_at = models.DateTimeField(blank=True, null=True)
    lock_cleared_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    password_reset_by_admin_at = models.DateTimeField(blank=True, null=True)

    # -------------------------------------------------------------------------
    # Phase 3 (Force Password Change)
    #
    # ✅ must_change_password:
    # - 로그인 성공 훅에서 "기본 비번(id 또는 incar+id)"으로 로그인한 경우 True로 수렴
    # - 비밀번호 변경 완료 시 False로 해제
    #
    # ⚠️ 미들웨어는 '기본 비번 여부'를 판별하지 않습니다.
    #    (원문 비밀번호를 알 수 없으므로) → 오직 이 플래그만 봅니다.
    # -------------------------------------------------------------------------
    must_change_password = models.BooleanField(default=False)
    must_change_password_set_at = models.DateTimeField(blank=True, null=True)
    must_change_password_cleared_at = models.DateTimeField(blank=True, null=True)

    # -------------------------------------------------------------------------
    # Django auth config
    # -------------------------------------------------------------------------
    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["name"]
    objects = CustomUserManager()

    # -------------------------------------------------------------------------
    # Model hooks / representation
    # -------------------------------------------------------------------------
    def save(self, *args, **kwargs):
        """
        정책:
        - grade == inactive 인 경우 is_active는 반드시 False
        - inactive가 아닌 경우 is_active를 자동 True로 돌리지는 않음(수동 제어 여지 유지)
        """
        if self.grade == "inactive":
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.id} ({self.name})"

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
