# Rate Example Development Guide — Final Edition (DB생명 계산식 포함)

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
