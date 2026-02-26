from __future__ import annotations

"""
Legacy shim module.

기존 코드 호환을 위해 upload_utils.py는 유지한다.
실제 구현은 하위 모듈로 분리되었고, 여기서는 동일 심볼을 re-export 한다.
"""

from .__init__ import *  # noqa: F403
from .__init__ import __all__  # noqa: F401