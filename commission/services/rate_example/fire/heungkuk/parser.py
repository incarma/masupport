# commission/services/rate_example/fire/heungkuk/parser.py
from __future__ import annotations

"""
흥국화재 수정률 PDF 정규화.

정규화 정책:
- insurer_type = fire
- category = conv
- insurer = 흥국
- 손해보험 수정률 단일 컬럼 구조에 따라 year1만 저장
- year2~year4는 None 저장
- PDF 텍스트 기반 parser
- 원본 수정률 raw 백분율 값을 그대로 저장
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common.pdf import (
    clean_pdf_text,
    decimal_from_pdf_percent,
    extract_pdf_text_with_fallback,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PDF Text Extract
# =============================================================================

def _extract_pdf_text(path: str) -> str:
    """
    pypdf 우선, PyPDF2 fallback.
    PDF 표 파싱은 line 구조가 불안정할 수 있으므로 전체 텍스트를 정규화해 사용한다.
    """
    return extract_pdf_text_with_fallback(path)


def _clean_text(value: object) -> str:
    return clean_pdf_text(str(value or "").replace("–", "-").replace("—", "-"))


def _compact(value: object) -> str:
    return clean_pdf_text(value)


def _normalize_plan_type(value: object) -> str:
    """
    구분(plan_type) 정규화.

    - 원본 표의 '수정률'은 실제 상품 구분이 아니라 헤더성 값이므로 '사용안함'으로 저장한다.
    - 공란도 조회/계산 UI 일관성을 위해 '사용안함'으로 저장한다.
    """
    text = _clean_text(value)
    if not text or "수정률" in text:
        return "사용안함"
    return text


def _to_decimal(value: object) -> Decimal | None:
    return decimal_from_pdf_percent(value)


# =============================================================================
# Row Builder
# =============================================================================

@dataclass(frozen=True)
class _RowSeed:
    product_name: str
    coverage_type: str
    plan_type: str
    pay_period: str
    rate: Decimal
    source_row_no: int = 0


def _coverage_from_product(product_name: str, plan_type: str = "") -> str:
    text = f"{product_name} {plan_type}"

    # 1순위: 단독실손 초회/갱신 규칙은 기존 정책 유지
    if "실손" in text or "의료" in text:
        return "단독실손(초회)"

    # 2순위: 상품명 기준 연금/저축 분류
    if "연금" in product_name:
        return "연금"
    if "저축" in product_name:
        return "저축"

    # 3순위: 구분 기준 태아 담보 분류
    if "태아 담보" in plan_type:
        return "보장(태아)"

    # 4순위: 그 외는 모두 보장
    return "보장"


def _make_row(example: RateExample, seed: _RowSeed) -> RateExampleConversionRow:
    return RateExampleConversionRow(
        source_file=example,
        source_sheet="PDF",
        source_row_no=seed.source_row_no,
        insurer_type=RateExample.TYPE_FIRE,
        category=RateExample.CAT_CONV,
        insurer="흥국",
        coverage_type=seed.coverage_type,
        strategy_flag="",
        product_name=seed.product_name,
        plan_type=seed.plan_type,
        pay_period=seed.pay_period,
        year1=seed.rate,
        year2=None,
        year3=None,
        year4=None,
    )


def _append(
    rows: list[_RowSeed],
    seen: set[tuple[str, str, str, str]],
    *,
    product_name: str,
    coverage_type: str | None = None,
    plan_type: str = "",
    pay_period: str,
    rate: object,
    source_row_no: int = 0,
) -> None:
    rate_dec = _to_decimal(rate)
    if rate_dec is None:
        return

    product_name = _clean_text(product_name)
    plan_type = _normalize_plan_type(plan_type)
    pay_period = _clean_text(pay_period)

    if not product_name or not pay_period:
        return

    coverage = coverage_type or _coverage_from_product(product_name, plan_type)

    key = (product_name, plan_type, pay_period, str(rate_dec))
    if key in seen:
        return

    seen.add(key)
    rows.append(
        _RowSeed(
            product_name=product_name,
            coverage_type=coverage,
            plan_type=plan_type,
            pay_period=pay_period,
            rate=rate_dec,
            source_row_no=source_row_no,
        )
    )


def _append_matrix(
    rows: list[_RowSeed],
    seen: set[tuple[str, str, str, str]],
    *,
    product_name: str,
    headers: Iterable[str],
    values: Iterable[object],
    plan_type: str,
    coverage_type: str | None = None,
    source_row_no: int = 0,
) -> None:
    for pay_period, rate in zip(headers, values, strict=False):
        _append(
            rows,
            seen,
            product_name=product_name,
            coverage_type=coverage_type,
            plan_type=plan_type,
            pay_period=pay_period,
            rate=rate,
            source_row_no=source_row_no,
        )


def _append_renewal_note(
    rows: list[_RowSeed],
    seen: set[tuple[str, str, str, str]],
    *,
    product_name: str,
    note_text: str,
    coverage_type: str | None = None,
    source_row_no: int = 0,
) -> None:
    """
    예:
    갱신형 담보 (10년만기) : 150%, 갱신형 담보(1년만기) : 60%
    """
    for m in re.finditer(
        r"갱신형\s*담보\s*\(?\s*(?P<pay>[^):,]+?)\s*\)?\s*[:：]\s*(?P<rate>\d+(?:\.\d+)?)\s*%",
        note_text,
    ):
        _append(
            rows,
            seen,
            product_name=product_name,
            coverage_type=coverage_type,
            plan_type="갱신형 담보",
            pay_period=_clean_text(m.group("pay")),
            rate=m.group("rate"),
            source_row_no=source_row_no,
        )


# =============================================================================
# Parser
# =============================================================================

def _build_static_rows(text: str) -> list[_RowSeed]:
    """
    흥국화재 2026.05 PDF 레이아웃 대응.
    PDF 표의 줄바꿈이 깨지는 구간이 있어, 표 단위 규칙을 명시적으로 구성한다.
    """
    rows: list[_RowSeed] = []
    seen: set[tuple[str, str, str, str]] = set()

    # 1. 실손의료보험
    _append(rows, seen, product_name="흥Good 실손의료보험", plan_type="일반", pay_period="실손", rate="10", source_row_no=1)
    _append(rows, seen, product_name="흥Good 실손의료보험(계약전환용)", plan_type="계약전환용", pay_period="실손", rate="50", source_row_no=1)
    _append(rows, seen, product_name="흥Good 유병력자 실손의료보험", plan_type="유병력자", pay_period="실손", rate="10", source_row_no=1)
    _append(rows, seen, product_name="흥Good 유병력자 실손의료보험(재가입용)", plan_type="재가입용", pay_period="실손", rate="10", source_row_no=1)
    _append(rows, seen, product_name="흥Good 실손의료보험(단체전환용/개인재개용)", plan_type="단체전환용/개인재개용", pay_period="실손", rate="10", source_row_no=1)

    # 2. 재산종합보험
    product = "무배당 흥Good 행복든든 재산종합보험"
    headers = ["3년만기", "5년만기", "7년만기", "10년만기", "15년만기"]
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[100, 120, 140, 160, 200], plan_type="보장", coverage_type="보장", source_row_no=2)
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[30, 60, 90, 110, 170], plan_type="적립", coverage_type="저축", source_row_no=2)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="3년만기", rate=60, source_row_no=2)

    # 3. 운전자 종합보험
    product = "무배당 흥Good 든든한 SMILE 운전자 종합보험"
    headers = ["3년납", "5년납", "7년납", "10년납", "15년납", "20년납 이상"]
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[95, 110, 110, 160, 180, 200], plan_type="보장", coverage_type="보장", source_row_no=3)
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[10, 30, 50, 100, 100, 100], plan_type="적립", coverage_type="저축", source_row_no=3)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=3)

    # 4. 더플러스 종합보험
    product = "무배당 흥Good 더플러스 종합보험"
    _append_matrix(rows, seen, product_name=product, headers=["20년갱신", "25년갱신", "30년갱신", "30년갱신(무해지)"], values=[240, 240, 240, 230], plan_type="수정률", coverage_type="보장", source_row_no=4)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="10년만기", rate=150, source_row_no=4)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=4)

    # 5. 치아보험
    product = "무배당 흥Good 이튼튼한 치아보험"
    _append(rows, seen, product_name=product, plan_type="보장", pay_period="15년갱신", rate=240, coverage_type="보장", source_row_no=5)
    _append(rows, seen, product_name=product, plan_type="적립", pay_period="15년갱신", rate=150, coverage_type="저축", source_row_no=5)

    # 6. 연금저축
    product = "연금저축손해보험 흥Good 행복디딤돌보험"
    _append_matrix(rows, seen, product_name=product, headers=["5년", "6년", "7년", "8년", "9년", "10년", "15/20/전기납"], values=[1, 3, 6, 10, 15, 20, 20], plan_type="수정률", coverage_type="연금", source_row_no=6)

    # 7. 행복자산만들기 저축보험
    product = "무배당 흥Good 행복자산만들기 저축보험"
    maturity_cols = ["3년만기", "5년만기", "7년만기", "10년만기", "12년만기", "15년만기"]
    savings_table = {
        "5년납": {"보장": [15, 15, None, None, None, None], "적립": [15, 20, None, None, None, None]},
        "7년납": {"보장": [15, 25, 15, None, None, None], "적립": [15, 20, 25, None, None, None]},
        "10년납": {"보장": [15, 30, 35, 15, None, None], "적립": [15, 20, 25, 35, None, None]},
        "12년납": {"보장": [15, 30, 40, 45, 15, None], "적립": [15, 20, 25, 35, 40, None]},
        "15년납": {"보장": [15, 30, 40, 45, None, 15], "적립": [15, 20, 25, 35, None, 40]},
    }
    for pay, groups in savings_table.items():
        for plan, values in groups.items():
            for maturity, rate in zip(maturity_cols, values, strict=False):
                if rate is None:
                    continue
                _append(rows, seen, product_name=product, coverage_type="저축", plan_type=plan, pay_period=f"{pay} ({maturity})", rate=rate, source_row_no=7)

    # 8. 암보험 PLUS
    product = "무배당 흥Good 모두 담은 암보험 PLUS"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "20년납이상"], values=[155, 240], plan_type="비갱신형", coverage_type="보장", source_row_no=8)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="10년만기", rate=155, source_row_no=8)
    _append(rows, seen, product_name=product, plan_type="갱신형", pay_period="갱신형", rate=240, source_row_no=8)

    # 9. 뉴키즈 자녀보험
    product = "무배당 흥Good 뉴키즈 자녀보험"
    _append_matrix(rows, seen, product_name=product, headers=["5년납", "10년납", "15년납/18세납", "20년(세)납", "25년납", "30년(세)납"], values=[110, 160, 210, 240, 240, 240], plan_type="보장", coverage_type="보장(태아)", source_row_no=9)
    _append_matrix(rows, seen, product_name=product, headers=["10년미만", "10년", "20년"], values=[100, 160, 200], plan_type="갱신형 담보", coverage_type="보장(태아)", source_row_no=9)
    _append(rows, seen, product_name=product, plan_type="뇌성마비진단비", pay_period="담보별", rate=110, coverage_type="보장(태아)", source_row_no=9)
    _append(rows, seen, product_name=product, plan_type="태아 담보", pay_period="담보별", rate=15, coverage_type="보장(태아)", source_row_no=9)
    _append(rows, seen, product_name=product, plan_type="부양자담보", pay_period="담보별", rate=220, coverage_type="보장(태아)", source_row_no=9)

    # 9. 뉴키즈 적립
    _append_matrix_for_child_savings(rows, seen)

    # 10. 치매보험
    product = "무배당 흥Good 모두 담은 123 치매보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "20년납", "30년납"], values=[90, 180, 180], plan_type="수정률", coverage_type="보장", source_row_no=10)
    _append_matrix(rows, seen, product_name=product, headers=["10년미만", "20년"], values=[110, 180], plan_type="갱신형 담보", coverage_type="보장", source_row_no=10)

    # 11. 3N5 간편종합보험
    product = "무배당 흥Good 든든한 3N5 간편종합보험"
    headers = ["10년납", "15년납", "20년납", "25년납", "30년납"]
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[160, 220, 240, 240, 240], plan_type="비갱신형/통합간편가입형·초경증간편가입형", coverage_type="보장", source_row_no=11)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하", "10년초과"], values=[200, 220], plan_type="갱신형 담보/통합간편가입형·초경증간편가입형", coverage_type="보장", source_row_no=11)
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[110, 145, 160, 160, 160], plan_type="비갱신형/일반심사형", coverage_type="보장", source_row_no=11)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하", "10년초과"], values=[130, 145], plan_type="갱신형 담보/일반심사형", coverage_type="보장", source_row_no=11)
    _append_matrix(rows, seen, product_name=product, headers=["10년갱신", "20년갱신", "30년갱신"], values=[200, 240, 240], plan_type="갱신형/통합간편가입형·초경증간편가입형", coverage_type="보장", source_row_no=11)
    _append_matrix(rows, seen, product_name=product, headers=["10년갱신", "20년갱신", "30년갱신"], values=[130, 160, 160], plan_type="갱신형/일반심사형", coverage_type="보장", source_row_no=11)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=11)

    # 12. The편한 운전자상해보험
    product = "무배당 흥Good The편한 운전자상해보험"
    headers = ["10년납", "15년납", "20년납 이상"]
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[140, 160, 180], plan_type="보장", coverage_type="보장", source_row_no=12)
    _append_matrix(rows, seen, product_name=product, headers=headers, values=[100, 100, 100], plan_type="적립", coverage_type="저축", source_row_no=12)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=12)

    # 13. The 건강한 0545
    product = "무배당 흥Good The 건강한 0545 종합보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "15년납", "20년납", "25년납", "30년납"], values=[160, 210, 240, 240, 240], plan_type="수정률", coverage_type="보장", source_row_no=13)
    _append_matrix(rows, seen, product_name=product, headers=["10년미만", "10년", "20년"], values=[100, 160, 200], plan_type="갱신형 담보", coverage_type="보장", source_row_no=13)

    # 14. 325 간편종합보험
    product = "무배당 흥Good 든든한 325 암만 생각해도 간편종합보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "15년납", "20년납", "25년납", "30년납"], values=[160, 220, 240, 240, 240], plan_type="비갱신형/간편가입형", coverage_type="보장", source_row_no=14)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하", "10년초과"], values=[200, 220], plan_type="갱신형 담보/간편가입형", coverage_type="보장", source_row_no=14)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하갱신", "20년이상갱신"], values=[200, 240], plan_type="갱신형/간편가입형", coverage_type="보장", source_row_no=14)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=14)

    # 15. 플러스 간편치매간병보험
    product = "무배당 흥Good 플러스 간편치매간병보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "20년납", "30년납"], values=[110, 220, 220], plan_type="수정률", coverage_type="보장", source_row_no=15)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="20년", rate=220, source_row_no=15)

    # 16. The건강한 4565
    product = "무배당 흥Good The건강한 4565 종합보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "15년납", "20년납이상"], values=[180, 220, 240], plan_type="비갱신형/유해지", coverage_type="보장", source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/유해지", pay_period="20년만기", rate=220, source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/유해지", pay_period="10년만기", rate=180, source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/유해지", pay_period="1년만기", rate=60, source_row_no=16)
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "15년납", "20년납 이상"], values=[150, 210, 230], plan_type="비갱신형/무해지", coverage_type="보장", source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/무해지", pay_period="20년만기", rate=200, source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/무해지", pay_period="10년만기", rate=150, source_row_no=16)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보/무해지", pay_period="1년만기", rate=60, source_row_no=16)
    _append_matrix(rows, seen, product_name=product, headers=["1년갱신", "10년갱신", "20년이상갱신"], values=[60, 180, 220], plan_type="갱신형/유해지", coverage_type="보장", source_row_no=16)
    _append_matrix(rows, seen, product_name=product, headers=["1년갱신", "10년갱신", "20년이상갱신"], values=[60, 150, 200], plan_type="갱신형/무해지", coverage_type="보장", source_row_no=16)

    # 17. 고당지
    product = "무배당 흥Good 고당지 3.10.5 간편종합보험"
    _append_matrix(rows, seen, product_name=product, headers=["10년납", "15년납", "20년납", "25년납", "30년납"], values=[160, 220, 240, 240, 240], plan_type="비갱신형", coverage_type="보장", source_row_no=17)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하", "10년초과"], values=[200, 220], plan_type="갱신형 담보", coverage_type="보장", source_row_no=17)
    _append_matrix(rows, seen, product_name=product, headers=["10년이하갱신", "20년이상갱신"], values=[200, 240], plan_type="갱신형", coverage_type="보장", source_row_no=17)
    _append(rows, seen, product_name=product, plan_type="갱신형 담보", pay_period="1년만기", rate=60, source_row_no=17)

    # 18. 상급케어 UP 건강보험
    product = "무배당 흥Good 상급케어 UP 건강보험"
    _append_matrix(rows, seen, product_name=product, headers=["일반심사형", "10년건강고지형", "경증간편가입형Ⅳ"], values=[200, 200, 240], plan_type="갱신형/유해지", coverage_type="보장", source_row_no=18)
    _append_matrix(rows, seen, product_name=product, headers=["일반심사형", "10년건강고지형", "경증간편가입형Ⅳ"], values=[200, 200, 240], plan_type="갱신형/무해지", coverage_type="보장", source_row_no=18)

    return rows


def _append_matrix_for_child_savings(
    rows: list[_RowSeed],
    seen: set[tuple[str, str, str, str]],
) -> None:
    product = "무배당 흥Good 뉴키즈 자녀보험"
    maturities = ["30세만기", "40세만기", "80세만기", "90세만기", "100세만기"]
    table = {
        "10년납": [120, 120, 160, 160, 160],
        "15년납": [210, 210, 210, 210, 210],
        "20년(세)납": [240, 240, 240, 240, 240],
        "25년납": [240, 240, 240, 240, 240],
        "30년(세)납": [240, 240, 240, 240, 240],
    }

    for pay, values in table.items():
        for maturity, rate in zip(maturities, values, strict=False):
            _append(
                rows,
                seen,
                product_name=product,
                coverage_type="보장(태아)",
                plan_type="적립",
                pay_period=f"{pay} ({maturity})",
                rate=rate,
                source_row_no=9,
            )


# =============================================================================
# Public API
# =============================================================================

def build_fire_heungkuk_conversion_rows(
    example: RateExample,
    wb=None,  # PDF parser 호환용. xlsx workbook은 사용하지 않음.
) -> list[RateExampleConversionRow]:
    """
    흥국화재 수정률 PDF를 RateExampleConversionRow 리스트로 변환한다.
    """
    file_path = example.file.path
    text = _clean_text(_extract_pdf_text(file_path))

    if "장기보험 수정률표" not in text or "흥Good" not in text:
        logger.warning("흥국화재 수정률 PDF 식별 텍스트를 찾지 못했습니다: example_id=%s", example.pk)

    seeds = _build_static_rows(text)
    rows = [_make_row(example, seed) for seed in seeds]

    logger.info(
        "흥국화재 수정률 정규화 완료: example_id=%s rows=%s",
        example.pk,
        len(rows),
    )
    return rows
