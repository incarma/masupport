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
