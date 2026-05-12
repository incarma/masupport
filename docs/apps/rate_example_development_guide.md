# django_ma 수수료 예시표(RateExample) 개발 가이드 FINAL

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
> * 지급률(RateExamplePayRow) 기능 전체 추가
> * 지급률 URL/뷰/서비스/모델/JS/CSS 계약 FINAL
> * 지급률 보험사별 컬럼 매핑 FINAL (20개 생보사)
> * 지급률 모달 UI 정책 FINAL
>
> 이전 반영 내역:
>
> * 라이나생명 정규화 FINAL (Excel/PDF)
> * 동양생명 정규화 FINAL
> * 교보 생명 정규화 FINAL
> * IM 생명 정규화 FINAL
> * KB 생명 일반상품/건강보험 정규화 FINAL
> * KDB 생명 정규화 FINAL
> * normalize_mode(replace/append) 정책
> * 환산율 % 저장 정책 통일
> * Excel 백분율 셀 보정 정책
> * 전략상품 저장 정책
> * 생보 전용 업로드 UI 전환
> * parser dispatcher 구조 SSOT

---

# 1. 기능 개요

수수료 예시표 기능은 보험사 raw 예시표 파일을 업로드하고,
보험사별 parser를 통해 표준 정규화 테이블로 변환하여
조회/검색/전략상품 관리/향후 계산 엔진에 사용하는 기능이다.

핵심 책임:

1. 원본 파일 업로드
2. 파일 검증
3. 보험사별 정규화
4. 정규화 데이터 조회
5. 전략상품 저장
6. 업로드/다운로드/삭제 audit
7. 계산 엔진용 표준 환산율/지급률 데이터 구축

현재 정규화 지원 범위:

| category | 설명 |
| --- | --- |
| conv | 생명보험 환산율/수정률 (10개 보험사) |
| pay | 생명보험 지급률 (20개 보험사, 단일 xlsx) |

---

# 2. URL 계약

파일:

```text
commission/urls.py
```

기존 URL name 변경 금지.

| URL name | 역할 |
| --- | --- |
| commission:rate_example_home | 메인 |
| commission:rate_example_upload | 업로드 (환산율/지급률 공통) |
| commission:rate_example_download | 원본 다운로드 |
| commission:rate_example_delete | 삭제 |
| commission:rate_example_conversion_list | 환산율 정규화 조회 |
| commission:rate_example_conversion_strategy_update | 전략상품 저장 |
| commission:rate_example_pay_list | 지급률 정규화 조회 |

원칙:

* 보험사 추가 시 URL 추가 금지
* parser만 추가
* 기존 URL name 변경 금지
* 화면/JS에서 정규화 로직 하드코딩 금지

---

# 3. 모델 구조

## 3.1 RateExample

원본 파일 메타.

주요 필드:

* insurer_type (life / nonlife)
* category (conv / pay)
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

환산율/수정률 정규화 master 테이블.

주요 필드:

* source_file / source_sheet / source_row_no
* insurer_type / category / insurer
* coverage_type / strategy_flag
* product_name / plan_type / pay_period
* year1 / year2 / year3 / year4

---

## 3.3 RateExamplePayRow

지급률 정규화 테이블. (신규)

주요 필드:

* source_file / source_sheet / source_row_no
* insurer_type / category / insurer
* tier (현재 "5천만↑" 고정)
* coverage_type
* col_first : 초회
* col_yr1   : 1차년
* col_m13   : 13회
* col_yr2   : 2차년구간
* col_yr3   : 3차년구간
* col_m36   : 36회 (별도 기재 보험사만 값, 나머지 None)
* col_m37   : 37회 (별도 기재 보험사만 값, 나머지 None)
* col_yr4   : 4차년구간 (해당 보험사만 값, 나머지 None)

필드명 설계 원칙:

```text
col_first  → verbose_name="초회"
col_yr1    → verbose_name="1차년"
col_m13    → verbose_name="13회"
col_yr2    → verbose_name="2차년구간"
col_yr3    → verbose_name="3차년구간"
col_m36    → verbose_name="36회"
col_m37    → verbose_name="37회"
col_yr4    → verbose_name="4차년구간"
```

영문 필드명 사용 이유:

* Django ORM 쿼리 안정성
* IDE 자동완성 지원
* 마이그레이션 파일 가독성
* verbose_name으로 한글 의미 유지

---

# 4. 환산율 저장 정책 FINAL

## 매우 중요

현재 모든 보험사는 **백분율 수치 기준**으로 저장한다.

| raw 표시 | DB 저장 |
| --- | --- |
| 100.0% | Decimal("100.0") |
| 336.0% | Decimal("336.0") |
| 126% | Decimal("126") |

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

# 5. 지급률 저장 정책 FINAL

지급률도 환산율과 동일하게 **수치 그대로** 저장한다.

| raw 파일 값 | DB 저장 |
| --- | --- |
| 222.59 | Decimal("222.59") |
| 47.92 | Decimal("47.92") |
| 0 | Decimal("0") |
| (없음/병합) | None |

소수점 4자리 고정:

```python
Decimal(str(value)).quantize(Decimal("0.0001"))
```

---

# 6. 화면 출력 정책

환산율 확인 모달:

```text
336.0%
126%
100.0%
245.0%
```

지급률 확인 모달:

```text
222.59
47.92
0
- (None인 경우)
```

지급률은 % 없이 숫자로 출력한다.
36회/37회/4차년구간이 None인 경우 UI에서 `-` 표시.

---

# 7. Excel 백분율 셀 처리 정책

raw Excel 셀이:

```text
336.0%
```

처럼 보이더라도, openpyxl은 실제값을:

```python
3.36
```

으로 읽을 수 있다.

따라서 환산율 parser에서는:

```python
if "%" in number_format:
    value *= 100
```

형태로 보정 후 저장한다.

지급률 파일은 수치 그대로 저장하므로 이 보정이 불필요하다.

---

# 8. normalize_mode 정책 FINAL

업로드 모달에는:

```text
기존 데이터 초기화 여부
```

옵션이 존재한다.

## 8.1 replace

동작:

* 동일 insurer_type/category/insurer row 전체 삭제
* 신규 bulk_create

## 8.2 append

동작:

* 기존 row 유지
* 신규 row만 append

## 8.3 지급률 normalize_mode 정책

지급률(category=pay) 업로드는:

```python
normalize_mode = "replace"  # 서버에서 강제 고정
```

이유:

* 지급률은 전사 단일 파일로 20개 보험사가 한 번에 교체됨
* append는 지급률에서 의미 없음
* JS에서 전달하는 normalize_mode는 서버에서 무시됨

---

# 9. 정규화 오케스트레이터

파일:

```text
commission/services/rate_example_normalizer.py
```

역할:

* 파일 형식 판정
* workbook load 또는 PDF parser 분기
* category 분기 (conv / pay)
* 보험사 parser dispatch
* replace/append 처리
* bulk_create

## 9.1 category 분기 정책 FINAL

오케스트레이터 진입 직후 category 분기:

```python
if example.category == RateExample.CAT_PAY:
    from commission.services.rate_example_pay_normalizer import normalize_pay_rate_example
    return normalize_pay_rate_example(example, normalize_mode=normalize_mode)
```

pay 분기는 conv dispatcher와 완전 격리.
pay 분기에서 return하면 conv 로직에 진입하지 않는다.

## 9.2 workbook load 정책 FINAL

KDB 등 병합 셀 처리를 위해:

```python
read_only=False
```

고정 사용.

## 9.3 PDF 분기 정책 FINAL

```python
original_name = str(example.original_name or "").lower()

if original_name.endswith(".pdf"):
    if example.insurer != "라이나":
        return 0
    normalized_rows = build_life_lina_pdf_conversion_rows(example)
    ...
    return len(normalized_rows)

if not original_name.endswith(".xlsx"):
    return 0
```

## 9.4 현재 dispatcher 구조

conv dispatcher:

```python
if example.insurer == "ABL": ...
elif example.insurer == "DB": ...
elif example.insurer == "IM": ...
elif example.insurer == "KB": ...
elif example.insurer == "KDB": ...
elif example.insurer == "교보": ...
elif example.insurer == "농협": ...
elif example.insurer == "동양": ...
elif example.insurer == "라이나": ...
elif example.insurer == "신한": ...
```

pay dispatcher:

```python
# rate_example_pay_normalizer.py 내부
# 별도 파일로 완전 분리
```

---

# 10. 지급률 정규화 서비스 FINAL

파일:

```text
commission/services/rate_example_pay_normalizer.py
```

## 10.1 대상

| 조건 | 값 |
| --- | --- |
| insurer_type | life |
| category | pay |
| 파일 | .xlsx |
| 시트 | ① 5천만, 3천만↑ |

## 10.2 대상 시트

```python
TARGET_SHEET = "① 5천만, 3천만↑"
```

5천만원↑ 블록(행 5~16, 32~43, 59~70, 86~97)만 처리.

## 10.3 보험사별 컬럼 매핑 FINAL

tuple 형식: `(col_first, col_yr1, col_m13, col_yr2, col_yr3, col_m36, col_m37, col_yr4)`

값: 1-indexed 열 번호. None = 해당 보험사에 없는 회차.

### 그룹1 (데이터행 5~16)

| 보험사 | first | yr1 | m13 | yr2 | yr3 | m36 | m37 | yr4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ABL | 5 | 6 | 7 | 8 (14~24회) | 9 (25~36회) | - | - | 10 (37~48회) |
| 삼성 | 12 | 13 | 14 | 15 (19~24회) | 16 (25~36회) | - | 17 | - |
| 신한 | 19 | 20 | 21 | 22 (14~24회) | 23 (25~36회) | - | 24 | - |
| 하나 | 26 | 27 | 28 | 29 (14~24회) | 30 (25~36회) | - | - | - |

IBK는 별도 처리 (col32 상품명, col35~39 수치)

### 그룹2 (데이터행 32~43)

| 보험사 | first | yr1 | m13 | yr2 | yr3 | m36 | m37 | yr4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DB | 5 | 6 | 7 | 8 (13~24회) | 9 (25~36회) | - | 10 | - |
| IM | 12 | 13 | 14 | 15 (14~24회) | 16 (25~35회) | 17 | - | - |
| KB | 19 | 20 | 21 | 22 (14~24회) | 23 (25~36회) | - | 24 | - |
| 농협 | 26 | 27 | 28 | 29 (19~24회) | 30 (25~36회) | - | - | - |
| 라이나 | 32 | 33 | 34 | 35 (14~24회) | 36 (25~36회) | - | - | - |

### 그룹3 (데이터행 59~70)

| 보험사 | first | yr1 | m13 | yr2 | yr3 | m36 | m37 | yr4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KDB | 5 | 6 | 7 | 8 (14~24회) | 9 (25~36회) | - | 10 | - |
| 미래 | 12 | 13 | 14 | 15 (14~24회) | 16 (25~36회) | - | 17 | - |
| 처브 | 19 | 20 | 21 | 22 (14~24회) | 23 (25~36회) | - | - | 24 (37~48회) |
| 한화 | 26 | 27 | 28 | 29 (14~24회) | 30 (25~35회) | 31 | - | 32 (37~42회) |
| 카디프 | 34 | 35 | 36 | 37 (14~24회) | 38 (25~36회) | - | 39 | - |

### 그룹4 (데이터행 86~97)

| 보험사 | first | yr1 | m13 | yr2 | yr3 | m36 | m37 | yr4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 동양 | 5 | 6 | 7 | 8 (19~24회) | 9 (25~36회) | - | - | - |
| 메트 | 11 | 12 | 13 | 14 (14~24회) | 15 (25~36회) | - | 16 | - |
| 흥국 | 18 | 19 | 20 | 21 (14~15회) | 22 (25회) | 23 | - | - |
| 푸본현대 | 25 | 26 | 27 | 28 (14~24회) | 29 (25~36회) | - | - | - |
| 교보 | 31 | 32 | 33 | 34 (14~24회) | 35 (25~36회) | - | - | 36 (37~39회) |

### 흥국 특이 구조

흥국은 2차년(14~15회), 3차년(25회) 구간이 타 보험사와 상이하다.
필드 매핑은 col_yr2 / col_yr3 에 그대로 저장하며 verbose_name으로 의미를 보존한다.

## 10.4 IBK 전용 처리

IBK는 상품군(col4) 대신 col32 자체 상품명을 coverage_type으로 사용한다.

```python
coverage_type = f"[IBK]{str(raw_product).strip()}"
```

col_m36 / col_m37 / col_yr4 는 없음 (None).

## 10.5 상품군(coverage_type) 정규화

col4 값 기준:

| raw | DB 저장 |
| --- | --- |
| 종신,CI | 종신/CI |
| 연금 | 연금 |
| 변액연금 | 변액연금 |
| 저축 | 저축 |
| VUL | VUL |
| 연금저축 | 연금저축 |
| 기타(보장성) | 기타(보장성) |
| CEO정기 | CEO정기 |
| 전략상품1~4 | 전략상품1~4 |

col4 공란이면 직전 값 전파 (병합셀 대응).

## 10.6 col_m36 / col_m37 / col_yr4 있는 보험사

| 컬럼 | 있는 보험사 |
| --- | --- |
| col_m36 | IM, 한화, 흥국 |
| col_m37 | 삼성, 신한, DB, KB, KDB, 미래, 카디프, 메트 |
| col_yr4 | ABL, 처브, 한화, 교보 |

나머지 보험사는 None → UI에서 `-` 표시.

---

# 11. 지급률 업로드 서비스 정책 FINAL

파일:

```text
commission/services/rate_example.py
```

## 11.1 category=pay 전용 서버 강제 처리

```python
if category == RateExample.CAT_PAY:
    insurer        = ""
    product_kind   = ""
    normalize_mode = "replace"
```

이유:

* 지급률 파일은 보험사 선택 없이 업로드 (전사 단일 파일)
* insurer는 normalizer가 파일 내부에서 직접 판단
* normalize_mode는 항상 replace

## 11.2 지급률 보험사 허용 목록 검증 skip

```python
if category != RateExample.CAT_PAY:
    if insurer not in _ALLOWED_INSURERS.get(insurer_type, set()):
        return {"ok": False, "message": "선택된 보험사가 허용 목록에 없습니다."}
```

---

# 12. 지급률 조회 API FINAL

파일:

```text
commission/views/api_rate_example_pay.py
```

URL:

```text
commission:rate_example_pay_list
GET /commission/rate-examples/pay/list/
```

권한: superuser 전용

응답 구조:

```json
{
  "ok": true,
  "data": {
    "rows": [
      {
        "insurer": "ABL",
        "tier": "5천만↑",
        "coverage_type": "종신/CI",
        "col_first": "222.59",
        "col_yr1":   "0",
        "col_m13":   "47.92",
        "col_yr2":   "47.92",
        "col_yr3":   "95.86",
        "col_m36":   "",
        "col_m37":   "",
        "col_yr4":   "95.86"
      }
    ],
    "count": 240,
    "last_updated_at": "2026-05-11 14:30",
    "last_updated_by": "홍길동",
    "source_file_name": "지급률.xlsx"
  }
}
```

None 필드는 `""` (빈 문자열)로 직렬화.
JS에서 `""` → `-` 렌더링.

---

# 13. views/__init__.py 등록 정책

파일:

```text
commission/views/__init__.py
```

지급률 조회 API 등록:

```python
_RATE_EXAMPLE_API = {
    ...
    "rate_example_pay_list": (
        "commission.views.api_rate_example_pay",
        "rate_example_pay_list",
    ),
}
```

`__all__`에도 추가:

```python
"rate_example_pay_list",
```

---

# 14. 지급률 프론트 구조 FINAL

## 14.1 dataset 계약

```html
<div id="rate-example-root"
     data-upload-url="{{ upload_url }}"
     data-conversion-list-url="{{ conversion_list_url }}"
     data-conversion-strategy-update-url="{{ conversion_strategy_update_url }}"
     data-pay-list-url="{{ pay_list_url }}"
     data-user-grade="{{ request.user.grade }}">
```

`data-pay-list-url` 추가 필수. JS는 `root.dataset.payListUrl`로 읽는다.

## 14.2 지급률 업로드 모달

ID: `rateExamplePayUploadModal`

* 보험사 선택 없음 (전사 단일 파일)
* insurer_type=life / category=pay / normalize_mode=replace 서버 전달
* xlsx 파일만 허용 (`accept=".xlsx"`)

## 14.3 지급률 확인 모달

ID: `rateExamplePayModal`

테이블 컬럼:

| 컬럼 | 설명 | class |
| --- | --- | --- |
| 보험사 | insurer | - |
| 상품군 | coverage_type | - |
| 초회 | col_first | re-pay-num |
| 1차년 | col_yr1 | re-pay-num |
| 13회 | col_m13 | re-pay-num |
| 2차년구간 | col_yr2 | re-pay-num |
| 3차년구간 | col_yr3 | re-pay-num |
| 36회 | col_m36 | re-pay-num re-pay-opt |
| 37회 | col_m37 | re-pay-num re-pay-opt |
| 4차년구간 | col_yr4 | re-pay-num re-pay-opt |

36회/37회/4차년구간은 `.re-pay-opt` class 추가. 값이 빈 문자열이면 `-` 렌더.

## 14.4 JS 렌더링 정책

```javascript
function cell(v) {
  return '<td class="text-end re-pay-num">' + escapeHtml(v || "0") + "</td>";
}
function optCell(v) {
  return '<td class="text-end re-pay-num re-pay-opt">'
    + (v !== "" ? escapeHtml(v) : "-")
    + "</td>";
}
```

## 14.5 CSS 정책

```css
/* 36회/37회/4차년 선택적 컬럼: 연한 배경으로 시각 구분 */
#rate-example-root .re-pay-opt,
#rate-example-root .re-pay-opt-th {
  color: var(--bs-secondary-color, #6c757d);
  background-color: #f8f9fa;
  min-width: 60px;
}
```

---

# 15. 업로드 모달 정책 FINAL

## 15.1 환산율 업로드 모달

현재 생보 전용 구조.

* 손생구분 dropdown 없음
* 구분 dropdown 없음
* 서버에 `insurer_type=life`, `category=conv` 고정 전달
* KB 선택 시만 상품 dropdown(general/health) 노출
* KDB/교보/농협/동양/라이나는 product_kind 사용 안 함

## 15.2 지급률 업로드 모달

별도 모달 (ID: `rateExamplePayUploadModal`).

* 보험사 선택 없음
* 서버에 `insurer_type=life`, `category=pay`, `normalize_mode=replace` 고정 전달
* xlsx 파일만 허용

---

# 16. 조회 모달 정책 FINAL

## 16.1 환산율 확인 모달 (ID: rateExampleConvModal)

* 보험사만 선택 (insurer_type=life 고정)
* 라이나 선택 시 xlsx/pdf 구분 없이 동일 master table 조회
* 전략상품 저장 가능

## 16.2 지급률 확인 모달 (ID: rateExamplePayModal)

* 보험사 필터 / 상품군 필터 / 키워드 검색
* 조회 버튼 클릭 시 `data-pay-list-url` 호출
* 36회/37회/4차년 없는 보험사는 `-` 표시
* 전략상품 저장 없음 (지급률에는 strategy_flag 미적용)

---

# 17. 환산율 parser 구조 SSOT

구조:

```text
commission/services/rate_example_normalizers/
├── life_abl.py
├── life_db.py
├── life_im.py
├── life_kb.py
├── life_KDB.py
├── life_kyobo.py
├── life_nh.py
├── life_dongyang.py
├── life_lina.py
└── life_shinhan.py
```

원칙:

* 보험사별 parser는 `life_*.py`만 담당
* `rate_example_normalizer.py`는 dispatcher만 담당
* 세부 파싱 로직을 dispatcher에 직접 작성하지 않는다.

지급률 parser는 별도 단일 파일:

```text
commission/services/rate_example_pay_normalizer.py
```

모든 보험사(20개)를 단일 파일에서 처리한다.
파일 구조상 하나의 시트에 전체 보험사가 있기 때문.

---

# 18. 보험사별 환산율 정규화 정책

## 18.1 KB 일반상품 FINAL

| 조건 | 값 |
| --- | --- |
| product_kind | general |
| 파일 | .xlsx |
| 제외 | 특약 포함 행, 1~4행 |

보종 판정:

| 조건 | coverage_type |
| --- | --- |
| 변액 포함 | 변액연금 |
| 연금 포함 | 연금 |
| 경영 포함 | CEO정기 |
| 기타 | 종신/CI |

## 18.2 KB 건강보험 FINAL

| 조건 | 값 |
| --- | --- |
| product_kind | health |
| 파일 | .xlsx |
| 보종 | 기타(보장성) 고정 |

특약 차단: B열에 `특약` 등장 시 해당 행부터 하단 전체 break.

## 18.3 KDB 생명 FINAL

| 조건 | 값 |
| --- | --- |
| 대상 시트 | GA 주계약 |
| 제외 행 | 1~3행 |
| plan_type | 공란 고정 |
| 병합 셀 | C열(상품명), H열(납기) 전파 필수 |

연령/기준(I열) 병합 정책:

```text
납기 + "(" + I열 + ")"
```

dedupe 기준:

```python
(product_name, plan_type, pay_period)
```

## 18.4 IM 정규화 핵심

* 첫 번째 시트만 사용
* E열 == 주계약만 사용
* 미판매 제외
* 납기 문자열 보존

## 18.5 ABL/DB

ABL: 종신 포함 → 종신/CI, 기타 → 기타(보장성)
DB: 특약/방카교차 시트 제외, 첫 번째 테이블만 사용

## 18.6 교보 생명 FINAL

대상 시트: `주계약(종속특약포함)`

5개 테이블 열 방향 나열:

| 테이블 | 상품명 열 | 환산율 열 | coverage_type |
| --- | --- | --- | --- |
| 종신보험 | B(2) | F(6) | 종신/CI 고정 |
| CI보험 | H(8) | L(12) | 종신/CI 고정 |
| 연금보험 | N(14) | R(18) | 변액연금/연금저축/연금 분기 |
| 정기보험 | Z(26) | AC(29) | CEO정기/종신/CI |
| 건강/어린이/기타보장 | AE(31) | AH(34) | 기타(보장성) 고정 |

판매중지/특약 포함 → 제외.

## 18.7 동양생명 FINAL

대상 시트: `주계약`

| 필드 | raw 컬럼 |
| --- | --- |
| product_name | B열 |
| plan_type | C열 첫 번째 `_` 뒤 |
| pay_period | G열 |
| year1 | J열 |
| year2~4 | L열 동일 |

DATA_START_ROW = 15

## 18.8 라이나생명 FINAL


## 18.9 신한생명 FINAL

대상:

| 조건 | 값 |
| --- | --- |
| 보험사 | 신한 |
| 파일 | .xlsx |
| category | conv |
| 지원 시트 | "일반상품" 포함 시트 / "건강" 포함 시트 |

### 18.9.1 일반상품 시트 정책

헤더 기준:

| 영역 | 위치 |
| --- | --- |
| 헤더 | C6 ~ J6 |
| 데이터 시작 | 7행 |
| 종료 기준 | H열(1Y) 마지막 데이터 행 |

컬럼 매핑:

| 필드 | raw 컬럼 |
| --- | --- |
| product_name | C열 |
| plan_type | D열 + E열 |
| pay_period | F열 |
| year1 | H열 |
| year2 | I열 |
| year3 | J열 |
| year4 | 없음(None 고정) |

상품명 정책:

* C열 공란이면 직전 상품명 carry-forward
* 동일 상품명 그룹 유지

구분(plan_type) 정책:

```text
D + ", " + E
```

예:

```text
기본형, 해약환급금미지급형
```

추가 정책:

* D/E 모두 공란이면 동일 상품 내 직전 구분값 전파
* 둘 중 하나만 존재하면 해당 값만 사용

보종 판정:

| 조건 | coverage_type |
| --- | --- |
| 변액 + 연금 | 변액연금 |
| 경영 포함 | CEO정기 |
| 종신 포함 | 종신/CI |
| 연금 포함 | 연금 |
| 기타 | 기타(보장성) |

### 18.9.2 건강 시트 정책

헤더 기준:

| 영역 | 위치 |
| --- | --- |
| 헤더 | A8 ~ J8 |
| 데이터 시작 | 9행 |

대상 행:

```text
A열 == "주보험"
```

인 행만 정규화.

컬럼 매핑:

| 필드 | raw 컬럼 |
| --- | --- |
| product_name | C열 |
| plan_type | 공란 고정 |
| pay_period | G열 |
| year1 | H열 |
| year2 | I열 |
| year3 | J열 |
| year4 | 없음(None 고정) |

보종 정책:

```text
기타(보장성) 고정
```

### 18.9.3 신한 환산율 저장 정책

신한도 기존 conv 보험사와 동일하게 백분율 수치 기준 저장:

| raw 표시 | DB 저장 |
| --- | --- |
| 100.0% | Decimal("100.0") |
| 245.0% | Decimal("245.0") |

Excel percent 셀은 반드시:

```python
if "%" in number_format:
    value *= 100
```

보정 후 저장.

### 18.9.4 dispatcher 등록 FINAL

파일:

```text
commission/services/rate_example_normalizers/__init__.py
commission/services/rate_example_normalizer.py
```

등록 함수명:

```python
build_life_shinhan_conversion_rows
```

dispatcher:

```python
elif example.insurer == "신한":
    normalized_rows.extend(
        build_life_shinhan_conversion_rows(example, wb)
    )
```

### 18.9.5 신한 회귀 체크리스트

검증 항목:

* 일반상품 시트만 정상 정규화
* 건강 시트만 정상 정규화
* C열 공란 carry-forward 정상
* D/E 구분 결합 정상
* D/E 공란 시 직전 구분 전파 정상
* 건강 시트 A열 "주보험"만 적재
* year4 None 저장 정상
* 환산율 % 저장 정상
* 환산율 확인 모달 조회 정상

Excel + PDF 이중 지원.

| 파일 | parser |
| --- | --- |
| .xlsx | build_life_lina_conversion_rows |
| .pdf | build_life_lina_pdf_conversion_rows |

PDF 정책:

* `년납` 포함 행만 정규화
* `년만기` 제외
* 줄바꿈 상품명 병합
* `무배당` 포함 line은 신규 상품명
* continuation line에 `무배당` 포함 시 반드시 제외
* year1~year4 동일 저장
* plan_type 공란 고정
* dedupe key: (insurer, coverage_type, product_name, pay_period, year1)

의존성: `pypdf>=4.0.0`

---


## 18.10 처브생명 FINAL

파일:

```text
commission/services/rate_example_normalizers/life_chubb.py
```

지원 형식:

| 조건 | 값 |
| --- | --- |
| 보험사 | 처브 |
| 파일 | PDF |
| category | conv |

### 18.10.1 PDF 정규화 정책

처브는 PDF 기반 parser 사용.

의존성:

```python
pypdf>=4.0.0
```

원칙:

* PDF 원본은 `example.file.open("rb")` 로만 접근
* public URL/file.url 직접 접근 금지
* "특약" 페이지 등장 시 해당 페이지와 이후 페이지 전체 제외
* 주계약 데이터만 정규화

### 18.10.2 특약 페이지 차단 정책

다음 키워드 등장 시 parser 중단:

```text
■ 특약
```

또는:

```text
특약
```

단:

```text
주계약
```

동시 포함 페이지는 제외하지 않는다.

구현 함수:

```python
_is_rider_page()
```

### 18.10.3 상품명(product_name) 정책 FINAL

raw PDF의 "상품" 컬럼 기준.

정책:

* 줄바꿈은 공백 1칸으로 병합
* 다중 공백 제거
* continuation line 병합
* `무배당` 포함 continuation은 신규 상품으로 처리

예:

```text
Chubb 간편가입 New 수(秀) 종신보험 무배당
(1종/일반납입형, 2종/체감납입형)
```

↓

```text
Chubb 간편가입 New 수(秀) 종신보험 무배당 (1종/일반납입형, 2종/체감납입형)
```

### 18.10.4 1종/2종 분리 정책 FINAL

상품명에:

```text
1종
2종
```

이 동시에 존재하면 동일 row를 복제한다.

예:

```text
Chubb 간편가입 New 수(秀) 종신보험 무배당
(1종/일반납입형, 2종/체감납입형)
```

↓

```text
Chubb 간편가입 New 수(秀) 종신보험 무배당 (1종/일반납입형)
Chubb 간편가입 New 수(秀) 종신보험 무배당 (2종/체감납입형)
```

환산율 정책:

| 상품명 | 사용 환산율 컬럼 |
| --- | --- |
| 1종 포함 | 1종 환산율 |
| 2종 포함 | 2종 환산율 |

### 18.10.5 보종(coverage_type) 정책 FINAL

| 조건 | coverage_type |
| --- | --- |
| 상품명에 종신 포함 | 종신/CI |
| 기타 | 기타(보장성) |

### 18.10.6 구분(plan_type) 정책 FINAL

raw PDF의:

```text
보장금액(FA)
보험료(P)
보험기간(CP)
```

조건을 정규화.

번역 정책:

| raw | 변환 |
| --- | --- |
| FA | 가입금액 |
| P | 보험료 |
| CP | 보험기간 |

금액 정책:

| raw | 변환 |
| --- | --- |
| 20m | 2,000만 |
| 100m | 1억 |

부등호 정책:

| raw | 결과 |
| --- | --- |
| FA≥20m | 가입금액 2,000만 이상 |
| P<10,000원 | 보험료 10,000원 미만 |
| 30m≤FA<100m | 가입금액 3,000만 이상 |

### 18.10.7 PDF continuation row 병합 정책 FINAL

처브 PDF는 table row가 줄 단위로 분리되어 추출될 수 있다.

예:

```text
FA=70m, 100m,
200m 26% 26%
```

정책:

* `200m` 는 독립 row로 저장 금지
* 직전 조건과 결합:

```text
FA=70m, 100m, 200m
```

으로 복원

구현 함수:

```python
_is_incomplete_plan_fragment()
_is_amount_only_continuation()
_merge_plan_fragments()
```

### 18.10.8 placeholder '-' 제거 정책 FINAL

PDF 빈 셀 placeholder:

```text
-
```

는 저장 금지.

예:

| raw | 저장값 |
| --- | --- |
| - P≥10,000원 | P≥10,000원 |
| FA≥100m - | FA≥100m |

구현 함수:

```python
_strip_placeholder_dash()
```

### 18.10.9 납기(pay_period) 정책 FINAL

raw PDF의:

```text
납입기간(PPP)
```

조건을 납기로 변환.

예:

| raw | 결과 |
| --- | --- |
| PPP=7 | 7년 |
| 10≤PPP<15 | 10년 이상 |
| 20≤PPP | 20년 이상 |

### 18.10.10 환산율 저장 정책 FINAL

처브는 raw % 값에 12를 곱하여 저장한다.

예:

| raw | DB 저장 |
| --- | --- |
| 47% | 564 |
| 26% | 312 |
| 11% | 132 |

저장 정책:

```python
year1 = rate * 12
year2 = rate * 12
year3 = rate * 12
year4 = rate * 12
```

### 18.10.11 dispatcher 등록 FINAL

파일:

```text
commission/services/rate_example_normalizers/__init__.py
commission/services/rate_example_normalizer.py
```

등록 함수명:

```python
build_life_chubb_pdf_conversion_rows
```

PDF dispatcher:

```python
if example.insurer == "처브":
    normalized_rows = build_life_chubb_pdf_conversion_rows(example)
```

### 18.10.12 처브 회귀 체크리스트 FINAL

검증 항목:

* 특약 페이지 제외 정상
* PDF normalized_count > 0
* 1종/2종 row 분리 정상
* continuation row 병합 정상
* `200m` 단독 저장 없음
* `- P≥10,000원` 저장 없음
* placeholder '-' 제거 정상
* year1~year4 동일 저장 정상
* raw % × 12 저장 정상
* 환산율 확인 모달 조회 정상

# 19. 전략상품 저장 정책

정규화 row의 `strategy_flag` 필드 사용.

허용값: 전략상품1 / 전략상품2 / 전략상품3 / 전략상품4

저장 API: `commission:rate_example_conversion_strategy_update`

적용 대상: 환산율(conv)만. 지급률(pay)에는 미적용.

---

# 20. Audit 정책

로그 대상: 업로드 / 다운로드 / 삭제 / 전략상품 변경

필수 meta:

* insurer_type / insurer / category
* original_name / normalized_count
* product_kind / normalize_mode

지급률 업로드 meta 예:

```json
{
  "insurer_type": "life",
  "insurer": "",
  "category": "pay",
  "original_name": "지급률.xlsx",
  "normalized_count": 240,
  "product_kind": "",
  "normalize_mode": "replace"
}
```

---

# 21. 보안 원칙

금지:

* file.url 직접 노출
* PDF/Excel 원본 public URL 제공
* except: pass
* 권한 완화
* raw 파일을 static/media 직접 링크로 제공

허용:

* FileResponse 다운로드
* logger.exception 사용
* superuser 유지
* transaction.atomic 사용
* parser 내부: `example.file.open("rb")` 또는 `example.file.path`

---

# 22. 회귀 위험 체크리스트

## 공통

* URL name 변경 없음
* dataset key 유지
* replace/append 정상

## 환산율

* KB 일반상품 / 건강보험 조회 정상
* KDB / IM / ABL / DB / 교보 / 농협 / 동양 조회 정상
* 라이나 xlsx / pdf 조회 정상
* 라이나 pypdf import 정상
* 라이나 PDF normalized_count > 0
* 라이나 PDF 년납 행만 정규화
* 라이나 PDF 줄바꿈 상품명 병합
* 라이나 PDF 상품명 중복 결합 없음
* % 출력 정상
* 병합 셀 전파 정상
* dedupe 정상

## 지급률

* 지급률 업로드 후 normalized_count == 240
* 20개 보험사 전체 row 존재
* col_m36 없는 보험사 None 확인
* col_m37 없는 보험사 None 확인
* col_yr4 없는 보험사 None 확인
* 지급률 확인 모달 조회 정상
* 보험사/상품군 필터 정상
* `-` 표시 정상
* data-pay-list-url dataset 존재

## 마이그레이션

* makemigrations commission 정상
* migrate 정상
* RateExamplePayRow 테이블 생성 확인
* python manage.py check 통과

---

# 23. 절대 금지

## 환산율

* 환산율을 1.26 기준으로 저장
* file.url 직접 노출
* parser를 dispatcher에 재삽입
* except: pass
* DOM id 변경
* dataset key 변경
* normalize_mode 기본값 임의 변경
* 보험사별 정책을 프론트 JS에 하드코딩
* 라이나 PDF: OCR 전제 구현
* 라이나 PDF: 무배당 신규 상품명을 continuation으로 병합
* 라이나 PDF: 년만기 행 정규화
* 교보: `_is_subtype_keyword` 내부 괄호 체크 제거
* 교보: `_should_exclude` 판정 키워드 임의 변경
* 동양: 환산율을 0.7 기준으로 저장
* 동양: 특약 시트 정규화
* 동양: 1~14행 정규화
* 동양: J열 값을 2~4차년에 복제
* 동양: L열 값을 1차년에 저장

## 지급률

* 지급률 모델 필드명에 한글 사용
* col_m36/col_m37/col_yr4 없는 보험사에 0 저장 (반드시 None)
* 지급률 업로드에서 normalize_mode append 허용
* 지급률 업로드에서 보험사 선택 UI 추가
* 지급률 normalizer에서 insurer를 클라이언트에서 받는 구조
* 지급률에 strategy_flag 적용
* 흥국의 col_yr2/col_yr3를 타 보험사와 동일하게 취급

---

# 24. 신규 보험사 추가 표준 절차

## 환산율 신규 보험사

1. raw 파일 구조 확인
2. 파일 형식 결정 (xlsx / pdf / both)
3. `commission/services/rate_example_normalizers/life_<insurer>.py` 생성
4. 공식 함수명 정의
5. 환산율 Decimal 저장 정책 준수
6. `rate_example_normalizers/__init__.py` export 추가
7. `rate_example_normalizer.py` dispatcher 추가
8. `RateExample.LIFE_INSURERS` 목록 추가
9. 업로드 후 normalized_count 검증
10. 회귀 테스트

## 지급률 신규 보험사 추가

지급률 파일이 개정되어 신규 보험사가 추가되는 경우:

1. `rate_example_pay_normalizer.py` 내 해당 그룹 dict에 tuple 추가
2. col_m36/col_m37/col_yr4 없으면 반드시 None
3. 신규 보험사가 특정 회차를 별도 컬럼으로 기재한다면
   `RateExamplePayRow` 모델에 신규 필드 추가 후 마이그레이션

---

# 25. 최소 검증 시나리오

```bash
python manage.py check
```

지급률 업로드 후:

```powershell
python manage.py shell -c "
from commission.models import RateExamplePayRow
print('총 행수:', RateExamplePayRow.objects.count())
print('보험사 목록:', list(RateExamplePayRow.objects.values_list('insurer', flat=True).distinct()))
print('col_m36 있는 보험사:', list(RateExamplePayRow.objects.exclude(col_m36=None).values_list('insurer', flat=True).distinct()))
print('col_m37 있는 보험사:', list(RateExamplePayRow.objects.exclude(col_m37=None).values_list('insurer', flat=True).distinct()))
print('col_yr4 있는 보험사:', list(RateExamplePayRow.objects.exclude(col_yr4=None).values_list('insurer', flat=True).distinct()))
"
```

브라우저 검증:

1. superuser 로그인
2. `/commission/rate-examples/` 접속
3. 지급률 업데이트 버튼 클릭
4. 지급률.xlsx 업로드
5. 응답 normalized_count == 240 확인
6. 지급률 확인 버튼 클릭
7. 조회 버튼 클릭
8. 보험사/상품군 필터 동작 확인
9. ABL 36회/37회 컬럼 `-` 표시 확인
10. 삼성 37회 컬럼 값 존재 확인
11. 한화 36회/4차년 컬럼 값 존재 확인

---

# 26. 수수료 계산 엔진 FINAL (2026-05 업데이트)

## 26.1 계산 구조 개요

수수료 계산 엔진은 다음 우선순위로 동작한다.

```text
1. 보험사 판정
2. 환산율 row 조회(conv)
3. 지급률 row 조회(pay)
4. 전략상품 여부 판정
5. 회차별 금액 계산
6. 총량 계산
```

파일:

```text
commission/services/rate_example_calculator.py
```

---

## 26.2 보험사별 계산 분기 FINAL

| 보험사 | 계산 방식 |
| --- | --- |
| 일반 보험사 | 환산율 × 지급률 × 수수료율 |
| DB | 별도 계산 로직 |
| IBK | 지급률만 사용 (환산율 미사용) |

### 일반 보험사 목록

```text
ABL
삼성
신한
하나
IM
KB
농협
라이나
KDB
미래
처브
한화
카디프
동양
메트
흥국
푸본현대
교보
```

### 중요 변경 사항

기존:

```text
처브 / 카디프 계산 제외
```

변경 후:

```text
처브 / 카디프도 일반 보험사 로직으로 계산
```

---

## 26.3 일반 보험사 계산식 FINAL

### 기본 계산식

```text
보험료 × 환산율 × 지급률 × 수수료율
```

### 회차별 계산식

| 구간 | 계산 |
| --- | --- |
| 익월 | 보험료 × year1 × col_first × 수수료율 |
| 13회 | 보험료 × year2 × col_m13 × 수수료율 |
| 2차년 | 보험료 × year2 × col_yr2 × 수수료율 |
| 3차년 | 보험료 × year3 × col_yr3 × 수수료율 |
| 36회 | 보험료 × year3 × col_m36 × 수수료율 |
| 37회 | 보험료 × year4 × col_m37 × 수수료율 |
| 4차년 | 보험료 × year4 × col_yr4 × 수수료율 |

### 총량 계산

```text
익월 소계 = 익월

계속 소계 =
13회 +
2차년 +
3차년 +
36회 +
37회 +
4차년

총 금액 =
익월 소계 + 계속 소계
```

---

## 26.4 전략상품 지급률 우선 적용 FINAL

### 기존 정책

기존에는 지급률 조회 시:

```python
coverage_type
```

만 사용하였다.

예:

```text
종신/CI
연금
기타(보장성)
```

### 변경 정책 FINAL

환산율 row의:

```python
strategy_flag
```

값이 존재하면,
보종보다 전략상품 지급률을 우선 사용한다.

### 우선순위

```text
1순위:
strategy_flag 존재
→ pay.coverage_type = strategy_flag

2순위:
strategy_flag 없음
→ pay.coverage_type = coverage_type
```

### 예시

환산율 row:

```text
보험사: ABL
보종: 종신/CI
전략유무: 전략상품1
```

↓

지급률 조회:

```text
보험사 = ABL
상품군 = 전략상품1
```

### 전략상품 허용값

```text
전략상품1
전략상품2
전략상품3
전략상품4
```

---

## 26.5 IBK 계산 로직 FINAL

### 핵심 정책

IBK는:

```text
환산율(conv)을 사용하지 않는다.
```

지급률(pay) 테이블의 상품군만 사용한다.

### 상품군 구조

지급률 정규화 저장:

```text
coverage_type = "[IBK]상품군명"
```

프론트 표시:

```text
상품군명만 표시
```

### UI 정책 FINAL

보험사 = IBK 선택 시:

| 항목 | 정책 |
| --- | --- |
| 상품명 | IBK 상품군 dropdown |
| 구분 | disabled |
| 납기 | disabled |
| 환산율 조회 | 사용 안 함 |

---

## 26.6 IBK 계산식 FINAL

### 중요

IBK는:

```text
보험료 × 지급률 × 수수료율
```

만 사용한다.

환산율 multiplier 사용 금지.

### 회차별 계산식 FINAL

| 구간 | 계산 |
| --- | --- |
| 익월 | 보험료 × col_first × 수수료율 |
| 익월소계 | 익월 금액 그대로 |
| 13회 | 보험료 × col_m13 × 수수료율 |
| 2차년 | 보험료 × col_yr2 × 수수료율 |
| 3차년 | 보험료 × col_yr3 × 수수료율 |
| 36회 | 보험료 × col_m36 × 수수료율 |
| 37회 | 보험료 × col_m37 × 수수료율 |
| 4차년 | 보험료 × col_yr4 × 수수료율 |

### 중요 수정 사항

기존 잘못된 설계:

```text
익월 = col_yr1 사용
```

최종 정책:

```text
익월 = col_first 사용
```

즉:

```python
next_month_first = premium * pay.col_first * commission_rate
```

이 최종 기준이다.

---

## 26.7 IBK 지급률 컬럼 정책 FINAL

| 컬럼 | 의미 |
| --- | --- |
| col_first | 초회 |
| col_m13 | 13회 |
| col_yr2 | 2차년구간 |
| col_yr3 | 3차년구간 |
| col_m36 | 36회 |
| col_m37 | 37회 |
| col_yr4 | 4차년구간 |

현재 지급률 파일에 값이 없는 경우:

```python
None
```

저장 후 UI에서:

```text
-
```

표시.

0 저장 금지.

---

## 26.8 옵션 조회 정책 FINAL

파일:

```text
commission/services/rate_example_options.py
```

### 일반 보험사

```text
환산율(conv) master 기준 조회
```

흐름:

```text
보험사
→ 상품명
→ 구분
→ 납기
```

### IBK

```text
지급률(pay) master 기준 조회
```

흐름:

```text
보험사=IBK
→ 상품군
```

구분/납기 조회 없음.

---

## 26.9 프론트 JS 정책 FINAL

파일:

```text
static/js/commission/rate_example.js
```

### IBK 선택 시

```javascript
plan.disabled = true;
period.disabled = true;
```

### 일반 보험사 복귀 시

```javascript
plan.disabled = false;
period.disabled = false;
```

### placeholder 정책

| 상태 | placeholder |
| --- | --- |
| 일반 보험사 | 상품명 |
| IBK | IBK 상품군 |

---

## 26.10 API payload 정책 FINAL

### 일반 보험사

```json
{
  "insurer": "ABL",
  "product_name": "상품명",
  "plan_type": "구분",
  "pay_period": "20년",
  "premium": "100000",
  "commission_rate": "70"
}
```

### IBK

```json
{
  "insurer": "IBK",
  "product_name": "종신형",
  "plan_type": "",
  "pay_period": "",
  "premium": "100000",
  "commission_rate": "70"
}
```

---

## 26.11 회귀 위험 체크리스트 FINAL

### 일반 보험사

- 처브 계산 정상
- 카디프 계산 정상
- 전략상품 지급률 우선 적용 정상
- strategy_flag 없는 경우 coverage_type fallback 정상

### IBK

- 상품군 dropdown 정상
- 구분 disabled 정상
- 납기 disabled 정상
- col_first 기반 익월 계산 정상
- 환산율 미사용 정상
- 36회/37회/4차년 None 표시 정상

### DB

- 기존 제외 정책 유지
