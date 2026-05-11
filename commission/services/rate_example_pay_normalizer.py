# commission/services/rate_example_pay_normalizer.py
from __future__ import annotations

"""
지급률 예시표 정규화 서비스.

파일 위치:
    commission/services/rate_example_pay_normalizer.py

역할:
- 업로드된 지급률 xlsx를 20개 생보사 컬럼 매핑에 따라 RateExamplePayRow로 적재한다.
- 대상 시트: '① 5천만, 3천만↑' (5천만원↑ 블록만 처리)
- IBK는 별도 레이아웃 처리 (coverage_type = "[IBK]{상품명}")
- 파서에서 예외 발생 시 삼키지 않고 호출부(rate_example_normalizer.py)에서 rollback

보안/운영 원칙:
- 파일 URL 직접 접근 금지. FieldFile.path만 서버 내부에서 사용.
- 파싱 실패 시 예외를 raise — 호출부 transaction.atomic()이 rollback 처리.
"""

import logging
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# ── 대상 시트명 ───────────────────────────────────────────────────────────────
TARGET_SHEET = "① 5천만, 3천만↑"

# ── 상품군 정규화 매핑 ────────────────────────────────────────────────────────
# raw 파일 col4 값 → DB 저장 coverage_type
COVERAGE_MAP: dict[str, str] = {
    "종신,CI":     "종신/CI",
    "연금":        "연금",
    "변액연금":    "변액연금",
    "저축":        "저축",
    "VUL":        "VUL",
    "연금저축":    "연금저축",
    "기타(보장성)": "기타(보장성)",
    "CEO정기":    "CEO정기",
    "전략상품1":  "전략상품1",
    "전략상품2":  "전략상품2",
    "전략상품3":  "전략상품3",
    "전략상품4":  "전략상품4",
}

# ── 보험사별 컬럼 매핑 ─────────────────────────────────────────────────────────
# 형식: {insurer_db_name: (col_a, col_b, col_c, col_d, col_e, col_f)}
# 값은 1-indexed 열 번호. None = 해당 컬럼 없음 (DB에 None 저장).
# insurer_db_name: RateExample.LIFE_INSURERS 의 약칭과 일치

# 그룹1 (헤더행 3, 데이터 5천만↑ 행 5~16)
_GROUP1_ROWS = (5, 16)
_GROUP1: dict[str, tuple] = {
    "ABL": (5,  6,  7,  8,  9,  10),
    "삼성": (12, 13, 14, 15, 16, 17),
    "신한": (19, 20, 21, 22, 23, 24),
    "하나": (26, 27, 28, 29, 30, None),
    # IBK는 별도 처리 — 이 dict에 포함하지 않음
}

# 그룹2 (헤더행 30, 데이터 5천만↑ 행 32~43)
_GROUP2_ROWS = (32, 43)
_GROUP2: dict[str, tuple] = {
    "DB":   (5,  6,  7,  8,  9,  10),
    "IM":   (12, 13, 14, 15, 16, 17),
    "KB":   (19, 20, 21, 22, 23, 24),
    "농협":  (26, 27, 28, 29, 30, None),
    "라이나": (32, 33, 34, 35, 36, None),
}

# 그룹3 (헤더행 57, 데이터 5천만↑ 행 59~70)
_GROUP3_ROWS = (59, 70)
_GROUP3: dict[str, tuple] = {
    "KDB":  (5,  6,  7,  8,  9,  10),
    "미래":  (12, 13, 14, 15, 16, 17),
    "처브":  (19, 20, 21, 22, 23, 24),
    "한화":  (26, 27, 28, 29, 30, 31),
    "카디프": (34, 35, 36, 37, 38, 39),
}

# 그룹4 (헤더행 84, 데이터 5천만↑ 행 86~97)
_GROUP4_ROWS = (86, 97)
_GROUP4: dict[str, tuple] = {
    "동양":   (5,  6,  7,  8,  9,  None),
    "메트":   (11, 12, 13, 14, 15, 16),
    "흥국":   (18, 19, 20, 21, 22, 23),
    "푸본현대": (25, 26, 27, 28, 29, None),
    "교보":   (31, 32, 33, 34, 35, 36),
}

# IBK 전용 (그룹1 데이터 행 공유 5~16, 컬럼 시작 col35)
_IBK_ROWS       = (5, 16)
_IBK_PRODUCT_COL = 32      # 1-indexed: col32 = IBK 자체 상품명
_IBK_COLS        = (35, 36, 37, 38, 39, None)

# 전체 그룹 목록 (순서 유지)
_GROUPS: list[tuple] = [
    (_GROUP1_ROWS, _GROUP1),
    (_GROUP2_ROWS, _GROUP2),
    (_GROUP3_ROWS, _GROUP3),
    (_GROUP4_ROWS, _GROUP4),
]


# ── 유틸 함수 ─────────────────────────────────────────────────────────────────

def _to_decimal(value) -> "Decimal | None":
    """raw 셀 값 → Decimal(소수점 4자리). None이면 None 반환."""
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _get_col(row: tuple, col_1indexed: "int | None") -> "Decimal | None":
    """1-indexed 열 번호 → row tuple에서 값 추출 후 Decimal 변환."""
    if col_1indexed is None:
        return None
    idx = col_1indexed - 1
    if idx < 0 or idx >= len(row):
        return None
    return _to_decimal(row[idx])


# ── 정규화 메인 함수 ───────────────────────────────────────────────────────────

def normalize_pay_rate_example(
    example,                       # commission.models.RateExample 인스턴스
    normalize_mode: str = "replace",
) -> int:
    """
    지급률 xlsx → RateExamplePayRow 정규화.

    반환: 생성된 RateExamplePayRow 수 (0이면 대상 없음)

    호출 조건:
        example.insurer_type == "life"
        example.category     == "pay"
        original_name 확장자  == ".xlsx"

    normalize_mode:
        "replace": 기존 insurer_type=life&category=pay 행 전체 삭제 후 새 적재 (기본값)
        "append" : 기존 행 유지 후 신규 행만 추가
    """
    # 늦은 import — 순환 참조 방지
    from commission.models import RateExamplePayRow  # noqa: PLC0415

    if not example.file:
        logger.warning("pay normalizer: file field is empty. pk=%s", example.pk)
        return 0

    fname = str(example.original_name or "").lower()
    if not fname.endswith(".xlsx"):
        logger.info(
            "pay normalizer: skip non-xlsx file. pk=%s original_name=%s",
            example.pk, example.original_name,
        )
        return 0

    # ── Workbook 로드 (data_only=True로 수식 결과값 읽기) ──────────────────────
    wb = load_workbook(example.file.path, data_only=True, read_only=False)

    if TARGET_SHEET not in wb.sheetnames:
        logger.warning(
            "pay normalizer: target sheet '%s' not found. pk=%s sheets=%s",
            TARGET_SHEET, example.pk, wb.sheetnames,
        )
        wb.close()
        return 0

    ws = wb[TARGET_SHEET]
    # 최대 110행까지 읽음 (그룹4 5천만↑ 마지막 행 97 + 여유 13행)
    all_rows: list[tuple] = list(ws.iter_rows(min_row=1, max_row=110, values_only=True))
    wb.close()

    normalized: list = []

    # ── 일반 19개 보험사 처리 ──────────────────────────────────────────────────
    for (row_start, row_end), insurer_map in _GROUPS:
        for insurer_name, col_tuple in insurer_map.items():
            col_a, col_b, col_c, col_d, col_e, col_f = col_tuple
            coverage_carry: "str | None" = None

            for row_1idx in range(row_start, row_end + 1):
                r = all_rows[row_1idx - 1]

                # col4(index 3) = 상품군 셀. 공란이면 직전 값 이어받기 (병합셀 대응)
                raw_cov = r[3]
                if raw_cov:
                    coverage_carry = str(raw_cov).strip()

                coverage_type = COVERAGE_MAP.get(coverage_carry or "", coverage_carry or "")

                normalized.append(RateExamplePayRow(
                    source_file   = example,
                    source_sheet  = TARGET_SHEET,
                    source_row_no = row_1idx,
                    insurer_type  = example.insurer_type,
                    category      = "pay",
                    insurer       = insurer_name,
                    tier          = "5천만↑",
                    coverage_type = coverage_type,
                    col_a = _get_col(r, col_a),
                    col_b = _get_col(r, col_b),
                    col_c = _get_col(r, col_c),
                    col_d = _get_col(r, col_d),
                    col_e = _get_col(r, col_e),
                    col_f = _get_col(r, col_f),
                ))

    # ── IBK 전용 처리 ─────────────────────────────────────────────────────────
    # IBK는 상품군(col4) 대신 col32 자체 상품명을 coverage_type 키로 사용
    ibk_a, ibk_b, ibk_c, ibk_d, ibk_e, ibk_f = _IBK_COLS
    for row_1idx in range(_IBK_ROWS[0], _IBK_ROWS[1] + 1):
        r = all_rows[row_1idx - 1]
        raw_product = r[_IBK_PRODUCT_COL - 1]   # col32 → index 31
        if not raw_product:
            continue
        coverage_type = f"[IBK]{str(raw_product).strip()}"

        normalized.append(RateExamplePayRow(
            source_file   = example,
            source_sheet  = TARGET_SHEET,
            source_row_no = row_1idx,
            insurer_type  = example.insurer_type,
            category      = "pay",
            insurer       = "IBK",
            tier          = "5천만↑",
            coverage_type = coverage_type,
            col_a = _get_col(r, ibk_a),
            col_b = _get_col(r, ibk_b),
            col_c = _get_col(r, ibk_c),
            col_d = _get_col(r, ibk_d),
            col_e = _get_col(r, ibk_e),
            col_f = _get_col(r, ibk_f),
        ))

    # ── replace / append 모드 처리 ─────────────────────────────────────────────
    if normalize_mode == "replace":
        deleted_count, _ = RateExamplePayRow.objects.filter(
            insurer_type=example.insurer_type,
            category="pay",
        ).delete()
        logger.info(
            "pay normalizer: replace mode — deleted %d existing rows. pk=%s",
            deleted_count, example.pk,
        )

    if normalized:
        RateExamplePayRow.objects.bulk_create(normalized, batch_size=500)

    logger.info(
        "pay normalizer: created %d rows. pk=%s insurer_type=%s normalize_mode=%s",
        len(normalized), example.pk, example.insurer_type, normalize_mode,
    )
    return len(normalized)