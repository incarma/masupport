# commission/services/rate_example_normalizer.py
from __future__ import annotations

"""
RateExample 정규화 서비스.

역할:
- 업로드된 예시표 원본 파일을 보험사별 규칙에 따라 정규화 테이블로 적재한다.
- 현재 지원 대상: 생명보험 / 환산률·수정률 / ABL, DB
- 원본 파일 저장/검증은 RateExampleService가 담당하고, 이 파일은 정규화만 담당한다.

보안/운영 원칙:
- 파일 URL 직접 접근 금지. FieldFile.path만 서버 내부에서 사용.
- 파싱 실패 시 예외를 삼키지 않고 호출부에서 rollback 가능하도록 raise.
- 동일 보험사·구분 정규화 데이터는 최신 업로드 기준으로 교체한다.
"""

import logging

from openpyxl import load_workbook

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example_normalizers.life_abl import (
    build_life_abl_conversion_rows,
)
from commission.services.rate_example_normalizers.life_db import (
    build_life_db_conversion_rows,
)
from commission.services.rate_example_normalizers.life_im import (
    build_life_im_conversion_rows,
)
from commission.services.rate_example_normalizers.life_kb import (
    build_life_kb_general_conversion_rows,
)

logger = logging.getLogger(__name__)


def normalize_rate_example(
    example: RateExample,
    *,
    product_kind: str = "",
    normalize_mode: str = "replace",
) -> int:
    """
    RateExample 업로드 파일을 정규화한다.

    현재 지원:
    - 생명보험 / 환산률·수정률 / ABL / xlsx
    - 생명보험 / 환산률·수정률 / DB / xlsx
    - 생명보험 / 환산률·수정률 / IM / xlsx
    - 생명보험 / 환산률·수정률 / KB / 일반상품 / xlsx

    반환:
    - 생성된 RateExampleConversionRow 수
    """
    normalize_mode = (normalize_mode or "replace").strip()
    if normalize_mode not in {"replace", "append"}:
        raise ValueError(f"Invalid normalize_mode: {normalize_mode}")

    if not (
        example.insurer_type == RateExample.TYPE_LIFE
        and example.category == RateExample.CAT_CONV
        and example.insurer in {"ABL", "DB", "IM", "KB"}
    ):
        return 0

    if not example.file:
        return 0

    # 정규화 대상은 xlsx 기준이다. xls/pdf는 원본 보관만 수행한다.
    if not str(example.original_name or "").lower().endswith(".xlsx"):
        return 0

    wb = load_workbook(example.file.path, data_only=True, read_only=True)

    normalized_rows: list[RateExampleConversionRow] = []

    # ── ABL 생명 환산률/수정률 정규화 ─────────────────────────────
    # 보험사별 parser는 rate_example_normalizers/life_*.py에 둔다.
    # 이 파일은 workbook 로드, 보험사 분기, 기존 master 교체만 담당한다.
    if example.insurer == "ABL":
        normalized_rows.extend(build_life_abl_conversion_rows(example, wb))

    # ── DB 생명 환산률/수정률 정규화 ──────────────────────────────
    # DB 규칙:
    # - 특약/방카교차 시트 제외
    # - 각 시트 첫 번째 테이블만 정규화
    # - 상품명은 A1, 보종은 상품명 기반 판정
    elif example.insurer == "DB":
        normalized_rows.extend(build_life_db_conversion_rows(example, wb))

    # ── IM 생명 환산률/수정률 정규화 ──────────────────────────────
    # IM 규칙:
    # - 첫 번째 시트 "(총괄)환산성적표"만 사용
    # - E열 구분 == "주계약"인 행만 정규화
    # - L열 기본형 값을 1~4차년에 동일 반영
    elif example.insurer == "IM":
        normalized_rows.extend(build_life_im_conversion_rows(example, wb))

    # ── KB 생명 환산률/수정률 정규화 ──────────────────────────────
    # KB 일반상품 규칙:
    # - "(주계약)"으로 표시된 테이블만 사용
    # - "(특약)" 테이블은 제외
    # - B/C/D/E/F/G/H/I/K 열 매핑
    elif example.insurer == "KB":
        if product_kind != "general":
            return 0
        normalized_rows.extend(build_life_kb_general_conversion_rows(example, wb))

    # 동일 보험사/구분의 정규화 master 처리.
    # - replace: 기존 방식. 기존 row 삭제 후 새 데이터 적재.
    # - append: 기존 row 유지 후 새 데이터만 추가.
    if normalize_mode == "replace":
        RateExampleConversionRow.objects.filter(
            insurer_type=example.insurer_type,
            category=example.category,
            insurer=example.insurer,
        ).delete()

    if normalized_rows:
        RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

    return len(normalized_rows)