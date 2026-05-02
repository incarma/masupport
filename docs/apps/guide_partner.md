# partner 앱 개발 가이드

> 외부 LLM이 전체 코드 없이 이 앱을 정확하게 디벨롭할 수 있도록 작성된 문서다.
> 실제 파일명 · 함수명 · id명을 그대로 사용한다.

---

## 1. 앱 책임 요약

`partner`는 **편제변경(StructureChange) · 요율변경(RateChange) · 지점효율(EfficiencyChange) · 권한관리(SubAdminTemp) · 전자서명(EfficiencySignRequest)** 을 통합 관리하는 파트너 운영 플랫폼이다.  
모든 변경 이력은 `PartnerChangeLog`와 `audit.log_action()`으로 이중 기록되며, 파일 업로드(Excel·확인서·PDF)와 SSOT 기반 권한 스코프(`resolve_branch_for_query`)로 데이터 접근을 제어한다.  
전자서명은 `EfficiencySignRequest → EfficiencyConfirmSign` 체계로 운영되며, 서명 완료 시 ReportLab으로 PDF를 자동 생성한다.

---

## 2. 디렉터리 구조

```
partner/
├── __init__.py
├── admin.py                        # admin_esign.py 위임 (from partner.admin_esign import *)
├── admin_esign.py                  # EfficiencySignRequest Admin (list_display, 색상 배지, PDF 링크)
├── apps.py                         # PartnerConfig
├── models.py                       # 11개 모델 정의
├── urls.py                         # 50개+ URL (app_name="partner")
├── views_shim.py                   # views/ 패키지 호환성 shim (레거시 import 지원)
├── tests.py                        # (stub)
├── management/commands/
│   └── sync_subadmin_temp.py      # SubAdminTemp 수동 동기화 명령
├── migrations/                     # 0001_initial ~ 0021 (총 21개)
├── services/
│   ├── __init__.py
│   ├── esign_service.py            # 전자서명 비즈니스 로직 SSOT (sign_request 생성·완료·조회)
│   └── pdf_service.py              # ReportLab 기반 PDF 생성 서비스
├── templates/partner/
│   ├── esign_confirm.html          # 전자서명 확인서 페이지
│   ├── manage_calculate.html       # 지점효율 관리 페이지
│   ├── manage_charts.html          # 편제변경 관리 페이지
│   ├── manage_rate.html            # 요율변경 관리 페이지
│   ├── manage_grades.html          # 권한관리 페이지
│   ├── manage_tables.html          # 테이블 관리 페이지
│   ├── join_form.html              # 입사 신청 폼
│   ├── pdf_processing.html         # PDF 생성 중 페이지
│   ├── pdf_success.html            # PDF 생성 완료 페이지
│   └── includes/
│       └── _esign_sign_modal.html  # 서명 모달 파셜
└── views/
    ├── __init__.py                 # 모든 뷰 re-export (urls.py 호환)
    ├── pages.py                    # HTML 페이지 뷰 (manage_* / join_form)
    ├── context.py                  # build_manage_context() 공용 컨텍스트 빌더
    ├── constants.py                # BRANCH_PARTS 상수
    ├── responses.py                # json_ok() / json_err() / parse_json_body()
    ├── utils.py                    # 권한 스코프·날짜·소속 표기 유틸 (SSOT)
    ├── structure.py                # 편제변경 AJAX API
    ├── rate.py                     # 요율변경 AJAX API
    ├── efficiency.py               # 지점효율 AJAX API + 확인서 업로드/다운로드
    ├── esign.py                    # 전자서명 AJAX API (esign_service로 위임)
    ├── grades.py                   # 권한관리 페이지 + Excel 업로드 + DataTables API
    ├── parts.py                    # 부문/부서/지점 조회 API
    ├── process_date.py             # 처리일자 업데이트 공용 로직
    ├── ratetable.py                # 요율현황 조회·Excel 업로드/다운로드
    ├── tablesettings.py            # 테이블 관리 API (select_for_update)
    └── subadmin.py                 # 중간관리자(leader) 추가/삭제

static/css/apps/partner.css         # partner 앱 전용 CSS
static/js/partner/
    ├── esign_confirm/              # 전자서명 확인서 JS 모듈
    │   ├── dom_refs.js             # DOM 중앙화 (window.EsignDom)
    │   ├── fetch.js                # 데이터 조회 (window.EsignFetch)
    │   ├── save.js                 # 저장 (window.EsignSave)
    │   ├── sign.js                 # 서명 (window.EsignSign)
    │   └── index.js                # 부트 진입점 + 연/월 초기화
    ├── manage_efficiency/          # 지점효율 JS 모듈
    │   ├── dom_refs.js, fetch.js, save.js, delete.js
    │   ├── confirm_upload.js       # 확인서 파일 업로드 모달
    │   ├── input_rows.js           # 입력 테이블 행 관리
    │   ├── modal_search.js         # 사용자 검색 모달 연계
    │   ├── formatters.js           # 숫자/날짜 포맷
    │   ├── col_widths.js           # 컬럼 폭 관리
    │   ├── utils.js                # 유틸
    │   └── index.js                # 메인 진입점
    ├── manage_rate/                # 요율변경 JS 모듈
    │   ├── dom_refs.js, fetch.js, save.js, delete.js
    │   ├── input_rows.js, table_dropdown.js, utils.js
    │   └── index.js
    ├── manage_structure/           # 편제변경 JS 모듈
    │   ├── availability.js, deadline.js, delete.js, dom_refs.js
    │   ├── fetch.js, input_rows.js, modal_search.js, save.js, utils.js
    │   └── index.js
    ├── manage_grades/
    │   └── index.js                # DataTables 렌더 + 권한 업데이트
    └── join_form.js                # Daum 우편번호 API 통합
```

---

## 3. 모델 구조

### RateChange (요율변경 이력)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `requester` | FK → CustomUser | CASCADE, related_name="ratechange_requests" | 신청자 |
| `target` | FK → CustomUser | CASCADE, related_name="ratechange_targets" | 대상자 |
| `part` | CharField(50) | default="-" | 부서 |
| `branch` | CharField(50) | default="-", db_index | 지점 |
| `month` | CharField(7) | db_index | "YYYY-MM" |
| `before_ftable`, `before_frate` | CharField | | 변경 전 손보 테이블/요율 |
| `before_ltable`, `before_lrate` | CharField | | 변경 전 생보 테이블/요율 |
| `after_ftable`, `after_frate` | CharField | | 변경 후 손보 테이블/요율 |
| `after_ltable`, `after_lrate` | CharField | | 변경 후 생보 테이블/요율 |
| `memo` | CharField(200) | | 메모 |
| `process_date` | DateField | null=True | 처리일자 |
| `created_at` | DateTimeField | auto_now_add | 생성일시 |

Meta: `ordering=["-id"]`, `indexes=[(month,), (branch,)]`

### StructureChange (편제변경 이력)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `requester` | FK → CustomUser | SET_NULL, related_name="structure_requests" | 신청자 |
| `target` | FK → CustomUser | SET_NULL, related_name="structure_targets" | 대상자 |
| `part`, `branch` | CharField | | 부서, 지점 |
| `target_branch`, `chg_branch` | CharField | | 변경 전/후 지점 |
| `rank`, `chg_rank` | CharField | | 변경 전/후 직급 |
| `table_name`, `chg_table` | CharField | | 변경 전/후 테이블명 |
| `rate`, `chg_rate` | DecimalField(5,2) | | 변경 전/후 요율 |
| `memo` | CharField(100) | | 메모 |
| `or_flag` | BooleanField | default=False | OR 처리 플래그 |
| `month` | CharField(7) | | "YYYY-MM" |
| `request_date` | DateTimeField | auto_now_add | 신청일시 |
| `process_date` | DateTimeField | blank=True | 처리일시 |

Meta: `verbose_name="편제변경 데이터"`, `ordering=["-month", "-request_date"]`

### PartnerChangeLog (파트너 변경 로그)

| 필드 | 타입 | 설명 |
|---|---|---|
| `user` | FK → CustomUser (SET_NULL) | 작업자 |
| `action` | CharField(50) | 작업 유형 문자열 |
| `detail` | TextField(blank) | 상세 내용 |
| `timestamp` | DateTimeField(auto_now_add) | |

Meta: `ordering=["-timestamp"]`

### StructureDeadline (편제변경 마감일)

| 필드 | 타입 | 제약조건 |
|---|---|---|
| `branch` | CharField(50) | |
| `month` | CharField(7) | |
| `deadline_day` | PositiveSmallIntegerField | 1~31 |
| `updated_at` | DateTimeField(auto_now) | |

Meta: `unique_together=("branch", "month")`

### SubAdminTemp (중간관리자 확장 정보)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `user` | OneToOneField → CustomUser | CASCADE, related_name="subadmin_detail" | 연결 사용자 |
| `name`, `part`, `branch` | CharField | | 성명, 부서, 지점 |
| `grade` | CharField | | grade 스냅샷 |
| `team_a`, `team_b`, `team_c` | CharField | | 팀 A/B/C |
| `position` | CharField | | 직책 |
| `level` | CharField | choices=["–","A레벨","B레벨","C레벨"], default="–" | 관리 레벨 |
| `updated_at` | DateTimeField(auto_now) | | |

Meta: `db_table="partner_subadmin_temp"`, `verbose_name="권한관리 확장정보"`  
⚠️ `accounts.signals.py`가 `CustomUser.grade` 변경 시 이 모델을 자동 동기화한다. 직접 생성/수정 시 signals 동작과 충돌 주의.

### TableSetting (테이블 설정)

| 필드 | 타입 | 제약조건 |
|---|---|---|
| `branch` | CharField(100) | |
| `table_name` | CharField(100) | |
| `rate` | CharField(20) | blank=True |
| `order` | PositiveIntegerField | default=0 |
| `created_at`, `updated_at` | DateTimeField | |

Meta: `unique_together=("branch", "table_name")`

### RateTable (요율관리 테이블)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `user` | OneToOneField → CustomUser | CASCADE, related_name="rate_table" | |
| `branch`, `team_a`, `team_b`, `team_c` | CharField | | |
| `non_life_table`, `life_table` | CharField | | 손보/생보 테이블명 |
| `updated_at` | DateTimeField(auto_now) | | |

### EfficiencyConfirmGroup (지점효율 확인서 그룹)

| 필드 | 타입 | 제약조건 |
|---|---|---|
| `confirm_group_id` | CharField(64) | unique, db_index |
| `uploader` | FK → CustomUser (SET_NULL) | related_name="efficiency_confirm_groups" |
| `part`, `branch` | CharField | default="–" |
| `month` | CharField(7) | db_index |
| `title`, `note` | CharField | blank=True |
| `created_at` | DateTimeField(auto_now_add) | |

Meta: `ordering=["-id"]`, `verbose_name="지점효율 확인서(그룹)"`

### EfficiencyConfirmAttachment (지점효율 확인서 첨부)

| 필드 | 타입 | 제약조건 |
|---|---|---|
| `group` | FK → EfficiencyConfirmGroup | PROTECT, null=True, related_name="attachments" |
| `uploader` | FK → CustomUser (SET_NULL) | related_name="efficiency_confirm_uploads" |
| `part`, `branch` | CharField | default="–" |
| `month` | CharField(7) | db_index |
| `file` | FileField | upload_to="partner/efficiency_confirm/%Y/%m/" |
| `original_name` | CharField(255) | |
| `created_at` | DateTimeField(auto_now_add) | |

⚠️ `group` 에 `PROTECT`가 걸려있어 그룹 삭제 전 첨부를 먼저 삭제해야 한다. `efficiency_delete_group()`은 `transaction.on_commit`에서 파일 삭제를 처리한다.

### EfficiencyChange (지점효율 내역)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `requester` | FK → CustomUser (SET_NULL) | related_name="efficiency_requests" | 신청자 |
| `target` | FK → CustomUser (SET_NULL, blank) | related_name="efficiency_targets" | 대상자 |
| `part`, `branch` | CharField | default="–" | |
| `month` | CharField(7) | db_index | "YYYY-MM" |
| `category` | CharField(30) | blank | 카테고리 |
| `amount` | PositiveIntegerField | null | 금액 |
| `ded_name`, `ded_id` | CharField | | 공제자 성명·사번 |
| `pay_name`, `pay_id` | CharField | | 지급자 성명·사번 |
| `content` | CharField(80) | | 내용 |
| `memo` | CharField(200) | | 메모 |
| `process_date` | DateField | null | 처리일자 |
| `confirm_group` | FK → EfficiencyConfirmGroup | PROTECT, null, related_name="efficiency_rows" | |
| `confirm_attachment` | FK → EfficiencyConfirmAttachment | PROTECT, null, related_name="efficiency_rows_legacy" | 레거시 |
| `start_ym`, `end_ym` | CharField(7) | default="" | 기간 "YYYY-MM" |
| `created_at` | DateTimeField(auto_now_add) | | |

### EfficiencySignRequest (전자서명 요청)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `confirm_group` | OneToOneField → EfficiencyConfirmGroup | CASCADE, related_name="sign_request" | |
| `ym` | CharField(7) | | "YYYY-MM" |
| `branch` | CharField(50) | default="–" | |
| `created_by` | FK → CustomUser | PROTECT, related_name="esign_requests_created" | |
| `doc_hash` | CharField(64) | blank | PDF SHA-256 |
| `pdf_file` | FileField | upload_to="esign/completed/", null | 완성 PDF |
| `status` | CharField | choices=[pending/partial/completed/cancelled], default=pending | |
| `created_at`, `updated_at` | DateTimeField | | |

Properties: `is_pending`, `is_completed`  
Meta: `indexes=[(ym, branch), (status,)]`

### EfficiencyConfirmSign (개별 서명 참여자)

| 필드 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `request` | FK → EfficiencySignRequest | CASCADE, related_name="signs" | |
| `signer` | FK → CustomUser | PROTECT, related_name="esign_participations" | |
| `role` | CharField | choices=[deduct/pay/head_confirm] | 역할 |
| `signed_at` | DateTimeField | null | 서명일시 |
| `ip_address` | GenericIPAddressField | null | |
| `user_agent` | TextField | blank | |
| `session_key` | CharField(40) | blank | 세션 스냅샷 |
| `pass_verified_at_sign` | DateTimeField | null | PASS 인증 스냅샷 |
| `created_at` | DateTimeField(auto_now_add) | | |

Property: `is_signed`  
Meta: `unique_together=("request", "signer")`

### 모델 간 관계 요약

```
CustomUser
  ├── RateChange.requester / .target (FK)
  ├── StructureChange.requester / .target (FK)
  ├── PartnerChangeLog.user (FK)
  ├── SubAdminTemp.user (OneToOne) ← accounts.signals가 grade 변경 시 자동 동기화
  ├── RateTable.user (OneToOne)
  ├── EfficiencyConfirmGroup.uploader (FK)
  ├── EfficiencyConfirmAttachment.uploader (FK)
  ├── EfficiencyChange.requester / .target (FK)
  └── EfficiencySignRequest.created_by (FK)
        └── EfficiencyConfirmSign.signer (FK)

EfficiencyConfirmGroup (1)
  ├── EfficiencyConfirmAttachment (N) [PROTECT]
  ├── EfficiencyChange (N) [PROTECT, via confirm_group]
  └── EfficiencySignRequest (1) [OneToOne, via sign_request]
        └── EfficiencyConfirmSign (N) [CASCADE]
```

---

## 4. URL 네임스페이스 + 엔드포인트

**네임스페이스:** `partner`  
**prefix:** `/partner/` (web_ma/urls.py: `include(("partner.urls", "partner"), namespace="partner")`)

### HTML 페이지

| URL name | route | 권한 |
|---|---|---|
| `join_form` | `join/` | superuser, head, leader, basic |
| `manage_calculate` | `calculate/` | superuser, head, leader |
| `manage_charts` | `manage_charts` | superuser, head, leader |
| `manage_rate` | `rate/` | superuser, head, leader |
| `manage_grades` | `grades/` | superuser, head |
| `manage_tables` | `tables/` | superuser, head |
| `esign_confirm` | `esign/` | superuser, head, leader |
| `upload_grades_excel` | `upload-grades-excel/` | POST, superuser |

### Structure AJAX API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `structure_fetch` | `api/structure/fetch/` | GET | JSON |
| `structure_save` | `api/structure/save/` | POST | JSON |
| `structure_delete` | `api/structure/delete/` | POST | JSON |
| `structure_update_process_date` | `api/structure/update-process-date/` | POST | JSON |
| `ajax_fetch` | `api/fetch/` | GET | JSON (레거시 alias) |
| `ajax_save` | `api/save/` | POST | JSON (레거시 alias) |
| `ajax_delete` | `api/delete/` | POST | JSON (레거시 alias) |
| `ajax_update_process_date` | `api/update-process-date/` | POST | JSON (레거시 alias) |

### Rate AJAX API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `rate_fetch` | `api/rate/fetch/` | GET | JSON |
| `rate_save` | `api/rate/save/` | POST | JSON |
| `rate_delete` | `api/rate/delete/` | POST | JSON |
| `rate_update_process_date` | `api/rate/update-process-date/` | POST | JSON |

### Efficiency AJAX API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `efficiency_fetch` | `api/efficiency/fetch/` | GET | JSON |
| `efficiency_save` | `api/efficiency/save/` | POST | JSON |
| `efficiency_delete_row` | `api/efficiency/delete/` | POST | JSON |
| `efficiency_delete_group` | `api/efficiency/delete-group/` | POST | JSON |
| `efficiency_update_process_date` | `api/efficiency/update-process-date/` | POST | JSON |
| `efficiency_confirm_groups` | `efficiency/confirm-groups/` | GET | JSON |
| `efficiency_confirm_upload` | `efficiency/confirm-upload/` | POST | JSON |
| `efficiency_confirm_attachment_download` | `efficiency/attachments/<int:att_id>/download/` | GET | FileResponse |
| `efficiency_confirm_template_download` | `efficiency/confirm-template/download/` | GET | FileResponse |

### E-Sign AJAX API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `esign_fetch` | `api/esign/fetch/` | GET | JSON |
| `esign_save` | `api/esign/save/` | POST | JSON |
| `esign_delete_group` | `api/esign/delete-group/` | POST | JSON |
| `esign_sign` | `api/esign/<int:request_id>/sign/` | POST | JSON |
| `esign_pdf` | `api/esign/<int:request_id>/pdf/` | GET | FileResponse |
| `esign_update_process_date` | `api/esign/process-date/` | POST | JSON |

### 권한관리 API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `ajax_users_data` | `api/users-data/` | GET | JSON (DataTables) |
| `ajax_update_level` | `api/update-level/` | POST | JSON |
| `ajax_add_sub_admin` | `api/add-sub-admin/` | POST | JSON |
| `ajax_delete_subadmin` | `ajax/delete-subadmin/` | POST | JSON |

### 조직 정보 조회 API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `ajax_fetch_channels` | `ajax/fetch-channels/` | GET | JSON |
| `ajax_fetch_parts` | `ajax/fetch-parts/` | GET | JSON |
| `ajax_fetch_branches` | `ajax/fetch-branches/` | GET | JSON |

### 테이블·요율현황 API

| URL name | route | 메서드 | 반환 |
|---|---|---|---|
| `ajax_table_fetch` | `ajax/table-fetch/` | GET | JSON |
| `ajax_table_save` | `ajax/table-save/` | POST | JSON |
| `ajax_rate_userlist` | `ajax/rate-userlist/` | GET | JSON |
| `ajax_rate_userlist_excel` | `ajax/rate-userlist-excel/` | GET | FileResponse |
| `ajax_rate_userlist_upload` | `ajax/rate-userlist-upload/` | POST | JSON |
| `ajax_rate_user_detail` | `ajax/rate-user-detail/` | GET | JSON |
| `ajax_rate_userlist_template_excel` | `ajax/rate-userlist-template-excel/` | GET | FileResponse |

### JSON 응답 형식

```python
# 성공 (partner/views/responses.py)
json_ok(payload)    # {"status": "success", ...payload}

# 실패
json_err(message, status=400)  # {"status": "error", "message": "..."}
```

⚠️ manual/board 앱의 `{"ok": True/False}` 형식과 다르다. partner는 `{"status": "success"/"error"}` 형식을 사용한다.

---

## 5. 권한 정책

### Grade별 페이지 접근 범위

| 페이지 | superuser | head | leader | basic |
|---|---|---|---|---|
| `manage_calculate` (지점효율) | ✅ | ✅ (본인 지점) | ✅ (팀 범위) | ❌ |
| `manage_charts` (편제변경) | ✅ | ✅ (본인 지점) | ✅ (팀 범위) | ❌ |
| `manage_rate` (요율변경) | ✅ | ✅ (본인 지점) | ✅ (팀 범위) | ❌ |
| `manage_grades` (권한관리) | ✅ | ✅ (본인 지점) | ❌ | ❌ |
| `manage_tables` (테이블 관리) | ✅ | ✅ | ❌ | ❌ |
| `esign_confirm` (전자서명) | ✅ | ✅ | ✅ | ❌ |
| `join_form` (입사신청) | ✅ | ✅ | ✅ | ✅ |

### 데이터 읽기/쓰기 권한 스코프

| grade | 읽기 범위 | 쓰기/삭제 범위 |
|---|---|---|
| `superuser` | 전체 (branch_param 존중) | 전체 |
| `head` | 본인 `user.branch`만 | 본인 지점만 |
| `leader` | `SubAdminTemp` 팀 기준 멤버 | 팀 기준 (제한) |
| `basic` | ❌ (페이지 접근 불가) | ❌ |

### 권한 강제 위치 (SSOT: `partner/views/utils.py`)

```python
# 읽기 스코프 (GET)
resolve_branch_for_query(user, branch_param)
# → superuser: branch_param 그대로 / 그 외: user.branch 강제

# 쓰기 스코프 (POST)
resolve_branch_for_write(user, branch_payload)
# → superuser: payload / 그 외: user.branch 우선

# 삭제 권한 (편제변경)
# structure.py: superuser/head 또는 record.requester == request.user
```

### 전자서명 역할(role)별 권한

| role | 설명 | 서명 가능 조건 |
|---|---|---|
| `deduct` | 공제자 | `ded_id`가 본인 사번 |
| `pay` | 지급자 | `pay_id`가 본인 사번 |
| `head_confirm` | 지점장 확인 | 해당 지점의 head grade |

### 데코레이터 위치

```python
# partner/views/pages.py
@login_required
@grade_required("superuser", "head", "leader")
def manage_calculate(request): ...

@login_required
@grade_required("superuser", "head")
def manage_grades(request): ...

# AJAX 뷰는 @login_required + 내부 resolve_branch_for_* 로 스코프 강제
```

---

## 6. 서비스/유틸 레이어 SSOT 목록

### `partner/views/utils.py` ⚠️

| 함수 | 역할 |
|---|---|
| `resolve_branch_for_query(user, branch_param)` | GET 요청 branch 스코프 결정 — superuser만 파라미터 존중 |
| `resolve_branch_for_write(user, branch_payload)` | POST 쓰기 branch 스코프 결정 |
| `resolve_part_for_write(user, part_payload)` | POST 쓰기 part 스코프 결정 |
| `build_current_user_payload(user)` | `{"grade", "branch", "part", "id", "name"}` 직렬화 |
| `get_level_team_filter_user_ids(user)` | leader의 팀 멤버 ID 리스트 반환 (SubAdminTemp 기반) |
| `find_table_rate(branch, table_name)` | TableSetting 기준 요율 조회 |
| `normalize_month(month)` | "YYYY-MM" 정규화 |
| `parse_yyyy_mm_dd_or_none(value)` | 날짜 문자열 → `date` 또는 `None` |
| `get_now_ym()` | 현재 연월 "YYYY-MM" 반환 |
| `build_affiliation_display(user)` | 소속 표시 문자열 생성 |
| `build_requester_affiliation_chain(user)` | "branch team_a team_b team_c" 체인 |

⚠️ **데이터 읽기/쓰기 branch 스코프는 반드시 `resolve_branch_for_*()` 함수만 경유한다.**  
직접 `user.branch`를 쿼리 파라미터로 사용하면 superuser의 타 지점 조회가 불가능해진다.

### `partner/services/esign_service.py` ⚠️

| 함수 | 역할 |
|---|---|
| `resolve_head_for_branch(branch)` | 해당 지점의 head grade 사용자 조회 |
| `get_my_sign_status(request_obj, user)` | 로그인 사용자의 서명 상태 반환 (`unsigned`/`signed`/`not_required`) |
| `get_my_sign_id(request_obj, user)` | 로그인 사용자의 EfficiencyConfirmSign.id 반환 |
| `create_sign_request(created_by, confirm_group, rows, branch, ym)` | 서명 요청 생성 + 참여자 자동 추출 (ded_id/pay_id/head) |
| `mark_sign_completed(sign_obj, signer, request)` | 서명 완료 기록 + PDF 생성 trigger |
| `build_esign_queryset(user, branch_filter='')` | 권한 스코프 기반 QuerySet 반환 |

⚠️ **전자서명 생성·완료·조회는 반드시 `esign_service.py` 함수를 경유한다.**  
`EfficiencySignRequest.objects.create()` 직접 호출 시 참여자(`EfficiencyConfirmSign`) 자동 생성이 누락된다.

### `partner/services/pdf_service.py`

| 함수 | 역할 |
|---|---|
| `generate_efficiency_confirm_pdf(rows, branch, ym)` | ReportLab으로 지점효율 확인서 PDF 생성 → `BytesIO` 반환 |
| `_try_register_korean_font()` | NotoSansKR 폰트 전역 등록 (없으면 Helvetica 폴백) |

### `partner/views/responses.py`

| 함수 | 역할 |
|---|---|
| `json_ok(payload, status=200)` | `{"status": "success", ...payload}` JsonResponse |
| `json_err(message, status=400, extra=None)` | `{"status": "error", "message": ...}` JsonResponse |
| `parse_json_body(request)` | `request.body` 안전 JSON 파싱 |

### `partner/views/context.py`

| 함수 | 역할 |
|---|---|
| `build_manage_context(request, **kwargs)` | 페이지 공통 컨텍스트 딕셔너리 빌드 |

### `partner/views/constants.py`

```python
BRANCH_PARTS: Dict[str, List[str]] = {
    "MA사업1부": [...],  # 소속 지점 목록
    "MA사업2부": [...],
    "MA사업3부": [...],
    "MA사업4부": [...],
    "MA사업5부": [...],
}
```

---

## 7. 템플릿 구조

### 상속 관계

```
base.html
├── partner/manage_calculate.html     (지점효율)
├── partner/manage_charts.html        (편제변경)
├── partner/manage_rate.html          (요율변경)
├── partner/manage_grades.html        (권한관리)
├── partner/manage_tables.html        (테이블관리)
├── partner/esign_confirm.html        (전자서명)
│   └── ({% include %}) includes/_esign_sign_modal.html
├── partner/join_form.html            (입사신청)
├── partner/pdf_processing.html
└── partner/pdf_success.html
```

### CSS 로드

모든 관리 페이지가 `{% block app_css %}` 블록에서 `partner.css`를 로드한다:

```html
{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/partner.css' %}?v={% now 'U' %}">
{% endblock %}
```

### 부트 데이터 주입 패턴 (json_script)

```html
{# manage_calculate.html, manage_charts.html 등 #}
{{ ManageefficiencyBoot|json_script:"boot-efficiency" }}
{{ currentUser|json_script:"current-user" }}
```

JS에서 읽기:
```javascript
const boot = JSON.parse(document.getElementById("boot-efficiency").textContent || "{}");
const currentUser = JSON.parse(document.getElementById("current-user").textContent || "{}");
```

---

## 8. JS 부트 패턴

### `manage_calculate.html` (지점효율)

**루트 엘리먼트:** `id="manage-efficiency"`

**dataset 계약 (변경 금지):**

| key | 연결 URL name |
|---|---|
| `data-user-grade` | 로그인 사용자 grade |
| `data-branch` | 기본 지점 |
| `data-fetch-channels-url` | `partner:ajax_fetch_channels` |
| `data-current-year`, `data-current-month` | 현재 연/월 |
| `data-selected-year`, `data-selected-month` | 선택된 연/월 |
| `data-data-fetch-url` | `partner:efficiency_fetch` |
| `data-data-save-url` | `partner:efficiency_save` |
| `data-data-delete-row-url` | `partner:efficiency_delete_row` |
| `data-data-delete-group-url` | `partner:efficiency_delete_group` |
| `data-update-process-date-url` | `partner:efficiency_update_process_date` |
| `data-efficiency-confirm-upload-url` | `partner:efficiency_confirm_upload` |
| `data-efficiency-confirm-groups-url` | `partner:efficiency_confirm_groups` |
| `data-search-user-url` | `accounts:api_search_user` |
| `data-input-col-widths` | JSON (컬럼 폭 설정) |
| `data-main-col-widths` | JSON (컬럼 폭 설정) |
| `data-static-version` | 캐시 버스팅용 버전 |

**BFCache 가드:** `manage_efficiency/index.js`에서 `document.documentElement.dataset.*` 패턴 사용

---

### `manage_charts.html` (편제변경)

**루트 엘리먼트:** `id="manage-structure"`

**dataset 계약:**

| key | 연결 URL name |
|---|---|
| `data-user-grade` | |
| `data-current-year`, `data-current-month` | |
| `data-selected-year`, `data-selected-month` | |
| `data-future-until` | 미래 변경 허용 월 수 |
| `data-data-fetch-url` | `partner:structure_fetch` |
| `data-data-save-url` | `partner:structure_save` |
| `data-data-delete-url` | `partner:structure_delete` |
| `data-set-deadline-url` | 마감일 설정 URL |
| `data-search-user-url` | `accounts:api_search_user` |
| `data-update-process-date-url` | `partner:structure_update_process_date` |
| `data-fetch-channels-url` | `partner:ajax_fetch_channels` |
| `data-fetch-parts-url` | `partner:ajax_fetch_parts` |
| `data-fetch-branches-url` | `partner:ajax_fetch_branches` |

---

### `manage_rate.html` (요율변경)

**루트 엘리먼트:** `id="manage-rate"`

**dataset 계약:**

| key | 연결 URL name |
|---|---|
| `data-user-grade` | |
| `data-default-branch` | 기본 지점 |
| `data-selected-year`, `data-selected-month` | |
| `data-fetch-url` | `partner:rate_fetch` |
| `data-save-url` | `partner:rate_save` |
| `data-delete-url` | `partner:rate_delete` |
| `data-table-fetch-url` | `partner:ajax_table_fetch` |
| `data-target-detail-url` | `partner:ajax_rate_user_detail` |
| `data-update-process-date-url` | `partner:rate_update_process_date` |
| `data-user-level` | SubAdminTemp.level |
| `data-team-a`, `data-team-b`, `data-team-c` | SubAdminTemp 팀 정보 |

---

### `manage_grades.html` (권한관리)

**루트 엘리먼트:** `id="manage-grades"`

**dataset 계약:**

| key | 연결 URL name |
|---|---|
| `data-user-grade` | |
| `data-user-branch` | |
| `data-selected-channel`, `data-selected-part`, `data-selected-branch` | 선택된 조직 |
| `data-update-level-url` | `partner:ajax_update_level` |
| `data-delete-subadmin-url` | `partner:ajax_delete_subadmin` |
| `data-add-subadmin-url` | `partner:ajax_add_sub_admin` |
| `data-search-url` | `partner:ajax_users_data` |
| `data-fetch-channels-url` | `partner:ajax_fetch_channels` |
| `data-fetch-parts-url` | `partner:ajax_fetch_parts` |
| `data-fetch-branches-url` | `partner:ajax_fetch_branches` |

---

### `esign_confirm.html` (전자서명)

**루트 엘리먼트:** `id="esign-confirm"`

**dataset 계약:**

| key | 설명 |
|---|---|
| `data-user-grade`, `data-user-id`, `data-user-branch`, `data-user-part` | 로그인 사용자 정보 |
| `data-fetch-url` | `partner:esign_fetch` |
| `data-save-url` | `partner:esign_save` |
| `data-delete-group-url` | `partner:esign_delete_group` |
| `data-process-date-url` | `partner:esign_update_process_date` |
| `data-sign-url-template` | `/partner/api/esign/{id}/sign/` (플레이스홀더) |
| `data-pdf-url-template` | `/partner/api/esign/{id}/pdf/` (플레이스홀더) |
| `data-search-user-url` | `accounts:api_search_user` |
| `data-can-input` | `"yes"/"no"` (yesno 필터) |
| `data-can-delete` | `"yes"/"no"` |
| `data-can-process-date` | `"yes"/"no"` |

**JS 모듈 구조 (IIFE 패턴, window 객체 공유):**

```
window.EsignDom   ← dom_refs.js
window.EsignFetch ← fetch.js
window.EsignSave  ← save.js
window.EsignSign  ← sign.js
index.js (부트 + 연결)
```

**BFCache 가드:** `index.js`의 `GUARD_KEY` 플래그 (중복 초기화 방지)

---

### `manage_tables.html` (테이블 관리)

**루트 엘리먼트:** `id="manage-table"`

**dataset 계약:**

| key | 연결 URL name |
|---|---|
| `data-user-grade` | |
| `data-branch` | 기본 지점 |
| `data-fetch-url` | `partner:ajax_table_fetch` |
| `data-save-url` | `partner:ajax_table_save` |
| `data-rate-list-url` | `partner:ajax_rate_userlist` |
| `data-rate-excel-url` | `partner:ajax_rate_userlist_excel` |
| `data-rate-upload-url` | `partner:ajax_rate_userlist_upload` |
| `data-rate-template-url` | `partner:ajax_rate_userlist_template_excel` |

---

## 9. CSS 스코프 규약

**파일:** `static/css/apps/partner.css`

### 스코프 루트 선택자

| 선택자 | 대응 템플릿 |
|---|---|
| `#manage-structure` | `manage_charts.html` |
| `#manage-rate` | `manage_rate.html` |
| `#manage-efficiency` | `manage_calculate.html` |
| `#esign-confirm` | `esign_confirm.html` |
| `#manage-grades` | `manage_grades.html` |
| `#manage-table` | `manage_tables.html` |

### 컬럼 폭 클래스 (CSS와 JS 동시 계약)

**편제변경 테이블 (`#manage-structure`):**
`.c-search`, `.c-rq`, `.c-tg`, `.c-before-branch`, `.c-after-branch`, `.c-before-rank`, `.c-after-rank`, `.c-or`, `.c-memo`, `.c-del`

**요율변경 테이블 (`#manage-rate`):**
`.c-rq`, `.c-tg`, `.c-before-ftable`, `.c-before-frate`, `.c-after-ftable`, `.c-after-frate`, `.c-before-ltable`, `.c-before-lrate`, `.c-after-ltable`, `.c-after-lrate`, `.c-memo`, `.c-del`

**지점효율 테이블 (`#manage-efficiency`):**
`.c-rq`, `.c-rq-branch`, `.c-category`, `.c-amount`, `.c-tax`, `.c-ded`, `.c-pay`, `.c-content`, `.c-del`

**전자서명 테이블 (`#esign-confirm`):**
`.esign-col-affiliation`, `.esign-col-month`, `.esign-col-category`, `.esign-col-amount`, `.esign-col-person`, `.esign-col-content`, `.esign-col-remove`

⚠️ 컬럼 폭 클래스는 `colgroup > col` 에 적용되며 JS가 `col_widths.js`에서 동적으로 override할 수 있다. CSS와 JS 양쪽을 동시에 수정해야 한다.

### 전역 누수 방지

- 모든 스타일은 `#manage-structure`, `#manage-rate`, `#manage-efficiency`, `#esign-confirm` 루트 id 하위에서만 적용된다.
- `base.css` 수정 금지. 공통 UI는 Bootstrap 유틸리티 클래스를 활용한다.
- `.loading-overlay`, `.loading-box`는 partner.css 전용으로 다른 앱에서 재사용하면 안 된다.

---

## 10. 절대 수정 금지 목록

| 파일/함수 | 금지 이유 |
|---|---|
| `partner/views/utils.py` `resolve_branch_for_query()` | 제거/수정 시 head/leader가 타 지점 데이터 조회 가능해지는 데이터 유출 위험 |
| `partner/views/utils.py` `resolve_branch_for_write()` | 제거/수정 시 head가 타 지점 데이터를 생성/수정 가능해짐 |
| `partner/services/esign_service.py` `create_sign_request()` | 우회 시 서명 참여자(EfficiencyConfirmSign) 자동 생성 누락 → 서명 불가 상태 |
| `partner/services/esign_service.py` `mark_sign_completed()` | 우회 시 서명 완료 스냅샷(IP, session_key, pass_verified_at_sign) 누락, PDF 생성 누락 |
| `EfficiencyConfirmGroup → EfficiencyConfirmAttachment` PROTECT | `on_delete=PROTECT`를 CASCADE로 변경 시 그룹 삭제 시 첨부 파일이 물리 삭제 없이 DB 레코드만 사라짐 |
| `EfficiencyConfirmGroup → EfficiencyChange` PROTECT | CASCADE 변경 시 그룹 삭제 시 내역 행도 자동 삭제됨 (감사 목적 데이터 소실) |
| `SubAdminTemp` `db_table="partner_subadmin_temp"` | `accounts/search_api.py` 가 `SubAdminTemp.objects.filter(user_id__in=ids)` 를 이 테이블명으로 직접 조회함. 테이블명 변경 시 accounts 앱 사용자 검색 전체 파손 |
| `partner/views/responses.py` `json_ok/json_err` 응답 키 | JS가 `response.status === "success"/"error"` 를 기대. 키 변경 시 모든 파트너 페이지 AJAX 파손 |
| `esign_confirm.html` `data-sign-url-template`, `data-pdf-url-template` | JS가 `{id}` 플레이스홀더를 replace해서 URL을 동적 생성. 형식 변경 시 서명/PDF 다운로드 불가 |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 대상 | 파일 | 용도 |
|---|---|---|
| `accounts.models.CustomUser` | `partner/models.py` | 모든 FK/OneToOne의 대상 모델 |
| `accounts.decorators.grade_required` | `partner/views/pages.py` | 페이지 접근 권한 데코레이터 |
| `accounts.decorators.login_required` | `partner/views/pages.py` | 로그인 강제 |
| `audit.constants.ACTION` | `partner/views/*.py` 전체 | 감사 로그 액션 코드 (PARTNER_RATE_SAVE, PARTNER_RATE_DELETE 등) |
| `audit.services.log_action` | `partner/views/*.py` 전체 | CRUD 감사 로그 기록 |
| `static/js/common/part_branch_selector.js` | 템플릿 | 부문→부서→지점 연쇄 드롭다운 |
| `static/js/common/search_user_modal.js` | 템플릿 | 사용자 검색 모달 |
| `templates/components/search_user_modal.html` | 템플릿 | 사용자 검색 모달 컴포넌트 |

### 다른 앱이 이 앱에 의존하는 관계

| 의존 앱 | 의존 대상 | 용도 |
|---|---|---|
| `accounts` | `partner.models.SubAdminTemp` | `accounts/search_api.py` — leader의 팀 범위 검색에서 SubAdminTemp 조회 |
| `accounts` | `partner.models.SubAdminTemp` | `accounts/signals.py` — grade 변경 시 SubAdminTemp 자동 동기화 |
| `accounts` | `SubAdminTemp.db_table` | DB 직접 조회 시 테이블명 의존 |

⚠️ `partner.SubAdminTemp`는 `accounts` 앱의 핵심 동작에 영향을 미친다. 이 모델 구조(특히 `user`, `level`, `team_a/b/c` 필드, `db_table`)를 변경하면 accounts 앱의 사용자 검색 권한 스코프가 파손된다.

---

## 12. 신규 기능 추가 패턴

### 신규 변경 유형 추가 (예: 수수료 변경)

1. `partner/models.py`에 새 모델 정의 (`CommissionChange` 등)
2. `makemigrations` + `migrate`
3. `partner/views/` 에 새 모듈 생성 (예: `commission.py`) — `json_ok/json_err`, `resolve_branch_for_*` 사용
4. `partner/views/__init__.py`에 re-export 추가
5. `partner/urls.py`에 URL 패턴 추가 (`api/commission/fetch/`, `api/commission/save/` 등)
6. `audit/constants.py`에 새 ACTION 상수 추가 (`PARTNER_COMMISSION_SAVE` 등)
7. 새 템플릿 생성 (`partner/manage_commission.html`) — 루트 id, dataset 계약 설정
8. `partner.css`에 스코프 루트 선택자 추가 (`#manage-commission`)
9. `static/js/partner/manage_commission/` 디렉터리 생성 (dom_refs.js, fetch.js, save.js, index.js)
10. `partner/views/pages.py`에 `manage_commission()` 페이지 뷰 추가

### 전자서명 역할(role) 추가

1. `EfficiencyConfirmSign.role` choices에 새 값 추가 + 마이그레이션
2. `esign_service.py` `create_sign_request()`의 참여자 자동 추출 로직 수정
3. `esign_confirm.html`의 서명 모달 및 테이블 렌더 업데이트
4. `partner/services/pdf_service.py`의 PDF 레이아웃 업데이트

### 신규 Excel 업로드/다운로드

1. 해당 view 모듈에 upload/download 뷰 추가
2. `validate_*` 함수로 확장자·MIME 검증 추가 (board/services/attachments.py 패턴 참고)
3. `FileResponse(File(f), as_attachment=True)` + `content_disposition_header()` 사용
4. `att.file.url` 직접 노출 금지 — 반드시 다운로드 뷰 경유

---

## 13. LLM 함정 포인트

### `json_ok/json_err` vs `ok/fail` 형식 혼동

```python
# ❌ partner 앱에서 manual/board 응답 형식 사용
return JsonResponse({"ok": True, "data": ...})

# ✅ partner 앱의 SSOT 응답 형식
from partner.views.responses import json_ok, json_err
return json_ok({"data": ...})    # {"status": "success", "data": ...}
return json_err("오류 메시지")    # {"status": "error", "message": "..."}
```

### `resolve_branch_for_query()` 없이 쿼리 작성

```python
# ❌ 금지: head 사용자가 타 지점 데이터 조회 가능
branch = request.GET.get("branch", "")
qs = RateChange.objects.filter(branch=branch)

# ✅ 올바른 방법
from partner.views.utils import resolve_branch_for_query
branch = resolve_branch_for_query(request.user, request.GET.get("branch", ""))
qs = RateChange.objects.filter(branch=branch)
```

### `SubAdminTemp` 직접 생성 — `accounts.signals` 충돌

```python
# ❌ 금지: SubAdminTemp 직접 생성
SubAdminTemp.objects.create(user=user, grade="leader", ...)

# ✅ 올바른 방법: subadmin.py의 ajax_add_sub_admin() 경유
# 이 함수가 grade="leader" 승격 + SubAdminTemp get_or_create를 함께 처리
# accounts/signals.py의 post_save 핸들러와 중복 실행 방지 로직 포함
```

`accounts.signals._sync_subadmin_on_grade_change()` 는 `CustomUser.grade` 변경 시 자동 실행된다.  
`SubAdminTemp`를 직접 생성하면 signals와 충돌해 `team_a/b/c`가 초기화될 수 있다.

### `EfficiencySignRequest` 직접 생성 — 참여자 누락

```python
# ❌ 금지: 직접 생성
EfficiencySignRequest.objects.create(confirm_group=group, ...)
# → EfficiencyConfirmSign 참여자가 생성되지 않아 서명 불가

# ✅ 올바른 방법
from partner.services.esign_service import create_sign_request
create_sign_request(created_by=request.user, confirm_group=group, rows=rows, branch=branch, ym=ym)
```

### `EfficiencyConfirmGroup` 삭제 — PROTECT 오류

```python
# ❌ 금지: 직접 삭제 시 PROTECT 에러
group.delete()
# IntegrityError: PROTECT constraint on EfficiencyConfirmAttachment

# ✅ 올바른 방법: efficiency_delete_group() 뷰 경유
# 이 함수가 첨부 삭제 → 행 삭제 → 그룹 삭제를 transaction.atomic() 내에서 순서대로 처리
```

### `data-sign-url-template` 플레이스홀더 형식

```javascript
// esign_confirm/sign.js
const signUrlTpl = root.dataset.signUrlTemplate;   // "/partner/api/esign/{id}/sign/"
const url = signUrlTpl.replace("{id}", requestId); // ID 동적 치환
```

서버에서 이 URL 패턴을 변경하면(`<int:request_id>`를 다른 형식으로), JS의 플레이스홀더(`{id}`)도 함께 변경해야 한다. URL conf와 dataset 값이 항상 동기화되어야 한다.

### `views_shim.py` — 레거시 import 지원

```python
# partner/views_shim.py
# views/ 패키지 이전 전 일부 코드가 from partner.views_shim import ... 로 접근
# 신규 코드에서 이 파일을 사용하면 안 됨
```

신규 뷰는 반드시 `partner/views/` 패키지에 추가하고 `__init__.py`에 re-export한다.

### `process_date.py` — 3개 도메인 공용 처리

`structure_update_process_date`, `rate_update_process_date`, `efficiency_update_process_date`는 모두 `partner/views/process_date.py`에 구현되어 있다. 처리일자 업데이트 로직을 각 도메인 뷰 파일에 인라인으로 작성하면 안 된다.

### 첨부 파일 URL 직접 노출 금지

```html
<!-- ❌ 금지 -->
<a href="{{ attachment.file.url }}">다운로드</a>

<!-- ✅ 올바른 방법 -->
<a href="{% url 'partner:efficiency_confirm_attachment_download' attachment.id %}">다운로드</a>
<a href="{% url 'partner:esign_pdf' request_obj.id %}">PDF 다운로드</a>
```

---

## 14. 회귀 위험 체크리스트

partner 앱 수정 시 반드시 확인해야 하는 포인트:

- [ ] **`resolve_branch_for_query()` 우회 여부** — GET 파라미터를 직접 쿼리에 사용하면 타 지점 데이터 유출
- [ ] **`resolve_branch_for_write()` 우회 여부** — POST payload branch를 그대로 쓰면 타 지점 데이터 생성 가능
- [ ] **`SubAdminTemp` 구조 변경** → `accounts/search_api.py` `_apply_permission_scope()` leader 팀 필터 영향 확인
- [ ] **`SubAdminTemp.db_table` 변경** → `accounts/search_api.py` 직접 조회 파손 여부 확인
- [ ] **전자서명 생성 시 `create_sign_request()` 경유** — 직접 생성 시 참여자 누락
- [ ] **전자서명 완료 시 `mark_sign_completed()` 경유** — 직접 업데이트 시 PDF 생성 미트리거
- [ ] **`EfficiencyConfirmGroup` 삭제 시 PROTECT 순서** — 첨부→행→그룹 순서 준수
- [ ] **파일 다운로드 URL 직접 노출** — `attachment.file.url` 대신 다운로드 뷰 경유 여부
- [ ] **감사 로그 누락** — 신규 CRUD 기능에 `log_action(request, ACTION.PARTNER_*, ...)` 호출 여부
- [ ] **`json_ok/json_err` 응답 형식** — `{"status": "success"/"error"}` 유지 여부 (JS와 계약)
- [ ] **`esign_sign()` 후 PDF 생성 trigger** — `transaction.on_commit` 내 PDF 생성 호출 유지
- [ ] **`EfficiencyConfirmSign.unique_together=("request", "signer")`** — 동일 사용자 중복 서명 시도 방어
- [ ] **테이블 관리 `select_for_update`** — `tablesettings.py`의 동시 저장 동시성 제어 유지
- [ ] **Excel 업로드 후 DB 외 파일 정리** — 임시 파일 삭제 로직 포함 여부
- [ ] **PDF 파일 `upload_to="esign/completed/"`** — 물리 파일이 남는 삭제 시 `pdf_file.delete(save=False)` 호출 여부
- [ ] **`StructureDeadline.unique_together=("branch", "month")`** — 마감일 중복 저장 방어
