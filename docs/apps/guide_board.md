# board 앱 개발 가이드

> **목적**: 외부 LLM이 전체 코드 없이 board 앱을 정확하게 디벨롭할 수 있는 수준의 참조 문서.
> **기준 커밋**: develop 브랜치 (2026-05-03)

---

## 1. 앱 책임 요약

보험 GA 조직의 **업무요청 게시판(Post)**, **직원업무 게시판(Task)**, **개인 업무관리(WorkTask)**, **담보평가 계산기(Collateral)**, **업계정보 뉴스(Industry)** 다섯 도메인을 담당한다. 모든 도메인은 공용 서비스 레이어(`board/services/`)를 경유하며, 첨부파일 URL 직접 노출과 소유자 격리 우회는 구조적으로 차단되어 있다.

---

## 2. 디렉터리 구조

```
board/
├── models.py                       # Post, Task, 첨부/댓글, CollateralEval, WorkCategory, WorkTask, WorkTaskAttachment
├── models_industry.py              # IndustryArticle, IndustryUserPreference, IndustryRecommendation, IndustryCollectJobLog
├── urls.py                         # 5개 패턴 그룹 + worktask_urls include (namespace="board")
├── worktask_urls.py                # WorkTask 전용 URL (중첩 네임스페이스 board:worktasks)
├── policies.py                     # ⚠️ Post 조회/수정/첨부 권한 정책 SSOT
├── constants.py                    # BOARD_ALLOWED_GRADES, TASK_ALLOWED_GRADES, STATUS_CHOICES 등
├── constants_industry.py           # 업계정보 SOURCE_CHOICES, TOPIC_CHOICES
├── forms.py                        # PostForm, TaskForm, CommentForm, TaskCommentForm
├── admin.py                        # Post, WorkCategory, WorkTask, Industry* Admin 등록
├── apps.py                         # BoardConfig (signal 로딩)
├── signals.py                      # Django signal handlers
├── task.py                         # WorkTask Celery 태스크 (반복생성, 알림 이메일)
├── views/
│   ├── __init__.py                 # 뷰 re-export surface (urls.py 호환)
│   ├── posts.py                    # Post CRUD + 인라인 업데이트 (BOARD_ALLOWED_GRADES)
│   ├── tasks.py                    # Task CRUD + 인라인 업데이트 (superuser 전용)
│   ├── worktasks.py                # WorkTask CRUD + AJAX (superuser + 소유자 격리)
│   ├── forms.py                    # 서식/PDF 생성 + 사용자 검색 AJAX
│   ├── attachments.py              # ⚠️ Post/Task 첨부 보안 다운로드 뷰
│   ├── collateral.py               # 담보평가 계산/이력/삭제 (login_required)
│   └── industry_info.py            # 업계정보 목록/북마크/선호도 API
├── services/
│   ├── attachments.py              # ⚠️ validate_board_attachment, save_attachments, open_fileresponse_from_fieldfile
│   ├── comments.py                 # ⚠️ handle_comments_actions (Post/Task 댓글 공용)
│   ├── inline_update.py            # ⚠️ inline_update_common (Post/Task 인라인 업데이트 공용)
│   ├── listing.py                  # ⚠️ read_list_params, apply_keyword_filter, apply_common_list_filters, paginate
│   ├── worktasks.py                # ⚠️ WorkTask 비즈니스 로직 SSOT (소유자 격리 보장)
│   ├── collateral.py               # 담보평가 계산 로직
│   ├── industry_news.py            # 네이버 뉴스 API 수집/파싱
│   ├── industry_recommend.py       # 추천 알고리즘
│   └── rate_limit.py               # Redis 기반 API rate limiting (fail-open)
├── tasks/
│   ├── __init__.py                 # Celery 태스크 export
│   └── industry_info.py            # 업계정보 수집/정리 배치 태스크
├── templates/board/
│   ├── base_board.html             # ⚠️ board 전용 레이아웃 (board-scope 주입, CSS 로드)
│   ├── post_list.html
│   ├── post_detail.html
│   ├── post_create.html
│   ├── post_edit.html
│   ├── task_list.html
│   ├── task_detail.html
│   ├── task_create.html
│   ├── task_edit.html
│   ├── worktask_list.html
│   ├── worktask_detail.html
│   ├── worktask_create.html
│   ├── worktask_edit.html
│   ├── collateral.html
│   ├── industry_info.html
│   ├── support_form.html
│   ├── states_form.html
│   └── includes/                   # partial 템플릿
│       ├── _edit_form.html         # Post/Task 생성/수정 공용 폼
│       ├── _form_common.html       # 필드 + 첨부파일 UI
│       ├── _comment_list.html      # 댓글 목록
│       ├── _comment_form.html      # 댓글 입력 폼
│       ├── _inline_handler_status_list.html  # 목록 인라인 담당자/상태 셀
│       ├── _industry_article_card.html       # 기사 카드
│       ├── _industry_pagination.html
│       └── pagination.html         # 공용 페이지네이션
├── templatetags/
│   ├── board_filters.py            # basename 필터
│   ├── industry_tags.py            # get_item 필터
│   └── querystring.py              # qs_replace simple_tag
└── migrations/                     # 26개 마이그레이션
```

---

## 3. 모델 구조

### 3.1 Post (업무요청)

- **`receipt_number`**: `CharField(unique=True)` — `YYYYMMDD{seq:03d}` 형식, `save()` 내 동시성 안전 자동생성 (IntegrityError 재시도)
- **`category`**: 구분 (POST_CATEGORY_VALUES 내 값)
- **`fa` / `code`**: 대상자명 / 대상자 사번
- **`user_id` / `user_name` / `user_branch`**: 요청자 스냅샷 — FK 없음, 문자열 저장
- **`handler`**: 담당자 (CharField, 인라인 수정 가능)
- **`status`**: `choices=STATUS_CHOICES_TUPLES` (기본 `"확인중"`)
  - 선택지: `"확인중"`, `"진행중"`, `"보완요청"`, `"완료"`, `"반려"`
- **`status_updated_at`**: `DateTimeField` — `save()` 내 status 또는 handler 변경 시 자동 갱신
- **관계**: `Attachment`(1:N), `Comment`(1:N)
- **Meta**: 정렬 `-created_at`

### 3.2 Task (직원업무)

- Post와 구조 동일, `status` 선택지만 다름: `"시작전"`, `"진행중"`, `"보완필요"`, `"완료"`
- **관계**: `TaskAttachment`(1:N), `TaskComment`(1:N)

### 3.3 Attachment / TaskAttachment

- **`file`**: `FileField` — `file.url` 직접 노출 금지, 반드시 다운로드 뷰 경유
- **`original_name`**: RFC5987 한글 파일명 보존용
- **`post` / `task`**: FK (ON DELETE CASCADE)

### 3.4 Comment / TaskComment

- **`author`**: `ForeignKey(CustomUser)`
- **`content`**: `TextField(max_length=500)`
- **Meta**: 정렬 `-created_at`

### 3.5 CollateralEval (담보평가)

- **`requester`**: `ForeignKey(CustomUser)` — 계산 요청자
- **`target_user`**: `ForeignKey(CustomUser, null=True)` — 대상자 (선택)
- **`property_type`**: `"apt"` / `"villa_new"` / `"villa_old"` / `"house"` / `"land"` / `"etc"`
- **`kb_price`**: KB 시세(원)
- **`prior_debt`**: 기설정 채권최고액(원)
- **`lease_deposit`**: 임차보증금(원)
- **`apply_rate`**: `DecimalField` — 70 / 60 / 50 / 40 (property_type에 따라 constants.py `COLLATERAL_RATE_MAP`)
- **`max_collateral`**: `kb_price × apply_rate / 100 − prior_debt`
- **`source`**: `"manual"` | `"api"`
- **Meta**: 정렬 `-created_at`

### 3.6 WorkCategory (업무 분류 마스터)

- **`code`** (PK, CharField): `commission`, `bond`, `risk`, `biz_dev`, `misc` 등
- **`is_active`**: False이면 생성 폼에서 미노출
- **Meta**: 정렬 `(sort_order, code)`

### 3.7 WorkTask (개인 업무관리)

- **`owner`**: `ForeignKey(CustomUser, CASCADE, db_index=True)` — 소유자 격리 키
- **`category`**: `ForeignKey(WorkCategory, PROTECT)`
- **`title`**: `CharField(max_length=200)`
- **`related_users`**: `M2M(CustomUser, blank=True)` — 메모 전용, 권한 부여 아님
- **`family_branches`**: `JSONField` — 영업가족 지점명 목록
- **반복 상수** (`WorkTask.RECURRENCE_*`):

| 상수 | 값 | 설명 |
|------|----|------|
| `RECURRENCE_NONE` | `"none"` | 반복 없음 |
| `RECURRENCE_MONTHLY_OPEN` | `"monthly_open"` | 매달 월초 (1~10일) |
| `RECURRENCE_MONTHLY_MID` | `"monthly_mid"` | 매달 중순 |
| `RECURRENCE_MONTHLY_END` | `"monthly_end"` | 매달 말 |
| `RECURRENCE_DAILY` | `"daily"` | 매일 |
| `RECURRENCE_CUSTOM` | `"custom"` | 직접 지정 (`recurrence_day` 연동) |

- **`template_task`**: `ForeignKey(self, null=True)` — 배치 자동생성 자식 레코드의 원본 참조
- **`target_ym`**: `CharField` (YYYY-MM) — 귀속 월
- **`status`**: `"pending"` / `"in_progress"` / `"done"` / `"skipped"`
- **`priority`**: `"high"` / `"mid"` / `"low"`
- **`is_notified`**: 알림 발송 완료 플래그 (중복 방지)
- **주요 프로퍼티**:
  - `is_template`: `template_task_id is None AND recurrence_type != "none"`
  - `is_overdue`: `due_date < 오늘 AND status not in (done, skipped)`
- **인덱스**: `(owner, status, due_date)`, `(template_task, target_ym)`

### 3.8 WorkTaskAttachment

- **`task`**: `ForeignKey(WorkTask, CASCADE)`
- **`uploaded_by`**: `ForeignKey(CustomUser, null=True, SET_NULL)`
- **`file`**: `FileField(upload_to="worktask_attachments/%Y/%m/")` — 직접 URL 노출 금지

### 3.9 IndustryArticle

- **`normalized_hash`**: `CharField(unique=True)` — 콘텐츠 해시, 중복 수집 방지
- **`source_portal`**: `"naver"` / `"daum"` / `"google"` / `"direct"`
- **`is_active` / `is_hidden`**: 노출 제어 플래그
- **`raw_payload_json`**: API 원본 응답 보존
- **db_table**: `"board_industry_article"`

### 3.10 IndustryUserPreference

- **복합 키**: `UniqueConstraint(user, article)`
- **`dwell_seconds`**: 체류시간 (추천 알고리즘 입력)
- **db_table**: `"board_industry_user_preference"`

---

## 4. URL 네임스페이스 + 엔드포인트 전체 목록

**namespace**: `board`

### Post (업무요청)

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `post_list` | `/board/` | GET | HTML |
| `post_create` | `/board/posts/create/` | GET/POST | HTML |
| `post_detail` | `/board/posts/<pk>/` | GET/POST | HTML |
| `post_edit` | `/board/posts/<pk>/edit/` | GET/POST | HTML |
| `ajax_update_post_field` | `/board/ajax/update-post-field/` | POST | JSON |
| `ajax_update_post_field_detail` | `/board/ajax/posts/<pk>/update-field/` | POST | JSON |
| `post_attachment_download` | `/board/posts/attachments/<att_id>/download/` | GET | File |

### Support / States Form

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `support_form` | `/board/support_form/` | GET | HTML |
| `states_form` | `/board/states_form/` | GET | HTML |
| `generate_request_support` | `/board/generate-support/` | POST | PDF |
| `generate_request_states` | `/board/generate-states/` | POST | PDF |
| `search_user` | `/board/search-user/` | GET | JSON |

### Task (직원업무)

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `task_list` | `/board/tasks/` | GET | HTML |
| `task_create` | `/board/tasks/create/` | GET/POST | HTML |
| `task_detail` | `/board/tasks/<pk>/` | GET/POST | HTML |
| `task_edit` | `/board/tasks/<pk>/edit/` | GET/POST | HTML |
| `ajax_update_task_field` | `/board/ajax/tasks/update-task-field/` | POST | JSON |
| `ajax_update_task_field_detail` | `/board/ajax/tasks/<pk>/update-field/` | POST | JSON |
| `task_attachment_download` | `/board/tasks/attachments/<att_id>/download/` | GET | File |

### Collateral (담보평가)

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `collateral` | `/board/collateral/` | GET | HTML |
| `collateral_calc` | `/board/collateral/calc/` | POST | JSON |
| `collateral_delete` | `/board/collateral/<eval_id>/delete/` | POST | JSON |

### Industry Info (업계정보)

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `industry_info` | `/board/industry-info/` | GET | HTML |
| `industry_bookmarks` | `/board/industry-info/bookmarks/` | GET | HTML |
| `api_industry_preference` | `/board/api/industry/articles/<article_id>/preference/` | POST | JSON |
| `api_industry_click` | `/board/api/industry/articles/<article_id>/click/` | POST | JSON |

### WorkTask (개인 업무관리) — 중첩 네임스페이스 `board:worktasks`

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `worktask_list` | `/board/worktasks/` | GET | HTML |
| `worktask_create` | `/board/worktasks/create/` | GET/POST | HTML |
| `worktask_detail` | `/board/worktasks/<pk>/` | GET | HTML |
| `worktask_edit` | `/board/worktasks/<pk>/edit/` | GET/POST | HTML |
| `worktask_done` | `/board/worktasks/<pk>/done/` | POST | JSON |
| `worktask_skip` | `/board/worktasks/<pk>/skip/` | POST | JSON |
| `worktask_delete` | `/board/worktasks/<pk>/delete/` | POST | JSON |
| `worktask_reset` | `/board/worktasks/<pk>/reset/` | POST | JSON |
| `worktask_inline_update` | `/board/worktasks/<pk>/inline-update/` | POST | JSON |
| `worktask_att_download` | `/board/worktasks/attachments/<att_id>/download/` | GET | File |
| `worktask_notify_check` | `/board/worktasks/api/notify-check/` | GET | JSON |

> WorkTask URL 참조 시 `{% url 'board:worktasks:worktask_list' %}` 형태로 중첩 네임스페이스를 사용한다.

---

## 5. 권한 정책

### 도메인별 접근 등급

| 도메인 | 허용 등급 | 강제 위치 |
|--------|----------|----------|
| Post/Support/States 전체 | `BOARD_ALLOWED_GRADES` = `("superuser", "head", "leader")` | `@grade_required(*BOARD_ALLOWED_GRADES)` (views/posts.py, views/forms.py) |
| Task 전체 | `TASK_ALLOWED_GRADES` = `("superuser",)` | `@grade_required(*TASK_ALLOWED_GRADES)` (views/tasks.py) |
| WorkTask 전체 | `superuser` 전용 | `@grade_required("superuser")` (views/worktasks.py 모든 뷰) |
| Collateral 조회/계산 | 로그인 사용자 전체 | `@login_required` (views/collateral.py) |
| Collateral 삭제 | `superuser`, `head` | `views/collateral.py:164` 인라인 grade 검증 |
| Industry 전체 | 로그인 사용자 전체 | `@login_required` (views/industry_info.py) |

### Post 세부 조회/수정 정책 — `board/policies.py` ⚠️

모든 Post 권한 판단은 이 파일을 단일 진실 소스(SSOT)로 한다. 뷰에서 직접 grade를 비교하는 코드 추가 금지.

| 함수 | 정책 |
|------|------|
| `can_view_post(user, post)` | superuser → 전체 / 작성자(`user_id`) → 본인 글 / head → 본인 + 동일 `user_branch` / leader → 본인만 |
| `can_edit_post(user, post)` | superuser + 작성자만 수정 가능 |
| `can_download_post_attachment(user, att)` | `can_view_post` 결과와 동일 |
| `can_download_task_attachment(user, att)` | `superuser` 전용 |
| `can_access_support_form(user)` | `BOARD_ALLOWED_GRADES` + inactive 아님 |

> ⚠️ `is_post_author()`는 `user.emp_id → user.user_id → user.id` 순으로 폴백하여 `post.user_id`와 문자열 비교한다. CustomUser의 기본 키가 사번(문자열)인 점을 반영한 설계다.

### WorkTask 소유자 격리

- 모든 WorkTask 뷰는 `@grade_required("superuser")`이므로 superuser만 접근 가능
- 조회는 반드시 `services.worktasks.get_user_queryset(request.user)` 또는 `get_user_task(request.user, pk)` 경유
- 첨부 다운로드 `worktask_att_download`는 추가로 `att.task.owner_id == request.user.pk` 검증 → 불일치 시 403

> ⚠️ Django Admin의 `WorkTaskAdmin`은 소유자 격리 예외다. Admin에서는 모든 WorkTask를 볼 수 있다. 이는 의도된 관리자 전용 예외 정책이다.

---

## 6. 서비스/유틸 레이어 SSOT 목록

### board/policies.py ⚠️

Post 조회/수정/다운로드 권한의 유일한 진실 소스. 뷰에서 직접 grade/branch 비교 금지.

| 함수 | 역할 |
|------|------|
| `can_view_post(user, post)` | Post 조회 가능 여부 |
| `can_edit_post(user, post)` | Post 수정/삭제 가능 여부 |
| `can_download_post_attachment(user, att)` | Post 첨부 다운로드 가능 여부 |
| `can_download_task_attachment(user, att)` | Task 첨부 다운로드 가능 여부 |

### board/services/attachments.py ⚠️

첨부파일 처리의 진실 소스. 직접 `FileResponse(open(...))` 작성 금지.

| 함수 | 역할 |
|------|------|
| `validate_board_attachment(uploaded_file)` | 파일 확장자·크기 검증 (ValidationError 발생) |
| `save_attachments(*, files, create_func)` | 첨부 파일 일괄 검증 + DB 저장 |
| `open_fileresponse_from_fieldfile(fieldfile, *, original_name)` | RFC5987 헤더 포함 FileResponse 생성 |

### board/services/comments.py ⚠️

| 함수 | 역할 |
|------|------|
| `handle_comments_actions(request, obj, comment_model, fk_field, redirect_detail_name)` | Post/Task 댓글 CRUD 공용 처리 (action_type: comment/edit_comment/delete_comment) |

### board/services/inline_update.py ⚠️

| 함수 | 역할 |
|------|------|
| `inline_update_common(*, obj, action, value, allowed_status_values)` | Post/Task 인라인 handler/status 변경 공용 처리 |

### board/services/listing.py ⚠️

Post/Task 목록 페이지의 필터·검색·페이지네이션 공용 처리. 뷰에서 직접 QS 필터 작성 금지.

| 함수 | 역할 |
|------|------|
| `read_list_params(request)` | GET 파라미터 → `ListParams` 구조체 |
| `apply_keyword_filter(qs, keyword, search_type)` | title/content/user_name 검색 |
| `apply_common_list_filters(qs, params)` | status/handler/category/date 필터 적용 |
| `paginate(request, qs, default_per_page)` | Django Paginator 래퍼 |
| `build_query_string_without_page()` | 페이지네이션 링크용 query string 재구성 |
| `get_handlers(qs)` | 담당자 목록 (unique) |

### board/services/worktasks.py ⚠️

WorkTask 도메인 전체의 진실 소스. ORM 직접 접근 금지.

| 함수 | 역할 |
|------|------|
| `get_user_queryset(user)` | owner=user 필터링 (소유자 격리 SSOT) |
| `get_user_task(user, pk)` | owner 불일치 시 404 (소유자 격리 SSOT) |
| `apply_filters(qs, params)` | ym/status/category/keyword 필터 |
| `create_task(user, data)` | owner=user 강제 후 WorkTask 생성 |
| `update_task(task, data)` | 필드 업데이트 |
| `save_attachment(task, file, user)` | WorkTaskAttachment 저장 |
| `delete_attachment(att, user)` | 첨부 파일 삭제 |
| `mark_done(task)` | status → `"done"` |
| `mark_skipped(task)` | status → `"skipped"` |
| `mark_pending(task)` | status → `"pending"` (reset) |
| `generate_monthly_tasks(year, month)` | 반복 원본 → 해당 월 자식 생성 (중복 방지) |
| `get_pending_notify_tasks()` | 알림 발송 대상 task 조회 (select_related 포함) |

### board/services/rate_limit.py

| 함수 | 역할 |
|------|------|
| `check_rate_limit(key, limit, period)` | Redis 기반 고정 윈도우 rate limit 확인 (fail-open) |

---

## 7. 템플릿 구조

### 상속 관계

```
base.html
└── board/base_board.html          ({% block content_wrapper %} → <div class="board-scope">)
    ├── board/post_list.html        ({% block content %})
    ├── board/post_detail.html      ({% block content %})
    ├── board/post_create.html      ({% block content %})
    ├── board/post_edit.html        ({% block content %})
    ├── board/task_list.html        ({% block content %})
    ├── board/task_detail.html      ({% block content %})
    ├── board/task_create.html      ({% block content %})
    ├── board/task_edit.html        ({% block content %})
    ├── board/worktask_list.html    ({% block content %})
    ├── board/worktask_detail.html  ({% block content %})
    ├── board/worktask_create.html  ({% block content %})
    ├── board/worktask_edit.html    ({% block content %})
    ├── board/collateral.html       ({% block content %})
    └── board/industry_info.html    ({% block content %})
```

### base_board.html 역할 ⚠️

모든 board 페이지는 `base_board.html`을 반드시 거친다. 이 파일은:
1. `{% block content_wrapper %}`에서 `<div class="board-scope">` 래퍼를 주입한다 — CSS 스코프 보장
2. `{% block app_css %}`에서 `static/css/apps/board.css`를 로드한다

새 board 페이지 추가 시 `base.html`이 아닌 `board/base_board.html`을 extends해야 `.board-scope` 래퍼와 CSS가 자동 적용된다.

### Include 관계

| 호출 템플릿 | include | 역할 |
|------------|---------|------|
| post_create/edit | `includes/_edit_form.html` | Post 생성/수정 공용 폼 |
| task_create/edit | `includes/_edit_form.html` | Task 생성/수정 공용 폼 |
| `_edit_form.html` | `includes/_form_common.html` | 필드 + 첨부파일 UI |
| post_detail/task_detail | `includes/_comment_list.html` | 댓글 목록 |
| post_detail/task_detail | `includes/_comment_form.html` | 댓글 입력 |
| post_list/task_list | `includes/_inline_handler_status_list.html` | 인라인 담당자/상태 셀 |
| industry_info | `includes/_industry_article_card.html` | 기사 카드 |
| collateral/worktask | `components/search_user_modal.html` | 사용자 검색 모달 (공용) |

---

## 8. JS 부트 패턴

모든 board 페이지는 `class="d-none"` boot div를 통해 URL을 JS에 주입한다.

### 루트 요소 및 dataset 키

#### Post 목록 / Task 목록

| boot id | data-* 속성 | 값 |
|---------|-----------|-----|
| `postListBoot` | `data-update-url` | `{% url 'board:ajax_update_post_field' %}` |
| `taskListBoot` | `data-update-url` | `{% url 'board:ajax_update_task_field' %}` |

**BFCache 가드**: 미적용 (목록 페이지는 서버 렌더링)  
**JS 파일**: `board/post_list.js`, `board/common/inline_update.js`, `board/common/status_ui.js`

#### Post 상세 / Task 상세

| boot id | data-* 속성 | 값 |
|---------|-----------|-----|
| `postDetailBoot` | `data-update-url` | `{% url 'board:ajax_update_post_field_detail' pk %}` |
| `taskDetailBoot` | `data-update-url` | `{% url 'board:ajax_update_task_field_detail' pk %}` |

**JS 파일**: `board/post_detail.js`, `board/common/detail_inline_update.js`, `board/common/comment_edit.js`

#### Collateral (담보평가)

| boot id | data-* 속성 | 값 |
|---------|-----------|-----|
| `collateralBoot` | `data-calc-url` | `{% url 'board:collateral_calc' %}` |
| | `data-delete-base-url` | `"/board/collateral/"` (고정 prefix) |
| | `data-can-delete` | `"true"` / `"false"` (superuser/head 여부) |

**BFCache 가드**: 미적용  
**JS 파일**: `board/collateral.js` (DataTables, 모달 처리 포함)

#### Industry Info (업계정보)

| root id | data-* 속성 | 값 |
|---------|-----------|-----|
| `industryInfoRoot` | `data-preference-url-template` | `{% url 'board:api_industry_preference' 0 %}` (0=placeholder) |
| | `data-click-url-template` | `{% url 'board:api_industry_click' 0 %}` |
| | `data-bookmarked-only` | `"1"` / `"0"` |

**초기 데이터 주입** (inline `<script>`):
```html
<script>
  window.industryPrefMap = { "article_id": {rating: ..., is_bookmarked: ..., is_hidden: ...} };
</script>
```

**BFCache 가드**: 미적용  
**JS 파일**: `board/industry_info.js`

#### WorkTask 목록

| boot id | data-* 속성 | 값 |
|---------|-----------|-----|
| `worktaskListBoot` | `data-delete-url` | `{% url 'board:worktasks:worktask_delete' 0 %}` (0=pk placeholder) |
| | `data-inline-url` | `{% url 'board:worktasks:worktask_inline_update' 0 %}` |

**JSON 옵션 주입** (script 태그):
```html
<script id="worktask-category-options" type="application/json">[...]</script>
<script id="worktask-status-options" type="application/json">[...]</script>
```

**테이블 행/셀 data-*** (인라인 수정 계약, 변경 금지):
```html
<tr class="worktask-row" data-pk="{{ task.pk }}" data-status="{{ task.status }}">
  <td class="worktask-cell-edit"
      data-field="category|priority|start_date|due_date|status"
      data-value="..."
      data-pk="{{ task.pk }}">
```

**BFCache 가드**: 미적용  
**JS 파일**: `board/worktask_list.js`

#### WorkTask 상세

| boot id | data-* 속성 | 값 |
|---------|-----------|-----|
| `worktaskDetailBoot` | `data-pk` | `{{ task.pk }}` |
| | `data-done-url` | `{% url 'board:worktasks:worktask_done' task.pk %}` |
| | `data-skip-url` | `{% url 'board:worktasks:worktask_skip' task.pk %}` |

**JS 파일**: `board/worktask_detail.js`

---

## 9. CSS 스코프 규약

- **파일**: `static/css/apps/board.css`
- **스코프 루트**: `.board-scope` — `base_board.html`이 주입하는 최상위 래퍼
- **원칙**: 모든 board CSS 규칙은 `.board-scope` 하위로 스코핑. `base.css` 수정 금지.
- **CSS 변수** (`.board-scope` 내):
  - `--board-narrow-max: 700px`
  - `--board-wide-max: 1600px`

### 주요 스코프별 클래스

| 영역 | 스코프 클래스 | 대표 하위 클래스 |
|------|-------------|-----------------|
| Post/Task 테이블 | `.board-post-table` | `.board-col-title`, `.board-col-channel` 등 |
| 인라인 업데이트 셀 | `.board-inline-cell` | `.board-inline-handler`, `.board-inline-status` |
| 상태 배지 | `.status-badge[data-status="..."]` | 한글 상태값 기반 색상 |
| 댓글 | `.board-comment-card` | `.board-comment-item`, `.comment-content` |
| 첨부파일 | `.board-filebox` | `.board-file-link` |
| 담보평가 | `.collateral-form-grid` | `#evalHistoryTable` |
| 업계정보 | `.industry-article-card` | `.js-rate-btn`, `.js-bookmark-btn` |
| WorkTask 테이블 | `.worktask-table` | `.worktask-row`, `.worktask-overdue`, `.worktask-done` |
| WorkTask 배지 | `.worktask-category-badge[data-category]` | `.status-badge[data-status="pending|done|..."]` |
| WorkTask 우선순위 | `.worktask-priority-badge[data-priority]` | `high=빨강`, `mid=노랑`, `low=파랑` |

> ⚠️ Post/Task의 `[data-status]`는 한글값 (`"접수"`, `"진행중"` 등), WorkTask의 `[data-status]`는 영문값 (`"pending"`, `"done"` 등)이다. 동일 선택자명이지만 값 체계가 다르다.

---

## 10. 절대 수정 금지 목록

| 파일/요소 | 금지 이유 |
|-----------|----------|
| `board/policies.py` 전체 | Post 조회/수정/다운로드 권한의 SSOT — 수정 시 head 사용자의 타 지점 데이터 열람 또는 작성자 본인 글 접근 불가 보안 사고 발생 |
| `board/services/attachments.py:open_fileresponse_from_fieldfile()` | RFC5987 한글 파일명 헤더 처리 로직 — 직접 `FileResponse(open(...))` 작성 시 한글 파일명 깨짐 또는 경로 탈출 위험 |
| `board/services/worktasks.py:get_user_queryset()` / `get_user_task()` | 소유자 격리의 유일한 구현체 — 우회 시 A사용자가 B사용자의 업무를 열람/수정하는 권한 상승 발생 |
| `Post.receipt_number` 생성 로직 (`models.py:save()`) | 동시성 안전한 YYYYMMDD+seq 생성 — IntegrityError 재시도 포함, 직접 생성 시 중복 발생 |
| `base_board.html:block content_wrapper` 내 `.board-scope` | 제거 시 `board.css` 전체 스코프 깨짐 — 스타일이 다른 앱에 누출됨 |
| `worktask_urls.py` 중첩 네임스페이스 `board:worktasks` | 기존 `board:` 네임스페이스와 병존 구조 — 변경 시 모든 `{% url 'board:worktasks:...' %}` 참조가 깨짐 |
| `WorkTask.RECURRENCE_*` 상수 값 | Celery `generate_monthly_worktasks` 태스크가 이 값으로 분기 — 변경 시 DB 기존 레코드와 불일치, 반복 생성 중단 |
| `worktask_att_download` 내 `att.task.owner_id == request.user.pk` 검증 | 제거 시 superuser가 타인 첨부를 다운로드할 수 있는 권한 상승 — WorkTask 소유자 격리의 최후 방어선 |
| `IndustryArticle.normalized_hash` (unique) | 중복 수집 방지 키 — 제거 시 동일 기사가 무한 재수집됨 |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 의존 대상 | 위치 | 용도 |
|-----------|------|------|
| `grade_required` 데코레이터 | `accounts/decorators.py` | 모든 뷰 등급 기반 권한 강제 |
| `CustomUser` 모델 | `accounts/models.py` | Post/Task/WorkTask author, Comment.author 등 FK |
| `accounts/search_api.py` (search_user) | `board/views/forms.py:search_user()` | 서식 폼/워크태스크 대상자 검색 |
| `audit.constants.ACTION` | `audit/constants.py` | Post 생성/수정/인라인 업데이트 감사 상수 |
| `audit.services.log_action` | `audit/services.py` | Post CRUD 감사 로그 기록 (`views/posts.py`) |
| Django `cache` framework | `services/rate_limit.py` | Redis rate limiting, Celery 태스크 락 |
| `components/search_user_modal.html` | `templates/components/` | 담보평가·WorkTask 사용자 검색 모달 |

### 다른 앱이 이 앱에 의존하는 관계

현재 다른 앱이 `board` 모델 또는 서비스를 직접 import하지 않는다. `board`는 독립 도메인이다.

---

## 12. 신규 기능 추가 패턴

### 패턴 A: Post/Task에 새 필드 + 인라인 수정 추가

1. `board/models.py` 필드 추가 + migration 생성
2. `board/constants.py`에 허용값 상수 추가 (있으면)
3. `board/services/inline_update.py:inline_update_common()` 내 `action` 분기 추가
4. `board/templates/board/includes/_inline_handler_status_list.html`에 셀 추가
5. `board/static/js/board/common/inline_update.js`에 action 처리 추가

### 패턴 B: 새 WorkTask 상태/액션 추가

1. `WorkTask` 모델 STATUS_CHOICES 업데이트 + migration
2. `board/services/worktasks.py`에 `mark_<new_status>(task)` 함수 추가
3. `board/views/worktasks.py`에 `@grade_required("superuser")` + `@require_POST` 뷰 추가
4. `board/worktask_urls.py`에 URL 추가
5. `board/templates/board/worktask_detail.html`의 `#worktaskDetailBoot`에 `data-<new>-url` 추가
6. `board/static/js/board/worktask_detail.js`에 처리 추가
7. `board/static/css/apps/board.css`에 새 상태 배지 색상 추가 (`[data-status="<new>"]`)

### 패턴 C: 새 반복 유형 추가

1. `WorkTask.RECURRENCE_*` 상수 추가 + `RECURRENCE_CHOICES` 업데이트
2. migration 생성
3. `board/services/worktasks.py:generate_monthly_tasks()` 내 반복 유형 분기 추가
4. `board/task.py:generate_monthly_worktasks` Celery 태스크가 `generate_monthly_tasks()`를 호출하므로 자동 반영
5. `board/templates/board/worktask_create.html` 폼 select 옵션 추가
6. `board/static/js/board/worktask_form.js` recurrence 토글 로직 업데이트

### 패턴 D: 새 board 도메인 페이지 추가

1. `board/views/` 하위 새 모듈 파일 생성 (`views/<domain>.py`)
2. `board/views/__init__.py`에 re-export 추가
3. `board/urls.py`에 URL 패턴 그룹 추가
4. `board/templates/board/<page>.html` 생성 (`{% extends 'board/base_board.html' %}` 필수)
5. `static/js/board/<page>.js` 생성 (boot div 패턴 준수)
6. `static/css/apps/board.css`에 `.board-scope` 하위로 스코핑하여 스타일 추가

### 패턴 E: 새 Celery 알림/배치 태스크 추가

1. `board/task.py`에 `@shared_task(name="board.tasks.<name>")` 등록
2. `web_ma/celery.py`의 `beat_schedule`에 등록 (task 이름이 정확히 일치해야 함)
3. `board/tasks/__init__.py`에 re-export 추가 (industry_info 패턴 참조)

---

## 13. LLM 함정 포인트

### ① Post 조회 권한은 "게시판 접근 권한"과 다르다

**함정**: `BOARD_ALLOWED_GRADES = ("superuser", "head", "leader")`이면 세 등급 모두 모든 Post를 볼 수 있다고 가정한다.  
**실제 설계**: 게시판 접근은 세 등급 모두 가능하지만, **개별 Post 조회**는 `policies.py:can_view_post()`를 통과해야 한다. leader는 본인 글만, head는 본인 + 동일 지점 글만 볼 수 있다.

### ② WorkTask는 superuser만 사용하지만, 그 superuser도 본인 업무만 볼 수 있다

**함정**: superuser는 모든 데이터를 볼 수 있다고 가정한다.  
**실제 설계**: `views/worktasks.py`는 `@grade_required("superuser")`만 통과시키지만, 내부에서 `get_user_queryset(request.user)`로 owner 필터를 강제 적용한다. superuser도 자신 소유 WorkTask만 볼 수 있다. (Admin은 예외)

### ③ Post.user_id는 CustomUser FK가 아닌 CharField 스냅샷이다

**함정**: `post.user_id`로 `CustomUser.objects.get(id=post.user_id)`를 시도한다.  
**실제 설계**: `user_id`, `user_name`, `user_branch`는 모두 `CharField` 스냅샷이다. 작성자 비교는 `policies.py:is_post_author()`를 사용해야 한다 — `str(user.id) == str(post.user_id)` 형태의 문자열 비교.

### ④ WorkTask URL은 `board:worktasks:worktask_list` 형태의 중첩 네임스페이스다

**함정**: `{% url 'board:worktask_list' %}`로 참조한다.  
**실제 설계**: `board/worktask_urls.py`는 `board:worktasks` 중첩 네임스페이스로 포함된다. 반드시 `{% url 'board:worktasks:worktask_list' %}` 형태를 사용해야 한다.

### ⑤ `base_board.html`은 `{% block content %}`가 아닌 `{% block content_wrapper %}`를 사용한다

**함정**: 다른 앱처럼 `{% block content %}`에 내용을 쓴다.  
**실제 설계**: `base_board.html`이 `{% block content_wrapper %}` 내에 `<div class="board-scope">...</div>` 래퍼를 삽입한다. 하위 페이지 템플릿은 `{% block content %}`를 override하여 `.board-scope` 내부에 내용을 작성한다.

### ⑥ 첨부 다운로드는 절대 `file.url`을 직접 노출하면 안 된다

**함정**: `<a href="{{ att.file.url }}">` 링크를 템플릿에 추가한다.  
**실제 설계**: CLAUDE.md 보안 규칙 2번. Post 첨부는 `board:post_attachment_download`, Task 첨부는 `board:task_attachment_download`, WorkTask 첨부는 `board:worktasks:worktask_att_download`를 경유해야 한다. 다운로드 뷰는 권한 검증 후 `open_fileresponse_from_fieldfile()`로 응답한다.

### ⑦ `generate_monthly_worktasks` 태스크의 등록명은 `board/task.py`에 있고 `board/tasks/__init__.py`와 다르다

**함정**: `board/tasks/__init__.py`에 태스크를 정의한다고 가정한다.  
**실제 설계**: WorkTask용 Celery 태스크 2개(`generate_monthly_worktasks`, `notify_due_worktasks`)는 `board/task.py`(복수형 없는 파일명)에 정의된다. 업계정보 태스크는 `board/tasks/` 패키지에 있다. beat_schedule의 `"task"` 이름이 `@shared_task(name=...)` 값과 정확히 일치해야 한다.

### ⑧ Post/Task 인라인 업데이트 form은 두 가지 경로가 있다

**함정**: 목록과 상세 페이지가 동일 엔드포인트를 사용한다고 가정한다.  
**실제 설계**: 목록 페이지 → `ajax_update_post_field` (pk를 POST body로 전달), 상세 페이지 → `ajax_update_post_field_detail` (pk를 URL 경로로 전달). 서로 다른 URL name을 사용한다.

---

## 14. 회귀 위험 체크리스트

### Post/Task 권한

- [ ] 새 뷰에서 Post 개별 접근 시 `policies.can_view_post(request.user, post)` 통과 여부를 검증하는가?
- [ ] 수정/삭제 전 `policies.can_edit_post(request.user, post)` 검증하는가?
- [ ] 첨부 다운로드가 `open_fileresponse_from_fieldfile()`을 경유하는가?
- [ ] `task_attachment_download`가 superuser 전용임을 확인했는가?

### WorkTask 소유자 격리

- [ ] 새 WorkTask 뷰에 `@grade_required("superuser")` 적용했는가?
- [ ] 모든 QS 조회가 `get_user_queryset(request.user)` 또는 `get_user_task(request.user, pk)` 경유인가?
- [ ] `worktask_att_download` 내 `att.task.owner_id == request.user.pk` 검증이 유지되는가?
- [ ] `related_users` M2M이 열람 권한이 아닌 순수 메모용임을 코드에서 오용하지 않는가?

### Celery 태스크

- [ ] `beat_schedule`의 `"task"` 값이 `@shared_task(name=...)` 등록명과 정확히 일치하는가?
- [ ] `generate_monthly_worktasks` 실행 후 동일 `(template_task, target_ym)` 조합의 자식이 중복 생성되지 않는가?
- [ ] `notify_due_worktasks` 발송 후 `is_notified=True` 갱신되어 재발송 방지가 동작하는가?
- [ ] 업계정보 수집 태스크 lock (`cache.add()`)이 있어 중복 실행이 방지되는가?

### 템플릿/CSS

- [ ] 새 board 페이지가 `board/base_board.html`을 extends하여 `.board-scope` 래퍼가 자동 적용되는가?
- [ ] `board.css`에 추가한 규칙이 `.board-scope` 하위로 스코핑되어 있는가?
- [ ] Post의 `[data-status]`는 한글값, WorkTask의 `[data-status]`는 영문값임을 CSS/JS에서 혼용하지 않는가?
- [ ] 새 boot div의 `data-*-url` 속성이 `{% url %}` 태그로 주입되고 JS 하드코딩이 없는가?

### 모델/마이그레이션

- [ ] `WorkTask.RECURRENCE_*` 상수 추가 시 `generate_monthly_tasks()` 분기도 업데이트했는가?
- [ ] `Post.receipt_number` 자동생성 로직 변경 시 동시성 안전(재시도) 코드가 유지되는가?
- [ ] `IndustryArticle.normalized_hash` unique 제약이 마이그레이션에서 유지되는가?
