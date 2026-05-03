# django_ma Board 앱 업무관리(WorkTask) 운영·개발 지침서

> 기준: 2026-05-03 현재 공유된 Board / WorkTask 관련 코드 기준  
> 대상: `django_ma/board` 앱 중 **업무관리(WorkTask)** 기능  
> 목적: 새 채팅에서 전체 소스코드를 다시 공유하지 않아도, WorkTask 관련 버그 분석·패치·리팩토링·기능 확장 피드백을 일관되게 진행하기 위한 기준 문서입니다.

---

## 0. 문서 목적

이 문서는 `django_ma` 프로젝트의 Board 앱 중 신규 업무관리 기능인 **WorkTask** 영역의 기준 문서입니다.

향후 다음 작업을 진행할 때 이 문서를 우선 참조합니다.

- 업무관리 목록/상세/등록/수정 화면 UI 수정
- 댓글 개수 표시, 첨부 아이콘, 상태 뱃지 등 레이아웃 조정
- 업무 반복 생성, 마감 알림, Celery 작업 점검
- 지점 선택, 관련 인물 선택, 대상자 검색 모달 연동
- 첨부파일 다운로드 보안 점검
- 권한 정책 분리 및 리팩토링
- Service layer 중심 구조 개선
- CSS No-Leak 점검
- CSP 대응 및 inline style/script 제거
- 운영 배포 전 회귀 체크

이 문서는 실제 코드를 대체하지 않습니다. 다만 전체 코드를 다시 제공하지 않아도, 코드 구조와 규약을 기준으로 안전한 피드백과 패치를 설계할 수 있도록 작성되었습니다.

---

## 1. 전체 기능 개요

WorkTask는 기존 Board 앱의 `Post(업무요청)` 및 `Task(직원업무)`와 별도로 분리된 개인 업무관리 기능입니다.

주요 목적은 다음과 같습니다.

- 업무 항목 등록/수정/삭제
- 업무 상태 관리
- 마감일 기반 D-day 표시
- 반복 업무 자동 생성
- 마감 전 알림
- 업무별 댓글 관리
- 업무별 첨부파일 관리
- 관련 인물 연결
- 지점 또는 대상 지점 지정
- 월별/상태별/분류별/지점별/키워드별 필터링

현재 URL 구조는 기존 Board 기능과 충돌하지 않도록 별도 namespace로 분리되어 있습니다.

```text
/board/worktasks/
```

Django URL namespace는 다음과 같습니다.

```text
board:worktasks
```

---

## 2. 관련 파일 구조

업무관리 관련 핵심 파일은 다음과 같습니다.

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
│  ├─ tasks.py
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
   │  ├─ base.css
   │  └─ apps/
   │     └─ board.css
   │
   └─ js/
      └─ board/
         ├─ worktask_list.js
         ├─ worktask_detail.js
         └─ worktask_form.js
```

---

## 3. Board 앱 전체 SSOT와 WorkTask의 위치

Board 앱은 기존에 다음 도메인을 포함합니다.

| 도메인 | 설명 |
|---|---|
| Post | 업무요청 게시판 |
| Task | 직원업무 게시판 |
| Support / States | 업무요청서 / 소명서 PDF |
| Collateral | 담보평가 계산기 |
| Industry Info | 업계정보 |
| WorkTask | 개인 업무관리 |

WorkTask는 기존 `/board/posts/`, `/board/tasks/`와 독립되어야 하며, 기존 URL·템플릿·JS 계약을 깨면 안 됩니다.

---

## 4. 핵심 설계 원칙

### 4.1 기능 변화 0 기본값

버그 수정 또는 UI 보완 요청이 있을 때는 요청한 범위 외 기능을 바꾸지 않습니다.

예:

- 댓글 개수 뱃지 줄바꿈 수정 요청 → CSS/마크업 최소 수정만 수행
- 지점 드롭다운 노출 문제 → 지점 옵션 조회 로직만 수정
- CSP 오류 수정 → inline style 제거 또는 CSS 클래스로 이동

금지:

- 목록 컬럼 재배치
- URL name 변경
- 상태값 변경
- 권한 완화
- 템플릿 id/class/data-* 광역 변경

---

### 4.2 URL namespace 고정

WorkTask URL은 `board:worktasks:*` namespace를 사용합니다.

예:

```django
{% url 'board:worktasks:worktask_list' %}
{% url 'board:worktasks:worktask_detail' task.pk %}
{% url 'board:worktasks:worktask_att_download' att.id %}
```

템플릿이나 redirect에서 raw path를 직접 쓰지 않습니다.

---

### 4.3 첨부파일 직접 URL 노출 금지

다음은 금지입니다.

```django
<a href="{{ att.file.url }}">
```

반드시 보호 다운로드 view를 사용합니다.

```django
<a href="{% url 'board:worktasks:worktask_att_download' att.id %}">
```

다운로드 흐름은 다음과 같아야 합니다.

```text
템플릿 URL
→ worktask_att_download view
→ service 또는 view에서 owner/권한 검증
→ FileResponse
→ RFC5987 파일명 처리
```

---

### 4.4 View는 얇게, Service는 두껍게

WorkTask의 핵심 데이터 접근은 `board/services/worktasks.py`를 경유해야 합니다.

중요 SSOT 함수:

```python
def get_user_queryset(user)
def get_user_task(user, pk)
def apply_filters(qs, params)
def create_task(user, data)
def update_task(task, data)
def mark_done(task)
def mark_skip(task)
def reset_status(task)
def delete_task(task, user)
def save_attachment(task, file, user)
def delete_attachment(att, user)
def get_pending_notify_tasks()
def generate_monthly_tasks(year, month)
```

특히 다음 규칙을 지킵니다.

- 목록 조회는 `get_user_queryset()` 시작
- 상세/수정/삭제는 `get_user_task()` 시작
- `get_object_or_404(WorkTask, pk=pk)` 단독 사용 금지
- owner 격리를 우회하지 않음

---

## 5. 주요 백엔드 파일별 지침

## 5.1 `board/constants.py`

역할:

- Board 앱 상수 SSOT
- 권한 등급
- 상태값
- 카테고리 선택값
- URL name
- Support Form 필드
- 담보평가 비율
- Audit action 상수

WorkTask에 직접 추가해야 할 상수가 생기면 이 파일에 추가할 수 있습니다.

권장 추가 후보:

```python
WORKTASK_ALLOWED_GRADES = ("superuser",)
WORKTASK_NAMESPACE = "board:worktasks"
WORKTASK_LIST = "board:worktasks:worktask_list"
WORKTASK_DETAIL = "board:worktasks:worktask_detail"
WORKTASK_ATTACHMENT_DOWNLOAD = "board:worktasks:worktask_att_download"
```

단, 기존 코드가 이미 URL name을 직접 사용 중이라면 한 번에 광역 변경하지 말고, 점진적으로 constants 기반으로 전환합니다.

---

## 5.2 `board/policies.py`

현재 Board 기본 정책은 Post 중심입니다.

기존 핵심 정책:

```python
def can_view_post(user, post)
def can_edit_post(user, post)
def can_download_post_attachment(user, attachment)
def can_download_task_attachment(user, attachment)
```

WorkTask는 현재 `@grade_required("superuser")`와 service의 owner 격리에 의존합니다.

향후 리팩토링 시 다음 정책 함수를 추가하는 것이 권장됩니다.

```python
def can_access_worktask(user) -> bool:
    return get_user_grade(user) == "superuser" and not is_inactive(user)


def can_view_worktask(user, task) -> bool:
    if not can_access_worktask(user):
        return False
    return str(getattr(task, "owner_id", "")) == str(getattr(user, "pk", ""))


def can_edit_worktask(user, task) -> bool:
    return can_view_worktask(user, task)


def can_download_worktask_attachment(user, attachment) -> bool:
    task = getattr(attachment, "task", None)
    return bool(task and can_view_worktask(user, task))
```

주의:

- 권한 완화를 위해 policy를 추가하면 안 됩니다.
- 현재 기준은 `superuser + owner 격리`입니다.
- 권한을 head/leader로 확장하려면 별도 기능 확장 설계가 필요합니다.

---

## 5.3 `board/signals.py`

역할:

- Attachment / TaskAttachment 삭제 시 실제 파일 삭제

현재 WorkTaskAttachment 삭제도 실제 파일 정리가 필요합니다.

점검 필요:

- `WorkTaskAttachment`도 signal 대상에 포함되어 있는지 확인
- 포함되어 있지 않다면 파일 orphan 가능성이 있습니다.

권장 방향:

```python
from .models import Attachment, TaskAttachment, WorkTaskAttachment

@receiver(post_delete, sender=WorkTaskAttachment)
def delete_worktask_attachment_file(sender, instance, **kwargs):
    _safe_delete_file(getattr(instance, "file", None))
```

단, 실제 패치 시 모델 import 순환 여부와 기존 service의 파일 삭제 로직 중복을 확인해야 합니다.

---

## 5.4 `board/worktask_urls.py`

WorkTask URL SSOT입니다.

현재 URL 구조:

```text
""                              worktask_list
"create/"                       worktask_create
"<int:pk>/"                     worktask_detail
"<int:pk>/edit/"                worktask_edit
"<int:pk>/done/"                worktask_done
"<int:pk>/skip/"                worktask_skip
"<int:pk>/delete/"              worktask_delete
"<int:pk>/reset/"               worktask_reset
"<int:pk>/inline-update/"       worktask_inline_update
"attachments/<int:att_id>/download/" worktask_att_download
"api/notify-check/"             worktask_notify_check
```

중요 규칙:

- 기존 `board/urls.py`의 post/task URL과 충돌 금지
- `include(("board.worktask_urls", "worktasks"))` 패턴 유지
- namespace는 `board:worktasks` 유지
- URL name 변경 금지

---

## 5.5 `board/views/__init__.py`

Board View Public API입니다.

기존 구조:

```python
from .posts import *
from .tasks import *
from .forms import *
from .attachments import *
from .collateral import ...
from .industry_info import ...
```

WorkTask는 현재 `board.views.worktasks` 모듈을 `worktask_urls.py`에서 직접 import합니다.

```python
from board.views import worktasks as wt_views
```

주의:

- `views/__init__.py`에서 worktasks view를 전부 re-export하지 않아도 현재 URL 구조는 동작합니다.
- 다만 외부에서 `board.views.worktask_list` 형태를 원한다면 `__init__.py`에 명시 export가 필요합니다.
- re-export 추가 시 기존 이름 충돌 여부를 확인해야 합니다.

---

## 5.6 `board/services/__init__.py`

현재 다음 코드가 있습니다.

```python
from board.views import worktasks  # noqa: F401
```

주의:

- `services/__init__.py`가 views를 import하는 구조는 계층 방향상 권장되지 않습니다.
- 일반적인 방향은 `views → services`입니다.
- `services → views`는 순환 import 위험이 있습니다.

향후 리팩토링 후보:

```python
# board/services/__init__.py
# 비워두거나 service module만 노출
```

단, 현재 import 경로 호환을 위해 사용 중일 수 있으므로 패치 전 grep으로 사용처를 확인합니다.

---

## 5.7 `board/models.py`

WorkTask 관련 모델은 다음 구성을 전제로 합니다.

예상 모델:

```text
WorkCategory
WorkTask
WorkTaskAttachment
WorkTaskComment
```

WorkTask 핵심 필드 예상:

| 필드 | 역할 |
|---|---|
| owner | 업무 소유자 |
| category | 업무 분류 |
| title | 업무명 |
| description | 메모 |
| start_date | 시작일 |
| due_date | 마감일 |
| priority | 우선순위 |
| status | 상태 |
| recurrence_type | 반복 유형 |
| recurrence_day | 반복 일자 |
| is_template | 반복 원본 여부 |
| template_task | 자동생성 자식의 원본 업무 |
| target_ym | 자동생성 대상 월 |
| notify_days_before | 알림 기준일 |
| is_notified | 알림 발송 여부 |
| family_branches | 지점명 목록 JSON |
| related_users | 관련 인물 M2M |
| created_at / updated_at | 생성/수정 시각 |

중요:

- `family_branches`는 JSON list[str] 형태입니다.
- 필터에서 `family_branches__contains=[branch]`를 사용합니다.
- DB가 PostgreSQL이면 JSON contains는 정상 동작하지만, SQLite 개발환경에서는 동작 차이가 있을 수 있습니다.

---

## 5.8 `board/forms.py`

WorkTask 관련 form은 다음이 포함됩니다.

```python
WorkTaskCommentForm
```

댓글 공통 처리에는 `board.services.comments.handle_comments_actions()`를 사용합니다.

WorkTask 등록/수정은 현재 Django Form보다는 `_extract_post_data(request)` 기반으로 처리되는 구조입니다.

향후 개선 후보:

- `WorkTaskForm` 도입
- 서버단 검증을 form으로 이동
- `_extract_post_data()` 중복 제거

단, 기능 변화 0 리팩토링으로 진행해야 하며, 입력 field name과 템플릿 DOM 계약을 바꾸면 안 됩니다.

---

## 5.9 `board/views/worktasks.py`

WorkTask HTTP view 레이어입니다.

핵심 원칙:

- 모든 view는 `@grade_required("superuser")`
- POST AJAX는 `@require_POST`
- DB 접근은 service 경유
- 첨부 다운로드는 권한 검증 후 FileResponse
- AJAX 응답 규약은 `{ "ok": true/false }`

### 5.9.1 `_get_worktask_branch_options(request)`

역할:

- 업무등록/수정/목록 필터의 지점 드롭다운 옵션 생성

현재 정책:

- superuser:
  - 활성 사용자 `CustomUser.branch` distinct
  - user.part가 있으면 해당 part로 제한
  - part가 없고 channel이 있으면 channel로 제한
- 그 외:
  - 본인 branch만 노출

주의:

- 현재 WorkTask view는 superuser 전용이므로, superuser가 소속 part/channel에 따라 제한되는 구조입니다.
- “superuser 산하 지점”이 정상 출력되지 않을 때는 이 함수가 1차 점검 대상입니다.
- 지점명 공백 제거를 위해 `Trim("branch")` 사용합니다.

### 5.9.2 `_ok`, `_err`

AJAX 응답 규약:

```json
{ "ok": true }
{ "ok": false, "error": "..." }
```

주의:

- Partner/Commission의 `{status: "success"}`와 다릅니다.
- WorkTask JS는 `result.ok`를 기준으로 판단합니다.

### 5.9.3 `worktask_list(request)`

기능:

- 월별 업무 목록 표시
- 필터 처리
- pagination
- 카테고리/상태/지점 옵션 전달

GET parameter:

| 파라미터 | 설명 |
|---|---|
| ym | 귀속월, `YYYY-MM` |
| status | 상태 |
| category | 분류 code |
| branch | 지점명 |
| keyword | 업무명/메모 검색어 |
| page | 페이지 |

조회 흐름:

```python
qs = wt_svc.get_user_queryset(request.user)
qs = wt_svc.apply_filters(qs, params)
qs = qs.order_by("priority", "due_date", "-created_at")
```

중요:

- `comment_count`는 service에서 annotate합니다.
- 템플릿에서 `task.comment_count`를 사용합니다.
- 첨부 수는 현재 `task.attachments.count`로 표시됩니다. prefetch가 있어도 template에서 count 호출 방식에 따라 추가 쿼리 가능성 점검이 필요합니다.

### 5.9.4 `worktask_create(request)`

기능:

- 업무 항목 등록
- 첨부 저장
- 성공 시 detail redirect

흐름:

```python
data = _extract_post_data(request)
task = wt_svc.create_task(request.user, data)
for f in request.FILES.getlist("attachments"):
    wt_svc.save_attachment(task, f, request.user)
```

주의:

- owner는 service에서 강제 주입합니다.
- view에서 owner를 직접 지정하면 안 됩니다.
- 저장 실패 시 서버 로그를 남기고 사용자에게 일반 오류 메시지를 보여줍니다.

### 5.9.5 `worktask_detail(request, pk)`

기능:

- 업무 상세 표시
- 댓글 등록/수정/삭제 처리

권한:

```python
task = wt_svc.get_user_task(request.user, pk)
```

즉 타인 업무 pk 접근 시 404가 정상입니다.

댓글 처리:

```python
handle_comments_actions(
    request=request,
    obj=task,
    comment_model=WorkTaskComment,
    fk_field="task",
    redirect_detail_name="board:worktasks:worktask_detail",
)
```

주의:

- 댓글 템플릿은 Board 공용 include를 사용합니다.
- `#commentEditCsrfToken` hidden input이 필요합니다.

### 5.9.6 `worktask_edit(request, pk)`

기능:

- 업무 수정
- 신규 첨부 추가
- 기존 첨부 삭제

권한:

```python
task = wt_svc.get_user_task(request.user, pk)
```

첨부 삭제:

```python
for key in request.POST:
    if key.startswith("delete_att_"):
        att = get_object_or_404(WorkTaskAttachment, pk=att_id, task=task)
        wt_svc.delete_attachment(att, request.user)
```

주의:

- 첨부 삭제는 task 소속 검증이 포함되어야 합니다.
- delete checkbox name 계약을 바꾸면 안 됩니다.

### 5.9.7 AJAX 상태 변경 view

예상 view:

```python
worktask_done
worktask_skip
worktask_reset
worktask_delete
worktask_inline_update
```

규약:

- POST only
- `@grade_required("superuser")`
- `wt_svc.get_user_task()`으로 owner 격리
- 응답은 `{ok: true/false}`

---

## 5.10 `board/services/worktasks.py`

WorkTask 서비스 레이어이며, 소유자 격리 SSOT입니다.

### 5.10.1 `get_user_queryset(user)`

모든 목록 조회의 시작점입니다.

기준:

```python
WorkTask.objects
    .filter(owner=user)
    .select_related("category", "owner")
    .prefetch_related("related_users", "attachments")
    .annotate(comment_count=Count("comments", distinct=True))
```

중요:

- owner=user 격리를 우회하면 안 됩니다.
- 목록 성능 최적화는 여기서 처리합니다.
- 댓글 count 표시도 여기서 annotate합니다.

### 5.10.2 `get_user_task(user, pk)`

상세/수정/삭제의 단일 진입점입니다.

```python
return get_object_or_404(WorkTask, pk=pk, owner=user)
```

타인 업무 접근 시 404를 반환하는 것이 정상입니다.

### 5.10.3 `apply_filters(qs, params)`

필터 처리 기준입니다.

필터:

- `ym`
- `status`
- `category`
- `branch`
- `keyword`

월 필터 규칙:

```text
1. 자동생성 자식: target_ym = ym
2. 일반 항목: due_date가 해당 월 범위
3. due_date 없는 원본 템플릿: 포함
```

지점 필터:

```python
qs = qs.filter(family_branches__contains=[branch])
```

주의:

- `family_branches`가 list[str]로 저장되어야 합니다.
- branch 값의 공백/중복 정규화는 `_clean_family_branches()`에서 처리합니다.

### 5.10.4 `_clean_family_branches(values)`

기능:

- 문자열 또는 list를 list[str]로 정규화
- 공백 제거
- 빈 값 제거
- 중복 제거
- 순서 유지

템플릿에서는 다음 방식으로 전송됩니다.

```html
<input type="hidden" name="family_branches" value="지점명">
```

### 5.10.5 `create_task(user, data)`

원칙:

- owner는 무조건 service에서 강제 주입
- `task.full_clean()` 수행
- related_users는 task 저장 후 set
- transaction.atomic 사용

### 5.10.6 `update_task(task, data)`

원칙:

- owner 변경 금지
- `owner`, `owner_id` 제거
- family_branches 정규화
- related_users가 None이면 M2M 변경하지 않음
- transaction.atomic 사용

### 5.10.7 상태 변경 함수

예상:

```python
mark_done(task)
mark_skip(task)
reset_status(task)
```

주의:

- 상태 변경 시 updated_at 또는 status 관련 필드 갱신 정책 유지
- 알림 상태 `is_notified` 초기화 여부가 필요한지 점검

### 5.10.8 반복 생성 함수

예상:

```python
generate_monthly_tasks(year, month)
```

Celery task에서 호출됩니다.

중요:

- 중복 생성 방지 필수
- 원본 템플릿과 자동생성 자식 구분 필수
- `target_ym` 기준 unique 또는 중복 체크 필요

---

## 5.11 `board/tasks.py`

WorkTask 관련 Celery task가 정의되어 있습니다.

### 5.11.1 반복 WorkTask 자동생성

Task name:

```python
board.tasks.generate_monthly_worktasks
```

역할:

- 반복 원본 업무에서 해당 월 자식 WorkTask 자동 생성
- `board.services.worktasks.generate_monthly_tasks()`에 위임

운영 주의:

- Celery beat schedule의 task 값과 `@shared_task(name=...)` 값이 정확히 일치해야 합니다.
- 불일치 시 task가 실행되지 않습니다.

점검 명령:

```bash
celery -A web_ma inspect registered | grep worktask
```

### 5.11.2 마감 D-N일 알림 이메일

Task name:

```python
board.tasks.notify_due_worktasks
```

역할:

- 마감 임박 미완료 업무를 owner별로 이메일 발송
- owner별 그룹핑으로 타인 업무 노출 방지
- 발송 완료 후 `is_notified=True`

주의:

- 이메일 없는 owner는 skip
- 발송 실패 시 retry
- 메일 본문에 타인 업무가 포함되면 안 됨

---

## 6. 템플릿 기준

## 6.1 공통 상속

WorkTask 템플릿은 Board 앱 전용 base를 상속해야 합니다.

```django
{% extends "board/base_board.html" %}
```

이유:

- `board.css`가 `app_css` 블록에서만 로드됨
- `.board-scope`로 CSS 누수 차단
- 전역 base.html과 앱 전용 CSS 분리

---

## 6.2 `worktask_list.html`

업무관리 목록 화면입니다.

### Boot root

```html
<div id="worktaskListBoot"
     class="worktask-list-wide"
     data-delete-url="..."
     data-inline-url="...">
```

JS는 이 dataset만 읽어야 합니다.

현재 data 계약:

| data-* | 역할 |
|---|---|
| data-delete-url | 삭제 AJAX URL, pk placeholder `0` 포함 |
| data-inline-url | 인라인 업데이트 URL, pk placeholder `0` 포함 |

확장 후보:

| data-* | 역할 |
|---|---|
| data-done-url | 완료 처리 URL |
| data-skip-url | 건너뜀 URL |
| data-reset-url | 상태 복원 URL |

단, 실제 JS 사용 여부 확인 후 추가해야 합니다.

### 필터 form

필터 항목:

- ym hidden
- status select
- category select
- branch select
- keyword input

주의:

- querystring 유지 로직이 prev/next ym 링크에 포함됩니다.
- 새 필터를 추가하면 월 이동 링크에도 반영해야 합니다.

### 목록 table

주요 컬럼:

| 컬럼 | 내용 |
|---|---|
| 분류 | category badge |
| 업무명 | title link + 첨부 icon + 댓글 count |
| 지점 | family_branches |
| 대상 | related_users |
| 우선순위 | priority |
| 시작일 | start_date |
| 마감일 | due_date + D-day |
| 상태 | status |
| 삭제 | delete button |

### 업무명 라인 DOM 계약

중요 구조:

```html
<td class="board-col-title">
  <div class="worktask-title-line">
    <a class="worktask-title-link">{{ task.title }}</a>
    <span class="worktask-title-icon">📎</span>
    <span class="worktask-comment-count-badge">...</span>
  </div>
</td>
```

댓글 count 줄바꿈 문제는 이 영역의 CSS가 1차 점검 대상입니다.

권장 CSS 방향:

```css
.board-scope .worktask-title-line {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  white-space: nowrap;
}

.board-scope .worktask-title-link {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-scope .worktask-comment-count-badge,
.board-scope .worktask-title-icon {
  flex: 0 0 auto;
  white-space: nowrap;
}
```

주의:

- `td.board-col-title`의 ellipsis 정책과 충돌하지 않도록 `.worktask-title-link`에 min-width:0을 줘야 합니다.
- badge가 줄바꿈되면 `flex: 0 0 auto`와 `white-space: nowrap`을 확인합니다.

---

## 6.3 `worktask_create.html`

업무 등록 화면입니다.

### form 계약

```html
<form method="post" enctype="multipart/form-data" id="worktaskCreateForm">
```

중요 field name:

| name | 설명 |
|---|---|
| category | 분류 |
| title | 업무명 |
| description | 메모 |
| start_date | 시작일 |
| due_date | 마감일 |
| priority | 우선순위 |
| recurrence_type | 반복 유형 |
| recurrence_day | 반복 일자 |
| family_branches | 지점 hidden input 다중 |
| related_users | 관련 인물 hidden input 다중 |
| attachments | 첨부파일 |
| notify_days_before | 알림 기준일 |

### 반복 custom 토글

DOM 계약:

```html
<select id="id_recurrence_type" name="recurrence_type">
<div id="recurrence-day-group">
<input id="id_recurrence_day" name="recurrence_day">
```

`worktask_form.js`가 이 id에 의존합니다.

### 지점 선택 모달

DOM 계약:

```html
<div id="family-branches-tags"></div>
<div id="family-branches-hidden-inputs"></div>
<select id="worktaskFamilyBranchSelect"></select>
<button id="btn-confirm-family-branch"></button>
<div id="worktaskFamilyBranchModal"></div>
```

주의:

- 버튼에 inline style을 넣으면 CSP 위반 가능성이 있습니다.
- hidden input은 반드시 `name="family_branches"` 유지
- 모달 내 select option은 서버에서 전달한 `branch_options`를 기준으로 렌더링

### 관련 인물 검색

공용 검색 모달을 사용합니다.

```text
templates/components/search_user_modal.html
static/js/common/search_user_modal.js
```

WorkTask JS는 `window.userSelected` 이벤트만 수신합니다.

---

## 6.4 `worktask_edit.html`

업무 수정 화면입니다.

### form 계약

```html
<form method="post" enctype="multipart/form-data" id="worktaskEditForm">
```

등록 화면과 대부분 동일하되 다음이 추가됩니다.

- 현재 status 수정
- 기존 family_branches tag 렌더링
- 기존 related_users tag 렌더링
- 기존 attachments 삭제 checkbox

주의:

- 기존 지점 hidden input id 생성 방식과 JS의 `makeSafeId()`가 충돌하지 않아야 합니다.
- 삭제 checkbox name은 view가 `delete_att_<id>` 패턴으로 탐색합니다.

---

## 6.5 `worktask_detail.html`

업무 상세 화면입니다.

### Boot root

```html
<div id="worktaskDetailBoot"
     data-pk="{{ task.pk }}"
     data-done-url="..."
     data-skip-url="...">
```

JS가 상세 상태 처리 URL을 읽습니다.

### 주요 표시 영역

- 분류 badge
- 상태 badge
- 우선순위 badge
- 반복 원본 표시
- 자동생성 표시
- 업무명
- 메모
- 댓글 카드
- 일정 카드
- 지점/대상 카드
- 첨부파일 카드
- 하단 액션

### 댓글 영역

```django
{% include "board/includes/_comment_list.html" with comments=comments empty_text="아직 댓글이 없습니다." %}
{% include "board/includes/_comment_form.html" with form=form action_url=detail_url submit_label="등록" %}
```

필수 hidden:

```html
<input type="hidden" id="commentEditCsrfToken" value="{{ csrf_token }}">
```

### D-day 표시

```html
<span id="detail-dday" class="worktask-dday-badge" data-due="YYYY-MM-DD"></span>
```

`worktask_detail.js`가 계산합니다.

---

## 7. 프론트엔드 JS 기준

## 7.1 공통 규칙

모든 WorkTask JS는 다음 규칙을 따릅니다.

- DOM이 없으면 조용히 종료
- root boot dataset만 읽음
- 중복 바인딩 방지
- 중복 제출 방지
- CSRF는 공용 유틸 사용
- 인라인 스크립트 금지
- 프론트에서 권한 판단 금지
- 사용자 검색 범위는 서버 API가 결정

---

## 7.2 `static/js/board/worktask_list.js`

목록 전용 JS입니다.

역할:

- 삭제 버튼 처리
- 인라인 셀 편집
- D-day 렌더링
- BFCache 대응

### Boot 계약

```js
const boot = document.getElementById("worktaskListBoot");
```

없으면 no-op 종료합니다.

### 중복 초기화 방지

```js
if (boot.dataset.inited === "1") return;
boot.dataset.inited = "1";
```

### 삭제 처리

계약:

- 삭제 버튼 class: `.worktask-delete-btn`
- data-pk 필요
- data-title 선택
- URL은 `boot.dataset.deleteUrl`에서 pk `0` 치환

응답:

```json
{ "ok": true }
```

### 인라인 편집

대상 cell:

```html
<td class="worktask-cell-edit"
    data-field="category"
    data-value="..."
    data-pk="...">
```

지원 field:

- category
- priority
- status
- start_date
- due_date

분류/status 옵션은 JSON script block에서 읽습니다.

예상 id:

```html
<script id="worktask-category-options" type="application/json">...</script>
<script id="worktask-status-options" type="application/json">...</script>
```

주의:

- JSON script block은 CSP 안전 방식입니다.
- inline JS로 옵션 배열을 만들지 않습니다.

---

## 7.3 `static/js/board/worktask_detail.js`

상세/등록/수정 일부 공용 JS입니다.

역할:

- 댓글 인라인 수정 초기화
- 관련 인물 검색 모달 연동
- 폼 중복 제출 방지
- D-day 렌더링
- 상세 상태 처리

주의:

- 관련 인물 검색 모달 open은 `search_user_modal.js`에 위임합니다.
- WorkTask JS가 직접 Bootstrap modal을 열지 않습니다.
- `userSelected` custom event만 수신합니다.

### 관련 인물 DOM 계약

```html
<button id="btn-search-related-user" class="btnOpenSearch"></button>
<div id="related-users-tags"></div>
<div id="related-users-hidden-inputs"></div>
```

hidden input:

```html
<input type="hidden" name="related_users" value="사용자ID">
```

---

## 7.4 `static/js/board/worktask_form.js`

등록/수정 폼 전용 JS입니다.

역할:

- 반복 유형 custom 토글
- 기존 관련 인물 태그 제거
- 지점 추가/삭제
- 관련 인물 검색 모달 연동
- 폼 중복 제출 방지

### 반복 토글

```js
const sel = document.getElementById("id_recurrence_type");
const group = document.getElementById("recurrence-day-group");
```

`sel.value !== "custom"`이면 `d-none`을 부여합니다.

### 지점 추가/삭제

DOM 계약:

```html
<div id="family-branches-tags"></div>
<div id="family-branches-hidden-inputs"></div>
<select id="worktaskFamilyBranchSelect"></select>
<button id="btn-confirm-family-branch"></button>
<div id="worktaskFamilyBranchModal"></div>
```

중요:

- tag와 hidden input이 항상 동기화되어야 합니다.
- 중복 지점은 Set으로 차단합니다.
- hidden input name은 `family_branches` 유지
- 삭제 버튼 class는 `.worktask-remove-family-branch`

### XSS 방어

JS에서 동적 HTML 생성 시 `_escHtml()` 또는 `_esc()` 사용이 필요합니다.

주의:

- branch/user.name 값을 `innerHTML`에 넣을 때 escape 없이 넣으면 XSS 위험이 있습니다.
- 가능하면 `textContent` 기반 DOM 생성으로 전환하는 것이 장기적으로 더 안전합니다.

---

## 8. CSS 기준

## 8.1 CSS 파일 위치

```text
static/css/apps/board.css
```

Board 앱 CSS는 반드시 `.board-scope` 하위에만 작성합니다.

금지:

```css
.worktask-title-line { ... }
```

필수:

```css
.board-scope .worktask-title-line { ... }
```

---

## 8.2 WorkTask 목록 레이아웃 기준

목록 테이블은 fixed layout 기반입니다.

```css
.board-scope .board-post-table {
  table-layout: fixed;
  width: 100%;
}
```

이 구조에서는 ellipsis가 동작하려면 다음 조건이 필요합니다.

- 부모 cell에 `overflow: hidden`
- 실제 텍스트 요소에 `min-width: 0`
- flex children에 적절한 `flex` 설정
- badge/icon은 `flex: 0 0 auto`

---

## 8.3 댓글 개수 badge 줄바꿈 방지 기준

업무명 오른쪽에 첨부 아이콘과 댓글 개수를 나란히 표시하려면 다음 구조를 유지합니다.

```css
.board-scope .worktask-title-line {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  white-space: nowrap;
}

.board-scope .worktask-title-link {
  display: inline-block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-scope .worktask-title-icon,
.board-scope .worktask-comment-count-badge {
  flex: 0 0 auto;
  white-space: nowrap;
}
```

주의:

- title link가 너무 길면 badge가 밀릴 수 있습니다.
- 이때 `worktask-title-link`에 `flex: 0 1 auto` 또는 `flex: 1 1 auto`를 적용할지 UI 요구에 맞게 결정합니다.
- badge를 항상 보이게 하려면 title link가 줄어들어야 합니다.

권장:

```css
.board-scope .worktask-title-link {
  flex: 0 1 auto;
  max-width: 100%;
}
```

---

## 8.4 CSP 대응 CSS 원칙

CSP 정책상 inline style은 차단될 수 있습니다.

금지:

```html
<div style="min-height:32px"></div>
```

권장:

```html
<div class="min-height-32"></div>
```

```css
.board-scope .min-height-32 {
  min-height: 32px;
}
```

단, 전역 helper가 필요한 경우 `base.css`에 넣을지, Board 전용이면 `board.css`에 넣을지 구분합니다.

---

## 9. 권한/보안 기준

## 9.1 접근 권한

현재 WorkTask는 superuser 전용입니다.

```python
@grade_required("superuser")
```

모든 view에 이 권한이 적용되어야 합니다.

적용 대상:

- list
- create
- detail
- edit
- done
- skip
- delete
- reset
- inline_update
- attachment_download
- notify_check

---

## 9.2 owner 격리

권한이 superuser라고 해도 WorkTask는 owner 격리를 유지합니다.

핵심:

```python
get_user_queryset(request.user)
get_user_task(request.user, pk)
```

현재 의미:

- superuser도 자기 owner 업무만 조회/수정/삭제
- 타인의 pk 접근 시 404

주의:

- 전체 관리자로 타인 업무 조회 기능을 추가하려면 별도 설계가 필요합니다.
- 단순히 `owner=user` 필터를 제거하면 보안 회귀입니다.

---

## 9.3 첨부파일 다운로드

원칙:

```text
att.file.url 직접 노출 금지
→ worktask_att_download 경유
→ owner 검증
→ FileResponse
```

점검 포인트:

- template에 `att.file.url`이 남아 있지 않은가
- download view가 `WorkTaskAttachment`만 조회하는가
- attachment의 task owner를 검증하는가
- Content-Disposition이 RFC5987 방식인가
- 파일 핸들 close가 보장되는가

---

## 9.4 CSRF

AJAX POST는 CSRF 토큰을 포함해야 합니다.

JS는 공용 유틸을 사용합니다.

```js
import { getCSRFToken } from "../common/manage/csrf.js";
```

금지:

- CSRF 토큰 파싱 중복 구현
- CSRF exempt 적용
- GET으로 상태 변경

---

## 9.5 XSS 방어

템플릿 원칙:

- `task.description|safe` 금지
- 사용자 입력값은 Django 자동 escape에 맡김
- JS에서 동적 HTML 생성 시 escape 필수

주의 영역:

- branch tag 생성
- related user tag 생성
- inline editor display 복원
- 댓글 내용

---

## 10. Celery / 운영 작업 기준

## 10.1 반복 업무 자동 생성

작업명:

```text
board.tasks.generate_monthly_worktasks
```

실행 주기 예:

```text
매월 1일 00:10
```

점검 항목:

- beat schedule task name 일치
- worker registered task에 포함
- 중복 생성 방지
- target_ym 저장
- template_task 연결
- transaction.atomic 사용

---

## 10.2 마감 알림

작업명:

```text
board.tasks.notify_due_worktasks
```

발송 기준:

```text
is_notified=False
AND due_date <= today + notify_days_before
AND 미완료 상태
```

주의:

- owner별 업무만 메일에 포함
- email 없는 사용자 skip
- 발송 성공 후 is_notified=True
- 실패 시 retry

---

## 11. Audit / Logging 기준

현재 WorkTask 코드에는 logger는 있으나 audit log 연계는 명시적으로 강화할 여지가 있습니다.

운영상 audit 대상 후보:

| 액션 | 권장 Audit action |
|---|---|
| 업무 생성 | board_worktask_create |
| 업무 수정 | board_worktask_update |
| 업무 삭제 | board_worktask_delete |
| 상태 변경 | board_worktask_status_update |
| 첨부 업로드 | board_worktask_attachment_upload |
| 첨부 다운로드 | board_worktask_attachment_download |
| 첨부 삭제 | board_worktask_attachment_delete |
| 반복 자동 생성 | board_worktask_generate_monthly |
| 알림 발송 | board_worktask_notify_due |

추가 시 기준:

```python
from audit.services import log_action
```

필수 메타:

- actor
- action
- object_type
- object_id
- success/fail
- reason
- request_id
- ip
- 주요 파라미터 요약

민감정보나 업무 상세 내용 전문을 audit meta에 넣지 않습니다.

---

## 12. 자주 발생 가능한 이슈와 원인 후보

## 12.1 댓글 개수 뱃지가 업무명 아래로 내려감

가능성 높은 원인:

1. `.worktask-title-line`이 flex가 아님
2. title link가 가로폭을 모두 차지함
3. badge에 `white-space: nowrap` 없음
4. 부모 td의 `overflow/ellipsis` 정책과 flex가 충돌
5. badge가 inline 요소인데 line-height 또는 display 설정이 불안정

점검 파일:

```text
templates/board/worktask_list.html
static/css/apps/board.css
```

권장 수정:

- `.worktask-title-line` flex 적용
- `.worktask-title-link` min-width:0 + ellipsis
- badge/icon flex none

---

## 12.2 지점 드롭다운이 비어 있음

가능성 높은 원인:

1. `_get_worktask_branch_options()`에서 superuser의 part/channel 필터가 너무 좁음
2. CustomUser.branch가 공백 또는 null
3. CustomUser.is_active=False 사용자만 존재
4. branch에 앞뒤 공백이 있어 distinct 결과가 이상함
5. 템플릿에서 `branch_options`를 렌더링하지 않음

점검 파일:

```text
board/views/worktasks.py
board/templates/board/worktask_create.html
board/templates/board/worktask_edit.html
```

---

## 12.3 지점 선택 후 저장되지 않음

가능성 높은 원인:

1. hidden input wrapper id 불일치
2. hidden input name이 `family_branches`가 아님
3. `worktask_form.js`가 로드되지 않음
4. `_extract_post_data()`에서 `request.POST.getlist("family_branches")`를 수집하지 않음
5. service에서 `_clean_family_branches()` 호출 누락
6. 모델 field가 JSONField가 아님 또는 migration 누락

점검 파일:

```text
worktask_create.html
worktask_edit.html
worktask_form.js
views/worktasks.py
services/worktasks.py
models.py
```

---

## 12.4 첨부 다운로드 403/404

가능성 높은 원인:

1. template URL name 오타
2. `att.file.url` 직접 사용 중
3. att_id는 존재하지만 해당 task owner가 현재 사용자가 아님
4. 실제 파일이 storage에 없음
5. FileResponse 생성 시 파일 경로 처리 오류
6. 원본 파일명 인코딩 문제

점검 파일:

```text
worktask_detail.html
worktask_edit.html
views/worktasks.py
services/worktasks.py
signals.py
```

---

## 12.5 인라인 수정이 저장되지 않음

가능성 높은 원인:

1. `#worktaskListBoot` 없음
2. `data-inline-url` 없음
3. pk placeholder `0` 치환 실패
4. CSRF 헤더 누락
5. 서버 응답이 `{ok:true}`가 아님
6. field 값이 서버 allowlist에 없음
7. category/status 옵션 JSON script 누락

점검 파일:

```text
worktask_list.html
worktask_list.js
views/worktasks.py
services/worktasks.py
```

---

## 12.6 반복 업무가 자동 생성되지 않음

가능성 높은 원인:

1. Celery worker 미실행
2. celery beat 미실행
3. beat schedule task name 불일치
4. `board.tasks` autodiscover 누락
5. 반복 원본 조건 불일치
6. 중복 생성 방지 로직이 과도하게 차단
7. target_ym 계산 오류

점검 명령:

```bash
celery -A web_ma inspect registered | grep worktask
celery -A web_ma beat --loglevel=info
celery -A web_ma worker --loglevel=info
```

---

## 13. 패치 응답 작성 기준

WorkTask 관련 코드 수정 요청을 받으면 반드시 다음 형식으로 답변합니다.

```text
1. 변경 목적
2. 수정 파일 목록 + 영향도
3. diff 패치
4. 회귀 위험 체크
5. 로컬 검증 체크리스트
6. 운영 배포 주의사항
```

### 13.1 diff 패치 원칙

- 전체 파일 재작성보다 최소 diff 우선
- id/class/data-* 변경 최소화
- URL name 변경 금지
- 권한 완화 금지
- `.file.url` 직접 노출 금지
- inline style/script 추가 금지

---

## 14. 회귀 위험 체크리스트

패치 전후 다음을 반드시 확인합니다.

### Backend

- [ ] `@grade_required("superuser")` 유지
- [ ] `get_user_queryset()` / `get_user_task()` 우회 없음
- [ ] owner 변경 허용 없음
- [ ] 첨부 다운로드 view 경유 유지
- [ ] AJAX POST에 `@require_POST` 유지
- [ ] 응답 JSON `{ok: true/false}` 유지
- [ ] transaction.atomic 필요한 곳 유지
- [ ] Celery task name 불일치 없음

### Template

- [ ] `board/base_board.html` 상속 유지
- [ ] `#worktaskListBoot` 유지
- [ ] `#worktaskDetailBoot` 유지
- [ ] form id 유지
- [ ] field name 유지
- [ ] hidden input name 유지
- [ ] `att.file.url` 직접 링크 없음
- [ ] inline style/script 추가 없음

### JavaScript

- [ ] dataset 기반 URL 사용
- [ ] dataset.inited 유지
- [ ] dataset.submitting 유지
- [ ] CSRF 공용 유틸 사용
- [ ] search_user_modal 직접 복제 없음
- [ ] userSelected 이벤트 계약 유지
- [ ] BFCache 대응 깨짐 없음

### CSS

- [ ] 모든 selector `.board-scope` 하위
- [ ] base.css에 앱 전용 스타일 추가하지 않음
- [ ] fixes.css에 WorkTask 전용 스타일 추가하지 않음
- [ ] table fixed layout과 ellipsis 충돌 없음
- [ ] 모바일 레이아웃 확인

---

## 15. 로컬 검증 체크리스트

### 15.1 기본 점검

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

### 15.2 WorkTask 화면 검증

- [ ] `/board/worktasks/` 진입
- [ ] 월 이동 prev/next 정상
- [ ] 상태 필터 정상
- [ ] 분류 필터 정상
- [ ] 지점 필터 정상
- [ ] 키워드 검색 정상
- [ ] 업무 등록 페이지 진입
- [ ] 지점 추가/삭제 정상
- [ ] 관련 인물 검색/선택/삭제 정상
- [ ] 첨부 업로드 정상
- [ ] 상세 페이지 진입
- [ ] 댓글 등록/수정/삭제 정상
- [ ] 첨부 다운로드 정상
- [ ] 수정 페이지 진입
- [ ] 기존 첨부 삭제 정상
- [ ] 목록 인라인 수정 정상
- [ ] 삭제 정상

### 15.3 권한 검증

- [ ] superuser 로그인 시 접근 가능
- [ ] superuser라도 타 owner 업무 pk 직접 접근 시 404인지 확인
- [ ] basic/head/leader 접근 차단 확인
- [ ] inactive 접근 차단 확인

### 15.4 브라우저 검증

- [ ] 콘솔 JS 오류 없음
- [ ] CSP inline style/script 오류 없음
- [ ] Network에서 AJAX 200/403/404 의미 정상
- [ ] 모바일 폭에서 목록/버튼 깨짐 없음
- [ ] 댓글 count 뱃지 줄바꿈 없음

### 15.5 운영 유사 검증

```powershell
python manage.py collectstatic --noinput
```

- [ ] static file 200/304 확인
- [ ] Whitenoise manifest 오류 없음
- [ ] 첨부 다운로드 파일명 한글 깨짐 없음
- [ ] 서버 로그에 traceback 기록 정상

---

## 16. 우선 개선 후보

현재 WorkTask 코드 기준으로 향후 개선 우선순위는 다음과 같습니다.

### 최상

- WorkTask 권한 policy 분리
- 첨부 다운로드 audit log 추가
- `services/__init__.py`의 views import 제거 검토

### 상

- WorkTaskAttachment 파일 삭제 signal 또는 service 일원화 점검
- `_extract_post_data()` 검증 로직 form/service로 분리
- inline update field allowlist 명확화
- JS 동적 innerHTML escape 점검

### 중상

- 목록 첨부 count 추가 쿼리 여부 최적화
- family_branches JSONField 필터 DB별 호환성 점검
- 반복 생성 unique constraint 또는 중복 방지 강화
- Celery task idempotency 문서화

### 중

- WorkTask constants 추가
- status/category option JSON 생성 helper 공통화
- D-day 렌더링 공통화
- 삭제 confirm 메시지 공통화

### 중하

- CSS 변수 정리
- badge 디자인 통일
- 모바일 테이블 UX 개선

### 하

- 주석 정리
- 버튼 라벨 통일
- 템플릿 공백 정리

---

## 17. 금지 패턴

다음은 WorkTask 코드 수정 시 금지합니다.

```django
<a href="{{ att.file.url }}">
```

```python
get_object_or_404(WorkTask, pk=pk)
```

```python
@csrf_exempt
```

```javascript
fetch(url, { method: "GET" }) // 상태 변경
```

```html
<div style="...">
<script>...</script>
```

```css
.worktask-title-line { ... }  /* .board-scope 누락 */
```

```python
WorkTask.objects.all()  # owner 격리 우회
```

---

## 18. 새 채팅에서 이 문서를 사용하는 방법

새 채팅에서 WorkTask 관련 요청을 할 때는 다음처럼 말하면 됩니다.

```text
board_worktask_guide.md 기준으로 업무관리 목록에서 댓글 뱃지가 줄바꿈되는 문제 diff 패치해줘.
```

또는:

```text
업무관리 WorkTask 기준 지침서 기준으로 지점 드롭다운이 비는 원인만 분석해줘. 해결책은 아직 제시하지 마.
```

또는:

```text
WorkTask 첨부 다운로드 보안 점검해줘. 패치 없이 체크리스트만.
```

이 문서를 기준으로 하면 전체 소스코드를 다시 공유하지 않아도, 구조와 규약을 전제로 분석 및 패치 설계가 가능합니다.

---

## 19. 최종 요약

WorkTask는 Board 앱 안에 있지만 기존 Post/Task와 독립된 업무관리 도메인입니다.

핵심은 다음 5가지입니다.

1. URL namespace는 `board:worktasks`로 유지합니다.
2. 모든 접근은 `superuser` 전용이며, service에서 owner 격리를 유지합니다.
3. 첨부파일은 절대 `.file.url`로 노출하지 않고 보호 다운로드 view를 사용합니다.
4. 프론트는 Boot dataset과 공용 search modal, CSRF 유틸을 재사용합니다.
5. CSS는 반드시 `.board-scope` 하위에만 작성하여 전역 누수를 막습니다.

이 기준을 깨지 않는 범위에서만 기능 수정, UI 보완, 리팩토링을 진행합니다.
