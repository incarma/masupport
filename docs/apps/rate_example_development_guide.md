# Rate Example Development Guide — Final Edition

> 기준 프로젝트: django_ma  
> 대상 앱: commission  
> 목적: 수수료 예시표(환산율/지급률) 업로드·정규화·옵션조회·계산·예시표 출력 기능의 최종 SSOT 가이드

---

# 1. 시스템 개요

Rate Example 시스템은 다음 기능을 통합 제공한다.

- 보험사별 raw 파일 업로드
- 환산율/수정률 정규화
- 지급률 정규화
- 상품/구분/납기 옵션 조회
- 수수료 예시 계산
- 예시표 엑셀/PDF 출력
- 보험사별 개별 파서(normalizer) 관리
- PDF 복합 헤더/좌표 기반 fallback 정규화 관리

핵심 원칙:

- 보험사별 파싱 규칙은 파일 단위로 분리
- 정규화 데이터는 단일 테이블(SSOT) 기준 사용
- 계산 로직은 서비스 레이어로 분리
- 프론트는 dataset 기반 URL 주입 사용
- 업로드/다운로드는 권한 검증 후 처리
- replace / append 정책 유지

---

# 2. 핵심 모델 구조

## 2-1. RateExample

원본 업로드 파일 메타 정보 저장.

주요 필드:

- insurer_type
- insurer
- category
- file
- uploaded_by
- uploaded_at

---

## 2-2. RateExampleConversionRow

환산율/수정률 정규화 테이블.

주요 필드:

- insurer_type
- insurer
- coverage_type
- strategy_flag
- product_name
- plan_type
- pay_period
- year1
- year2
- year3
- year4

운영 규칙:

- 퍼센트는 Decimal("100.0") 형태 저장
- 100% → 100.0
- scientific notation 금지
- UI 출력 시 trailing % 사용

---

## 2-3. RateExamplePayRow

지급률 정규화 테이블.

주요 필드:

- insurer
- product_name
- plan_type
- pay_period
- initial_rate
- month13_rate
- year2_rate
- year3_rate
- month36_rate
- month37_rate
- year4_rate

운영 규칙:

최종 저장값:

```python
normalized_rate = raw_rate / Decimal("0.97")
```

백엔드 저장 시 반드시 적용.

---

# 3. 정규화 아키텍처

## 3-1. 진입점

파일:

```python
commission/services/rate_example_normalizer.py
```

역할:

- 업로드 파일 로드
- 보험사별 normalizer dispatch
- replace / append 처리
- bulk_create 수행

---

## 3-2. 보험사별 normalizer 구조

위치:

```python
commission/services/rate_example_normalizers/
```

규칙:

- 보험사별 파일 분리
- build_* 함수 export
- __init__.py 에 등록

예시:

```python
from commission.services.rate_example_normalizers.life_kb import (
    build_life_kb_general_conversion_rows,
)
```

---

# 4. normalize_mode 정책

## replace

기존 데이터 삭제 후 재적재.

삭제 기준:

```python
(insurer_type, insurer, category)
```

---

## append

기존 데이터 유지 후 추가 적재.

중복 허용.

---

# 5. 보험사별 정규화 규칙

# 5-1. ABL

파일:

```python
life_abl.py
```

규칙:

- 퍼센트 보정
- 특약 제외
- Decimal 백분율 저장

---

# 5-2. DB

파일:

```python
life_db.py
```

규칙:

- 방카교차 제외
- 특약 제외
- 상품명 기반 보종 판별

13회/2차년 계산 정책은 별도 계산 서비스에서 처리.

---

# 5-3. IM

파일:

```python
life_im.py
```

규칙:

- "(총괄)환산성적표" 시트만 사용
- E열 == "주계약"
- L열 == "미판매" 제외
- 납기 문자열 원문 유지
- scientific notation 방지

---

# 5-4. KB

파일:

```python
life_kb.py
```

일반상품:

- 특약 제외
- 괄호 기반 구분 추출
- 보종 자동 판별

건강보험:

- "특약" 이후 전체 제외
- 보종 = 기타(보장성)

추가 방어:

- 헤더 텍스트 "상품" 제거
- 데이터 시작행 정확히 제한

---

# 5-5. KDB

파일:

```python
life_KDB.py
```

규칙:

- "GA 주계약" 시트
- 병합셀 전체 전개
- 납기 + 연령 결합
- 구분 공백 허용

---

# 5-6. 교보

파일:

```python
life_kyobo.py
```

규칙:

- 다중 병렬 테이블
- 판매중지 제외
- 상품명 carry-down
- 테이블별 파서 분리

---

# 5-7. 동양

파일:

```python
life_dongyang.py
```

규칙:

- 주계약 시트만 사용
- 1~12행 제외
- 상품명 = 대표상품명(B열)
- 구분 = 첫 번째 underscore 이후 텍스트
- 보종 자동 판별

함수명 SSOT:

```python
build_life_dongyang_conversion_rows
```

---

# 5-8. 라이나

파일:

```python
life_lina.py
```

규칙:

- 병합셀 완전 해제
- 줄바꿈 상품명 정리
- 년납 기준 필터링
- 중복 문자열 제거

---

# 5-9. 메트라이프

파일:

```python
life_metlife.py
```

규칙:

- 기존 구조 기반 일반 환산율 정규화
- Decimal 퍼센트 저장
- pay_period 원문 유지

---

# 5-10. 신한

파일:

```python
life_shinhan.py
```

규칙:

- 보험사 컬럼 = 신한
- 병합셀 해제
- 상품/구분/납기 정규화
- 빈 상품행 제외

---

# 5-11. 처브

파일:

```python
life_chubb.py
```

규칙:

- "- P≥10,000원" 구분 유지
- 특수 문자열 손실 금지
- 납기 원문 유지

---

# 5-12. 카디프

파일:

```python
life_cardif.py
```

규칙:

- 병합셀 정규화
- 상품군 구조 유지
- category=conv 기준 사용

---

# 5-13. 미래에셋

파일:

```python
life_mirae.py
```

규칙:

- 보장성 시트 정규화
- 병합셀 완전 해제
- 형/종 구분 매핑
- 상품명 빈 행 제외

---

# 5-14. 삼성생명

파일:

```python
life_samsung.py
```

규칙:

- 보험사 컬럼 = 삼성
- 보장성 시트 대상
- 가로 병합:
  - 좌측 셀만 유지
- 세로 병합:
  - 전체 행 복제
- 상품명(F열)
- 구분(G열)

---

# 5-16. 하나생명

파일:

```python
life_hana.py
```

정규화 대상:

- PDF raw 파일 기반
- 첫 번째 페이지만 정규화
- 보험사 컬럼은 항상 `하나` 저장
- 정규화 함수명은 `build_life_hana_pdf_conversion_rows`

---

## 핵심 진입점 등록

`commission/services/rate_example_normalizers/__init__.py`에 export한다.

```python
from commission.services.rate_example_normalizers.life_hana import (
    build_life_hana_pdf_conversion_rows,
)
```

`commission/services/rate_example_normalizer.py`의 PDF 분기에서 `example.insurer == "하나"`일 때 호출한다.

```python
if example.insurer == "하나":
    normalized_rows = build_life_hana_pdf_conversion_rows(example)
```

`commission/services/rate_example.py`의 생명보험 환산율/수정률 무상품구분 보험사 목록에도 `하나`를 포함한다.

---

## PDF 페이지 정책

- raw PDF의 첫 번째 페이지만 사용한다.
- 2페이지 이후 특약별/부가 테이블은 하나생명 주계약 정규화 대상에서 제외한다.
- `source_sheet`는 `PDF Page 1`로 저장한다.

---

## PDF 추출 정책

하나생명 PDF는 일반 XLSX형 표가 아니라 다음 특징이 있다.

- 복합 헤더 구조
- 시각적 병합 셀
- 상품명/상품유형/심사유형/납입기간/환산율이 서로 다른 좌표 영역에 분산
- `PyMuPDF page.find_tables()`가 표는 감지하더라도 헤더 감지에 실패할 수 있음

따라서 parser는 2단계 구조로 둔다.

1. `find_tables()` 기반 table parser 우선 시도
2. 헤더 감지 실패 또는 table 미감지 시 좌표 기반 fallback parser 실행

```python
if header_idx < 0:
    rows = _build_rows_from_page_lines(example, page)
    if rows:
        return rows
```

---

## 병합/줄바꿈 처리

### 병합 처리

PDF에는 실제 Excel 병합셀 정보가 없으므로, 빈 셀/시각적 병합 구조는 carry-forward 방식으로 복원한다.

- 상품명 carry-forward
- 상품유형 carry-forward
- 심사유형 carry-forward
- 납입기간은 row anchor로 사용
- 환산율 컬럼은 잘못된 중복 방지를 위해 carry-forward하지 않음

### 줄바꿈 처리

상품명:

```python
_join_lines(value, sep="")
```

심사유형:

```python
_join_lines(value, sep=", ")
```

상품유형:

```python
_join_lines(value, sep=" ")
```

---

## 상품명(product_name) 규칙

raw 데이터의 `상품명` 컬럼 텍스트를 기본 상품명으로 사용한다.

상품명 셀이 줄바꿈되어 여러 줄이면 첫 줄 아래 텍스트를 모두 이어붙여 한 줄로 만든다.

심사유형은 괄호 안에 넣어 상품명 뒤에 붙인다.

예:

```text
(무)하나로누리는건강보험 (일반심사형, 간편심사형(3.0.5 ~ 3.5.5))
```

---

## 보종(coverage_type) 규칙

```python
if "종신" in product_name:
    coverage_type = "종신/CI"

elif "연금" in product_name and "변액" in product_name:
    coverage_type = "변액연금"

elif "연금" in product_name:
    coverage_type = "연금"

else:
    coverage_type = "기타(보장성)"
```

---

## 구분(plan_type) 규칙

raw 데이터의 `상품유형` 컬럼 값을 `plan_type`에 저장한다.

줄바꿈된 경우 각 줄을 공백 한 칸으로 연결한다.

예:

```text
해약환급금 미지급형
```

---

## 납기(pay_period) 규칙

raw 데이터의 `납입기간` 컬럼 값을 정규화 테이블의 `pay_period` 컬럼, 즉 화면의 `납기` 컬럼에 저장한다.

허용 예:

```text
5년납
7년납
10년납
15년납
20년납
20년납/30년납
전기납
일시납
전납기
非일시납
```

좌표 기반 fallback parser에서는 `납입기간` 텍스트를 row anchor로 사용한다.

```python
pay_period = _clean_cell(pay_line.text)
```

---

## 환산율(year1~year4) 규칙

raw PDF의 환산율 컬럼을 다음과 같이 매핑한다.

| raw 컬럼 | 정규화 컬럼 |
|---|---|
| `1차년` | `year1` |
| `2차년` | `year2` |
| `3차년~` | `year3` |
| `3차년~` | `year4` |

`3차년~` 값은 `year3`, `year4`에 동일 저장한다.

퍼센트는 `%`를 제거한 Decimal 백분율 값으로 저장한다.

예:

```text
130% → Decimal("130")
220% → Decimal("220")
```

---

## 제외/방어 규칙

다음 행은 제외한다.

- 상품명이 비어 있는 행
- 납입기간이 비어 있는 행
- 환산율이 모두 비어 있는 행
- 판매중지 상품
- 특약 상품
- 표 제목/기준일/비고성 행

---

## 좌표 기반 fallback 핵심 구조

```python
@dataclass(frozen=True)
class HanaPdfLine:
    y: float
    x: float
    text: str
```

핵심 흐름:

```python
lines = _extract_pdf_lines(page)
pay_lines = [
    line for line in lines
    if 340 <= line.x <= 410 and _looks_like_pay_period(line.text)
]
```

납입기간 row를 기준으로 같은 y-band의 텍스트를 묶는다.

```python
band = [
    line for line in lines
    if prev_y + 0.1 <= line.y <= y + 8.5
]
```

컬럼별 x축 범위는 PDF 좌표 추출 결과에 따라 조정 가능하도록 normalizer 내부 상수성 로직으로 유지한다.

---

## 검증 명령

```powershell
python manage.py check
python manage.py shell -c "from commission.models import RateExampleConversionRow as R; print(R.objects.filter(insurer='하나').count())"
```

업로드 후 `하나` 보험사 기준 row 수가 0이면 다음을 점검한다.

1. `Hana PDF header not detected` 로그 발생 여부
2. fallback parser 진입 여부
3. `_looks_like_pay_period()`가 납입기간 텍스트를 감지하는지
4. PDF 좌표 범위(`x_min/x_max`)가 실제 파일과 맞는지
5. `pay_period`가 `납기` 필터 옵션에 노출되는지

---

# 6. 지급률 정규화 정책

지급률은 환산율과 별도 테이블 관리.

저장 정책:

```python
stored_rate = raw_rate / Decimal("0.97")
```

반드시 백엔드 저장 시 적용.

프론트 계산 금지.

---

# 7. 옵션 조회 서비스

파일:

```python
commission/services/rate_example_options.py
```

역할:

- 보험사 목록
- 상품명 목록
- 구분 목록
- 납기 목록

조회 SSOT:

```python
RateExampleConversionRow
```

단:

IBK 상품군은 지급률 테이블 기준 조회.

---

# 8. 계산 서비스

파일:

```python
commission/services/rate_example_calculator.py
```

역할:

- 예시표 계산
- 지급률 적용
- 차년도 계산
- 소계 계산

---

# 9. IBK 계산 규칙

익월:

```python
보험료 × 초회 지급률 × 수수료율
```

13회:

```python
보험료 × 13회 지급률 × 수수료율
```

2차년:

```python
보험료 × 2차년 지급률 × 수수료율
```

동일 방식:

- 3차년
- 36회
- 37회
- 4차년

---

# 10. 프론트엔드 규칙

페이지:

```html
rate_example_home.html
```

원칙:

- dataset 기반 URL 주입
- fetch 직접 하드코딩 금지
- 공통 CSRF 사용
- readJsonOrThrow 사용

---

# 11. API 응답 규칙

성공:

```json
{
  "ok": true
}
```

실패:

```json
{
  "ok": false,
  "message": "..."
}
```

---

# 12. 보안 규칙

금지:

```html
{{ file.url }}
```

반드시 다운로드 뷰 경유.

---

# 13. Audit 규칙

업로드/삭제/대량변경 시:

```python
log_action(...)
```

필수.

---

# 14. CSS 규칙

앱 스코프 유지:

```css
#rate-example-home .class { }
```

전역 오염 금지.

---

# 15. JS 규칙

금지:

```javascript
document.cookie.match(...)
```

반드시:

```javascript
getCSRFToken()
```

사용.

---

# 16. Harness 점검

실행:

```bash
bash scripts/harness/run_all.sh
```

포함:

- security_lint.sh
- quality_lint.sh
- celery_check.sh
- css_scope_check.sh

---

# 17. 주요 운영 체크리스트

## 업로드 후

- collectstatic 여부
- celery task 등록 여부
- audit 로그 여부
- replace 동작 여부
- scientific notation 여부
- 납기 문자열 손실 여부
- 병합셀 해제 여부
- 특약 제외 여부

---

# 18. 절대 금지 사항

금지:

- @csrf_exempt
- att.file.url 직접 노출
- request.user.username 사용
- JS URL 하드코딩
- CSS 전역 오염
- audit 없는 grade 변경

---

# 19. 권장 개발 순서

1. raw 파일 분석
2. 병합셀 구조 확인
3. 데이터 시작행 확인
4. 상품명/구분/납기(pay_period) 매핑
5. 퍼센트 보정
6. Decimal 저장
7. replace 검증
8. modal 출력 검증
9. 계산 검증
10. harness 검증

---

# 20. 참고 SSOT 문서

- django_ma_master.md
- guide_commission.md
- security_guide.md
- frontend_guide.md
- security_checklist.md
- quality_checklist.md
- NEVER_DO.md
- HARNESS_RULES.md
- QUALITY_RULES.md

