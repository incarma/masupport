# django_ma Board 앱 업무관리(WorkTask) 최종 운영·개발 지침서

> 기준일: 2026-05-03  
> 대상: `django_ma/board` 앱의 **업무관리(WorkTask)** 기능  
> 목적: 새 채팅에서 전체 소스코드를 다시 공유하지 않아도 WorkTask 관련 버그 분석, UI 보완, 캘린더 기능 확장, 보안 점검, 성능 개선, 운영 배포 검증을 일관되게 수행하기 위한 최종 기준 문서입니다.  
> 반영 범위: 기존 `board_worktask_guide.md` + 2026-05-03 업무관리 캘린더/필터 UI 보완 논의 + 대한민국 공휴일 `Celery + DB 캐시 구조` 설계 방향.

---

## 0. 문서 사용 원칙

이 문서는 WorkTask 기능의 **운영·개발 SSOT 보조 문서**입니다. 실제 코드를 대체하지 않으며, 패치 작성 전 반드시 현재 코드와 대조해야 합니다.

향후 WorkTask 관련 요청을 받으면 다음 순서로 판단합니다.

1. 요청 유형 분류
   - 원인 분석
   - 버그 수정 패치
   - UI 보완
   - 기능 확장 설계
   - 리팩토링
   - 운영/보안 점검
2. 변경 범위 확정
3. 기존 URL, dataset, DOM id, service layer, 권한 정책 유지 여부 확인
4. diff 패치 제시
5. 로컬/운영 검증 체크리스트 제시

특히 WorkTask는 `board:worktasks` 중첩 namespace, `worktaskListBoot` dataset, `board/services/worktasks.py` 소유자 격리, `.board-scope` CSS 스코프가 핵심 계약입니다.

---

## 1. WorkTask 기능 개요

WorkTask는 기존 Board 앱의 `Post(업무요청)` 및 `Task(직원업무)`와 별개로 동작하는 업무관리 기능입니다.

주요 기능은 다음과 같습니다.

- 업무 등록/수정/삭제
- 업무 상세 조회
- 상태 관리: `pending`, `in_progress`, `done`, `skipped`
- 우선순위 관리: `high`, `mid`, `low`
- 시작일/마감일 관리
- D-day 표시
- 업무 분류 관리: `WorkCategory`
- 관련 인물 연결: `related_users`
- 관련 지점/영업가족 목록: `family_branches`
- 댓글 관리: `WorkTaskComment`
- 첨부파일 관리: `WorkTaskAttachment`
- 월별/상태별/분류별/지점별/키워드 검색
- 목록 인라인 편집
- 반복 업무 자동 생성
- 마감 알림
- 상단 업무 캘린더
- 향후 대한민국 공휴일 표시: `Holiday` DB 캐시 기반 확장 예정

현재 WorkTask는 **superuser 전용 + owner 소유자 격리** 구조입니다.

---

## 2. 핵심 파일 구조

```text
django_ma/
├─ board/
│  ├─ constants.py
│  ├─ policies.py
│  ├─ signals.py
│  ├─ urls.py
│  ├─ worktask_urls.py
│  ├─ models.py
│  ├─ forms.py
│  ├─ tasks.py 또는 board/tasks/worktasks.py 계열
│  │
│  ├─ views/
│  │  ├─ __init__.py
│  │  └─ worktasks.py
│  │
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ comments.py
│  │  └─ worktasks.py
│  │
│  └─ templates/
│     └─ board/
│        ├─ base_board.html
│        ├─ worktask_list.html
│        ├─ worktask_create.html
│        ├─ worktask_detail.html
│        └─ worktask_edit.html
│
└─ static/
   ├─ css/
   │  └─ apps/
   │     └─ board.css
   │
   └─ js/
      └─ board/
         ├─ worktask_list.js
         ├─ worktask_detail.js
         └─ worktask_form.js
```

주의할 점:

- `worktask_list.html`은 `board/base_board.html`을 상속해야 합니다.
- `board/base_board.html`은 `.board-scope`를 주입하고 `static/css/apps/board.css`를 로드합니다.
- WorkTask 전용 CSS는 반드시 `.board-scope` 하위 selector만 사용해야 합니다.
- WorkTask JS는 `type="module"`로 로드하며 공통 CSRF 유틸을 import합니다.

---

## 3. URL namespace 계약

WorkTask URL은 `board:worktasks:*` 중첩 namespace를 사용합니다.

대표 URL:

```text
/board/worktasks/
/board/worktasks/create/
/board/worktasks/<pk>/
/board/worktasks/<pk>/edit/
/board/worktasks/<pk>/inline-update/
/board/worktasks/<pk>/delete/
/board/worktasks/attachments/<att_id>/download/
/board/worktasks/api/notify-check/
```

템플릿에서는 반드시 다음 형식으로 reverse합니다.

```django
{% url 'board:worktasks:worktask_list' %}
{% url 'board:worktasks:worktask_create' %}
{% url 'board:worktasks:worktask_detail' task.pk %}
{% url 'board:worktasks:worktask_edit' task.pk %}
{% url 'board:worktasks:worktask_att_download' att.id %}
```

금지:

```html
<a href="/board/worktasks/1/">...</a>
```

다만 현재 `worktask_list.js`의 캘린더 링크에는 다음처럼 raw path fallback이 남아 있을 수 있습니다.

```js
href="/board/worktasks/${encodeURIComponent(item.id)}/"
```

향후 보완 시 `calendar_items` payload에 `detail_url`을 서버에서 넣고 JS는 해당 값을 사용하도록 개선하는 것이 안전합니다.

---

## 4. 권한 정책

### 4.1 현재 기준

WorkTask 전체는 `superuser` 전용입니다.

```python
@grade_required("superuser")
def worktask_list(request): ...
```

상세/수정/삭제/인라인 업데이트/첨부 다운로드 모두 동일하게 `superuser` 전용입니다.

### 4.2 owner 소유자 격리

WorkTask는 superuser라도 모든 WorkTask를 보는 구조가 아니라, 일반 화면에서는 `owner=request.user` 기준으로 격리합니다.

핵심 SSOT:

```python
# board/services/worktasks.py
get_user_queryset(user)
get_user_task(user, pk)
```

규칙:

- 목록: 반드시 `get_user_queryset(request.user)` 시작
- 상세/수정/삭제: 반드시 `get_user_task(request.user, pk)` 시작
- 타인 업무 pk 직접 접근 시 404가 정상
- 첨부 다운로드는 `att.task.owner_id == request.user.pk` 추가 검증

금지:

```python
WorkTask.objects.get(pk=pk)
get_object_or_404(WorkTask, pk=pk)
```

예외:

- Django Admin은 관리자 전용 전체 조회 예외입니다.

---

## 5. 모델 기준

### 5.1 WorkCategory

업무 분류 마스터입니다.

주요 필드:

- `code`: PK
- `label`: 표시명
- `sort_order`: 정렬
- `is_active`: 생성/수정 UI 노출 여부

목록 필터와 인라인 편집 옵션은 활성 분류만 사용합니다.

```python
WorkCategory.objects.filter(is_active=True).order_by("sort_order")
```

### 5.2 WorkTask

핵심 필드:

| 필드 | 설명 |
|---|---|
| `owner` | 업무 소유자, 화면 조회 격리 기준 |
| `category` | 업무 분류 |
| `title` | 업무명 |
| `description` | 상세 내용 |
| `related_users` | 관련 인물 M2M, 권한 부여 용도 아님 |
| `family_branches` | 관련 지점명 목록 JSON list[str] |
| `start_date` | 시작일 |
| `due_date` | 마감일 |
| `calendar_span_mode` | 시작일~마감일 기간 막대 표시 여부 |
| `recurrence_type` | 반복 유형 |
| `recurrence_day` | 직접 반복 일자 |
| `template_task` | 반복 자동생성 자식의 원본 |
| `target_ym` | 자동생성 자식 귀속월 `YYYY-MM` |
| `status` | `pending`, `in_progress`, `done`, `skipped` |
| `priority` | `high`, `mid`, `low` |
| `notify_days_before` | 마감 알림 기준일 |
| `is_notified` | 알림 발송 여부 |
| `created_at`, `updated_at` | 생성/수정 시각 |

### 5.3 `calendar_span_mode`

상단 캘린더 확장 과정에서 추가된 필드입니다.

```python
calendar_span_mode = models.BooleanField(
    default=False,
    verbose_name="캘린더 기간 막대 표시",
    help_text="체크 시 시작일부터 마감일까지 캘린더에 기간 막대로 표시합니다.",
)
```

의미:

- `False`: 시작일 도래 후 완료/보류 전까지 오늘 일정에 rolling 표시
- `True`: 시작일~마감일 전체 기간에 막대형 일정으로 표시

적용 조건:

- `start_date`와 `due_date`가 모두 있을 때만 의미가 있습니다.
- 시작일 또는 마감일이 하나만 있는 경우에는 rolling 표시 규칙을 따릅니다.

마이그레이션 필요:

```bash
python manage.py makemigrations board
python manage.py migrate
```

### 5.4 WorkTaskAttachment

첨부파일 모델입니다.

주요 규칙:

- `file.url` 직접 노출 금지
- 다운로드는 `worktask_att_download` view 경유
- 원본 파일명은 `original_name`에 저장
- 다운로드 응답은 RFC5987 한글 파일명 처리

### 5.5 WorkTaskComment

댓글 모델입니다.

- 댓글 처리는 `board/services/comments.py`의 `handle_comments_actions()`를 재사용합니다.
- 상세 페이지의 댓글 수정/삭제 DOM 계약은 기존 Board 댓글 공통 partial 기준을 유지합니다.

---

## 6. Service Layer 기준

파일:

```text
board/services/worktasks.py
```

### 6.1 소유자 격리 SSOT

```python
def get_user_queryset(user):
    return (
        WorkTask.objects
        .filter(owner=user)
        .select_related("category", "owner")
        .prefetch_related("related_users", "attachments")
        .annotate(comment_count=Count("comments", distinct=True))
    )
```

규칙:

- 모든 목록/캘린더/필터는 이 함수에서 시작합니다.
- calendar payload도 이 함수를 사용해야 합니다.
- `prefetch_related("related_users", "attachments")`를 유지해 목록 N+1 위험을 줄입니다.

### 6.2 상세 조회 SSOT

```python
def get_user_task(user, pk):
    return get_object_or_404(WorkTask, pk=pk, owner=user)
```

### 6.3 필터 적용

```python
def apply_filters(qs, params): ...
```

GET parameter:

| 키 | 의미 |
|---|---|
| `ym` | 귀속월 `YYYY-MM` |
| `status` | 상태 |
| `category` | 분류 code |
| `branch` | 지점명 |
| `keyword` | 업무명/내용 검색어 |

월 필터 기준:

```text
1. 자동생성 자식: target_ym = ym
2. 일반 업무: due_date가 해당 월 범위
3. due_date 없는 원본 템플릿: 포함
```

주의:

- `branch` 필터는 `family_branches__contains=[branch]` 기반입니다.
- SQLite 개발환경과 PostgreSQL 운영환경의 JSON contains 동작 차이를 점검해야 합니다.

### 6.4 생성/수정

생성:

```python
def create_task(user, data):
    related_users = data.pop("related_users", [])
    with transaction.atomic():
        data["family_branches"] = _clean_family_branches(...)
        task = WorkTask(**data, owner=user)
        task.full_clean()
        task.save()
        if related_users:
            task.related_users.set(related_users)
```

수정:

```python
def update_task(task, data):
    data.pop("owner", None)
    data.pop("owner_id", None)
    ...
```

규칙:

- owner 변경 금지
- family_branches는 `_clean_family_branches()`로 정규화
- related_users는 저장 후 `.set()`
- transaction.atomic 유지

### 6.5 캘린더 payload 생성

함수:

```python
def build_calendar_payload(user, *, range_start: date, range_end: date, today: date | None = None) -> list[dict]: ...
```

이 함수는 상단 캘린더 표시용 데이터를 만듭니다.

기본 원칙:

- 반드시 `get_user_queryset(user)` 경유
- `done`, `skipped`는 제외
- `priority` 기준 정렬
- 조회 범위 밖 일정은 제외
- 날짜 계산은 서버에서 수행하고 JS는 렌더링만 담당

종료 상태:

```python
WORKTASK_CALENDAR_TERMINAL_STATUSES = [
    WorkTask.STATUS_DONE,
    WorkTask.STATUS_SKIPPED,
]
```

우선순위 정렬:

```python
WORKTASK_PRIORITY_SORT = {
    WorkTask.PRIORITY_HIGH: 0,
    WorkTask.PRIORITY_MID: 1,
    WorkTask.PRIORITY_LOW: 2,
}
```

---

## 7. 캘린더 기능 최종 기준

### 7.1 화면 위치

업무관리 목록 페이지 상단에 캘린더 카드를 배치합니다.

위치 순서:

```text
페이지 제목
→ 업무 캘린더 카드
→ 필터 카드
→ 업무 목록 테이블
```

템플릿 root:

```html
<div id="worktaskListBoot" class="worktask-list-wide" ...>
```

캘린더 DOM:

```html
<div class="card shadow p-3 border-0 rounded-4 mb-3 worktask-calendar-card">
  <div class="worktask-calendar-toolbar">
    <div>
      <p class="fw-bold mb-0" id="worktask-calendar-title">업무 캘린더</p>
      <p class="small text-muted mb-0" id="worktask-calendar-subtitle">...</p>
    </div>
    <div class="worktask-calendar-controls">
      <button id="worktask-calendar-prev">◀</button>
      <button id="worktask-calendar-today" class="d-none">오늘</button>
      <button id="worktask-calendar-next">▶</button>
      <button id="worktask-calendar-toggle">🗓 월간</button>
    </div>
  </div>
  <div id="worktask-calendar" class="worktask-calendar" data-view="week"></div>
</div>
```

### 7.2 Boot dataset 계약

`worktaskListBoot`에 다음 data 속성이 필요합니다.

```html
<div id="worktaskListBoot"
     data-delete-url="..."
     data-inline-url="..."
     data-calendar-today="{{ calendar_today }}"
     data-calendar-anchor="{{ calendar_anchor }}"
     data-calendar-view="{{ calendar_view }}"
     data-calendar-week-start="{{ calendar_week_start }}"
     data-calendar-week-end="{{ calendar_week_end }}"
     data-calendar-month-start="{{ calendar_month_start }}"
     data-calendar-month-end="{{ calendar_month_end }}">
```

각 값의 의미:

| dataset | 의미 |
|---|---|
| `calendarToday` | 실제 오늘 날짜 |
| `calendarAnchor` | 현재 보고 있는 캘린더 기준일 |
| `calendarView` | `week` 또는 `month` |
| `calendarWeekStart` | 현재 주간 보기 시작일 |
| `calendarWeekEnd` | 현재 주간 보기 종료일 |
| `calendarMonthStart` | 현재 월간 보기 시작일 |
| `calendarMonthEnd` | 현재 월간 보기 종료일 |

### 7.3 GET 파라미터 계약

캘린더 이동은 GET 파라미터로 상태를 유지합니다.

| 파라미터 | 값 | 설명 |
|---|---|---|
| `cal_view` | `week` / `month` | 현재 캘린더 보기 |
| `cal_anchor` | `YYYY-MM-DD` | 현재 캘린더 기준일 |

예:

```text
/board/worktasks/?ym=2026-05&cal_view=week&cal_anchor=2026-05-03
/board/worktasks/?ym=2026-05&cal_view=month&cal_anchor=2026-05-03
```

주의:

- 업무 목록 월도 필터 `ym`과 캘린더 표시 기준 `cal_anchor`는 별도입니다.
- 목록은 `ym` 기준으로 필터링됩니다.
- 캘린더는 `cal_view + cal_anchor` 기준으로 렌더링됩니다.

### 7.4 서버 날짜 계산

`board/views/worktasks.py`에 다음 유틸이 필요합니다.

```python
def _month_range_from_ym(ym: str) -> tuple[date, date]: ...

def _week_range_containing(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)
```

`worktask_list()` 흐름:

```python
cal_view = request.GET.get("cal_view", "week")
cal_anchor_raw = request.GET.get("cal_anchor", "")

today = timezone.localdate()
calendar_anchor = parsed cal_anchor or today
if cal_view not in ("week", "month"):
    cal_view = "week"

week_start, week_end = _week_range_containing(calendar_anchor)
view_month_start, view_month_end = _month_range_from_ym(
    f"{calendar_anchor.year}-{calendar_anchor.month:02d}"
)

calendar_range_start = min(view_month_start, week_start)
calendar_range_end = max(view_month_end, week_end)

calendar_items = wt_svc.build_calendar_payload(
    request.user,
    range_start=calendar_range_start,
    range_end=calendar_range_end,
    today=today,
)
```

### 7.5 캘린더 표시 규칙

상태가 `done` 또는 `skipped`인 업무는 캘린더에서 제외합니다.

업무 날짜별 표시 규칙:

| 시작일 | 마감일 | 옵션 | 표시 기준 |
|---|---|---|---|
| 없음 | 없음 | 무관 | 완료/보류 전까지 매일 오늘 칸에 표시 |
| 있음 | 없음 | 무관 | 시작일 도래 후 완료/보류 전까지 매일 오늘 칸에 표시 |
| 없음 | 있음 | 무관 | 마감일 이후 완료/보류 전까지 매일 오늘 칸에 표시 |
| 있음 | 있음 | `calendar_span_mode=False` | 시작일 도래 후 완료/보류 전까지 매일 오늘 칸에 표시 |
| 있음 | 있음 | `calendar_span_mode=True` | 시작일~마감일까지 기간 막대 표시 |

주의:

- `done`, `skipped` 전환 후에는 다음 렌더링부터 캘린더에서 빠져야 합니다.
- 상태 인라인 변경 후 즉시 캘린더 DOM에서 제거까지 하려면 추가 JS 갱신 로직이 필요합니다. 현재 기준은 새로고침 후 반영입니다.

### 7.6 주간/월간 전환

JS 기준:

```js
let view = boot.dataset.calendarView || root.dataset.view || "week";
root.dataset.view = view;
_renderCalendar(root, items, view);
_syncCalendarHeader(view);
```

중요 버그 이력:

- `_initCalendar()`에서 `_renderCalendar()`를 호출하지 않으면 캘린더 본문이 비어 보입니다.
- 초기화 시 반드시 `_renderCalendar(root, items, view)`를 호출해야 합니다.

### 7.7 이전/다음/오늘 이동

버튼:

```html
#worktask-calendar-prev
#worktask-calendar-next
#worktask-calendar-today
```

JS 기준:

```js
prevBtn?.addEventListener("click", () => _shiftCalendar(view, -1));
nextBtn?.addEventListener("click", () => _shiftCalendar(view, 1));
todayBtn?.addEventListener("click", () => _moveCalendar({
  view,
  anchor: boot.dataset.calendarToday,
}));
```

주간:

```js
anchor.setDate(anchor.getDate() + amount * 7);
```

월간:

```js
anchor.setMonth(anchor.getMonth() + amount);
```

오늘 버튼 표시 기준:

```js
todayBtn?.classList.toggle("d-none", anchorKey === todayKey);
```

주의:

- 기준일이 오늘과 다르면 `오늘` 버튼을 표시합니다.
- 버튼 클릭은 URL GET 파라미터를 갱신하여 서버 렌더링으로 이동합니다.

### 7.8 헤더 표시

주간 보기:

```text
2026년 5월 1주차
주간 캘린더
```

월간 보기:

```text
2026년 5월
월간 캘린더
```

JS:

```js
function _syncCalendarHeader(view) {
  const anchor = _dateFromKey(boot.dataset.calendarAnchor || boot.dataset.calendarToday);
  if (view === "month") {
    title.textContent = `${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월`;
    subtitle.textContent = "월간 캘린더";
    toggle.textContent = "↩ 주간";
  } else {
    const weekNo = _weekOfMonth(anchor);
    title.textContent = `${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월 ${weekNo}주차`;
    subtitle.textContent = "주간 캘린더";
    toggle.textContent = "🗓 월간";
  }
}
```

주의:

- 월간 보기에서 요일 헤더를 `dayKeys` 전체 기준으로 생성하면 요일명이 날짜 수만큼 반복되는 버그가 발생합니다.
- 요일 헤더는 항상 월~금 5개만 고정 출력해야 합니다.

### 7.9 토요일/일요일 제외 최종 기준

요청 사항:

- 주간 캘린더: 월요일~금요일만 표시
- 월간 캘린더: 월요일~금요일만 표시
- 토/일 날짜 칸 제거
- 토/일 요일 헤더 제거

JS 기준:

```js
const dayKeys = [];
for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
  const day = d.getDay(); // 0=일, 6=토
  if (day !== 0 && day !== 6) {
    dayKeys.push(_dateKey(d));
  }
}

const dayNames = ["월", "화", "수", "목", "금"];
html.push(`<div class="worktask-calendar-head">`);
dayNames.forEach((name) => {
  html.push(`<div class="worktask-calendar-weekday">${name}</div>`);
});
html.push(`</div>`);
```

금지 패턴:

```js
// 월간에서 요일명이 날짜 수만큼 반복되는 원인
const weekdayMap = ["일","월","화","수","목","금","토"];
dayKeys.forEach((key) => {
  const d = _dateFromKey(key);
  const name = weekdayMap[d.getDay()];
  html.push(`<div class="worktask-calendar-weekday">${name}</div>`);
});
```

CSS 기준:

```css
.board-scope .worktask-calendar-head{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.board-scope .worktask-calendar-grid{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
```

### 7.10 캘린더 JSON 데이터 주입

템플릿 하단:

```django
{{ calendar_items|json_script:"worktask-calendar-items" }}
```

JS:

```js
function _readCalendarItems() {
  const el = document.getElementById("worktask-calendar-items");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent || "[]");
  } catch (e) {
    console.warn("[worktask_list] calendar json parse failed", e);
    return [];
  }
}
```

주의:

- CSP 대응을 위해 inline script 직접 대입 대신 `json_script` 사용.
- 데이터를 `window.calendarItems = ...`로 직접 주입하지 않습니다.

---

## 8. 필터 카드 UI 최종 기준

### 8.1 배치 요구사항

요청 반영 후 필터 카드는 한 줄 구조입니다.

좌측:

```text
상태 / 분류 / 지점 / 검색 / 조회 / 초기화
```

우측 끝:

```text
이전월 버튼 / 월도 선택 / 다음월 버튼 / + 업무 등록
```

### 8.2 템플릿 구조

```html
<form method="get" class="worktask-filter-form">
  <div class="worktask-filter-inline">

    <div class="worktask-filter-item">상태 select</div>
    <div class="worktask-filter-item">분류 select</div>
    <div class="worktask-filter-item">지점 select</div>
    <div class="worktask-filter-item worktask-keyword-item">검색 input</div>

    <div class="worktask-filter-actions">
      <button type="submit" class="btn btn-primary btn-sm">조회</button>
      <a href="?ym={{ ym }}" class="btn btn-outline-secondary btn-sm">초기화</a>
    </div>

    <div class="worktask-filter-right">
      <a class="btn btn-sm btn-outline-secondary">◀</a>
      <input type="month" name="ym" class="form-control form-control-sm worktask-month-input" value="{{ ym }}">
      <a class="btn btn-sm btn-outline-secondary">▶</a>
      <a href="{% url 'board:worktasks:worktask_create' %}" class="btn btn-primary btn-sm worktask-create-icon-btn">+ 업무 등록</a>
    </div>

  </div>
</form>
```

### 8.3 CSS 기준

```css
.board-scope .worktask-filter-inline{
  display: flex;
  align-items: end;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 2px;
}

.board-scope .worktask-filter-right{
  margin-left: auto;
  flex: 0 0 auto;
  display: flex;
  align-items: end;
  gap: 8px;
}

.board-scope .worktask-filter-item{
  flex: 0 0 auto;
}

.board-scope .worktask-keyword-item{
  min-width: 220px;
}

.board-scope .worktask-month-input{
  width: 150px;
}
```

주의:

- 월도 선택과 업무 등록 버튼은 `.worktask-filter-right` 안에 두어야 우측 끝 배치가 가능합니다.
- 이 그룹을 필터 항목보다 앞에 두면 우측 끝 정렬이 깨집니다.
- 모바일에서는 `overflow-x:auto`로 한 줄 스크롤을 허용합니다.

---

## 9. WorkTask 목록 JS 기준

파일:

```text
static/js/board/worktask_list.js
```

### 9.1 모듈/부트 가드

```js
import { getCSRFToken } from "../common/manage/csrf.js";

const boot = document.getElementById("worktaskListBoot");
if (!boot) {
  console.debug("[worktask_list] boot element not found — skip");
  throw "[worktask_list] no-op exit";
}

if (boot.dataset.inited === "1") {
  console.debug("[worktask_list] already inited — skip");
} else {
  boot.dataset.inited = "1";
  _init();
}
```

규칙:

- CSRF 중복 구현 금지
- `getCSRFToken()` 공통 유틸 사용
- BFCache/중복 바인딩 방지 필수

### 9.2 초기화 순서

```js
function _init() {
  _initCalendar();
  _bindDeleteButtons();
  _bindInlineEdit();
  _renderDdays();
}
```

캘린더가 상단에 있으므로 `_initCalendar()`를 먼저 호출합니다.

### 9.3 인라인 편집

편집 가능 필드:

- `category`
- `priority`
- `start_date`
- `due_date`
- `status`

DOM 계약:

```html
<td class="worktask-cell-edit"
    data-field="priority"
    data-value="{{ task.priority }}"
    data-pk="{{ task.pk }}">
  <span class="worktask-cell-display">...</span>
</td>
```

AJAX:

```js
const url = _buildActionUrl(boot.dataset.inlineUrl, pk);
const result = await _postJsonBody(url, { field, value: newVal });
```

주의:

- `change`와 `blur`가 모두 발생하므로 `editor.dataset.saving` 중복 방지 필수
- 상태가 `done` 또는 `skipped`로 변경되면 row에 `.worktask-done` 적용
- 상태 변경 후 캘린더 즉시 갱신은 현재 필수 아님. 필요 시 확장 설계 필요

### 9.4 삭제 처리

삭제 버튼 DOM:

```html
<button class="worktask-delete-btn" data-pk="{{ task.pk }}" data-title="{{ task.title|escapejs }}">🗑</button>
```

삭제 성공 시 row 제거:

```js
const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
if (row) row.remove();
```

주의:

- 서버에서는 반드시 `wt_svc.get_user_task()`으로 owner 검증
- 삭제 성공 후 캘린더도 즉시 제거하려면 별도 DOM 업데이트 필요

---

## 10. 등록/수정 폼 기준

파일:

```text
board/templates/board/worktask_create.html
board/templates/board/worktask_edit.html
static/js/board/worktask_form.js
```

### 10.1 `calendar_span_mode` 체크박스

시작일/마감일 입력 영역 근처에 배치합니다.

등록:

```django
<input class="form-check-input"
       type="checkbox"
       name="calendar_span_mode"
       id="id_calendar_span_mode"
       value="1"
       {% if post_data.calendar_span_mode %}checked{% endif %}>
```

수정:

```django
<input class="form-check-input"
       type="checkbox"
       name="calendar_span_mode"
       id="id_calendar_span_mode"
       value="1"
       {% if task.calendar_span_mode %}checked{% endif %}>
```

서버 추출:

```python
"calendar_span_mode": post.get("calendar_span_mode") == "1",
```

### 10.2 날짜 필드

- `start_date`
- `due_date`

날짜는 `_extract_post_data()`에서 안전 파싱합니다.

```python
def _parse_date(key: str):
    raw = post.get(key, "").strip()
    if not raw:
        return None
    try:
        y, m, d = map(int, raw.split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None
```

주의:

- 잘못된 날짜는 `None`으로 처리됩니다.
- 더 엄격한 사용자 오류 메시지가 필요하면 Form 도입이 필요합니다.

---

## 11. 대한민국 공휴일 표시 설계 기준

### 11.1 결론

공휴일 목록을 코드에 하드코딩하는 방식은 임시공휴일, 선거일, 대체공휴일 변경에 자동 대응할 수 없습니다.

운영 기준 권장 구조는 다음입니다.

```text
공공데이터포털 특일정보 API
→ Celery 또는 management command 수집
→ DB Holiday 캐시 저장
→ WorkTask view에서 조회
→ json_script로 template 전달
→ JS에서 날짜 칸에 표시
```

### 11.2 금지 방식

```text
❌ JS에서 외부 API 직접 호출
❌ view 요청마다 외부 API 실시간 호출
❌ 공휴일 하드코딩만으로 운영
❌ 템플릿에 연도별 휴일을 inline script로 직접 삽입
```

### 11.3 권장 모델

별도 앱 또는 공통 앱에 둘 수 있습니다.

권장 앱명:

```text
calendar_core
```

권장 모델:

```python
class KoreanHoliday(models.Model):
    date = models.DateField(unique=True, db_index=True)
    name = models.CharField(max_length=80)
    is_holiday = models.BooleanField(default=True)
    is_temporary = models.BooleanField(default=False)
    source = models.CharField(max_length=30, default="data_go_kr")
    raw_payload = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 11.4 수집 방식

권장 수집 진입점:

```text
calendar_core/services/kr_holidays.py
calendar_core/tasks.py
calendar_core/management/commands/sync_kr_holidays.py
```

역할:

- API 호출
- 응답 파싱
- 날짜/공휴일명 정규화
- DB upsert
- 실패 시 기존 캐시 유지
- 실패 로그 기록
- 선택적으로 audit log 기록

### 11.5 Celery Beat 주기

권장:

```text
매일 새벽 03:20: 올해, 다음해 동기화
매월 1일 03:40: 전년도~다음해 재동기화
배포 직후 또는 수동 필요 시: management command 실행
```

이유:

- 임시공휴일은 연중 갑자기 발표될 수 있습니다.
- 매일 동기화하면 운영자가 직접 수정하지 않아도 일정 기간 내 반영됩니다.
- API 장애 시 기존 DB 캐시를 사용하므로 화면 장애를 방지합니다.

### 11.6 WorkTask 연동

`worktask_list()`에서 캘린더 범위 기준으로 조회합니다.

```python
holidays = KoreanHoliday.objects.filter(
    date__range=(calendar_range_start, calendar_range_end),
    is_holiday=True,
).order_by("date")
```

템플릿:

```django
{{ calendar_holidays|json_script:"worktask-calendar-holidays" }}
```

JS:

```js
function _readCalendarHolidays() {
  const el = document.getElementById("worktask-calendar-holidays");
  if (!el) return {};
  try {
    const rows = JSON.parse(el.textContent || "[]");
    return Object.fromEntries(rows.map((h) => [h.date, h]));
  } catch {
    return {};
  }
}
```

렌더링:

```js
if (holidayMap[key]) {
  html.push(`<div class="worktask-calendar-holiday">${_escHtml(holidayMap[key].name)}</div>`);
}
```

CSS:

```css
.board-scope .worktask-calendar-holiday{
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  color: #dc3545;
  background: #fff5f5;
  border: 1px solid #f1aeb5;
}
```

### 11.7 월~금 캘린더와 공휴일의 관계

현재 WorkTask 캘린더는 월~금만 표시합니다.

따라서:

- 토/일 공휴일은 화면에 표시되지 않습니다.
- 평일 공휴일만 표시됩니다.
- 대체공휴일이 월요일이면 월요일 칸에 표시됩니다.

### 11.8 환경변수

권장 `.env`:

```env
KOREAN_HOLIDAY_API_ENABLED=True
KOREAN_HOLIDAY_API_BASE_URL=https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo
KOREAN_HOLIDAY_API_KEY=...
KOREAN_HOLIDAY_API_TIMEOUT=10
```

주의:

- API key는 코드에 저장하지 않습니다.
- 운영과 개발의 API key는 분리합니다.
- API 장애 시 화면 요청이 실패하면 안 됩니다.

---

## 12. CSS 기준

파일:

```text
static/css/apps/board.css
```

### 12.1 No-Leak 원칙

모든 WorkTask CSS는 `.board-scope` 하위여야 합니다.

허용:

```css
.board-scope .worktask-calendar-card { ... }
```

금지:

```css
.worktask-calendar-card { ... }
```

### 12.2 WorkTask 목록 폭

```css
.board-scope .worktask-list-wide{
  width: 86vw;
  max-width: none;
  margin-left: calc(-43vw + 50%);
}
```

모바일:

```css
@media (max-width: 576px){
  .board-scope .worktask-list-wide{
    width: 100%;
    margin-left: 0;
  }
}
```

### 12.3 캘린더 핵심 CSS

```css
.board-scope .worktask-calendar-head,
.board-scope .worktask-calendar-grid{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}

.board-scope .worktask-calendar-day{
  min-height: 118px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 8px;
  background: #fff;
  min-width: 0;
}

.board-scope .worktask-calendar-day.is-today{
  border-color: #005BAC;
  box-shadow: 0 0 0 2px rgba(0, 91, 172, .12);
}
```

주의:

- 월~금만 표시하므로 `repeat(5, ...)`가 기준입니다.
- `repeat(7, ...)`로 되돌리면 주말 제거 UI가 깨집니다.

---

## 13. 첨부파일 보안 기준

### 13.1 다운로드 URL

템플릿에서 직접 `att.file.url`을 쓰면 안 됩니다.

금지:

```django
<a href="{{ att.file.url }}">다운로드</a>
```

허용:

```django
<a href="{% url 'board:worktasks:worktask_att_download' att.id %}">다운로드</a>
```

### 13.2 다운로드 view

기준:

```python
@grade_required("superuser")
def worktask_att_download(request, att_id: int):
    att = get_object_or_404(WorkTaskAttachment, pk=att_id)
    if att.task.owner_id != request.user.pk:
        return HttpResponseForbidden("접근 권한이 없습니다.")
    ...
    return FileResponse(...)
```

주의:

- 소유자 불일치 시 403 또는 404 중 정책을 명확히 유지합니다.
- 파일 열기 실패는 서버 로그에 기록합니다.
- 운영 감사로그 확장 대상입니다.

---

## 14. Celery 작업 기준

### 14.1 반복 업무 자동 생성

역할:

- 반복 원본 WorkTask를 기반으로 월별 자식 업무 생성
- 중복 생성 방지
- target_ym 지정

검증 포인트:

```bash
celery -A web_ma inspect registered
```

확인:

- task name이 beat schedule과 일치하는지
- worker가 정상 실행 중인지
- Redis 연결 오류가 없는지
- 같은 월 업무가 중복 생성되지 않는지

### 14.2 마감 알림

역할:

- `due_date`가 있고 아직 완료/보류가 아닌 업무 중 알림 대상 조회
- owner별로 알림 발송
- 발송 후 `is_notified=True`

주의:

- owner별 그룹핑으로 타인 업무가 이메일에 섞이면 안 됩니다.
- 발송 실패 시 retry 정책 필요
- 상태가 `done` 또는 `skipped`인 업무는 알림 대상에서 제외

### 14.3 공휴일 수집 Celery 확장

향후 추가될 공휴일 수집 task는 WorkTask와 직접 결합하지 않는 것이 좋습니다.

권장:

```text
calendar_core.tasks.sync_korean_holidays
```

WorkTask는 DB 캐시 조회만 수행합니다.

---

## 15. 운영/배포 기준

### 15.1 정적파일

운영은 Whitenoise Manifest 기반 정적파일을 전제로 합니다.

패치 후:

```bash
python manage.py collectstatic --noinput
```

주의:

- JS/CSS 수정 후 브라우저 캐시 때문에 이전 파일이 보일 수 있습니다.
- 개발 검증 시 `Ctrl + F5` 강력 새로고침합니다.
- 운영에서 임의 query string 캐시 무력화는 원칙적으로 지양하고 Manifest 해시를 신뢰합니다.

### 15.2 마이그레이션

`calendar_span_mode` 추가 시 필수:

```bash
python manage.py makemigrations board
python manage.py migrate
```

공휴일 모델 추가 시:

```bash
python manage.py makemigrations calendar_core
python manage.py migrate
```

### 15.3 로그

필수 로그 대상:

- WorkTask 생성 실패
- WorkTask 수정 실패
- 첨부 다운로드 소유자 불일치
- 첨부 파일 열기 실패
- Celery 반복 생성 실패
- Celery 알림 발송 실패
- 공휴일 API 수집 실패

감사로그 확장 후보:

- WorkTask 첨부 다운로드
- WorkTask 대량 반복 생성
- WorkTask 삭제
- 공휴일 수동 동기화

---

## 16. 회귀 위험 체크리스트

패치 전/후 반드시 확인합니다.

| 항목 | 점검 |
|---|---|
| 권한 | `@grade_required("superuser")` 유지 여부 |
| 소유자 격리 | `get_user_queryset`, `get_user_task` 우회 여부 |
| URL | `board:worktasks:*` namespace 유지 여부 |
| 첨부 | `.file.url` 직접 노출 여부 |
| 템플릿 | `worktaskListBoot` id 유지 여부 |
| dataset | 캘린더 data-* 키 유지 여부 |
| JS | `boot.dataset.inited` 중복 가드 유지 여부 |
| JS | `_renderCalendar()` 초기 호출 누락 여부 |
| 캘린더 | 월~금 5칸 grid 유지 여부 |
| 캘린더 | 월간 헤더가 dayKeys 반복으로 생성되지 않는지 |
| 필터 | `.worktask-filter-right` 우측 배치 유지 여부 |
| CSS | `.board-scope` 누수 여부 |
| CSP | inline script/style 추가 여부 |
| 운영 | collectstatic 필요 여부 |
| DB | 마이그레이션 필요 여부 |

---

## 17. 로컬 검증 시나리오

기본 검증:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

마이그레이션이 있는 경우:

```bash
python manage.py makemigrations board
python manage.py migrate
python manage.py check
```

브라우저 검증:

1. `/board/worktasks/` 진입
2. 캘린더가 상단에 표시되는지 확인
3. 기본 보기가 오늘 포함 주간 캘린더인지 확인
4. 주간 캘린더가 월~금만 표시되는지 확인
5. 월간 전환 후 월~금만 표시되는지 확인
6. 월간 헤더가 `월 화 수 목 금` 한 줄만 표시되는지 확인
7. 이전/다음 주 이동 확인
8. 이전/다음 월 이동 확인
9. 다른 주/월 이동 후 `오늘` 버튼 노출 확인
10. 오늘 버튼 클릭 시 오늘 기준 보기로 복귀 확인
11. 필터 카드에서 상태/분류/지점/검색/조회/초기화가 좌측에 있는지 확인
12. 월도 선택/업무 등록 버튼이 우측 끝에 있는지 확인
13. 시작일/마감일 없는 업무가 오늘 칸에 표시되는지 확인
14. `done`, `skipped` 업무가 캘린더에서 제외되는지 확인
15. `calendar_span_mode=True` 업무가 시작~마감 기간에 표시되는지 확인
16. 인라인 상태 변경이 목록 row에 반영되는지 확인
17. 첨부 다운로드가 보호 URL로 동작하는지 확인
18. `Ctrl + F5` 후에도 동일하게 표시되는지 확인

---

## 18. 운영 유사 검증 시나리오

1. Docker/Gunicorn 환경에서 정적파일이 200/304로 로드되는지 확인
2. `worktask_list.js`가 최신 버전인지 네트워크 탭에서 확인
3. `board.css`가 최신 버전인지 확인
4. 캘린더 버튼 클릭 시 URL의 `cal_view`, `cal_anchor`가 정상 변경되는지 확인
5. `page`, `ym`, `status`, `category`, `branch`, `keyword`와 `cal_view`, `cal_anchor` 조합에서 충돌이 없는지 확인
6. Celery worker/beat가 정상 실행 중인지 확인
7. 공휴일 캐시 확장 후에는 API 장애 상황에서도 WorkTask 페이지가 정상 표시되는지 확인

---

## 19. 향후 개선 후보

### 19.1 단기

- 캘린더 item 링크 raw path 제거: 서버에서 `detail_url` 제공
- 캘린더 상태 인라인 변경 후 즉시 DOM 갱신
- 캘린더 날짜 칸 높이/스크롤 UX 개선
- 공휴일 DB 캐시 모델 추가 전 설계 리뷰

### 19.2 중기

- WorkTaskForm 도입으로 `_extract_post_data()` 검증 강화
- WorkTask 정책 함수 분리: `can_view_worktask`, `can_edit_worktask`, `can_download_worktask_attachment`
- WorkTask 첨부 다운로드 audit log 추가
- 반복 생성 bulk 처리 개선
- 알림 발송 이력 모델 분리

### 19.3 장기

- head/leader까지 WorkTask 권한 확장 여부 검토
- 조직 캘린더/개인 캘린더 분리
- 공휴일 + 영업일 계산 기반 마감일 자동 조정
- Google Calendar 연동은 별도 보안/동의 설계 후 검토

---

## 20. 패치 응답 표준 포맷

WorkTask 코드 수정 요청 시 응답은 다음 구조를 따릅니다.

```text
1. 변경 목적
2. 수정 파일 목록 + 영향도
3. diff 패치
4. 로컬 검증 체크리스트
5. 운영 배포 주의사항
```

원인 분석만 요청받은 경우:

```text
1. 현상 요약
2. 원인 후보 Top N
3. 근거
4. 원인 확정 관측 포인트
```

“해결책 금지”가 명시된 경우 diff나 명령어를 제시하지 않습니다.

---

## 21. 최종 요약

WorkTask의 현재 최종 기준은 다음입니다.

- `board:worktasks` 중첩 namespace 유지
- `superuser` 전용 + owner 소유자 격리 유지
- 목록/상세/수정/삭제는 service layer 경유
- 첨부파일은 `.file.url` 직접 노출 금지
- `worktaskListBoot` dataset이 JS 부트 SSOT
- 캘린더는 `cal_view`, `cal_anchor` 기반 서버 렌더링
- 캘린더는 월~금만 표시
- 월간 요일 헤더는 항상 `월 화 수 목 금` 5개 고정
- 필터 카드 우측 끝에 월도 선택/업무 등록 배치
- `calendar_span_mode`로 기간 막대 표시 제어
- 대한민국 공휴일은 하드코딩이 아니라 API + Celery + DB 캐시 구조로 확장
- 모든 CSS는 `.board-scope` 하위에만 작성

