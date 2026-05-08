# commission/services/rate_example_normalizer.py.py
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

logger = logging.getLogger(__name__)


def _coverage_type_for_abl_protection(product_name: str) -> str:
    """상품명에 '종신' 포함 여부로 보종 분기."""
    return "종신/CI" if "종신" in product_name else "기타(보장성)"


def _normalize_abl_protection(example: RateExample, ws) -> Iterable[RateExampleConversionRow]:
    """
    ABL [주계약(보장성)_12개월 선지급] 시트 정규화.

    사용자 규칙:
    - 보험사: ABL
    - 보종: 상품명에 '종신' 포함 시 종신/CI, 아니면 기타(보장성)
    - 상품명: A열
    - 구분: B열(형태)
    - 납기: E열
    - 1차년: F열
    - 2차년: G열
    - 3차년: H열
    - 4차년: I열
    """
    rows: list[RateExampleConversionRow] = []
    last_product = ""
    last_plan = ""

    for row_no in range(5, ws.max_row + 1):
        product = _clean_text(ws.cell(row_no, 1).value) or last_product
        plan = _clean_text(ws.cell(row_no, 2).value) or last_plan
        pay_period = _clean_text(ws.cell(row_no, 5).value)

        y1_raw = ws.cell(row_no, 6).value
        y2_raw = ws.cell(row_no, 7).value
        y3_raw = ws.cell(row_no, 8).value
        y4_raw = ws.cell(row_no, 9).value

        if _clean_text(ws.cell(row_no, 1).value):
            last_product = product
        if _clean_text(ws.cell(row_no, 2).value):
            last_plan = plan

        if not product and not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw, y4_raw):
            continue
        if not pay_period and not _has_any_rate(y1_raw, y2_raw, y3_raw, y4_raw):
            continue

        rows.append(RateExampleConversionRow(
            source_file=example,
            source_sheet=SHEET_ABL_PROTECTION,
            source_row_no=row_no,
            insurer_type=example.insurer_type,
            category=example.category,
            insurer="ABL",
            coverage_type=_coverage_type_for_abl_protection(product),
            strategy_flag="",
            product_name=product,
            plan_type=plan,
            pay_period=pay_period,
            year1=_to_decimal(y1_raw),
            year2=_to_decimal(y2_raw),
            year3=_to_decimal(y3_raw),
            year4=_to_decimal(y4_raw),
        ))

    return rows


def normalize_rate_example(example: RateExample) -> int:
    """
    RateExample 업로드 파일을 정규화한다.

    현재 지원:
    - 생명보험 / 환산률·수정률 / ABL / xlsx
    - 생명보험 / 환산률·수정률 / DB / xlsx
    - 생명보험 / 환산률·수정률 / IM / xlsx

    반환:
    - 생성된 RateExampleConversionRow 수
    """
    if not (
        example.insurer_type == RateExample.TYPE_LIFE
        and example.category == RateExample.CAT_CONV
        and example.insurer in {"ABL", "DB", "IM"}
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

    # 동일 보험사/구분의 정규화 master는 최신 업로드 기준으로 교체한다.
    RateExampleConversionRow.objects.filter(
        insurer_type=example.insurer_type,
        category=example.category,
        insurer=example.insurer,
    ).delete()

    if normalized_rows:
        RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

    return len(normalized_rows)