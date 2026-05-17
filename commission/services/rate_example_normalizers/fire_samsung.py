# django_ma/commission/services/rate_example_normalizers/fire_samsung.py
from __future__ import annotations

"""
삼성화재 손해보험 수정률 정규화 parser.

대상:
- insurer_type = fire
- category = conv
- insurer = 삼성

정규화 출력:
- 보험사     → insurer = "삼성"
- 상품군     → coverage_type
- 상품명     → product_name
- 구분       → plan_type
- 납기       → pay_period
- 수정률     → year1

중요:
- RateExampleConversionRow.year1은 DecimalField이므로 "%" 문자열을 저장하지 않는다.
- raw 수치 자체를 백분율 수치로 저장한다.
  예: raw 160 → Decimal("160") 저장 → 화면/API에서 "160%"로 표시
- raw가 Excel 내부 percent 값(예: 1.6, number_format="0%")이면 표시값 기준 160으로 보정한다.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from commission.models import RateExample, RateExampleConversionRow


INSURER = "삼성"

TITLE_SEARCH_MAX_ROWS = 12

HEADER_KEY_PLAN = "구분"
HEADER_KEY_PAY_PERIOD = "납기"
HEADER_KEY_RATE = "수정률"

PAY_PERIOD_HEADER_KEYWORDS = ("년", "만기", "최초", "갱신")
SKIP_TEXT_KEYWORDS = ("담보군", "비고", "주)", "※", "*")


def build_fire_samsung_conversion_rows(
    example: RateExample,
    wb,
) -> list[RateExampleConversionRow]:
    """
    삼성화재 손보 수정률 raw workbook을 RateExampleConversionRow 목록으로 변환한다.

    처리 방식:
    1. 모든 시트 순회
    2. 병합셀 값을 parser 내부 matrix에서만 전파
    3. 테이블 제목행과 헤더행을 탐지
    4. 테이블별로 행형/매트릭스형 수정률을 공통 스키마로 펼침
    """
    rows: list[RateExampleConversionRow] = []

    for ws in wb.worksheets:
        values = _build_value_matrix(ws)
        table_headers = _find_header_rows(ws, values)

        for idx, header in enumerate(table_headers):
            header_row, header_cols = header
            next_header_row = (
                table_headers[idx + 1][0]
                if idx + 1 < len(table_headers)
                else (ws.max_row or header_row) + 1
            )

            title = _find_table_title(values, header_row)
            if not title:
                continue

            product_name = _normalize_product_name(title)
            if not product_name:
                continue

            plan_col = header_cols.get("plan")
            pay_period_col = header_cols.get("pay_period")
            rate_col = header_cols.get("rate")
            pay_period_rate_cols = header_cols.get("pay_period_rate_cols", [])

            for row_no in range(header_row + 1, next_header_row):
                row_values = [
                    _to_text(values.get((row_no, col_no)))
                    for col_no in range(1, (ws.max_column or 1) + 1)
                ]
                if _is_skip_row(row_values):
                    continue

                plan_type = _to_text(values.get((row_no, plan_col))) if plan_col else ""
                plan_type = _clean_text(plan_type)

                # A. 납기 컬럼 + 수정률 컬럼이 모두 있는 행형 테이블
                if pay_period_col and rate_col:
                    pay_period = _normalize_pay_period(values.get((row_no, pay_period_col)))
                    mod_rate = _to_decimal_percent(
                        values.get((row_no, rate_col)),
                        number_format=_cell_number_format(ws, row_no, rate_col),
                    )
                    if not pay_period or mod_rate is None:
                        continue

                    rows.append(_make_row(
                        example=example,
                        ws=ws,
                        row_no=row_no,
                        title=title,
                        product_name=product_name,
                        plan_type=plan_type,
                        pay_period=pay_period,
                        mod_rate=mod_rate,
                    ))
                    continue

                # B. 납기 컬럼 없이 헤더가 납기 역할을 하는 매트릭스형 테이블
                for col_no, header_text in pay_period_rate_cols:
                    pay_period = _normalize_pay_period(header_text)
                    mod_rate = _to_decimal_percent(
                        values.get((row_no, col_no)),
                        number_format=_cell_number_format(ws, row_no, col_no),
                    )
                    if not pay_period or mod_rate is None:
                        continue

                    rows.append(_make_row(
                        example=example,
                        ws=ws,
                        row_no=row_no,
                        title=title,
                        product_name=product_name,
                        plan_type=plan_type,
                        pay_period=pay_period,
                        mod_rate=mod_rate,
                    ))

    return rows


def _make_row(
    *,
    example: RateExample,
    ws: Worksheet,
    row_no: int,
    title: str,
    product_name: str,
    plan_type: str,
    pay_period: str,
    mod_rate: Decimal,
) -> RateExampleConversionRow:
    """RateExampleConversionRow 생성 공통 helper."""
    return RateExampleConversionRow(
        source_file=example,
        source_sheet=ws.title,
        source_row_no=row_no,
        insurer_type=RateExample.TYPE_FIRE,
        category=RateExample.CAT_CONV,
        insurer=INSURER,
        coverage_type=_resolve_coverage_type(
            title=title,
            product_name=product_name,
            plan_type=plan_type,
            pay_period=pay_period,
        ),
        strategy_flag="",
        product_name=product_name,
        plan_type=plan_type,
        pay_period=pay_period,
        year1=mod_rate,
        year2=None,
        year3=None,
        year4=None,
    )


def _build_value_matrix(ws: Worksheet) -> dict[tuple[int, int], Any]:
    """
    병합셀 값을 포함한 value matrix를 만든다.

    실제 workbook은 변경하지 않고, parser 내부에서만 병합 범위 전체에
    좌상단 값을 전파한다.
    """
    values: dict[tuple[int, int], Any] = {}

    for row in ws.iter_rows():
        for cell in row:
            values[(cell.row, cell.column)] = cell.value

    for merged in ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged.bounds
        top_left = values.get((min_row, min_col))
        for row_no in range(min_row, max_row + 1):
            for col_no in range(min_col, max_col + 1):
                values[(row_no, col_no)] = top_left

    return values


def _find_header_rows(
    ws: Worksheet,
    values: dict[tuple[int, int], Any],
) -> list[tuple[int, dict[str, Any]]]:
    """
    테이블 헤더행을 찾는다.

    지원 형태:
    - 구분 / 납기 / 수정률
    - 구분 / 5년 / 10년 / 최초 / 갱신 등 납기형 헤더
    """
    headers: list[tuple[int, dict[str, Any]]] = []

    for row_no in range(1, (ws.max_row or 1) + 1):
        row_map: dict[int, str] = {
            col_no: _clean_text(values.get((row_no, col_no)))
            for col_no in range(1, (ws.max_column or 1) + 1)
        }

        non_empty = {col: text for col, text in row_map.items() if text}
        if len(non_empty) < 2:
            continue

        plan_col = _find_col_by_exact(non_empty, HEADER_KEY_PLAN)
        pay_period_col = _find_col_by_exact(non_empty, HEADER_KEY_PAY_PERIOD)
        rate_col = _find_col_by_exact(non_empty, HEADER_KEY_RATE)

        pay_period_rate_cols = [
            (col_no, text)
            for col_no, text in non_empty.items()
            if _looks_like_pay_period_header(text)
        ]

        # 행형: 구분 + 납기 + 수정률
        if plan_col and pay_period_col and rate_col:
            headers.append((
                row_no,
                {
                    "plan": plan_col,
                    "pay_period": pay_period_col,
                    "rate": rate_col,
                    "pay_period_rate_cols": [],
                },
            ))
            continue

        # 매트릭스형: 구분 + 납기형 헤더 1개 이상
        if plan_col and pay_period_rate_cols:
            headers.append((
                row_no,
                {
                    "plan": plan_col,
                    "pay_period": None,
                    "rate": None,
                    "pay_period_rate_cols": pay_period_rate_cols,
                },
            ))

    return headers


def _find_table_title(
    values: dict[tuple[int, int], Any],
    header_row: int,
) -> str:
    """
    헤더행 위쪽에서 가장 가까운 테이블 제목을 찾는다.

    제목은 보통 병합셀 또는 첫 번째 텍스트 셀에 있고,
    ':'가 있으면 상품명 파싱에도 사용된다.
    """
    start = max(1, header_row - TITLE_SEARCH_MAX_ROWS)

    for row_no in range(header_row - 1, start - 1, -1):
        texts = [
            _clean_text(values.get((row_no, col_no)))
            for col_no in range(1, 80)
        ]
        texts = [t for t in texts if t]
        if not texts:
            continue

        joined = " ".join(texts)
        if _is_probable_title(joined):
            return joined

    return ""


def _is_probable_title(text: str) -> bool:
    """테이블 제목 후보 여부를 판단한다."""
    if not text:
        return False
    if any(k in text for k in SKIP_TEXT_KEYWORDS):
        return False
    if HEADER_KEY_PLAN in text and (HEADER_KEY_RATE in text or HEADER_KEY_PAY_PERIOD in text):
        return False
    return True


def _normalize_product_name(title: str) -> str:
    """
    상품명 정규화.

    ':'가 있으면 오른쪽 텍스트만 상품명으로 사용하고,
    없으면 제목 전체를 상품명으로 사용한다.
    """
    text = _clean_text(title)
    if ":" in text:
        text = text.split(":", 1)[1]
    elif "：" in text:
        text = text.split("：", 1)[1]
    return _clean_text(text)


def _resolve_coverage_type(
    *,
    title: str,
    product_name: str,
    plan_type: str,
    pay_period: str,
) -> str:
    """
    상품군 정규화.

    - 제목에 실손 포함 + 납기 최초 → 단독실손(초회)
    - 제목에 실손 포함 + 납기 갱신 → 단독실손(갱신)
    - 제목에 자녀 포함 → 보장(태아)
    - 그 외 → 보장
    """
    title_text = _clean_text(title)
    product_text = _clean_text(product_name)
    plan_text = _clean_text(plan_type)
    pay_text = _clean_text(pay_period)
    joined = f"{title_text} {product_text} {plan_text}"

    if "실손" in joined:
        if "최초" in pay_text:
            return "단독실손(초회)"
        if "갱신" in pay_text:
            return "단독실손(갱신)"

    # 삼성화재 raw는 태아/자녀 정보가 테이블 제목뿐 아니라
    # 요약표의 세분/상품명/구분 영역에만 존재하는 경우가 있어
    # title + product_name + plan_type 전체를 기준으로 판정한다.
    if "자녀" in joined or "슈퍼스타" in joined:
        return "보장(태아)"

    return "보장"


def _normalize_pay_period(value: Any) -> str:
    """
    납기 정규화.

    - 숫자만 있으면 끝에 '년' 추가
    - Excel 숫자 10.0은 '10년' 처리
    - 텍스트는 줄바꿈 제거 후 공백 정리
    """
    text = _clean_text(value)
    if not text:
        return ""

    if re.fullmatch(r"\d+(\.0+)?", text):
        return f"{str(int(Decimal(text)))}년"

    return text


def _to_decimal_percent(value: Any, *, number_format: str = "") -> Decimal | None:
    """
    수정률을 Decimal 백분율 수치로 변환한다.

    정책:
    - raw 수치가 160이면 Decimal("160") 저장
    - raw 문자열이 '160%'이면 Decimal("160") 저장
    - Excel 내부값이 1.6이고 number_format이 '%'이면 표시값 기준 Decimal("160") 저장
    - 0, 공란, '-'는 제외
    """
    if value is None:
        return None

    if isinstance(value, str):
        text = _clean_text(value)
        if not text or text in {"-", "–", "—"}:
            return None
        text = text.replace("%", "").replace(",", "")
    else:
        text = str(value).replace(",", "")

    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError):
        return None

    if dec == 0:
        return None

    # Excel percent 서식 셀 중 내부값이 1.45 / 2.4처럼 저장된 경우만
    # 표시값 기준 145 / 240으로 보정한다.
    # 이미 raw가 145 / 240인 값에는 절대 100을 곱하지 않는다.
    if "%" in str(number_format or "") and abs(dec) <= Decimal("3"):
        dec = dec * Decimal("100")

    # 방어 보정:
    # 기존 잘못된 parser 또는 특수 서식 때문에 14500, 2400처럼 과대계상된
    # 값이 들어온 경우 실제 수정률 수치로 되돌린다.
    # 예: 14500 -> 145, 2400 -> 240
    while abs(dec) >= Decimal("10000"):
        dec = dec / Decimal("100")
    while abs(dec) > Decimal("1000"):
        dec = dec / Decimal("10")
        dec = dec * Decimal("100")

    return dec.quantize(Decimal("0.0001"))


def _cell_number_format(ws: Worksheet, row_no: int, col_no: int) -> str:
    """셀 number_format 안전 조회."""
    try:
        return str(ws.cell(row=row_no, column=col_no).number_format or "")
    except Exception:
        return ""


def _find_col_by_exact(non_empty: dict[int, str], label: str) -> int | None:
    """공백 제거 후 정확히 일치하는 헤더 컬럼을 찾는다."""
    normalized_label = _compact(label)
    for col_no, text in non_empty.items():
        if _compact(text) == normalized_label:
            return col_no
    return None


def _looks_like_pay_period_header(text: str) -> bool:
    """납기 역할을 할 수 있는 헤더인지 판단한다."""
    value = _clean_text(text)
    if not value:
        return False
    if _compact(value) in {
        _compact(HEADER_KEY_PLAN),
        _compact(HEADER_KEY_PAY_PERIOD),
        _compact(HEADER_KEY_RATE),
    }:
        return False
    return any(keyword in value for keyword in PAY_PERIOD_HEADER_KEYWORDS)


def _is_skip_row(row_values: list[str]) -> bool:
    """주석/빈 행/합계성 행 제외."""
    texts = [v for v in row_values if v]
    if not texts:
        return True

    joined = " ".join(texts)
    if any(keyword in joined for keyword in SKIP_TEXT_KEYWORDS):
        return True

    # 데이터 없이 라벨만 있는 행 방어
    if len(texts) == 1 and _is_probable_title(texts[0]):
        return True

    return False


def _to_text(value: Any) -> str:
    """값을 문자열로 안전 변환한다."""
    if value is None:
        return ""
    return str(value)


def _clean_text(value: Any) -> str:
    """줄바꿈/중복 공백 정리."""
    text = _to_text(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compact(value: Any) -> str:
    """비교용 문자열: 모든 공백 제거."""
    return re.sub(r"\s+", "", _clean_text(value))