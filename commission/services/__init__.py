# django_ma/commission/services/__init__.py
from __future__ import annotations

"""
commission.services public package.

역할:
- collect, rate_example, collect_notice 등 commission 도메인 서비스 모듈의 루트 패키지다.
- 현재는 명시적 re-export를 제공하지 않는다.

규칙:
- View는 가능한 한 services 모듈을 통해 도메인 로직을 호출한다.
- 단, 기존 public import surface를 깨지 않기 위해 무리한 re-export는 추가하지 않는다.
"""