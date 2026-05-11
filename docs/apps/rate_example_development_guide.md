# django_ma 수수료 예시표(RateExample) 개발 가이드 FINAL (동양 포함 리팩토링)

> 목적:
>
> 추후 전체 세부 코드를 다시 제공하지 않아도,
> 수수료 예시표 기능의 구조·계약·정규화 정책·보험사별 parser 구조를
> 빠르게 이해하고 안전하게 디벨롭할 수 있도록 정리한 FINAL 기준 문서입니다.
>
> 기준일: 2026-05-11
>
> 최신 반영 (이번 버전):
>
> * 동양생명 정규화 FINAL
> * 동양 대상 시트 정책: `주계약` only
> * 동양 raw 제외 정책: 1~14행 제외, 15행부터 데이터 처리
> * 동양 컬럼 매핑 정책: B/C/G/J/L열 기준
> * 동양 보종 판정 정책: 종신/연금/기타(보장성)
> * 동양 함수명 SSOT: `build_life_dongyang_conversion_rows`
> * 동양 legacy alias 정책: `build_dongyang_conversion_rows`
> * dispatcher / parser 구조 / 회귀 체크리스트 보강
>
> 이전 반영 내역:
>
> * 교보 생명 정규화 FINAL (5개 테이블)
> * 교보 공통 헬퍼 리팩토링 (_parse_table / _resolve_product / _make_row)
> * 서브타입 키워드 판정 정책 (_is_subtype_keyword 강화)
> * 판매중지/특약 제외 정책 통일 (_should_exclude)
> * 교보 parser 구조 SSOT 추가
> * 회귀 체크리스트 보강
>
> * IM 생명 정규화 FINAL
> * KB 생명 일반상품 정규화 FINAL
> * KB 건강보험 정규화 FINAL
> * KDB 생명 정규화 FINAL
> * normalize_mode(replace/append) 정책
> * 환산율 % 저장 정책 통일
> * Excel 백분율 셀 보정 정책
> * 전략상품 저장 정책
> * 생보 전용 업로드 UI 전환
> * parser dispatcher 구조 SSOT
> * 병합 셀 전파 정책
> * KDB dedupe 정책

---

# 1. 기능 개요

수수료 예시표 기능은 보험사 raw 예시표 파일을 업로드하고,
보험사별 parser를 통해 표준 정규화 테이블로 변환하여
조회/검색/전략상품 관리/향후 계산 엔진에 사용하는 기능이다.

핵심 책임:

1. 원본 파일 업로드
2. 파일 검증
3. 보험사별 xlsx 정규화
4. 정규화 데이터 조회
5. 전략상품 저장
6. 업로드/다운로드/삭제 audit
7. 계산 엔진용 표준 환산율 데이터 구축

---

# 2. URL 계약

파일:

```text
commission/urls.py
```

기존 URL name 변경 금지.

| URL name                                           | 역할      |
| -------------------------------------------------- | ------- |
| commission:rate_example_home                       | 메인      |
| commission:rate_example_upload                     | 업로드     |
| commission:rate_example_download                   | 원본 다운로드 |
| commission:rate_example_delete                     | 삭제      |
| commission:rate_example_conversion_list            | 정규화 조회  |
| commission:rate_example_conversion_strategy_update | 전략상품 저장 |

원칙:

* 보험사 추가 시 URL 추가 금지
* parser만 추가
* 기존 URL name 변경 금지

---

# 3. 모델 구조

## 3.1 RateExample

원본 파일 메타.

주요 필드:

* insurer_type
* category
* insurer
* file
* original_name
* uploaded_by
* created_at

보안 원칙:

금지:

```django
{{ example.file.url }}
```

허용:

```python
open_fileresponse_from_fieldfile(...)
```

---

## 3.2 RateExampleConversionRow

정규화 master 테이블.

주요 필드:

* source_file
* source_sheet
* source_row_no
* insurer_type
* category
* insurer
* coverage_type
* strategy_flag
* product_name
* plan_type
* pay_period
* year1~year4

---

# 4. 환산율 저장 정책 FINAL

## 매우 중요

현재 모든 보험사는
"백분율 수치 기준"으로 저장한다.

예:

| raw 표시 | DB 저장            |
| ------ | ---------------- |
| 100.0% | Decimal("100.0") |
| 336.0% | Decimal("336.0") |
| 126%   | Decimal("126")   |

즉:

```python
100% == Decimal("100")
```

이지:

```python
100% == Decimal("1.0")
```

가 아니다.

---

# 5. 화면 출력 정책

환산율 확인 모달에서는:

```text
336.0%
126%
100.0%
```

형태로 출력한다.

즉:

* DB 저장값 = 숫자
* UI 표시값 = `%` 포함 문자열

---

# 6. Excel 백분율 셀 처리 정책

raw Excel 셀이:

```text
336.0%
```

처럼 보이더라도,
openpyxl은 실제값을:

```python
3.36
```

으로 읽을 수 있다.

따라서 parser에서는:

```python
if "%" in number_format:
    value *= 100
```

형태로 보정 후 저장한다.

최종 저장:

```python
Decimal("336.0")
```

---

# 7. normalize_mode 정책 FINAL

업로드 모달에는:

```text
기존 데이터 초기화 여부
```

옵션이 존재한다.

---

## replace

```text
기존 데이터를 초기화하고 새 데이터를 업데이트 합니다.
```

동작:

* 동일 insurer_type/category/insurer row 전체 삭제
* 신규 bulk_create

기존 정책 유지.

---

## append

```text
기존 데이터에 새 데이터를 추가합니다.
```

동작:

* 기존 row 유지
* 신규 row만 append

주의:

* dedupe 없음
* 동일 상품 중복 가능

---

# 8. 정규화 오케스트레이터

파일:

```text
commission/services/rate_example_normalizer.py
```

역할:

* workbook load
* 보험사 parser dispatch
* replace/append 처리
* bulk_create

현재 지원:

| insurer | 지원 |
| ------- | -- |
| ABL     | O  |
| DB      | O  |
| IM      | O  |
| KB      | O  |
| KDB     | O  |
| 교보      | O  |
| 동양      | O  |

---

## workbook load 정책 FINAL

KDB 병합 셀 처리를 위해:

```python
read_only=False
```

고정 사용.

금지:

```python
load_workbook(..., read_only=True)
```

이유:

```python
ReadOnlyWorksheet has no merged_cells
```

병합 셀 API 미지원.

---

## 현재 dispatcher 구조

```python
if example.insurer == "ABL":
    ...
elif example.insurer == "DB":
    ...
elif example.insurer == "IM":
    ...
elif example.insurer == "KB":
    ...
elif example.insurer == "KDB":
    ...
elif example.insurer == "교보":
    ...
elif example.insurer == "동양":
    ...
```

---

# 9. parser 구조 SSOT

구조:

```text
commission/services/rate_example_normalizers/
├── life_abl.py
├── life_db.py
├── life_im.py
├── life_kb.py
├── life_KDB.py
├── life_kyobo.py
└── life_dongyang.py
```

원칙:

* 보험사별 parser는 life_*.py만 담당
* rate_example_normalizer.py는 dispatcher만 담당
* legacy parser/helper 유지 금지

---

# 10. KB 일반상품 정규화 FINAL

파일:

```text
life_kb.py
```

---

## 10.1 대상

| 조건           | 값       |
| ------------ | ------- |
| insurer_type | life    |
| category     | conv    |
| insurer      | KB      |
| product_kind | general |
| 파일           | .xlsx   |

---

## 10.2 raw 제외 정책

raw 1~4행은 정규화 제외.

```python
for row_no in range(5, ...)
```

---

## 10.3 특약 제외 정책 FINAL

상품명(B열)에:

```text
특약
```

문구가 포함된 행은 제외.

```python
if "특약" in product_name:
    continue
```

---

## 10.4 보종 판정 FINAL

| 조건    | coverage_type |
| ----- | ------------- |
| 변액 포함 | 변액연금          |
| 연금 포함 | 연금            |
| 경영 포함 | CEO정기         |
| 정기 포함 | 종신/CI         |
| 기타    | 종신/CI         |

---

## 10.5 컬럼 매핑

| 정규화 필드       | raw       |
| ------------ | --------- |
| product_name | B열        |
| pay_period   | C열        |
| plan_type    | D/E/K열 조합 |
| year1        | F열        |
| year2        | G열        |
| year3        | H열        |
| year4        | I열        |

---

# 11. KB 건강보험 정규화 FINAL

파일:

```text
life_kb.py
```

---

## 11.1 대상

| 조건           | 값      |
| ------------ | ------ |
| insurer_type | life   |
| category     | conv   |
| insurer      | KB     |
| product_kind | health |
| 파일           | .xlsx  |

---

## 11.2 핵심 정책

* workbook 내 모든 시트 사용
* 각 시트 1~3행 제외
* B열 구분값에 "특약" 포함 시 해당 행부터 하단 전체 제외
* 보험사 컬럼은 강제로 KB 저장
* 보종은 강제로 기타(보장성) 저장

---

## 11.3 특약 차단 정책 FINAL

B열:

```text
특약
```

문구가 발견되는 행부터:

```python
break
```

즉:

* 특약 행 포함
* 특약 하단 전체 제외

---

## 11.4 상품명/구분 파싱 정책

raw 상품(C열):

```text
KB암보험(기본형)(무해약형)
```

정규화 결과:

| 필드           | 값         |
| ------------ | --------- |
| product_name | KB암보험     |
| plan_type    | 기본형, 무해약형 |

---

## 11.5 컬럼 매핑

| 정규화 필드       | raw     |
| ------------ | ------- |
| product_name | C열 괄호 밖 |
| plan_type    | C열 괄호 안 |
| pay_period   | D열      |
| year1        | E열      |
| year2        | F열      |
| year3        | G열      |
| year4        | H열      |

---

# 12. KDB 생명 정규화 FINAL

파일:

```text
commission/services/rate_example_normalizers/life_KDB.py
```

---

## 12.1 대상

| 조건           | 값     |
| ------------ | ----- |
| insurer_type | life  |
| category     | conv  |
| insurer      | KDB   |
| 파일           | .xlsx |

---

## 12.2 대상 시트

반드시 아래 시트만 사용:

```text
GA 주계약
```

다른 시트는 모두 무시.

---

## 12.3 raw 제외 정책

1~3행 제외:

```python
for row_no in range(4, ...)
```

---

## 12.4 병합 셀 처리 FINAL

KDB raw는:

* 상품명(C열)
* 납기(H열)

가 병합되어 여러 행을 점유한다.

openpyxl은 병합 범위 첫 셀만 값을 보유하므로,
반드시 병합값 전파 로직 필요.

예:

| row | C열            |
| --- | ------------- |
| 7   | 버팀목New케어보험(무) |
| 8   | 빈값            |
| 9   | 빈값            |

정규화 결과:

| row | 상품명           |
| --- | ------------- |
| 7   | 버팀목New케어보험(무) |
| 8   | 버팀목New케어보험(무) |
| 9   | 버팀목New케어보험(무) |

---

## 12.5 각 행 독립 상품 처리 정책

병합 상품명이어도:

* 구분
* 납기

가 다르면 서로 다른 상품으로 본다.

즉:

```text
상품명 동일 != 같은 상품
```

이다.

---

## 12.6 구분(plan_type) 정책 FINAL

KDB는:

```python
plan_type = ""
```

고정.

즉:

* D열 구분 사용 안 함
* 정규화 테이블의 구분 컬럼은 공란 저장

---

## 12.7 연령/기준(I열) 병합 정책 FINAL

I열 값이 있으면:

```text
납기(H열) + "(" + I열 + ")"
```

형태로 결합.

예:

| H열   | I열  | 결과        |
| ---- | --- | --------- |
| 3년만기 | 3년납 | 3년만기(3년납) |

---

## 12.8 보종 판정 FINAL

| 조건      | coverage_type |
| ------- | ------------- |
| 연금 + 변액 | 변액연금          |
| 연금 + 저축 | 연금저축          |
| 종신 포함   | 종신/CI         |
| CEO 포함  | CEO정기         |
| 연금 포함   | 연금            |
| 기타      | 기타(보장성)       |

주의:

* 변액연금 우선
* 연금저축 우선
* 일반 연금은 마지막

---

## 12.9 컬럼 매핑 FINAL

| 정규화 필드       | raw        |
| ------------ | ---------- |
| product_name | C열         |
| plan_type    | 공란         |
| pay_period   | H열 + I열 결합 |
| year1        | K열         |
| year2        | K열         |
| year3        | K열         |
| year4        | K열         |

---

## 12.10 dedupe 정책 FINAL

최종 정규화 후:

```python
(product_name, plan_type, pay_period)
```

가 동일하면 같은 상품으로 보고 제거.

즉:

```python
seen_keys = {
    (상품명, 구분, 납기)
}
```

기준 dedupe.

---

# 13. IM 정규화 핵심

* 첫 번째 시트만 사용
* E열 == 주계약만 사용
* 미판매 제외
* 납기 문자열 보존

---

# 14. ABL/DB 정책

ABL:

* 종신 포함 → 종신/CI
* 기타 → 기타(보장성)

DB:

* 특약/방카교차 시트 제외
* 첫 번째 테이블만 사용

---

# 15. 교보 생명 정규화 FINAL

파일:

```text
commission/services/rate_example_normalizers/life_kyobo.py
```

---

## 15.1 대상

| 조건           | 값     |
| ------------ | ----- |
| insurer_type | life  |
| category     | conv  |
| insurer      | 교보    |
| 파일           | .xlsx |

---

## 15.2 대상 시트

반드시 아래 시트만 사용:

```text
주계약(종속특약포함)
```

다른 시트(특약, 단체보험, 단체 특약 등)는 모두 무시.

---

## 15.3 테이블 구성

교보 raw 파일은 단일 시트에 5개 테이블이 열 방향으로 나열된다.

| 테이블           | 상품명 열   | 구분 열       | 납기 열    | 환산율 열   | 보종 판정 정책              |
| ------------- | ------- | ---------- | ------- | ------- | --------------------- |
| 종신보험          | B열(2)   | E열(5)      | D열(4)   | F열(6)   | 종신/CI 고정              |
| CI보험          | H열(8)   | K열(11)     | J열(10)  | L열(12)  | 종신/CI 고정              |
| 연금보험          | N열(14)  | Q열(17)     | P열(16)  | R열(18)  | 연금 / 변액연금 / 연금저축 분기   |
| 정기보험          | Z열(26)  | 없음         | AB열(28) | AC열(29) | CEO정기(경영 포함) / 종신/CI  |
| 건강/어린이/기타보장   | AE열(31) | 없음         | AG열(33) | AH열(34) | 기타(보장성) 고정            |

* 5행은 헤더. 데이터는 6행부터 시작.
* 각 테이블의 마지막 행은 해당 환산율 열의 마지막 데이터 행으로 독립 탐색한다.

---

## 15.4 공통 헬퍼 구조

```text
_text(value) → str
_should_exclude(product_name) → bool
_is_subtype_keyword(value) → bool
_to_decimal_percent(cell) → Decimal | None
_last_data_row(ws, rate_col) → int
_resolve_product(...) → tuple
_make_row(...) → RateExampleConversionRow
_parse_table(...) → list[RateExampleConversionRow]
```

공통 헬퍼 원칙:

* 테이블 추가 시 `_parse_table()` + `coverage_type_fn` 만 추가
* 상품명 처리 로직(`_resolve_product`)은 모든 테이블이 공유
* 보종 판정은 테이블별 함수(`_coverage_*`)로 분리

---

## 15.5 상품명 제외 정책 FINAL

`_should_exclude()` 기준:

* 상품명에 `판매중지` 포함 → 제외
* 상품명에 `특약` 포함 → 제외
* 해당 상품 하위 공란 행도 동일하게 제외 (전파)

```python
def _should_exclude(product_name: str) -> bool:
    name = _text(product_name)
    return "판매중지" in name or "특약" in name
```

---

## 15.6 상품명 공란 전파 정책 FINAL

`_resolve_product()` 처리 순서:

1. B열(또는 해당 테이블 상품명 열)이 공란 → 직전 상품명 전파
2. 서브타입 키워드(`_is_subtype_keyword`) → 직전 상품명에 합성
3. 일반 상품명 → 그대로 사용

---

## 15.7 서브타입 키워드 판정 정책 FINAL

`_is_subtype_keyword()` 판정 기준:

* 문자열 전체가 `(` 로 시작하고 `)` 로 끝남
* **내부에 추가 괄호가 없음** (단일 괄호 쌍)

```python
def _is_subtype_keyword(value: str) -> bool:
    v = value.strip()
    if not (v.startswith("(") and v.endswith(")")):
        return False
    inner = v[1:-1]
    return "(" not in inner and ")" not in inner
```

예:

| 값                          | 판정    | 이유              |
| -------------------------- | ----- | --------------- |
| `(기본형)`                    | True  | 단일 괄호 쌍         |
| `(체증형)`                    | True  | 단일 괄호 쌍         |
| `(무)교보바로받는웰스연금(거치형)`       | False | 내부에 추가 괄호 있음    |
| `기본형(플러스),보장강화형(플러스)`      | False | 괄호로 시작 안 함      |

서브타입 합성 예:

| 직전 상품명                            | 서브타입 키워드 | 합성 결과                              |
| ---------------------------------- | -------- | ---------------------------------- |
| 교보하이브리드변액종신보험(무배당)\_판매중지          | (체증형)    | 교보하이브리드변액종신보험(무배당)\_판매중지(체증형)      |

합성 후 `_should_exclude` 재판정 → 판매중지 포함이므로 제외.

---

## 15.8 보종 판정 FINAL

### 종신보험 / CI보험

```python
coverage_type = "종신/CI"  # 고정
```

### 연금보험

| 조건      | coverage_type |
| ------- | ------------- |
| 변액 포함   | 변액연금          |
| 저축 포함   | 연금저축          |
| 기타      | 연금            |

우선순위: 변액연금 > 연금저축 > 연금

### 정기보험

| 조건    | coverage_type |
| ----- | ------------- |
| 경영 포함 | CEO정기         |
| 기타    | 종신/CI         |

### 건강/어린이/기타보장

```python
coverage_type = "기타(보장성)"  # 고정
```

---

## 15.9 Excel % 셀 보정 정책

교보 raw 파일의 환산율 열(F/L/R/AC/AH)은 모두 `number_format='0%'` 또는 `'0.00%'`.

openpyxl 읽기 결과:

| Excel 표시 | openpyxl value | number_format | DB 저장         |
| -------- | -------------- | ------------- | ------------- |
| 75%      | 0.75           | 0%            | Decimal("75") |
| 150%     | 1.5            | 0%            | Decimal("150")|
| 0.22%    | 0.0022         | 0.00%         | Decimal("0.22")|

`_to_decimal_percent()` 가 `number_format`에 `%` 포함 시 ×100 보정 적용.

---

## 15.10 회귀 위험 포인트

* `TARGET_SHEET_NAME = "주계약(종속특약포함)"` byte 일치 필수
* 각 테이블 환산율 열 번호 변경 금지 (열 이동 시 상수 전체 점검)
* `_is_subtype_keyword` 내부 괄호 체크 로직 변경 금지
* `_should_exclude` 판정 키워드(`판매중지`, `특약`) 변경 시 전 테이블 영향

---


# 16. 동양생명 정규화 FINAL

파일:

```text
commission/services/rate_example_normalizers/life_dongyang.py
```

---

## 16.1 대상

| 조건           | 값     |
| ------------ | ----- |
| insurer_type | life  |
| category     | conv  |
| insurer      | 동양    |
| 파일           | .xlsx |

---

## 16.2 대상 시트

반드시 아래 시트만 사용:

```text
주계약
```

다른 시트는 모두 무시한다.

실제 raw 파일 기준 확인된 시트:

| 시트명 | 처리 |
| ------ | ---- |
| 주계약 | 정규화 대상 |
| 특약   | 무시 |

---

## 16.3 raw 제외 정책

동양 raw 파일은 1~12행이 안내/기준 영역이고, 13~14행은 헤더 영역이다.

따라서 정규화 데이터는 15행부터 처리한다.

```python
DATA_START_ROW = 15

for row_no in range(DATA_START_ROW, ws.max_row + 1):
    ...
```

정책:

* 1~14행 제외
* 15행부터 데이터 row로 판단
* `source_row_no`에는 실제 Excel 행 번호 저장

---

## 16.4 함수명 SSOT

동양 parser의 공식 함수명은 아래로 통일한다.

```python
build_life_dongyang_conversion_rows(example, workbook)
```

호환 alias는 허용한다.

```python
build_dongyang_conversion_rows = build_life_dongyang_conversion_rows
```

이유:

* `life_abl.py` 등 기존 생보 parser 함수명 패턴과 맞춘다.
* `rate_example_normalizers/__init__.py` export와 `rate_example_normalizer.py` dispatcher import 이름이 일치해야 한다.
* 함수명 불일치 시 업로드 시점에 `ImportError`가 발생한다.

금지:

```python
# __init__.py 또는 normalizer.py에서 실제 파일에 없는 함수명 import 금지
from commission.services.rate_example_normalizers.life_dongyang import build_dongyang_conversion_rows
```

허용:

```python
from commission.services.rate_example_normalizers.life_dongyang import (
    build_life_dongyang_conversion_rows,
)
```

---

## 16.5 컬럼 매핑 FINAL

| 정규화 필드       | raw 컬럼 | 설명 |
| ------------ | ------- | ---- |
| insurer      | 고정값   | `동양` |
| product_name | B열      | 대표상품명 |
| coverage_type | B열 기반 | 상품명 키워드로 판정 |
| plan_type    | C열      | 세부상품명 중 첫 번째 `_` 뒤 텍스트 |
| pay_period   | G열      | 납입기간 원문 |
| year1        | J열      | 초년도 환산 변경후 |
| year2        | L열      | 차년도 환산 변경후 |
| year3        | L열      | 차년도 환산 변경후 |
| year4        | L열      | 차년도 환산 변경후 |

---

## 16.6 상품명 전파 정책

동양 raw 파일은 대표상품명(B열)이 병합 또는 공란으로 내려오는 행이 있을 수 있다.

정책:

* B열 값이 있으면 `current_product_name` 갱신
* B열 값이 없으면 직전 상품명 전파
* 전파 후에도 상품명이 없으면 제외

```python
if raw_product_name:
    current_product_name = raw_product_name

product_name = current_product_name

if not product_name:
    continue
```

---

## 16.7 구분(plan_type) 파싱 정책 FINAL

세부상품명(C열)에서 첫 번째 언더스코어(`_`) 뒤 텍스트를 저장한다.

예:

| C열 raw | plan_type |
| ------- | --------- |
| 무배당A상품_보장형_평준납입형 | 보장형_평준납입형 |
| 무배당B상품_해약환급금 일부지급 | 해약환급금 일부지급 |
| 언더스코어없음 | 공란 |

정책:

```python
def _plan_type_from_detail(detail_name: str) -> str:
    detail = _text(detail_name)
    if "_" not in detail:
        return ""
    return detail.split("_", 1)[1].strip()
```

주의:

* 첫 번째 `_` 앞 텍스트는 상품명 성격이므로 구분에 저장하지 않는다.
* `_`가 여러 개 있으면 첫 번째 `_` 뒤 전체를 보존한다.
* `_`가 없으면 공란 저장한다.

---

## 16.8 보종 판정 FINAL

상품명(B열) 기준으로 판정한다.

| 조건 | coverage_type |
| ---- | ------------- |
| `종신` 포함 | 종신/CI |
| `연금` 포함 | 연금 |
| 기타 | 기타(보장성) |

우선순위:

```text
종신 > 연금 > 기타(보장성)
```

구현 예:

```python
def _coverage_type(product_name: str) -> str:
    name = _text(product_name)
    if "종신" in name:
        return "종신/CI"
    if "연금" in name:
        return "연금"
    return "기타(보장성)"
```

---

## 16.9 환산율 처리 FINAL

동양 raw의 환산율 컬럼:

| 연차 | raw 컬럼 | 저장 필드 |
| ---- | -------- | -------- |
| 1차년 | J열 | year1 |
| 2차년 | L열 | year2 |
| 3차년 | L열 | year3 |
| 4차년 | L열 | year4 |

즉, 차년도 환산 변경후(L열)를 2~4차년에 동일하게 저장한다.

```python
year1 = _to_decimal_percent(ws.cell(row_no, COL_YEAR1_AFTER))
next_year = _to_decimal_percent(ws.cell(row_no, COL_NEXT_AFTER))

year2 = next_year
year3 = next_year
year4 = next_year
```

---

## 16.10 Excel % 셀 보정 정책

동양 raw의 J/L열은 Excel 표시상 `%` 형식일 수 있다.

openpyxl은 아래처럼 읽을 수 있다.

| Excel 표시 | openpyxl value | number_format | DB 저장 |
| ---------- | -------------- | ------------- | ------- |
| 70%        | 0.7            | 0%            | Decimal("70") |
| 150%       | 1.5            | 0%            | Decimal("150") |
| 0.22%      | 0.0022         | 0.00%         | Decimal("0.22") |

반드시 기존 환산율 저장 정책과 동일하게 백분율 수치 기준으로 저장한다.

```python
if "%" in number_format:
    dec *= Decimal("100")
```

금지:

```python
# 70%를 Decimal("0.7")로 저장 금지
```

---

## 16.11 row 제외 정책 FINAL

제외 대상:

* 상품명 전파 후에도 상품명이 없는 행
* 세부상품명(C열)이 없는 행
* J/L열 환산률이 모두 비어 있는 행
* 1~14행

기본적으로 `특약` 문구는 동양 주계약 시트에서 별도 제외 키워드로 적용하지 않는다.

이유:

* 요구사항의 대상 시트가 `주계약`으로 고정되어 있다.
* `특약` 시트는 시트 단위로 무시한다.
* 주계약 시트 내 특약성 문구 제외는 별도 raw 케이스 확인 후 정책화한다.

---

## 16.12 dispatcher 연결 정책

파일:

```text
commission/services/rate_example_normalizer.py
```

import:

```python
from commission.services.rate_example_normalizers.life_dongyang import (
    build_life_dongyang_conversion_rows,
)
```

분기:

```python
elif example.insurer == "동양":
    rows = build_life_dongyang_conversion_rows(example, wb)
```

주의:

* `rate_example_normalizer.py`는 dispatcher만 담당한다.
* 동양 세부 파싱 로직을 dispatcher에 직접 작성하지 않는다.
* `normalize_mode` 처리, 기존 row 삭제, `bulk_create`는 기존 오케스트레이터 정책을 그대로 따른다.

---

## 16.13 프론트 드롭다운 정책

파일:

```text
commission/templates/commission/rate_example_home.html
static/js/commission/rate_example_home.js
```

정책:

* 업로드 모달 보험사 dropdown에 `동양` 추가
* 조회 모달 보험사 dropdown에 `동양` 추가
* KB 전용 product_kind dropdown은 동양 선택 시 숨김
* JS에 동양 정규화 규칙 하드코딩 금지

서버 전달값:

```text
insurer_type = life
category = conv
insurer = 동양
```

---

## 16.14 동양 회귀 위험 포인트

* `TARGET_SHEET_NAME = "주계약"` byte 일치 필수
* `DATA_START_ROW = 15` 변경 금지
* B/C/G/J/L 열 번호 변경 금지
* 공식 함수명 `build_life_dongyang_conversion_rows` 유지
* `__init__.py` export명과 dispatcher import명 일치 필수
* J열은 1차년만 저장
* L열은 2~4차년에 동일 저장
* `%` 보정 누락 시 모든 환산율이 100분의 1로 저장됨

---


# 17. 프론트 구조

파일:

```text
static/js/commission/rate_example_home.js
```

핵심:

* root.dataset.inited 중복 방지
* normalize_mode FormData 전달
* 생보 전용 업로드 구조
* 보험사 dropdown 항상 활성화
* KB 선택 시 상품 dropdown 노출

---

# 18. 업로드 모달 정책 FINAL

현재 업로드 모달은 생보 전용 구조.

제거된 항목:

* 손생구분 dropdown
* 구분 dropdown

서버에는:

```python
insurer_type = "life"
category = "conv"
```

고정 전달.

---

## 18.1 KB 상품 dropdown

KB 선택 시만 노출.

옵션:

* general
* health

KDB/교보/동양은 product_kind 사용 안 함.

---

# 19. 조회 모달 정책 FINAL

환산율 확인 모달:

* 손생구분 제거
* 보험사만 선택
* insurer_type=life 고정 조회

---

# 20. 전략상품 저장 정책

정규화 row의:

```text
strategy_flag
```

필드를 사용.

허용값:

* 전략상품1
* 전략상품2
* 전략상품3
* 전략상품4

저장 API:

```text
commission:rate_example_conversion_strategy_update
```

---

# 21. Audit 정책

로그 대상:

* 업로드
* 다운로드
* 삭제
* 전략상품 변경

필수 meta:

* insurer_type
* insurer
* category
* original_name
* normalized_count
* product_kind
* normalize_mode

---

# 22. 보안 원칙

금지:

* file.url 직접 노출
* except: pass
* 권한 완화
* raw 파일 public URL 제공

허용:

* FileResponse 다운로드
* logger.exception 사용
* superuser 유지
* transaction.atomic 사용

---

# 23. 회귀 위험 체크리스트

* URL name 변경 없음
* dataset key 유지
* replace 정상
* append 정상
* KB 일반상품 조회 정상
* KB 건강보험 조회 정상
* KDB 조회 정상
* IM 조회 정상
* ABL 조회 정상
* DB 조회 정상
* 교보 조회 정상 (189건 기준)
* 교보 종신/CI 조회 정상
* 교보 CI보험 조회 정상
* 교보 연금보험 조회 정상 (변액연금/연금저축 분기 포함)
* 교보 정기보험(CEO정기) 조회 정상
* 교보 건강/기타보장 조회 정상
* 교보 판매중지/특약 제외 정상 (잔존 0건)
* 교보 서브타입 합성 후 재판정 정상
* 교보 괄호 단독 상품명 잔존 없음
* 동양 조회 정상
* 동양 `주계약` 시트만 정규화 정상
* 동양 `특약` 시트 무시 정상
* 동양 1~14행 제외 정상
* 동양 B열 상품명 전파 정상
* 동양 C열 첫 번째 `_` 뒤 구분 저장 정상
* 동양 G열 납기 원문 보존 정상
* 동양 J열 → 1차년 저장 정상
* 동양 L열 → 2~4차년 동일 저장 정상
* 동양 종신/연금/기타 보종 판정 정상
* 동양 `%` 보정 정상
* 동양 함수명 import 정상 (`build_life_dongyang_conversion_rows`)
* % 출력 정상
* 336.0% 정상 출력
* 병합 셀 전파 정상
* dedupe 정상
* python manage.py check 통과

---

# 24. 절대 금지

* 환산율을 1.26 기준으로 저장
* file.url 직접 노출
* parser를 dispatcher에 재삽입
* except: pass 사용
* DOM id 변경
* dataset key 변경
* normalize_mode 기본값 변경
* 보험사별 정책을 프론트 JS에 하드코딩
* 교보 `_is_subtype_keyword` 내부 괄호 체크 제거
* 교보 `_should_exclude` 판정 키워드 임의 변경
* 교보 테이블 열 번호 상수를 parser 밖에서 하드코딩
* 동양 환산율을 0.7 기준으로 저장
* 동양 `특약` 시트를 정규화 대상에 포함
* 동양 1~14행을 정규화 대상에 포함
* 동양 J열 값을 2~4차년에 복제
* 동양 L열 값을 1차년에 저장
* 동양 공식 함수명과 dispatcher import명을 다르게 유지

---

동양생명 관련 최신 반영 기준 포함 리팩토링 완료. 이번 버전 주요 변경:

* 동양 parser 구조 (`life_dongyang.py`) 추가
* 동양 공식 함수명 `build_life_dongyang_conversion_rows` 기준화
* 동양 legacy alias `build_dongyang_conversion_rows` 정책 추가
* `주계약` 시트 only 정규화 정책 추가
* 1~14행 제외, 15행부터 처리 정책 추가
* B/C/G/J/L 열 매핑 정책 추가
* 종신/연금/기타 보종 판정 정책 추가
* J열 1차년, L열 2~4차년 저장 정책 추가
* 동양 `%` 보정 및 회귀 체크리스트 보강 완료
* 절대금지 동양 관련 항목 추가