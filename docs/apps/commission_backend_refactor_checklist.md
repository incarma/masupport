# django_ma commission 앱 백엔드 리팩토링 지침서 (최종완성본)

> 기준일: 2026-05-24
> 상태: 전 단계 완료 — P9 완료 (life parser 구현 이동 + backward shim 전환 완료)
> 기준 커밋: P9 완료 시점 기준 (refactor/p3-rate-normalizers-hardening 브랜치)

---

# 목차

1. 리팩토링 목표
2. 절대 보존 원칙
3. 완료 단계 목록
4. 현재 검증 기준
5. 현재 실제 파일 구조 (Source of Truth)
6. 계층별 역할 정리
7. 공통 helper 체계 (_common/)
8. PDF parser 체계
9. decimal.py 정책
10. text.py 정책
11. rows.py 정책
12. excel.py 정책
13. 생보 parser 현황
14. 손보 parser 현황
15. 정규화 진입점 (rate_example_normalizer.py)
16. 지급률 정규화 진입점 (rate_example_pay_normalizer.py)
17. Harness 체계
18. upload_utils 리팩토링
19. upload_handlers 리팩토링
20. Deposit 구조
21. Regression hardening
22. 금지 사항
23. 최종 DoD

---

# 1. 리팩토링 목표

commission 앱 백엔드의 기능 변화 없이 다음 목표를 달성한다.

- 중복 제거
- SSOT 강화
- parser 안정성 강화
- PDF parser fallback 안정화
- 업로드/다운로드 보안 유지
- 회귀 위험 최소화
- 테스트 및 Harness 기반 검증 체계 정착

---

# 2. 절대 보존 원칙

## 2-1. 기능 변화 금지

- 기존 URL / namespace 유지
- 기존 JSON 응답 구조 유지
- 기존 DOM / dataset 계약 유지
- 업로드 replace / append 의미 유지
- 환산율 / 수정률 / 지급률 계산 정책 유지

## 2-2. 보안 정책 유지

- `.file.url` 직접 노출 금지
- FileResponse / attachment 기반 다운로드만 허용
- token 다운로드 권한 유지
- CSRF 우회 추가 금지
- audit log 제거 금지

## 2-3. 저장 정책 유지

### 생명보험 환산율

Excel percent format → ×100 보정 유지

예시:
```python
0.7 + number_format "%"
→ Decimal("70")
```

### 손해보험 수정률

- raw 그대로 저장
- ×100 금지
- /100 금지

### 지급률

- 저장 시 `/0.97` 유지 (생보 / 손보 동일)

### 특수 보험사

- 처브 / 카디프: `% × 12` 유지
- 하나생명 / 흥국생명: PDF 좌표 기반 parser 유지
- 삼성손보: 병합셀 정책 (build_worksheet_value_map 기반) 유지
- KB생명: 일반상품 / 건강보험 product_kind 분기 유지
- 교보생명: 5-table parser 유지

---

# 3. 완료 단계 목록

```text
P2-1 upload_utils 정리              ✅ 완료
P2-2 upload_handlers 정리           ✅ 완료
P5 테스트 보강                      ✅ 완료
P3 저위험 parser 정리               ✅ 완료
P1-4 Deposit 구조 정리              ✅ 완료
P7-1 PDF helper 기초 구축           ✅ 완료
P7-2 Decimal/Text helper 안정화     ✅ 완료
P7-3 PDF parser 안정화              ✅ 완료
P7-4 Harness / lint 체계 강화       ✅ 완료
P7-5 Regression hardening           ✅ 완료
P7-6 rate_example 패키지화 + life shim 경로 생성   ✅ 완료
P7-6-fire fire parser 구현 이동     ✅ 완료
P8 life parser 구현 이동            ✅ 완료
    rate_example_normalizers/life_*.py 실구현 →
    rate_example/life/{insurer}/parser.py 로 이동
P9 backward shim 전환 + import 경로 최신화   ✅ 완료
    rate_example_normalizers/life_*.py → backward shim 전환
    rate_example_normalizer.py + __init__.py import 경로 최신화
P10 life_*.py backward shim 완전 제거        ✅ 완료
    rate_example_normalizers/life_*.py (19개) 삭제
    rate_example_normalizers/__init__.py → 최소 package marker로 교체
    외부 import surface 0건 확인 후 제거 (fire와 동일한 canonical 구조 달성)
P11 common helper canonical 경로 이전       ✅ 완료
    _common/ 실제 구현 → rate_example/common/ 로 이동
    rate_example/common/ 개별 모듈 shim → 실제 구현으로 교체
    rate_example/common/__init__.py → 로컬 import로 전환
    전체 parser + tests.py import 경로 최신화 (30개 파일)
    rate_example_normalizers/ 디렉토리 완전 삭제
```

남은 단계: **없음 — 전 단계 완료**

---

# 4. 현재 검증 기준

```text
python manage.py check                         ✅
python manage.py test commission               ✅ 46 tests OK
python manage.py makemigrations --check --dry-run ✅
bash scripts/harness/run_all.sh                ✅
```

---

# 5. 현재 실제 파일 구조

## 5-1. 전체 tree

```text
commission/services/
├── rate_example/                          # 신규 서비스 패키지
│   ├── __init__.py                        # RateExampleService 클래스 포함
│   │                                      # (기존 import 경로 호환 유지)
│   ├── common/                            # 공통 helper 실제 구현 위치
│   │   ├── __init__.py                    # 공통 export 목록
│   │   ├── decimal.py                     # Decimal 변환 helper
│   │   ├── excel.py                       # 병합 셀 helper
│   │   ├── pdf.py                         # PDF 추출 / PdfTextItem / fallback chain
│   │   ├── rows.py                        # 파일 내부 중복 방지
│   │   └── text.py                        # 텍스트 정규화
│   ├── fire/                              # 손해보험 parser (실제 구현 위치)
│   │   ├── __init__.py                    # 빈 파일
│   │   ├── aig/   parser.py              # AIG 수정률 PDF parser
│   │   ├── db/    parser.py              # DB손보 수정률 Excel parser
│   │   ├── hana/  parser.py              # 하나손보 수정률 PDF parser
│   │   ├── hanhwa/ parser.py             # 한화손보 수정률 Excel parser
│   │   ├── heungkuk/ parser.py           # 흥국화재 수정률 PDF parser
│   │   ├── hyundai/ parser.py            # 현대해상 수정률 Excel parser
│   │   ├── kb/    parser.py              # KB손보 수정률 Excel parser
│   │   ├── lotte/ parser.py              # 롯데손보 수정률 Excel parser
│   │   ├── meritz/ parser.py             # 메리츠화재 수정률 PDF parser
│   │   ├── nh/    parser.py              # 농협손보 수정률 Excel parser
│   │   ├── samsung/ parser.py            # 삼성화재 수정률 Excel parser
│   │   └── pay/   parser.py              # 손보 지급률 Excel parser
│   │                                      # (rate_example_pay_normalizer.py 경유)
│   └── life/                              # 생보 parser (실제 구현 위치)
│       ├── __init__.py
│       └── {insurer}/ parser.py          # 생보 parser 실제 구현
│                                          # (19개 보험사)
│
│
├── rate_example_normalizer.py            # 환산율/수정률 정규화 진입점
└── rate_example_pay_normalizer.py        # 지급률 정규화 진입점
```

## 5-2. 구조 요약

| 경로 | 역할 |
|---|---|
| `rate_example/__init__.py` | `RateExampleService` 클래스 (업로드/삭제/목록) |
| `rate_example/common/` | **공통 helper 실제 구현** |
| `rate_example/fire/{insurer}/parser.py` | **손보 parser 실제 구현** |
| `rate_example/fire/pay/parser.py` | **손보 지급률 parser 실제 구현** |
| `rate_example/life/{insurer}/parser.py` | **생보 parser 실제 구현** |
| `rate_example_normalizer.py` | 환산율/수정률 정규화 라우팅 진입점 |
| `rate_example_pay_normalizer.py` | 지급률 정규화 라우팅 진입점 |

---

# 6. 계층별 역할 정리

## 생보 import 경로

```text
실제 구현: commission/services/rate_example/life/{insurer}/parser.py
backward shim: 없음 (P10에서 life_*.py 삭제 완료)

정규화 진입점(rate_example_normalizer.py)은:
  rate_example.life.{insurer}.parser 에서 직접 import (실제 구현 경로)
```

## 손보 import 경로

```text
실제 구현: commission/services/rate_example/fire/{insurer}/parser.py
backward shim: 없음 (구 rate_example_normalizers/fire_*.py 파일 삭제됨)

정규화 진입점(rate_example_normalizer.py)은:
  rate_example.fire.{insurer}.parser 에서 직접 import (실제 구현 경로)
```

## 공통 helper import 경로

```text
실제 구현: commission/services/rate_example/common/{module}.py
canonical import: commission.services.rate_example.common

각 parser는 rate_example.common 경로만 사용
```

---

# 7. 공통 helper 체계 (rate_example/common/)

## 위치

```text
commission/services/rate_example/common/
├── __init__.py   — 전체 export 목록
├── decimal.py    — Decimal 변환 helper
├── excel.py      — 병합 셀 helper
├── pdf.py        — PDF 추출 / PdfTextItem / fallback chain
├── rows.py       — 파일 내부 중복 방지
└── text.py       — 텍스트 정규화
```

## canonical import

```text
commission.services.rate_example.common
```

---

# 8. PDF parser 체계 (_common/pdf.py)

## 핵심 구조체

```python
@dataclass(frozen=True)
class PdfTextItem:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
```

용도: 하나생명·흥국생명 PDF 좌표 기반 parser의 row grouping 기반

## 핵심 helper 함수

```python
extract_pdf_text_with_fallback(path: str) -> str
```

fallback 우선순위:

```text
1차: pdfplumber
2차: PyMuPDF (fitz)
3차: pypdf
```

- 1~2차 실패 → `logger.debug`
- 3차 실패 → `logger.exception` + raise

```python
extract_pdf_lines_with_pypdf(example) -> list[tuple[int, int, str]]
```

- `FieldFile.open("rb")` 기반 (`.file.url` 직접 접근 금지)
- 반환: `(page_no, line_no, text)` 튜플 목록

```python
group_pdf_items_by_y(items, *, y_tolerance=3.0) -> list[list[PdfTextItem]]
```

- y좌표 기준 row grouping
- tolerance 허용 범위 내 같은 행으로 묶음
- x0 기준 정렬

```python
clean_pdf_text(value) -> str
decimal_from_pdf_percent(value) -> Decimal | None
dedupe_by_key(items, key_fn) -> list
```

## 보안 원칙

- `.file.url` 직접 접근 금지
- `FieldFile.path` 또는 `FieldFile.open("rb")` 만 사용

---

# 9. decimal.py 정책

## 주요 함수

```python
decimal_from_text(value) -> Decimal | None
```

- comma 제거, percent 기호 제거, 공란/대시 → None

```python
decimal_percent_cell(cell, *, normalize_integral=False) -> Decimal | None
```

- Excel 셀 객체를 백분율 표시 Decimal로 변환
- `number_format`에 `%`가 있고 value가 숫자이면 ×100 보정
- 적용: `life_dongyang.py`, `life_met.py` 등

```python
decimal_percent_value(value, *, number_format="", ...) -> Decimal | None
```

- value + number_format을 분리 전달받는 버전
- 적용: `life_KDB.py` 등

## 저장 정책 요약

| 구분 | 정책 |
|---|---|
| 생보 환산율 (Excel percent format) | ×100 보정 저장 |
| 손보 수정률 | raw 그대로 저장 |
| 지급률 (생보/손보 공통) | raw ÷ 0.97 저장 |
| 처브/카디프 | PDF % × 12 |

---

# 10. text.py 정책

```python
clean_text(value) -> str       # 단순 str 변환, 줄바꿈 유지
clean_spaces(value) -> str     # 연속 공백/줄바꿈 1칸으로 축약
is_empty_like(value) -> bool   # 공란성 값 판정
EMPTY_LIKE_TEXTS = {"", "nan", "none", "-"}
```

- 상품명 병합 / 줄바꿈 처리 정책은 보험사별 parser가 개별 유지
- 단순 공백 normalize만 공통화

---

# 11. rows.py 정책

```python
append_unique(rows, seen, row, key) -> None
```

- 파일 내부 완전 중복 row 방지
- DB 기존 row 보존(append 업로드 의미)은 이 함수와 무관
- same-file 중복만 제거

---

# 12. excel.py 정책

```python
build_merged_value_map(ws) -> dict[tuple[int,int], Any]
cell_value_with_merged(ws, merged_map, row_no, col_no) -> Any
build_worksheet_value_map(ws, *, include_empty=True) -> dict[tuple[int,int], Any]
filled_value_above(values, *, header_row, row_no, col_no, is_filled) -> Any
```

- worksheet 자체를 unmerge 하거나 값 직접 쓰기 금지
- parser 내부 lookup 전용

| 함수 | 주요 사용처 |
|---|---|
| `build_merged_value_map` | `life_samsung.py` (병합셀 정책) |
| `build_worksheet_value_map` | `fire_samsung/parser.py` (병합셀 포함 전체 map) |
| `filled_value_above` | `fire_nh/parser.py` (공란 carry-up) |

---

# 13. 생보 parser 현황

## 실제 구현 위치

```text
commission/services/rate_example/life/{insurer}/parser.py
```

## backward shim

없음. `life_*.py` 파일은 P10에서 삭제됨 (fire와 동일한 canonical 구조).

## 보험사 목록 (19개)

| 보험사 | 파일 | 형식 | 특이사항 |
|---|---|---|---|
| ABL | life_abl.py | Excel | |
| DB | life_db.py | Excel | 13회/36회/37회 특수 계산식 |
| IM | life_im.py | Excel | |
| KB | life_kb.py | Excel | general / health product_kind 분기 |
| KDB | life_KDB.py | Excel | |
| 교보 | life_kyobo.py | Excel | 5-table parser |
| 농협 | life_nh.py | Excel | |
| 동양 | life_dongyang.py | Excel | |
| 라이나 | life_lina.py | Excel+PDF | Excel/PDF 분기 |
| 메트 | life_met.py | Excel | |
| 미래 | life_mirae.py | Excel | |
| 삼성 | life_samsung.py | Excel | 병합셀 정책 |
| 신한 | life_shinhan.py | Excel | scale_small_percent_text |
| 처브 | life_chubb.py | PDF | % × 12 |
| 카디프 | life_cardif.py | PDF | % × 12 |
| 푸본현대 | life_fubon.py | PDF | |
| 하나 | life_hana.py | PDF | 좌표 기반 parser |
| 한화 | life_hanhwa.py | Excel | product_kind 분기 (whole/annuity/general) |
| 흥국 | life_heungkuk.py | PDF | 좌표 기반 parser |

## rate_example_normalizers/__init__.py export 목록

```python
# 생보 함수만 export (손보 함수는 없음)
build_life_abl_conversion_rows
build_life_db_conversion_rows
build_life_im_conversion_rows
build_life_kb_general_conversion_rows
build_life_kb_health_conversion_rows
build_life_kdb_conversion_rows
build_life_kyobo_conversion_rows
build_life_nh_conversion_rows
build_life_dongyang_conversion_rows
build_life_lina_conversion_rows
build_life_lina_pdf_conversion_rows
build_life_met_conversion_rows
build_life_shinhan_conversion_rows
build_life_chubb_pdf_conversion_rows
build_life_cardif_pdf_conversion_rows
build_life_mirae_conversion_rows
build_life_samsung_conversion_rows
build_life_fubon_pdf_conversion_rows
build_life_hana_pdf_conversion_rows
build_life_heungkuk_pdf_conversion_rows
build_life_hanhwa_conversion_rows
```

---

# 14. 손보 parser 현황

## 실제 구현 위치

```text
commission/services/rate_example/fire/{insurer}/parser.py
```

## backward shim

없음. 구 `rate_example_normalizers/fire_*.py` 파일은 삭제됨.

## 수정률 conv parser (11개)

| 보험사 | 디렉터리 | 형식 | 특이사항 |
|---|---|---|---|
| AIG | fire/aig/ | PDF | fallback chain 사용, 판매종료 제외, 자동갱신 pay_period |
| DB | fire/db/ | Excel | |
| KB | fire/kb/ | Excel | |
| 농협 | fire/nh/ | Excel | filled_value_above 사용 |
| 롯데 | fire/lotte/ | Excel | build_worksheet_value_map 사용 |
| 메리츠 | fire/meritz/ | PDF | fallback chain 사용 |
| 삼성 | fire/samsung/ | Excel | 병합셀 정책, build_worksheet_value_map 사용 |
| 하나 | fire/hana/ | PDF | |
| 한화 | fire/hanhwa/ | Excel | |
| 현대 | fire/hyundai/ | Excel | |
| 흥국 | fire/heungkuk/ | PDF | |

## 지급률 pay parser (1개, 별도 경로)

```text
commission/services/rate_example/fire/pay/parser.py
→ rate_example_pay_normalizer.py 경유 (rate_example_normalizer.py 아님)
```

- 대상 시트: `① 5천만,3천만↑`
- 대상 구간: `5천만↑` 만 정규화
- 저장: `insurer_type="fire"`, `category="pay"`
- 지급률 저장 정책: raw ÷ 0.97 (생보 지급률과 동일)

---

# 15. 정규화 진입점 (rate_example_normalizer.py)

## import 구조

```python
# 생보 import — rate_example/life/ 실제 구현 경로
from commission.services.rate_example.life.abl.parser import build_life_abl_conversion_rows
from commission.services.rate_example.life.db.parser import build_life_db_conversion_rows
...

# 손보 import — rate_example/fire/ 실제 구현 경로
from commission.services.rate_example.fire.db.parser import build_fire_db_conversion_rows
from commission.services.rate_example.fire.kb.parser import build_fire_kb_conversion_rows
from commission.services.rate_example.fire.nh.parser import build_fire_nh_conversion_rows
from commission.services.rate_example.fire.samsung.parser import build_fire_samsung_conversion_rows
from commission.services.rate_example.fire.lotte.parser import build_fire_lotte_conversion_rows
from commission.services.rate_example.fire.hanhwa.parser import build_fire_hanhwa_conversion_rows
from commission.services.rate_example.fire.hyundai.parser import build_fire_hyundai_conversion_rows
from commission.services.rate_example.fire.aig.parser import build_fire_aig_pdf_conversion_rows
from commission.services.rate_example.fire.hana.parser import build_fire_hana_pdf_conversion_rows
from commission.services.rate_example.fire.meritz.parser import build_fire_meritz_pdf_conversion_rows
from commission.services.rate_example.fire.heungkuk.parser import build_fire_heungkuk_conversion_rows
```

## 지원 대상 (env_type별)

### 생보 conv 대상

```python
{"ABL", "DB", "IM", "KB", "KDB", "교보", "농협", "동양",
 "라이나", "메트", "미래", "삼성", "신한", "처브", "카디프",
 "푸본현대", "하나", "한화", "흥국"}
```

### 손보 conv 대상

```python
{"AIG", "DB", "KB", "농협", "롯데", "메리츠", "삼성", "하나", "한화", "현대", "흥국"}
```

## 레거시 insurer_type 처리

```python
LEGACY_FIRE_TYPE = "nonlife"

def _effective_insurer_type(value: str) -> str:
    raw = str(value or "").strip()
    return RateExample.TYPE_FIRE if raw == LEGACY_FIRE_TYPE else raw
```

- 구 `nonlife` 타입을 현재 `fire` SSOT로 보정
- replace 모드 삭제 시 `fire` / `nonlife` 혼재 row 함께 정리

## 0건 방어

```python
_raise_if_supported_but_empty(...)
```

- 지원 대상인데 정규화 결과 0건이면 ValueError 발생
- transaction.atomic()이 rollback 보장

---

# 16. 지급률 정규화 진입점 (rate_example_pay_normalizer.py)

```python
# 손보 지급률 parser
from commission.services.rate_example.fire.pay.parser import build_fire_pay_rows
```

- 생보 지급률: 동일 파일 내에서 직접 처리 (컬럼 매핑 방식)
- 손보 지급률: `fire/pay/parser.py`에 위임
- 지급률 저장값 = raw ÷ 0.97 (생보/손보 동일)

---

# 17. Harness 체계

## 스크립트 위치

```text
scripts/harness/run_all.sh          — 전체 lint 순차 실행
scripts/harness/security_lint.sh    — 보안 위반 탐지
scripts/harness/quality_lint.sh     — 코드 품질 위반 탐지
scripts/harness/celery_check.sh     — Celery task 이름 정합성
scripts/harness/css_scope_check.sh  — CSS 스코프 위반 탐지
```

## run_all.sh 역할

- 4개 스크립트 순서대로 실행
- 결과를 `docs/audit/lint_result_YYYYMMDD.txt` 에 저장
- 하나라도 실패 시 `exit 1`
- 커밋 전 검증 기준

## security_lint.sh 점검 항목

- CSRF exempt 사용 탐지
- `.file.url` 직접 노출 탐지
- log_action 미호출 패턴 탐지
- audit 상수 미정의 사용 탐지

## quality_lint.sh 점검 항목

| 규칙 | 설명 | 차단 여부 |
|---|---|---|
| Q-01 | CSRF 토큰 재구현 (getCSRFToken SSOT 위반) | ❌ 차단 |
| Q-02a | 앱 CSS `:root` 전역 변수 선언 | ❌ 차단 |
| Q-02b | commission.css 전역 클래스 선언 | ❌ 차단 |
| Q-03 | commission/views/ JSON 응답 helper 중복 정의 | ❌ 차단 |
| URL-01 | JS 내 Django 앱 경로 하드코딩 | ❌ 차단 |
| BF-01 | IIFE BFCache 가드(dataset.inited) 누락 | ⚠️ 경고만 |
| EX-01 | except: pass 예외 삼키기 | ❌ 차단 |
| RN-01 | normalizer 위험 연산 패턴 (`* 100` 등) | ⚠️ 경고만 |
| RN-02 | PDF extractor 중복 구현 후보 | ⚠️ 경고만 |

## celery_check.sh 점검 항목

- `@shared_task(name=...)` 등록명과 `beat_schedule` `"task"` 값 정합성

## css_scope_check.sh 점검 항목

- CSS 파일 스코프 루트 선택자 준수

## 결과 저장

```text
docs/audit/lint_result_YYYYMMDD.txt
```

---

# 18. upload_utils 리팩토링

## 파일 구조

```text
commission/upload_utils/
├── _convert.py      — 타입 변환 helper
├── _detect.py       — 컬럼 탐지
├── _readers.py      — 파일 reader (xlsx/xls fallback)
├── _db.py           — DB 저장 helper
├── __init__.py      — public API export
└── upload_utils.py  — 레거시 shim 유지
```

## 보존 정책

- `_norm_emp_id()` 사번 정규화 유지
- `_extract_emp7_from_a()` 유지
- pandas isna 방어 유지
- import surface 유지

---

# 19. upload_handlers 리팩토링

## 파일 구조

```text
commission/upload_handlers/
├── approval.py    — 결재 업로드
├── efficiency.py  — 능률 업로드
├── collect.py     — 채권 업로드
├── deposit.py     — 입금 업로드
└── registry.py    — registry SSOT
```

## 보존 정책

- raw matrix 위치 기반 parser 유지
- `bulk_create(update_conflicts=True)` 유지
- `registry` `upload_type` 유지

---

# 20. Deposit 구조

## 신규 구조

```text
commission/services/deposit.py
commission/services/deposit_serializers.py
commission/views/api_deposit_impl.py
```

## 완료 사항

- serializer 책임 분리
- aggregate helper 분리
- dataclass 도입
- API 응답 계약 유지 (deposit_home.js alias / 기존 JSON key 유지)

---

# 21. Regression hardening

## 테스트 기준

```text
46 tests OK
python manage.py test commission
```

## 강화 영역

- PDF helper
- Decimal helper
- upload token
- Deposit serializer
- parser helper
- fail download permission

## 회귀 방지 목표

- 저장값 동일
- row count 동일
- upload 결과 동일
- 계산 결과 동일

---

# 22. 금지 사항

## 절대 금지

- `.file.url` 직접 노출
- row-by-row `save()` (bulk_create 사용)
- `Decimal` → `float` 변경
- parser 의미 통합 (보험사별 정책 각자 유지)
- 보험사 canonical 값 변경
- 지급률 `/0.97` 제거
- 손보 수정률에 `×100` 적용
- 생보 환산율 `×100` 보정 제거
- `_common/` helper 내 보험사별 특수 정책 강제 통합

---

# 23. 최종 DoD

## 코드 구조

- public import surface 유지
- fire: `rate_example/fire/{insurer}/parser.py` canonical
- life: `rate_example/life/{insurer}/parser.py` canonical
- common helper: `rate_example/common/` canonical
- rate_example_normalizers/ 디렉토리 완전 삭제
- backward shim 없음 (life_*.py / fire_*.py / _common 모두 삭제)
- parser 정책 보존

## 보안

- 다운로드 권한 유지
- URL 직접 노출 없음
- CSRF 유지
- audit log 유지

## 성능

- `bulk_create` 유지 (batch_size=500)
- parser 성능 유지

## 회귀

- 46 tests OK
- run_all.sh 통과
- migration 없음
- parser row count 유지

---

# 24. 다음 작업

```text
모든 단계 완료. 다음 작업은 별도 기획에 따른다.
```

---

# 25. 최종 요약 (2026-05-24 기준)

commission 백엔드 리팩토링은 다음 상태다.

```text
저위험 구조 정리 완료
upload 체계 안정화 완료
PDF parser 공통 기반 구축 완료
Harness / lint 체계 정착 완료
Regression hardening 완료
rate_example 패키지화 완료
fire parser 구현 이동 완료 (구 fire_*.py 파일 삭제)
life parser 구현 이동 완료 (rate_example/life/{insurer}/parser.py 로 이동)
life_*.py backward shim 전환 완료
rate_example_normalizer.py + __init__.py import 경로 최신화 완료
life_*.py backward shim 완전 제거 완료 (fire와 동일한 canonical 구조 달성)
```

검증 결과:

```text
python manage.py check                         ✅
python manage.py test commission               ✅ 46 tests OK
python manage.py makemigrations --check --dry-run ✅
bash scripts/harness/run_all.sh                ✅
```
