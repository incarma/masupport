# 업무관리 캘린더 대한민국 공휴일 연동 설계지침서

> 대상: `django_ma` 프로젝트 `board` 앱의 `WorkTask` 캘린더
> 단계: 설계 전용 문서 — 실제 코드 패치 전 검토용
> 핵심 구조: **외부 공휴일 API → Celery 수집 → DB 캐시 → WorkTask 캘린더 렌더링**

---

## 1. 목적

업무관리 페이지 상단 캘린더에 대한민국 기준 공휴일을 안정적으로 표시한다.

단순 하드코딩 방식은 임시공휴일, 대체공휴일, 선거일 등 수시 변경 이슈에 자동 대응할 수 없으므로 운영 환경에서는 부적합하다. 따라서 외부 공휴일 데이터를 주기적으로 수집하고, 이를 DB에 캐시한 뒤 화면에서는 내부 DB만 조회하는 구조를 사용한다.

---

## 2. 결론 요약

권장 구조는 다음과 같다.

```text
공휴일 외부 API
    ↓
Celery task 또는 management command
    ↓
Holiday DB 캐시 테이블
    ↓
board.views.worktasks.worktask_list
    ↓
json_script
    ↓
static/js/board/worktask_list.js
    ↓
캘린더 날짜 칸에 공휴일 표시
```

운영 원칙:

- View에서 외부 API를 직접 호출하지 않는다.
- 브라우저 JS에서 외부 API를 직접 호출하지 않는다.
- 공휴일 데이터는 DB 캐시를 SSOT로 사용한다.
- Celery/관리 명령은 외부 API 수집과 DB upsert만 담당한다.
- 캘린더 렌더링은 기존 WorkTask 캘린더 데이터와 공휴일 데이터를 분리해서 처리한다.

---

## 3. 왜 DB 캐시가 필요한가

### 3.1 하드코딩 방식의 문제

하드코딩은 다음 상황에 자동 대응하지 못한다.

- 임시공휴일 추가
- 대체공휴일 정책 변경
- 선거일 지정
- 정부 긴급 지정 휴일
- API 기준 변경 후 기존 목록과 실제 공휴일 불일치

따라서 하드코딩은 개발 초기 목업 또는 긴급 임시 대응에만 적합하다.

### 3.2 View 직접 API 호출의 문제

`worktask_list` 진입 시마다 외부 API를 호출하면 다음 문제가 발생한다.

- 페이지 로딩 지연
- 외부 API 장애 시 업무관리 페이지 장애 전파
- API rate limit 또는 service key 장애
- 운영 로그에서 장애 원인 추적 어려움
- 테스트 재현성 저하

따라서 View는 내부 DB만 조회해야 한다.

### 3.3 JS 직접 API 호출의 문제

브라우저에서 외부 API를 직접 호출하면 다음 문제가 발생한다.

- API Key 노출 가능성
- CORS 문제
- 사용자 네트워크 환경에 따른 렌더링 불안정
- 감사/운영 로그 통제 어려움

따라서 JS는 서버가 내려준 `json_script`만 읽는다.

---

## 4. 적용 범위

### 포함 범위

- 대한민국 공휴일 데이터 캐시 모델
- 외부 API 수집 태스크 설계
- Celery Beat 주기 실행 설계
- 수동 재수집 management command 설계
- WorkTask 캘린더 view 연동 설계
- 프론트 렌더링 데이터 계약
- 운영 장애 대응 및 롤백 전략

### 제외 범위

- 실제 코드 패치
- API Key 발급 절차 세부 안내
- 기존 WorkTask 캘린더 UI 대규모 리디자인
- 토요일/일요일 다시 노출 정책 변경

---

## 5. 앱/모듈 배치 설계

공휴일 데이터는 board 앱 전용이라기보다는 전사 공통 데이터에 가깝다. 다만 현재 사용처가 WorkTask 캘린더 하나라면 다음 두 가지 선택지가 있다.

### 선택안 A: `board` 앱 내부 배치

```text
board/
├── models.py
├── services/
│   ├── worktasks.py
│   └── holidays.py
├── tasks.py
└── management/commands/
    └── sync_kr_holidays.py
```

장점:

- 적용 범위가 명확하다.
- 초기 구현이 빠르다.
- board 캘린더와 함께 관리하기 쉽다.

단점:

- 추후 dash/manual/partner 등 다른 앱에서 공휴일을 쓰면 공통화가 필요하다.

### 선택안 B: `core` 또는 `common` 앱 신설

```text
common/
├── models.py
├── services/
│   └── holidays.py
├── tasks.py
└── management/commands/
    └── sync_kr_holidays.py
```

장점:

- 전사 공통 캘린더/영업일 계산으로 확장 가능하다.
- WorkTask 외 다른 앱에서도 재사용 가능하다.

단점:

- 새 앱 추가, migration, admin, import path 정리가 필요하다.

### 권장

현재 단계에서는 **board 내부 배치**를 권장한다. 향후 다른 앱에서 공휴일/영업일 계산이 필요해지면 `common` 앱으로 분리한다.

---

## 6. 데이터 모델 설계

### 6.1 모델명

권장 모델명:

```python
KrHoliday
```

후보:

- `Holiday`: 범용적이나 국가 구분이 불명확하다.
- `KrHoliday`: 대한민국 기준임이 명확하다.
- `CalendarHoliday`: 캘린더 도메인 확장에 유리하다.

### 6.2 필드 설계

```text
KrHoliday
├── date              DateField(unique=True, db_index=True)
├── name              CharField(max_length=80)
├── is_holiday        BooleanField(default=True)
├── is_temporary      BooleanField(default=False)
├── source            CharField(max_length=30, default="api")
├── source_event_id   CharField(max_length=80, blank=True, default="")
├── raw_payload       JSONField(default=dict, blank=True)
├── fetched_at        DateTimeField(null=True, blank=True)
├── created_at        DateTimeField(auto_now_add=True)
└── updated_at        DateTimeField(auto_now=True)
```

### 6.3 필드 설명

| 필드 | 목적 |
|---|---|
| `date` | 공휴일 날짜. 캘린더 매칭의 핵심 키 |
| `name` | 화면에 표시할 공휴일명 |
| `is_holiday` | API가 휴일 여부를 제공하는 경우 저장. 일반적으로 True만 렌더링 |
| `is_temporary` | 임시공휴일 추정/수동 지정 여부 |
| `source` | `api`, `manual`, `override` 등 출처 |
| `source_event_id` | 외부 API 원천 식별자. 없으면 빈 문자열 |
| `raw_payload` | 원본 응답 일부 저장. 디버깅/감사용 |
| `fetched_at` | 마지막 수집 시각 |
| `created_at`, `updated_at` | 운영 추적용 |

### 6.4 unique 정책

기본은 `date` unique를 권장한다.

이유:

- 캘린더 표시 기준은 날짜 1개당 공휴일 표시 1개면 충분하다.
- 같은 날짜에 여러 명칭이 있을 수 있으나 화면에서는 병합 표시하면 된다.
- 운영 단순성이 높다.

다만 추후 여러 이벤트를 동일 날짜에 모두 표시해야 하면 아래 구조로 확장한다.

```text
unique_together = (date, name)
```

현재 WorkTask 캘린더 목적에서는 `date unique`가 더 적합하다.

---

## 7. 외부 API 수집 설계

### 7.1 데이터 소스

권장 데이터 소스는 공공데이터 기반의 대한민국 특일/공휴일 정보 API다.

운영 설계상 중요한 것은 특정 API 이름보다 다음 조건이다.

- 연도 단위 조회 가능
- 날짜, 명칭, 휴일 여부 제공
- API Key 기반 인증
- 정부/공공기관 데이터 기반
- 장애 시 재시도 가능

### 7.2 API Key 관리

API Key는 `.env` 또는 운영 Secret으로 관리한다.

권장 환경변수:

```text
KR_HOLIDAY_API_ENABLED=true
KR_HOLIDAY_API_KEY=...
KR_HOLIDAY_API_BASE_URL=...
KR_HOLIDAY_FETCH_YEARS_BEFORE=1
KR_HOLIDAY_FETCH_YEARS_AFTER=2
```

주의:

- settings.py에 key를 하드코딩하지 않는다.
- template 또는 JS에 key를 절대 노출하지 않는다.
- 로그에 전체 URL을 남길 경우 serviceKey가 노출되지 않도록 마스킹한다.

---

## 8. 수집 서비스 설계

### 8.1 서비스 파일

```text
board/services/holidays.py
```

### 8.2 주요 함수

```python
def fetch_kr_holidays_from_api(year: int) -> list[dict]:
    """외부 API에서 특정 연도 공휴일 원천 데이터를 가져온다."""


def normalize_holiday_row(raw: dict) -> dict:
    """API 응답 1건을 KrHoliday upsert 가능한 dict로 정규화한다."""


def sync_kr_holidays_for_year(year: int, *, actor=None, source="api") -> dict:
    """특정 연도 공휴일을 수집하고 DB에 upsert한다."""


def get_holidays_between(start: date, end: date) -> list[dict]:
    """캘린더 렌더링용 공휴일 목록을 반환한다."""
```

### 8.3 반환 포맷

`sync_kr_holidays_for_year()` 반환 예시:

```json
{
  "ok": true,
  "year": 2026,
  "fetched": 18,
  "created": 1,
  "updated": 17,
  "skipped": 0
}
```

`get_holidays_between()` 반환 예시:

```json
[
  {"date": "2026-05-05", "name": "어린이날", "is_temporary": false},
  {"date": "2026-05-25", "name": "부처님오신날", "is_temporary": false}
]
```

---

## 9. Celery Task 설계

### 9.1 태스크 파일

기존 `web_ma/celery.py`에서 앱 task autodiscover가 동작하므로 board 앱에 둔다.

```text
board/tasks.py
```

이미 board task가 있다면 동일 파일에 추가한다.

### 9.2 태스크 목록

```python
@shared_task(name="board.sync_kr_holidays_for_year")
def sync_kr_holidays_for_year_task(year: int) -> dict:
    ...


@shared_task(name="board.sync_kr_holidays_window")
def sync_kr_holidays_window_task() -> dict:
    ...
```

### 9.3 수집 범위

권장 기본 범위:

```text
현재 연도 - 1년
현재 연도
현재 연도 + 1년
현재 연도 + 2년
```

이유:

- 전년도 데이터: 과거 조회/월 이동 대응
- 현재 연도: 기본 화면 대응
- 다음 1~2년: 연말/연초 업무계획 대응

환경변수로 조정 가능하게 한다.

```text
KR_HOLIDAY_FETCH_YEARS_BEFORE=1
KR_HOLIDAY_FETCH_YEARS_AFTER=2
```

### 9.4 Celery Beat 주기

권장 스케줄:

```text
매일 04:20  sync_kr_holidays_window
매월 1일 04:40 sync_kr_holidays_window
```

매일 실행하는 이유:

- 임시공휴일이 갑자기 지정될 수 있다.
- 외부 API 반영 시점을 예측하기 어렵다.
- upsert 구조라 매일 실행해도 데이터 중복 위험이 낮다.

### 9.5 락 정책

중복 실행 방지를 위해 cache lock을 사용한다.

```text
lock key: board:kr_holidays:sync:YYYY
TTL: 10분
```

전체 window task는 연도별 task를 순차 실행하거나 내부 loop로 처리한다.

---

## 10. Management Command 설계

운영자가 수동으로 재수집할 수 있어야 한다.

```text
python manage.py sync_kr_holidays --year 2026
python manage.py sync_kr_holidays --from-year 2025 --to-year 2028
python manage.py sync_kr_holidays --window
```

### 옵션

| 옵션 | 의미 |
|---|---|
| `--year` | 특정 연도만 수집 |
| `--from-year` | 시작 연도 |
| `--to-year` | 종료 연도 |
| `--window` | settings 기준 기본 window 수집 |
| `--dry-run` | DB 저장 없이 결과만 출력 |
| `--force` | lock 무시 또는 기존 데이터 덮어쓰기 |

### 사용 시나리오

- 임시공휴일 발표 직후 즉시 반영
- 운영 장애 후 재수집
- API Key 교체 후 검증
- 배포 직후 초기 데이터 적재

---

## 11. WorkTask View 연동 설계

### 11.1 기존 흐름

현재 `worktask_list`는 다음 데이터를 template에 내려준다.

```text
calendar_items
calendar_today
calendar_anchor
calendar_view
calendar_week_start
calendar_week_end
calendar_month_start
calendar_month_end
```

이 흐름은 유지한다.

### 11.2 추가할 데이터

```python
calendar_holidays = get_holidays_between(
    calendar_range_start,
    calendar_range_end,
)
```

template context:

```python
"calendar_holidays": calendar_holidays
```

### 11.3 Template 계약

```html
{{ calendar_holidays|json_script:"worktask-calendar-holidays" }}
```

기존 `calendar_items`와 분리한다.

```html
{{ calendar_items|json_script:"worktask-calendar-items" }}
{{ calendar_holidays|json_script:"worktask-calendar-holidays" }}
```

분리 이유:

- 업무 일정과 공휴일은 데이터 성격이 다르다.
- 업무 일정은 owner scope 대상이다.
- 공휴일은 공통 public calendar 데이터다.
- 프론트 렌더링에서 표시 레이어를 분리할 수 있다.

---

## 12. 프론트 JS 연동 설계

### 12.1 읽기 함수

```javascript
function _readCalendarHolidays() {
  const el = document.getElementById("worktask-calendar-holidays");
  if (!el) return {};

  try {
    const rows = JSON.parse(el.textContent || "[]");
    return rows.reduce((acc, row) => {
      if (row.date) acc[row.date] = row;
      return acc;
    }, {});
  } catch (e) {
    console.warn("[worktask_list] holiday json parse failed", e);
    return {};
  }
}
```

### 12.2 렌더링 위치

`_renderCalendar()`에서 날짜 숫자 아래에 표시한다.

```javascript
const holiday = holidays[key];
if (holiday) {
  html.push(`
    <div class="worktask-calendar-holiday" title="${_escAttr(holiday.name)}">
      ${_escHtml(holiday.name)}
    </div>
  `);
}
```

### 12.3 주말 제외 정책과의 관계

현재 캘린더는 월~금만 표시한다.

따라서:

- 토요일 공휴일: 화면 미표시
- 일요일 공휴일: 화면 미표시
- 평일 공휴일: 화면 표시
- 대체공휴일이 평일이면 표시

이 정책은 현재 사용자의 요청과 일치한다.

---

## 13. CSS 설계

```css
.board-scope .worktask-calendar-holiday{
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  margin-bottom: 4px;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
  color: #dc3545;
  background: #fff5f5;
  border: 1px solid #f1aeb5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.board-scope .worktask-calendar-day.is-holiday{
  background: #fffafa;
}
```

공휴일은 업무 아이템보다 위에 배치하는 것을 권장한다.

날짜 칸 구조 예시:

```text
[5]
어린이날
업무 A
업무 B
```

---

## 14. Audit / Logging 설계

### 14.1 수집 로그

공휴일 수집은 운영 데이터 동기화 행위이므로 로그 대상이다.

필수 로그 항목:

```text
year
fetched_count
created_count
updated_count
skipped_count
success
error_message
elapsed_ms
```

### 14.2 AuditLog 대상 여부

공휴일 데이터는 사용자 개인정보나 권한 데이터는 아니지만, 운영 화면에 영향을 주는 기준 데이터다.

권장:

- Celery 자동 수집: 일반 logger INFO
- 수동 management command: logger INFO
- 관리자 UI에서 수동 override 기능을 만들 경우: AuditLog 기록

### 14.3 로그 예시

```text
INFO board.holidays sync_kr_holidays year=2026 fetched=18 created=1 updated=17 skipped=0 elapsed_ms=932 success=true
ERROR board.holidays sync_kr_holidays year=2026 error="API timeout" success=false
```

---

## 15. 장애 대응 설계

### 15.1 외부 API 장애

동작 원칙:

- 기존 DB 캐시를 유지한다.
- 화면은 기존 캐시 기준으로 계속 동작한다.
- Celery task만 실패 로그를 남긴다.
- 사용자 화면에 외부 API 장애를 노출하지 않는다.

### 15.2 API Key 만료/오류

대응:

1. task 실패 로그 확인
2. API Key 교체
3. `sync_kr_holidays --window` 수동 실행
4. 업무관리 캘린더 확인

### 15.3 잘못된 공휴일 데이터 유입

대응:

- `source="manual"` 또는 `source="override"` 수동 보정 가능 구조를 둔다.
- API 재수집 시 수동 override를 덮어쓸지 여부를 정책으로 분리한다.

권장 정책:

```text
source="override" 데이터는 API sync에서 덮어쓰지 않는다.
source="api" 데이터만 API sync에서 갱신한다.
```

---

## 16. 수동 Override 설계

임시공휴일이 API에 늦게 반영되는 경우를 대비해 수동 등록 기능을 고려한다.

### 16.1 1단계: Django Admin 관리

`KrHoliday`를 admin에 등록한다.

관리자는 다음 필드를 수정할 수 있다.

- date
- name
- is_holiday
- is_temporary
- source

### 16.2 2단계: 별도 운영 UI

추후 필요 시 superuser 전용 UI를 만든다.

```text
/board/holidays/
```

초기 단계에서는 Django Admin만으로 충분하다.

### 16.3 Override 정책

- 관리자 수동 등록: `source="override"`
- API sync는 `source="override"` 레코드를 덮어쓰지 않음
- 같은 날짜에 API 값이 들어오면 override 우선

---

## 17. 보안 설계

### 17.1 API Key 보호

- `.env`에서만 관리
- JS/template에 노출 금지
- 로그에 serviceKey 포함 URL 출력 금지
- 설정값 출력 debug 로그 금지

### 17.2 네트워크 타임아웃

외부 API 호출은 반드시 timeout을 둔다.

권장:

```text
connect timeout: 3초
read timeout: 10초
```

### 17.3 응답 검증

외부 API 응답은 신뢰하지 않는다.

검증 항목:

- 날짜 형식 검증
- 공휴일명 길이 제한
- null/빈 값 방어
- 예상 구조와 다른 응답 방어
- XML/JSON 파싱 실패 방어

---

## 18. 성능 설계

### 18.1 View 조회 최적화

공휴일 조회는 날짜 range 조건만 사용한다.

```python
KrHoliday.objects.filter(
    date__gte=calendar_range_start,
    date__lte=calendar_range_end,
    is_holiday=True,
)
```

`date`에 index가 있으므로 성능 부담이 낮다.

### 18.2 프론트 데이터 크기

한 달 범위 공휴일은 보통 0~5건 수준이다. 연도 전체를 내려줄 필요가 없다.

### 18.3 Celery 부하

연도별 API 호출은 하루 1회 수준이면 충분하다. DB upsert도 소량이므로 부하가 매우 낮다.

---

## 19. 테스트 설계

### 19.1 Unit Test

대상:

- `normalize_holiday_row()`
- `sync_kr_holidays_for_year()`
- `get_holidays_between()`

검증:

- 정상 날짜 변환
- 잘못된 날짜 skip
- 중복 날짜 update
- source override 보호
- API 장애 시 기존 DB 보존

### 19.2 View Test

대상:

- `worktask_list`

검증:

- context에 `calendar_holidays` 포함
- 현재 캘린더 range에 맞는 공휴일만 포함
- 로그인/권한 정책 기존 유지

### 19.3 JS 수동 검증

- 평일 공휴일이 월간 캘린더에 표시되는지
- 평일 공휴일이 주간 캘린더에 표시되는지
- 토/일 공휴일은 주말 숨김 정책으로 미표시되는지
- 업무 일정과 공휴일이 같은 날짜에 함께 표시되는지

---

## 20. 배포 절차

### 20.1 1차 배포

1. 모델 추가
2. migration 생성
3. admin 등록
4. service 함수 추가
5. management command 추가
6. 운영 환경변수 설정
7. 수동 command로 초기 적재
8. 업무관리 캘린더 확인

### 20.2 2차 배포

1. Celery task 추가
2. beat_schedule 추가
3. worker/beat 재시작
4. task 로그 확인

### 20.3 3차 배포

1. WorkTask view 연동
2. template json_script 추가
3. JS 렌더링 추가
4. CSS 추가
5. 브라우저 검증

---

## 21. 롤백 전략

### 21.1 UI 롤백

- `worktask_list.html`의 `calendar_holidays json_script` 제거
- `worktask_list.js`의 holiday 렌더링 제거
- CSS holiday 스타일 제거

DB 캐시 테이블은 남겨도 기존 기능에 영향이 없다.

### 21.2 수집 롤백

- Celery beat_schedule에서 holiday task 제거
- worker 재시작
- API 환경변수 비활성화

### 21.3 DB 롤백

필요 시 migration rollback 가능하지만, 공휴일 테이블은 독립 테이블이므로 운영상 삭제하지 않아도 된다.

---

## 22. 최소 구현 MVP

MVP는 다음까지만 구현한다.

```text
1. KrHoliday 모델
2. Django Admin 등록
3. sync_kr_holidays management command
4. get_holidays_between service
5. worktask_list context 추가
6. template json_script 추가
7. JS/CSS 렌더링
```

Celery 자동 수집은 MVP 이후 2단계로 붙여도 된다.

---

## 23. 확장 단계

### Phase 1 — DB 캐시 + 수동 수집

- 모델
- admin
- service
- management command
- WorkTask 캘린더 표시

### Phase 2 — Celery 자동 수집

- Celery task
- beat_schedule
- cache lock
- 실패 로그

### Phase 3 — 관리자 override

- Admin action 또는 별도 superuser UI
- override source 보호
- AuditLog 기록

### Phase 4 — 영업일 계산 공통화

- 영업일 여부 계산
- D-day 계산에서 공휴일 제외
- 알림 발송일 계산에서 공휴일 제외
- partner/dash/commission으로 공통 확장

---

## 24. WorkTask 캘린더와의 최종 데이터 계약

### Template

```html
{{ calendar_items|json_script:"worktask-calendar-items" }}
{{ calendar_holidays|json_script:"worktask-calendar-holidays" }}
```

### Holiday JSON

```json
[
  {
    "date": "2026-05-05",
    "name": "어린이날",
    "is_temporary": false
  }
]
```

### JS 내부 map

```javascript
{
  "2026-05-05": {
    "date": "2026-05-05",
    "name": "어린이날",
    "is_temporary": false
  }
}
```

---

## 25. 최종 체크리스트

### 설계 체크

- [ ] View에서 외부 API 직접 호출 없음
- [ ] JS에서 외부 API 직접 호출 없음
- [ ] API Key가 서버 환경변수에만 존재
- [ ] DB 캐시가 SSOT
- [ ] 수동 재수집 command 존재
- [ ] Celery task는 실패해도 사용자 화면 장애를 만들지 않음
- [ ] `source="override"` 데이터 보호 정책 존재

### 보안 체크

- [ ] API Key 로그 노출 없음
- [ ] 외부 응답 검증 있음
- [ ] timeout 있음
- [ ] 예외 로깅 있음
- [ ] 사용자 화면에 내부 오류 노출 없음

### 운영 체크

- [ ] 초기 데이터 적재 절차 문서화
- [ ] beat_schedule 등록 확인
- [ ] worker/beat task name 일치 확인
- [ ] 실패 시 수동 재수집 절차 존재
- [ ] 운영 로그 검색 키워드 정의

### 프론트 체크

- [ ] 공휴일 json_script id 고정
- [ ] WorkTask 일정과 공휴일 렌더 레이어 분리
- [ ] 월~금 캘린더 정책 유지
- [ ] 공휴일명 escape 처리
- [ ] CSS는 `.board-scope` 하위에만 추가

---

## 26. 권장 최종안

`django_ma`의 현재 운영 방향에서는 다음 순서가 가장 안전하다.

1. `KrHoliday` 모델을 board 앱에 추가한다.
2. management command로 먼저 수동 적재 구조를 만든다.
3. 업무관리 캘린더에 DB 캐시 공휴일을 표시한다.
4. 화면 동작이 안정화되면 Celery Beat 자동 수집을 추가한다.
5. 임시공휴일 대응 강화를 위해 admin override 정책을 추가한다.
6. 추후 D-day/알림 계산에서도 공휴일을 제외하는 영업일 계산으로 확장한다.

