# commission 앱 개발 가이드

> **목적**: 외부 LLM이 전체 코드 없이 commission 앱을 정확하게 디벨롭할 수 있는 수준의 참조 문서.
> **기준 커밋**: develop 브랜치 (2026-05-03)

---

## 1. 앱 책임 요약

보험 GA 조직의 **채권현황(Deposit)**, **수수료 결재/지점효율(Approval/Efficiency)**, **환수관리(Collect)** 세 도메인을 담당한다. 엑셀 업로드로 원장 데이터를 갱신하고, 권한별 조회·피드백 기능을 제공한다.

---

## 2. 디렉터리 구조

```
commission/
├── models.py                     # 10개 모델 (Deposit/Approval/Collect 도메인)
├── urls.py                       # 26개 URL 패턴 (namespace="commission")
├── admin.py                      # 비어있음 — 모델 미등록
├── apps.py                       # CommissionConfig
├── views/
│   ├── __init__.py               # Lazy import surface — 순환 import 방지 + 501 stub
│   ├── pages.py                  # 페이지 뷰 4개 (deposit_home, approval_home, collect_home 등)
│   ├── api_collect.py            # 환수관리 API 7개
│   ├── api_deposit.py            # Deposit API shim (impl로 위임)
│   ├── api_deposit_impl.py       # Deposit API 실구현 6개 함수
│   ├── api_upload.py             # 채권 엑셀 업로드 메인 뷰
│   ├── approval.py               # 결재/효율 업로드 뷰
│   ├── downloads.py              # 엑셀 다운로드 뷰 3개
│   ├── constants.py              # UPLOAD_CATEGORIES, EXCESS_THRESHOLD 등
│   ├── utils_json.py             # _json_ok / _json_error 헬퍼
│   ├── utils_fail_excel.py       # 업로드 실패 목록 Excel 생성
│   ├── utils_excel.py            # Excel 유틸
│   ├── _files.py                 # save_temp_upload / safe_delete (임시 파일 관리)
│   ├── _ym.py                    # resolve_ym — year/month 파라미터 파싱
│   └── _excel_export.py          # Excel 내보내기
├── services/
│   ├── __init__.py               # 비어있음 (placeholder)
│   └── collect.py                # ⚠️ Collect 도메인 비즈니스 로직 SSOT (628줄)
├── upload_handlers/
│   ├── __init__.py
│   ├── registry.py               # ⚠️ 업로드 스펙 레지스트리 SSOT
│   ├── deposit.py                # Deposit 핸들러 10개
│   ├── collect.py                # 환수관리 업로드 핸들러 1개
│   ├── approval.py               # 결재 업로드 핸들러
│   └── efficiency.py             # 효율 업로드 핸들러
├── upload_utils/
│   ├── __init__.py
│   ├── _convert.py               # 타입 변환 유틸 8개 함수
│   ├── _detect.py                # 컬럼 탐지 유틸 7개 함수
│   ├── _readers.py               # Excel/CSV 읽기 6개 함수
│   ├── _db.py                    # DB 헬퍼 2개 (bulk 조회, upload log)
│   └── upload_utils.py           # (legacy wrapper)
├── templates/commission/
│   ├── deposit_home.html         # 채권현황 페이지 (764줄)
│   ├── approval_home.html        # 수수료 결재/지점효율 페이지 (196줄)
│   ├── collect_home.html         # 환수관리 페이지 (511줄)
│   └── _approval_upload_modal.html  # 결재 업로드 모달 partial
├── templatetags/
│   └── commission_extras.py      # get_item 필터 (dict 안전 접근)
└── migrations/                   # 21개 마이그레이션
```

---

## 3. 모델 구조

### 3.1 Deposit 도메인

#### `DepositSummary`
- **역할**: 사용자별 채권 요약 (PK = `user` OneToOneField → CustomUser)
- **주요 필드 (선발)**:

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `final_payment` | DecimalField | 최종지급액 (음수 = 환수 대상) |
| `debt_total` | DecimalField | 채권 합계 |
| `surety_total` | DecimalField | 보증보험 합계 (필터링값) |
| `other_total` | DecimalField | 기타채권 합계 (필터링값) |
| `div_1m` / `div_2m` / `div_3m` | CharField | 분급 구분 |
| `comm_3m` ~ `comm_12m` | DecimalField | 3~12개월 수수료 |
| `ns_13_round` / `ls_13_round` 등 | DecimalField | 통산 손/생보 지표 |
| `updated_at` | DateTimeField | 마지막 업로드 시각 |

- **관계**: `user` = FK(CustomUser, OneToOne, CASCADE)

#### `DepositSurety`
- **역할**: 보증보험 상세 (1:N, 재업로드 시 사번 단위 DELETE → bulk_create)
- **주요 필드**: `user`(FK), `product_name`, `policy_no`, `amount`, `status`, `start_date`, `end_date`

#### `DepositOther`
- **역할**: 기타채권 상세 (1:N, 재업로드 시 사번 단위 DELETE → bulk_create)
- **주요 필드**: `user`(FK), `product_name`, `product_type`, `amount`, `bond_no`, `status`, `start_date`, `memo`

#### `DepositUploadLog`
- **역할**: Deposit 업로드 이력 추적
- **제약**: `UniqueConstraint(part, upload_type)` — 부서×업로드유형 당 1건 (upsert)
- **주요 필드**: `part`, `upload_type`, `uploaded_at`, `row_count`, `file_name`

### 3.2 Approval/Efficiency 도메인

#### `ApprovalExcelUploadLog`
- **제약**: `UniqueConstraint(ym, part, kind)` — 월도×부서×종류 당 1건
- **필드**: `ym`(YYYY-MM), `part`, `kind`('efficiency'|'approval'), `uploaded_by`(FK SET_NULL), `uploaded_at`, `row_count`, `file_name`

#### `ApprovalPending`
- **역할**: 수수료 미결 현황
- **제약**: `UniqueConstraint(ym, user)`
- **필드**: `ym`, `user`(FK), `emp_name`, `actual_pay`, `approval_flag`('Y'|'N')

#### `EfficiencyPayExcess`
- **역할**: 지점효율 지급 초과 현황
- **제약**: `UniqueConstraint(ym, user)`
- **필드**: `ym`, `user`(FK), `pay_amount_sum`

### 3.3 Collect 도메인

#### `CollectRecord`
- **역할**: 환수관리 엑셀 원장 (36개 컬럼 전체 저장)
- **설계 특이점**: `emp_id`는 `CharField` (FK 없음) — 엑셀 원본 사번 그대로 저장
- **제약**: `UniqueConstraint(emp_id, ym)` → 재업로드 시 `update_conflicts=True`로 덮어쓰기
- **인덱스**: `Index(ym, part)`, `Index(ym, bizmoon)`
- **핵심 필드**:

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `emp_id` | CharField | 사번 (7자리, FK 없음) |
| `ym` | CharField(6) | 월도 YYYYMM |
| `final_payment` | DecimalField | 최종지급액 (음수 = 환수 대상) |
| `bizmoon` | CharField | 부문 |
| `part` | CharField | 부서 |
| `branch` | CharField | 영업가족 |
| `collect_action` | CharField | 환수조치 |
| `status` | CharField | 상태 |
| `surety_bond_total` | DecimalField | 보증채권합계 |
| `actual_pay` | DecimalField | 실지급액 |
| `uploaded_at` | DateTimeField | auto_now |

#### `CollectFeedback`
- **역할**: 환수 대상자 운영 피드백 이력 (누적, 수정/삭제 가능)
- **설계 특이점**: `emp_id`는 `CharField` (FK 없음), author만 FK(CustomUser, PROTECT)
- **제약**: 없음 (이력 누적형) — 수정/삭제 권한은 서비스에서 `author_id` 검증
- **인덱스**: `Index(emp_id, -created_at)`
- **부서 선택지**: '채권추심부', '담당부서', '영업지점'

#### `CollectUploadLog`
- **역할**: 환수관리 업로드 이력
- **제약**: `UniqueConstraint(ym)` — 월도 당 1건 (`update_or_create`)
- **필드**: `ym`, `uploaded_by`(FK SET_NULL), `uploaded_at`, `row_count`, `file_name`

#### `CollectDropdownFeedback`
- **역할**: 드롭다운 방식 피드백 (영업가족용/본사용 구분)
- **설계 특이점**: UniqueConstraint 없음 — 이력 누적, 최신 1건은 Subquery로 조회
- **인덱스**: `Index(emp_id, ym, feedback_type)`
- **feedback_type 선택지**:
  - `branch` (영업가족): 입금예정, 익월상계, 상위차감, 연락두절(추심요청), 기타
  - `hq` (본사): 입금예정, 익월상계, 상위차감, 보증청구, 기타

---

## 4. URL 네임스페이스 + 엔드포인트 전체 목록

**namespace**: `commission`

### 페이지

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `redirect_to_deposit` | `/commission/` | GET | redirect → `deposit_home` |
| `deposit_home` | `/commission/deposit/` | GET | HTML |
| `approval_home` | `/commission/approval/` | GET | HTML |
| `collect_home` | `/commission/collect/` | GET | HTML |

### 업로드

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `upload_excel` | `/commission/upload-excel/` | POST | JSON |
| `approval_upload_excel` | `/commission/approval/upload-excel/` | POST | JSON |

### 다운로드

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `download_upload_fail_excel` | `/commission/download/upload-fail/` | GET | Excel file |
| `download_approval_pending_excel` | `/commission/approval/excel/pending/` | GET | Excel file |
| `download_efficiency_excess_excel` | `/commission/approval/excel/efficiency-excess/` | GET | Excel file |

### Deposit API

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `api_user_detail` | `/commission/api/user-detail/` | GET | JSON |
| `api_deposit_summary` | `/commission/api/deposit-summary/` | GET | JSON |
| `api_deposit_surety_list` | `/commission/api/deposit-surety/` | GET | JSON |
| `api_deposit_other_list` | `/commission/api/deposit-other/` | GET | JSON |
| `api_support_pdf` | `/commission/api/support-pdf/` | GET | JSON |

### Collect API

| name | route | 메서드 | 반환 |
|------|-------|--------|------|
| `api_collect_list` | `/commission/collect/api/list/` | GET | JSON |
| `api_collect_ym_list` | `/commission/collect/api/ym-list/` | GET | JSON |
| `api_collect_feedback_list` | `/commission/collect/api/feedback/` | GET | JSON |
| `api_collect_feedback_create` | `/commission/collect/api/feedback/create/` | POST | JSON |
| `api_collect_feedback_update` | `/commission/collect/api/feedback/update/` | POST | JSON |
| `api_collect_feedback_delete` | `/commission/collect/api/feedback/delete/` | POST | JSON |
| `api_collect_dropdown_feedback_save` | `/commission/collect/api/dropdown-feedback/save/` | POST | JSON |

**JSON 응답 형식 (전체 통일)**: `{ "ok": true|false, "message": "...", "data": {...} }`

---

## 5. 권한 정책

### 도메인별 접근 등급

| 도메인 | 페이지/API | 허용 등급 | 강제 위치 |
|--------|-----------|----------|----------|
| Deposit 페이지 | `deposit_home` | `staff`, `admin`, `superuser` ⚠️ | `@grade_required` (pages.py:136) |
| Approval 페이지 | `approval_home` | `staff`, `admin`, `superuser` ⚠️ | `@grade_required` (pages.py:172) |
| Collect 페이지 | `collect_home` | `superuser`, `head`, `leader` | `@grade_required` (pages.py:256) |
| Collect API | 전체 7개 | `superuser`, `head`, `leader` | `@grade_required` (api_collect.py) |
| 업로드 | `upload_excel`, `approval_upload_excel` | `superuser` 전용 | `@grade_required` (api_upload.py, approval.py) |
| Deposit API 조회 | `api_deposit_summary` 등 | superuser/head/main_admin 또는 본인 | `_can_view_target()` (api_deposit_impl.py) |

> ⚠️ **grade "staff", "admin" 주의**: `deposit_home`, `approval_home`에서 사용된 `"staff"`, `"admin"`은 CLAUDE.md 공식 등급표(`superuser`, `head`, `leader`, `basic`, `resign`, `inactive`)에 없는 값이다. `accounts/decorators.py`의 `GRADE_ALIAS_MAP`이 현재 비어있으므로, 이 두 등급은 사실상 **접근 불가 등급**처럼 동작할 수 있다. 수정 전 `accounts/decorators.py`의 실제 grade 비교 로직을 반드시 확인하고 의도를 검증할 것.

### Collect 피드백 세부 권한

| 작업 | 조건 |
|------|------|
| 피드백 생성 | superuser/head/leader |
| 피드백 수정/삭제 | `author_id == request.user.id` (services/collect.py에서 검증) |
| 드롭다운 `branch` 저장 | head/leader |
| 드롭다운 `hq` 저장 | superuser |

---

## 6. 서비스/유틸 레이어 SSOT 목록

### commission/services/collect.py ⚠️ (Collect 도메인 전체 SSOT)

모든 Collect 도메인 ORM 조작은 이 파일을 경유해야 한다. 뷰에서 `CollectRecord`, `CollectFeedback` 등을 직접 쿼리하지 말 것.

| 공개 함수 | 역할 |
|-----------|------|
| `ym_to_date(ym)` | "202603" → `date(2026, 3, 1)` |
| `date_to_ym(d)` | `date` → "202603" |
| `offset_ym(base_ym, months)` | 월도 상대 계산 |
| `get_available_yms()` | 업로드된 월도 목록 (최신순) |
| `get_available_parts()` | 부서 목록 |
| `get_available_bizmoons()` | 부문 목록 |
| `get_collect_list(ym, tab, part, bizmoon, user)` | ⚠️ 탭별 필터링된 rows 반환 SSOT |
| `get_feedbacks(emp_id)` | CollectFeedback 이력 (최신순) |
| `create_feedback(author, emp_id, content, date_input, department, manager)` | 피드백 생성 |
| `update_feedback(feedback_id, author, content)` | 피드백 수정 (권한 없으면 None 반환 → 403) |
| `delete_feedback(feedback_id, author)` | 피드백 삭제 (권한 없으면 False 반환 → 403) |
| `save_dropdown_feedback(author, emp_id, ym, feedback_type, value)` | 드롭다운 피드백 이력 저장 |

### commission/upload_handlers/registry.py ⚠️ (업로드 타입 등록 SSOT)

새 업로드 타입 추가 시 반드시 이 파일에 `UploadSpec`을 등록해야 한다. `constants.py`의 `SUPPORTED_UPLOAD_TYPES`는 이 registry 기반으로 동적 생성된다.

| 공개 함수 | 역할 |
|-----------|------|
| `get_upload_spec(upload_type)` | 업로드 타입 → `UploadSpec` (없으면 None) |
| `supported_upload_types()` | 지원하는 업로드 타입 목록 반환 |

### commission/views/utils_json.py

| 함수 | 역할 |
|------|------|
| `_json_ok(data=None, message="")` | `{"ok": true, ...}` 응답 생성 |
| `_json_error(message, status=400)` | `{"ok": false, "message": "..."}` 응답 생성 |

### commission/views/_files.py

| 함수 | 역할 |
|------|------|
| `save_temp_upload(file)` | 업로드 파일을 임시 경로에 저장, 경로 반환 |
| `safe_delete(path)` | 임시 파일 삭제 (예외 무시) |

### commission/views/_ym.py

| 함수 | 역할 |
|------|------|
| `resolve_ym(request)` | `?ym=YYYY-MM` 또는 `?year=&month=` 파라미터 파싱 |

### commission/upload_utils/_convert.py ⚠️

업로드 핸들러 내에서 값 변환 시 반드시 재사용. 직접 `int()`, `Decimal()` 캐스팅 금지.

| 함수 | 역할 |
|------|------|
| `_to_int(v, default=0)` | 안전한 정수 변환 (콤마 제거, "nan" 처리) |
| `_to_decimal(v, default=DEC2)` | Decimal 변환 |
| `_safe_decimal_q2(v, default=DEC2)` | Decimal quantize(소수 2자리) |
| `_to_date(v)` | pandas Timestamp/datetime/문자열 → date |
| `_norm_emp_id(v)` | "1234567.0" → "1234567" (float 사번 정규화) |

### commission/upload_utils/_detect.py ⚠️

엑셀 컬럼명이 매번 달라질 수 있으므로 패턴 기반 탐지 함수를 반드시 사용.

| 함수 | 역할 |
|------|------|
| `_detect_emp_id_col(df)` | 사번 컬럼 탐지 |
| `_detect_col(df, must_include, any_include)` | 복합 조건 컬럼 탐지 |
| `_find_exact_or_space_removed(df_cols, target)` | 공백 무관 정확 매칭 |

---

## 7. 템플릿 구조

### 상속 관계

```
base.html
├── commission/deposit_home.html    ({% block content %})
├── commission/approval_home.html   ({% block content %})
└── commission/collect_home.html    ({% block content_wrapper %})  ← 와이드 레이아웃
```

> ⚠️ `collect_home.html`은 `{% block content %}`가 아닌 `{% block content_wrapper %}`를 사용한다. 86vw 넓은 테이블 레이아웃이 필요하기 때문이다. 다른 commission 페이지와 다른 블록명임에 주의.

### CSS 로드

모든 페이지는 `{% block app_css %}` 블록에서 `static/css/apps/commission.css`를 로드한다:

```html
{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/commission.css' %}{% if STATIC_VERSION %}?v={{ STATIC_VERSION }}{% endif %}">
{% endblock %}
```

### partial 인클루드

- `commission/approval_home.html` → `{% include 'commission/_approval_upload_modal.html' %}`
- `commission/deposit_home.html` → `{% include 'components/search_user_modal.html' %}`
- `commission/collect_home.html` → `{% include 'components/search_user_modal.html' %}`

---

## 8. JS 부트 패턴

### 루트 엘리먼트 및 dataset

#### deposit_home.html / deposit_home.js

- **루트 id**: `deposit-home`
- **dataset 키** (변경 금지 계약):

| 속성 | 연결 URL name |
|------|--------------|
| `data-user-detail-url` | `commission:api_user_detail` |
| `data-deposit-summary-url` | `commission:api_deposit_summary` |
| `data-deposit-surety-url` | `commission:api_deposit_surety_list` |
| `data-deposit-other-url` | `commission:api_deposit_other_list` |
| `data-reset-url` | `commission:deposit_home` |
| `data-support-pdf-url` | `commission:api_support_pdf` |

- **BFCache 가드**: 없음 (root 존재 여부만 체크)
- **패턴**: IIFE (`(() => { ... })()`)
- **공용 유틸**: `window.CommissionCommon.dom / .format / .net / .modals` (없으면 fallback)

#### collect_home.html / collect_home.js

- **루트 id**: `collect-home`
- **dataset 키** (변경 금지 계약):

| 속성 | 연결 URL name |
|------|--------------|
| `data-api-list-url` | `commission:api_collect_list` |
| `data-api-ym-list-url` | `commission:api_collect_ym_list` |
| `data-api-feedback-list-url` | `commission:api_collect_feedback_list` |
| `data-api-feedback-create-url` | `commission:api_collect_feedback_create` |
| `data-api-feedback-update-url` | `commission:api_collect_feedback_update` |
| `data-api-feedback-delete-url` | `commission:api_collect_feedback_delete` |
| `data-api-dropdown-feedback-save-url` | `commission:api_collect_dropdown_feedback_save` |
| `data-upload-url` | `commission:upload_excel` |
| `data-search-user-url` | `accounts_search_url` (context 주입) |
| `data-default-ym` | 가장 최신 월도 |
| `data-current-user-id` | `request.user.id` |
| `data-current-user-grade` | `request.user.grade` |

- **BFCache 가드**: ✅ `root.dataset.inited === "1"` + `window.addEventListener("pageshow", ...)` (collect_home.js:32)
- **패턴**: ESM (`type="module"`)
- **외부 의존**: SheetJS `vendor/xlsx/0.18.5/xlsx.full.min.js` (XLS 클라이언트 다운로드)

#### approval_home.html

- **루트 id**: `approval-home`
- **dataset 키**:
  - `data-selected-ym`: 현재 선택 월도 (YYYY-MM)
  - `data-selected-part`: 현재 선택 부서
- **JS 파일**: `approval_home_export.js` (XLS 내보내기), `approval_excel_upload.js` (업로드 폼)
- **XLS 내보내기 트리거**: `data-export-table="#tableId"`, `data-export-name="파일명"`

### 공용 JS 유틸 로드 순서 (deposit, collect 모두 동일)

```html
<script src="{% static 'js/commission/_dom.js' %}..."></script>
<script src="{% static 'js/commission/_format.js' %}..."></script>
<script src="{% static 'js/commission/_net_json.js' %}..."></script>
<script src="{% static 'js/commission/_modals.js' %}..."></script>
<script src="{% static 'js/commission/{page}_home.js' %}..." [type="module"]></script>
<script src="{% static 'js/excel_upload.js' %}..."></script>  {# 업로드 폼 공용 #}
```

`window.CommissionCommon` 네임스페이스:
- `.dom`: `$()`, `text()`, `safeSetText()`
- `.format`: `comma()`, `percent()`, `escapeHtml()`
- `.net`: `fetchJSON()`, `firstObject()`, `arrayRows()`
- `.modals`: `TextViewer` (말줄임 모달), `SupportModal` (지원신청서)

---

## 9. CSS 스코프 규약

- **파일**: `static/css/apps/commission.css` (405줄)
- **Deposit 스코프**: `.deposit-maxw` 클래스로 폭 제한 + `table-layout: fixed`
- **Approval 스코프**: `.commission-nowrap-table`, `.commission-table-scroll`
- **Collect 스코프**: `.collect-wide` (86vw 넓은 레이아웃)
- **드롭다운 피드백 색상**: `.val-green`, `.val-blue`, `.val-red`, `.val-yellow`, `.val-gray` (값별 배경색)
- **말줄임 셀**: `.ellipsis-cell` → 클릭 시 `TextViewer` 모달로 전체 내용 표시

**원칙**: `commission.css` 내 모든 규칙은 `.deposit-maxw`, `.collect-wide`, `.commission-*` 등 commission 전용 클래스 또는 `#deposit-home`, `#collect-home`, `#approval-home` ID 하위로 스코핑. `base.css`는 절대 수정하지 않는다.

---

## 10. 절대 수정 금지 목록

| 파일/요소 | 금지 이유 |
|-----------|----------|
| `commission/upload_handlers/registry.py` | 업로드 타입 SSOT — 변경 시 `views/constants.py`의 `SUPPORTED_UPLOAD_TYPES`와 `deposit_home.html`의 업로드 버튼 목록이 즉시 깨진다 |
| `commission/services/collect.py` 내 `_apply_scope()` | leader 팀 스코프 필터 로직 — 변경 시 팀장이 타팀 데이터를 열람하는 보안 사고 발생 |
| `CollectRecord` 필드명 (`emp_id`, `ym`) | `UniqueConstraint(emp_id, ym)` 기반 upsert 키 — 변경 시 재업로드 덮어쓰기 불가, 중복 데이터 누적 |
| `CollectDropdownFeedback` UniqueConstraint 없음 설계 | 의도적 이력 누적 설계 — UniqueConstraint 추가 시 Subquery 기반 최신값 조회 로직 전체 교체 필요 |
| `deposit_home.html` `id="deposit-home"` 및 모든 `data-*-url` | `deposit_home.js`의 유일한 URL 소스, 변경 시 전체 Deposit 기능 무력화 |
| `collect_home.html` `id="collect-home"` 및 모든 `data-*-url` | `collect_home.js`의 유일한 URL 소스, 변경 시 전체 환수관리 기능 무력화 |
| `commission/views/__init__.py` lazy import 구조 | 순환 import 방지 + 501 stub 패턴 — 일반 import로 변경 시 Django 시작 시 순환 참조 오류 발생 위험 |
| `DepositSurety` / `DepositOther` 업로드 방식 (사번 DELETE → bulk_create) | 사번 단위 전체 교체가 의도된 설계 — UPDATE로 변경 시 삭제된 항목이 잔류함 |
| `upload_utils/_convert.py` `_norm_emp_id()` | "1234567.0" → "1234567" 정규화 — 제거 시 float 사번이 DB에 저장되어 조회/매핑 실패 |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 의존 대상 | 위치 | 용도 |
|-----------|------|------|
| `grade_required` 데코레이터 | `accounts/decorators.py` | 모든 뷰의 권한 강제 |
| `CustomUser` 모델 | `accounts/models.py` | `DepositSummary.user`, `CollectFeedback.author` 등 FK |
| `accounts/search_api.py` | `accounts/` | `accounts_search_url` context로 사용자 검색 모달 연동 |
| `audit.constants.ACTION` | `audit/constants.py` | `COLLECT_FEEDBACK_CREATE/UPDATE/DELETE` 액션 상수 |
| `audit.services.log_action` | `audit/services.py` | 피드백 CRUD 감사 로그 |
| `components/search_user_modal.html` | `templates/components/` | deposit/collect 페이지 사용자 검색 모달 |
| `static/js/excel_upload.js` | `static/js/` | 공용 엑셀 업로드 폼 처리 |
| `vendor/xlsx/0.18.5/xlsx.full.min.js` | `static/vendor/` | collect_home XLS 클라이언트 다운로드 |

### 다른 앱이 이 앱에 의존하는 관계

현재 다른 앱이 `commission` 앱 모델 또는 서비스를 직접 import하는 의존 관계는 없다. `commission`은 독립 도메인 앱이다.

---

## 12. 신규 기능 추가 패턴

### 패턴 A: 새 Deposit 업로드 타입 추가

1. `commission/upload_handlers/deposit.py`에 `handle_upload_<type>(df) → dict` 함수 추가
2. `commission/upload_handlers/registry.py`에 `UploadSpec(upload_type="...", mode="df", fn=handle_upload_<type>, msg_tpl="...")` 등록
3. `commission/views/constants.py`의 `UPLOAD_TYPES_ORDER`에 표시 순서 추가 (있는 경우)
4. `DepositSummary` 모델 필드 변경이 필요하면 migration 생성 후 `api_deposit_impl.py`의 `_summary_to_payload()` 업데이트
5. `deposit_home.html` 업로드 버튼은 `supported_upload_types()` 기반으로 자동 생성되므로 별도 수정 불필요

### 패턴 B: Collect API 신규 엔드포인트 추가

1. `commission/services/collect.py`에 비즈니스 로직 함수 추가 (ORM 직접 접근은 이 파일에서만)
2. `commission/views/api_collect.py`에 뷰 함수 추가 (`@login_required` + `@grade_required` + `@require_GET/POST`)
3. `commission/urls.py`에 URL 패턴 추가
4. `commission/templates/commission/collect_home.html`의 `id="collect-home"` 요소에 `data-api-<name>-url="{% url '...' %}"` 추가
5. `collect_home.js`의 `URLS` 객체에 키 추가

### 패턴 C: CollectRecord 필드 추가

1. `commission/models.py` 필드 추가
2. `python manage.py makemigrations commission` → `python manage.py migrate`
3. `commission/upload_handlers/collect.py`의 컬럼 탐지 로직 및 row 파싱에 필드 추가
4. `commission/services/collect.py`의 `_serialize_record()` 함수에 반환 dict 키 추가
5. `collect_home.js` 테이블 렌더링 함수에 컬럼 추가

### 패턴 D: 새 페이지 뷰 추가

1. `commission/views/pages.py`에 뷰 함수 추가 (`@grade_required` 필수)
2. `commission/views/__init__.py`의 `_PAGES` dict에 등록
3. `commission/urls.py`에 URL 추가
4. `commission/templates/commission/<page>.html` 생성 (`{% extends 'base.html' %}`, `{% block app_css %}` 패턴 준수)
5. `static/js/commission/<page>.js` 생성 (IIFE 또는 ESM, `root.dataset.inited` 가드)

---

## 13. LLM 함정 포인트

### ① `CollectRecord.emp_id`는 CharField, CustomUser FK가 아니다

**함정**: 사번 필드이므로 `ForeignKey(CustomUser)` 로 구현하고 싶어진다.  
**실제 설계**: `CharField` — 엑셀 원본 사번을 그대로 저장. CustomUser DB에 없는 퇴직자도 기록 가능하도록 의도적으로 FK를 피했다. `CollectFeedback.emp_id`도 동일하다.

### ② `DepositSummary.surety_total`은 필터링된 값이다

**함정**: `DepositSurety` 레코드의 단순 합계로 계산하면 된다고 생각한다.  
**실제 설계**: `api_deposit_impl.py`의 `_calc_filtered_totals()`가 `status`, `product_type` 등 조건으로 필터링한 값을 반환한다. API 응답에서 `surety_total_all`, `other_total_all`은 원본 합계, `surety_total`, `other_total`은 필터링값이다.

### ③ `CommissionCommon` 유틸은 없어도 동작한다

**함정**: `window.CommissionCommon`이 undefined면 오류가 발생할 것이라 생각한다.  
**실제 설계**: `deposit_home.js`는 `const C = window.CommissionCommon || {};`로 받아 각 유틸을 `null` fallback으로 사용한다. 유틸이 없어도 기본 기능은 동작한다.

### ④ `views/__init__.py` lazy import 패턴을 일반 import로 바꾸면 안 된다

**함정**: `from .pages import deposit_home` 같은 일반 import로 단순화하고 싶어진다.  
**실제 설계**: `__getattr__` 기반 lazy import는 순환 참조 방지 + 특정 모듈 로드 실패 시 나머지 뷰가 501 stub으로 유지되어 서비스 전체가 다운되지 않도록 설계되었다.

### ⑤ `CollectDropdownFeedback`에 UniqueConstraint를 추가하면 안 된다

**함정**: "emp_id+ym+feedback_type 당 1건이어야 한다"고 오해하여 UniqueConstraint를 추가한다.  
**실제 설계**: 이력 누적이 목적이다. 최신 1건은 `_latest_branch_feedback_subquery()` / `_latest_hq_feedback_subquery()`로 Subquery 조회한다. UniqueConstraint 추가 시 이 Subquery 패턴 전체를 교체해야 한다.

### ⑥ `collect_home.html`은 `{% block content %}`를 쓰지 않는다

**함정**: 다른 commission 페이지와 같이 `{% block content %}`를 사용한다고 가정한다.  
**실제 설계**: `{% block content_wrapper %}`를 사용한다 — 와이드 테이블(86vw)을 위해 `container` 래핑을 직접 제어하는 레이아웃이다.

### ⑦ `PART_ALIAS`는 upload_handlers/collect.py에만 있고 서비스에도 적용된다

**함정**: 부서명 alias 치환이 업로드 시에만 필요하다고 생각한다.  
**실제 설계**: `commission/services/collect.py`의 SSOT인 `PART_ALIAS = {"1인GA사업부": "MA사업4부"}`가 업로드 핸들러 내 row 파싱 시 치환을 담당한다 (collect.py:252). 서비스 조회 시에는 이미 치환된 값이 DB에 저장되어 있다.

### ⑧ Deposit 페이지의 `grade_required("staff", "admin", "superuser")`는 실제 존재하지 않는 등급명이다

**함정**: "staff"와 "admin"이 유효한 등급이라고 가정하고 새 사용자에게 부여하려 한다.  
**실제 설계**: 공식 등급은 `superuser`, `head`, `leader`, `basic`, `resign`, `inactive`이다. `GRADE_ALIAS_MAP`이 비어 있으므로 "staff", "admin"은 일치하는 사용자가 없을 가능성이 높다. 현재 동작 방식을 검증한 후 등급명을 정정해야 한다.

---

## 14. 회귀 위험 체크리스트

commission 앱 수정 시 반드시 확인:

### 업로드 관련
- [ ] 새 핸들러 추가 후 `registry.py`에 등록했는가?
- [ ] `DepositSurety` / `DepositOther` 업로드 핸들러 수정 시 "사번 단위 DELETE → bulk_create" 패턴이 유지되는가?
- [ ] `_norm_emp_id()` 호출이 모든 핸들러의 emp_id 파싱에 적용되는가?
- [ ] 업로드 후 `DepositUploadLog` 또는 `CollectUploadLog` upsert가 실행되는가?

### Collect 서비스
- [ ] 새 조회 함수가 `_apply_scope(qs, user, part, bizmoon)`을 통과하는가? (leader 팀 스코프 필수)
- [ ] N+1 쿼리 발생 여부: Subquery 대신 루프 내 DB 조회가 생기지 않았는가?
- [ ] `CollectFeedback` 수정/삭제에 `select_for_update()`가 적용되어 있는가?
- [ ] `transaction.atomic()` 블록 내에서 업로드 처리가 이루어지는가?

### 권한
- [ ] 새 Collect API 뷰에 `@login_required` + `@grade_required("superuser", "head", "leader")`가 모두 적용되었는가?
- [ ] 드롭다운 피드백 `feedback_type=hq` 저장이 superuser로만 제한되는가?
- [ ] `_can_view_target()` 로직이 Deposit API의 타인 조회를 차단하는가?

### 템플릿/JS
- [ ] `id="deposit-home"` / `id="collect-home"` / `id="approval-home"` 루트 요소 id가 변경되지 않았는가?
- [ ] 새 API URL 추가 시 해당 `data-*-url` 속성이 템플릿에 추가되었는가?
- [ ] `collect_home.js`가 `type="module"`인 상태에서 `window.CommissionCommon`을 정상적으로 읽는가?
- [ ] SheetJS(`vendor/xlsx/0.18.5/xlsx.full.min.js`)가 `collect_home.js`보다 먼저 로드되는가?

### 모델
- [ ] `CollectRecord` 필드 추가 후 `_serialize_record()` 반환 dict에 반영했는가?
- [ ] migration 생성 후 `collect_home.js` 테이블 렌더링 함수에도 컬럼이 추가되었는가?
- [ ] `UniqueConstraint(emp_id, ym)` 키가 그대로인가? (변경 시 bulk upsert 로직 전면 수정 필요)
