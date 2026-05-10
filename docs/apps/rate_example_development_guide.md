# django_ma 수수료 예시표(RateExample) 개발 가이드 FINAL (KDB 포함 리팩토링)

> 목적:
>
> 추후 전체 세부 코드를 다시 제공하지 않아도,
> 수수료 예시표 기능의 구조·계약·정규화 정책·보험사별 parser 구조를
> 빠르게 이해하고 안전하게 디벨롭할 수 있도록 정리한 FINAL 기준 문서입니다.
>
> 기준일: 2026-05-10
>
> 최신 반영:
>
> * IM 생명 정규화 FINAL
> * KB 생명 일반상품 정규화 FINAL
> * KB 건강보험 정규화 FINAL
> * KDB 생명 정규화 FINAL
> * normalize_mode(replace/append) 정책
> * 환산율 % 저장 정책 통일
> * Excel 백분율 셀 보정 정책
> * append 정책
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
└── life_KDB.py
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

# 15. 프론트 구조

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

# 16. 업로드 모달 정책 FINAL

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

## 16.1 KB 상품 dropdown

KB 선택 시만 노출.

옵션:

* general
* health

KDB는 product_kind 사용 안 함.

---

# 17. 조회 모달 정책 FINAL

환산율 확인 모달:

* 손생구분 제거
* 보험사만 선택
* insurer_type=life 고정 조회

---

# 18. 전략상품 저장 정책

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

# 19. Audit 정책

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

# 20. 보안 원칙

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

# 21. 회귀 위험 체크리스트

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
* % 출력 정상
* 336.0% 정상 출력
* 특약 제외 정상
* 괄호 파싱 정상
* 병합 셀 전파 정상
* dedupe 정상
* python manage.py check 통과

---

# 22. 절대 금지

* 환산율을 1.26 기준으로 저장
* file.url 직접 노출
* parser를 dispatcher에 재삽입
* except: pass 사용
* DOM id 변경
* dataset key 변경
* normalize_mode 기본값 변경
* 보험사별 정책을 프론트 JS에 하드코딩

---

KDB 관련 최신 반영 기준 포함 리팩토링 완료. 기존 guide 대비:

* KDB parser 구조 추가
* merged_cells/read_only 정책 추가
* 병합 셀 전파 정책 추가
* dedupe 정책 추가
* KDB 납기 조합 정책 추가
* KDB 보종 우선순위 추가
* product_kind 비사용 정책 추가
* 회귀 체크리스트 보강 완료 
