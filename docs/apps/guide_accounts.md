# accounts 앱 개발 가이드

> 외부 LLM이 전체 코드 없이 이 앱을 정확하게 디벨롭할 수 있도록 작성된 문서다.
> 실제 파일명 · 함수명 · 필드명을 그대로 사용한다.

---

## 1. 앱 책임 요약

`accounts`는 **CustomUser 모델 정의, 인증(로그인/로그아웃/비밀번호 변경), 계정 잠금(Lockout), 강제 비밀번호 변경(Phase 3), 대량 사용자 엑셀 업로드/다운로드** 를 담당한다.  
다른 모든 앱이 `CustomUser`와 `grade_required` 데코레이터에 의존하며, 사용자 검색은 `accounts/search_api.py`가 SSOT다.

---

## 2. 디렉터리 구조

```
accounts/
├── __init__.py
├── admin.py                  # CustomAdminSite 기반 Django Admin: Excel 업로드/다운로드, 계정 관리 액션
├── apps.py                   # AccountsConfig; ready()에서 signals 등록
├── constants.py              # 캐시 키 접두어, Lockout 상수, Excel MIME 타입 (SSOT)
├── custom_admin.py           # CustomAdminSite 정의 (superuser 전용 Admin)
├── decorators.py             # grade_required, not_inactive_required 데코레이터
├── forms.py                  # ExcelUploadForm, ActiveOnlyAuthenticationForm, StrictPasswordChangeForm
├── middleware/
│   └── force_password_change.py  # Phase 3: must_change_password=True 사용자 비번 변경 강제 리다이렉트
├── migrations/               # 0001_initial ~ 0019 (총 19개)
├── models.py                 # CustomUser 모델 (AbstractBaseUser + PermissionsMixin)
├── models_policy.py          # (비어있음, 향후 정책 로직 이전 예정)
├── policies/
│   └── password_policy.py    # should_enforce() - 강제 비번 변경 대상 여부 판단 엔진
├── search_api.py             # 사용자 검색 SSOT (직접 호출 금지, 이 파일만 경유)
├── services/
│   └── users_excel_import.py # Excel 파싱·정규화·도메인 변환 함수 모음
├── signals.py                # pre_save/post_save → grade 변경 시 SubAdminTemp 동기화
├── static/accounts/excel/
│   └── 양식_계정관리.xlsx    # Admin Excel 업로드 양식 파일
├── tasks.py                  # Celery: process_users_excel_task (Excel 대량 업로드)
├── tests.py                  # (stub, 테스트 미작성)
├── urls.py                   # accounts 네임스페이스 URL 5개
├── utils.py                  # build_affiliation_display() 유틸
└── views.py                  # 로그인(SessionCloseLoginView), 비번변경, 업로드 진행률, 검색 API
```

전역 템플릿 (앱 내부 templates/ 없음):

```
templates/
├── registration/
│   ├── login.html                         # 로그인 페이지
│   ├── password_change_form.html          # 비밀번호 변경 폼
│   └── password_change_done.html          # 변경 완료 페이지
└── admin/accounts/customuser/
    ├── change_list.html                   # Admin 사용자 목록 (Excel 업로드 버튼 추가)
    └── upload_excel.html                  # Admin Excel 업로드 진행률 폴링 페이지

static/js/accounts/
├── admin_upload_progress.js               # Admin 전용: 업로드 진행률 폴링 IIFE
└── policy_console.js                      # (stub, Phase 5 예정)
```

---

## 3. 모델 구조

### CustomUser (`accounts/models.py`)

**상속:** `AbstractBaseUser`, `PermissionsMixin`  
**USERNAME_FIELD:** `id` (사원번호)  
**REQUIRED_FIELDS:** `["name"]`

#### 핵심 필드

| 필드명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | `CharField(30)` | PK, unique | 사원번호 (로그인 식별자) |
| `name` | `CharField(100)` | required | 성명 |
| `regist` | `CharField(50)` | blank, null | 등록번호(소속 등록 정보) |
| `birth` | `DateField` | blank, null | 생년월일 |
| `enter` | `DateField` | blank, null | 입사일자 |
| `quit` | `DateField` | blank, null | 퇴사일자 |
| `channel` | `CharField(10)` | blank, default="" | 부문 (예: "MA부문") |
| `division` | `CharField(30)` | blank, default="" | 총괄 |
| `part` | `CharField(10)` | blank, default="" | 부서 |
| `branch` | `CharField(100)` | blank, default="" | 지점 |
| `grade` | `CharField(20)` | choices (아래 참조) | 권한 등급 |
| `status` | `CharField(20)` | default="재직" | 재직상태 |
| `is_active` | `BooleanField` | default=True | 활성화 여부 |
| `is_staff` | `BooleanField` | default=False | Django admin 접근 여부 |
| `is_superuser` | `BooleanField` | default=False | Django superuser |
| `login_fail_count` | `PositiveIntegerField` | default=0 | 연속 로그인 실패 횟수 |
| `is_locked` | `BooleanField` | default=False | 계정 잠금 여부 (Phase 4) |
| `locked_at` | `DateTimeField` | blank, null | 잠금 시각 |
| `last_login_fail_at` | `DateTimeField` | blank, null | 마지막 실패 시각 |
| `lock_reason` | `CharField(50)` | blank, default="" | 잠금 사유 |
| `lock_cleared_at` | `DateTimeField` | blank, null | 잠금 해제 시각 |
| `lock_cleared_by` | `ForeignKey(self)` | null, blank | 잠금 해제한 관리자 |
| `password_reset_by_admin_at` | `DateTimeField` | blank, null | 관리자 비번 초기화 시각 |
| `must_change_password` | `BooleanField` | default=False | 강제 비번 변경 플래그 (Phase 3) |
| `must_change_password_set_at` | `DateTimeField` | blank, null | 플래그 설정 시각 |
| `must_change_password_cleared_at` | `DateTimeField` | blank, null | 플래그 해제 시각 |
| `pass_verified` | `BooleanField` | default=False | PASS 전자서명 검증 완료 |
| `pass_verified_at` | `DateTimeField` | blank, null | PASS 검증 완료 시각 |
| `pass_verified_ip` | `GenericIPAddressField` | blank, null | PASS 검증 IP |
| `ci_hash` | `CharField(64)` | blank, default="" | CI 값 SHA-256 해시 |

#### Grade Choices (SSOT)

| 값 | 설명 | `is_active` 자동값 |
|---|---|---|
| `"superuser"` | 시스템 최고 관리자 | True |
| `"head"` | 파트너별 최상위 관리자 | True |
| `"leader"` | 파트너별 중간 관리자 | True |
| `"basic"` | 일반 사용자(설계사) | True |
| `"resign"` | 퇴사자 | True (로그인 가능, 기능 제한) |
| `"inactive"` | 비활성 | **False 강제** |

#### 운영 정책

⚠️ `save()` 오버라이드: `grade == "inactive"`이면 `is_active = False`를 **자동 강제**한다.  
DB에 직접 UPDATE해도 `save()` 경유 시 반드시 동기화된다.  
`CustomUser.objects.filter(...).update(grade="inactive")`는 `save()`를 우회하므로 `is_active`가 동기화되지 않는다. ⚠️

#### 모델 간 관계

- `lock_cleared_by` → `ForeignKey("self", null=True, blank=True)` (자기 참조)
- `partner.SubAdminTemp` → accounts를 참조 (역방향: `signals.py`에서 grade 변경 시 동기화)

---

## 4. URL 네임스페이스 + 엔드포인트

**네임스페이스:** `accounts`  
**prefix:** `/accounts/` (web_ma/urls.py에서 include)

| URL name | route | 메서드 | 반환 | 설명 |
|---|---|---|---|---|
| `accounts:password_change` | `/accounts/password-change/` | GET, POST | HTML | 비밀번호 변경 폼 |
| `accounts:password_change_done` | `/accounts/password-change/done/` | GET | HTML | 변경 완료 페이지 |
| `accounts:accounts_upload_progress` | `/accounts/upload-progress/` | GET | JSON | Celery 업로드 진행률 폴링 |
| `accounts:accounts_upload_result` | `/accounts/upload-result/<task_id>/` | GET | FileResponse | 업로드 결과 xlsx 다운로드 |
| `accounts:api_search_user` | `/accounts/api/search-user/` | GET | JSON | 사용자 검색 (신규 SSOT) |
| `accounts:search_user_legacy` | `/accounts/search-user/` | GET | JSON | 사용자 검색 (레거시 alias) |

**accounts 네임스페이스 밖 (web_ma/urls.py 직접 등록):**

| URL name | route | 메서드 | 반환 | 설명 |
|---|---|---|---|---|
| `login` | `/login/` | GET, POST | HTML | 로그인 (`SessionCloseLoginView`) |
| `logout` | `/logout/` | POST | redirect | 로그아웃 (`auth_views.LogoutView`) |

---

## 5. 권한 정책

### Grade별 접근 범위

| grade | 사용자 검색 범위 | Admin 접근 | 비밀번호 변경 |
|---|---|---|---|
| `superuser` | 전체 (scope=branch면 특정 지점) | ✅ (CustomAdminSite) | ✅ |
| `head` | 자기 branch만 | ❌ | ✅ |
| `leader` | scope=branch면 branch, 아니면 SubAdminTemp 팀 | ❌ | ✅ |
| `basic` | 자신만 | ❌ | ✅ |
| `resign` | 자신만 | ❌ | ✅ |
| `inactive` | 자신만 (로그인 불가이므로 실질적 차단) | ❌ | ❌ |

### 권한 강제 위치

- **로그인 차단:** `ActiveOnlyAuthenticationForm.confirm_login_allowed()` — is_locked, is_active=False 검증
- **뷰 접근 제어:** `accounts/decorators.py`의 `@grade_required(*allowed_grades)` — 모든 앱에서 이걸 사용
- **검색 범위 제한:** `accounts/search_api.py`의 `_apply_permission_scope()` — 검색 결과 생성 시 서버에서 강제
- **Admin 접근:** `CustomAdminSite.has_permission()` — `grade == "superuser"`만 허용

### `grade_required` 사용 패턴

```python
# accounts/decorators.py
@grade_required("head")              # 단일 grade
@grade_required("head", "leader")    # 복수 grade
@grade_required(["superuser", "head"])  # 리스트 형태도 지원

# forbidden_template 기본값: "no_permission_popup.html"
# None 또는 "" 지정 시 → 403 반환
```

---

## 6. 서비스/유틸 레이어 SSOT 목록

### `accounts/search_api.py` ⚠️

| 함수 | 역할 |
|---|---|
| `read_search_params(request)` | GET 파라미터(q, scope, branch) 파싱 → `SearchParams` 반환 |
| `search_users_for_api(request)` | 권한 스코프 적용 후 사용자 검색, SubAdminTemp 병합, 최대 50건 반환 |

⚠️ **사용자 검색은 반드시 `search_users_for_api(request)`만 경유해야 한다.**  
`CustomUser.objects.filter(name__icontains=...)` 직접 호출은 권한 스코프가 빠지므로 금지.  
다른 앱에서 검색이 필요하면 `{% url 'accounts:api_search_user' %}`로 AJAX 호출하거나 `search_users_for_api()`를 import해서 사용한다.

### `accounts/services/users_excel_import.py` ⚠️

| 함수 | 역할 |
|---|---|
| `normalize_emp_id(v)` | float→int 문자열, NaN→"" 정규화 |
| `normalize_part(v)` | 특정 부서명 매핑 (예: "1인GA사업부"→"MA사업4부") |
| `parse_excel_date(value)` | datetime/date/문자열 → `date` 객체 |
| `infer_channel(part_text)` | 부서명으로 부문 추론 (MA/CA/PA/전략) |
| `infer_grade(name, employed_flag)` | 이름·재직여부로 grade 추론 |
| `infer_status(grade)` | grade로 재직상태 추론 |
| `pick_worksheet_by_required_cols(wb)` | REQUIRED_COLS 포함 시트 자동 선택 |
| `build_defaults_from_row(headers, row)` | 엑셀 행 → (emp_id, name, defaults_dict) |

⚠️ **Excel 업로드 로직은 반드시 이 파일의 함수를 재사용한다.** `tasks.py`의 `process_users_excel_task` 직접 수정 전 이 파일의 도메인 변환 함수 먼저 확인.

### `accounts/decorators.py`

| 함수 | 역할 |
|---|---|
| `grade_required(*allowed_grades, forbidden_template)` | 모든 앱의 뷰에서 grade 접근 제어 |
| `not_inactive_required(view_func)` | inactive grade 차단 |

### `accounts/policies/password_policy.py`

| 함수 | 역할 |
|---|---|
| `should_enforce(user, request=None) → bool` | 사용자에게 강제 비번 변경 미들웨어 적용 여부 판단 |

⚠️ `ForcePasswordChangeMiddleware`는 `should_enforce()`만 호출한다. 강제 변경 로직 수정 시 `password_policy.py`를 수정해야 한다.

### `accounts/utils.py`

| 함수 | 역할 |
|---|---|
| `build_affiliation_display(*, branch, level, team_a, team_b, team_c) → str` | 소속 표시 문자열 생성 (branch + 팀 레벨 조합) |

### `accounts/constants.py` ⚠️

| 상수 | 값 | 용도 |
|---|---|---|
| `CACHE_PROGRESS_PREFIX` | `"upload_progress:"` | 업로드 진행률 캐시 키 |
| `CACHE_STATUS_PREFIX` | `"upload_status:"` | 업로드 상태 캐시 키 |
| `CACHE_ERROR_PREFIX` | `"upload_error:"` | 업로드 에러 캐시 키 |
| `CACHE_RESULT_PATH_PREFIX` | `"upload_result_path:"` | 결과 파일 경로 캐시 키 |
| `CACHE_TIMEOUT_SECONDS` | `3600` | 캐시 TTL (1시간) |
| `LOGIN_FAIL_MAX_COUNT` | `5` | 잠금 임계값 |
| `LOCK_REASON_LOGIN_FAIL_MAX` | `"LOGIN_FAIL_MAX"` | 잠금 사유 코드 |
| `EXCEL_CONTENT_TYPE` | `"application/vnd.openxmlformats-..."` | Excel MIME 타입 |

⚠️ **Lockout 임계값(`LOGIN_FAIL_MAX_COUNT=5`)과 캐시 키 접두어는 이 파일이 SSOT다.** 분산 수정 금지.

---

## 7. 템플릿 구조

accounts 앱은 **앱 내부 templates/ 디렉터리가 없다.** 전역 templates/ 사용.

### 상속 관계

```
base.html
└── templates/registration/login.html              ({% extends 'base.html' %})
└── templates/registration/password_change_form.html ({% extends 'base.html' %})
└── templates/registration/password_change_done.html ({% extends 'base.html' %})

templates/admin/accounts/customuser/
├── change_list.html     (Django Admin override: Excel 업로드 버튼 추가)
└── upload_excel.html    (Admin 전용: 업로드 진행률 폴링 UI)
```

### CSS 로드

accounts 앱 전용 CSS 파일 없음. `base.html`의 전역 스타일만 사용한다.  
`login.html`은 `app_css` 블록 없음. `.login-card-wrap`, `.login-title`, `.login-error-alert` 클래스는 `base.css`에 정의됨.

---

## 8. JS 부트 패턴

### `admin_upload_progress.js` (Admin 전용)

- **루트 엘리먼트 id:** `uploadProgressBox`
- **BFCache 가드:** `window.__accountsUsersUploadPollingStarted` 전역 플래그로 중복 실행 차단

**dataset 계약 (`#uploadProgressBox`):**

| key | 설명 | 변경 금지 이유 |
|---|---|---|
| `data-task-id` | Celery task UUID | JS와 서버 상태 폴링 연결 키 |
| `data-progress-url` | `/accounts/upload-progress/` URL | JS 하드코딩 금지 계약 |

**DOM 계약 (변경 금지):**

| id | 역할 |
|---|---|
| `progressBar` | Bootstrap progress bar 너비·텍스트 |
| `progressStatusText` | 상태 텍스트 표시 |
| `progressErrorText` | 에러 텍스트 표시 |
| `resultDownloadBtn` | 완료 후 활성화되는 다운로드 링크 |

**폴링 로직:** 1초 간격 fetch, FAILURE/SUCCESS 시 중단. 네트워크 에러 시 3초 후 재시도.

### `password_change_form.html` 인라인 JS

- `form.dataset.samePwGuardBound = "1"` 으로 중복 바인딩 방지 (BFCache 가드)
- 클라이언트에서 `old_password === new_password1` 일치 시 submit 차단 (UX 보조용, SSOT는 `StrictPasswordChangeForm.clean()`)

---

## 9. CSS 스코프 규약

accounts 앱 전용 CSS 파일 없음. 앱 전용 스타일은 `base.css`의 `.login-*`, `.auth-done-*` 등의 클래스로 관리된다.  
accounts 관련 신규 스타일 추가 시: `static/css/apps/accounts.css` 신규 생성 + `base_board.html` 패턴 참고해 `app_css` 블록에서 로드.  
**`base.css` 직접 수정 금지.** `base.css`는 전역 토큰/공통 UI이므로 accounts 전용 규칙을 넣으면 다른 앱에 누수된다.

---

## 10. 절대 수정 금지 목록

| 파일 | 금지 이유 |
|---|---|
| `accounts/constants.py` (Lockout 상수) | `LOGIN_FAIL_MAX_COUNT` 변경 시 운영 중 계정 잠금 임계값이 어긋남. DB에 이미 누적된 `login_fail_count`와 불일치 발생 |
| `accounts/constants.py` (캐시 키 접두어) | Redis 캐시 키 변경 시 진행 중인 업로드 작업의 진행률 추적 불가. 기존 작업 상태 영원히 조회 불가 |
| `accounts/models.py` `save()` 오버라이드 | `inactive → is_active=False` 동기화 제거 시 비활성 계정이 로그인 가능해지는 보안 취약점 발생 |
| `accounts/search_api.py` `_apply_permission_scope()` | 권한 스코프 로직 변경 시 basic/resign 사용자가 전체 직원 정보를 조회 가능해지는 정보 노출 위험 |
| `accounts/custom_admin.py` `CustomAdminSite.has_permission()` | `grade == "superuser"` 조건 제거 시 일반 사원이 Admin에 접근 가능해짐 |
| `accounts/middleware/force_password_change.py` Whitelist | `FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES`에 과도한 URL 추가 시 강제 비번 변경 우회 가능 |
| `accounts/services/users_excel_import.py` `REQUIRED_COLS` | 필수 컬럼 목록 변경 시 기존 양식_계정관리.xlsx와 불일치, 업로드 전체 실패 |
| `static/accounts/excel/양식_계정관리.xlsx` | Admin 양식 파일. 컬럼 헤더 변경 시 `REQUIRED_COLS` 동시 수정 필수 |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 대상 | 파일 | 용도 |
|---|---|---|
| `partner.models.SubAdminTemp` | `accounts/search_api.py`, `accounts/signals.py` | 팀 레벨 정보 조회 및 grade 변경 시 동기화 |
| `audit.services.log_action` | `accounts/views.py` | 로그인 성공/실패, 비번 변경 감사 로깅 |
| `audit.constants.ACTION` | `accounts/views.py` | 감사 로그 액션 코드 |
| `audit.utils.mask_value` | `accounts/views.py` | 민감 정보 마스킹 |

### 다른 앱이 이 앱에 의존하는 관계

| 의존 앱 | 의존 대상 | 용도 |
|---|---|---|
| **전체 앱** | `accounts.models.CustomUser` | AUTH_USER_MODEL — Django User 모델 |
| **전체 앱** | `accounts.decorators.grade_required` | 뷰 접근 권한 제어 |
| **전체 앱** | `accounts:api_search_user` | 사용자 검색 모달 (search_user_modal.html) |
| `board` | `accounts.decorators.grade_required` | 업무 뷰 권한 |
| `partner` | `CustomUser.grade`, `CustomUser.branch` | SubAdminTemp 팀 관리 대상 |
| `web_ma/urls.py` | `accounts.views.SessionCloseLoginView` | `/login/` URL 직접 연결 |
| `web_ma/urls.py` | `accounts.custom_admin.custom_admin_site` | `/admin/` URL 연결 |

---

## 12. 신규 기능 추가 패턴

### 신규 뷰 + URL 추가

1. `accounts/views.py`에 view 함수 작성 (`@login_required` + `@grade_required` 데코레이터 적용)
2. `accounts/urls.py`의 `urlpatterns`에 `path()` 추가
3. `web_ma/urls.py` 변경 불필요 (accounts prefix 이미 include 됨)
4. 강제 비번 변경 우회가 필요한 URL이면 `settings.FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES`에 URL name 추가

### 신규 Grade 추가

1. `accounts/models.py` `GRADE_CHOICES`에 새 값 추가
2. `makemigrations` + `migrate`
3. `accounts/decorators.py` `GRADE_ALIAS_MAP` 업데이트 (필요 시)
4. `accounts/search_api.py` `_apply_permission_scope()`에 새 grade 분기 추가
5. `accounts/policies/password_policy.py` `FORCE_PASSWORD_CHANGE_EXEMPT_GRADES` 확인
6. 모든 앱의 `@grade_required(...)` 호출부 영향도 검토

### 신규 Phase (보안 기능) 추가 예시 (Phase 5 가정)

1. `accounts/models.py`에 관련 필드 추가
2. `makemigrations` + `migrate`
3. `accounts/constants.py`에 상수 추가
4. `accounts/policies/`에 정책 파일 추가
5. 필요 시 `accounts/middleware/`에 미들웨어 추가 → `settings.MIDDLEWARE`에 등록
6. `accounts/views.py`에 관련 뷰 추가

### Excel 컬럼 추가

1. `accounts/services/users_excel_import.py`의 `REQUIRED_COLS` 수정 (필수 컬럼이면)
2. `build_defaults_from_row()`에 파싱 로직 추가
3. `accounts/tasks.py`의 `flush_chunk` 내 보호 필드(`PROTECTED_FIELDS`) 여부 결정
4. `static/accounts/excel/양식_계정관리.xlsx` 업데이트
5. Admin 안내 문구 업데이트

---

## 13. LLM 함정 포인트

### `USERNAME_FIELD = "id"` — 사원번호가 PK

Django 기본 User는 `username` 필드를 사용한다. 이 프로젝트는 `id`(사원번호)를 로그인 식별자로 사용한다.  
`request.user.username` 참조는 AttributeError. **반드시 `request.user.id`를 사용한다.**  
로그인 폼의 input name은 `username`이 아닌 `username`이지만 실제로는 사원번호를 받는다. (Django AuthenticationForm 내부 처리)

### `CustomUser.objects.filter().update()` — `save()` 우회 위험

`grade="inactive"`로 `bulk update` 시 `is_active`가 자동 동기화되지 않는다.  
⚠️ grade 변경은 반드시 인스턴스를 통해 `user.save()`로 처리해야 한다.

### `search_api.py` vs `CustomUser.objects.filter()` 직접 검색

사용자 검색을 `CustomUser.objects.filter(name__icontains=q)` 로 구현하면 권한 스코프가 빠진다.  
`basic` grade 사용자가 전체 직원 목록을 조회할 수 있게 된다.  
⚠️ **검색은 반드시 `accounts/search_api.py`의 `search_users_for_api(request)`를 경유한다.**

### `SessionCloseLoginView`의 URL name은 `"login"`, NOT `"accounts:login"`

로그인 URL은 `web_ma/urls.py`에서 `name="login"`으로 직접 등록된다.  
`accounts` 네임스페이스에 없으므로 `{% url 'login' %}`이 올바르다. `{% url 'accounts:login' %}`은 NoReverseMatch.

### `FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES` — 콤마 구분 문자열

`settings.py`에서 `config("FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES", default="login,logout,...")` 형태로 읽힌다.  
리스트가 아닌 **콤마 구분 문자열**이므로 신규 URL 추가 시 `.env.dev`와 `.env.prod` 양쪽을 모두 수정해야 한다.

### `lock_cleared_by` — 자기 참조 ForeignKey

`lock_cleared_by = ForeignKey("self", null=True, blank=True)` 다.  
직렬화(serializers) 작성 시 재귀 참조 주의. Admin action에서 자동 설정 (`request.user`).

### Admin은 `custom_admin_site`, Django 기본 admin은 비활성

`admin.site`가 아닌 `custom_admin_site = CustomAdminSite(name="custom_admin")`를 사용한다.  
새 모델을 Admin에 등록할 때 `admin.site.register()`가 아닌 `custom_admin_site.register()`로 해야 한다.  
`accounts/admin.py` 상단의 `custom_admin_site.register(CustomUser, CustomUserAdmin)` 참고.

### Excel 업로드 결과 파일 경로 — `_safe_upload_result_path()` 필수

`upload_result_view`에서 결과 파일 다운로드 시 경로 traversal 방지를 위해 `_safe_upload_result_path(raw_path)`를 반드시 경유한다.  
Redis 캐시에서 꺼낸 경로를 그대로 `open()`하면 Path Traversal 취약점이다.

---

## 14. 회귀 위험 체크리스트

accounts 앱 수정 시 반드시 확인해야 하는 포인트:

- [ ] **`CustomUser.grade` 변경** → `is_active` 자동 동기화 여부 확인 (`save()` 경유했는가)
- [ ] **Lockout 임계값 변경** → `constants.LOGIN_FAIL_MAX_COUNT`만 수정하고 관련 메시지(`_build_invalid_login_message`, `_build_locked_message`) 동시 수정 여부
- [ ] **강제 비번 변경 whitelist 변경** → `settings.py`의 `FORCE_PASSWORD_CHANGE_URL_WHITELIST_NAMES` + `.env.dev` + `.env.prod` 모두 반영 여부
- [ ] **새 URL 추가** → Phase 3 미들웨어 우회 필요 여부 검토 (비인증 접근 허용 URL이면 whitelist 등록)
- [ ] **Excel 컬럼 변경** → `양식_계정관리.xlsx` 파일과 `REQUIRED_COLS` 동기화 여부
- [ ] **사용자 검색 변경** → `search_api.py`의 권한 스코프(`_apply_permission_scope`) 유지 여부
- [ ] **Admin action 추가** → `CustomAdminSite.has_permission()` — superuser 전용 제한 의도 위반 여부
- [ ] **signals.py 변경** → `grade` 변경 시 `SubAdminTemp` 자동 동기화 로직 유지 여부 (`partner` 앱 연동)
- [ ] **`AuditLog` 누락** → 로그인/비번변경/계정잠금 해제 등 민감 액션의 `audit.services.log_action()` 호출 여부
- [ ] **캐시 키 변경** → 진행 중인 업로드 작업의 진행률 추적 불가 여부 (Redis 키 불일치)
- [ ] **`infer_grade()` 변경** → 엑셀 업로드로 생성되는 신규 계정의 grade 기본값 영향도
- [ ] **`partner.SubAdminTemp` import 의존** → signals.py, search_api.py 모두 SubAdminTemp를 import함. partner 앱 구조 변경 시 accounts도 점검
