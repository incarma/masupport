# django_ma CORE INFRA 통합 개발·보안·성능 체크리스트 FINAL

> 목적: `develop_core_infra.md`와 `develop(classfy)_core_infra.md`를 하나의 기준 문서로 통합하여, 추후 새 채팅에서 전체 소스코드와 기존 대화 컨텍스트를 모두 공유하지 않더라도 Core Infra 관련 보안 보완, 성능 개선, 운영 안정화, 코드 리팩토링을 일관된 기준으로 진행하기 위한 최종 지침서입니다.  
> 기준일: 2026-04-30  
> 적용 범위: `web_ma`, `accounts`, `audit`, 전역 `templates`, 전역 `static`, `ops/nginx`, 그리고 core infra 보안 정책에 직접 영향을 주는 `board`, `manual`, `partner`, `commission`, `dash` 일부 view/template/static 코드.

---

## 0. 이 문서를 사용하는 방법

새 채팅에서 Core Infra 관련 개발을 이어갈 때는 이 문서를 기준으로 다음 순서로 판단합니다.

1. 요청이 보안/성능/운영/리팩토링 중 어디에 해당하는지 분류합니다.
2. 등급을 `최상 → 상 → 중상 → 중 → 중하 → 하` 중 하나로 판정합니다.
3. 완료된 항목인지, 추가 진행이 필요한 항목인지 확인합니다.
4. 패치가 필요한 경우 기존 파일은 `diff`, 신규 파일은 `최종완성본`으로 작성합니다.
5. 패치 후 반드시 grep/check/collectstatic/권한 시나리오를 검증합니다.

---

## 1. 통합 기준 문서 출처

본 문서는 아래 두 문서를 통합·정리한 최종본입니다.

- `develop_core_infra.md`
  - 보안 취약점 체크리스트
  - 성능 개선 체크리스트
  - 즉시조치급 / 빠른 보완 / 운영 안정성 / 구조 개선 기준

- `develop(classfy)_core_infra.md`
  - 등급 기준: 최상, 상, 중상, 중, 중하, 하
  - 완료된 즉시조치급 패치 현황
  - CSP 2단계 패치 현황
  - 남은 보완 영역과 우선순위

---

## 2. Core Infra 적용 범위

```text
django_ma/
├─ web_ma/
│  ├─ settings.py
│  ├─ urls.py
│  ├─ views.py
│  ├─ middleware.py
│  ├─ celery.py
│  ├─ asgi.py
│  └─ wsgi.py
├─ accounts/
│  ├─ models.py
│  ├─ views.py
│  ├─ admin.py
│  ├─ tasks.py
│  ├─ urls.py
│  ├─ forms.py
│  ├─ search_api.py
│  ├─ decorators.py
│  ├─ custom_admin.py
│  ├─ middleware/force_password_change.py
│  ├─ policies/password_policy.py
│  └─ services/users_excel_import.py
├─ audit/
│  ├─ models.py
│  ├─ middleware.py
│  ├─ services.py
│  ├─ utils.py
│  ├─ constants.py
│  └─ admin.py
├─ templates/
│  ├─ base.html
│  ├─ no_permission_popup.html
│  ├─ landing/index.html
│  ├─ registration/*.html
│  ├─ admin/accounts/customuser/change_list.html
│  └─ components/search_user_modal.html
├─ static/
│  ├─ css/base.css
│  ├─ css/fixes.css
│  ├─ css/plugins/datatables.css
│  ├─ css/apps/*.css
│  ├─ css/admin/accounts_customuser.css
│  ├─ js/base_ui.js
│  ├─ js/login_page.js
│  ├─ js/datatable_config.js
│  ├─ js/excel_upload.js
│  ├─ js/common/*
│  └─ vendor/*
└─ ops/
   └─ nginx/default.conf
```

연관 앱 파일도 Core Infra 보안 정책에 직접 영향을 주면 이 문서의 대상입니다.

```text
board/views/attachments.py
board/views/worktasks.py
manual/views/attachment.py
manual/templates/manual/manual_detail.html
partner/views/efficiency.py
partner/views/esign.py
commission/views/downloads.py
commission/views/api_upload.py
commission/views/approval.py
dash/viewmods/api_upload.py
dash/viewmods/api_retention_upload.py
dash/templates/dash/*.html
```

---

## 3. 현재 완료된 핵심 보완사항

### 3.1 최상급 보안 패치 완료 항목

- [x] CSRF 실패 로그에서 cookie/token 원문 제거
- [x] CSRF 실패 로그 값 마스킹
- [x] Audit meta key 기반 민감정보 마스킹
- [x] `X-Forwarded-For`, `X-Real-IP` 신뢰 범위 검증
- [x] `AUDIT_TRUSTED_PROXY_CIDRS` 기반 trusted proxy만 proxy header 신뢰
- [x] accounts 업로드 결과 파일 owner 검증
- [x] accounts 결과 파일 `UPLOAD_RESULT_DIR` 외부 접근 차단
- [x] RequestLog에서 healthcheck/static/favicon/robots 제외
- [x] Response header에 `X-Request-ID` 세팅
- [x] CSP `unsafe-eval` 제거
- [x] CSP `object-src 'none'` 추가
- [x] `/media/` 직접 접근 Nginx 403 차단
- [x] `.file.url`, `.image.url` 실제 직접 사용 전수 점검 통과
- [x] Excel upload 결과 HTML escape 처리
- [x] fail download URL same-origin 검증
- [x] DataTables 컬럼 필터 제목 escape
- [x] dashboard `hideWarnById()` JS 변수 오류 수정 기준 확정

### 3.2 CSP 2단계 패치 완료 항목

- [x] `json_script` → `window.*` bridge 외부화
- [x] legacy `window.csrfToken` 주입 외부화
- [x] inline `onsubmit="return false"` 제거
- [x] approval upload validation inline script 제거
- [x] PDF 생성 polling inline script 제거
- [x] dash retention Chart.js CDN 제거
- [x] manage_calculate boot inline script 제거
- [x] manage_charts boot inline script 제거
- [x] manage_rate boot inline script 제거
- [x] common CSP-safe JS 기준 확정
  - `auto_submit_controls.js`
  - `confirm_submit.js`
  - `redirect_buttons.js`
  - `json_boot_bridge.js`
  - `csrf_window.js`
  - `prevent_form_submit.js`

### 3.3 CSP style 정리 완료 기준

최근 점검 명령 기준:

```powershell
rg "<style>|style=|onclick=|onsubmit=|onchange=" templates board manual partner commission dash `
  -g "*.html" `
  -g "!**/__pycache__/**"
```

마지막 잔여로 확인된 항목:

```text
templates/admin/accounts/customuser/change_list.html
6:<style>
```

완료 기준:

- 해당 `<style>` 내용을 `static/css/admin/accounts_customuser.css`로 이동
- 템플릿은 `{% block extrastyle %}`에서 외부 CSS 로드
- grep 결과 0건

---

## 4. 등급 체계

## 4.1 최상 Critical

### 정의

서비스 침해, 개인정보·파일·정산정보 유출, 인증/인가 우회, XSS 악용, 감사 로그 신뢰성 훼손으로 직접 이어질 수 있는 항목입니다.

### 판정 기준

다음 중 하나라도 해당하면 최상입니다.

- 권한 없는 사용자가 파일, 업로드 결과, 정산자료, 개인정보에 접근 가능
- 인증 없는 내부 API 접근 가능
- `/media/` 또는 `.file.url`로 객체 권한 검증 없이 파일 접근 가능
- XSS로 세션/CSRF/민감정보 탈취 가능
- proxy IP 위조로 감사로그 신뢰성 붕괴
- CSRF 실패/RequestLog/AuditLog에 cookie, token, password, 주민번호 등 원문 저장
- superuser/head/leader/basic 권한 scope가 서버에서 강제되지 않음
- 업로드 결과 token 또는 fail token이 사용자/세션/권한과 바인딩되지 않음

### 최상 체크리스트

#### 완료

- [x] `/media/` 직접 접근 차단
- [x] `.file.url`, `.image.url` 실제 직접 사용 제거
- [x] CSRF 실패 cookie 원문 로그 제거
- [x] Audit meta 민감 key 마스킹
- [x] XFF trusted proxy 검증
- [x] accounts upload result owner 검증
- [x] accounts result path traversal 차단
- [x] CSP `unsafe-eval` 제거
- [x] CSP inline script 주요 구간 외부화
- [x] dashboard JS 경고 표시 함수 오류 수정 기준 확정

#### 진행 필요

- [ ] `templates/admin/accounts/customuser/change_list.html` inline `<style>` 최종 제거 확인
- [ ] `style-src 'unsafe-inline'` 완전 제거 후 운영 CSP 적용
- [ ] commission fail token owner/session/권한 검증
- [ ] commission 다운로드 view 권한 데코레이터/스코프 전수 점검
- [ ] manual `b.content|safe` 제거 및 sanitize filter 적용
- [ ] `.file.url`, `.image.url` grep 결과가 주석 외 0건인지 CI/정기 점검화
- [ ] 모든 보호 파일 다운로드 view에 audit log 성공/실패 기록 확인

---

## 4.2 상 High

### 정의

직접적인 침해까지는 아니더라도 운영 장애, 대량 DB 부하, 대량 파일 누적, 배포 실패, 업로드 장애, 보안 취약점 확장 가능성이 큰 항목입니다.

### 판정 기준

- RequestLog가 트래픽 증가 시 DB write 병목 유발
- Excel 업로드가 대용량에서 timeout/메모리 폭증 유발
- Docker/Nginx/collectstatic 설정 오류가 배포 장애 유발
- 업로드 파일 크기/확장자/MIME 검증 누락
- 검색 API가 full scan으로 DB 부하 유발
- CDN 의존으로 CSP 또는 운영망 장애 발생
- `csrf_exempt`가 남아 있고 대체 CSRF 체계가 불명확

### 상 체크리스트

#### 완료

- [x] health/static/favicon/robots RequestLog 제외
- [x] dash retention Chart.js CDN 제거
- [x] Excel upload 결과 escape
- [x] fail download URL same-origin 검증
- [x] DataTables 컬럼 제목 escape
- [x] CSP vendor 로컬화 기준 확정

#### 진행 필요

- [ ] RequestLog retention/cleanup 정책 적용
- [ ] upload MIME/size 검증 전 앱 일관화
- [ ] dash upload 검증 보강
- [ ] partner upload 검증 보강
- [ ] commission upload 검증 보강
- [ ] Dockerfile collectstatic 실패 무시 제거 여부 점검
- [ ] Docker base image 버전 고정
- [ ] docker-compose 운영 bind mount 제거 검토
- [ ] redis/nginx latest 태그 제거
- [ ] landing/login fetch JSON non-JSON/403/500 방어 강화
- [ ] search API `icontains` 성능 개선 또는 index/검색전략 점검

---

## 4.3 중상 Moderate-High

### 정의

즉시 보안 사고 가능성은 낮지만 장기 운영 중 장애, 디스크 누적, 로그 비대화, Celery 재실행 중복 처리 등으로 이어질 수 있는 항목입니다.

### 판정 기준

- temp/result 파일 cleanup 없음
- RequestLog/AuditLog retention 없음
- Celery task idempotency 불명확
- cache key TTL 또는 owner binding 미흡
- DB index가 조회 패턴과 맞지 않음
- Audit meta 크기 제한 미흡

### 중상 체크리스트

#### 완료

- [x] Audit meta depth/items 제한
- [x] Audit meta key 기반 민감정보 마스킹
- [x] accounts cache result owner binding
- [x] Celery connection loss 관련 운영 기준 문서화

#### 진행 필요

- [ ] `UPLOAD_TEMP_DIR` cleanup task
- [ ] `UPLOAD_RESULT_DIR` cleanup task
- [ ] commission fail token cleanup/owner binding
- [ ] RequestLog retention task
- [ ] AuditLog retention task
- [ ] Celery task idempotency 전수 점검
- [ ] cleanup task 인자 방어
- [ ] beat schedule task 등록명과 실제 task name 일치 검증
- [ ] path/status/user index 효율 점검

---

## 4.4 중 Moderate

### 정의

현재 기능은 동작하지만 누적 시 성능 저하나 유지보수 비용을 증가시키는 항목입니다.

### 판정 기준

- signals에서 중복 DB 조회 발생
- SubAdminTemp sync 비효율
- DataTables destroy/reinit 과도
- 루프 내부 개별 query로 N+1 발생
- 공통 유틸이 있으나 일부 페이지 자체 구현 유지

### 중 체크리스트

#### 완료

- [x] 공통 fetch JSON 유틸 `readJsonOrThrow()` 기준 확정
- [x] 공통 CSRF 유틸 기준 확정
- [x] DataTables safe destroy/adjust 유틸 기준 확정
- [x] duplicate submit guard 패턴 기준 확정

#### 진행 필요

- [ ] signals DB 조회 최소화
- [ ] SubAdminTemp sync 최적화
- [ ] partner/manage_grades DataTables 초기화 비용 점검
- [ ] partner/manage_tables DataTables 정책 점검
- [ ] DataTables 자동 초기화 범위 제한
- [ ] `file_upload_utils.js` 전체 HTML 교체 방식 검토
- [ ] landing animation 코드 중복 제거
- [ ] build_affiliation 계열 N+1 가능성 점검
- [ ] fetch JSON 처리 공통화 잔여 페이지 점검

---

## 4.5 중하 Low-Mid

### 정의

보안·성능의 즉시 영향은 작지만 구조 일관성, 코드 탐색성, 패치 안정성을 떨어뜨리는 항목입니다.

### 판정 기준

- `admin.py`, `views.py` 과도하게 비대
- shim/lazy import가 많아 실제 호출 경로 파악 어려움
- submit lock/loading/toast/modal 처리 분산
- CSS selector 위치가 앱별/전역 경계를 오감
- template DOM 계약 문서화 부족

### 중하 체크리스트

#### 완료

- [x] Core Infra 주요 파일 위치 문서화
- [x] 공통 JS 유틸 기준 문서화
- [x] CSS 레이어 기준 문서화
- [x] CSP-safe 공통 JS 도입 기준 확정

#### 진행 필요

- [ ] accounts/admin.py 서비스 분리
- [ ] login view 책임 분리
- [ ] RequestLog async/batch 처리 검토
- [ ] submit lock 공통 유틸화
- [ ] base_ui.js 역할 정리
- [ ] legacy `main_admin/sub_admin` 문구/상수 잔재 제거
- [ ] template DOM id/dataset 계약 문서화 강화
- [ ] JS boot 패턴 미적용 페이지 정리

---

## 4.6 하 Low

### 정의

즉각적인 장애나 취약점은 아니지만 운영 품질과 유지보수성을 높이는 개선 영역입니다.

### 판정 기준

- 문서화 부족
- unused vendor/static 정리
- Docker image size 최적화
- 주석/파일명/버전 쿼리 정리
- 테스트 시나리오 문서화

### 하 체크리스트

#### 완료

- [x] Core Infra 운영 원칙 문서화
- [x] 보안/성능 등급 체계 문서화
- [x] grep 명령 및 검증 명령 문서화

#### 진행 필요

- [ ] unused vendor 제거
- [ ] Docker image 경량화
- [ ] static vendor version 일관성 정리
- [ ] 문서 최신화 자동화
- [ ] 보안 grep CI 자동화
- [ ] pytest 기반 permission/file download regression test 추가
- [ ] 운영 SOP와 개발 SOP 분리 정리

---

## 5. 주요 보안 정책별 상세 체크리스트

## 5.1 파일 접근 정책

### 절대 기준

- `.file.url` 직접 링크 금지
- `.image.url` 직접 링크 금지
- `/media/` 직접 접근 금지
- 다운로드는 보호 view + 권한 검증 + FileResponse
- 파일 다운로드는 audit log 대상

### 검증 명령

```powershell
rg "\.file\.url|\.image\.url" templates board manual partner commission dash `
  -g "*.html" -g "*.py" `
  -g "!**/__pycache__/**" `
  -g "!docs/**" `
  -g "!*.txt"
```

### 완료 기준

- 실제 href/src 또는 serializer URL에 `.file.url`, `.image.url` 없음
- 주석/문서성 문자열만 남는 경우 통과
- Nginx `/media/` 직접 접근 403

---

## 5.2 CSP 정책

### 절대 기준

금지:

- `<script>` inline logic
- `<style>` inline style block
- `style=`
- `onclick=`
- `onsubmit=`
- `onchange=`
- `unsafe-eval`
- 불필요한 외부 CDN

### 검증 명령

```powershell
rg "<style>|style=|onclick=|onsubmit=|onchange=" templates board manual partner commission dash `
  -g "*.html" `
  -g "!**/__pycache__/**"
```

### 진행 필요

- [ ] `templates/admin/accounts/customuser/change_list.html` inline style 제거 확인
- [ ] `style-src 'self'`로 전환 가능 여부 확인
- [ ] 외부 Daum postcode 사용 시 CSP 예외 여부 명확화
- [ ] Cloudflare beacon 필요 여부 결정

---

## 5.3 Audit / RequestLog 정책

### 완료된 기준

- querystring 마스킹
- 민감 key 기반 meta 마스킹
- X-Request-ID response header
- health/static/favicon/robots 제외
- body 저장 금지
- CSRF cookie/token 원문 로그 금지

### 진행 필요

- [ ] RequestLog retention
- [ ] AuditLog retention
- [ ] 대량 request에서 DB write 부하 측정
- [ ] RequestLog async/batch 도입 여부 검토
- [ ] 로그 보존기간 운영정책 확정

---

## 5.4 업로드 결과 / fail token 정책

### accounts 업로드 결과

완료 기준:

- task owner cache 검증
- result path `UPLOAD_RESULT_DIR` 내부 제한
- legacy owner 없는 task는 superuser만 fallback

### commission fail token

진행 필요:

- [ ] token payload에 `owner_id` 저장
- [ ] token payload에 필요 시 `session_key`, `grade`, `scope` 저장
- [ ] 다운로드 시 owner/권한 검증
- [ ] legacy owner 없는 token은 superuser만 fallback
- [ ] TTL 유지
- [ ] 실패 시 내부 정보 미노출

---

## 5.5 Manual sanitize 정책

### 위험 패턴

```django
{{ b.content|safe }}
```

### 권장 기준

```django
{% load manual_sanitize %}
{{ b.content|sanitize_manual_html }}
```

### 진행 필요

- [ ] `manual/templatetags/manual_sanitize.py` 기준 확인
- [ ] `script`, `style`, `on*`, `javascript:` 제거
- [ ] `span style` 제거
- [ ] Quill 허용 태그 allowlist 유지
- [ ] 기존 DB content sanitize management command 운영 여부 확인
- [ ] sanitize 후 화면 깨짐 회귀 테스트

---

## 6. 성능 개선 상세 체크리스트

## 6.1 DB / Query

- [ ] N+1 query 확인
- [ ] `select_related` 적용 가능 여부
- [ ] `prefetch_related` 적용 가능 여부
- [ ] 루프 내부 query 제거
- [ ] row-by-row save를 bulk 처리로 전환
- [ ] 대량 update 시 transaction 범위 확인
- [ ] 경쟁 조건이 있는 경우 `select_for_update()` 검토
- [ ] 검색 API `icontains` full scan 완화
- [ ] RequestLog path/status/ts index 점검

## 6.2 Celery

- [ ] task idempotency 확인
- [ ] connection loss 후 재실행 안전성 확인
- [ ] soft/hard time limit 적정성
- [ ] worker prefetch 설정 적정성
- [ ] batch size clamp
- [ ] progress cache TTL
- [ ] result cleanup
- [ ] beat schedule task name 일치 검증

## 6.3 Frontend

- [ ] 이벤트 중복 바인딩 방지
- [ ] BFCache 재진입 안전성
- [ ] `dataset.inited` 사용
- [ ] `dataset.bound` 사용
- [ ] `readJsonOrThrow()` 사용
- [ ] DataTables destroy/reinit 안정성
- [ ] Chart.js destroy 후 재렌더링
- [ ] inline style/class 토글 정책 준수

## 6.4 CSS

- [ ] 앱 전용 스타일이 `base.css`에 새지 않았는가
- [ ] `fixes.css`에 임시 앱 전용 스타일이 남지 않았는가
- [ ] `!important` 남용이 없는가
- [ ] DataTables 스타일 중복이 없는가
- [ ] partner/board/manual/commission/dash CSS scope 유지

---

## 7. 빠른 검색 명령

### 7.1 파일 직접 접근

```powershell
rg "\.file\.url|\.image\.url|MEDIA_URL|django\.views\.static\.serve|serve\(" .
```

### 7.2 CSP inline

```powershell
rg "<style>|style=|onclick=|onsubmit=|onchange=" templates board manual partner commission dash `
  -g "*.html" `
  -g "!**/__pycache__/**"
```

### 7.3 CSRF exempt

```powershell
rg "csrf_exempt" .
```

### 7.4 FileResponse

```powershell
rg "FileResponse" .
```

### 7.5 업로드 결과 / fail token

```powershell
rg "fail_token|upload_fail|CACHE_RESULT_PATH_PREFIX|result_path|UPLOAD_RESULT_DIR|UPLOAD_TEMP_DIR" .
```

### 7.6 로그 민감정보

```powershell
rg "HTTP_COOKIE|QUERY_STRING|password|token|session|csrftoken|resident|jumin|주민번호" audit accounts web_ma
```

### 7.7 legacy grade

```powershell
rg "main_admin|sub_admin" accounts partner board manual commission dash templates
```

---

## 8. 검증 명령

### Django

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --dry-run --noinput
```

### Celery

```bash
celery -A web_ma inspect registered
```

### Docker

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f celery
docker compose logs -f celery-beat
docker compose logs -f nginx
```

### Healthcheck

```bash
curl -i https://ma-support.kr/healthz
curl -i http://127.0.0.1/nginx-healthz
curl -i https://ma-support.kr/media/test.txt
```

기대:

```text
/healthz → 200 ok
/nginx-healthz → 200 ok
/media/test.txt → 403 Forbidden
```

---

## 9. 패치 작성 표준

Core Infra 패치 요청 시 답변 구조는 다음을 사용합니다.

### 9.1 변경 목적

- 1~2줄 요약

### 9.2 수정 파일 목록 + 영향도

| 파일 | 변경 내용 | 영향도 | 회귀 위험 |
|---|---|---|---|

### 9.3 기존 파일 diff

- 반드시 unified diff
- DOM id, dataset, URL name 임의 변경 금지
- 권한 스코프 임의 완화 금지

### 9.4 신규 파일 최종본

- 추가 리팩토링 필요 없도록 전체 코드 제공
- 주요 기능별 주석 포함
- import/export 명확화

### 9.5 회귀 위험 체크

- [ ] 권한 스코프 변경 여부
- [ ] URL reverse/name 변경 여부
- [ ] template DOM id/dataset 변경 여부
- [ ] 파일 다운로드 정책 위반 여부
- [ ] upload/cache/task contract 변경 여부
- [ ] DataTables 정책 영향 여부
- [ ] CSS 전역 누수 여부
- [ ] 운영 설정 영향 여부
- [ ] CSP 차단 가능성
- [ ] Celery task 등록명 변경 여부

### 9.6 검증 시나리오

- [ ] `python manage.py check`
- [ ] `python manage.py collectstatic --dry-run --noinput`
- [ ] 권한별 계정 테스트
- [ ] URL 직접 호출 테스트
- [ ] 업로드/다운로드 테스트
- [ ] 브라우저 console CSP 오류 확인
- [ ] 서버 로그 traceback 확인

---

## 10. 다음 단계 우선순위

### 1순위: CSP style 최종 마무리

- 등급: 최상~상
- 대상:
  - `templates/admin/accounts/customuser/change_list.html`
  - 전역 template grep 잔여
  - `web_ma/settings.py` CSP
- 완료 기준:
  - grep 출력 0건
  - `style-src 'self'`
  - 주요 화면 console CSP 오류 없음

### 2순위: commission fail token 보호

- 등급: 최상
- 대상:
  - `commission/views/utils_fail_excel.py`
  - `commission/views/downloads.py`
  - `commission/views/api_upload.py`
  - `commission/views/approval.py`
- 완료 기준:
  - owner_id/session_key/scope metadata
  - 다운로드 권한 검증
  - legacy fallback superuser 제한
  - audit log

### 3순위: cleanup/retention

- 등급: 중상~상
- 대상:
  - `web_ma/celery.py`
  - `accounts/tasks.py`
  - `commission/views/_files.py`
  - `audit/models.py`
- 완료 기준:
  - temp/result cleanup
  - RequestLog/AuditLog retention
  - beat schedule 등록
  - cleanup 인자 방어

### 4순위: upload validation 전수 보강

- 등급: 상
- 대상:
  - `commission/views/api_upload.py`
  - `commission/views/approval.py`
  - `dash/viewmods/api_upload.py`
  - `dash/viewmods/api_retention_upload.py`
  - `partner/views/efficiency.py`
  - `partner/views/ratetable.py`
- 완료 기준:
  - 크기 제한
  - 확장자 allowlist
  - MIME/content_type 검증
  - finally cleanup
  - audit success/fail

### 5순위: 구조/성능 리팩토링

- 등급: 중~중하
- 대상:
  - `accounts/admin.py`
  - `accounts/views.py`
  - `audit/middleware.py`
  - 공통 JS
  - DataTables 페이지
- 완료 기준:
  - 기능 변화 0
  - 중복 제거
  - SSOT 재사용
  - 테스트 시나리오 제시

---

## 11. 금지 패턴

- [ ] `/media/` 직접 서빙 허용
- [ ] `.file.url`, `.image.url` 직접 링크
- [ ] object permission 없이 FileResponse 반환
- [ ] `csrf_exempt` 신규 추가 또는 방치
- [ ] CSRF 실패 로그 cookie 원문 기록
- [ ] token/password/session/주민번호 원문 로그
- [ ] `X-Forwarded-For` 무조건 신뢰
- [ ] `DEBUG=True` 운영 임시 해결
- [ ] `main_admin/sub_admin` 신규 권한 판단
- [ ] `base.css`/`fixes.css`에 앱 전용 상세 스타일 추가
- [ ] Celery beat task명과 실제 task명 불일치
- [ ] URL name/DOM id/dataset 광역 변경
- [ ] CSP 강화 후 console 검증 생략
- [ ] token/task_id만으로 결과 파일 반환

---

## 12. 새 채팅 기본 전제

향후 새 채팅에서 Core Infra 개발을 이어갈 때 다음을 기본 전제로 봅니다.

1. settings SSOT는 `web_ma.settings`.
2. 운영은 Docker Compose + Nginx + Gunicorn/Uvicorn + Redis + Celery + PostgreSQL.
3. `/media/` 직접 접근 금지.
4. 파일 다운로드는 보호 view + 권한 검증 + FileResponse.
5. 권한 등급은 `superuser/head/leader/basic/resign/inactive`.
6. `main_admin/sub_admin`은 legacy.
7. CSP 목표는 `script-src 'self'`, `style-src 'self'`.
8. inline script/style/event handler는 금지.
9. accounts upload result는 owner 검증 완료 기준.
10. commission fail token은 다음 Critical 후보.
11. manual stored HTML은 sanitize 필요.
12. audit log는 민감정보 마스킹과 request_id 연결 필요.
13. 프론트는 dataset boot, safe binding, CSRF utility, `readJsonOrThrow`, duplicate submit guard를 기본 패턴으로 사용.
14. CSS는 base/plugins/fixes/apps 레이어를 유지.
15. 기존 파일 수정은 diff, 신규 파일은 최종본으로 제시.
16. 패치 후 grep/check/collectstatic/권한 테스트를 제시.

---

END
