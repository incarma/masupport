# django_ma CORE INFRA 성능·보안 등급 분류 지침서

> 기준 버전: 2026-04-30  
> 반영 범위: `guide_core_infra.md`, `develop_core_infra.md`, 기존 `develop(classfy)_core_infra.md`, 그리고 최근 완료된 CORE INFRA 즉시조치급/CSP 2단계 패치 결과

---

## 1. 문서 목적

본 문서는 `django_ma` 프로젝트의 CORE INFRA 영역에서 발견되는 보안, 성능, 운영 안정성, 구조 개선 이슈를 일관된 기준으로 분류하기 위한 등급 기준서이다.

이 문서는 다음 상황에서 사용한다.

- 신규 취약점 또는 성능 이슈의 우선순위 판단
- 패치 전 영향도/회귀 위험 분류
- 패치 후 완료/잔여 항목 구분
- 운영 점검 체크리스트 작성
- 새 채팅에서 추가 설명 없이 core infra 개선 흐름을 이어가기 위한 기준 문서

---

## 2. 적용 범위

본 등급 분류 기준은 다음 영역에 적용한다.

```text
web_ma/
├─ settings.py
├─ urls.py
├─ views.py
├─ middleware.py
├─ celery.py
├─ asgi.py
└─ wsgi.py

accounts/
├─ models.py
├─ views.py
├─ admin.py
├─ tasks.py
├─ urls.py
├─ forms.py
├─ search_api.py
├─ decorators.py
├─ custom_admin.py
├─ middleware/force_password_change.py
├─ policies/password_policy.py
└─ services/users_excel_import.py

audit/
├─ models.py
├─ middleware.py
├─ services.py
├─ utils.py
├─ constants.py
└─ admin.py

templates/
├─ base.html
├─ landing/index.html
├─ registration/*.html
└─ components/search_user_modal.html

static/
├─ css/base.css
├─ css/fixes.css
├─ css/plugins/datatables.css
├─ js/base_ui.js
├─ js/login_page.js
├─ js/datatable_config.js
├─ js/excel_upload.js
├─ js/common/*
└─ vendor/*

ops/
└─ nginx/default.conf
```

연관 앱 파일도 core infra 보안 정책에 직접 영향을 주는 경우 본 문서의 분류 대상에 포함한다.

예:

```text
board/views/attachments.py
manual/views/attachment.py
partner/views/efficiency.py
partner/views/esign.py
commission/views/downloads.py
dash/viewmods/api_upload.py
```

---

## 3. 현재 패치 반영 상태 요약

### 3.1 완료된 CORE INFRA 즉시조치급 패치

아래 항목은 최신 기준에서 완료된 것으로 본다.

| 구분 | 항목 | 현재 상태 | 기준 파일 |
|---|---|---|---|
| 로그 보안 | `csrf_failure` 쿠키 원문 로그 제거 | 완료 | `accounts/views.py` |
| 로그 보안 | CSRF 실패 로그 값 마스킹 | 완료 | `accounts/views.py`, `audit/utils.py` |
| IP 신뢰 | `X-Forwarded-For` 신뢰 범위 검증 | 완료 | `audit/utils.py`, `web_ma/settings.py` |
| 파일 권한 | 계정 업로드 결과 파일 owner 검증 | 완료 | `accounts/views.py`, `accounts/admin.py` |
| 파일 경로 | `UPLOAD_RESULT_DIR` 외부 결과 파일 차단 | 완료 | `accounts/views.py`, `accounts/admin.py` |
| RequestLog | healthcheck/static/favicon/robots 제외 | 완료 | `audit/middleware.py`, `web_ma/settings.py` |
| RequestLog | Response `X-Request-ID` 세팅 | 완료 | `audit/middleware.py` |
| Audit meta | 민감 key 기반 meta 값 마스킹 | 완료 | `audit/services.py`, `audit/utils.py` |
| CSP | `unsafe-eval` 제거 | 완료 | `web_ma/settings.py` |
| CSP | `object-src 'none'` 추가 | 완료 | `web_ma/settings.py` |
| Front XSS | `excel_upload.js` 결과 HTML escape | 완료 | `static/js/excel_upload.js` |
| Front XSS | fail download URL same-origin 검증 | 완료 | `static/js/excel_upload.js` |
| Front XSS | DataTables 컬럼 필터 제목 escape | 완료 | `static/js/datatable_config.js` |

### 3.2 완료된 CSP 2단계 패치

아래 항목은 최신 기준에서 완료된 것으로 본다.

| 구분 | 항목 | 현재 상태 | 기준 파일 |
|---|---|---|---|
| CSP script | `json_script` → `window.*` bridge 외부화 | 완료 | `static/js/common/json_boot_bridge.js` |
| CSP script | legacy `window.csrfToken` 주입 외부화 | 완료 | `static/js/common/csrf_window.js` |
| CSP script | inline `onsubmit="return false"` 제거 | 완료 | `static/js/common/prevent_form_submit.js`, `partner/templates/partner/esign_confirm.html` |
| CSP script | approval upload validation inline script 제거 | 완료 | `static/js/commission/approval_upload_validation.js` |
| CSP script | PDF 생성 polling inline script 제거 | 완료 | `static/js/partner/pdf_processing.js` |
| CSP vendor | dash retention Chart.js CDN 제거 | 완료 | `dash/templates/dash/dash_retention.html` |
| CSP boot | manage_calculate boot inline script 제거 | 완료 | `partner/templates/partner/manage_calculate.html` |
| CSP boot | manage_charts boot inline script 제거 | 완료 | `partner/templates/partner/manage_charts.html` |
| CSP boot | manage_rate boot inline script 제거 | 완료 | `partner/templates/partner/manage_rate.html` |

### 3.3 아직 남은 주요 보완 영역

아래 항목은 다음 단계 후보이다.

| 구분 | 항목 | 등급 | 상태 |
|---|---|---:|---|
| CSP style | `style-src 'unsafe-inline'` 제거 | 최상~상 | 진행 예정 |
| CSP style | 템플릿 `style=""`, `<style>` 외부 CSS화 | 최상~상 | 진행 예정 |
| 파일 lifecycle | `UPLOAD_TEMP_DIR`, `UPLOAD_RESULT_DIR`, fail token cleanup | 중상~상 | 진행 예정 |
| Commission | fail token owner/session 바인딩 | 최상 | 진행 예정 |
| Commission | 다운로드 view 권한 데코레이터/스코프 점검 | 최상 | 진행 예정 |
| Dash | 업로드 파일 크기/확장자/MIME 검증 | 상 | 진행 예정 |
| Partner | 일부 업로드 MIME/size 검증 보강 | 상 | 진행 예정 |
| Manual | `b.content|safe` sanitize 정책 점검 | 최상~상 | 진행 예정 |
| RequestLog | retention/cleanup 정책 | 중상 | 진행 예정 |
| Docker | 이미지 태그/collectstatic/운영 bind mount 점검 | 상~중상 | 진행 예정 |

---

## 4. 등급 체계 정의

### 4.1 🔴 최상 Critical

#### 정의

서비스 침해, 개인정보·파일·정산정보 유출, 인증/인가 우회, 파일 접근 권한 실패, XSS 악용 가능성이 직접적인 항목이다.

#### 판정 기준

다음 중 하나라도 해당하면 최상으로 분류한다.

- 권한 없는 사용자가 파일, 업로드 결과, 정산자료, 개인정보에 접근 가능
- 인증 없는 내부 API 접근 가능
- `/media/` 또는 `.file.url`로 객체 권한 검증 없이 파일 직접 접근 가능
- XSS로 세션/CSRF/민감정보 탈취 가능
- Proxy IP 위조로 감사로그 신뢰성이 깨짐
- CSRF 실패/RequestLog/AuditLog에 cookie, token, password, 주민번호 등 민감정보가 원문 저장됨
- superuser/head/leader/basic scope가 서버에서 강제되지 않음
- 업로드 결과 token 또는 fail token이 사용자/세션/권한과 바인딩되지 않아 타인이 다운로드 가능

#### 대표 항목

| 항목 | 현재 상태 | 기준 |
|---|---|---|
| `/media/` 직접 접근 | 운영 Nginx 403 기준 유지 | `ops/nginx/default.conf` |
| `.file.url` 직접 링크 | board/manual/partner 주요 파일은 보호 view 기준 | 각 앱 template/view |
| 계정 업로드 결과 권한 | 완료 | owner cache + result path 검증 |
| `X-Forwarded-For` 무조건 신뢰 | 완료 | trusted proxy CIDR만 신뢰 |
| `csrf_failure` cookie 원문 로그 | 완료 | cookie는 `***` |
| CSP `unsafe-eval` | 완료 | 제거됨 |
| inline script | 주요 partner/commission/pdf/dash retention 완료 | 추가 전수 점검 필요 |
| `style-src 'unsafe-inline'` | 미완료 | 다음 단계 |
| commission fail token owner 검증 | 미완료 | 다음 최상 후보 |

#### 완료 처리 기준

최상 항목은 다음 조건을 모두 만족해야 완료로 본다.

- 서버 측 권한 검증이 존재한다.
- URL 직접 호출로도 차단된다.
- 파일은 `FileResponse`로만 제공된다.
- 로그에 민감정보가 남지 않는다.
- 템플릿/JS에서 직접 URL 또는 inline 위험 경로가 제거된다.
- 권한 실패/파일 없음/실패 다운로드 시 내부 경로를 노출하지 않는다.

---

### 4.2 🟠 상 High

#### 정의

직접적인 데이터 유출까지는 아니더라도 운영 장애, 대량 DB 부하, 대량 파일 누적, 대량 업로드 성능 저하, 보안 취약점으로 확장될 가능성이 큰 항목이다.

#### 판정 기준

- RequestLog가 트래픽 증가 시 DB write 병목을 만들 수 있음
- Excel 업로드가 대용량에서 timeout/메모리 폭증을 유발할 수 있음
- Docker/Nginx/collectstatic 설정 오류가 배포 장애를 유발할 수 있음
- 업로드 파일 크기/확장자/MIME 검증이 일부 앱에 없음
- 검색 API가 full scan으로 DB 부하를 유발함
- CDN 의존으로 CSP 또는 운영망 장애가 발생할 수 있음
- `csrf_exempt`가 남아 있고 대체 CSRF 체계가 불명확함

#### 대표 항목

| 항목 | 현재 상태 | 비고 |
|---|---|---|
| RequestLog DB write 부하 | 일부 완화 | health/static 제외 완료, retention 미완료 |
| Excel row-by-row 처리 | 앱별 상이 | dash/commission/accounts 전수 점검 필요 |
| Dash upload 파일 검증 | 미완료 | 크기/확장자/MIME 필요 |
| Partner upload MIME/size | 일부 미완료 | efficiency confirm, ratetable 등 |
| Docker collectstatic 실패 무시 | 점검 필요 | 운영 배포 후보 |
| Docker latest tag | 점검 필요 | redis/nginx tag 고정 후보 |
| dash retention CDN Chart.js | 완료 | 로컬 vendor 전환 |

#### 완료 처리 기준

- 대량 트래픽/대량 업로드에서 장애 가능성을 낮춘다.
- 실패 시 서버가 명확한 오류를 남긴다.
- 파일·업로드·로그 lifecycle이 관리된다.
- 운영 배포가 재현 가능하다.

---

### 4.3 🟡 중상 Moderate-High

#### 정의

즉시 보안 사고 가능성은 낮지만 장기 운영 중 장애, 디스크 누적, 로그 비대화, Celery 재실행 중복 처리 등으로 이어질 수 있는 항목이다.

#### 판정 기준

- temp/result 파일 cleanup이 없음
- RequestLog/AuditLog retention 정책이 없음
- Audit meta 크기/깊이/개수 제한이 미흡함
- Celery task idempotency가 불명확함
- cache key TTL 또는 owner 바인딩이 미흡함
- DB index가 조회 패턴과 맞지 않음

#### 대표 항목

| 항목 | 현재 상태 | 비고 |
|---|---|---|
| Audit meta 크기 제한 | 완료 | depth/items 제한 + key masking |
| Upload temp/result cleanup | 미완료 | Celery beat 후보 |
| RequestLog retention | 미완료 | cleanup task 후보 |
| Celery idempotency | 일부 기준화 | board/dash/commission 전수 점검 필요 |
| cache result owner | accounts 완료 | commission fail token 미완료 |

#### 완료 처리 기준

- cleanup/retention 정책이 있다.
- Celery 재실행 시 중복/파손이 없다.
- 로그/파일/캐시가 무기한 누적되지 않는다.

---

### 4.4 🟢 중 Moderate

#### 정의

현재 기능은 동작하지만 누적 시 성능 저하나 유지보수 비용을 증가시키는 항목이다.

#### 판정 기준

- signals에서 중복 DB 조회가 발생함
- SubAdminTemp sync가 비효율적임
- 화면별 JS에서 DataTables destroy/reinit이 과도함
- 루프 내부 개별 query로 N+1이 발생함
- 공통 유틸이 있으나 일부 페이지가 자체 구현을 계속 사용함

#### 대표 항목

| 항목 | 현재 상태 | 비고 |
|---|---|---|
| SubAdminTemp sync 비효율 | 점검 후보 | accounts/partner 연동 |
| DataTables 재초기화 비용 | 점검 후보 | partner/manage_grades, manage_tables |
| build_affiliation N+1 | 점검 후보 | partner/views/utils.py |
| fetch JSON 처리 중복 | 일부 개선 | common/manage/http.js 우선 |

---

### 4.5 🔵 중하 Low-Mid

#### 정의

보안·성능에 즉시 영향은 작지만 구조 일관성, 코드 탐색성, 패치 안정성을 떨어뜨리는 항목이다.

#### 판정 기준

- admin.py 또는 views.py가 과도하게 비대함
- shim/lazy import가 많아 실제 호출 경로 파악이 어려움
- JS submit lock, loading, toast, modal 처리가 분산됨
- CSS selector 위치가 앱별/전역 경계를 오감
- 템플릿의 DOM 계약 문서화가 부족함

#### 대표 항목

| 항목 | 현재 상태 | 비고 |
|---|---|---|
| admin.py 비대화 | 남음 | 장기 서비스 분리 후보 |
| fetch JSON 처리 중복 | 일부 남음 | 공통화 지속 |
| submit lock 분산 | 일부 남음 | 공통 유틸 후보 |
| legacy grade 문구 | 일부 남음 | main_admin/sub_admin 잔재 정리 |

---

### 4.6 ⚪ 하 Low

#### 정의

즉각적인 장애나 취약점으로 보기 어렵지만 운영 품질과 유지보수성을 높이는 개선 영역이다.

#### 판정 기준

- 문서화 부족
- unused vendor/static 정리
- Docker image size 최적화
- 주석/파일명/버전 쿼리 정리
- 테스트 시나리오 문서화

#### 대표 항목

| 항목 | 현재 상태 | 비고 |
|---|---|---|
| vendor unused 제거 | 점검 후보 | CSP/local vendor 이후 정리 |
| Docker image 최적화 | 점검 후보 | slim/cache layer |
| 설정 문서화 | 지속 보완 | guide_core_infra.md와 동기화 |

---

## 5. 최신 Critical 항목 상태표

### 5.1 완료된 Critical

| Critical 항목 | 완료 여부 | 근거 |
|---|---:|---|
| `csrf_failure` 로그 쿠키 마스킹 | 완료 | cookie 원문 제거, reason/path/UA 등 mask 적용 |
| `X-Forwarded-For` 신뢰 검증 | 완료 | `AUDIT_TRUSTED_PROXY_CIDRS` 기반 |
| accounts 업로드 결과 파일 권한 검증 | 완료 | owner cache + fallback 제한 |
| accounts 결과 파일 path traversal 차단 | 완료 | `UPLOAD_RESULT_DIR` 내부만 허용 |
| Audit meta 민감 key 마스킹 | 완료 | `is_sensitive_key()` 적용 |
| `unsafe-eval` 제거 | 완료 | CSP default에서 제거 |
| 주요 inline script 외부화 | 완료 | boot bridge, csrf bridge, pdf polling, validation |
| dash retention CDN 제거 | 완료 | local vendor Chart.js |

### 5.2 남은 Critical 후보

| Critical 후보 | 이유 | 우선 확인 파일 |
|---|---|---|
| `style-src 'unsafe-inline'` 제거 | inline style 기반 XSS 방어 완성 필요 | `web_ma/settings.py`, `templates/**/*.html`, `static/css/*` |
| commission fail token 권한 검증 | token만 알면 실패 엑셀 다운로드 가능 | `commission/views/utils_fail_excel.py`, `commission/views/downloads.py`, `api_upload.py`, `approval.py` |
| commission 다운로드 권한 검증 | 정산/수수료 데이터 다운로드 scope 필요 | `commission/views/downloads.py` |
| manual `b.content|safe` sanitize | 저장 HTML XSS 가능성 | `manual/templates/manual/manual_detail.html`, manual block 저장 view/service |
| `.file.url` 잔존 | 객체 권한 없는 파일 접근 가능성 | 전체 template grep |

---

## 6. 최신 High 항목 상태표

| High 항목 | 현재 상태 | 다음 조치 |
|---|---|---|
| RequestLog 과다 저장 | health/static 제외 완료 | retention/cleanup 설계 |
| Excel 대량 업로드 성능 | 앱별 상이 | accounts/commission/dash bulk 처리 점검 |
| upload MIME/size 검증 | board/manual 일부 완료, dash/partner/commission 일부 미완료 | 앱별 SSOT 검증 추가 |
| Docker 운영 안전성 | 점검 필요 | collectstatic, base image, latest tag, bind mount |
| landing/login fetch JSON 방어 | 일부 미완료 | non-JSON/403/500 처리 강화 |
| DataTables full init 비용 | 점검 필요 | 페이지별 제한 |

---

## 7. 최신 Moderate-High 항목 상태표

| Moderate-High 항목 | 현재 상태 | 다음 조치 |
|---|---|---|
| Audit meta 크기 제한 | 완료 | settings 기반 민감키 확장 검토 |
| temp/result 파일 cleanup | 미완료 | Celery cleanup task |
| RequestLog/AuditLog retention | 미완료 | 주기 삭제/보존기간 설정 |
| Celery idempotency | 일부 구현 | task별 재실행 안전성 점검 |
| cache TTL/owner 바인딩 | accounts 완료, commission 미완료 | commission fail token 보강 |

---

## 8. 패치 전 등급 판정 절차

새 이슈를 발견하면 아래 순서로 등급을 결정한다.

### 8.1 1차 질문

1. 권한 없는 사용자가 데이터/파일/정산정보에 접근할 수 있는가?
2. 인증 없이 내부 API를 호출할 수 있는가?
3. 로그에 민감정보가 원문으로 남는가?
4. XSS/CSRF/세션 탈취로 이어질 수 있는가?
5. 운영에서 장애 또는 대량 부하를 유발할 수 있는가?
6. 장기적으로 디스크/DB/캐시가 누적되는가?
7. 단순 구조·문서·중복 개선인가?

### 8.2 판정 흐름

```text
데이터 유출/권한 우회/파일 직접 접근/XSS 가능
→ Critical

운영 장애/대량 부하/업로드 장애/배포 실패 가능
→ High

장기 누적/cleanup 없음/retention 없음/Celery 재실행 위험
→ Moderate-High

성능 저하/N+1/중복 query/프론트 재렌더 비용
→ Moderate

구조 중복/SSOT 미준수/파일 분리 필요
→ Low-Mid

문서화/unused 제거/미세 최적화
→ Low
```

---

## 9. CORE INFRA 패치 표준 산출물

CORE INFRA 패치 요청 시 반드시 아래 형식을 따른다.

### 9.1 변경 목적

- 1~2줄로 보안/성능/운영 목적 설명

### 9.2 수정 파일 목록 + 영향도

| 파일 | 변경 내용 | 영향도 | 회귀 위험 |
|---|---|---|---|
| 예: `web_ma/settings.py` | CSP 조정 | 운영 전체 | 높음 |

### 9.3 diff patch

- 기존 파일은 unified diff로 제시한다.
- 신규 파일은 최종 완성본 형태로 제시한다.
- URL name, DOM id, dataset, 권한 스코프를 임의 변경하지 않는다.

### 9.4 회귀 위험 체크

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

### 9.5 검증 명령

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --dry-run --noinput
```

필요 시:

```bash
celery -A web_ma inspect registered
```

---

## 10. 다음 단계 우선순위 제안

### 10.1 1순위: CSP style 정리

#### 등급

```text
Critical ~ High
```

#### 이유

- `script-src 'self'` 대응은 상당 부분 완료됨
- 아직 `style-src 'self' 'unsafe-inline'`이 남아 있음
- 템플릿에 `style=""`, `<style>` 블록이 다수 존재

#### 우선 확인 파일

```text
templates/base.html
templates/registration/login.html
templates/registration/password_change_form.html
templates/registration/password_change_done.html
templates/landing/index.html
partner/templates/partner/*.html
commission/templates/commission/*.html
dash/templates/dash/*.html
manual/templates/manual/*.html
static/css/base.css
static/css/fixes.css
static/css/apps/*.css
```

#### 완료 기준

- `<style>` 블록 제거
- `style=""` 제거 또는 최소화
- CSS class로 외부화
- `style-src 'unsafe-inline'` 제거 가능 상태 확보

### 10.2 2순위: commission fail token 보호

#### 등급

```text
Critical
```

#### 이유

- 업로드 실패 엑셀은 사용자 식별자/스코프 제외 정보 포함 가능
- token만으로 다운로드 가능하면 권한 우회 위험

#### 우선 확인 파일

```text
commission/views/utils_fail_excel.py
commission/views/downloads.py
commission/views/api_upload.py
commission/views/approval.py
commission/urls.py
static/js/excel_upload.js
```

#### 완료 기준

- token payload에 owner_id/session_key/grade/scope metadata 저장
- 다운로드 시 로그인/권한/owner 검증
- token TTL 유지
- 실패 시 404 또는 권한 오류로 내부 정보 미노출

### 10.3 3순위: upload cleanup/retention

#### 등급

```text
Moderate-High ~ High
```

#### 우선 확인 파일

```text
web_ma/settings.py
web_ma/celery.py
accounts/tasks.py
accounts/views.py
accounts/admin.py
commission/views/_files.py
commission/views/utils_fail_excel.py
audit/models.py
audit/middleware.py
```

#### 완료 기준

- temp/result 파일 cleanup task
- RequestLog/AuditLog retention task
- beat_schedule 등록명과 실제 task name 일치
- cleanup 인자 방어

### 10.4 4순위: upload validation 전수 보강

#### 등급

```text
High
```

#### 우선 확인 파일

```text
commission/views/api_upload.py
commission/views/approval.py
commission/views/_files.py
dash/viewmods/api_upload.py
dash/viewmods/api_retention_upload.py
partner/views/efficiency.py
partner/views/ratetable.py
```

#### 완료 기준

- 파일 크기 제한
- 확장자 allowlist
- MIME/content_type 검증
- temp 저장명 안전화
- finally cleanup
- audit log 성공/실패 기록

---

## 11. 금지 패턴

아래 패턴은 등급과 무관하게 금지한다.

- `/media/` 직접 서빙 허용
- `.file.url` 직접 링크
- 파일 다운로드를 권한 검증 없이 `FileResponse`로 제공
- `csrf_exempt`를 이유 없이 유지 또는 신규 추가
- CSRF 실패 로그에 cookie 원문 기록
- Audit meta에 password/token/session/주민번호/전화번호 원문 기록
- `X-Forwarded-For`를 무조건 신뢰
- `DEBUG=True`로 운영 문제 임시 해결
- `main_admin/sub_admin`을 신규 권한 판단 기준으로 사용
- `base.css`/`fixes.css`에 앱 전용 스타일 추가
- Celery beat task명을 실제 등록명과 다르게 작성
- URL name/DOM id/dataset을 광범위하게 변경
- CSP 강화를 적용하면서 영향 페이지 검증을 생략

---

## 12. 빠른 검색어

### 12.1 파일 직접 접근

```bash
rg "\.file\.url|\.image\.url|MEDIA_URL|django\.views\.static\.serve|serve\(" .
```

### 12.2 inline script/style

```bash
rg "<script>|<style>|style=|onclick=|onsubmit=|onchange=" templates static
```

### 12.3 CSRF exempt

```bash
rg "csrf_exempt" .
```

### 12.4 FileResponse

```bash
rg "FileResponse" .
```

### 12.5 업로드 결과/fail token

```bash
rg "fail_token|upload_fail|CACHE_RESULT_PATH_PREFIX|result_path|UPLOAD_RESULT_DIR|UPLOAD_TEMP_DIR" .
```

### 12.6 로그 민감정보

```bash
rg "HTTP_COOKIE|QUERY_STRING|password|token|session|csrftoken|resident|jumin|주민번호" audit accounts web_ma
```

---

## 13. 등급별 적용 원칙 요약

| 등급 | 처리 기준 | 패치 형태 |
|---|---|---|
| Critical | 즉시 조치 | 기능 변화 최소 diff, 권한/로그/파일 보안 우선 |
| High | 빠른 보완 | 운영 장애 예방, 대량 처리 안정화 |
| Moderate-High | 계획 수립 후 보완 | cleanup/retention/idempotency 중심 |
| Moderate | 리팩토링 후보 | 성능/중복/N+1 개선 |
| Low-Mid | 구조 개선 후보 | SSOT화, 모듈화, 문서화 |
| Low | 선택 개선 | 최적화, unused 제거, 안내 보강 |

---

## 14. 최신 결론

현재 CORE INFRA는 다음 상태로 본다.

```text
Critical 1차 보안 패치: 완료
CSP script 2단계 패치: 완료
CSP style 정리: 진행 예정
commission fail token 보호: 진행 예정
upload cleanup/retention: 진행 예정
upload validation 전수 보강: 진행 예정
```

따라서 다음 보안 패치 우선순위는 아래 순서가 적절하다.

1. `style-src 'unsafe-inline'` 제거를 위한 inline style 외부화
2. commission fail token owner/session/권한 검증
3. upload temp/result cleanup + RequestLog/AuditLog retention
4. dash/commission/partner upload validation 전수 보강
5. Docker/Nginx 운영 안전성 추가 점검

---

END
