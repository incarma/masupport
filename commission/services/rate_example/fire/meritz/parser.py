# commission/services/rate_example/fire/meritz/parser.py
from __future__ import annotations

"""
메리츠화재 PDF 수정률 정규화.

역할:
- 메리츠화재 장기보험 수정률 PDF를 RateExampleConversionRow 기준으로 정규화한다.
- 담보명에 "기본계약" 또는 "반려견"이 포함된 행만 적재한다.
- 손해보험 수정률 단일 컬럼 정책에 따라 수정률은 year1에 저장한다.

정규화 정책:
- 보험사: "메리츠" 고정
- 상품명: PDF 상품명 컬럼
- 구분: PDF 구분 컬럼. 빈 값이면 "사용안함"
- 납기: 납입기간 + "(" + 보험기간 + ")" 조합
  - 납입기간: "년" 뒤에 "납" 추가
  - 보험기간: "년" 뒤에 "만기" 추가
- 상품군:
  - 상품명에 연금 포함 → 연금
  - 상품명에 저축 포함 → 저축
  - 상품명에 태아 포함 → 보장(태아)
  - 상품명에 실손 포함 + 구분 최초 → 단독실손(초회)
  - 상품명에 실손 포함 + 구분 갱신 → 단독실손(갱신)
  - 그 외 → 보장
"""

import logging
import re
from decimal import Decimal
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common.pdf import (
    clean_pdf_text,
    decimal_from_pdf_percent,
)

logger = logging.getLogger(__name__)

INSURER = "메리츠"
TARGET_COVERAGE_KEYWORDS = ("기본계약", "반려견")


def _clean_text(value) -> str:
    """
    PDF 셀 텍스트 공통 정리.

    주요기능:
    - None 방어
    - 줄바꿈/중복 공백 제거
    - 한 셀의 여러 줄 텍스트를 한 줄로 연결
    """
    return clean_pdf_text(str(value or "").replace("\n", " "))


def _append_suffix_after_year(value: str, suffix: str) -> str:
    """
    '년' 뒤에 지정 suffix를 추가한다.

    예:
    - 10년      → 10년납 / 10년만기
    - 20~30년  → 20~30년납 / 20~30년만기
    - 3년/10년 → 3년납/10년납
    - 이미 년납/년만기 형태면 중복 추가하지 않는다.
    """
    text = _clean_text(value)
    if not text:
        return ""

    if suffix == "납":
        return re.sub(r"년(?!\s*납)", "년납", text)

    if suffix == "만기":
        return re.sub(r"년(?!\s*만기)", "년만기", text)

    return text


def _normalize_pay_period(pay_period: str, insurance_period: str) -> str:
    """
    납기 조립.

    주요기능:
    - 납입기간: 년 → 년납
    - 보험기간: 년 → 년만기
    - 보험기간이 없으면 납입기간만 저장
    """
    pay = _append_suffix_after_year(pay_period, "납")
    period = _append_suffix_after_year(insurance_period, "만기")

    if pay and period:
        return f"{pay}({period})"
    return pay


def _to_decimal_percent(value) -> Decimal | None:
    """
    수정률 값을 Decimal로 변환한다.

    PDF 원문 예:
    - 150%
    - 1.5%
    - 240
    """
    text = _clean_text(value)
    if not text:
        return None

    return decimal_from_pdf_percent(text)


def _normalize_product_group(product_name: str, plan_type: str) -> str:
    """
    상품명/구분 기준 상품군 정규화.
    """
    product = _clean_text(product_name)
    plan = _clean_text(plan_type)

    if "연금" in product:
        return "연금"
    if "저축" in product:
        return "저축"
    if "태아" in product:
        return "보장(태아)"
    if "실손" in product:
        if plan == "최초":
            return "단독실손(초회)"
        if plan == "갱신":
            return "단독실손(갱신)"
    return "보장"


def _is_target_coverage(coverage_name: str) -> bool:
    """
    정규화 대상 담보명 판별.

    담보명에 기본계약 또는 반려견 포함 시만 정규화한다.
    """
    text = _clean_text(coverage_name)
    return any(keyword in text for keyword in TARGET_COVERAGE_KEYWORDS)


def _iter_pdf_rows(path: str) -> Iterable[list[str]]:
    """
    PDF 테이블 row 추출.

    주요기능:
    - pdfplumber 기반 table 추출
    - 셀 병합/누락으로 빈 셀이 발생해도 직전 값 carry-forward 가능하도록 원문 row 반환
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("메리츠 PDF 정규화에는 pdfplumber가 필요합니다.") from exc

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for row in table or []:
                    cleaned = [_clean_text(cell) for cell in (row or [])]
                    if any(cleaned):
                        yield cleaned


def _find_header_indexes(row: list[str]) -> dict[str, int]:
    """
    헤더 row에서 필요한 컬럼 인덱스를 탐지한다.

    PDF 추출 결과에 따라 헤더명이 일부 붙거나 줄바꿈될 수 있어 contains 방식으로 탐지한다.
    """
    joined_cells = [_clean_text(cell) for cell in row]

    def find(*keywords: str) -> int:
        for idx, cell in enumerate(joined_cells):
            if all(k in cell for k in keywords):
                return idx
        return -1

    return {
        "product_name": find("상품명"),
        "coverage_name": find("담보명"),
        "pay_period": find("납입기간"),
        "insurance_period": find("보험기간"),
        "mod_rate": find("초년도", "수정"),
        "plan_type": find("구분"),
    }


def _get(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return _clean_text(row[idx])


def build_fire_meritz_pdf_conversion_rows(example: RateExample) -> list[RateExampleConversionRow]:
    """
    메리츠화재 PDF 수정률 row 생성.

    반환:
    - DB bulk_create 대상 RateExampleConversionRow 리스트
    """
    if not example.file:
        return []

    path = example.file.path
    rows: list[RateExampleConversionRow] = []

    header: dict[str, int] | None = None

    # 병합 셀 분리 후 동일 텍스트 삽입 효과를 위해 주요 컬럼은 직전 값 carry-forward.
    last_product_name = ""
    last_coverage_name = ""
    last_plan_type = ""

    for raw_row in _iter_pdf_rows(path):
        if not header:
            candidate = _find_header_indexes(raw_row)
            if candidate["product_name"] >= 0 and candidate["coverage_name"] >= 0:
                header = candidate
            continue

        product_name = _get(raw_row, header["product_name"]) or last_product_name
        coverage_name = _get(raw_row, header["coverage_name"]) or last_coverage_name
        plan_type = _get(raw_row, header["plan_type"]) or last_plan_type or "사용안함"
        pay_period_raw = _get(raw_row, header["pay_period"])
        insurance_period_raw = _get(raw_row, header["insurance_period"])
        mod_rate = _to_decimal_percent(_get(raw_row, header["mod_rate"]))

        if product_name:
            last_product_name = product_name
        if coverage_name:
            last_coverage_name = coverage_name
        if plan_type and plan_type != "사용안함":
            last_plan_type = plan_type

        if not product_name or not _is_target_coverage(coverage_name):
            continue
        if mod_rate is None:
            continue

        plan_type = plan_type or "사용안함"
        pay_period = _normalize_pay_period(pay_period_raw, insurance_period_raw)
        if not pay_period:
            continue

        rows.append(
            RateExampleConversionRow(
                source_file=example,
                source_sheet="PDF",
                source_row_no=len(rows) + 1,
                insurer_type=RateExample.TYPE_FIRE,
                category=RateExample.CAT_CONV,
                insurer=INSURER,
                coverage_type=_normalize_product_group(product_name, plan_type),
                strategy_flag="",
                product_name=product_name,
                plan_type=plan_type,
                pay_period=pay_period,
                year1=mod_rate,
                year2=None,
                year3=None,
                year4=None,
            )
        )

    logger.info(
        "fire meritz pdf normalizer: created %s rows. pk=%s file=%s",
        len(rows),
        example.pk,
        example.original_name,
    )
    return rows
