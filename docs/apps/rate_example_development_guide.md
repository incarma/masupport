# django_ma 수수료 예시표(RateExample) 개발 가이드

> 목적: 추후 전체 세부 코드를 다시 제공하지 않아도, 수수료 예시표 기능의 구조·계약·확장 규칙을 빠르게 이해하고 안전하게 디벨롭할 수 있도록 정리한 기준 문서입니다.  
> 적용 범위: `commission` 앱의 예시표 업로드, 원본 파일 관리, 환산률/수정률 정규화, 정규화 데이터 조회/필터/전략유무 저장 UI.  
> 기준일: 2026-05-08

---

## 1. 기능 책임 요약

수수료 예시표 기능은 보험사별 raw 예시표 파일을 업로드하고, 일부 보험사의 `환산률/수정률` raw xlsx를 표준 정규화 테이블(`RateExampleConversionRow`)로 변환해 조회·필터·전략상품 지정에 활용하는 기능입니다.

핵심 책임은 다음과 같습니다.

1. 원본 파일 메타 저장 및 다운로드
2. 업로드 파일 검증
3. 보험사별 raw xlsx 정규화
4. 정규화 master 데이터 교체
5. 환산률/수정률 확인 모달 조회
6. 정규화 row별 전략유무 저장
7. 업로드/다운로드/삭제/전략 변경 감사 로그 기록

---

## 2. 관련 URL 계약

파일: `commission/urls.py`

예시표 관련 URL name은 변경하지 않습니다. 기존 URL name은 템플릿, JS, reverse, 감사 흐름에서 사용될 수 있으므로 신규 기능은 “추가”만 원칙으로 합니다.

| URL name | route | method | 역할 |
|---|---|---:|---|
| `commission:rate_example_home` | `/commission/rate-examples/` | GET | 예시표 메인 페이지 |
| `commission:rate_example_upload` | `/commission/rate-examples/upload/` | POST | 예시표 파일 업로드 |
| `commission:rate_example_download` | `/commission/rate-examples/<int:pk>/download/` | GET | 원본 파일 다운로드 |
| `commission:rate_example_delete` | `/commission/rate-examples/<int:pk>/delete/` | POST | 원본 파일 삭제 |
| `commission:rate_example_conversion_list` | `/commission/rate-examples/conversions/` | GET | 정규화 row 조회 |
| `commission:rate_example_conversion_strategy_update` | `/commission/rate-examples/conversions/strategy/` | POST | 전략유무 저장 |

운영 원칙:

- URL name 변경 금지
- 기존 route 변경 금지
- 신규 보험사 정규화 추가 시 URL 추가 불필요
- 신규 API가 반드시 필요한 경우에만 기존 URL 하위에 추가

---

## 3. 모델 구조

파일: `commission/models.py`

### 3.1 `RateExample`

예시표 원본 파일 메타 모델입니다.

주요 필드:

| 필드 | 설명 |
|---|---|
| `insurer_type` | 손생구분. `life`, `nonlife` |
| `category` | 구분. `conv` = 환산률/수정률, `pay` = 지급률 |
| `insurer` | 보험사명. 예: `ABL`, `DB` |
| `file` | 원본 첨부파일 |
| `original_name` | 업로드 당시 원본 파일명 |
| `uploaded_by` | 업로더 |
| `created_at` | 등록일시 |

상수:

| 상수 | 의미 |
|---|---|
| `TYPE_LIFE = "life"` | 생명보험 |
| `TYPE_NONLIFE = "nonlife"` | 손해보험 |
| `CAT_CONV = "conv"` | 환산률/수정률 |
| `CAT_PAY = "pay"` | 지급률 |
| `LIFE_INSURERS` | 생명보험 허용 보험사 목록 |
| `NONLIFE_INSURERS` | 손해보험 허용 보험사 목록 |
| `ALLOWED_EXTENSIONS` | `.pdf`, `.xls`, `.xlsx` |
| `ALLOWED_MIME_TYPES` | PDF, XLS, XLSX MIME |
| `MAX_FILE_SIZE` | 20MB |

보안 원칙:

- `file.url` 직접 노출 금지
- 다운로드는 반드시 `rate_example_download` 뷰 경유
- 뷰 내부에서도 `open_fileresponse_from_fieldfile()` 사용

### 3.2 `RateExampleConversionRow`

환산률/수정률 정규화 master 모델입니다.

주요 필드:

| 필드 | 설명 |
|---|---|
| `source_file` | 원본 `RateExample` FK |
| `source_sheet` | 원본 시트명 |
| `source_row_no` | 원본 행 번호 |
| `insurer_type` | 손생구분 |
| `category` | 구분 |
| `insurer` | 보험사 |
| `coverage_type` | 보종 |
| `strategy_flag` | 전략유무. 예: `전략상품1` |
| `product_name` | 상품명 |
| `plan_type` | 구분 |
| `pay_period` | 납기 |
| `year1`~`year4` | 1~4차년 환산률/수정률 |

정렬 기준:

```python
ordering = [
    "insurer_type",
    "insurer",
    "coverage_type",
    "product_name",
    "pay_period",
    "id",
]
```

조회용 인덱스:

- `idx_re_conv_scope`: `insurer_type`, `category`, `insurer`
- `idx_re_conv_source`: `source_file`, `source_sheet`

중요:

- 현재 정규화 master는 “보험사 + 손생구분 + category” 범위 단위로 전체 교체됩니다.
- `product_name + plan_type + pay_period` 기준 upsert 방식이 아닙니다.
- 따라서 새 raw 업로드 시 기존 row id와 `strategy_flag`는 보존되지 않습니다.

---

## 4. 서비스 레이어

### 4.1 업로드 서비스

파일: `commission/services/rate_example.py`

클래스:

```python
class RateExampleService:
```

주요 메서드:

| 메서드 | 역할 |
|---|---|
| `_validate_file(uploaded_file)` | 확장자, MIME, 용량 검증 |
| `create(...)` | 파일 메타 생성 + 정규화 호출 |
| `delete(instance, actor)` | 파일 물리 삭제 + DB 삭제 |
| `list_all()` | 목록 조회 |

`create()` 흐름:

1. `insurer_type` 검증
2. `category` 검증
3. 보험사 허용 목록 검증
4. 파일 확장자/MIME/용량 검증
5. `RateExample.objects.create(...)`
6. `normalize_rate_example(instance)` 호출
7. `normalized_count` 반환

트랜잭션:

- `create()`는 `@transaction.atomic`
- 정규화 중 예외 발생 시 원본 파일 메타와 정규화 row 생성이 rollback됩니다.

주의:

- 뷰에서 직접 ORM으로 `RateExample`을 생성하지 않습니다.
- 반드시 `RateExampleService.create()`를 경유합니다.

---

## 5. 정규화 오케스트레이터

파일: `commission/services/rate_example_normalizer.py`

역할:

- 정규화 대상 여부 판단
- xlsx 여부 판단
- workbook 로드
- 보험사별 normalizer 분기
- 기존 정규화 master 삭제
- 신규 row bulk insert

현재 지원 대상:

| insurer_type | category | insurer | 파일 |
|---|---|---|---|
| `life` | `conv` | `ABL` | `.xlsx` |
| `life` | `conv` | `DB` | `.xlsx` |

처리 흐름:

```python
if not (
    example.insurer_type == RateExample.TYPE_LIFE
    and example.category == RateExample.CAT_CONV
    and example.insurer in {"ABL", "DB"}
):
    return 0
```

```python
wb = load_workbook(example.file.path, data_only=True, read_only=True)
```

```python
if example.insurer == "ABL":
    normalized_rows.extend(build_life_abl_conversion_rows(example, wb))
elif example.insurer == "DB":
    normalized_rows.extend(build_life_db_conversion_rows(example, wb))
```

정규화 master 교체:

```python
RateExampleConversionRow.objects.filter(
    insurer_type=example.insurer_type,
    category=example.category,
    insurer=example.insurer,
).delete()

if normalized_rows:
    RateExampleConversionRow.objects.bulk_create(normalized_rows, batch_size=500)
```

중요 운영 정책:

- 기존 데이터는 보험사 단위로 전체 삭제 후 새 raw 기준 재생성
- 새 raw에 없는 상품은 삭제 효과 발생
- 새 raw에 있는 신규 상품은 추가 효과 발생
- 동일 상품의 row id는 유지되지 않음
- row별 수동값(`strategy_flag`) 유지가 필요하면 향후 merge/upsert 구조로 변경해야 함

---

## 6. 보험사별 normalizer 패키지 구조

목표 구조:

```text
commission/services/rate_example_normalizers/
├── __init__.py
├── life_abl.py
└── life_db.py
```

패턴:

- 파일명은 `<손생>_<보험사>` 형식 사용
- 생명보험 ABL → `life_abl.py`
- 생명보험 DB → `life_db.py`
- 손해보험 DB를 추가한다면 → `nonlife_db.py` 형태 권장

각 normalizer는 다음 public entrypoint를 제공합니다.

```python
def build_life_abl_conversion_rows(example: RateExample, wb: Workbook) -> list[RateExampleConversionRow]:
    ...
```

```python
def build_life_db_conversion_rows(example: RateExample, wb: Workbook) -> list[RateExampleConversionRow]:
    ...
```

오케스트레이터는 public entrypoint만 import합니다. 내부 `_normalize_*`, `_to_decimal`, `_clean_text` 등은 모듈 내부 private helper로 유지합니다.

---

## 7. ABL생명 정규화 규칙

파일: `commission/services/rate_example_normalizers/life_abl.py`

### 7.1 대상

| 조건 | 값 |
|---|---|
| `insurer_type` | `life` |
| `category` | `conv` |
| `insurer` | `ABL` |
| 파일 | `.xlsx` |

### 7.2 필수 시트

| 상수 | 시트명 |
|---|---|
| `SHEET_ABL_SAVING` | `주계약(저축성)` |
| `SHEET_ABL_PROTECTION` | `주계약(보장성)_12개월 선지급` |

두 시트 중 하나라도 없으면 `ValueError`를 발생시켜 transaction rollback을 유도합니다.

### 7.3 저축성 시트 매핑

| 정규화 필드 | 원본 |
|---|---|
| `insurer` | `ABL` |
| `coverage_type` | `연금` 고정 |
| `product_name` | A열 |
| `plan_type` | B열 |
| `pay_period` | C열 |
| `year1` | D열 |
| `year2` | E열 |
| `year3` | F열 |
| `year4` | `None` |

특징:

- 시작 행: 5행
- 상품명/구분이 비어 있으면 직전 값을 이어받음
- 납기와 환산률이 모두 없으면 제외

### 7.4 보장성 시트 매핑

| 정규화 필드 | 원본 |
|---|---|
| `insurer` | `ABL` |
| `coverage_type` | 상품명에 `종신` 포함 시 `종신/CI`, 아니면 `기타(보장성)` |
| `product_name` | A열 |
| `plan_type` | B열 |
| `pay_period` | E열 |
| `year1` | F열 |
| `year2` | G열 |
| `year3` | H열 |
| `year4` | I열 |

특징:

- 시작 행: 5행
- 상품명/구분이 비어 있으면 직전 값을 이어받음
- 납기와 환산률이 모두 없으면 제외

---

## 8. DB생명 정규화 규칙

파일: `commission/services/rate_example_normalizers/life_db.py`

### 8.1 대상

| 조건 | 값 |
|---|---|
| `insurer_type` | `life` |
| `category` | `conv` |
| `insurer` | `DB` |
| 파일 | `.xlsx` |

### 8.2 제외 시트

시트명에 아래 키워드가 포함되면 정규화 제외:

- `특약`
- `방카교차`

### 8.3 첫 번째 테이블만 정규화

각 시트에서 첫 번째 구분/납기/연차 테이블만 정규화합니다.

정규화 중 아래 키워드가 나오면 두 번째 테이블로 판단하고 종료:

- `특약`
- `의무부가`

### 8.4 상품명

- 각 시트 A1 셀 사용
- `□` 제거
- 공백 trim

### 8.5 보종 판정

보종은 시트명이 아니라 A1 상품명 기준으로 판단합니다.

| A1 상품명 조건 | `coverage_type` |
|---|---|
| `종신` 포함 | `종신/CI` |
| `연금` 포함 | `연금` |
| `경영` 포함 | `CEO정기` |
| 그 외 | `기타(보장성)` |

### 8.6 컬럼 매핑

DB raw는 2줄 헤더 구조입니다.

예:

- 헤더 1행차: A=`구분`, B=`납기`, C=`성적률`
- 헤더 2행차: C=`1차년`, D=`2차년`, E=`3차년`, F=`계` 또는 `4차년`

정규화 매핑:

| 정규화 필드 | 원본 |
|---|---|
| `insurer` | `DB` |
| `coverage_type` | A1 상품명 기반 |
| `product_name` | A1 |
| `plan_type` | A열 |
| `pay_period` | B열 |
| `year1` | C열 |
| `year2` | D열 |
| `year3` | E열 |
| `year4` | F열. 단, F열 헤더가 `계`이면 제외 |

특징:

- A열 구분이 비어 있으면 직전 구분을 이어받음
- 빈 행 또는 특약/의무부가 테이블 시작 시 첫 번째 테이블 종료
- 판매상품목록처럼 정규화 테이블이 없는 시트는 로그만 남기고 skip

---

## 9. API View

파일: `commission/views/api_rate_example.py`

### 9.1 업로드

```python
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_upload(request):
    ...
```

특징:

- superuser 전용 고정
- 페이지 권한이 확장되어도 이 데코레이터는 변경하지 않음
- `RateExampleService.create()` 경유
- 성공 시 `normalized_count` 반환
- `ACTION.COMMISSION_RATE_EXAMPLE_UPLOAD` 감사 로그 기록

응답 예:

```json
{
  "ok": true,
  "message": "파일이 등록되었습니다.",
  "data": {
    "normalized_count": 123
  }
}
```

### 9.2 다운로드

```python
@login_required
@grade_required("superuser", forbidden_template=None)
def rate_example_download(request, pk):
    ...
```

특징:

- superuser 전용 고정
- `open_fileresponse_from_fieldfile()` 사용
- 파일 직접 URL 노출 금지
- 성공/실패 감사 로그 기록

### 9.3 삭제

```python
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_delete(request, pk):
    ...
```

특징:

- superuser 전용 고정
- `RateExampleService.delete()` 경유
- 원본 파일 물리 삭제
- `conversion_rows`는 FK CASCADE로 함께 삭제
- 감사 로그 기록

---

## 10. 정규화 데이터 조회/전략유무 API

파일: `commission/views/api_rate_example_conversion.py`

### 10.1 정규화 row 조회

```python
@login_required
@grade_required("superuser", forbidden_template=None)
@require_GET
def rate_example_conversion_list(request):
    ...
```

GET 파라미터:

| 파라미터 | 값 |
|---|---|
| `insurer_type` | `life` 또는 `nonlife` |
| `insurer` | 보험사명 |

고정 category:

```python
category = RateExample.CAT_CONV
```

조회 조건:

```python
RateExampleConversionRow.objects.filter(
    insurer_type=insurer_type,
    category=category,
    insurer=insurer,
)
```

정렬:

```python
.order_by("coverage_type", "product_name", "plan_type", "pay_period", "id")
```

응답 data:

| key | 설명 |
|---|---|
| `rows` | 정규화 row 목록 |
| `count` | row 수 |
| `last_updated_at` | 마지막 업로드 시각 |
| `last_updated_by` | 업로더명 |
| `source_file_name` | 원본 파일명 |

### 10.2 전략유무 저장

```python
@login_required
@grade_required("superuser", forbidden_template=None)
@require_POST
def rate_example_conversion_strategy_update(request):
    ...
```

POST 파라미터:

| 파라미터 | 설명 |
|---|---|
| `id` | `RateExampleConversionRow.id` |
| `strategy_flag` | 전략유무 값 |

허용값:

```python
STRATEGY_CHOICES = {
    "",
    "전략상품1",
    "전략상품2",
    "전략상품3",
    "전략상품4",
}
```

주의:

- 현재 전략유무는 row에 직접 저장됩니다.
- 새 raw 업로드 시 동일 보험사 정규화 row가 전체 삭제 후 재생성되므로 기존 전략유무는 초기화됩니다.
- 전략유무 유지가 필요하면 별도 key table 또는 upsert merge 구조가 필요합니다.

---

## 11. 프론트엔드 구조

파일: `static/js/commission/rate_example_home.js`

### 11.1 root

```javascript
const root = document.getElementById("rate-example-root");
```

중복 초기화 방지:

```javascript
if (root.dataset.inited === "1") return;
root.dataset.inited = "1";
```

### 11.2 dataset 계약

템플릿 root에 아래 dataset이 필요합니다.

| dataset | JS 변수 | 설명 |
|---|---|---|
| `data-upload-url` | `UPLOAD_URL` | 업로드 API |
| `data-conversion-list-url` | `CONVERSION_LIST_URL` | 정규화 조회 API |
| `data-conversion-strategy-update-url` | `CONVERSION_STRATEGY_UPDATE_URL` | 전략유무 저장 API |
| `data-user-grade` | - | 사용자 grade |

### 11.3 보험사 목록

템플릿의 `json_script`를 읽습니다.

```javascript
const LIFE_INSURERS = JSON.parse(
  document.getElementById("life-insurers-data").textContent
);
const NONLIFE_INSURERS = JSON.parse(
  document.getElementById("nonlife-insurers-data").textContent
);
```

보험사 추가 시:

1. `RateExample.LIFE_INSURERS` 또는 `NONLIFE_INSURERS` 수정
2. 페이지 context에서 해당 목록 전달
3. JS 수정 없이 드롭다운 반영

### 11.4 업로드 흐름

1. 파일추가 모달에서 손생구분 선택
2. 보험사 드롭다운 동적 구성
3. `FormData` 생성
4. `fetch(UPLOAD_URL, POST)`
5. `X-CSRFToken` 헤더 포함
6. 성공 시 모달 닫고 `location.reload()`

주의:

- `window.csrfToken` 의존
- CSRF 없는 POST 금지
- FormData에 파일 포함

### 11.5 환산률/수정률 확인 모달

조회 흐름:

1. 손생구분 선택
2. 보험사 선택
3. `CONVERSION_LIST_URL?insurer_type=...&insurer=...`
4. rows 렌더링
5. 필터 select 생성
6. 키워드 검색/정렬 적용

표시 컬럼:

| 순서 | 컬럼 |
|---:|---|
| 1 | 보종 |
| 2 | 전략유무 |
| 3 | 상품명 |
| 4 | 구분 |
| 5 | 납기 |
| 6 | 1차년 |
| 7 | 2차년 |
| 8 | 3차년 |
| 9 | 4차년 |

### 11.6 전략유무 저장

- `.re-strategy-select` change 이벤트 위임
- `FormData(id, strategy_flag)`
- `CONVERSION_STRATEGY_UPDATE_URL` POST
- 성공 시 `convRowsOriginal` 갱신 후 재렌더

---

## 12. 템플릿 구조

파일: `commission/templates/commission/rate_example_home.html`

핵심 DOM 계약:

| ID / class | 역할 |
|---|---|
| `#rate-example-root` | 페이지 root |
| `#life-insurers-data` | 생보 보험사 json_script |
| `#nonlife-insurers-data` | 손보 보험사 json_script |
| `#re-table` | 원본 예시표 파일 목록 |
| `#rateExampleUploadModal` | 파일추가 모달 |
| `#re-modal-type` | 업로드 손생구분 |
| `#re-modal-cat` | 업로드 구분 |
| `#re-modal-insurer` | 업로드 보험사 |
| `#re-modal-file` | 업로드 파일 |
| `#re-btn-save` | 업로드 저장 버튼 |
| `#rateExampleConvModal` | 환산률/수정률 확인 모달 |
| `#re-conv-type` | 조회 손생구분 |
| `#re-conv-insurer` | 조회 보험사 |
| `#re-conv-btn-apply` | 조회 버튼 |
| `#re-conv-tbody` | 정규화 row 렌더링 영역 |
| `.re-conv-filter` | 필터 select |
| `#re-conv-keyword` | 키워드 검색 |
| `.re-sort-btn` | 정렬 버튼 |
| `.re-strategy-select` | 전략유무 select |

주의:

- DOM id 변경 금지
- dataset key 변경 금지
- JS 파일명/로드 순서 변경 시 반드시 기능 테스트

---

## 13. CSS 구조

파일: `static/css/apps/commission.css`

예시표 스코프:

```css
#rate-example-root { ... }
#rateExampleConvModal { ... }
#reCellFullTextModal { ... }
```

주의:

- `rateExampleConvModal`은 `#rate-example-root` 밖에 위치하므로 `#rate-example-root #rateExampleConvModal` 형태로 쓰면 적용되지 않습니다.
- 모달 스타일은 `#rateExampleConvModal` 직접 스코프를 사용합니다.
- 앱 전용 CSS에서 전역 클래스만 단독 선언하지 않습니다.
- 기존 `#deposit-home`, `#collect-home`, `#collect-notice` 스타일과 충돌하지 않도록 스코프 유지합니다.

---

## 14. 보안/권한/감사 원칙

### 14.1 권한

예시표 업로드/다운로드/삭제/정규화 조회/전략 저장은 현재 superuser 전용입니다.

```python
@grade_required("superuser", forbidden_template=None)
```

페이지 조회 권한이 향후 head 등으로 확장되더라도, 업로드·삭제·전략 저장은 별도 정책 검토 없이 완화하지 않습니다.

### 14.2 파일 보안

금지:

```html
<a href="{{ example.file.url }}">
```

허용:

```html
<a href="{% url 'commission:rate_example_download' ex.pk %}">
```

다운로드 뷰 내부:

```python
open_fileresponse_from_fieldfile(
    example.file,
    original_name=example.original_name or "",
)
```

### 14.3 감사 로그

감사 대상:

| 행위 | ACTION |
|---|---|
| 업로드 | `ACTION.COMMISSION_RATE_EXAMPLE_UPLOAD` |
| 다운로드 | `ACTION.COMMISSION_RATE_EXAMPLE_DOWNLOAD` |
| 삭제 | `ACTION.COMMISSION_RATE_EXAMPLE_DELETE` |
| 전략유무 변경 | `ACTION.COMMISSION_RATE_EXAMPLE_STRATEGY_UPDATE` |

감사 로그 실패는 사용자 동작을 막지 않되, `logger.exception()`으로 남깁니다.

---

## 15. 신규 보험사 정규화 추가 절차

예: 생명보험 삼성 추가

### 15.1 모델 보험사 목록 확인

파일: `commission/models.py`

```python
RateExample.LIFE_INSURERS
```

목록에 없으면 추가합니다. 단순 리스트 변경이면 일반적으로 migration은 불필요합니다.

### 15.2 normalizer 파일 추가

권장 파일명:

```text
commission/services/rate_example_normalizers/life_samsung.py
```

public entrypoint:

```python
def build_life_samsung_conversion_rows(
    example: RateExample,
    wb: Workbook,
) -> list[RateExampleConversionRow]:
    ...
```

### 15.3 오케스트레이터 등록

파일: `commission/services/rate_example_normalizer.py`

```python
from commission.services.rate_example_normalizers.life_samsung import (
    build_life_samsung_conversion_rows,
)
```

지원 보험사 set에 추가:

```python
example.insurer in {"ABL", "DB", "삼성"}
```

분기 추가:

```python
elif example.insurer == "삼성":
    normalized_rows.extend(build_life_samsung_conversion_rows(example, wb))
```

### 15.4 검증

- 업로드 normalized_count 확인
- 정규화 모달 조회
- 기존 ABL/DB 회귀 확인
- 로그에 header not found 등 불필요한 반복 로그 없는지 확인

---

## 16. 향후 개선 후보

### 16.1 전략유무 보존

현재 replace-all 방식으로 인해 새 raw 업로드 시 `strategy_flag`가 초기화됩니다.

개선안:

1. 업로드 전 기존 row의 key-value 백업
2. key = `insurer_type + category + insurer + product_name + plan_type + pay_period`
3. 새 row 생성 시 key가 같으면 기존 `strategy_flag` 복원

주의:

- 동명이상품/동일 납기 중복 가능성이 있으면 source_sheet까지 key에 포함할지 검토 필요
- 별도 `RateExampleStrategyRule` 모델로 분리하는 방식도 가능

### 16.2 공통 helper 분리

현재 `life_abl.py`, `life_db.py`에 `_clean_text`, `_to_decimal`, `_has_any_rate`가 각각 존재합니다.

개선안:

```text
commission/services/rate_example_normalizers/common.py
```

공통화 후보:

- `_clean_text`
- `_to_decimal`
- `_has_any_rate`

단, 보험사별 decimal 처리 규칙이 달라질 가능성이 있으므로 무리한 공통화는 지양합니다.

### 16.3 정규화 registry 도입

현재는 `if example.insurer == ...` 분기입니다.

확장 보험사가 많아지면:

```python
NORMALIZER_REGISTRY = {
    ("life", "conv", "ABL"): build_life_abl_conversion_rows,
    ("life", "conv", "DB"): build_life_db_conversion_rows,
}
```

형태로 변경 가능합니다.

---

## 17. 최소 검증 시나리오

### 17.1 Django check

```bash
python manage.py check
```

### 17.2 업로드 검증

1. `/commission/rate-examples/` 진입
2. 파일추가 모달 열기
3. `생명보험 / 환산률·수정률 / ABL` 업로드
4. `normalized_count > 0`
5. `생명보험 / 환산률·수정률 / DB` 업로드
6. `normalized_count > 0`

### 17.3 조회 검증

1. 환산률/수정률 확인 모달 열기
2. `생명보험 / ABL` 조회
3. `생명보험 / DB` 조회
4. 필터/키워드/정렬 정상 확인
5. 말줄임 셀 클릭 시 전체 텍스트 모달 확인

### 17.4 전략유무 검증

1. 전략유무 select 변경
2. 네트워크 POST 200 확인
3. 새로고침 후 값 유지 확인
4. 같은 보험사 raw 재업로드 시 값 초기화 여부 확인

### 17.5 보안 검증

1. 비 superuser 업로드 차단 확인
2. 파일 직접 URL 노출 없음 확인
3. 다운로드가 `rate_example_download` 뷰를 경유하는지 확인
4. 감사 로그 기록 확인

---

## 18. 회귀 위험 체크리스트

패치 전후 아래 항목을 반드시 확인합니다.

| 항목 | 확인 |
|---|---|
| URL name 변경 없음 |  |
| template id 변경 없음 |  |
| root dataset key 변경 없음 |  |
| JS 이벤트 바인딩 유지 |  |
| CSRF 헤더 포함 |  |
| superuser 권한 유지 |  |
| 파일 다운로드 뷰 경유 |  |
| ABL 업로드 정상 |  |
| DB 업로드 정상 |  |
| 정규화 조회 정상 |  |
| 전략유무 저장 정상 |  |
| 기존 commission deposit/collect CSS 영향 없음 |  |
| `python manage.py check` 통과 |  |

---

## 19. 자주 발생한 문제와 원인

### 19.1 업로드는 200인데 모달에 데이터가 없음

가능 원인:

- `normalized_count = 0`
- normalizer가 header를 찾지 못함
- 정규화 대상 보험사 set에 보험사가 빠짐
- `.xlsx`가 아닌 파일 업로드
- 조회 모달에서 `insurer_type`/`insurer` 파라미터 불일치

확인:

```text
[rate_example][DB] table header not found sheet=...
```

### 19.2 DB생명 보종이 잘못 들어감

현재 기준:

- 시트명이 아니라 A1 상품명 기준입니다.
- A1에 `종신`, `연금`, `경영` 포함 여부를 확인합니다.

### 19.3 전략유무가 업로드 후 사라짐

현재 구조상 정상 동작입니다.

이유:

- 같은 보험사 정규화 row 전체 삭제 후 새로 insert
- 기존 row의 `strategy_flag`도 함께 삭제

개선이 필요하면 “전략유무 보존 패치”를 별도 진행합니다.

---

## 20. 개발 시 절대 금지

- `RateExample.file.url` 직접 노출
- 업로드/삭제 권한을 임의로 superuser 외로 완화
- `rate_example_upload`에서 서비스 레이어 우회
- 기존 URL name 변경
- 템플릿 DOM id 변경
- JS dataset key 변경
- 정규화 실패 예외를 조용히 삼키기
- raw 파일 파싱 실패를 성공처럼 처리하기
- 기존 ABL/DB 정규화 회귀 확인 없이 신규 보험사 추가
