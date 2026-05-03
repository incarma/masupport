# django_ma 보안 감사 체크리스트
> 생성일: 2026-05-03
> 점검 브랜치/커밋: 5e7e7f1 (develop)
> 점검 범위: 전체 앱 (accounts / board / commission / dash / manual / partner / audit)

---

## 요약 대시보드

| 카테고리 | 항목 수 | 🔴 위반 | 🟡 확인필요 | ✅ 준수 | ➖ 해당없음 |
|----------|---------|---------|------------|--------|-----------|
| S-A. 파일 접근 보안 | 7 | 0 | 1 | 6 | 0 |
| S-B. 인증 및 권한 제어 | 8 | 2 | 2 | 4 | 0 |
| S-C. 입력 검증 및 인젝션 방지 | 5 | 0 | 1 | 4 | 0 |
| S-D. CSRF 및 세션 보안 | 3 | 1 | 0 | 2 | 0 |
| S-E. 감사(Audit) 로그 | 5 | 2 | 1 | 2 | 0 |
| S-F. 운영 환경 보안 설정 | 4 | 0 | 1 | 3 | 0 |
| **합계** | **32** | **5** | **6** | **21** | **0** |

---

## 🔴 즉시 조치 필요 항목 (위반 판정)

| 항목 ID | 설명 | 위반 파일/위치 | 위험도 |
|---------|------|--------------|--------|
| S-B-05 | grade 변경(leader 승격/강등) 시 audit 로그 미기록 | `partner/views/subadmin.py:56-57, 130-131` | 높음 |
| S-B-06 | 계정 Excel 업로드(grade 변경 포함) 시 audit 로그 미기록 | `accounts/admin.py`, `accounts/tasks.py` | 높음 |
| S-D-01 | commission 업로드/결재 엔드포인트에 `@csrf_exempt` 적용 | `commission/views/api_upload.py:54`, `commission/views/approval.py:92` | 높음 |
| S-E-01 | `ACTION.COMMISSION_EXCEL_UPLOAD`가 `audit/constants.py`에 미정의 (AttributeError 발생) | `commission/views/approval.py:119,131,142,177,213,226` | 중간 |
| S-E-04 | grade 변경 행위(ACCOUNTS_GRADE_UPDATE, PARTNER_LEADER_ADD/DELETE)가 상수는 정의됐지만 실제 `log_action` 호출 없음 | `audit/constants.py:70-71,83` / 호출 없음 | 높음 |

---

## 상세 점검 결과

### S-A. 파일 접근 보안

#### S-A-01. 템플릿 직접 파일 URL 노출 여부 (`att.file.url`, `/media/` 직접 링크)
- **판정**: ✅ 준수
- **점검 방법**: 전체 HTML 템플릿에서 `.file.url` 및 `/media/` 패턴 grep
- **근거**: 검색 결과 없음. `board/templates/board/worktask_edit.html:196`, `worktask_detail.html:168` 등에 "att.file.url 직접 링크 금지" 주석이 명시되어 있으며, 모든 첨부 다운로드는 뷰 경유.

---

#### S-A-02. Board Post 첨부파일 다운로드 뷰 권한 검증
- **판정**: ✅ 준수
- **점검 방법**: `board/views/attachments.py` 전체 분석
- **근거**: `post_attachment_download` → `@login_required` + `@grade_required(*BOARD_ALLOWED_GRADES)` + `can_download_post_attachment(request.user, att)` (policies.py SSOT 경유). 실패 시 403/redirect + audit 로그 기록.

---

#### S-A-03. Board Task 첨부파일 다운로드 뷰 권한 검증
- **판정**: ✅ 준수
- **점검 방법**: `board/views/attachments.py:125-164`
- **근거**: `task_attachment_download` → `@grade_required(*TASK_ALLOWED_GRADES)` + `can_download_task_attachment(request.user, att)` (superuser만 허용). 실패 시 redirect + audit 로그.

---

#### S-A-04. WorkTask 첨부파일 다운로드 소유자 격리
- **판정**: ✅ 준수
- **점검 방법**: `board/views/worktasks.py:366-406`
- **근거**: `worktask_att_download` → `@grade_required("superuser")` + `att.task.owner_id != request.user.pk` 명시적 소유자 검증. 불일치 시 403 반환 + 경고 로그.

---

#### S-A-05. Manual 첨부파일 다운로드 권한 검증
- **판정**: ✅ 준수
- **점검 방법**: `manual/views/attachment.py:100-132`
- **근거**: `manual_attachment_download` → `@login_required` + `manual_accessible_or_denied(request, manual)` (manual/utils/permissions.py SSOT 경유). `grade`, `admin_only`, `is_published` 기준 종합 검증 후 FileResponse.

---

#### S-A-06. 파일 업로드 검증 SSOT 경유 여부 (규약 6)
- **판정**: 🟡 확인필요
- **점검 방법**: `board/views/posts.py:435`, `board/views/tasks.py:335` 분석
- **근거**: `board/views/posts.py:435` 및 `tasks.py:335`에서 `Attachment.objects.create(post=post, **kwargs)` / `TaskAttachment.objects.create(task=task, **kwargs)`가 람다 형태로 `save_attachments()` 에 전달되고 있어 SSOT 준수 여부가 람다 래핑 여부에 달림. 실제 `save_attachments()` 호출 체인이 `validate_board_attachment()`를 경유하는지 추가 확인 권장.

---

#### S-A-07. UPLOAD_TEMP_DIR 경로 조작 방지
- **판정**: ✅ 준수
- **점검 방법**: `accounts/views.py:118-125`, `commission/views/_files.py`
- **근거**: `_safe_upload_result_path()`에서 `Path.resolve()`로 절대경로 정규화 후 `UPLOAD_RESULT_DIR` 기준 부모 경로 검증 수행. 경로 탈출 방지.

---

### S-B. 인증 및 권한 제어

#### S-B-01. grade_required 데코레이터 구현 (SSOT)
- **판정**: ✅ 준수
- **점검 방법**: `accounts/decorators.py` 전체 분석
- **근거**: `grade_required`는 `@login_required` 포함 + `request.user.grade`를 allowed_set과 비교. 미허용 시 template 또는 403 반환. `_expand_allowed_grades`로 레거시 alias 처리.

---

#### S-B-02. board 권한 판단 SSOT 경유 (rules: policies.py)
- **판정**: ✅ 준수
- **점검 방법**: `board/policies.py`, `board/views/attachments.py`
- **근거**: `can_view_post`, `can_edit_post`, `can_download_post_attachment`, `can_download_task_attachment` 모두 `board/policies.py`에서 단일 정의. 뷰는 이 함수만 호출.

---

#### S-B-03. manual 권한 판단 SSOT 경유 (rules: permissions.py)
- **판정**: ✅ 준수
- **점검 방법**: `manual/utils/permissions.py`, `manual/views/attachment.py`
- **근거**: `manual_accessible_or_된`, `filter_manuals_for_user`, `ensure_superuser_or_403` 모두 `manual/utils/permissions.py` SSOT. 뷰에서 직접 grade 비교 없음.

---

#### S-B-04. WorkTask 소유자 격리 SSOT 경유 (규약 12)
- **판정**: ✅ 준수
- **점검 방법**: `board/views/worktasks.py` 전체 분석 + `board/services/worktasks.py`
- **근거**: 모든 목록/상세/수정/삭제/완료/건너뜀 뷰가 `wt_svc.get_user_queryset()` 또는 `wt_svc.get_user_task()` 경유. `WorkTask.objects.get()` 단독 호출 없음. 첨부 삭제 시 `get_object_or_404(WorkTaskAttachment, pk=att_id, task=task)`로 소유자 간접 검증.

---

#### S-B-05. grade 변경 행위에 대한 권한 제어 및 audit 로그 누락 (규약 10)
- **판정**: 🔴 위반
- **점검 방법**: `partner/views/subadmin.py` 분석 + `log_action` 호출 grep
- **근거**: `ajax_add_sub_admin()`과 `ajax_delete_subadmin()`에서 `u.grade = "leader"` / `target.grade = "basic"` 후 `.save(update_fields=["grade"])`를 수행하지만, `log_action()` 호출이 전혀 없다. `audit/constants.py`에 `PARTNER_LEADER_ADD`, `PARTNER_LEADER_DELETE`, `ACCOUNTS_GRADE_UPDATE` 상수가 정의되어 있으나 실제로 사용되지 않는다.
- **위반 파일**: `partner/views/subadmin.py:56-57`, `partner/views/subadmin.py:130-131`
- **권장 조치**: `ajax_add_sub_admin()` 및 `ajax_delete_subadmin()` 성공 분기에 `log_action(request, ACTION.PARTNER_LEADER_ADD/DELETE, obj=u, ...)` 추가.

---

#### S-B-06. 계정 Excel 업로드(grade 포함) audit 로그 미기록 (규약 10)
- **판정**: 🔴 위반
- **점검 방법**: `accounts/admin.py`, `accounts/tasks.py` 분석 + `log_action` + `ACCOUNTS_EXCEL_UPLOAD` grep
- **근거**: `accounts/admin.py`의 엑셀 업로드 뷰 및 `accounts/tasks.py`의 Celery 처리 태스크에서 `log_action()`을 호출하지 않는다. `audit/constants.py:81`에 `ACCOUNTS_EXCEL_UPLOAD = "accounts.excel.upload"`, `ACCOUNTS_GRADE_UPDATE = "accounts.user.grade.update"` 상수가 정의되어 있으나 `accounts/` 내에서 전혀 사용되지 않는다. 계정 일괄 업로드는 grade 변경을 포함하므로 감사 공백이 크다.
- **권장 조치**: `accounts/tasks.py`의 `process_users_excel_task` 완료 분기에 `log_action(request, ACTION.ACCOUNTS_EXCEL_UPLOAD, ...)` 추가. grade 변경 건에 대해서는 `ACTION.ACCOUNTS_GRADE_UPDATE`도 별도 기록 권장.

---

#### S-B-07. 사용자 검색 API SSOT 경유 여부 (규약 2)
- **판정**: ✅ 준수
- **점검 방법**: `accounts/views.py:550-559`, `accounts/search_api.py`
- **근거**: `api_search_user()` 및 레거시 `search_user()` 모두 `search_users_for_api(request)` (SSOT) 호출만 함. 프론트 필터링 없음. 권한 스코프는 `_apply_permission_scope()`에서 grade 기준으로 단일 처리.

---

#### S-B-08. request.user.username 사용 금지 (규약 7, USERNAME_FIELD="id")
- **판정**: 🟡 확인필요
- **점검 방법**: `.py` 및 `.html` 파일 전체 grep
- **근거**: Python 코드와 HTML 템플릿 모두에서 `user.username` 또는 `request.user.username` 패턴이 검색되지 않음. 다만 `accounts/views.py:280`에서 `SessionCloseLoginView._extract_login_id()`가 `request.POST.get("username")`을 사용하는데, 이는 Django의 `AuthenticationForm`이 기본적으로 `username` 필드명을 사용하기 때문에 form 입력값 수신 목적이므로 규약 위반과는 다른 맥락. 그러나 사번 기반 `id` 필드와의 혼동 가능성이 있으므로 코드 리뷰 권장.

---

### S-C. 입력 검증 및 인젝션 방지

#### S-C-01. ORM raw()/extra() 사용 여부 (SQL 인젝션)
- **판정**: ✅ 준수
- **점검 방법**: 전체 `.py` 파일에서 `.raw(` 및 `.extra(` 패턴 grep
- **근거**: 검색 결과 없음. 전체 코드베이스가 Django ORM QuerySet API만 사용.

---

#### S-C-02. 파일 업로드 확장자/MIME 검증
- **판정**: ✅ 준수
- **점검 방법**: `board/services/attachments.py:113-197`
- **근거**: `validate_board_attachment()`에서 파일명 존재, 빈 파일, 크기 초과(10MB), 허용 확장자(`.pdf`, `.docx` 등 18종), 허용 MIME 타입(16종) 순서로 검증. `DEFAULT_ALLOWED_EXTENSIONS`, `DEFAULT_ALLOWED_CONTENT_TYPES` 상수로 SSOT 관리. settings 오버라이드 가능.

---

#### S-C-03. commission 업로드 타입 검증 (registry SSOT)
- **판정**: ✅ 준수
- **점검 방법**: `commission/views/api_upload.py:72-92`
- **근거**: `SUPPORTED_UPLOAD_TYPES`는 `commission.upload_handlers.registry` 기반 자동 생성. `upload_type not in SUPPORTED_UPLOAD_TYPES`로 사전 필터 후, `get_upload_spec(upload_type)`으로 spec 조회. 미등록 타입은 `KeyError` → 400 반환.

---

#### S-C-04. 숫자/날짜 파라미터 파싱 안전성
- **판정**: ✅ 준수
- **점검 방법**: `board/views/worktasks.py:100-118`, `commission/views/api_collect.py:83`
- **근거**: `int()` 변환 시 `try/except ValueError`로 폴백 처리. `ym` 파라미터는 `len(ym) != 6 or not ym.isdigit()` 정규화 검증.

---

#### S-C-05. 경로 탈출(Path Traversal) 방어
- **판정**: 🟡 확인필요
- **점검 방법**: `board/services/attachments.py:96-98`, `accounts/views.py:118-125`
- **근거**: `_build_download_filename()`에서 `os.path.basename(raw)`로 경로 주입 방어. `_safe_upload_result_path()`에서 `UPLOAD_RESULT_DIR` 기준 부모 경로 검증. 단, commission `save_temp_upload()`는 FileSystemStorage 기반이므로 기본 Django 저장 정책 외 추가 경로 검증이 없는 점 확인 권장.

---

### S-D. CSRF 및 세션 보안

#### S-D-01. commission 엔드포인트 @csrf_exempt 적용 (규약 8)
- **판정**: 🔴 위반
- **점검 방법**: 전체 `.py`에서 `csrf_exempt` grep
- **근거**: `commission/views/api_upload.py:54`와 `commission/views/approval.py:92` 두 엔드포인트에 `@csrf_exempt`가 적용되어 있다. 두 뷰 모두 `@grade_required("superuser")`가 함께 적용되어 있어 로그인 우회는 불가하지만, CSRF 토큰 없이 cross-origin POST가 가능하다. 엑셀 파일 업로드(multipart)라도 CSRF 토큰 검증을 우회할 이유가 없다.
- **위반 파일**: `commission/views/api_upload.py:13,54`, `commission/views/approval.py:14,92`
- **권장 조치**: `@csrf_exempt` 제거. 프론트엔드 JavaScript에서 `getCsrf()` 헬퍼로 `X-CSRFToken` 헤더를 포함하거나, FormData multipart에 `csrfmiddlewaretoken` 필드를 포함하도록 수정.

---

#### S-D-02. 세션/CSRF 쿠키 보안 설정
- **판정**: ✅ 준수
- **점검 방법**: `web_ma/settings.py:316-336`
- **근거**: `SESSION_COOKIE_SECURE = IS_PROD`, `CSRF_COOKIE_SECURE = IS_PROD`. 운영 환경(`IS_PROD=True`)에서만 Secure 플래그 활성화. `SESSION_COOKIE_HTTPONLY = True`. `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`, `SESSION_COOKIE_AGE = 3600`. `SameSite=Lax` 설정.

---

#### S-D-03. ForcePasswordChangeMiddleware 등록 및 동작 (규약 5)
- **판정**: ✅ 준수
- **점검 방법**: `web_ma/settings.py:179`, `accounts/middleware/force_password_change.py`, `accounts/policies/password_policy.py`
- **근거**: `MIDDLEWARE` 리스트의 `AuthenticationMiddleware` 이후 위치에 `accounts.middleware.force_password_change.ForcePasswordChangeMiddleware` 등록. `should_enforce()`는 전역 토글(`FORCE_PASSWORD_CHANGE_ENABLED`, default=False), `must_change_password` 플래그, grade 예외, scope 범위를 순서대로 검증. URL whitelist(password_change/done/login/logout)로 무한 리다이렉트 방지. 단, `FORCE_PASSWORD_CHANGE_ENABLED`의 기본값이 `False`이므로 프로덕션에서 `.env.prod`에 명시 필요.

---

### S-E. 감사(Audit) 로그

#### S-E-01. ACTION.COMMISSION_EXCEL_UPLOAD 미정의로 AttributeError 발생
- **판정**: 🔴 위반
- **점검 방법**: `audit/constants.py` 전체 검색 + Python import 실행 확인
- **근거**: `commission/views/approval.py`의 6개 위치(lines 119, 131, 142, 177, 213, 226)에서 `ACTION.COMMISSION_EXCEL_UPLOAD`를 참조하지만, `audit/constants.py`에 이 상수가 정의되어 있지 않다 (`AttributeError: type object 'ACTION' has no attribute 'COMMISSION_EXCEL_UPLOAD'` 런타임 확인). 결재/효율성 엑셀 업로드의 audit 로그가 try/except 내부이므로 조용히 실패하지만, 감사 기록이 전혀 남지 않는다.
- **위반 파일**: `audit/constants.py` (누락), `commission/views/approval.py:119,131,142,177,213,226`
- **권장 조치**: `audit/constants.py`의 ACTION 클래스에 `COMMISSION_EXCEL_UPLOAD = "commission.excel.upload"` 추가. 또는 기존 `COMMISSION_UPLOAD_APPROVAL = "commission.upload.approval"` 상수를 사용하도록 `approval.py` 수정.

---

#### S-E-02. 로그인/로그아웃 audit 로그 기록
- **판정**: ✅ 준수
- **점검 방법**: `accounts/views.py:431-436`, `accounts/views.py:490-519`
- **근거**: 로그인 성공 시 `ACTION.AUTH_LOGIN_SUCCESS`, 실패 시 `ACTION.AUTH_LOGIN_FAIL`, 잠금 임계치 도달 시 `ACTION.AUTH_LOGIN_LOCKED`, 잠긴 계정 접근 시 `ACTION.AUTH_LOGIN_BLOCKED_LOCKED` 모두 기록. try/except 감싸서 audit 실패가 로그인을 차단하지 않도록 처리.

---

#### S-E-03. 비밀번호 변경/초기화 audit 로그
- **판정**: ✅ 준수
- **점검 방법**: `accounts/views.py:159-173`, `accounts/admin.py:401-411`, `accounts/admin.py:432-441`
- **근거**: 비밀번호 변경 완료 시 `ACTION.ACCOUNTS_PASSWORD_CHANGE_COMPLETED`, 관리자 초기화 시 `ACTION.ACCOUNTS_PASSWORD_RESET_UNLOCK`, must_change_password 해제 시 `ACTION.ACCOUNTS_PASSWORD_CHANGE_CLEARED`. 모두 try/except 패턴 준수.

---

#### S-E-04. grade 변경 audit 로그 미기록 (규약 10)
- **판정**: 🔴 위반
- **점검 방법**: `partner/views/subadmin.py`, `accounts/tasks.py` + `log_action` grep
- **근거**: `PARTNER_LEADER_ADD`, `PARTNER_LEADER_DELETE`, `ACCOUNTS_GRADE_UPDATE` 상수가 `audit/constants.py:70-71,83`에 정의되어 있지만, 어떤 파일에서도 `log_action()`에 이 상수들을 전달하지 않는다. `partner/views/subadmin.py`의 두 엔드포인트에서 실제 grade를 변경하지만 audit 기록 없음. 계정의 권한 등급 변경은 가장 중요한 보안 이벤트 중 하나다.
- **권장 조치**: `partner/views/subadmin.py`의 `ajax_add_sub_admin()` 및 `ajax_delete_subadmin()` 마지막 `JsonResponse` 반환 전에 `log_action()` 추가.

---

#### S-E-05. 첨부 다운로드 audit 로그
- **판정**: 🟡 확인필요
- **점검 방법**: `board/views/attachments.py:55-67`, `manual/views/attachment.py:123-128`, `board/views/worktasks.py:366-406`
- **근거**: `post_attachment_download`, `task_attachment_download`, `manual_attachment_download`는 모두 `log_action()` 기록. 단, `worktask_att_download`는 성공/실패 시 logger.warning 기록은 있지만 `log_action()`을 호출하지 않는다. WorkTask 첨부 다운로드의 공식 audit 기록이 없어 감사 추적 공백이 존재함.
- **권장 조치**: `board/views/worktasks.py:worktask_att_download`에 성공/실패 모두 `log_action(request, ACTION.TASK_ATTACHMENT_DOWNLOAD, ...)` 추가.

---

### S-F. 운영 환경 보안 설정

#### S-F-01. DEBUG/IS_PROD 제어 및 Fail-fast
- **판정**: ✅ 준수
- **점검 방법**: `web_ma/settings.py:87-113`
- **근거**: `IS_PROD = APP_ENV in ("prod", "production") and not DEBUG` 단일 정의. `APP_ENV=prod`에서 `DEBUG=True`이면 `RuntimeError` 즉시 발생. `APP_ENV=dev`에서 `DEBUG=False`로 runserver 실행 시 `RuntimeError` 발생. `SECRET_KEY`는 `config("SECRET_KEY")`로 `.env`에서 로드, 하드코딩 없음.

---

#### S-F-02. 보안 헤더 (HSTS, CSP, X-Frame-Options 등)
- **판정**: ✅ 준수
- **점검 방법**: `web_ma/settings.py:640-703`
- **근거**: `SECURE_SSL_REDIRECT = IS_PROD` (기본값), `SECURE_HSTS_SECONDS = 30일 (IS_PROD)`, `X_FRAME_OPTIONS = "DENY"`, `SECURE_CONTENT_TYPE_NOSNIFF = True`, `SECURE_REFERRER_POLICY = "same-origin"`, `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"`. CSP는 `SecurityHeadersMiddleware`를 통해 응용. `CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"` 커스텀 핸들러 등록.

---

#### S-F-03. 쿠키 도메인 및 SameSite 설정
- **판정**: ✅ 준수
- **점검 방법**: `web_ma/settings.py:324-334`
- **근거**: `SESSION_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN`은 `IS_PROD` 조건 내에서만 `.ma-support.kr`로 설정. `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_SAMESITE = "Lax"`. `CSRF_COOKIE_HTTPONLY = False` (JS 읽기용, 의도적 설정).

---

#### S-F-04. FORCE_PASSWORD_CHANGE_ENABLED 프로덕션 설정
- **판정**: 🟡 확인필요
- **점검 방법**: `web_ma/settings.py:253-258`
- **근거**: `FORCE_PASSWORD_CHANGE_ENABLED`의 기본값이 `False`이다. 미들웨어(`ForcePasswordChangeMiddleware`)는 등록되어 있고 코드 로직도 완성되어 있으나, `.env.prod`에서 `FORCE_PASSWORD_CHANGE_ENABLED=True`가 명시되지 않으면 기본 비밀번호 강제 변경 기능이 실제 운영에서 비활성화 상태가 된다. 또한 `FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES/PARTS/CHANNELS` 중 하나 이상이 설정되어야 `should_enforce()`가 `True`를 반환한다. 현재 `.env.prod` 파일 내용을 직접 확인할 수 없으므로 확인 필요.
- **권장 조치**: `.env.prod`에 `FORCE_PASSWORD_CHANGE_ENABLED=True`와 적절한 scope 설정이 되어 있는지 운영 팀과 확인. 전체 적용 시 `FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES`를 비워두면 scope가 없어 강제 안 됨 주의.

---

## 보안 개선 로드맵

### 🔴 즉시 조치 (이번 스프린트 내)

1. **[S-E-01] `COMMISSION_EXCEL_UPLOAD` 상수 추가**
   - `audit/constants.py`에 `COMMISSION_EXCEL_UPLOAD = "commission.excel.upload"` 추가
   - 또는 `commission/views/approval.py`에서 `ACTION.COMMISSION_UPLOAD_APPROVAL` 사용으로 수정
   - 결재/효율성 업로드 audit 기록 즉시 복구 가능

2. **[S-D-01] `@csrf_exempt` 제거**
   - `commission/views/api_upload.py`, `commission/views/approval.py`에서 `@csrf_exempt` 제거
   - 프론트엔드 JS에서 `X-CSRFToken` 헤더 또는 `csrfmiddlewaretoken` FormData 필드 포함 확인

3. **[S-B-05, S-E-04] grade 변경 audit 로그 추가**
   - `partner/views/subadmin.py:ajax_add_sub_admin()`: 성공 분기에 `log_action(request, ACTION.PARTNER_LEADER_ADD, obj=u, meta={...})`
   - `partner/views/subadmin.py:ajax_delete_subadmin()`: 성공 분기에 `log_action(request, ACTION.PARTNER_LEADER_DELETE, obj=target, meta={...})`

4. **[S-B-06] 계정 Excel 업로드 audit 로그 추가**
   - `accounts/tasks.py`의 `process_users_excel_task()` 완료 시 `log_action()` 추가 (request 없을 경우 `request=None` 허용)

### 🟠 단기 조치 (1~2주 내)

5. **[S-E-05] WorkTask 첨부 다운로드 audit 로그 추가**
   - `board/views/worktasks.py:worktask_att_download()`에 `log_action(request, ACTION.TASK_ATTACHMENT_DOWNLOAD, ...)` 추가

6. **[S-A-06] Board 첨부 업로드 검증 체인 명시적 확인**
   - `board/views/posts.py:435`, `board/views/tasks.py:335`에서 `save_attachments()` 람다 패턴이 실제로 `validate_board_attachment()`를 경유하는지 단위 테스트 추가

7. **[partner/views/grades.py] traceback.print_exc() → logger.exception() 교체**
   - `partner/views/grades.py:261,392`, `partner/views/structure.py:176,209,246`, `partner/views/ratetable.py:427,473`에서 `traceback.print_exc()` → `logger.exception(...)` 교체로 운영 로그 일원화

### 🟡 중기 조치 (이번 분기 내)

8. **[S-B-08] `request.POST.get("username")` 사용 패턴 문서화**
   - `accounts/views.py:280`의 `SessionCloseLoginView._extract_login_id()`에서 Django AuthenticationForm의 `username` 필드명 사용 의도를 주석으로 명시

9. **[S-F-04] ForcePasswordChange 프로덕션 활성화 확인**
   - `.env.prod`의 `FORCE_PASSWORD_CHANGE_ENABLED` 및 scope 설정 검토
   - 점진적 적용 플랜 수립 (branch/part 단위 순차 적용)

10. **[S-D-03] 관련 audit 로그 추가**
    - `accounts/views.py`의 강제 비밀번호 변경 리다이렉트 시 `log_action()` 추가 고려

### 🟢 모니터링

- **CSRF 실패**: `django.security.csrf` 로거 → `access.log`, 비정상 급증 시 알림 설정
- **WorkTask 소유자 불일치 시도**: `board/views/worktasks.py:worktask_att_download`의 `logger.warning` 모니터링
- **비밀번호 강제 변경 리다이렉트**: `accounts.access` 로거의 `PASSWORD_ENFORCE_REDIRECT` 건수 추적
- **업로드 실패 건수**: commission/accounts 업로드 에러 로그 주기적 확인
