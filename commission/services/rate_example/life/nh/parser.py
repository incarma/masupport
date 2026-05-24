# commission/services/rate_example/life/nh/parser.py
from __future__ import annotations

"""
농협생명 (NH) GA채널 환산율표 정규화 파서.

정규화 대상:
  - GA 시트 단일 시트
  - 블록 1: 주계약 월납   (R9~R51)
  - 블록 2: 주계약 저축·연금 (R56~R69)

제외 대상:
  - 특약(비갱신/갱신), 일시납 블록 전체

파싱 원칙:
  - '-' 값(미적용 구간) → 해당 (납기, rate) 조합 행 자체 제외
  - 환산율이 float/int 아닌 행 전체 제외
  - 마이초이스NH종신보험처럼 납기가 헤더 행에 포함된 경우
    → 납기 텍스트/숫자 행을 감지 후 다음 행 환산율과 zip 매핑
  - 연금/저축상품 2-row pair(납기 행 + 환산율 행) 반복 구조
    → pair 감지 후 언피벗

저장 정책:
  - 환산율은 백분율 수치 기준으로 저장한다 (프로젝트 SSOT).
    예: Excel 표시 80.0%  → openpyxl value=0.8  → DB Decimal("80.0")
        Excel 표시 155.0% → openpyxl value=1.55 → DB Decimal("155.0")
  - 농협 raw 파일의 환산율 셀은 number_format='0.0%' 이므로
    openpyxl data_only 읽기 시 내부 저장값(배수)이 반환된다.
    → ×100 보정 후 저장 (교보와 동일 정책)

컬럼 인덱스 (1-based):
  col_2: 상품분류 (product_class)
  col_3: 상품명   (product_name)
  col_4: 상품구분  (plan_type)
  col_5: 세부구분  (일부 상품 전용)
  col_6~9: 납기별 환산율 (또는 납기 레이블 헤더)
"""

import logging
from decimal import Decimal

from commission.models import RateExample, RateExampleConversionRow
from commission.services.rate_example.common.decimal import (
    decimal_percent_value,
)

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

TARGET_SHEET = "GA"

# 주계약 월납 블록 (헤더·주석 행 포함)
BLOCK_MONTHLY_START = 9
BLOCK_MONTHLY_END   = 51   # inclusive

# 주계약 저축·연금 블록
BLOCK_SAVINGS_START = 56
BLOCK_SAVINGS_END   = 69   # inclusive

# 헤더/주석 행 판별 접두사
SKIP_PREFIXES = ("주)", "※", "상품분류", "구  분", "1.", "①", "②", "③")

# 표준 납기 레이블
STD_PAY_LABELS = ["10년 미만", "10년 이상", "15년 이상", "20년 이상"]


# ── 보종 판정 ─────────────────────────────────────────────────────────────────

def _coverage_type(product_name: str, product_class: str = "") -> str:
    n = (product_name or "").replace("\n", "")
    if "종신" in n:
        if "경영인" in n or "CEO" in n:
            return "CEO정기"
        return "종신/CI"
    if "정기" in n:
        return "CEO정기" if "경영" in n else "종신/CI"
    if "치매" in n or "간병" in n:
        return "기타(보장성)"
    if "연금저축" in n:
        return "연금저축"
    if "연금" in n:
        return "연금"
    if "저축" in n:
        return "연금"
    if "실손" in n:
        return "실손"
    return "기타(보장성)"


# ── 값 판별 헬퍼 ──────────────────────────────────────────────────────────────

def _is_pay_label_str(v) -> bool:
    """납기 레이블 문자열인지 (ex: '5년납', '10년 이상', '20년납')."""
    if not isinstance(v, str):
        return False
    s = v.strip()
    return bool(s) and s != "-"


def _is_rate_value(v) -> bool:
    """유효한 환산율 숫자인지."""
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str) and v.strip() == "-":
        return False
    return False


def _to_decimal(v, is_percent_cell: bool = False) -> Decimal | None:
    """
    float/int → Decimal. None/'-' → None.

    is_percent_cell=True 이면 ×100 보정을 적용한다.
    농협 raw 파일의 환산율 셀은 number_format='0.0%' 이므로
    openpyxl이 반환하는 값이 Excel 내부 저장값(배수)이다.
    예: 화면 표시 80.0% → openpyxl value=0.8 → 보정 후 Decimal("80.0")
    """
    if not _is_rate_value(v):
        return None

    number_format = "0%" if is_percent_cell else ""
    dec = decimal_percent_value(v, number_format=number_format)
    if dec is None:
        return None

    if is_percent_cell:
        return dec.quantize(Decimal("0.0001"))
    return dec


def _is_header_or_comment_row(v2, v3) -> bool:
    """헤더·주석 행 판별."""
    for v in (v2, v3):
        if v is None:
            continue
        s = str(v).strip()
        for prefix in SKIP_PREFIXES:
            if s.startswith(prefix):
                return True
    return False


def _cell(ws, row_no: int, col_idx: int):
    """1-based 컬럼 인덱스로 셀 값 반환."""
    return ws.cell(row=row_no, column=col_idx).value


def _is_percent_cell(ws, row_no: int, col_idx: int) -> bool:
    """
    해당 셀의 number_format에 '%' 가 포함되는지 판별.

    농협 환산율 셀은 '0.0%' 포맷이므로 True 반환.
    납기 레이블 셀('0"년납"' 등)은 False 반환.
    """
    nf = ws.cell(row=row_no, column=col_idx).number_format or ""
    return "%" in nf


def _normalize_pay_label(v) -> str:
    """납기 레이블 정규화. 숫자이면 '5년' 형태로 변환."""
    if isinstance(v, (int, float)):
        n = int(v)
        return f"{n}년납"
    return str(v).strip()


def _make_row(
    example: RateExample,
    sheet_name: str,
    row_no: int,
    product_name: str,
    plan_type: str,
    pay_period: str,
    rate: Decimal,
    coverage_type: str,
) -> RateExampleConversionRow:
    return RateExampleConversionRow(
        source_file=example,
        source_sheet=sheet_name,
        source_row_no=row_no,
        insurer_type=example.insurer_type,
        category=example.category,
        insurer=example.insurer,
        coverage_type=coverage_type,
        strategy_flag="",
        product_name=product_name.replace("\n", " ").strip(),
        plan_type=(plan_type or "").strip(),
        pay_period=pay_period.strip(),
        year1=rate,
        year2=rate,
        year3=rate,
        year4=rate,
    )


# ── 주계약 월납 블록 파서 ──────────────────────────────────────────────────────

def _parse_monthly_block(
    example: RateExample,
    ws,
    sheet_name: str,
) -> list[RateExampleConversionRow]:
    """
    주계약 월납 블록 (R9~R51) 정규화.

    처리 케이스:
      표준) 10년미만/이상/15년이상/20년이상 4컬럼 구조
      케이스 B) 상품 고유 납기 헤더 (NH올원더풀치매보험: 헤더가 str)
      케이스 A) 마이초이스NH종신보험: 납기가 str 또는 int 숫자로 6~9열에 등장하며
               plan_type 변경마다 새 납기 헤더 행이 등장한다.

    납기 헤더 행 판별 기준:
      1) v6이 str이고 rate 값이 아닌 경우 → 납기 헤더 행 (str 레이블)
      2) in_custom_pay_mode=True이고 v3이 없고 v4가 있으며
         v6~v9 중 하나라도 숫자(int/float)인 경우 → 숫자 납기 헤더 행

    마이초이스 처리 흐름:
      R15: v3=상품명, v4=해약환급금일부지급형, v6='5년납'(str) → 케이스1 납기헤더
      R16: v8=1.65, v9=1.8 → flush → 해약/10년납=1.65, 해약/12년납=1.8
      R17: v4='표준형', v6=5(int), v7=7, v8=10, v9=12 → 케이스2 납기헤더 (plan 갱신)
      R18: v8=1.25, v9=1.45 → flush → 표준형/10년납=1.25, 표준형/12년납=1.45
      R19: v6='20년납'(str) → 케이스1 납기헤더 (plan 그대로 '표준형')
      R20: v6=2.4 → flush → 표준형/20년납=2.4
    """
    rows: list[RateExampleConversionRow] = []

    cur_product       = ""
    cur_plan          = ""
    cur_product_class = ""

    # 납기 헤더 모드: v6~v9에 납기 레이블이 들어오고 다음 행에 환산율이 오는 구조
    in_custom_pay_mode = False
    custom_pay_labels: list[str] = []

    # 현재 상품에 활성화된 납기 레이블 목록 (표준 or 커스텀)
    active_pay_labels: list[str] = list(STD_PAY_LABELS)

    def flush_custom(row_no_ref: int, v6, v7, v8, v9, plan_override: str = ""):
        plan = plan_override if plan_override else cur_plan
        raw_rates = [v6, v7, v8, v9]
        col_indices = [6, 7, 8, 9]
        for label, rv, col_idx in zip(custom_pay_labels, raw_rates, col_indices):
            pct = _is_percent_cell(ws, row_no_ref, col_idx)
            dec = _to_decimal(rv, pct)
            if dec is None:
                continue
            rows.append(_make_row(
                example, sheet_name, row_no_ref,
                cur_product, plan, label, dec,
                _coverage_type(cur_product, cur_product_class),
            ))

    for row_no in range(BLOCK_MONTHLY_START, BLOCK_MONTHLY_END + 1):
        v2 = _cell(ws, row_no, 2)
        v3 = _cell(ws, row_no, 3)
        v4 = _cell(ws, row_no, 4)
        v5 = _cell(ws, row_no, 5)
        v6 = _cell(ws, row_no, 6)
        v7 = _cell(ws, row_no, 7)
        v8 = _cell(ws, row_no, 8)
        v9 = _cell(ws, row_no, 9)

        # ── 헤더/주석 행 스킵 ─────────────────────────────────────────────────
        if _is_header_or_comment_row(v2, v3):
            in_custom_pay_mode = False
            custom_pay_labels  = []
            active_pay_labels  = list(STD_PAY_LABELS)
            continue

        # ── 상품명 갱신 ────────────────────────────────────────────────────────
        # v3이 있으면 새 상품 시작 → 커스텀 납기 모드 초기화
        if v3 is not None:
            cur_product       = str(v3)
            # '상품구분'은 컬럼 헤더 텍스트이므로 plan_type에 저장하지 않는다.
            _plan_raw = str(v4) if v4 is not None else ""
            cur_plan = "" if _plan_raw.strip() == "상품구분" else _plan_raw
            cur_product_class = str(v2) if v2 is not None else cur_product_class
            in_custom_pay_mode = False
            custom_pay_labels  = []
            active_pay_labels  = list(STD_PAY_LABELS)

        # ── 케이스 1: v6이 str인 납기 헤더 행 감지 ───────────────────────────
        #    예: v6='5년납', v6='10년 이상', v6='20년납'
        if _is_pay_label_str(v6):
            # v4가 있으면 plan 갱신 (표준형 / 해약환급금일부지급형 등)
            if v4 is not None and v3 is None:
                cur_plan = str(v4)
            # 납기 레이블 수집 (str만)
            labels = []
            for rv in (v6, v7, v8, v9):
                if rv is None:
                    break
                if isinstance(rv, str):
                    s = rv.strip()
                    if s and s != "-":
                        labels.append(s)
                elif isinstance(rv, (int, float)):
                    # 숫자 납기: 5, 7, 10, 12 → '5년납', '7년납', '10년납', '12년납'
                    labels.append(_normalize_pay_label(rv))
                # '-' 값 납기는 skip
            if labels:
                custom_pay_labels  = labels
                active_pay_labels  = labels
                in_custom_pay_mode = True
            continue

        # ── 케이스 2: in_custom_pay_mode 상태에서 v4(plan 변경) + v6~v9가 숫자 납기 ──
        #    예: R17: v4='표준형', v6=5, v7=7, v8=10, v9=12
        if (
            in_custom_pay_mode
            and v3 is None
            and v4 is not None
            and any(isinstance(rv, (int, float)) for rv in (v6, v7, v8, v9))
            and not any(_is_rate_value(rv) and rv < 5 for rv in (v6, v7, v8, v9) if rv is not None)
            # 납기 숫자는 보통 5~30 범위. 환산율은 0.1~2.7 범위.
            # v6이 5 이상 int이면 납기로 판단
            and all(
                (isinstance(rv, (int, float)) and int(rv) >= 5)
                for rv in (v6, v7, v8, v9) if rv is not None
            )
        ):
            cur_plan = str(v4)
            labels = [
                _normalize_pay_label(rv)
                for rv in (v6, v7, v8, v9) if rv is not None
            ]
            if labels:
                custom_pay_labels  = labels
                active_pay_labels  = labels
                in_custom_pay_mode = True
            continue

        # ── in_custom_pay_mode: 환산율 flush ─────────────────────────────────
        if in_custom_pay_mode:
            # v4가 있으면 cur_plan 갱신 (예: 핑크케어 R47=간편가입, R48=일반가입)
            # '상품구분'은 컬럼 헤더이므로 제외
            if v3 is None and v4 is not None and str(v4).strip() not in ("상품구분", ""):
                cur_plan = str(v4).strip()
            flush_custom(row_no, v6, v7, v8, v9)
            continue

        # ── 표준 환산율 행 처리 ────────────────────────────────────────────────
        # plan 갱신 (v3 없고 v4만 있는 경우 — 예: 만기환급형)
        if v3 is None and v4 is not None:
            cur_plan = str(v4)

        for label, rv, col_idx in zip(active_pay_labels, (v6, v7, v8, v9), (6, 7, 8, 9)):
            pct = _is_percent_cell(ws, row_no, col_idx)
            dec = _to_decimal(rv, pct)
            if dec is None:
                continue
            # v5가 세부구분으로 사용되는 경우 (9988NH건강보험 등)
            plan = cur_plan
            if v5 is not None:
                plan = f"{cur_plan}/{str(v5)}" if cur_plan else str(v5)

            rows.append(_make_row(
                example, sheet_name, row_no,
                cur_product, plan, label, dec,
                _coverage_type(cur_product, cur_product_class),
            ))

    return rows


# ── 주계약 저축·연금 블록 파서 ───────────────────────────────────────────────

def _parse_savings_block(
    example: RateExample,
    ws,
    sheet_name: str,
) -> list[RateExampleConversionRow]:
    """
    주계약 저축·연금 블록 (R56~R69) 정규화.

    구조:
      납기 레이블 행 (str) + 환산율 행이 pair로 반복.
      한 상품당 최대 2 pair (최대 8개 납기).
      '-' 값 제외.
      실손의료비보험: 납기 헤더 없이 단일 환산율 → pay_period='전기납' 저장.
    """
    rows: list[RateExampleConversionRow] = []

    cur_product       = ""
    cur_product_class = ""
    pending_labels: list[str] = []

    for row_no in range(BLOCK_SAVINGS_START, BLOCK_SAVINGS_END + 1):
        v2 = _cell(ws, row_no, 2)
        v3 = _cell(ws, row_no, 3)
        v6 = _cell(ws, row_no, 6)
        v7 = _cell(ws, row_no, 7)
        v8 = _cell(ws, row_no, 8)
        v9 = _cell(ws, row_no, 9)

        # 주석/헤더 스킵
        if _is_header_or_comment_row(v2, v3):
            pending_labels = []
            continue

        # 상품명 갱신
        if v3 is not None:
            cur_product       = str(v3)
            cur_product_class = str(v2) if v2 is not None else cur_product_class
            pending_labels    = []

        raw_vals = [v6, v7, v8, v9]

        # 납기 레이블 행 판별: v6~v9 중 하나라도 str인 경우
        is_label_row = any(_is_pay_label_str(rv) for rv in raw_vals)

        if is_label_row:
            pending_labels = []
            for rv in raw_vals:
                if _is_pay_label_str(rv):
                    pending_labels.append(rv.strip())
                # '-' 값 납기는 skip
            continue

        # 환산율 행
        if pending_labels:
            for label, rv, col_idx in zip(pending_labels, raw_vals, (6, 7, 8, 9)):
                pct = _is_percent_cell(ws, row_no, col_idx)
                dec = _to_decimal(rv, pct)
                if dec is None:
                    continue
                rows.append(_make_row(
                    example, sheet_name, row_no,
                    cur_product, "", label, dec,
                    _coverage_type(cur_product, cur_product_class),
                ))
            pending_labels = []
        else:
            # 단일 환산율 행 (실손의료비보험 등 납기 헤더 없는 상품)
            pct = _is_percent_cell(ws, row_no, 6)
            dec = _to_decimal(v6, pct)
            if dec is not None:
                rows.append(_make_row(
                    example, sheet_name, row_no,
                    cur_product, "", "전기납", dec,
                    _coverage_type(cur_product, cur_product_class),
                ))

    return rows


# ── 진입점 ────────────────────────────────────────────────────────────────────

def build_life_nh_conversion_rows(
    example: RateExample,
    wb,
) -> list[RateExampleConversionRow]:
    """
    농협생명 GA 환산율표 정규화 진입점.

    반환:
    - RateExampleConversionRow 리스트 (DB 미저장 상태)
    """
    if TARGET_SHEET not in wb.sheetnames:
        logger.warning(
            "life_nh: '%s' 시트를 찾을 수 없습니다. sheetnames=%s",
            TARGET_SHEET,
            wb.sheetnames,
        )
        return []

    ws = wb[TARGET_SHEET]

    monthly_rows = _parse_monthly_block(example, ws, TARGET_SHEET)
    savings_rows = _parse_savings_block(example, ws, TARGET_SHEET)

    logger.info(
        "life_nh: 정규화 완료 — 총 %d rows (월납=%d, 저축연금=%d)",
        len(monthly_rows) + len(savings_rows),
        len(monthly_rows),
        len(savings_rows),
    )

    return monthly_rows + savings_rows
