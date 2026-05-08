# django_ma 수수료 예시표(RateExample) 개발 가이드 FINAL

> 목적: 추후 전체 세부 코드를 다시 제공하지 않아도, 수수료 예시표 기능의 구조·계약·확장 규칙을 빠르게 이해하고 안전하게 디벨롭할 수 있도록 정리한 최종 기준 문서입니다.
>
> 적용 범위:
>
> - `commission` 앱의 예시표 업로드
> - 원본 파일 관리
> - 환산률/수정률 정규화
> - 정규화 데이터 조회/필터/전략유무 저장
> - 보험사별 raw xlsx normalizer 확장
>
> 기준일: 2026-05-08
>
> 최신 반영:
>
> - IM생명 환산률/수정률 정규화 추가
> - 환산률 저장 기준 통일(백분율 수치 기준)
> - 환산률 모달 `%` 출력 정책 추가
> - 납기 문자열 보존 정책 추가
> - IM `미판매` row 제외 정책 추가

---

# 1. 기능 책임 요약

수수료 예시표 기능은 보험사별 raw 예시표 파일을 업로드하고,
보험사별 raw xlsx를 표준 정규화 테이블(`RateExampleConversionRow`)로 변환하여
조회·검색·전략상품 지정·향후 수수료 계산 엔진에 활용하는 기능입니다.

핵심 책임:

1. 원본 파일 메타 저장
2. 원본 파일 다운로드
3. 업로드 파일 검증
4. 보험사별 raw xlsx 정규화
5. 정규화 master 교체
6. 환산률/수정률 확인 모달 조회
7. 전략상품 저장
8. 업로드/다운로드/삭제 감사 로그 기록
9. 향후 계산 엔진에서 사용할 환산률 데이터 표준화

---

# 2. URL 계약

파일:

```text
commission/urls.py
```

기존 URL name 변경 금지.

| URL name | route | 역할 |
|---|---|---|
| `commission:rate_example_home` | `/commission/rate-examples/` | 메인 페이지 |
| `commission:rate_example_upload` | `/commission/rate-examples/upload/` | 파일 업로드 |
| `commission:rate_example_download` | `/commission/rate-examples/<pk>/download/` | 원본 다운로드 |
| `commission:rate_example_delete` | `/commission/rate-examples/<pk>/delete/` | 원본 삭제 |
| `commission:rate_example_conversion_list` | `/commission/rate-examples/conversions/` | 정규화 row 조회 |
| `commission:rate_example_conversion_strategy_update` | `/commission/rate-examples/conversions/strategy/` | 전략유무 저장 |

운영 규칙:

- URL name 변경 금지
- 기존 route 변경 금지
- 신규 보험사 추가 시 URL 추가 불필요
- 보험사별 normalizer만 추가

---

# 3. 모델 구조

파일:

```text
commission/models.py
```

## 3.1 RateExample

원본 파일 메타 모델.

주요 필드:

| 필드 | 설명 |
|---|---|
| insurer_type | 손생구분 (`life`, `nonlife`) |
| category | `conv`, `pay` |
| insurer | 보험사 |
| file | 원본 파일 |
| original_name | 업로드 원본명 |
| uploaded_by | 업로더 |
| created_at | 등록시각 |

현재 생보 환산률/수정률 지원 보험사:

- ABL
- DB
- IM

보안:

- `file.url` 직접 노출 금지
- 다운로드는 download view 경유
- `open_fileresponse_from_fieldfile()` 사용

## 3.2 RateExampleConversionRow

정규화 master 테이블.

주요 필드:

| 필드 | 설명 |
|---|---|
| source_file | 원본 FK |
| source_sheet | 원본 시트 |
| source_row_no | 원본 행 |
| insurer_type | 손생구분 |
| category | conv/pay |
| insurer | 보험사 |
| coverage_type | 보종 |
| strategy_flag | 전략유무 |
| product_name | 상품명 |
| plan_type | 구분 |
| pay_period | 납기 |
| year1~year4 | 환산률/수정률 |

중요 정책:

- 보험사 단위 replace-all
- 업로드 시 기존 row 전체 삭제 후 재생성
- row id 유지되지 않음
- strategy_flag 유지되지 않음

---

# 4. 환산률 저장 기준 (매우 중요)

## 4.1 현재 FINAL 저장 기준

모든 보험사의 환산률은
"백분율 수치 기준"으로 저장한다.

예:

| raw 표시 | DB 저장 |
|---|---|
| 100.0% | Decimal("100.0") |
| 126% | Decimal("126") |
| 596.0% | Decimal("596.0") |

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

## 4.2 계산 엔진 적용 기준

향후 계산식:

```python
보험료 × 환산률 × 지급률 × 수수료율
```

적용 시 반드시:

```python
conversion_rate = row.year1 / Decimal("100")
```

형태로 비례 적용한다.

예:

```python
Decimal("126") / Decimal("100") == Decimal("1.26")
```

---

## 4.3 화면 출력 정책

환산률/수정률 확인 모달에서는:

```text
126%
596.0%
100.0%
```

형태로 출력한다.

즉:

- DB 저장값은 숫자
- UI는 `%` 포함 문자열

---

# 5. 정규화 오케스트레이터

파일:

```text
commission/services/rate_example_normalizer.py
```

역할:

- 정규화 대상 판단
- workbook 로드
- 보험사별 parser 호출
- 기존 master 삭제
- 신규 bulk insert

현재 지원:

| insurer | 지원 |
|---|---|
| ABL | O |
| DB | O |
| IM | O |

현재 구조:

```python
if example.insurer == "ABL":
    ...
elif example.insurer == "DB":
    ...
elif example.insurer == "IM":
    ...
```

replace-all 정책:

```python
RateExampleConversionRow.objects.filter(
    insurer_type=...,
    category=...,
    insurer=...,
).delete()
```

이후:

```python
bulk_create(...)
```

---

# 6. normalizer 패키지 구조

```text
commission/services/rate_example_normalizers/
├── __init__.py
├── life_abl.py
├── life_db.py
└── life_im.py
```

규칙:

- `<손생>_<보험사>.py`
- public entrypoint만 export
- 내부 helper는 private 유지

예:

```python
def build_life_im_conversion_rows(...):
    ...
```

---

# 7. ABL 정규화 규칙

파일:

```text
life_abl.py
```

## 대상

- 생명보험
- 환산률/수정률
- xlsx

## 저장 기준

ABL도 현재는 백분율 수치 기준 저장.

예:

```text
192.0% → Decimal("192.0")
```

## 화면 출력

```text
192.0%
324.0%
```

## 보종 판정

| 조건 | coverage_type |
|---|---|
| 상품명에 종신 포함 | 종신/CI |
| 그 외 | 기타(보장성) |

---

# 8. DB 정규화 규칙

파일:

```text
life_db.py
```

## 제외 시트

- 특약
- 방카교차

## 첫 번째 테이블만 정규화

두 번째 테이블 시작 시 종료.

## 보종 판정

| 조건 | 보종 |
|---|---|
| 종신 포함 | 종신/CI |
| 연금 포함 | 연금 |
| 경영 포함 | CEO정기 |
| 기타 | 기타(보장성) |

## 저장 기준

DB도 백분율 수치 기준 저장.

예:

```text
596.0% → Decimal("596.0")
```

---

# 9. IM 정규화 규칙 (신규 FINAL)

파일:

```text
life_im.py
```

---

## 9.1 대상

| 조건 | 값 |
|---|---|
| insurer_type | life |
| category | conv |
| insurer | IM |
| 파일 | .xlsx |

---

## 9.2 사용 시트

반드시 첫 번째 시트:

```text
(총괄)환산성적표
```

시트명이 다르면:

```python
raise ValueError(...)
```

발생.

---

## 9.3 정규화 대상 행

E열 `구분` 값이:

```text
주계약
```

인 행만 정규화.

그 외:

- 특약
- 빈 행
- 안내 row

등은 제외.

---

## 9.4 미판매 제외 정책

L열 `기본형` 값이:

```text
미판매
```

이면 정규화 제외.

즉:

```python
if basic_rate_raw == "미판매":
    continue
```

---

## 9.5 보종 판정 규칙

기준 컬럼:

```text
F열 주계약
```

판정 우선순위:

| 조건 | coverage_type |
|---|---|
| 변액 포함 | 변액연금 |
| 종신 포함 | 종신/CI |
| 연금 포함 | 연금 |
| 기타 | 기타(보장성) |

주의:

```text
변액연금
```

은 반드시:

```text
연금
```

보다 우선 판정.

---

## 9.6 컬럼 매핑

| 정규화 필드 | raw |
|---|---|
| insurer | IM |
| coverage_type | F열 기반 |
| strategy_flag | H열 GA |
| product_name | F열 |
| plan_type | K열 |
| pay_period | J열 |
| year1~year4 | L열 기본형 |

---

## 9.7 전략상품 매핑

| raw | 저장 |
|---|---|
| 전략상품I | 전략상품1 |
| 전략상품II | 전략상품2 |
| 전략상품III | 전략상품3 |
| 전략상품IV | 전략상품4 |

유니코드 로마숫자도 허용:

- Ⅰ
- Ⅱ
- Ⅲ
- Ⅳ

---

## 9.8 납기 문자열 보존 정책

IM raw에서는:

```text
20년 이상
```

처럼 표시되지만,
openpyxl은 숫자만 읽는 경우가 있다.

따라서:

```python
_format_excel_display_text()
```

helper를 사용해 표시 문자열 기준으로 보정한다.

최종 저장:

```text
20년 이상
15년납
```

등 raw 의미 유지.

---

## 9.9 환산률 저장 기준

L열 기본형:

```text
126%
```

이면 DB에는:

```python
Decimal("126")
```

저장.

즉:

```text
126% ≠ 1.26 저장
```

이다.

---

# 10. API 구조

파일:

```text
commission/views/api_rate_example.py
```

모든 업로드/삭제/조회는:

```python
@grade_required("superuser")
```

기준 유지.

---

# 11. 환산률 조회 API

파일:

```text
commission/views/api_rate_example_conversion.py
```

조회 응답:

```json
{
  "year1": "126%"
}
```

형태.

현재 FINAL 정책:

- ABL → `%` 출력
- DB → `%` 출력
- IM → `%` 출력

---

# 12. 프론트 구조

파일:

```text
static/js/commission/rate_example_home.js
```

root:

```javascript
#rate-example-root
```

중복 초기화 방지:

```javascript
root.dataset.inited
```

보험사 목록:

```javascript
life-insurers-data
```

json_script 기반.

따라서:

```python
RateExample.LIFE_INSURERS
```

수정 시 JS 수정 없이 드롭다운 반영 가능.

---

# 13. 템플릿 구조

파일:

```text
rate_example_home.html
```

중요 DOM:

| id | 역할 |
|---|---|
| rate-example-root | root |
| rateExampleUploadModal | 업로드 모달 |
| rateExampleConvModal | 조회 모달 |
| re-conv-tbody | 결과 tbody |

주의:

- DOM id 변경 금지
- dataset key 변경 금지
- JS selector 변경 시 회귀 위험 큼

---

# 14. 보안 원칙

금지:

```html
{{ example.file.url }}
```

허용:

```django
{% url 'commission:rate_example_download' pk %}
```

업로드/삭제/전략 변경은 superuser 유지.

---

# 15. 신규 보험사 추가 절차

예:

```text
삼성생명
```

절차:

1. LIFE_INSURERS 추가
2. life_samsung.py 생성
3. normalizer import
4. insurer set 추가
5. elif 분기 추가
6. 회귀 테스트

---

# 16. 최소 검증 시나리오

## Django check

```bash
python manage.py check
```

## 업로드 검증

- ABL 업로드
- DB 업로드
- IM 업로드

모두:

```text
normalized_count > 0
```

확인.

---

## 조회 검증

환산률/수정률 모달:

- ABL 조회
- DB 조회
- IM 조회

확인 항목:

| 항목 | 기대값 |
|---|---|
| 환산률 | 126% 형태 |
| 납기 | 20년 이상 유지 |
| 전략상품 | 전략상품1~4 |
| IM 미판매 | 제외 |

---

## 계산 검증

반드시:

```python
row.year1 / Decimal("100")
```

형태로 계산.

---

# 17. 회귀 위험 체크리스트

| 항목 | 확인 |
|---|---|
| URL name 변경 없음 | □ |
| dataset key 유지 | □ |
| ABL 조회 정상 | □ |
| DB 조회 정상 | □ |
| IM 조회 정상 | □ |
| % 출력 정상 | □ |
| IM 미판매 제외 정상 | □ |
| 납기 문자열 유지 | □ |
| 전략상품 저장 정상 | □ |
| python manage.py check 통과 | □ |

---

# 18. 자주 발생한 문제

## 18.1 1.26처럼 표시됨

원인:

- old decimal 정책
- `%` 출력 helper 미적용

현재 FINAL:

```text
126%
```

출력.

---

## 18.2 IM 납기가 숫자만 보임

원인:

- openpyxl이 표시 문자열 대신 숫자만 읽음

해결:

```python
_format_excel_display_text()
```

사용.

---

## 18.3 IM 미판매 상품 노출됨

원인:

```text
미판매
```

row 제외 조건 미적용.

현재 FINAL:

```python
if basic_rate_raw == "미판매":
    continue
```

---

# 19. 향후 개선 후보

## 전략유무 보존

현재 replace-all 구조로 인해 초기화됨.

개선 후보:

- merge/upsert
- key table
- 전략 rule table

---

## registry 구조

현재:

```python
if insurer == ...
```

향후:

```python
NORMALIZER_REGISTRY
```

가능.

---

# 20. 절대 금지

- file.url 직접 노출
- superuser 권한 완화
- URL name 변경
- dataset key 변경
- DOM id 변경
- 정규화 실패를 성공처럼 처리
- 기존 보험사 회귀 확인 없이 신규 보험사 추가
- 환산률을 1.26 기준으로 저장하도록 되돌리기

