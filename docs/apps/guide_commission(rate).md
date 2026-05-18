# Rate Example Development Guide — Final Edition (DB/KB/농협/삼성/롯데/한화 손보 정규화 포함)

> 기준 프로젝트: django_ma  
> 대상 앱: commission  
> 최종 반영일: 2026-05-18  
> 목적: 수수료 예시표(환산율/수정률/지급률) 업로드·정규화·옵션조회·계산·예시표 출력 기능의 최종 SSOT 가이드

---

# DB생명 계산식 추가 반영 사항

> 기준 프로젝트: django_ma  
> 대상 앱: commission  
> 목적: 수수료 예시표(환산율/지급률) 업로드·정규화·옵션조회·계산·예시표 출력 기능의 최종 SSOT 가이드

---

# DB생명 계산식 추가 반영 사항

## DB생명 전용 계산 정책

DB생명은 일반 생명보험 계산식과 일부 계속분 계산 로직이 다르다.

특히:

- 13회(계속분)
- 36회(계속분)
- 37회(계속분)

계산 시 사용하는 환산율 기준이 일반 보험사와 다르므로 반드시 전용 분기로 처리해야 한다.

---

## DB생명 계산 공식

### 익월(초회)

```python
보험료
× 1차년 환산율
× 초회 지급률
× 수수료율
```

---

### 익월 소계

```python
익월 수수료 그대로 사용
```

---

### 13회(계속분)

DB생명 핵심 예외 규칙.

```python
보험료
× (1차년 환산율 + 2차년 환산율)
× 13회 지급률
× 수수료율
```

주의:

- 일반 보험사처럼 `2차년 환산율만` 사용하면 안 된다.
- 반드시 `(1차년 + 2차년)` 합산 환산율 사용.

---

### 2차년(계속분)

```python
보험료
× 2차년 환산율
× 2차년구간 지급률
× 수수료율
```

---

### 3차년(계속분)

```python
보험료
× 3차년 환산율
× 3차년구간 지급률
× 수수료율
```

---

### 36회(계속분)

DB생명 핵심 예외 규칙.

```python
보험료
× 1차년 환산율
× 36회 지급률
× 수수료율
```

주의:

- 일반 보험사처럼 `3차년 환산율` 사용 금지.
- 반드시 `1차년 환산율` 사용.

---

### 37회(계속분)

```python
보험료
× 1차년 환산율
× 37회 지급률
× 수수료율
```

---

### 4차년(계속분)

```python
보험료
× 4차년 환산율
× 4차년구간 지급률
× 수수료율
```

---

### 계속 소계

```python
13회
+ 2차년
+ 3차년
+ 36회
+ 37회
+ 4차년
```

---

### 총량

```python
익월 소계 + 계속 소계
```

---

### 비율

```python
총량 / 보험료
```

---

# 구현 SSOT

파일:

```python
commission/services/rate_example_calculator.py
```

DB생명 계산은 반드시 서비스 레이어에서 처리한다.

View/API에서 계산 금지.

---

## 구현 원칙

금지:

```python
if insurer == "DB":
    # view 내부 계산
```

반드시:

```python
calculate_rate_example_commission(...)
```

서비스 내부에서 처리.

---

## 권장 구조

```python
if data.insurer == "DB":
    return _calculate_db_life_commission(...)
```

또는:

```python
if insurer == "DB":
    # DB 전용 분기
else:
    # 일반 보험사 계산
```

---

## DB 계산용 환산율 multiplier 규칙

정규화 테이블 저장값:

```python
100.0
150.0
220.0
```

계산 전 반드시:

```python
Decimal(value) / Decimal("100")
```

처리.

예:

```python
y1 = _pct_to_multiplier(year1_rate)
```

---

## DB 계산 전용 helper 권장

```python
_amount_or_none_with_conversion_multiplier(...)
```

역할:

- 이미 계산된 환산율 multiplier 직접 사용
- `(1차년 + 2차년)` 합산 계산 지원

---

## DB 계산 검증 체크포인트

반드시 검증:

### 13회

```python
보험료
× (year1 + year2)
× pay.col_m13
× 수수료율
```

### 36회

```python
보험료
× year1
× pay.col_m36
× 수수료율
```

### 37회

```python
보험료
× year1
× pay.col_m37
× 수수료율
```

---

## 운영 주의사항

DB생명 계산식은 일반 보험사와 다르므로:

- 공통 계산 helper 재사용 시 주의
- 일반 생보 계산식에 DB 분기 섞지 말 것
- 반드시 insurer == "DB" 전용 분기 유지

---

# 프론트 옵션 연동

보험사 선택 시:

```text
DB
```

대문자 canonical 값 유지.

금지:

```text
db
```

---

## 보험사 canonical 규칙

파일:

```python
commission/services/rate_example_options.py
```

권장:

```python
INSURER_CANONICAL_MAP = {
    "db": "DB",
}
```

---

## 상품명 드랍다운 선택 정책

파일:

```javascript
static/js/commission/rate_example_home.js
```

combo 선택은 반드시:

```javascript
pointerdown
```

이벤트 기준 처리.

금지:

```javascript
click
```

blur 이후 이벤트 누락 가능.

---

# 이하 기존 지침 유지

- 환산율 정규화 정책 유지
- 지급률 저장 정책 유지
- replace / append 유지
- Decimal 백분율 저장 유지
- audit 정책 유지
- dataset 기반 fetch 유지
- harness 점검 유지

---

# 검증 명령

```powershell
python manage.py check
```

DB 계산 검증:

```powershell
python manage.py shell
```

```python
from commission.services.rate_example_calculator import calculate_rate_example_commission
```

---

# 핵심 회귀 체크

1. DB 이외 보험사 계산 영향 없는지
2. 13회 계산 정상인지
3. 36회 계산 정상인지
4. 37회 계산 정상인지
5. 총량 계산 정상인지
6. 비율 계산 정상인지
7. 상품명 드랍다운 선택 정상인지
8. insurer=db → DB canonical 변환 정상인지


---

# 손해보험(FIRE) 지급률 정규화 — Final SSOT

## 개요

손해보험 지급률은 기존 생명보험 지급률과 별도의 RAW 레이아웃을 사용한다.

프로젝트 canonical insurer_type:

```python
fire
```

기존 `nonlife`는 더 이상 사용하지 않는다.

---

# 대상 RAW 파일 규칙

## 대상 시트

다음 시트만 정규화:

```text
[① 5천만,3천만↑]
```

다른 시트는 모두 제외.

---

## 대상 구간

정규화 대상:

```text
(5천만원↑)
```

정규화 제외:

```text
(3천만원↑)
```

---

# 정규화 컬럼 구조

## 출력 컬럼

| 컬럼 | 설명 |
|---|---|
| 보험사 | 보험사 canonical |
| 상품군 | 보장/연금/저축 등 |
| 초회 | 초회 지급률 |
| 2~6회 | 2~6회 지급률 |
| 7~12회 | 7~12회 지급률 |
| 13회 | 13회 지급률 |
| 14회 | 14회 지급률 |
| 15회 | 15회 지급률 |

---

# 보험사 canonical 정책

```python
INSURER_CANONICAL_MAP = {
    "현대해상": "현대",
    "DB손해보험": "DB",
    "KB손해보험": "KB",
    "메리츠화재": "메리츠",
    "한화손해보험": "한화",
    "롯데손해보험": "롯데",
    "흥국화재": "흥국",
    "삼성화재": "삼성",
    "농협손해보험": "농협",
    "하나손해보험": "하나",
}
```

---

# 상품군 정책

허용 상품군:

```python
PRODUCT_GROUPS = {
    "보장",
    "보장(태아)",
    "연금",
    "저축",
    "단독실손(초회)",
    "단독실손(갱신)",
}
```

허용 목록 이외는 정규화 제외.

---

# 저장 모델 매핑

모델:

```python
RateExamplePayRow
```

## 필드 매핑

| RAW 컬럼 | 저장 필드 |
|---|---|
| 초회 | col_first |
| 2~6회 | col_yr1 |
| 7~12회 | col_m13 |
| 13회 | col_yr2 |
| 14회 | col_yr3 |
| 15회 | col_m36 |

---

# 지급률 보정 정책

손해보험 지급률도 생명보험과 동일하게 저장 전 보정한다.

공식:

```python
최종 저장 지급률 = RAW 지급률 / Decimal("0.97")
```

예:

```python
323.33 / 0.97
= 333.329896...
```

---

# 구현 파일

## 손보 지급률 parser

```python
commission/services/rate_example_normalizers/fire_pay.py
```

핵심 함수:

```python
build_fire_pay_rows(example)
```

---

## 지급률 정규화 진입점

```python
commission/services/rate_example_pay_normalizer.py
```

핵심 분기:

```python
if example.insurer_type == RateExample.TYPE_FIRE:
```

---

# insurer_type 정책

## canonical key

```python
RateExample.TYPE_FIRE = "fire"
```

금지:

```python
nonlife
```

---

# 옵션/조회 API 정책

## 허용 insurer_type

```python
life
fire
```

레거시 URL 방어:

```python
if insurer_type == "nonlife":
    insurer_type = "fire"
```

허용.

---

# 지급률 확인 모달 정책

손해보험 지급률 확인 모달은 생명보험과 다른 컬럼 구조를 사용한다.

## 손보 지급률 모달 컬럼

| 보험사 | 상품군 | 초회 | 2~6회 | 7~12회 | 13회 | 14회 | 15회 |

---

## 생보 지급률 모달 컬럼

| 보험사 | 상품군 | 초회 | 1차년 | 13회 | 2차년구간 | 3차년구간 | 36회 | 37회 | 4차년구간 |

---

# 프론트 렌더링 정책

파일:

```javascript
static/js/commission/rate_example_home.js
```

손보 탭 여부:

```javascript
ACTIVE_INSURER_TYPE === "fire"
```

기준으로 렌더링 분기.

---

# replace / append 정책

## replace

```python
RateExamplePayRow.objects.filter(
    insurer_type="fire",
    category="pay",
).delete()
```

후 전체 재삽입.

---

## append

기존 데이터 유지 후 신규 insert.

---

# 검증 명령

## 코드 검증

```powershell
python manage.py check
```

## parser import 확인

```powershell
python manage.py shell -c "from commission.services.rate_example_normalizers.fire_pay import build_fire_pay_rows; print(build_fire_pay_rows)"
```

## 저장 결과 검증

```powershell
python manage.py shell -c "from commission.models import RateExamplePayRow as R; qs=R.objects.filter(insurer_type='fire', category='pay').order_by('insurer','coverage_type'); print(qs.count())"
```

---

# 회귀 체크리스트

1. 생명보험 지급률 영향 없는지
2. 손해보험 지급률 조회 정상인지
3. 손해보험 지급률 업로드 정상인지
4. 지급률 모달 헤더 정상 전환되는지
5. fire canonical 정상 동작하는지
6. nonlife legacy URL fallback 정상인지
7. 지급률 0.97 보정 정상 적용되는지
8. replace 모드 정상 삭제되는지
9. append 모드 정상 insert 되는지



---

# 손해보험 수정률 단일 컬럼 구조 — Final SSOT

## 개요

손해보험(FIRE) 수정률 구조를 기존 다차년 구조에서 단일 수정률 구조로 단순화한다.

기존:

| 보험사 | 상품군 | 상품명 | 구분 | 납기 | 1차년 | 2차년 | 3차년 | 4차년 |

변경 후:

| 보험사 | 상품군 | 상품명 | 구분 | 납기 | 수정률 |

---

# 핵심 정책

## DB 필드명 유지 정책

UI 용어는 모두:

보종 → 상품군

으로 통일한다.

단, DB SSOT 필드는 기존 호환성 유지를 위해 그대로 유지한다.

coverage_type

변경 금지:
- Django model field
- serializer key
- queryset filter key
- API payload key

---

# 손해보험 수정률 저장 정책

손해보험 수정률은:

RateExampleConversionRow.year1

필드 단일값으로 저장한다.

| 화면 컬럼 | 저장 필드 |
|---|---|
| 수정률 | year1 |

미사용:
- year2
- year3
- year4

손보 저장 시 None 처리.

---

# 손보 계산 테이블 구조

| 선택 | 보험사 | 상품명 | 구분 | 납기 | 익월(초회) | 익월 소계(초회) | 13회(계속분) | 14회(계속분) | 15회(계속분) | 계속 소계(계속분) | 금액(총량) | 비율(총량) |

---

# 손해보험 계산식 — Final

파일:

commission/services/rate_example_calculator.py

## 익월(초회)

보험료 × 수정률 × 초회 지급률 × 수수료율

사용 컬럼:
- conv.year1
- pay.col_first

## 13회(계속분)

보험료 × 수정률 × 13회 지급률 × 수수료율

사용 컬럼:
- conv.year1
- pay.col_yr2

## 14회(계속분)

보험료 × 수정률 × 14회 지급률 × 수수료율

사용 컬럼:
- conv.year1
- pay.col_yr3

## 15회(계속분)

보험료 × 수정률 × 15회 지급률 × 수수료율

사용 컬럼:
- conv.year1
- pay.col_m36

## 계속 소계

13회 + 14회 + 15회

## 총량

익월 소계 + 계속 소계

## 비율

총량 / 보험료

---

# 지급률 컬럼 매핑

| 화면 컬럼 | 저장 필드 |
|---|---|
| 초회 | col_first |
| 2~6회 | col_yr1 |
| 7~12회 | col_m13 |
| 13회 | col_yr2 |
| 14회 | col_yr3 |
| 15회 | col_m36 |

---

# 전략유무 정책

손해보험:
- 전략유무 사용 안함
- strategy_flag = ""
- 필터 숨김 처리

---

# 손보 보험사 canonical

- AIG
- DB
- KB
- 농협
- 롯데
- 메리츠
- 삼성
- 하나
- 한화
- 현대
- 흥국

---

# 회귀 체크리스트

1. 생보 계산 정상 여부
2. 손보 계산 정상 여부
3. 손보 수정률 저장 정상 여부
4. 손보 지급률 조회 정상 여부
5. 상품군 label 전체 반영 여부
6. colspan mismatch 없는지
7. duplicated kwargs 제거 여부




# KB 손해보험 수정률 정규화 — Final SSOT

## 개요

KB 손해보험 수정률 raw 파일을 `RateExampleConversionRow` 기준으로 정규화한다.

대상:

```text
insurer_type = fire
category = conv
insurer = KB
```

정규화 파일:

```text
commission/services/rate_example_normalizers/fire_kb.py
```

---

# 대상 시트

```text
GA채널_수정률
```

다른 시트는 정규화하지 않는다.

---

# DB 저장 구조

| 정규화 컬럼 | DB 필드 |
|---|---|
| 보험사 | insurer |
| 상품군 | coverage_type |
| 상품명 | product_name |
| 구분 | plan_type |
| 납기 | pay_period |
| 수정률 | year1 |

---

# canonical key 정책

손해보험 canonical key:

```python
RateExample.TYPE_FIRE
```

금지:

```text
nonlife
```

---

# 병합 셀 처리 규칙

- 병합 셀은 모두 해제된 것으로 처리
- 병합 범위 전체에 좌상단 값 전파

예시:

```text
A1:C3 = 보장

↓

A1~C3 전체 = 보장
```

---

# 상품명 정규화

기준 컬럼:

```text
C열 상품명
```

규칙:

- 줄바꿈 제거
- 여러 줄은 공백 연결
- trim 처리

예시:

```text
KB The좋은
닥터플러스건강

↓

KB The좋은 닥터플러스건강
```

---

# 상품군 정규화

기준 컬럼:

```text
B열 구분
```

| raw 값 | 저장값 |
|---|---|
| 재물 | 제외 |
| 저축 | 저축 |
| 연금 | 연금 |
| 실손 + 갱신 "-" | 단독실손(초회) |
| 실손 + 갱신값 존재 | 단독실손(초회), 단독실손(갱신) |
| 기타 | 보장 |

---

# 태아 상품 규칙

기준 컬럼:

```text
G열 당보그룹
```

다음 키워드 포함 시:

```text
신생아
태아
```

저장값:

```text
보장(태아)
```

---

# 구분 컬럼 정규화

기준 컬럼:

```text
G열 당보그룹
```

규칙:

- 값을 그대로 저장
- 단, `단일`은 공란 저장

예시:

```text
단일 → ""
유병자 → 유병자
```

---

# 납기 정규화

기준 컬럼:

| 컬럼 | 의미 |
|---|---|
| E열 | 보험기간 |
| F열 | 납입기간 |

---

## 납입기간 규칙

- `납` 문자열 없으면 `년` 뒤에 `납` 삽입

예시:

```text
10년 → 10년납
```

---

## 보험기간 규칙

- 줄바꿈 제거
- 여러 줄은 `/` 연결
- 이미 `/` 시작 문자열은 중복 `/` 미삽입

예시:

```text
80세만기
90세만기
100세만기

↓

80세만기/90세만기/100세만기
```

---

## 최종 납기 조합

```text
납입기간 + " (" + 보험기간 + ")"
```

예시:

```text
10년납 (80세만기/90세만기/100세만기/110세만기)
```

---

# 수정률 저장 정책

기준 컬럼:

| 컬럼 | 의미 |
|---|---|
| I열 | 최초 |
| J열 | 갱신 |

---

## 일반 상품

```text
I열 최초값 저장
```

---

## 단독실손(갱신)

```text
J열 갱신값 저장
```

---

# 중요 수정 사항

## 기존 오류 코드

```python
return raw * Decimal("100")
```

문제:

```text
160 → 16000%
```

---

## 최종 정책

raw 값을 그대로 저장한다.

| raw | 저장 |
|---|---|
| 160 | 160 |
| 95 | 95 |
| 240 | 240 |

최종 표시:

```text
160%
```

---

# 실손 처리 정책

조건:

```text
B열 = 실손
```

---

## J열 = "-"

생성 row:

```text
단독실손(초회)
```

---

## J열 값 존재

생성 row:

```text
단독실손(초회)
단독실손(갱신)
```

---

# 제외 정책

```text
B열 = 재물
```

해당 row 저장 금지.

---

# Orchestrator 연동

## __init__.py

```python
from commission.services.rate_example_normalizers.fire_kb import (
    build_fire_kb_conversion_rows,
)
```

---

## __all__

```python
"build_fire_kb_conversion_rows",
```

---

# rate_example_normalizer.py 수정

## 보험사 대상 추가

```python
and example.insurer in {"DB", "KB"}
```

---

## 실행 분기

```python
elif (
    example.insurer_type == RateExample.TYPE_FIRE
    and example.insurer == "KB"
):
    normalized_rows.extend(
        build_fire_kb_conversion_rows(example, wb)
    )
```

---

# 업로드 검증 정책

다음 조건에서만 product_kind 사용:

```python
insurer_type == "life"
and category == "conv"
and insurer in {"KB", "한화"}
```

---

# 프론트엔드 정책

KB 손해보험:

- 상품구분 드랍다운 사용 안함
- 단일 raw 파일 사용
- product_kind 빈 값 전송

---

# rate_example_home.js 정책

손보 페이지:

```javascript
isNonlifePage() === true
```

일 때:

- 상품구분 영역 숨김
- KB/한화 validation 비활성화
- product_kind 빈 값 전송

---

# 검증 시나리오

```powershell
python manage.py check
```

```python
from commission.models import RateExampleConversionRow as R

qs = R.objects.filter(
    insurer_type="fire",
    category="conv",
    insurer="KB",
)

print(qs.count())
```

---

# 필수 검증 항목

```text
[ ] 재물 상품 제외
[ ] 태아 상품 → 보장(태아)
[ ] 실손 초회/갱신 분리 생성
[ ] 단일 → 구분 공란
[ ] 납기 괄호 조합 정상
[ ] 수정률 160 → 160%
[ ] 상품구분 드랍다운 숨김
[ ] KB 손보 업로드 정상 완료
[ ] DB 손보 기능 영향 없음
```

---

# 운영 주의사항

- migration 불필요
- static rebuild 불필요
- 기존 KB 손보 데이터 초기화 후 재업로드 권장
- replace 모드 권장
- 권한 정책 변경 없음
- superuser 업로드 정책 유지

---

# 최종 SSOT

KB 손해보험 수정률 정책:

```text
단일 raw 파일 기반
상품구분 없음
raw 수정률 그대로 저장
```

---

# 농협손해보험 수정률 정규화 — Final SSOT

## 개요

농협손해보험 수정률 raw 파일을 `RateExampleConversionRow` 기준으로 정규화한다.

대상:

```text
insurer_type = fire
category = conv
insurer = 농협
```

정규화 파일:

```text
commission/services/rate_example_normalizers/fire_nh.py
```

핵심 원칙:

- 색상 기준 판별을 사용하지 않는다.
- 병합 셀은 parser 내부 value matrix에서만 전개한다.
- 테이블 시작은 B~F열 헤더 `납입기간 / 보험기간 / 계약구분 / 모집(ㄱ) / 수금(ㄴ)`로 판별한다.
- 테이블 내부 공란 셀은 현재 셀과 헤더 사이 같은 컬럼의 마지막 텍스트로 보정한다.
- 수정률은 raw 백분율 표시값을 그대로 `year1`에 저장한다.

---

## DB 저장 구조

모델:

```python
RateExampleConversionRow
```

| 정규화 컬럼 | DB 필드 | 정책 |
|---|---|---|
| 보험사 | `insurer` | `농협` 고정 |
| 상품군 | `coverage_type` | 보장 / 보장(태아) / 단독실손(초회) / 단독실손(갱신) |
| 상품명 | `product_name` | A열 `◈` 뒤 텍스트 |
| 구분 | `plan_type` | `【...】` 텍스트 기반 |
| 납기 | `pay_period` | 납입기간 + 보험기간 |
| 수정률 | `year1` | E열 `모집(ㄱ)` raw 백분율 |
| 미사용 | `year2~year4` | `None` 저장 |

---

## 원본 파일 구조 기준

### 상품 블록

상품 시작 기준:

```text
A열에 ◈ 포함
```

상품명 추출:

```python
A열 텍스트 중 "◈" 뒤의 텍스트
```

예:

```text
◈ (무) NH아이맘헤아림어린이보험2604
→ (무) NH아이맘헤아림어린이보험2604
```

특정 상품 시작 행과 다음 상품 시작 행 사이의 테이블을 해당 상품 데이터로 정규화한다.

---

## 병합 셀 처리 정책

농협 raw 파일은 병합 셀이 있으므로 `openpyxl` workbook은 `read_only=False`로 로드한다.

parser 내부에서만 다음 방식으로 전개한다.

```text
병합 범위 전체 = 좌상단 셀 값
```

주의:

- 실제 workbook에는 `unmerge_cells()`를 실행하지 않는다.
- 정규화 전용 `values[(row, col)]` matrix에서만 병합 값을 전파한다.
- 색상 matrix는 사용하지 않는다.

---

## 테이블 판별 정책

색상 기준 판별 금지.

테이블 헤더 기준:

```text
B열 = 납입기간
C열 = 보험기간
D열 = 계약구분
E열 = 모집(ㄱ)
F열 = 수금(ㄴ)
```

상수:

```python
HEADER_LABELS = ("납입기간", "보험기간", "계약구분", "모집(ㄱ)", "수금(ㄴ)")
```

해당 헤더가 발견된 행 이후를 현재 상품/구분의 정규화 테이블로 본다.

---

## 테이블 내부 공란 보정 정책

색상이 아닌 헤더 기준으로 보정한다.

규칙:

```text
테이블 내 특정 셀이 비어 있으면,
해당 셀 상단과 헤더 행 사이의 같은 컬럼에서
가장 가까운 마지막 텍스트를 사용한다.
```

적용 대상:

| 컬럼 | 의미 |
|---|---|
| B열 | 납입기간 |
| C열 | 보험기간 |
| D열 | 계약구분 |
| E열 | 모집(ㄱ) |

구현 helper:

```python
_filled_table_value(values, header_row, row_no, col_no)
```

이 정책으로 기존 색상 값 누락/`fgColor.rgb` 객체 문제와 무관하게 정규화한다.

---

## 구분(plan_type) 정규화 정책

구분 후보 기준:

```text
행 내에 【...】 형태의 텍스트가 있는 경우
```

추출:

```python
【적립부】 → 적립부
```

2줄 구분 처리:

```text
상위 구분 + " (" + 하위 구분 + ")"
```

예:

```text
1종 해지환급금미지급형Ⅱ
보장부
→ 1종 해지환급금미지급형Ⅱ (보장부)
```

주의:

- 같은 행에서 여러 `【...】` 값이 있으면 중복 제거 후 순서 유지한다.
- 새 상품 블록을 만나면 `current_plan`과 pending plan buffer를 초기화한다.
- 새 테이블 헤더를 만나면 pending plan buffer만 초기화하고 현재 구분은 유지한다.

---

## 상품군(coverage_type) 정규화 정책

### 실손 상품

조건:

```text
상품명에 "실손" 포함
```

계약구분 기준:

| 계약구분 | 상품군 |
|---|---|
| 신규 | 단독실손(초회) |
| 갱신 | 단독실손(갱신) |

### 태아 상품

조건:

```text
plan_type에 "태아" 포함
```

저장:

```text
보장(태아)
```

### 그 외

```text
보장
```

---

## 납기(pay_period) 정규화 정책

기준 컬럼:

| 컬럼 | 의미 |
|---|---|
| B열 | 납입기간 |
| C열 | 보험기간 |

최종 조합:

```text
납입기간 + " (" + 보험기간 + ")"
```

보험기간 줄바꿈 처리:

```text
줄바꿈 → /
```

예:

```text
20년납 + 80세만기\n90세만기\n100세만기
→ 20년납 (80세만기/90세만기/100세만기)
```

---

## 수정률(year1) 저장 정책

기준 컬럼:

```text
E열 모집(ㄱ)
```

저장 정책:

```text
raw 백분율 표시값 그대로 저장
```

예:

| raw | 저장값 | 화면 표시 |
|---|---:|---:|
| 230 | 230 | 230% |
| 160 | 160 | 160% |

주의:

- `× 100` 금지.
- `/ 0.97` 보정 금지.
- `year2`, `year3`, `year4`는 `None` 저장.

---

## Orchestrator 연동

### `commission/services/rate_example_normalizers/__init__.py`

import 추가:

```python
from commission.services.rate_example_normalizers.fire_nh import (
    build_fire_nh_conversion_rows,
)
```

`__all__` 추가:

```python
"build_fire_nh_conversion_rows",
```

---

### `commission/services/rate_example_normalizer.py`

대상 보험사 추가:

```python
is_fire_conv_target = (
    example.insurer_type == RateExample.TYPE_FIRE
    and example.category == RateExample.CAT_CONV
    and example.insurer in {"DB", "KB", "농협"}
)
```

실행 분기 추가:

```python
elif example.insurer_type == RateExample.TYPE_FIRE and example.insurer == "농협":
    normalized_rows.extend(build_fire_nh_conversion_rows(example, wb))
```

---

## 조회 API 정책

조회 API는 기존 `RateExampleConversionRow` 조회를 그대로 사용한다.

조건:

```python
RateExampleConversionRow.objects.filter(
    insurer_type="fire",
    category="conv",
    insurer="농협",
)
```

손보 수정률 화면에서는 `year1`을 `mod_rate`로 렌더링한다.

---

## 초기화/재업로드 절차

기존 농협 데이터 초기화:

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; print(R.objects.filter(insurer_type='fire', category='conv', insurer='농협').delete())"
```

재업로드:

```text
손해보험 / 수정률 / 농협 / replace
```

검증:

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; qs=R.objects.filter(insurer_type='fire', category='conv', insurer='농협'); print(qs.count()); print(qs.values('product_name','plan_type','coverage_type','pay_period','year1')[:10])"
```

---

## 필수 검증 항목

```text
[ ] 농협 업로드 시 normalized_count > 0
[ ] 수정률 조회 모달에서 보험사=농협 조회 가능
[ ] 상품명에 ◈ 뒤 텍스트만 저장
[ ] 2줄 구분이 "상위 (하위)"로 저장
[ ] 실손 신규 → 단독실손(초회)
[ ] 실손 갱신 → 단독실손(갱신)
[ ] 태아 구분 → 보장(태아)
[ ] 납기 = 납입기간 (보험기간/보험기간/보험기간)
[ ] 수정률 230 → 230%로 표시
[ ] DB/KB 손보 정규화 영향 없음
[ ] 생명보험 환산율/지급률 영향 없음
```

---

## 운영 주의사항

- migration 불필요.
- model 변경 없음.
- URL 변경 없음.
- 권한 변경 없음.
- static rebuild 불필요.
- 기존 농협 row가 0건으로 생성된 이력이 있으면 반드시 삭제 후 replace 재업로드한다.

---

## 최종 SSOT

농협손해보험 수정률 정책:

```text
색상 기준 사용 금지
헤더 기준 테이블 판별
헤더와 현재 셀 사이의 마지막 텍스트로 공란 보정
수정률은 raw 백분율 그대로 year1 저장
```



---

# 삼성화재(FIRE) 수정률 정규화 — Final SSOT (2026-05-17 추가)

## 개요

삼성화재 손해보험 수정률 RAW 파일을 `RateExampleConversionRow` 기준으로 정규화한다.

대상:

```text
insurer_type = fire
category = conv
insurer = 삼성
```

정규화 파일:

```python
commission/services/rate_example_normalizers/fire_samsung.py
```

---

# 핵심 정책

## 저장 구조

| 정규화 컬럼 | DB 필드 |
|---|---|
| 보험사 | insurer |
| 상품군 | coverage_type |
| 상품명 | product_name |
| 구분 | plan_type |
| 납기 | pay_period |
| 수정률 | year1 |

---

# 수정률 저장 정책 (최종)

삼성화재 raw 수정률은 실제 표시값의 100배 형태로 들어온다.

예:

| raw 값 | 실제 의미 |
|---|---|
| 2000 | 20% |
| 14500 | 145% |
| 24000 | 240% |

따라서 저장 직전:

```python
Decimal(raw) / Decimal("100")
```

처리 후 저장한다.

최종 저장 예시:

| raw | 저장값 |
|---|---|
| 2000 | 20 |
| 14500 | 145 |
| 24000 | 240 |

주의:

- `×100` 보정 금지
- `/0.97` 보정 금지
- number_format 기반 percent multiplier 금지

---

# 병합 셀 처리 정책

실제 workbook 수정 없이 parser 내부 matrix에서만 병합 값을 전파한다.

```text
병합 범위 전체 = 좌상단 셀 값
```

주의:

- `unmerge_cells()` 사용 금지
- workbook 직접 수정 금지

---

# 테이블 제목 탐지 정책

삼성 raw는 한 시트 내 여러 테이블과 참고 문구가 혼재한다.

기존 문제:

```text
(참고용) 삼성화재 GA 주요상품 수정률 한눈에 보기...
삼성화재 GA 주요상품 & 담보 수정률 요약...
```

같은 참고 텍스트가 상품명/상품군으로 잘못 정규화됨.

---

# 제목 탐지 개선 정책

## 1. 현재 테이블 컬럼 범위 안에서만 제목 탐색

기존:

```python
for col_no in range(1, 80)
```

문제:

- 다른 테이블 제목까지 함께 읽음
- 병합셀 전파로 같은 문구가 반복됨

최종 정책:

```python
_header_title_search_bounds(header_cols)
```

기준으로 현재 테이블 헤더 범위 내에서만 제목 탐색.

---

## 2. 의미 없는 제목 제외

다음 키워드 포함 시 제목 후보 제외:

```python
TITLE_EXCLUDE_KEYWORDS = (
    "참고용",
    "한눈에 보기",
    "요약",
    "제작일자",
    "대외비",
    "현장관리자",
    "수수료지급",
)
```

---

## 3. 중복 제목 제거

병합셀 전파로 같은 텍스트가 여러 번 등장하는 현상 방어:

```python
_unique_nonempty_texts(...)
```

사용.

동일 텍스트는 1회만 유지.

---

# 자녀/태아 상품 정규화 정책

## 대상 제목

예:

```text
자녀 : NEW 마이 슈퍼스타 1-2종
```

---

# 상품명 정책

상품명:

```text
':' 오른쪽 텍스트 + '(' + 갱신구분 + ')'
```

예:

```text
NEW 마이 슈퍼스타 1-2종 (비갱신)
NEW 마이 슈퍼스타 1-2종 (갱신)
```

---

# 구분 정책

다음 헤더 사용:

```text
보장(80/90/100세 만기)
보장(20/30세만기)
```

저장:

```python
plan_type
```

---

# 납기 정책

```text
납기 컬럼 값 그대로 저장
```

---

# 상품군 정책

조건:

```text
납기에 "태아" 포함
```

저장:

```text
보장(태아)
```

그 외:

```text
보장
```

---

# 수정률 정책

다음 컬럼 사용:

```text
"보장" 포함 헤더 컬럼
```

해당 셀 값을 수정률로 저장.

---

# 최종 중복 방어 정책

최종 업로드 전:

```python
_dedupe_conversion_rows(rows)
```

적용.

다음 값이 모두 같으면 동일 상품으로 간주:

| 기준 |
|---|
| 상품군 |
| 상품명 |
| 구분 |
| 납기 |

최초 row만 유지.

---

# 상품군 정책

## 단독실손

조건:

```text
실손 포함
```

분기:

| 납기 | 상품군 |
|---|---|
| 최초 | 단독실손(초회) |
| 갱신 | 단독실손(갱신) |

---

## 태아/자녀

조건:

```text
자녀 포함
슈퍼스타 포함
```

저장:

```text
보장(태아)
```

---

## 일반 상품

저장:

```text
보장
```

---

# openpyxl custom.xml 오류 대응

삼성 raw 파일 일부는:

```text
docProps/custom.xml
```

custom property가 깨져 있음.

오류 예:

```text
StringProperty.name should be <class 'str'> but value is <class 'NoneType'>
```

최종 정책:

- 최초 load_workbook 실패 시
- custom.xml 제거 후 retry load

서비스:

```python
_load_workbook_safely()
```

---

# 최종 회귀 체크리스트

```text
[ ] 삼성 업로드 정상 완료
[ ] 수정률 2000 → 20%
[ ] 수정률 14500 → 145%
[ ] 참고용 문구 정규화 제외
[ ] 요약 문구 정규화 제외
[ ] NEW 마이 슈퍼스타 태아 상품 정상 생성
[ ] 보장(태아) 정상 분류
[ ] 동일 상품 중복 insert 방어
[ ] 생명보험 영향 없음
[ ] DB/KB/농협 손보 영향 없음
```

---

# 최종 SSOT

삼성화재 손보 수정률 정책:

```text
현재 테이블 범위 내 제목만 사용
참고용/요약 문구 제거
수정률은 raw / 100 저장
자녀/태아 상품 별도 정규화
최종 dedupe 적용
```


---

# 롯데손해보험(FIRE) 수정률 정규화 — Final SSOT (2026-05-18 추가)

## 개요

롯데손해보험 수정률 RAW 파일을 `RateExampleConversionRow` 기준으로 정규화한다.

대상:

```text
insurer_type = fire
category = conv
insurer = 롯데
```

정규화 파일:

```python
commission/services/rate_example_normalizers/fire_lotte.py
```

---

# 핵심 정책

## 저장 구조

| 정규화 컬럼 | DB 필드 |
|---|---|
| 보험사 | insurer |
| 상품군 | coverage_type |
| 상품명 | product_name |
| 구분 | plan_type |
| 납기 | pay_period |
| 수정률 | year1 |

미사용:

```text
year2
year3
year4
```

손보 수정률 구조 정책에 따라 `None` 저장.

---

# 좌/우 병렬 테이블 구조 정책

롯데 RAW는 동일 상품에 대해:

- 좌측 테이블
- 우측 테이블

이 병렬로 배치된 구조를 사용한다.

핵심 규칙:

| 우측 상태 | 처리 정책 |
|---|---|
| 좌동 | 좌측 블록 사용 |
| 판매중지 | 좌/우 전체 제외 |
| 일반 | 우측 블록 사용 |

---

# 상품 블록(pair) 판별 정책

상품 시작 기준:

| 위치 | 의미 |
|---|---|
| B열 | 좌측 상품명 |
| I열 | 우측 상품명 |

다음 조건이면 상품 블록 시작행으로 판단한다.

```python
_looks_like_product_start(...)
```

제외 키워드:

```python
TITLE_EXCLUDE_KEYWORDS = (
    "공통사항",
    "변경전",
    "변경후",
    "상품",
    "■",
    "※",
)
```

---

# 병합 셀 처리 정책

실제 workbook 수정 금지.

parser 내부 matrix에서만 병합 값을 전파한다.

```text
병합 범위 전체 = 좌상단 셀 값
```

금지:

```python
unmerge_cells()
```

---

# 우측 상태 판별 정책

우측 block 범위 내 텍스트를 검사한다.

## 판매중지

조건:

```text
판매중지 포함
```

정책:

```text
좌/우 block 전체 제외
```

---

## 좌동

조건:

```text
좌동 포함
```

정책:

```text
좌측 block 기준 정규화
```

---

## 일반

그 외:

```text
우측 block 기준 정규화
```

---

# 상품군(coverage_type) 정책

## 단독실손

조건:

```text
상품명 또는 구분에 "실손" 포함
```

분기:

| 납기 | 상품군 |
|---|---|
| 최초 포함 | 단독실손(초회) |
| 갱신 포함 | 단독실손(갱신) |
| 그 외 | 단독실손(갱신) |

---

## 연금

조건:

```text
상품명에 "연금" 포함
```

저장:

```text
연금
```

---

## 저축

조건:

```text
상품명에 "저축" 포함
```

저장:

```text
저축
```

---

## 일반 상품

저장:

```text
보장
```

---

# 상품명(product_name) 정책

기준 컬럼:

| 위치 | 컬럼 |
|---|---|
| 좌측 | B열 |
| 우측 | I열 |

정규화:

- 줄바꿈 제거
- 다중 공백 제거
- trim 처리

---

# 구분(plan_type) 정책

기준 컬럼:

| 위치 | 컬럼 |
|---|---|
| 좌측 | C열 |
| 우측 | J열 |

저장 정책:

```text
raw 문자열 그대로 저장
```

---

# 납기(pay_period) 정책

기준 컬럼:

| 위치 | 컬럼 |
|---|---|
| 좌측 | D열 |
| 우측 | K열 |

저장 정책:

```text
raw 문자열 그대로 저장
```

---

# 수정률(year1) 저장 정책

기준 컬럼:

| 위치 | 컬럼 |
|---|---|
| 좌측 | E열 |
| 우측 | L열 |

저장 정책:

```text
raw 백분율 표시값 그대로 저장
```

예:

| raw | 저장값 | 화면 표시 |
|---|---:|---:|
| 130 | 130 | 130% |
| 95 | 95 | 95% |
| 240 | 240 | 240% |

주의:

- `×100` 금지
- `/100` 금지
- `/0.97` 금지

---

# 손보 수정률 화면 표시 정책

DB손보만 기존 legacy 배율 정책을 유지한다.

| 보험사 | 저장값 | 화면 |
|---|---|---|
| DB | 2.4 | 240% |
| 롯데 | 130 | 130% |

최종 정책:

```python
if row.insurer == "DB":
    shown = value * 100
else:
    shown = value
```

---

# Orchestrator 연동

## __init__.py

```python
from commission.services.rate_example_normalizers.fire_lotte import (
    build_fire_lotte_conversion_rows,
)
```

---

## __all__

```python
"build_fire_lotte_conversion_rows",
```

---

# rate_example_normalizer.py 수정

## 보험사 대상 추가

```python
and example.insurer in {"DB", "KB", "농협", "삼성", "롯데"}
```

---

## 실행 분기

```python
elif example.insurer_type == RateExample.TYPE_FIRE and example.insurer == "롯데":
    normalized_rows.extend(build_fire_lotte_conversion_rows(example, wb))
```

---

# 검증 시나리오

```powershell
python manage.py check
```

---

## parser import 확인

```powershell
python manage.py shell -c "from commission.services.rate_example_normalizers.fire_lotte import build_fire_lotte_conversion_rows; print(build_fire_lotte_conversion_rows)"
```

---

## 저장 결과 검증

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; qs=R.objects.filter(insurer_type='fire', category='conv', insurer='롯데'); print(qs.count())"
```

---

# 필수 검증 항목

```text
[ ] 롯데 업로드 정상 완료
[ ] 좌동 → 좌측 block 사용 정상 동작
[ ] 판매중지 → 좌/우 전체 제외 정상 동작
[ ] 실손 최초 → 단독실손(초회)
[ ] 실손 갱신 → 단독실손(갱신)
[ ] 연금 상품 → 연금
[ ] 저축 상품 → 저축
[ ] 일반 상품 → 보장
[ ] 수정률 130 → 130%
[ ] 삼성/농협/KB/DB 손보 영향 없음
[ ] 생명보험 환산율 영향 없음
```

---

# 운영 주의사항

- migration 불필요
- model 변경 없음
- URL 변경 없음
- static rebuild 불필요
- replace 모드 재업로드 권장
- 기존 롯데 데이터 초기화 후 재업로드 권장

---

# 최종 SSOT

롯데손해보험 수정률 정책:

```text
좌/우 병렬 상품 block pair 기반 처리
우측 "좌동" → 좌측 block 사용
우측 "판매중지" → 전체 제외
수정률은 raw 백분율 그대로 저장
DB손보만 legacy ×100 표시 유지
```

---

# 한화손해보험(FIRE) 수정률 정규화 — Final SSOT (2026-05-18 추가)

## 개요

한화손해보험 수정률 RAW 파일을 `RateExampleConversionRow` 기준으로 정규화한다.

대상:

```text
insurer_type = fire
category = conv
insurer = 한화
```

정규화 파일:

```python
commission/services/rate_example_normalizers/fire_hanhwa.py
```

핵심 목적:

- 한화손해보험 raw xlsx 내 반복 테이블을 상품 단위로 인식한다.
- 손해보험 수정률 단일 컬럼 구조에 맞춰 `year1`에 수정률을 저장한다.
- `보장(태아)` 상품군의 구분 값에서 `주)` 텍스트를 제거한다.
- 납기 값이 `수금`인 컬럼은 정규화 대상에서 제외한다.

---

## 저장 구조

모델:

```python
RateExampleConversionRow
```

| 정규화 컬럼 | DB 필드 | 정책 |
|---|---|---|
| 보험사 | `insurer` | `한화` 고정 |
| 상품군 | `coverage_type` | 보장 / 보장(태아) / 연금 / 저축 / 단독실손(초회) / 단독실손(갱신) |
| 상품명 | `product_name` | 최초 `구분` 셀 2행 상단의 `○` 포함 텍스트 |
| 구분 | `plan_type` | B/C열 조합 |
| 납기 | `pay_period` | 신계약환산율 하위 헤더 또는 환산율 포함 헤더 |
| 수정률 | `year1` | raw 백분율 표시값 그대로 저장 |
| 미사용 | `year2~year4` | `None` 저장 |

---

## 원본 파일 구조 기준

### 테이블 시작 기준

B열 값이 다음과 같은 행을 상품 테이블 헤더로 판단한다.

```text
구분
구  분
구    분
```

raw 파일에는 `구  분`처럼 중간 공백이 포함될 수 있으므로, 헤더 비교 시 공백 제거 정규화가 필수다.

구현 helper:

```python
def _norm_key(value):
    return re.sub(r"\s+", "", _flat_text(value))
```

테이블 헤더 판정:

```python
if _norm_key(values[r][2]) != "구분":
    continue
```

---

## 병합 셀 처리 정책

한화 raw 파일은 병합 셀이 존재하므로 parser 내부 matrix에서만 병합 값을 전개한다.

```text
병합 범위 전체 = 좌상단 셀 값
```

금지:

```python
ws.unmerge_cells(...)
```

주의:

- 실제 workbook을 수정하지 않는다.
- 정규화 전용 `values`, `formats` matrix에서만 병합 값을 전파한다.
- openpyxl workbook은 `read_only=False`로 로드되어야 한다.

---

## 상품명(product_name) 정규화 정책

상품명은 각 테이블의 최초 `구분` 셀 기준으로 2행 상단에서 찾는다.

기준:

```text
최초 "구분" 셀 2행 상단의 "○" 기호 포함 텍스트
```

정규화:

- `○`, `●`, `◯`, `◎`, `ㆍ`, `-` 등 선행 기호 제거
- 줄바꿈 제거
- 다중 공백 제거
- trim 처리

예:

```text
○ 한화 더건강한 한아름종합보험 무배당2604
→ 한화 더건강한 한아름종합보험 무배당2604
```

보조 탐색:

```text
header_row - 2
header_row - 3
header_row - 4
header_row - 1
```

raw 병합/공백 변동에 대비하여 위 범위에서 `○` 포함 텍스트를 찾는다.

---

## 구분(plan_type) 정규화 정책

기준 컬럼:

| 컬럼 | 의미 |
|---|---|
| B열 | 구분 1 |
| C열 | 구분 2 |

조합 규칙:

| 조건 | 저장값 |
|---|---|
| B열 값만 존재 | B열 값 |
| B열 값과 C열 값이 동일 | B열 값 |
| B열 값과 C열 값이 다름 | `B열 값 (C열 값)` |

예:

```text
B열: 보장/적립
C열: 1종, 2종
→ 보장/적립 (1종, 2종)
```

```text
B열: 보장/적립
C열: 3종, 4종
→ 보장/적립 (3종, 4종)
```

---

## 보장(태아) 구분 후처리 정책

추가 요구사항:

```text
보장(태아) 상품의 구분 컬럼 데이터에서 "주)" 텍스트 삭제
```

적용 조건:

```python
coverage_type == "보장(태아)"
```

처리:

```python
text = text.replace("주)", "")
```

예:

| 기존 | 최종 |
|---|---|
| `주)기본형` | `기본형` |
| `주) 실속형` | `실속형` |
| `주)표준형 (1종)` | `표준형 (1종)` |

주의:

- 전체 상품군에 일괄 적용하지 않는다.
- `보장`, `연금`, `저축`, `단독실손(초회)`, `단독실손(갱신)`은 기존 구분 값을 유지한다.

---

## 납기(pay_period) 정규화 정책

### Case 1. `신계약환산율` 헤더가 있는 경우

`신계약환산율` 하위 세부 헤더를 납기로 사용한다.

예:

```text
신계약환산율
 ├─ 10년납
 ├─ 15년납
 └─ 20년납
```

저장:

```text
10년납
15년납
20년납
```

---

### Case 2. `신계약환산율` 헤더가 없는 경우

`구분` 컬럼 우측의 `환산율` 포함 헤더에서 `환산율` 단어를 제거한 값을 납기로 사용한다.

예:

```text
만기후재가입시 및 갱신시 환산율
→ 만기후재가입시 및 갱신시
```

---

## 납기 `수금` 제외 정책

한화 raw 일부 테이블에는 납기 후보로 다음 값들이 함께 존재한다.

```text
갱신시
최초계약시
수금
```

이 중 `수금`은 실제 납기 개념이 아니라 내부 수금 기준값 컬럼이므로 정규화에서 제외한다.

구현 조건:

```python
if _norm_key(pay_period) == "수금":
    continue
```

필수 검증:

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; print(R.objects.filter(insurer='한화', pay_period='수금').count())"
```

기대 결과:

```text
0
```

---

## 상품군(coverage_type) 정규화 정책

허용 상품군:

```python
PRODUCT_GROUPS = {
    "보장",
    "보장(태아)",
    "연금",
    "저축",
    "단독실손(초회)",
    "단독실손(갱신)",
}
```

### 단독실손

조건:

```text
상품명에 "실손" 포함
```

분기:

| 납기 조건 | 상품군 |
|---|---|
| 납기에 `최초` 포함 | 단독실손(초회) |
| 납기에 `갱신` 포함 | 단독실손(갱신) |
| 그 외 | 단독실손(갱신) |

### 연금

조건:

```text
상품명에 "연금" 포함
```

저장:

```text
연금
```

### 저축

조건:

```text
상품명에 "저축" 포함
```

저장:

```text
저축
```

### 태아

조건:

```text
구분에 "태아관련" 포함
```

저장:

```text
보장(태아)
```

### 일반 상품

그 외:

```text
보장
```

---

## 수정률(year1) 저장 정책

수정률은 raw 백분율 표시값을 그대로 저장한다.

| raw | 저장값 | 화면 표시 |
|---|---:|---:|
| `2%` | `2` | `2%` |
| `160%` | `160` | `160%` |
| `220` | `220` | `220%` |

주의:

- `×100` 금지
- `/100` 금지
- `/0.97` 보정 금지
- `year2`, `year3`, `year4`는 `None` 저장

문자열에 숫자와 `%` 외 문자가 섞여 있으면 숫자만 추출해 저장한다.

예:

```text
160% 주)
→ 160
```

---

## 데이터 행 제외 정책

다음 행은 정규화하지 않는다.

```text
B열 공란
B열이 구분/구  분 헤더
B열이 ※로 시작
B열이 주)로 시작
수정률 값이 비어 있는 행
납기가 수금인 컬럼
```

---

## 최종 중복 방어 정책

저장 전 dedupe를 수행한다.

중복 판단 기준:

| 기준 |
|---|
| 상품군 |
| 상품명 |
| 구분 |
| 납기 |
| 수정률 |

동일 key는 최초 row만 유지한다.

---

## Orchestrator 연동

### `commission/services/rate_example_normalizers/__init__.py`

import 추가:

```python
from commission.services.rate_example_normalizers.fire_hanhwa import (
    build_fire_hanhwa_conversion_rows,
)
```

`__all__` 추가:

```python
"build_fire_hanhwa_conversion_rows",
```

---

### `commission/services/rate_example_normalizer.py`

대상 보험사 추가:

```python
is_fire_conv_target = (
    example.insurer_type == RateExample.TYPE_FIRE
    and example.category == RateExample.CAT_CONV
    and example.insurer in {"DB", "KB", "농협", "롯데", "삼성", "한화"}
)
```

실행 분기 추가:

```python
elif example.insurer_type == RateExample.TYPE_FIRE and example.insurer == "한화":
    normalized_rows.extend(build_fire_hanhwa_conversion_rows(example, wb))
```

주의:

- 한화생명(`life_hanhwa.py`) 분기와 혼동하지 않는다.
- 손해보험 한화는 반드시 `example.insurer_type == RateExample.TYPE_FIRE` 조건 안에서 먼저 처리한다.

---

## 조회 API 정책

조회 API는 기존 `RateExampleConversionRow` 조회를 그대로 사용한다.

조건:

```python
RateExampleConversionRow.objects.filter(
    insurer_type="fire",
    category="conv",
    insurer="한화",
)
```

손보 수정률 화면에서는 `year1`을 `mod_rate`로 렌더링한다.

DB손보만 legacy 표시 정책을 유지한다.

```python
shown = value * 100 if row.insurer == "DB" else value
```

따라서 한화는 저장값에 `%`만 붙여 표시한다.

---

## 초기화/재업로드 절차

기존 한화 데이터 초기화:

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; print(R.objects.filter(insurer_type='fire', category='conv', insurer='한화').delete())"
```

재업로드:

```text
손해보험 / 수정률 / 한화 / replace
```

검증:

```powershell
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; qs=R.objects.filter(insurer_type='fire', category='conv', insurer='한화'); print(qs.count()); print(qs.values('coverage_type','product_name','plan_type','pay_period','year1')[:10])"
```

---

## 필수 검증 항목

```text
[ ] 한화 업로드 시 normalized_count > 0
[ ] 수정률 조회 모달에서 보험사=한화 조회 가능
[ ] B열 "구  분" 헤더를 정상 인식
[ ] 상품명에서 "○" 기호 제거
[ ] B/C열 구분 조합이 "B (C)" 형태로 저장
[ ] 보장(태아) 상품 구분에서 "주)" 제거
[ ] pay_period="수금" row 0건
[ ] 실손 최초 → 단독실손(초회)
[ ] 실손 갱신 → 단독실손(갱신)
[ ] 연금 상품 → 연금
[ ] 저축 상품 → 저축
[ ] 일반 상품 → 보장
[ ] 수정률 160 → 160% 표시
[ ] DB/KB/농협/삼성/롯데 손보 영향 없음
[ ] 생명보험 한화 정규화 영향 없음
[ ] 생명보험 환산율/지급률 영향 없음
```

---

## 운영 주의사항

- migration 불필요
- model 변경 없음
- URL 변경 없음
- static rebuild 불필요
- 권한 변경 없음
- superuser 업로드 정책 유지
- replace 모드 재업로드 권장
- 기존 한화 row가 잘못 생성된 이력이 있으면 반드시 삭제 후 재업로드한다.

---

## 최종 SSOT

한화손해보험 수정률 정책:

```text
B열 "구분/구  분" 테이블 기준 처리
상품명은 "○" 포함 제목에서 기호 제거
B/C열 구분이 다르면 "B (C)"로 결합
보장(태아) 구분의 "주)" 제거
납기 "수금" 컬럼 제외
수정률은 raw 백분율 그대로 year1 저장
```

