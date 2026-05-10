# commission/services/rate_example_normalizer.py
from __future__ import annotations

"""
RateExample 정규화 서비스.

역할:
- 업로드된 예시표 원본 파일을 보험사별 규칙에 따라 정규화 테이블로 적재한다.
- 현재 지원 대상: 생명보험 / 환산율·수정률 / ABL, DB
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
    build_life_kb_health_conversion_rows,
)
from commission.services.rate_example_normalizers.life_KDB import (
    build_life_kdb_conversion_rows,
)
from commission.services.rate_example_normalizers.life_kyobo import (
    build_life_kyobo_conversion_rows,
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
    - 생명보험 / 환산율·수정률 / ABL / xlsx
    - 생명보험 / 환산율·수정률 / DB / xlsx
    - 생명보험 / 환산율·수정률 / IM / xlsx
    - 생명보험 / 환산율·수정률 / KB / 일반상품 / xlsx
    - 생명보험 / 환산율·수정률 / KB / 건강보험 / xlsx
    - 생명보험 / 환산율·수정률 / KDB / xlsx
    - 생명보험 / 환산율·수정률 / 교보 / xlsx

    반환:
    - 생성된 RateExampleConversionRow 수
    """
    normalize_mode = (normalize_mode or "replace").strip()
    if normalize_mode not in {"replace", "append"}:
        raise ValueError(f"Invalid normalize_mode: {normalize_mode}")

    if not (
        example.insurer_type == RateExample.TYPE_LIFE
        and example.category == RateExample.CAT_CONV
        and example.insurer in {"ABL", "DB", "IM", "KB", "KDB", "교보"}
    ):
        return 0

    if not example.file:
        return 0

    # 정규화 대상은 xlsx 기준이다. xls/pdf는 원본 보관만 수행한다.
    if not str(example.original_name or "").lower().endswith(".xlsx"):
        return 0

    # ─────────────────────────────────────────────────────
    # 병합 셀 지원 필요
    #
    # KDB 정규화는:
    # - 상품명(C열) 병합
    # - 납기(H열) 병합
    # 정보를 읽어야 한다.
    #
    # openpyxl ReadOnlyWorksheet는 merged_cells를 지원하지 않으므로
    # read_only=False 로 workbook을 로드한다.
    #
    # 현재 예시표 파일 크기(수 MB 수준)에서는
    # 메모리 부담보다 정규화 정확성이 우선이다.
    # ─────────────────────────────────────────────────────
    wb = load_workbook(
        example.file.path,
        data_only=True,
        read_only=False,
    )

    normalized_rows: list[RateExampleConversionRow] = []

    # ── ABL 생명 환산율/수정률 정규화 ─────────────────────────────
    # 보험사별 parser는 rate_example_normalizers/life_*.py에 둔다.
    # 이 파일은 workbook 로드, 보험사 분기, 기존 master 교체만 담당한다.
    if example.insurer == "ABL":
        normalized_rows.extend(build_life_abl_conversion_rows(example, wb))

    # ── DB 생명 환산율/수정률 정규화 ──────────────────────────────
    # DB 규칙:
    # - 특약/방카교차 시트 제외
    # - 각 시트 첫 번째 테이블만 정규화
    # - 상품명은 A1, 보종은 상품명 기반 판정
    elif example.insurer == "DB":
        normalized_rows.extend(build_life_db_conversion_rows(example, wb))

    # ── IM 생명 환산율/수정률 정규화 ──────────────────────────────
    # IM 규칙:
    # - 첫 번째 시트 "(총괄)환산성적표"만 사용
    # - E열 구분 == "주계약"인 행만 정규화
    # - L열 기본형 값을 1~4차년에 동일 반영
    elif example.insurer == "IM":
        normalized_rows.extend(build_life_im_conversion_rows(example, wb))

    # ── KB 생명 환산율/수정률 정규화 ──────────────────────────────
    # KB 일반상품 규칙:
    # - "(주계약)"으로 표시된 테이블만 사용
    # - "(특약)" 테이블은 제외
    # - B/C/D/E/F/G/H/I/K 열 매핑
    elif example.insurer == "KB":
        if product_kind == "general":
            normalized_rows.extend(build_life_kb_general_conversion_rows(example, wb))
        elif product_kind == "health":
            normalized_rows.extend(build_life_kb_health_conversion_rows(example, wb))
        else:
            return 0
        
    # ── KDB 생명 환산율/수정률 정규화 ─────────────────────────────
    # KDB 규칙:
    # - "GA 주계약" 시트만 사용
    # - 1~3행 제외, 4행부터 정규화
    # - 상품명(C), 납기(H), 연령/기준(I), 변경후(K) 열 매핑
    # - 구분(plan_type)은 공란 저장
    # - 병합된 상품명/납기는 행별 값으로 전파
    # - 상품명+구분+납기 기준 중복 제거
    # - 변경후(K) 값을 1~4차년에 동일 반영
    elif example.insurer == "KDB":
        normalized_rows.extend(build_life_kdb_conversion_rows(example, wb))
    
    # ── 교보 생명 환산율/수정률 정규화 ─────────────────────────────
    # 교보 규칙:
    # - "주계약(종속특약포함)" 시트만 사용
    # - 1~3행 제외
    # - 판매중지 상품 제외
    # - 상품명 공란 시 직전 유효 상품명 전파
    # - 총환산월초 값을 1~4차년에 동일 반영
    elif example.insurer == "교보":
        normalized_rows.extend(build_life_kyobo_conversion_rows(example, wb))

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