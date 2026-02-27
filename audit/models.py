# django_ma/audit/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class RequestLog(models.Model):
    """
    모든 요청/응답 단위 로그.
    body는 저장하지 않는다(민감정보 위험).
    """
    ts = models.DateTimeField(default=timezone.now, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="request_logs",
        db_index=True,
    )

    is_authenticated = models.BooleanField(default=False, db_index=True)
    method = models.CharField(max_length=10, db_index=True)
    path = models.CharField(max_length=512, db_index=True)
    querystring = models.CharField(max_length=1024, blank=True, default="")

    status_code = models.IntegerField(db_index=True)
    duration_ms = models.IntegerField(default=0, db_index=True)

    ip = models.CharField(max_length=64, blank=True, default="", db_index=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    referer = models.CharField(max_length=512, blank=True, default="")

    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        db_table = "audit_request_log"
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["-ts"]),
            models.Index(fields=["user", "-ts"]),
            models.Index(fields=["status_code", "-ts"]),
            models.Index(fields=["path", "-ts"]),
        ]

    def __str__(self):
        return f"[{self.ts:%Y-%m-%d %H:%M:%S}] {self.method} {self.path} {self.status_code}"


class AuditLog(models.Model):
    """
    의미 있는 액션(등록/수정/삭제/다운로드/권한변경 등) 이벤트 로그.
    """
    ts = models.DateTimeField(default=timezone.now, db_index=True)

    action = models.CharField(max_length=100, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )
    ip = models.CharField(max_length=64, blank=True, default="", db_index=True)

    success = models.BooleanField(default=True, db_index=True)
    reason = models.CharField(max_length=300, blank=True, default="")

    # 대상 객체 식별(필요할 때만)
    object_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    object_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # 부가정보 (민감정보 금지, 반드시 최소화/마스킹)
    meta = models.JSONField(blank=True, default=dict)

    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        db_table = "audit_audit_log"
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["action", "-ts"]),
            models.Index(fields=["user", "-ts"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["success", "-ts"]),
        ]

    def __str__(self):
        return f"[{self.ts:%Y-%m-%d %H:%M:%S}] {self.action} ({'OK' if self.success else 'FAIL'})"