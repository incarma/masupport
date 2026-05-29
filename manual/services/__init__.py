# django_ma/manual/services/__init__.py

"""
manual.services 패키지

뷰에서 ORM 직접 호출을 제거하고 도메인별 서비스 모듈로 위임한다.
뷰는 서비스 함수만 호출한다 (board/services/worktasks.py 참조 패턴).

- manuals    : Manual 도메인 (CRUD + 목록 쿼리)
- sections   : ManualSection 도메인 (CRUD + 정렬 지원)
- blocks     : ManualBlock 도메인 (CRUD + 이동 + 정렬)
- attachments: ManualBlockAttachment 도메인 (업로드/삭제/다운로드)
"""

from . import manuals, sections, blocks, attachments

__all__ = ["manuals", "sections", "blocks", "attachments"]
