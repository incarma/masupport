# django_ma/commission/upload_handlers/__init__.py
from __future__ import annotations

"""
commission.upload_handlers public API

SSOT(단일 진실) 정책:
- DepositUploadLog 갱신 로직은 deposit._update_upload_log 를 SSOT로 사용한다.
- 외부(views 등)에서는 commission.upload_handlers.* 로 import 하는 것을 권장한다.
  (내부 구현 파일 위치 변경 시에도 import surface 유지 가능)
- registry.py의 UploadSpec이 upload_type → handler 라우팅의 SSOT다.
- underscore alias는 기존 import 호환을 위한 surface이므로 P2 단계에서는 제거하지 않는다.
"""

# ---------------------------------------------------------------------
# SSOT: DepositUploadLog 갱신
# ---------------------------------------------------------------------
from .deposit import _update_upload_log  # SSOT

# ---------------------------------------------------------------------
# Backward-compatible re-exports
# - 기존 코드 호환을 위해 underscore alias를 계속 제공한다.
# ---------------------------------------------------------------------
from .approval import _handle_upload_commission_approval  # noqa: F401
from .efficiency import _handle_upload_efficiency_pay_excess  # noqa: F401

__all__ = [
    "_update_upload_log",
    "_handle_upload_commission_approval",
    "_handle_upload_efficiency_pay_excess",
]