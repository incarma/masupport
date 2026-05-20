from __future__ import annotations

"""
Legacy shim module.

기존 코드 호환을 위해 upload_utils.py는 유지한다.
실제 구현은 하위 모듈로 분리되었고, 여기서는 동일 심볼을 re-export 한다.

주의:
- 신규 코드는 `from commission.upload_utils import ...` 경로를 사용한다.
- 이 파일은 과거 `commission.upload_utils.upload_utils` import 경로 보호용이다.
- 기능 변화 0 리팩토링 범위에서는 제거하지 않는다.
- __all__은 package root의 공개 surface와 항상 동일해야 한다.
"""

from .__init__ import *  # noqa: F403
from .__init__ import __all__  # noqa: F401