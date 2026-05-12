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
from commission.services.rate_example_normalizers.life_nh import (
    build_life_nh_conversion_rows,
)
from commission.services.rate_example_normalizers.life_dongyang import (
    build_life_dongyang_conversion_rows,
)
from commission.services.rate_example_normalizers.life_lina import (
    build_life_lina_conversion_rows,
    build_life_lina_pdf_conversion_rows,
)
from commission.services.rate_example_normalizers.life_met import (
    build_life_met_conversion_rows,
)
from commission.services.rate_example_normalizers.life_shinhan import (
    build_life_shinhan_conversion_rows,
)
from commission.services.rate_example_normalizers.life_chubb import (
    build_life_chubb_pdf_conversion_rows,
)
from commission.services.rate_example_normalizers.life_cardif import (
    build_life_cardif_pdf_conversion_rows,
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
    - 생명보험 / 환산율·수정률 / 라이나 / xlsx
    - 생명보험 / 환산율·수정률 / 라이나 / pdf

    반환:
    - 생성된 RateExampleConversionRow 수
    """
    normalize_mode = (normalize_mode or "replace").strip()
    if normalize_mode not in {"replace", "append"}:
        raise ValueError(f"Invalid normalize_mode: {normalize_mode}")
    
    # ── 지급률 정규화 분기 (category == "pay") ────────────────────────────────
    # conv 오케스트레이터와 완전 격리. pay 파일이 이 분기에서 처리되면 즉시 반환한다.
    if example.category == RateExample.CAT_PAY:
        from commission.services.rate_example_pay_normalizer import (  # noqa: PLC0415
            normalize_pay_rate_example,
        )
        return normalize_pay_rate_example(example, normalize_mode=normalize_mode)

    if not (
        example.insurer_type == RateExample.TYPE_LIFE
        and example.category == RateExample.CAT_CONV
        and example.insurer in {"ABL", "DB", "IM", "KB", "KDB", "교보", "농협", "동양", "라이나", "메트", "신한", "처브", "카디프"}  # conv 대상 보험사
    ):
        return 0

    if not example.file:
        return 0

    original_name = str(example.original_name or "").lower()

    # ─────────────────────────────────────────────────────
    # 라이나 PDF 전용 정규화
    # - 기존 xlsx parser와 완전 분리
    # - 다른 보험사 PDF는 원본 보관만 수행
    # - PDF는 병합 셀 정보가 없으므로 텍스트 흐름 기반으로 행을 복원
    # ─────────────────────────────────────────────────────
    if original_name.endswith(".pdf"):
        # ── 처브 PDF 전용 정규화 ─────────────────────────────────────────
        # - 주계약 페이지만 정규화
        # - "특약" 섹션 감지 시 해당 페이지와 이후 페이지 제외
        # - 환산율은 raw % 값에 12를 곱해 1~4차년에 동일 저장
        if example.insurer == "처브":
            normalized_rows = build_life_chubb_pdf_conversion_rows(example)

            if normalize_mode == "replace":
                RateExampleConversionRow.objects.filter(
                    insurer_type=example.insurer_type,
                    category=example.category,
                    insurer=example.insurer,
                ).delete()

            if normalized_rows:
                RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

            return len(normalized_rows)
        
        # ── 카디프 PDF 전용 정규화 ───────────────────────────────────────
        # - 주계약 영역만 정규화
        # - "□ 특약" 이후 테이블 제외
        # - PDF raw % 값에 12를 곱해 year1~year4에 저장
        if example.insurer == "카디프":
            normalized_rows = build_life_cardif_pdf_conversion_rows(example)

            if normalize_mode == "replace":
                RateExampleConversionRow.objects.filter(
                    insurer_type=example.insurer_type,
                    category=example.category,
                    insurer=example.insurer,
                ).delete()

            if normalized_rows:
                RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

            return len(normalized_rows)
        
        if example.insurer != "라이나":
            return 0

        normalized_rows = build_life_lina_pdf_conversion_rows(example)

        if normalize_mode == "replace":
            RateExampleConversionRow.objects.filter(
                insurer_type=example.insurer_type,
                category=example.category,
                insurer=example.insurer,
            ).delete()

        if normalized_rows:
            RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)

        return len(normalized_rows)

    # 그 외 기존 보험사는 xlsx만 정규화한다.
    if not original_name.endswith(".xlsx"):
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

    # ── 농협 생명 환산율/수정률 정규화 ─────────────────────────────
    elif example.insurer == "농협":
        normalized_rows.extend(build_life_nh_conversion_rows(example, wb))

    # ── 동양 생명 환산율/수정률 정규화 ─────────────────────────────
    # 동양생명 GA raw 예시표 정규화
    # - 대상 시트: 주계약
    # - 제외: 1~14행 헤더/안내 영역
    # - J열: 1차년, L열: 2~4차년
    elif example.insurer == "동양":
        normalized_rows.extend(build_life_dongyang_conversion_rows(example, wb))

    # ── 라이나 생명 환산율/수정률 정규화 ─────────────────────────────
    # 라이나 규칙:
    # - 병합 셀 값을 row 단위로 전파한 뒤 정규화
    # - raw "구분" 영역 첫 번째 컬럼 → 상품명
    # - raw "구분" 영역 마지막 컬럼 → 납기
    # - 납기에 "년납" 포함 행만 정규화
    # - 환산율 값을 1~4차년에 동일 반영
    elif example.insurer == "라이나":
        normalized_rows.extend(build_life_lina_conversion_rows(example, wb))

    # ── 메트 생명 환산율/수정률 정규화 ─────────────────────────────
    # - 대상 시트: 주계약 CSC
    # - 상품명(C), 납기(E), 보험료(F)/가입금액(G), 1~4차년(K~N) 매핑
    elif example.insurer == "메트":
        normalized_rows.extend(build_life_met_conversion_rows(example, wb))
    
    # ── 신한 생명 환산율/수정률 정규화 ─────────────────────────────
    # 신한 규칙:
    # - "일반상품" 포함 시트: C6~J6 헤더, 7행부터 1Y(H열) 마지막 데이터까지
    # - 상품명(C) 공란은 직전 상품명으로 전파
    # - 구분(D/E)은 콤마+공백으로 결합, 둘 다 공란이면 동일 상품명 내 직전 구분 전파
    # - 납기(F), 1~3차년(H~J), 4차년 없음
    # - "건강" 포함 시트: A8~J8 헤더, A열이 "주보험"인 행만 정규화
    elif example.insurer == "신한":
        normalized_rows.extend(build_life_shinhan_conversion_rows(example, wb))

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