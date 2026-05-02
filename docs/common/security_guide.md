# 보안 가이드 (Security Guide)

> 이 문서는 `accounts/decorators.py`, `accounts/search_api.py`,
> `board/views/attachments.py`, `board/services/attachments.py`,
> `manual/utils/permissions.py`, `accounts/middleware/force_password_change.py`
> 의 실제 코드를 기준으로 작성된 SSOT다.
>
> 새 기능 구현 전 이 문서를 먼저 읽고, 구현 후 14항 체크리스트를 실행한다.

---

## 1. Grade 등급 체계

### 등급 정의 (SSOT: `accounts/models.py` `GRADE_CHOICES`)

| grade | 설명 | `is_active` | 로그인 | 비고 |
|---|---|---|---|---|
| `superuser` | 시스템 최고 관리자 | True | 가능 | Django Admin 접근 가능 |
| `head` | 파트너별 최상위 관리자 | True | 가능 | 본인 지점 전체 조회 가능 |
| `leader` | 파트너별 중간 관리자 | True | 가능 | 팀 범위 조회 (SubAdminTemp 기반) |
| `basic` | 일반 사용자(설계사) | True | 가능 | 자신만 조회 가능 |
| `resign` | 퇴사자 | True | 가능 | 기능 제한, 자신만 조회 가능 |
| `inactive` | 비활성 | **False (자동)** | **불가** | `save()` 시 `is_active=False` 강제 |

### Grade별 접근 가능 범위 요약

| 기능 | superuser | head | leader | basic | resign | inactive |
|---|---|---|---|---|---|---|
| 사용자 검색 | 전체 / 지점 필터 | 본인 지점만 | 팀 범위 | 자신만 | 자신만 | 자신만 (로그인 불가) |
| Board 게시물 조회 | 전체 | 본인 글 + 지점 글 | 본인 글만 | 본인 글만 | 본인 글만 | 차단 |
| 첨부 다운로드 (Post) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 첨부 다운로드 (Task) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manual 관리자 전용(`admin_only=True`) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manual 비공개(`is_published=False`) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Django Admin | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 운영 정책

- `grade="inactive"` 저장 시 `CustomUser.save()` 오버라이드가 `is_active=False`를 **자동 강제**한다.  
- ⚠️ `CustomUser.objects.filter(...).update(grade="inactive")` 는 `save()`를 우회하므로 `is_active`가 동기화되지 않는다. 반드시 인스턴스 경유 `user.save()` 를 사용한다.

---

## 2. `grade_required` 데코레이터 사용 규약

**위치:** `accounts/decorators.py`

### 올바른 사용 패턴

```python
from accounts.decorators import grade_required

# 단일 grade
@grade_required("head")

# 복수 grade
@grade_required("head", "leader")

# 리스트 형태 (레거시 코드와의 호환)
@grade_required(["superuser", "head"])

# JSON API — 403 반환 (팝업 템플릿 없이)
@grade_required("superuser", forbidden_template=None)
@grade_required("superuser", forbidden_template="")
```

### 동작 원리

```python
def grade_required(*allowed_grades, forbidden_template="no_permission_popup.html"):
    ...
    def _wrapped_view(request, *args, **kwargs):
        user_grade = getattr(request.user, "grade", None)
        if user_grade not in allowed_set:
            if forbidden_template:
                return render(request, forbidden_template)   # 팝업 템플릿 렌더
            return HttpResponseForbidden("권한이 없습니다.")  # 403
        return view_func(request, *args, **kwargs)
```

- 내부적으로 `@login_required`가 먼저 적용된다 (로그인 안 된 사용자 → 로그인 페이지 리다이렉트).
- `forbidden_template` 기본값은 `"no_permission_popup.html"` — HTML 응답이므로 AJAX 뷰에는 `forbidden_template=None` 필수.

### `GRADE_ALIAS_MAP`

```python
# accounts/decorators.py
GRADE_ALIAS_MAP = {}  # 레거시 grade(main_admin/sub_admin) 전환 완료. 현재 빈 상태.
```

- `main_admin`, `sub_admin`은 운영에서 제거된 레거시 값이다. 코드에서 이 문자열을 사용하면 안 된다.
- alias 확장이 필요하면 `GRADE_ALIAS_MAP`에만 추가하고 `grade_required` 호출부는 건드리지 않는다.

### `not_inactive_required` 데코레이터

```python
from accounts.decorators import not_inactive_required

@not_inactive_required  # inactive grade 사용자 차단, no_permission_popup.html 렌더
def my_view(request): ...
```

- `grade_required`와 달리 특정 등급만 허용하는 게 아니라 `inactive`만 차단한다.
- 로그인 사용자면 모두 허용하되, 퇴사·비활성 계정만 걸러야 할 때 사용한다.

---

## 3. 파일 다운로드 보안 정책 SSOT

**SSOT:** `board/services/attachments.py`  
**적용 뷰:** `board/views/attachments.py`

### 핵심 원칙: 첨부 URL 직접 노출 금지

```
❌ 금지 패턴
<a href="{{ att.file.url }}">다운로드</a>

✅ 올바른 패턴
<a href="{% url 'board:post_attachment_download' att.id %}">다운로드</a>
<a href="{% url 'board:task_attachment_download' att.id %}">다운로드</a>
```

**금지 이유:** `att.file.url`은 미디어 파일 경로를 직접 노출한다.  
이 URL을 알면 인증·권한 검사 없이 누구든 파일에 접근할 수 있다.  
다운로드 뷰를 경유해야만 `@login_required` + `@grade_required` + `can_download_*()` 정책이 적용된다.

### 다운로드 뷰 패턴 (board 기준)

```python
# board/views/attachments.py
@login_required
@grade_required(*BOARD_ALLOWED_GRADES)          # 1단계: grade 검사
def post_attachment_download(request, att_id):
    att = get_object_or_404(Attachment, id=att_id)
    if not can_download_post_attachment(request.user, att):   # 2단계: 정책 검사
        _log_attachment_download(request, att, kind="post", success=False, reason="permission_denied")
        return redirect(POST_LIST)
    
    response = _open_download_or_404(att)                     # 3단계: FileResponse 생성
    _log_attachment_download(request, att, kind="post", success=True)
    return response
```

**3단계 필수:** grade 검사 → 정책 검사 → FileResponse 생성. 하나라도 생략하면 보안 구멍이다.

### `open_fileresponse_from_fieldfile()` — FileResponse SSOT

```python
# board/services/attachments.py
from board.services.attachments import open_fileresponse_from_fieldfile

response = open_fileresponse_from_fieldfile(att.file, original_name=att.original_name or "")
```

이 함수가 처리하는 것:
- `fieldfile.path` 기반 실제 파일 존재 확인 (없으면 `Http404`)
- `File(f)` wrapper로 파일 핸들 close 보장
- `Content-Disposition` RFC 5987 (`filename*=UTF-8''...`) 한글 파일명 호환
- `_normalize_download_filename()` — Windows 금지문자·예약어(`CON`, `NUL`, `COM1`…)·길이 제한 처리

⚠️ **`open(file_path, "rb")`를 직접 호출해서 `FileResponse`를 만들면 안 된다.** 파일명 정규화, 핸들 close 보장이 빠진다.

### 업로드 검증 SSOT

```python
# board/services/attachments.py
from board.services.attachments import save_attachments

save_attachments(
    files=request.FILES.getlist("attachments"),
    create_func=lambda **kw: Attachment.objects.create(post=post, **kw),
)
```

`save_attachments()`가 내부적으로 `validate_board_attachment()`를 호출한다.  
검증 항목: 파일명 존재, 크기(기본 10MB), 확장자 허용 목록, Content-Type 허용 목록.

**허용 확장자 (기본값):**
`.pdf`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.txt`, `.csv`,
`.xls`, `.xlsx`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.hwp`, `.hwpx`

오버라이드: `settings.BOARD_ATTACHMENT_ALLOWED_EXTENSIONS`, `settings.BOARD_ATTACHMENT_ALLOWED_CONTENT_TYPES`

⚠️ **업로드 시 서버단 검증 없이 `Attachment.objects.create(file=f)`를 직접 호출하면 안 된다.**  
반드시 `save_attachments()` 또는 `validate_board_attachment(f)`를 경유한다.

---

## 4. 사용자 검색 권한 범위 정책

**SSOT:** `accounts/search_api.py`의 `search_users_for_api(request)`

### Grade별 검색 가능 범위

| grade | 검색 가능 범위 | 조건 |
|---|---|---|
| `superuser` | 전체 사용자 | 기본. `scope=branch` + `branch` 파라미터 있으면 해당 지점만 |
| `head` | `user.branch`와 동일한 지점의 사용자만 | 항상 지점 고정 |
| `leader` | `scope=branch`이면 `user.branch` / 아니면 SubAdminTemp 팀 기준 | 팀A/B/C 레벨에 따라 다름 |
| `basic` | 자기 자신만 (`id=user.id`) | |
| `resign` | 자기 자신만 (`id=user.id`) | |
| 기타 (미정의) | `qs.none()` — 결과 없음 | |

### leader의 팀 범위 상세

```python
# accounts/search_api.py _apply_permission_scope()
if level == "A레벨" and team_a:
    return qs.filter(subadmin_detail__team_a=team_a)
if level == "B레벨" and team_b:
    return qs.filter(subadmin_detail__team_b=team_b)
if level == "C레벨" and team_c:
    return qs.filter(subadmin_detail__team_c=team_c)
# SubAdminTemp 없거나 팀 미정 시 → 지점 전체
return qs.filter(branch=p.user_branch)
```

팀 레벨 정보는 `partner.models.SubAdminTemp`에서 읽는다.

### `search_users_for_api()` 경유 필수 이유

```python
# ❌ 금지 — 권한 스코프 없이 전체 조회
CustomUser.objects.filter(name__icontains=q)

# ✅ 올바른 방법 1: 뷰에서 API 경유
# accounts/views.py → api_search_user → search_users_for_api(request)

# ✅ 올바른 방법 2: 다른 앱 서버사이드에서 직접 import
from accounts.search_api import search_users_for_api
result = search_users_for_api(request)
```

- `search_users_for_api(request)` 는 반드시 `request` 객체를 받아야 한다. `request.user.grade`와 `request.user.branch`로 스코프를 결정하기 때문이다.
- 결과 한도: 최대 50건(`RESULT_LIMIT = 50`). 키워드 없으면 빈 결과 반환 (전체 목록 조회 방지).
- 프론트에서 결과를 추가 필터링하는 것은 허용하나, **서버 결과보다 더 많은 사용자를 노출하는 클라이언트 로직은 금지**한다.

### 검색 파라미터 (GET)

| 파라미터 | 설명 | 비고 |
|---|---|---|
| `q` | 검색 키워드 | name, regist, channel, division, part, branch, id 검색 |
| `scope` | `"branch"` 고정 시 지점 필터 강화 | superuser/leader에게만 효과 있음 |
| `branch` | 특정 지점명 | superuser + scope=branch 조합에서만 사용 |

---

## 5. 미들웨어 동작 정책

**SSOT:** `accounts/middleware/force_password_change.py` + `accounts/policies/password_policy.py`

### Phase 3: 강제 비밀번호 변경 미들웨어

**설정 위치:** `settings.MIDDLEWARE` — `ForcePasswordChangeMiddleware`

**강제 리다이렉트 조건 (`should_enforce(user)` → `True` 판정):**

1. `settings.FORCE_PASSWORD_CHANGE_ENABLED == True`
2. `user.is_authenticated == True`
3. `user.must_change_password == True`
4. `user.grade` ∉ `settings.FORCE_PASSWORD_CHANGE_EXEMPT_GRADES`
5. 스코프 판정에서 `allow=True` AND `deny=False`

**→ 모두 만족 시 `accounts:password_change`로 리다이렉트.**

### 미들웨어 Bypass 예외 목록

다음 경로는 `should_enforce()`를 호출하지 않고 무조건 통과한다:

| 조건 | 예외 경로/이름 |
|---|---|
| Prefix bypass | `/static/*`, `/media/*`, `/favicon.ico`, `/robots.txt` |
| URL name whitelist | `settings.FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES` (콤마 구분 문자열) |
| 비인증 사용자 | `user.is_authenticated == False` |
| URL resolve 실패 | `Resolver404` — 강제하지 않음 (안전 우선) |
| 정책 엔진 예외 | `should_enforce()` 내부 예외 — 강제하지 않음 (장애 방어) |

### 기본 Whitelist (SSOT: `settings.py`)

```
FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES = "login,logout,accounts:password_change,accounts:password_change_done"
```

⚠️ 신규 URL을 whitelist에 추가하면 강제 비번 변경 우회 경로가 된다.  
추가 전 "이 URL이 비번 변경 없이 접근되어도 되는가?"를 반드시 검토한다.  
`.env.dev`와 `.env.prod` 양쪽 모두 업데이트해야 한다.

### 스코프 판정 규칙 (deny-first)

```
우선순위: branch > part > channel

deny 목록 (FORCE_PASSWORD_CHANGE_DENY_BRANCHES/PARTS/CHANNELS)에 해당하면 → 강제 안 함
allow 목록 (FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES/PARTS/CHANNELS)에 해당하면 → 강제함
allow 목록 전부 비어있으면 → 강제 안 함 (점진 적용 안전 기본값)
```

### `must_change_password` 플래그 설정 경위

| 경우 | 설정 위치 |
|---|---|
| 기본 비밀번호(사번 또는 `incar`+사번) 로그인 감지 | `accounts/views.py` `SessionCloseLoginView.form_valid()` |
| Admin에서 비밀번호 초기화 | `accounts/admin.py` `reset_password_and_unlock_accounts` action |
| Excel 업로드로 신규 계정 생성 | `accounts/tasks.py` `process_users_excel_task` — 생성 시 `True` 자동 설정 |

---

## 6. 감사(Audit) 로그 대상 행위 목록

**SSOT:** `audit/constants.py` `ACTION` 클래스  
**호출:** `from audit.services import log_action`

### 반드시 Audit 로그를 남겨야 하는 행위

#### 인증 관련

| `ACTION` 상수 | 이벤트 |
|---|---|
| `AUTH_LOGIN_SUCCESS` | 로그인 성공 |
| `AUTH_LOGIN_FAIL` | 로그인 실패 (잘못된 비밀번호) |
| `AUTH_LOGIN_LOCKED` | 로그인 실패 → 계정 자동 잠금 |
| `AUTH_LOGIN_BLOCKED_LOCKED` | 잠긴 계정으로 로그인 시도 |
| `AUTH_LOGOUT` | 로그아웃 |

#### 계정 관리

| `ACTION` 상수 | 이벤트 |
|---|---|
| `ACCOUNTS_EXCEL_UPLOAD` | 사용자 Excel 업로드 |
| `ACCOUNTS_LEVEL_UPDATE` | 팀 레벨 변경 |
| `ACCOUNTS_GRADE_UPDATE` | 권한 등급 변경 |
| `ACCOUNTS_PASSWORD_RESET_UNLOCK` | 관리자가 비밀번호 초기화 + 잠금 해제 |
| `ACCOUNTS_PASSWORD_CHANGE_COMPLETED` | 사용자가 비밀번호 변경 완료 |
| `ACCOUNTS_PASSWORD_CHANGE_CLEARED` | 강제 변경 플래그 해제 (비상 동선) |

#### 첨부파일

| `ACTION` 상수 | 이벤트 |
|---|---|
| `BOARD_ATTACHMENT_UPLOAD` | Post 첨부 업로드 |
| `BOARD_ATTACHMENT_DELETE` | Post 첨부 삭제 |
| `BOARD_ATTACHMENT_DOWNLOAD` | Post 첨부 다운로드 (성공/실패 모두) |
| `TASK_ATTACHMENT_DOWNLOAD` | Task 첨부 다운로드 (성공/실패 모두) |
| `MANUAL_ATTACHMENT_UPLOAD` | Manual 첨부 업로드 |
| `MANUAL_ATTACHMENT_DELETE` | Manual 첨부 삭제 |
| `MANUAL_ATTACHMENT_DOWNLOAD` | Manual 첨부 다운로드 |

#### Board / Manual / Partner

| 카테고리 | 대상 행위 |
|---|---|
| Board | Post/Task 생성·수정·삭제, 상태/담당자/인라인 변경, 댓글 생성·수정·삭제 |
| Manual | Manual/Section/Block 생성·수정·삭제·순서변경, PDF 생성 |
| Partner | 수수료율·조직구조·효율 저장/삭제, 리더 추가/삭제, 전자서명 |
| Commission | Excel 업로드 (입금/승인/효율) |

### `log_action()` 호출 규약

```python
from audit.services import log_action
from audit.constants import ACTION

log_action(
    request,
    ACTION.BOARD_ATTACHMENT_DOWNLOAD,
    obj=att,                          # 감사 대상 객체 (선택)
    meta={"kind": "post", "att_id": att.id},  # 부가 정보 (선택)
    success=True,                     # 성공 여부
    reason="permission_denied",       # 실패 원인 (실패 시 필수)
)
```

- `log_action()` 실패가 사용자 동작을 막으면 안 된다. `try/except` 감싸기 필수 (board의 `_log_attachment_download()` 패턴 참고).
- **신규 ACTION 추가 시 `audit/constants.py`에만 추가하고, 문자열 값은 `"domain.object.action"` 형식**으로 유지한다 (예: `"board.post.create"`).

---

## 7. LLM이 자주 저지르는 보안 실수 패턴

### 7-1. ⚠️ 권한 완화로 임시 해결

```python
# ❌ 금지: "일단 돌아가게" 목적의 grade 완화
@grade_required("basic")   # 원래 "head"여야 하는 뷰를 basic으로 낮춤
def sensitive_view(request): ...

# ❌ 금지: 데코레이터 제거
# @grade_required("superuser")  ← 주석 처리
@login_required
def admin_only_view(request): ...

# ❌ 금지: forbidden_template=None으로 에러 숨기기만 함
@grade_required("superuser", forbidden_template=None)
# → 403 반환은 되지만, 실제로는 "403이 나오니까 grade를 낮춰야겠다"는 잘못된 방향 유도
```

**올바른 접근:** 권한 오류가 발생하면 "왜 이 사용자에게 이 grade가 없는가"를 먼저 조사한다.  
테스트 목적이면 테스트용 superuser 계정을 사용한다.

### 7-2. ⚠️ 정책 함수 우회 — 인라인 grade 판단

```python
# ❌ 금지: 뷰/템플릿에서 grade를 직접 비교해 정책 구현
if request.user.grade in ("superuser", "head"):
    can_download = True

# ❌ 금지: Manual 권한을 뷰에서 직접 구현
if manual.admin_only and request.user.grade not in ("superuser", "head"):
    return HttpResponseForbidden()

# ✅ 올바른 방법: 정책 함수 경유
from manual.utils.permissions import manual_accessible_or_denied
denied = manual_accessible_or_denied(request, manual)
if denied:
    return denied

from board.policies import can_download_post_attachment
if not can_download_post_attachment(request.user, att):
    return redirect(POST_LIST)
```

**이유:** 정책이 코드 여러 곳에 흩어지면 정책 변경 시 누락이 발생한다.  
모든 정책 판단은 SSOT 함수 한 곳에 있어야 변경이 안전하다.

### 7-3. ⚠️ 파일 URL 직접 노출

```html
<!-- ❌ 금지: storage URL 직접 노출 -->
<a href="{{ att.file.url }}">{{ att.original_name }}</a>
<img src="{{ user.profile_image.url }}">
<a href="/media/board/{{ att.file.name }}">다운로드</a>

<!-- ✅ 올바른 방법: 다운로드 뷰 경유 -->
<a href="{% url 'board:post_attachment_download' att.id %}">{{ att.original_name }}</a>
```

**이유:** `/media/` URL은 `CLAUDE.md`에 명시된 대로 **직접 서빙이 금지**되어 있다.  
(`web_ma/urls.py` 주석: "/media/ 직접 서빙 금지. 파일 접근은 반드시 앱별 보호 view에서 권한 검증 후 FileResponse로 제공한다.")

### 7-4. ⚠️ `CustomUser.objects.filter()` 직접 검색

```python
# ❌ 금지: 권한 스코프 없는 직접 검색
users = CustomUser.objects.filter(name__icontains=q)[:50]

# ❌ 금지: AJAX 응답에 전체 사용자 직렬화
users = CustomUser.objects.values("id", "name", "branch")

# ✅ 올바른 방법
from accounts.search_api import search_users_for_api
result = search_users_for_api(request)  # request.user.grade로 스코프 자동 적용
```

**이유:** `basic` 사용자가 전체 직원 명부를 조회할 수 있게 된다.

### 7-5. ⚠️ Force Password Change 미들웨어 무력화

```python
# ❌ 금지: must_change_password 강제 해제로 미들웨어 우회
user.must_change_password = False
user.save()

# ❌ 금지: Whitelist에 무분별한 URL 추가
FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES = "login,logout,...,dashboard,api"

# ❌ 금지: FORCE_PASSWORD_CHANGE_ENABLED = False 로 전체 비활성화 (운영환경)
```

**이유:** 비밀번호 변경 강제 정책을 우회하면 초기 비밀번호 사용자가 방치된다.  
정책 변경은 `should_enforce()`와 settings 스코프 설정으로만 조정한다.

### 7-6. ⚠️ `inactive` grade 사용자에게 데이터 반환

```python
# ❌ 금지: inactive 체크 없이 데이터 반환
@login_required
def api_view(request):
    data = get_data_for_user(request.user)
    return JsonResponse(data)

# ✅ 올바른 방법 (방법 1: 데코레이터)
@not_inactive_required
@login_required
def api_view(request): ...

# ✅ 올바른 방법 (방법 2: grade_required로 inactive 제외)
@grade_required("superuser", "head", "leader", "basic")  # resign만 허용하거나 inactive만 제외
def api_view(request): ...
```

**이유:** `inactive` 사용자는 `is_active=False`이지만 Django 세션이 남아있는 경우 `is_authenticated=True`가 될 수 있다.  
`@login_required`만으로는 inactive를 막지 못한다.

### 7-7. ⚠️ 업로드 서버 검증 없이 파일 저장

```python
# ❌ 금지: 직접 저장
for f in request.FILES.getlist("attachments"):
    Attachment.objects.create(post=post, file=f, original_name=f.name)

# ✅ 올바른 방법
from board.services.attachments import save_attachments
save_attachments(
    files=request.FILES.getlist("attachments"),
    create_func=lambda **kw: Attachment.objects.create(post=post, **kw),
)
```

**이유:** 확장자·Content-Type·크기 검증 없이 저장하면 악성 파일이 서버에 저장된다.

### 7-8. ⚠️ `bulk update`로 `is_active` 동기화 우회

```python
# ❌ 금지: bulk update는 save()를 우회함
CustomUser.objects.filter(grade="inactive").update(is_active=False)
# → 표시상 맞는 것 같지만, 반대 방향("inactive"로 바꾸면서 is_active 안 꺼짐) 위험

CustomUser.objects.filter(branch="특정지점").update(grade="inactive")
# → is_active가 False로 바뀌지 않아 로그인 가능 상태 유지

# ✅ 올바른 방법: 인스턴스 경유
for user in CustomUser.objects.filter(branch="특정지점"):
    user.grade = "inactive"
    user.save()   # save()에서 is_active=False 자동 강제
```

---

## 8. 신규 기능에서 보안 체크리스트

새 뷰·API를 추가할 때 반드시 확인한다:

- [ ] `@login_required` 또는 `@grade_required` 적용 여부
- [ ] `inactive` grade 사용자를 명시적으로 차단했는가 (의도적으로 허용한 경우는 주석으로 이유 명시)
- [ ] 파일 다운로드 뷰라면 `open_fileresponse_from_fieldfile()` 경유 여부
- [ ] 파일 URL을 템플릿에 직접 노출하지 않았는가 (`att.file.url` 사용 금지)
- [ ] 사용자 검색이 필요하면 `search_users_for_api(request)` 또는 `{% url 'accounts:api_search_user' %}` 경유 여부
- [ ] 권한 판단이 뷰/템플릿에 인라인으로 흩어지지 않고 SSOT 정책 함수를 경유하는가
- [ ] 민감 행위(로그인, 파일 다운로드, grade 변경, 비밀번호 변경)에 `log_action()` 호출이 있는가
- [ ] `log_action()` 호출이 `try/except`로 감싸져 있어 로그 실패가 사용자 동작을 막지 않는가
- [ ] `grade="inactive"` 저장이 있다면 `user.save()` 경유인가 (`bulk update` 금지)
- [ ] 새 URL이 Force Password Change 미들웨어 whitelist 추가 대상인지 검토했는가
- [ ] JSON API 응답에 불필요한 사용자 정보(전체 직원 목록, 개인정보)가 포함되지 않았는가
- [ ] `BOARD_ATTACHMENT_ALLOWED_EXTENSIONS`에 없는 확장자 업로드를 서버에서 차단하는가
