# django_ma Commission App 최종 운영·개발 지침서

> 기준일: 2026-04-30  
> 대상 앱: `commission`  
> 목적: 앞으로 새로운 채팅에서 전체 소스코드를 다시 공유하지 않더라도, `commission` 앱 관련 보안 취약점 보완, 성능 개선, 기능 변화 0 리팩토링, 업로드/다운로드 오류, 프론트 렌더링 오류, 환수관리 이슈에 일관되게 대응하기 위한 기준 문서입니다.  
> 현재 문서는 **패치 지시서가 아니라 기준 지침서**입니다. 실제 코드 수정은 사용자가 “패치 진행”을 명시한 뒤 diff 형식으로 별도 진행합니다.

---

## 0. 최상위 원칙

Commission 앱은 수수료·채권·환수·결재 데이터를 다루는 민감 업무 앱입니다. 따라서 모든 개선은 다음 순서를 우선합니다.

1. **보안**
   - 인증/권한/스코프 검증이 최우선입니다.
   - 수수료, 채권, 환수, 지급액, 보증보험, 기타채권, 피드백 데이터는 내부 민감정보로 취급합니다.
   - 파일 다운로드는 token만으로 열리면 안 됩니다.
   - 업로드 파일은 서버단에서 크기, 확장자, MIME, 파일 구조를 검증해야 합니다.

2. **기능 변화 0**
   - 사용자가 리팩토링이나 패치를 요청해도 UI·동작·URL·템플릿 DOM 계약은 기본적으로 바꾸지 않습니다.
   - 기존 URL name, DOM id, data-* 속성, JS 이벤트 계약, 업로드 타입 문자열은 유지합니다.
   - 개선은 내부 구현을 더 안전하고 빠르게 만드는 방식으로 진행합니다.

3. **SSOT 재사용**
   - 업로드 타입은 `commission/upload_handlers/registry.py`가 기준입니다.
   - 엑셀 파싱/컬럼 탐지/변환은 `commission/upload_utils/`가 기준입니다.
   - JSON 응답과 파일명 처리는 `commission/views/utils_json.py`가 기준입니다.
   - 임시 업로드 저장/삭제는 `commission/views/_files.py`가 기준입니다.
   - 월도 파싱은 `commission/views/_ym.py`가 기준입니다.
   - 프론트 공통 유틸은 `window.CommissionCommon.*`가 기준입니다.

4. **권한은 서버에서 최종 판단**
   - 템플릿에서 버튼을 숨기는 것은 UX일 뿐입니다.
   - 실제 접근 가능 여부는 view, service, queryset scope에서 강제합니다.
   - `CustomUser.pk == 사번 문자열` 규약을 절대 깨지 않습니다.

5. **운영 안정성**
   - 업로드/다운로드/대량 삭제/대량 upsert는 transaction과 audit/logging을 고려합니다.
   - 예외는 삼키지 말고 서버 로그에 남기며, 사용자에게는 내부정보 없는 메시지를 반환합니다.
   - 임시파일은 finally 또는 안전한 정리 로직으로 제거합니다.

---

## 1. Commission 앱 기능 범위

Commission 앱은 크게 네 개의 도메인으로 구성됩니다.

| 도메인 | 기능 | 주요 데이터 |
|---|---|---|
| Deposit / 채권관리 | 대상자별 채권·보증보험·기타채권·수수료 지표 조회, 지원신청서 텍스트 생성, 엑셀 업로드 | `DepositSummary`, `DepositSurety`, `DepositOther`, `DepositUploadLog` |
| Approval / 수수료결재 | 월도/부서별 수수료 미결현황 조회, 엑셀 업로드, 엑셀 다운로드 | `ApprovalPending`, `ApprovalExcelUploadLog` |
| Efficiency / 지점효율 | 월도/부서별 지급 초과현황 조회, 엑셀 업로드, 엑셀 다운로드 | `EfficiencyPayExcess`, `ApprovalExcelUploadLog` |
| Collect / 환수관리 | 환수 대상자 조회, 탭별 분류, 지점/본사 피드백, 피드백 이력, 안내문자, 엑셀 업로드/다운로드 | `CollectRecord`, `CollectFeedback`, `CollectDropdownFeedback`, `CollectUploadLog`, `DepositSummary` |

---

## 2. 디렉터리 구조 기준

현재 기준 Commission 앱은 다음 구조로 이해합니다.

```text
commission/
├─ apps.py
├─ urls.py
├─ models.py
├─ admin.py
│
├─ templates/
│  └─ commission/
│     ├─ deposit_home.html
│     ├─ approval_home.html
│     ├─ collect_home.html
│     └─ _approval_upload_modal.html
│
├─ views/
│  ├─ __init__.py
│  ├─ pages.py
│  ├─ api_deposit.py
│  ├─ api_deposit_impl.py
│  ├─ api_upload.py
│  ├─ approval.py
│  ├─ api_collect.py
│  ├─ downloads.py
│  ├─ constants.py
│  ├─ utils_json.py
│  ├─ utils_excel.py
│  ├─ utils_fail_excel.py
│  ├─ _excel_export.py
│  ├─ _files.py
│  └─ _ym.py
│
├─ services/
│  └─ collect.py
│
├─ upload_handlers/
│  ├─ __init__.py
│  ├─ registry.py
│  ├─ deposit.py
│  ├─ approval.py
│  ├─ efficiency.py
│  └─ collect.py
│
├─ upload_utils/
│  ├─ __init__.py
│  ├─ upload_utils.py
│  ├─ _convert.py
│  ├─ _detect.py
│  ├─ _readers.py
│  └─ _db.py
│
└─ templatetags/
   └─ commission_extras.py
```

프론트 정적 파일은 다음 구조로 이해합니다.

```text
static/
├─ css/
│  └─ apps/
│     └─ commission.css
│
└─ js/
   ├─ commission/
   │  ├─ _dom.js
   │  ├─ _format.js
   │  ├─ _net_json.js
   │  ├─ _modals.js
   │  ├─ deposit_home.js
   │  ├─ approval_excel_upload.js
   │  ├─ approval_home_export.js
   │  └─ collect_home.js
   │
   └─ excel_upload.js
```

---

## 3. URL 기준

`commission/urls.py`의 URL name은 변경하지 않습니다. 신규 기능은 기존 name을 바꾸지 않고 신규 URL만 추가합니다.

### 3.1 Pages

| URL | View | Name | 비고 |
|---|---|---|---|
| `/commission/` | `redirect_to_deposit` | `commission_home` | deposit으로 redirect |
| `/commission/deposit/` | `deposit_home` | `deposit_home` | 채권관리 |
| `/commission/approval/` | `approval_home` | `approval_home` | 수수료결재 |
| `/commission/collect/` | `collect_home` | `collect_home` | 환수관리 |

### 3.2 Upload APIs

| URL | View | Name | 비고 |
|---|---|---|---|
| `/commission/upload-excel/` | `upload_excel` | `upload_excel` | 채권/환수관리 registry 기반 업로드 |
| `/commission/approval/upload-excel/` | `approval_upload_excel` | `approval_upload_excel` | approval/efficiency 업로드 |

### 3.3 Downloads

| URL | View | Name | 비고 |
|---|---|---|---|
| `/commission/download/upload-fail/` | `download_upload_fail_excel` | `download_upload_fail_excel` | fail token 기반 다운로드 |
| `/commission/approval/excel/pending/` | `download_approval_pending_excel` | `download_approval_pending_excel` | 수수료 미결 다운로드 |
| `/commission/approval/excel/efficiency-excess/` | `download_efficiency_excess_excel` | `download_efficiency_excess_excel` | 지점효율 초과 다운로드 |

### 3.4 Deposit APIs

| URL | View | Name |
|---|---|---|
| `/commission/api/user-detail/` | `api_user_detail` | `api_user_detail` |
| `/commission/api/deposit-summary/` | `api_deposit_summary` | `api_deposit_summary` |
| `/commission/api/deposit-surety/` | `api_deposit_surety_list` | `api_deposit_surety_list` |
| `/commission/api/deposit-other/` | `api_deposit_other_list` | `api_deposit_other_list` |
| `/commission/api/support-pdf/` | `api_support_pdf` | `api_support_pdf` |

> `api_support_pdf`라는 이름이 남아 있어도, 현재 프론트에서는 PDF가 아니라 지원신청서 텍스트 모달 흐름으로 동작할 수 있습니다. URL name은 호환성 때문에 유지합니다.

### 3.5 Collect APIs

| URL | View | Name |
|---|---|---|
| `/commission/collect/api/list/` | `api_collect_list` | `api_collect_list` |
| `/commission/collect/api/ym-list/` | `api_collect_ym_list` | `api_collect_ym_list` |
| `/commission/collect/api/feedback/` | `api_collect_feedback_list` | `api_collect_feedback_list` |
| `/commission/collect/api/feedback/create/` | `api_collect_feedback_create` | `api_collect_feedback_create` |
| `/commission/collect/api/feedback/update/` | `api_collect_feedback_update` | `api_collect_feedback_update` |
| `/commission/collect/api/feedback/delete/` | `api_collect_feedback_delete` | `api_collect_feedback_delete` |
| `/commission/collect/api/dropdown-feedback/save/` | `api_collect_dropdown_feedback_save` | `api_collect_dropdown_feedback_save` |

---

## 4. 모델 기준

### 4.1 DepositSummary

사용자 단위 채권 요약입니다.

핵심 규약:

```text
DepositSummary.user = OneToOneField(CustomUser, primary_key=True)
DepositSummary PK == CustomUser.id == 사번 문자열
```

주요 필드 그룹:

| 그룹 | 필드 예시 |
|---|---|
| 기본/요약 | `final_payment`, `sales_total`, `refund_expected`, `pay_expected`, `maint_total` |
| 채권/보증/기타 | `debt_total`, `surety_total`, `other_total`, `required_debt`, `final_excess_amount` |
| 분급/계속분 | `div_1m`, `div_2m`, `div_3m`, `inst_current`, `inst_prev` |
| 환수/지급 | `refund_ns`, `refund_ls`, `pay_ns`, `pay_ls` |
| 보증 O/X | `surety_o_refund_*`, `surety_x_refund_*`, `surety_o_pay_*`, `surety_x_pay_*` |
| 장기 수수료 | `comm_3m`, `comm_6m`, `comm_9m`, `comm_12m` |
| 유지율/수금율 | `ns_13_round`, `ns_18_round`, `ls_13_round`, `ls_18_round`, `ns_18_total`, `ns_25_total`, `ls_18_total`, `ls_25_total`, `ns_2_6_due`, `ns_2_13_due`, `ls_2_6_due`, `ls_2_13_due` |

주의:

- `DepositSummary`는 업로드 핸들러에서 사번 기준 upsert됩니다.
- 현재 일부 deposit 업로드 핸들러는 row-by-row `update_or_create` 구조입니다. 성능 개선 시 bulk upsert 후보입니다.
- 단, bulk 전환 시 기존 누락 사용자 집계, missing_sample, upload log semantics를 유지해야 합니다.

### 4.2 DepositSurety

보증보험 상세입니다. 사용자 1:N 관계입니다.

핵심 필드:

- `user`
- `product_name`
- `policy_no`
- `amount`
- `status`
- `start_date`
- `end_date`

주의:

- 프론트에서는 `policy_no`가 긴 값일 수 있어 ellipsis-cell로 표시하고 TextViewer 모달로 전체 내용을 봅니다.
- 서버 응답에서 개인정보 또는 민감 증권번호 노출 범위를 검토할 수 있습니다.

### 4.3 DepositOther

기타채권 상세입니다. 사용자 1:N 관계입니다.

핵심 필드:

- `user`
- `product_name`
- `product_type`
- `amount`
- `bond_no`
- `status`
- `start_date`
- `memo`

주의:

- `memo`, `bond_no`는 민감할 수 있으므로 출력 범위와 권한을 확인합니다.
- 프론트는 `memo`를 ellipsis-cell + TextViewer로 표시합니다.

### 4.4 DepositUploadLog

채권 업로드 로그입니다.

Unique 기준:

```text
(part, upload_type)
```

필드:

- `part`
- `upload_type`
- `uploaded_at`
- `row_count`
- `file_name`

업로드 로그 갱신 SSOT:

```text
commission.upload_handlers.deposit._update_upload_log
```

### 4.5 ApprovalExcelUploadLog

Approval/Efficiency 업로드 로그입니다.

Unique 기준:

```text
(ym, part, kind)
```

kind:

- `efficiency`
- `approval`

필드:

- `ym`
- `part`
- `kind`
- `uploaded_by`
- `uploaded_at`
- `row_count`
- `file_name`

### 4.6 ApprovalPending

수수료 미결 현황입니다.

Unique 기준:

```text
(ym, user)
```

핵심 필드:

- `ym`
- `user`
- `emp_name`
- `actual_pay`
- `approval_flag`

업로드 기준:

- 실지급액 > 0
- 결재값 == `N`
- DB 유자격: `regist in {"손생등록", "생보등록", "손보등록"}`
- 같은 사번 여러 행은 실지급액 합산

### 4.7 EfficiencyPayExcess

지점효율 지급 초과 현황입니다.

Unique 기준:

```text
(ym, user)
```

핵심 필드:

- `ym`
- `user`
- `pay_amount_sum`

조회 기준:

- `EXCESS_THRESHOLD = 10_000_000`
- 화면에서는 threshold 초과 데이터만 표시합니다.

### 4.8 Collect 도메인 모델

환수관리 관련 모델은 다음 기준으로 이해합니다.

| 모델 | 역할 |
|---|---|
| `CollectRecord` | 월도별 환수 대상자 원본/계산 데이터 |
| `CollectFeedback` | 대상자별 수기 피드백 이력 |
| `CollectDropdownFeedback` | 대상자+월도별 지점/본사 드롭다운 피드백 |
| `CollectUploadLog` | 환수관리 업로드 로그 |

주의:

- Collect 조회는 `commission/services/collect.py` 서비스 레이어가 SSOT입니다.
- view에서 직접 ORM을 추가하지 않습니다.

---

## 5. View Layer 기준

### 5.1 `commission/views/__init__.py`

역할:

- `commission.views` import surface를 안정화합니다.
- URLConf가 `from . import views` 패턴으로 동작할 수 있도록 lazy import를 제공합니다.
- pages, upload, deposit APIs, approval uploads, downloads, collect APIs를 이름별로 lazy resolve합니다.
- approval/efficiency upload 모듈 import 실패 시 501 stub을 반환할 수 있습니다.

주의:

- 이 파일은 호환성 레이어입니다.
- 실제 구현 위치를 바꿔도 URLConf import가 깨지지 않게 유지합니다.
- 단, 501 stub은 운영에서 호출되면 안 되는 최후 안전망입니다. 정상 구현에서는 실제 view가 import되어야 합니다.

### 5.2 `commission/views/pages.py`

역할:

- HTML 페이지 렌더링.
- `deposit_home`, `approval_home`, `collect_home`.
- 공통 parts 목록, upload types, upload logs, selected_ym, pending/efficiency rows 등을 context로 구성합니다.

주요 helper:

| 함수 | 역할 |
|---|---|
| `_list_parts_excluding_centers()` | 센터 제외 부서 목록 |
| `_ym_from_year_month()` | `YYYY-MM` 생성 |
| `_parse_year_month()` | GET year/month 파싱 |
| `_year_options()` | 연도 옵션 |
| `_month_options()` | 월 옵션 |
| `_accounts_search_url()` | accounts 검색 URL reverse fallback |
| `redirect_to_deposit()` | commission root redirect |
| `deposit_home()` | 채권관리 페이지 |
| `approval_home()` | 수수료결재 페이지 |
| `collect_home()` | 환수관리 페이지 |

주의:

- `accounts_search_url`은 공통 검색 모달 계약에 중요합니다.
- 템플릿 DOM id와 dataset URL은 JS가 직접 의존합니다.
- 페이지 권한 데코레이터는 실제 데이터 민감도에 맞게 검토 대상입니다.

### 5.3 `commission/views/api_deposit_impl.py`

Deposit 조회 실제 구현입니다.

핵심 책임:

1. 요청에서 대상자 ID 파싱
2. 대상자 조회
3. 권한 검증
4. payload 생성
5. JSON 응답

대상자 ID 파라미터 호환:

```text
user, id, emp_id, employee_id, regist, username
```

대상자 조회:

- 기본은 `CustomUser.pk` / `CustomUser.id`
- legacy 필드 `emp_id`, `regist`, `username`도 방어적으로 탐색
- `only("id", "name", "part", "branch", "enter", "quit", "regist", "grade")`로 최소 조회

권한 기준:

```text
superuser, main_admin, head → 열람 가능
그 외 → 본인만 열람 가능
```

주의:

- Deposit 데이터는 채권/수수료 민감정보이므로 이 권한 정책은 매우 중요합니다.
- 향후 `leader`에게 팀 단위 조회를 허용할지 여부는 정책 결정 후 별도 적용해야 합니다.
- 프론트 대상자 검색에서 보였다고 해서 API 조회 권한이 있는 것은 아닙니다. API에서 최종 차단해야 합니다.

### 5.4 `commission/views/api_deposit.py`

Backward-compatible shim입니다.

역할:

- 우선 `commission.views.api.deposit` import 시도.
- 실패 시 `commission.views.api_deposit_impl`.
- 누락 attr은 501 JSON fallback.

주의:

- 실제 구현은 `api_deposit_impl.py` 기준입니다.
- 이 shim은 import path 호환용입니다.

### 5.5 `commission/views/api_upload.py`

Deposit/Collect registry 기반 업로드 API입니다.

현재 기준:

```python
@csrf_exempt
@require_POST
@grade_required("superuser")
def upload_excel(request):
    ...
```

입력:

- `part`
- `upload_type`
- `excel_file`

처리 흐름:

1. part 필수 검증
2. upload_type 지원 여부 검증
3. 파일 존재 검증
4. registry에서 spec 조회
5. 임시 저장
6. transaction.atomic
7. mode에 따라 df/file handler 호출
8. 업로드 로그 갱신
9. fail token 생성
10. JSON 응답

중요 SSOT:

- `commission.upload_handlers.registry.get_upload_spec`
- `commission.upload_handlers.registry.supported_upload_types`
- `commission.views._files.save_temp_upload`
- `commission.views._files.safe_delete`
- `commission.upload_utils._read_excel_safely`
- `commission.upload_handlers._update_upload_log`

보안 점검 후보:

- `csrf_exempt` 제거 또는 대체 필요.
- 파일 크기/확장자/MIME 서버단 검증 필요.
- `part` 파라미터가 실제 사용자의 업로드 허용 범위인지 확인 필요.
- fail token을 사용자/세션/스코프와 바인딩해야 합니다.
- 업로드 성공/실패 audit log 일관성 검토 필요.

성능 점검 후보:

- DataFrame handler 내부 row-by-row update 개선.
- 대용량 파일 파싱 전 파일 크기 제한.
- fail rows 전체 저장 여부와 cache payload 크기 제한.
- transaction 범위 내에서 불필요한 파일 읽기/큰 처리 포함 여부 검토.

### 5.6 `commission/views/approval.py`

Approval/Efficiency 업로드 API입니다.

현재 기준:

```python
@csrf_exempt
@require_POST
@grade_required("superuser")
def approval_upload_excel(request):
    ...
```

입력:

- `ym` 또는 `year/month`
- `part`
- `kind`
- `excel_file`

kind:

```text
approval
efficiency
```

처리 흐름:

1. `resolve_ym()`으로 월도 파싱
2. kind 검증
3. 파일 존재 검증
4. 임시 저장
5. transaction.atomic
6. `_common_upload()` 호출
7. 기존 데이터 삭제
8. handler 실행
9. `ApprovalExcelUploadLog.update_or_create`
10. fail token 생성
11. audit log

주의:

- `_common_upload()`는 기존 데이터 삭제 후 신규 handler upsert를 수행합니다.
- 삭제 범위는 `ym`과 선택 `part` 기준입니다.
- 삭제와 upsert가 같은 transaction에 있어야 합니다.
- `part`가 빈 문자열이면 전체를 대상으로 삭제/업로드될 수 있습니다.

보안 점검 후보:

- `csrf_exempt` 제거.
- 파일 검증 추가.
- part scope 검증.
- audit meta에서 파일명/오류/파라미터 마스킹 검토.
- 실패 다운로드 token owner binding.

성능 점검 후보:

- raw matrix를 row_count 계산과 handler에서 중복 읽는 구조 최적화 가능.
- 대량 삭제 범위에 인덱스 영향 확인.
- `delete()` 후 bulk_create 방식은 단순하지만, 대량일 때 lock/시간 확인 필요.

### 5.7 `commission/views/downloads.py`

Excel 다운로드 view입니다.

다운로드 종류:

1. `download_upload_fail_excel`
2. `download_approval_pending_excel`
3. `download_efficiency_excess_excel`

현재 특징:

- `@require_GET`만 적용된 함수가 존재합니다.
- fail download는 token만 있으면 cache payload를 내려줄 수 있습니다.
- approval/efficiency export는 queryset 전체 또는 최신 ym 기준으로 rows 생성 후 xlsx 응답을 반환합니다.

보안 점검 후보:

- 로그인/권한 데코레이터 추가.
- superuser/head/leader 스코프 정책 확정.
- fail token을 생성한 사용자/세션/업로드 스코프와 묶기.
- token 재사용/만료/노출 방어.
- 다운로드 audit log 추가.

성능 점검 후보:

- 대량 rows → pandas DataFrame → BytesIO는 메모리 사용량이 큼.
- 대량 다운로드는 iterator/openpyxl write_only 또는 streaming 검토 가능.
- `select_related("user")`는 유지해야 합니다.
- fields를 `.only()` 또는 `.values()`로 제한할 수 있습니다.

### 5.8 `commission/views/api_collect.py`

Collect API wrapper입니다.

기준 원칙:

- `@login_required`
- `@grade_required("superuser", "head", "leader")`
- JSON 응답은 `_json_ok`, `_json_error`
- 비즈니스 로직은 `commission.services.collect`만 호출
- 피드백 생성/수정/삭제는 audit log 연동

API별 책임:

| 함수 | 메서드 | 역할 |
|---|---|---|
| `api_collect_list` | GET | 탭별 환수 목록 조회 |
| `api_collect_ym_list` | GET | 월도 드롭다운 조회 |
| `api_collect_feedback_list` | GET | 대상자 피드백 이력 조회 |
| `api_collect_feedback_create` | POST | 피드백 생성 |
| `api_collect_feedback_update` | POST | 피드백 수정 |
| `api_collect_feedback_delete` | POST | 피드백 삭제 |
| `api_collect_dropdown_feedback_save` | POST | 지점/본사 드롭다운 피드백 저장 |

주의:

- view는 서비스 레이어 호출만 담당해야 합니다.
- 권한 판정은 서비스에서도 재검증되어야 합니다.
- 피드백 본문은 XSS 방지상 HTML로 저장/렌더링하지 않고 텍스트로 처리해야 합니다.

---

## 6. Service Layer 기준

### 6.1 `commission/services/collect.py`

Collect 도메인 로직 SSOT입니다.

핵심 원칙:

- view는 이 모듈만 호출합니다.
- 직접 ORM은 service layer에 둡니다.
- 수정/삭제 권한 판정은 service layer에서 수행합니다.
- N+1 방지를 위해 Subquery + annotate를 활용합니다.
- 수정/삭제에는 `transaction.atomic()`과 필요 시 `select_for_update()`를 사용합니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `ym_to_date()` | `YYYYMM` → date |
| `date_to_ym()` | date → `YYYYMM` |
| `offset_ym()` | 월도 offset |
| `_parse_surety_bond_detail()` | `"채권:0 / 보증:0"` 파싱 |
| `_build_deposit_map()` | DepositSummary의 기타합계/환수예상 bulk 조회 |
| `_latest_feedback_subquery()` | 최신 피드백 annotate |
| `_latest_branch_feedback_subquery()` | 최신 지점 드롭다운 피드백 annotate |
| `_latest_hq_feedback_subquery()` | 최신 본사 드롭다운 피드백 annotate |
| `_get_allowed_emp_ids_for_leader()` | leader 팀 scope 계산 |
| `_apply_scope()` | superuser/head/leader 스코프 적용 |
| `_serialize_record()` | CollectRecord → API row dict |
| `get_available_yms()` | 월도 목록 |
| `get_available_parts()` | 부서 목록 |
| `get_available_bizmoons()` | 부문 목록 |
| `get_collect_all()` | 전체 탭 |
| `get_collect_new()` | 신규 탭 |
| `get_collect_long3/6/12()` | 장기 탭 |
| `get_collect_list()` | 탭 dispatcher |
| `get_feedbacks()` | 피드백 이력 |
| `create_feedback()` | 피드백 생성 |
| `update_feedback()` | 피드백 수정 |
| `delete_feedback()` | 피드백 삭제 |
| `save_dropdown_feedback()` | 드롭다운 피드백 저장 |

권한 스코프:

```text
superuser → 전체, 단 part/bizmoon 필터 적용
head      → 본인 branch 고정
leader    → SubAdminTemp 팀 기준, 팀 미설정 시 본인 branch fallback
```

주의:

- `_apply_scope()`는 조회뿐 아니라 대상자 피드백 접근 정책과도 정합되어야 합니다.
- leader scope 계산이 부정확하면 타 지점/타 팀 환수 데이터가 노출될 수 있습니다.
- 피드백 생성/수정/삭제도 대상 emp_id가 요청자의 scope 안인지 확인해야 합니다.

---

## 7. Upload Registry 기준

### 7.1 `commission/upload_handlers/registry.py`

업로드 타입 SSOT입니다.

```python
@dataclass(frozen=True)
class UploadSpec:
    upload_type: str
    mode: Literal["df", "file"]
    fn: Callable
    msg_tpl: str
```

mode 의미:

| mode | 처리 방식 |
|---|---|
| `df` | view에서 `_read_excel_safely()`로 DataFrame 생성 후 handler에 전달 |
| `file` | view에서 임시 파일 경로와 원본명 전달 |

지원 upload_type:

| upload_type | mode | handler |
|---|---|---|
| `최종지급액` | df | `deposit.handle_upload_final_payment` |
| `환수지급예상` | df | `deposit.handle_upload_refund_pay_expected` |
| `보증증액` | df | `deposit.handle_upload_guarantee_increase` |
| `채권지표` | df | `deposit.handle_upload_deposit_metrics` |
| `응당생보` | df | `deposit.handle_upload_ls_due` |
| `응당손보` | df | `deposit.handle_upload_ns_due` |
| `보증보험` | df | `deposit.handle_upload_surety` |
| `기타채권` | df | `deposit.handle_upload_other_debt` |
| `통산손보` | file | `deposit.handle_upload_ns_total_from_file` |
| `통산생보` | file | `deposit.handle_upload_ls_total_from_file` |
| `환수관리` | df | `collect.handle_upload_collect` |

신규 업로드 타입 추가 절차:

1. `upload_handlers/<domain>.py`에 handler 추가.
2. 필요 시 `upload_utils`의 reader/detect/convert 재사용.
3. `registry.py`에 UploadSpec 추가.
4. 화면의 upload type select에 옵션 추가.
5. `SUPPORTED_UPLOAD_TYPES` 자동 반영 확인.
6. 업로드 로그 정책 확인.
7. 실패행/fail token 정책 확인.
8. 테스트 시나리오 추가.

금지:

- view에서 upload_type 문자열별 if/elif를 직접 늘리는 방식.
- registry를 우회하여 임의 handler 호출.
- upload_type 문자열 변경.

---

## 8. Upload Handlers 기준

### 8.1 `upload_handlers/deposit.py`

채권 업로드 핸들러 SSOT입니다.

핵심 helper:

| 함수 | 역할 |
|---|---|
| `_existing_ids(ids)` | CustomUser 존재 여부 bulk 조회 + missing_sample |
| `_update_summary(uid, defaults)` | DepositSummary upsert |
| `_update_upload_log()` | DepositUploadLog 갱신 SSOT |

주요 handler:

| 함수 | 역할 |
|---|---|
| `handle_upload_final_payment()` | 최종지급액 |
| `handle_upload_refund_pay_expected()` | 환수/지급예상 |
| `handle_upload_deposit_metrics()` | 채권지표 |
| `handle_upload_guarantee_increase()` | 보증증액 호환 |
| `handle_upload_ls_due()` | 응당생보 |
| `handle_upload_ns_due()` | 응당손보 |
| `handle_upload_surety()` | 보증보험 상세 |
| `handle_upload_other_debt()` | 기타채권 상세 |
| `handle_upload_ns_total_from_file()` | 통산손보 raw matrix |
| `handle_upload_ls_total_from_file()` | 통산생보 raw matrix |

성능상 주의:

- `DepositSummary.objects.update_or_create()`가 row-by-row로 호출되는 handler는 대량 업로드 시 병목입니다.
- 개선 시 bulk upsert로 전환할 수 있으나, 다음을 유지해야 합니다.
  - 누락 사용자 count
  - missing_sample
  - 기존 필드만 업데이트
  - default 값 semantics
  - upload log count
  - transaction 범위
  - 에러 메시지

보안상 주의:

- Excel 값은 신뢰하지 않습니다.
- 사번 정규화 후 CustomUser 존재 확인은 필수입니다.
- part scope가 필요한 업로드는 서버에서 강제해야 합니다.

### 8.2 `upload_handlers/approval.py`

수수료결재 업로드 handler입니다.

고정 컬럼:

| 컬럼 | index | 의미 |
|---|---:|---|
| B | 1 | 사원명 |
| C | 2 | 사번 |
| N | 13 | 실지급액 |
| O | 14 | 결재값 |

조건:

```text
pay > 0
flag == "N"
user.regist in {"손생등록", "생보등록", "손보등록"}
part가 있으면 user.part == part
```

처리:

- 동일 사번은 실지급액 합산.
- `ApprovalPending.bulk_create(update_conflicts=True)` 사용.

주의:

- part를 빈 값으로 넘기면 전체 대상입니다.
- part scope는 업로드 view에서 현재 사용자의 권한과 함께 검증해야 합니다.
- raw matrix 파일 구조가 바뀌면 고정 index 기반이 깨질 수 있습니다.

### 8.3 `upload_handlers/efficiency.py`

지점효율 지급 초과 handler입니다.

핵심 로직:

- 상단 0~5행에서 `구분`, `금액` 또는 `지급액` 헤더 탐지.
- 사번은 E열(index 4).
- `구분 == "지급"` 행만 합산.
- 지급 금액이 0이면 제외.
- part가 있으면 user.part로 scope 제한.
- `EfficiencyPayExcess.bulk_create(update_conflicts=True)` 사용.

주의:

- 파일 양식 편차가 크면 header detection 실패 가능.
- 실패 메시지는 사용자가 이해할 수 있게 유지합니다.
- part scope 검증은 서버단에서 추가로 보강해야 합니다.

### 8.4 `upload_handlers/collect.py`

환수관리 업로드 handler입니다.

엑셀 구조 기준:

```text
헤더: 1행 (index 0)
합계행: 2행 (index 1)
실데이터: 3행 (index 2)부터
```

핵심 상수:

- `PART_ALIAS`
- `COL_MAP`
- `UPDATE_FIELDS`

필수 컬럼:

```text
사번
월도
최종지급액
```

처리 흐름:

1. 컬럼명 normalize.
2. 필수 컬럼 존재 확인.
3. 행별 파싱.
4. emp_id 정규화.
5. ym 정규화.
6. 빈 emp_id/ym 스킵.
7. `CollectRecord.bulk_create(update_conflicts=True)`.
8. `CollectUploadLog.update_or_create`.
9. 결과 dict 반환.

주의:

- handler는 순수 처리에 가깝고, audit log는 view에서 담당하는 구조입니다.
- upload_type=`환수관리`는 기존 `upload_excel` view를 재사용합니다.
- 현재 `upload_excel`은 `part`를 필수로 요구하므로 collect_home에서는 hidden `part=전체`로 전달합니다.

---

## 9. Upload Utils 기준

### 9.1 `upload_utils/__init__.py`

공식 public API입니다. 외부에서는 하위 파일 직접 import보다 `commission.upload_utils` import를 우선합니다.

Export 범위:

- constants/converters
- column detection
- readers
- DB helpers

주의:

- 기존 import 경로 호환을 위해 `upload_utils/upload_utils.py` legacy shim도 유지합니다.

### 9.2 `_convert.py`

주요 함수:

| 함수 | 역할 |
|---|---|
| `_to_int()` | 숫자/문자/NaN → int |
| `_to_decimal()` | 숫자/문자/NaN → Decimal |
| `_safe_decimal_q2()` | Decimal 2자리 quantize |
| `_to_date()` | Timestamp/datetime/string → date |
| `_to_div()` | 분급/정상 정규화 |
| `_norm_emp_id()` | 사번 정규화, `1234567.0` → `1234567` |
| `_extract_emp7_from_a()` | raw A열에서 7자리 사번 추출 |

주의:

- `_to_int()`는 `int(float(s))`이므로 큰 숫자나 지수 표기 처리 시 정밀도 검토 가능.
- 사번은 문자열로 유지해야 하며, 숫자형 변환으로 앞자리 0이 사라지는 사고를 피해야 합니다.

### 9.3 `_detect.py`

컬럼 탐지 SSOT입니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `_norm_col()` | 컬럼명 normalize |
| `_best_match_col()` | required/optional/ban token 기반 best match |
| `_find_col_by_aliases()` | alias group 기반 탐지 |
| `_detect_emp_id_col()` | 사번/사원코드/등록번호/FC코드 탐지 |
| `_detect_col()` | 범용 탐지 |
| `_find_exact_or_space_removed()` | 정확/공백제거/normalize 일치 |
| `_detect_refundpay_col()` | 환수/지급 관련 특화 탐지 |

사번 탐지 ban token:

```text
계약, 증권, 주민, 연락, 전화, 휴대, 메일, email
```

주의:

- 컬럼 탐지는 업로드 성공률에 직접 영향이 있습니다.
- 탐지 로직 변경은 반드시 여러 실제 양식으로 회귀 테스트합니다.

### 9.4 `_readers.py`

엑셀/텍스트/HTML reader SSOT입니다.

지원 케이스:

- `.xlsx`
- `.xls`
- HTML table 형태의 Excel
- CSV
- TSV
- semi-colon separated text
- raw matrix

주요 함수:

| 함수 | 역할 |
|---|---|
| `_decode_bytes_best_effort()` | utf-8/cp949/euc-kr 복원 |
| `_parse_first_html_table()` | HTML table 첫 번째 파싱 |
| `_read_text_table()` | CSV/TSV/text DataFrame |
| `_read_text_table_matrix()` | CSV/TSV/text raw matrix |
| `_read_excel_safely()` | 일반 업로드 reader |
| `_read_excel_raw_matrix()` | raw matrix reader |

보안 점검 후보:

- 파일 확장자와 실제 content sniffing 불일치 검증.
- 파일 크기 상한.
- HTML table 파싱 시 과도한 크기/중첩 방어.
- pandas/openpyxl parser exception 메시지 노출 제한.

### 9.5 `_db.py`

DB helper입니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `_bulk_existing_user_ids(ids)` | CustomUser 존재 PK bulk 조회 |
| `_update_upload_log()` | Deprecated wrapper → deposit SSOT 위임 |

주의:

- 업로드 로그 갱신은 `commission.upload_handlers.deposit._update_upload_log`가 기준입니다.

---

## 10. View Utils 기준

### 10.1 `_excel_export.py`

rows → xlsx response SSOT입니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `rows_to_xlsx_bytes()` | list[dict] → xlsx bytes |
| `xlsx_bytes_response()` | bytes → HttpResponse attachment |
| `rows_to_excel_response()` | one-shot helper |

주의:

- rows가 비어있으면 `b""` 반환합니다. 호출부에서 404 처리하는 패턴을 유지합니다.
- pandas + openpyxl 기반이므로 대량 export에서 메모리 사용량을 확인해야 합니다.

### 10.2 `_files.py`

임시 업로드 저장/삭제 SSOT입니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `save_temp_upload()` | UploadedFile을 FileSystemStorage에 저장 |
| `safe_delete()` | 실패해도 예외 전파 없이 temp 삭제 |

주의:

- 현재 `FileSystemStorage()` 기본 저장 위치를 사용합니다.
- 보안 개선 시 전용 temp dir, 파일명 sanitization, 확장자/MIME 검증을 이 흐름 앞단 또는 별도 util로 추가할 수 있습니다.
- 삭제 실패를 완전히 숨기면 운영 temp 누적이 생길 수 있으므로 로그 보강 후보입니다.

### 10.3 `_ym.py`

월도 파싱 SSOT입니다.

지원 입력:

```text
ym=YYYY-MM
ym=YYYYMM
year=YYYY & month=MM
```

주요 함수:

- `split_ym`
- `validate_ym`
- `resolve_ym`

주의:

- Approval은 `YYYY-MM`을 사용합니다.
- Collect는 `YYYYMM`을 사용합니다.
- 두 규약을 혼동하지 않습니다.

### 10.4 `utils_fail_excel.py`

fail rows를 xlsx로 cache에 저장하고 token을 반환합니다.

현재 구조:

```text
cache key = commission:upload_fail:{token}
payload = {"content": bytes, "filename": filename}
TTL = 1 hour
```

보안상 핵심 취약 후보:

- token만 알면 다운로드 가능할 수 있음.
- owner/session/권한 scope 바인딩이 없습니다.
- cache payload에 민감정보가 들어갈 수 있습니다.
- token 재사용/공유/로그 노출 리스크가 있습니다.

개선 방향:

- payload에 `owner_id`, `scope`, `created_at`, `purpose`, `upload_type` 저장.
- 다운로드 view에서 `request.user.id`와 일치 확인.
- 필요 시 superuser만 타인 token 허용.
- fail rows 전체 내용 최소화.
- 다운로드 시 audit log 기록.

### 10.5 `utils_json.py`

JSON 응답과 attachment filename SSOT입니다.

주요 함수:

| 함수 | 역할 |
|---|---|
| `_json_error()` | `{ok:false, message}` |
| `_json_ok()` | `{ok:true, ...}` |
| `_set_attachment_filename()` | ASCII fallback + RFC5987 `filename*` |

주의:

- Excel 다운로드 응답은 `_set_attachment_filename()`을 사용합니다.
- JSON 응답 포맷은 프론트의 `fetchJSON`과 맞아야 합니다.

---

## 11. 템플릿 DOM 계약

Commission 프론트는 템플릿 DOM id, data-*에 강하게 의존합니다. 아래 요소는 변경 금지입니다.

### 11.1 `deposit_home.html`

Root:

```html
<div id="deposit-home"
     data-user-detail-url="..."
     data-deposit-summary-url="..."
     data-deposit-surety-url="..."
     data-deposit-other-url="..."
     data-reset-url="..."
     data-support-pdf-url="...">
```

중요 버튼:

| id | 역할 |
|---|---|
| `resetUserBtn` | 대상자 초기화 |
| `supportPdfBtn` | 지원신청서 텍스트 모달 |

대상자 bind:

| id | data-bind |
|---|---|
| `target_emp_id` | `target.id` |
| `target_name` | `target.name` |
| `target_part` | `target.part` |
| `target_branch` | `target.branch` |
| `target_join_date` | `target.join_date_display` |
| `target_retire_date` | `target.retire_date_display` |

summary bind:

- `summary.final_payment`
- `summary.sales_total`
- `summary.refund_expected`
- `summary.pay_expected`
- `summary.maint_total`
- `summary.debt_total`
- `summary.surety_total`
- `summary.other_total`
- `summary.required_debt`
- `summary.final_excess_amount`
- `summary.div_1m`
- `summary.div_2m`
- `summary.div_3m`
- `summary.inst_current`
- `summary.inst_prev`
- `summary.refund_ns`
- `summary.refund_ls`
- `summary.pay_ns`
- `summary.pay_ls`
- `summary.surety_o_refund_ns`
- `summary.surety_o_refund_ls`
- `summary.surety_o_refund_total`
- `summary.surety_o_pay_ns`
- `summary.surety_o_pay_ls`
- `summary.surety_o_pay_total`
- `summary.surety_x_refund_ns`
- `summary.surety_x_refund_ls`
- `summary.surety_x_refund_total`
- `summary.surety_x_pay_ns`
- `summary.surety_x_pay_ls`
- `summary.surety_x_pay_total`
- `summary.comm_3m`
- `summary.comm_6m`
- `summary.comm_9m`
- `summary.comm_12m`
- `summary.ns_13_round`
- `summary.ns_18_round`
- `summary.ls_13_round`
- `summary.ls_18_round`
- `summary.ns_18_total`
- `summary.ns_25_total`
- `summary.ls_18_total`
- `summary.ls_25_total`
- `summary.ns_2_6_due`
- `summary.ns_2_13_due`
- `summary.ls_2_6_due`
- `summary.ls_2_13_due`

상세 테이블:

| id | 역할 |
|---|---|
| `suretyTable` | 보증보험 테이블 |
| `suretyColGroup` | 보증보험 colgroup |
| `suretyTableBody` | JS 렌더링 대상 |
| `otherTable` | 기타채권 테이블 |
| `otherColGroup` | 기타채권 colgroup |
| `otherTableBody` | JS 렌더링 대상 |

업로드 모달:

| id/name | 역할 |
|---|---|
| `excelUploadModal` | 엑셀 업로드 모달 |
| `excelUploadForm` | 공용 excel_upload.js 의존 |
| `uploadPartSelect` | part |
| `uploadTypeSelect` | upload_type |
| `excelFile` | 파일 input |
| `excelUploadResultModal` | 결과 모달 |
| `excelUploadResultBody` | 결과 본문 |
| `excelUploadReloadBtn` | 새로고침 버튼 |
| `uploadToast` | 완료 toast |

### 11.2 `approval_home.html`

Root:

```html
<div id="approval-home"
     data-selected-ym="{{ selected_ym }}"
     data-selected-part="{{ selected_part }}">
```

주요 DOM:

| id/selector | 역할 |
|---|---|
| `controlsForm` | 조회 form |
| `efficiencyExcessTable` | 지점효율 초과현황 테이블 |
| `approvalPendingTable` | 수수료 미결현황 테이블 |
| `[data-export-table]` | client xls export 버튼 |
| `[data-export-name]` | export file base name |

주의:

- 현재 title에 inline style이 남아 있습니다. CSP `unsafe-inline` 제거 시 후보입니다.
- export는 server download가 아니라 `approval_home_export.js`의 Blob 기반 `.xls` 생성입니다.

### 11.3 `_approval_upload_modal.html`

중요 DOM:

| id/name | 역할 |
|---|---|
| `approvalExcelUploadModal` | 모달 |
| `approvalUploadForm` | 업로드 form |
| `ym` | 월도 |
| `part` | 부서 |
| `kind` | approval/efficiency |
| `excel_file` | 파일 |
| `approvalUploadResult` | 결과 표시 |
| `approvalFailDownloadWrap` | 실패 다운로드 영역 |
| `approvalFailDownloadLink` | 실패 다운로드 링크 |
| `approvalUploadSubmitBtn` | 제출 버튼 |

주의:

- 이 partial에는 Bootstrap validation용 inline script가 있습니다.
- CSP 개선 시 외부 JS로 분리 후보입니다.
- 업로드 submit lock/네트워크 로직은 `approval_excel_upload.js`가 담당합니다.

### 11.4 `collect_home.html`

Root:

```html
<div id="collect-home"
     data-api-list-url="..."
     data-api-ym-list-url="..."
     data-api-feedback-list-url="..."
     data-api-feedback-create-url="..."
     data-api-feedback-update-url="..."
     data-api-feedback-delete-url="..."
     data-upload-url="..."
     data-search-user-url="..."
     data-default-ym="..."
     data-current-user-id="..."
     data-api-dropdown-feedback-save-url="..."
     data-current-user-grade="...">
```

필터 DOM:

| id | 역할 |
|---|---|
| `ymSelect` | 월도 |
| `bizmoonSelect` | 부문 |
| `partSelect` | 부서 |
| `branchSelect` | 영업가족 |
| `collectKeywordInput` | 키워드 |
| `collectSearchBtn` | 조회 |

탭/테이블:

| id/selector | 역할 |
|---|---|
| `collectTabs` | 탭 root |
| `[data-tab]` | 탭 버튼 |
| `collectExcelDownloadBtn` | SheetJS 엑셀 다운로드 |
| `collectTableHead` | JS가 컬럼 교체 |
| `collectTableBody` | JS가 row 렌더링 |

피드백 모달:

| id | 역할 |
|---|---|
| `feedbackManagerModal` | 피드백 관리 모달 |
| `openFeedbackManagerBtn` | 피드백 관리 버튼 |
| `feedbackSearchUserBtn` | 대상자 검색 |
| `selectedTargetDisplay` | 선택 대상자 표시 |
| `feedbackListBody` | 피드백 이력 |
| `feedbackDateInput` | 입력일 |
| `feedbackDepartment` | 담당부서 |
| `feedbackManager` | 담당자 |
| `feedbackContent` | 피드백 내용 |
| `feedbackSubmitBtn` | 저장 버튼 |

안내문자 모달:

| id | 역할 |
|---|---|
| `smsTemplateModal` | 안내문자 모달 |
| `smsTemplateBody` | 안내문자 본문 |
| `smsCopyBtn` | 복사 버튼 |

업로드 모달:

| id/name | 역할 |
|---|---|
| `excelUploadModal` | 업로드 모달 |
| `excelUploadForm` | 공용 excel_upload.js 의존 |
| hidden `part=전체` | upload_excel view의 part 필수 대응 |
| hidden `upload_type=환수관리` | registry 라우팅 |
| `excelFile` | 파일 input |
| `excelUploadResultModal` | 결과 모달 |
| `excelUploadResultBody` | 결과 본문 |
| `excelUploadReloadBtn` | 새로고침 |
| `uploadToast` | 완료 toast |

주의:

- `collect_home.html`에는 일부 inline style이 남아 있습니다.
- CSP 강화 시 CSS class로 이동해야 합니다.
- collect_home.js의 컬럼 순서와 CSS nth-child 규칙이 결합되어 있습니다.

---

## 12. JavaScript 공통 유틸 기준

### 12.1 `static/js/commission/_dom.js`

전역 namespace:

```javascript
window.CommissionCommon.dom
```

제공:

| 함수 | 역할 |
|---|---|
| `$()` | querySelector helper |
| `text()` | null-safe string trim |
| `safeSetText()` | 빈 값이면 `-` 표시 |

원칙:

- 전역에 추가만 합니다.
- 기존 consumer fallback을 유지하므로 이 파일이 없어도 동작하도록 설계되어 있습니다.

### 12.2 `_format.js`

전역 namespace:

```javascript
window.CommissionCommon.format
```

제공:

| 함수 | 역할 |
|---|---|
| `toText()` | null-safe string |
| `stripCommas()` | comma 제거 |
| `comma()` | 정수 천단위 포맷 |
| `percent()` | 소수점 2자리 `%` |
| `escapeHtml()` | HTML escape |
| `safeSetText` | dom.safeSetText convenience |

주의:

- innerHTML 사용 전 반드시 `escapeHtml()`을 사용해야 합니다.
- 단순 텍스트 삽입은 `textContent`를 우선합니다.

### 12.3 `_net_json.js`

전역 namespace:

```javascript
window.CommissionCommon.net
```

제공:

| 함수 | 역할 |
|---|---|
| `fetchJSON()` | JSON fetch + content-type guard |
| `firstObject()` | 다양한 응답 구조에서 첫 object 추출 |
| `arrayRows()` | 다양한 응답 구조에서 rows array 추출 |

`fetchJSON()` 특징:

- `credentials: "same-origin"`
- `X-Requested-With: XMLHttpRequest`
- `content-type`이 `application/json`이 아니면 body 일부 포함하여 throw
- `data.ok === false`면 throw

주의:

- GET에는 적합합니다.
- POST에는 CSRF header가 별도로 필요합니다.
- 오류 메시지에 body 일부가 포함되므로 운영 콘솔/로그 노출 범위를 고려해야 합니다.

### 12.4 `_modals.js`

전역 namespace:

```javascript
window.CommissionCommon.modals
```

제공:

| 객체 | 역할 |
|---|---|
| `TextViewer` | `.ellipsis-cell` 전체보기 |
| `SupportModal` | 지원신청서 텍스트 모달 |

TextViewer:

- `ensureModal()`
- `open(title, text)`
- `bindEllipsisClickOnce(flagKey)`

SupportModal:

- `open({ textValue, buildTextFn, target, summary, suretyItems, otherItems })`
- Bootstrap 없으면 alert fallback
- 복사 버튼 Clipboard API + textarea fallback

주의:

- 동적으로 innerHTML로 모달을 생성하지만, 실제 사용자 데이터는 `textContent`로 주입합니다.
- inline style이 모달 HTML 안에 남아 있습니다. CSP 강화 시 CSS class로 분리 후보입니다.

---

## 13. Page JavaScript 기준

### 13.1 `deposit_home.js`

역할:

- 채권관리 페이지 대상자 선택/조회/렌더링.
- `userSelected` 이벤트 수신.
- URL query `?user=` pushState/popstate.
- API 4개 병렬 호출.
- data-bind 렌더.
- 보증보험/기타채권 테이블 렌더.
- ellipsis modal.
- 지원신청서 텍스트 생성/모달 표시.

초기화:

```javascript
const root = document.getElementById("deposit-home");
if (!root) return;
```

URL dataset:

- `data-user-detail-url`
- `data-deposit-summary-url`
- `data-deposit-surety-url`
- `data-deposit-other-url`

공용 util fallback:

- `CommissionCommon.dom`
- `CommissionCommon.format`
- `CommissionCommon.net`
- `CommissionCommon.modals`

중요 alias:

```javascript
"target.emp_id" → "target.id"
"target.join_date" → "target.join_date_display"
"target.leave_date" → "target.retire_date_display"
"summary.final_pay" → "summary.final_payment"
"summary.long_term" → "summary.sales_total"
"summary.loss_asset" → "summary.maint_total"
"summary.deposit_total" → "summary.debt_total"
"summary.etc_total" → "summary.other_total"
"summary.need_deposit" → "summary.required_debt"
"summary.final_extra_pay" → "summary.final_excess_amount"
"summary.month1" → "summary.div_1m"
"summary.month2" → "summary.div_2m"
"summary.month3" → "summary.div_3m"
```

주의:

- alias는 legacy 템플릿 호환용이므로 제거하지 않습니다.
- `summary.payment` 참조가 있을 수 있으므로 실제 API payload와 정합성 점검이 필요합니다.
- userSelected 이벤트는 window/document 양쪽에서 수신합니다.
- common/search_user_modal.js의 deposit-home 분기 동작과 충돌 여부를 점검해야 합니다.

성능 후보:

- 동일 user 반복 조회 캐싱.
- surety/other rows 대량 시 부분 렌더 또는 DocumentFragment 검토.
- support text builder에서 이미 로드된 데이터를 재사용하므로 OK.

보안 후보:

- innerHTML 렌더 시 escapeHtml 유지 필수.
- 민감 필드 노출 권한은 서버에서 최종 검증.

### 13.2 `approval_excel_upload.js`

역할:

- 수수료결재/지점효율 업로드 form 처리.
- FormData 강제 set.
- 확장자/ym/kind/file 1차 검증.
- dataset.submitting 중복 제출 방지.
- fail_download_url 링크 표시.
- 성공 시 toast, modal close, reload.

중요 DOM:

- `approvalUploadForm`
- `approvalUploadResult`
- `approvalExcelUploadModal`
- `approvalFailDownloadWrap`
- `approvalFailDownloadLink`

보안 후보:

- 클라이언트 확장자 검증은 보조일 뿐, 서버 검증 필수.
- fail_download_url same-origin 검증은 필요합니다.
- catch에서 상세 오류를 숨기고 있으므로 사용자 안내와 서버 로그 분리 필요.

성능 후보:

- 대용량 업로드 진행률은 현재 실시간 progress가 없습니다.
- 긴 업로드에는 Celery 전환 또는 progress UI 검토 가능.

### 13.3 `approval_home_export.js`

역할:

- HTML table을 clone하여 `.xls` 파일로 다운로드.
- input/select/textarea 값을 텍스트로 치환.
- `button`, `a.btn` 제거.
- filename은 root dataset의 selected ym/part + timestamp.

중요 selector:

```text
[data-export-table]
[data-export-name]
#approval-home
```

주의:

- HTML 기반 `.xls`는 Excel 호환 방식입니다.
- 대용량 테이블은 DOM clone 비용이 큽니다.
- 데이터 신뢰성 높은 export는 서버 XLSX 다운로드와 역할을 분리해야 합니다.
- HTML title에 escape 처리가 없으므로 baseName이 사용자 입력이 될 가능성은 낮지만 점검 대상입니다.

### 13.4 `collect_home.js`

역할:

- 환수관리 페이지 전체 인터랙션.
- type="module".
- boot root dataset 기반 URL 사용.
- 탭/필터/정렬/검색/branch filter.
- 피드백 CRUD.
- 드롭다운 피드백 저장.
- 대상자 검색 모달 연동.
- 안내문자 생성/복사.
- SheetJS 엑셀 다운로드.

초기화 guard:

```javascript
const root = document.getElementById("collect-home");
if (!root) throw new Error(...);

if (root.dataset.inited === "1") throw new Error(...);
root.dataset.inited = "1";
```

주의:

- 중복 초기화 방어는 좋지만 `throw`는 페이지 전체 JS 오류로 이어질 수 있습니다. 향후 기능 변화 0 개선 시 `return` 방식 검토 가능.
- 모든 URL은 dataset에서만 읽습니다.
- `apiFetch()`는 GET JSON parsing fallback이 약합니다. `_net_json.js`와 통합 후보입니다.
- `apiPost()`는 CSRF header 포함.

상태:

```javascript
state = {
  tab,
  ym,
  part,
  bizmoon,
  branch,
  keyword,
  selectedEmpId,
  selectedEmpName,
  sortKey,
  sortDir
}
```

캐시:

```javascript
_allTabData = {
  all: [],
  new: [],
  long3: [],
  long6: [],
  long12: []
}
```

중요 UI 데이터:

- COMMON_COLS
- EXTRA_COLS
- TAB_COLS
- BRANCH_FEEDBACK_OPTIONS
- HQ_FEEDBACK_OPTIONS
- DROPDOWN_VALUE_CLASS
- SMS_ACCOUNT

보안 주의:

- 대부분 HTML 렌더에 `esc()` 사용.
- `buildSmsTemplate()`는 textContent에 주입되어 비교적 안전.
- 피드백 content는 esc 처리 필수.
- dropdown value는 서버에서도 허용값 검증 필요.
- 피드백 대상 emp_id가 현재 사용자 권한 scope 내인지 서버에서 확인해야 합니다.

성능 후보:

- `_allTabData` 전체 rows를 탭별로 메모리에 보관합니다.
- 필터/정렬마다 전체 배열을 재계산합니다.
- `innerHTML`로 테이블 전체 재렌더링합니다.
- 데이터량 증가 시 pagination/virtual rendering/server-side filtering 검토가 필요합니다.
- 탭 전환 시 서버 재요청합니다. 필요 시 캐시 재사용 정책 검토 가능.

### 13.5 `excel_upload.js`

공용 엑셀 업로드 JS입니다.

Commission에서 쓰는 DOM:

- `excelUploadForm`
- `excelFile`
- `excelUploadModal`
- `excelUploadResultModal`
- `excelUploadResultBody`
- `excelUploadReloadBtn`
- `uploadToast`

주의:

- commission deposit/collect 모두 이 공용 JS에 의존합니다.
- fail_download_url 표시 시 same-origin 검증이 필요합니다.
- HTML 삽입값 escape 정책을 유지합니다.

---

## 14. CSS 기준

### 14.1 `static/css/apps/commission.css`

역할:

- deposit_home, approval_home, collect_home의 앱 전용 스타일.
- 전역 base.css와 분리.
- 테이블 스크롤/ellipsis/컬럼폭/collect wide layout 관리.

주요 섹션:

1. Shared tokens/layout
2. Deposit Home
3. Approval Home
4. Collect Home

### 14.2 Shared

| class | 역할 |
|---|---|
| `.deposit-maxw` | 채권/결재 카드 최대폭 1100px |
| `.collect-wide` | 환수관리 wide layout |
| `.deposit-title` | title color |
| `.deposit-section-title` | section title |
| `.ellipsis-cell` | 클릭 가능한 말줄임 span |

주의:

- `.collect-wide`는 `86vw`와 negative margin을 사용합니다.
- 모바일에서는 width 100%로 복귀합니다.

### 14.3 Deposit table

중요 selector:

- `.info-table`
- `#suretyTable`
- `#otherTable`
- `#suretyColGroup`
- `#otherColGroup`

정책:

- 데스크톱: fixed layout + colgroup width.
- 모바일: min-width + table-layout auto + horizontal scroll.
- 긴 값은 ellipsis.

주의:

- colgroup 비율은 JS 렌더와 결합되어 있습니다.
- id selector 기반이므로 다른 앱으로 누수될 가능성은 낮습니다.

### 14.4 Approval table

중요 selector:

- `.commission-table-scroll`
- `.commission-nowrap-table`
- `.money-cell`

정책:

- table width max-content.
- nowrap.
- overflow visible.
- horizontal scroll.

### 14.5 Collect table

중요 selector:

- `.collect-filter-bar`
- `#collectTableHead th:nth-child(...)`
- `#collectTableBody td:nth-child(...)`
- `.collect-td-feedback`
- `.collect-td-dropdown`
- `.collect-dropdown-select`
- `.amount-negative`
- `.collect-emp-id-cell`
- `.collect-feedback-cell`
- `.collect-feedback-item`
- `.collect-notice`

주의:

- CSS nth-child가 collect_home.js의 TAB_COLS 순서와 강하게 결합되어 있습니다.
- 컬럼 추가/삭제/순서 변경 시 CSS 동시 수정이 필요합니다.
- 탭별 컬럼 수 차이를 class 기반으로 일부 해결하고 있습니다.
- 드롭다운 피드백 컬럼 추가 이후 전체 탭 총 컬럼 수가 바뀌었으므로 기존 주석과 실제 컬럼 수 불일치 여부를 점검해야 합니다.

---

## 15. 권한 정책 기준

### 15.1 전체 권한 원칙

| 영역 | 기본 권한 |
|---|---|
| 채권관리 페이지 | 서버 정책 재검토 필요. 민감정보이므로 최소 로그인 + scope 필요 |
| 채권 대상자 API | superuser/main_admin/head 또는 본인 |
| 채권 업로드 | superuser |
| 수수료결재 페이지 | 서버 정책 재검토 필요 |
| approval/efficiency 업로드 | superuser |
| approval/efficiency 다운로드 | 권한 데코레이터 보강 필요 |
| 환수관리 페이지/API | superuser/head/leader |
| 환수 피드백 | superuser/head/leader + scope |
| 환수 dropdown feedback | branch: head/leader, hq: superuser로 프론트 제한. 서버에서도 동일 검증 필요 |

### 15.2 스코프 기준

사용자 등급별 기본 스코프:

| grade | 조회 범위 |
|---|---|
| superuser | 전체 |
| head | 본인 branch |
| leader | 팀 기준, 팀 미설정 시 branch fallback |
| basic | 본인 |
| inactive | 차단 |

주의:

- `main_admin`, `sub_admin`은 legacy로 남아 있을 수 있습니다.
- 신규 정책에서는 `head`, `leader` 중심으로 정리하되 기존 호환을 깨지 않습니다.
- 권한 alias는 `accounts.decorators.grade_required` 정책을 확인합니다.

### 15.3 서버 확인 필수 지점

- `deposit_home`
- `approval_home`
- `collect_home`
- `api_user_detail`
- `api_deposit_summary`
- `api_deposit_surety_list`
- `api_deposit_other_list`
- `upload_excel`
- `approval_upload_excel`
- `download_upload_fail_excel`
- `download_approval_pending_excel`
- `download_efficiency_excess_excel`
- `api_collect_*`

---

## 16. 보안 점검 기준

아래 항목은 실제 취약점 보완 전 반드시 체크합니다.

### 16.1 인증/권한

- [ ] 모든 민감 view/API에 `login_required` 또는 `grade_required`가 있는가?
- [ ] `download_approval_pending_excel`에 권한 데코레이터가 있는가?
- [ ] `download_efficiency_excess_excel`에 권한 데코레이터가 있는가?
- [ ] `download_upload_fail_excel`이 token만으로 파일을 내려주지 않는가?
- [ ] fail token이 요청자와 바인딩되어 있는가?
- [ ] Deposit API가 대상자 scope를 서버에서 최종 검증하는가?
- [ ] Collect 피드백 조회/생성/수정/삭제가 emp_id scope를 검증하는가?
- [ ] dropdown feedback save가 권한별 feedback_type을 서버에서 검증하는가?
- [ ] head/leader가 part/bizmoon query로 scope를 우회할 수 없는가?

### 16.2 CSRF

- [ ] `upload_excel`의 `@csrf_exempt` 제거 또는 합당한 이유가 있는가?
- [ ] `approval_upload_excel`의 `@csrf_exempt` 제거 또는 합당한 이유가 있는가?
- [ ] 모든 POST fetch에 `X-CSRFToken`이 포함되는가?
- [ ] JSON POST API에서 CSRF middleware가 정상 동작하는가?
- [ ] form 기반 업로드는 `{% csrf_token %}`을 포함하는가?

### 16.3 업로드 파일 검증

- [ ] 서버단 파일 크기 제한이 있는가?
- [ ] 서버단 확장자 allowlist가 있는가?
- [ ] MIME/content sniffing이 있는가?
- [ ] `.xlsx`, `.xls`, HTML table, CSV/TSV 허용 정책이 명확한가?
- [ ] 허용하지 않는 파일을 pandas/openpyxl에 넘기기 전에 차단하는가?
- [ ] 임시파일 저장 경로가 공개 media 아래 노출되지 않는가?
- [ ] 임시파일 삭제 실패가 로그로 남는가?
- [ ] 업로드 중 예외 발생 시 temp cleanup이 보장되는가?
- [ ] 대용량/zip bomb성 Excel 방어가 있는가?

### 16.4 다운로드

- [ ] 모든 다운로드는 view를 경유하는가?
- [ ] 파일명은 RFC5987 방식으로 세팅되는가?
- [ ] 다운로드 권한 검증이 view에서 수행되는가?
- [ ] fail download token이 TTL을 가지는가?
- [ ] fail download token이 owner/scope와 바인딩되는가?
- [ ] download audit log가 남는가?
- [ ] 다운로드 응답에 내부 경로가 노출되지 않는가?

### 16.5 XSS / HTML Injection

- [ ] JS innerHTML 삽입 전 모든 사용자/DB 값이 escape되는가?
- [ ] `collect_home.js`의 row render가 `esc()`를 유지하는가?
- [ ] `deposit_home.js`의 table render가 `escapeHtml()`을 유지하는가?
- [ ] 피드백 content는 HTML이 아니라 text로 처리되는가?
- [ ] `approval_home_export.js`에서 title/baseName이 사용자 입력으로 오지 않는가?
- [ ] upload result modal에서 서버 message를 HTML로 직접 삽입하지 않는가?
- [ ] 템플릿의 inline script/style이 CSP 정책과 충돌하지 않는가?

### 16.6 민감정보 노출

- [ ] 채권합계/보증합계/환수예상/지급액은 권한 없는 사용자에게 노출되지 않는가?
- [ ] 증권번호/채권번호/비고/피드백 내용 노출 범위가 적절한가?
- [ ] Excel export에 현재 사용자의 scope 밖 데이터가 포함되지 않는가?
- [ ] fail rows에 불필요한 개인정보가 포함되지 않는가?
- [ ] 로그에 파일명, 사번, token, 오류 body가 과도하게 남지 않는가?

### 16.7 Audit

중요 행위는 audit log 대상입니다.

- [ ] 채권 업로드 성공/실패
- [ ] approval/efficiency 업로드 성공/실패
- [ ] 환수관리 업로드 성공/실패
- [ ] fail excel 다운로드
- [ ] approval/efficiency excel 다운로드
- [ ] 피드백 생성/수정/삭제
- [ ] dropdown feedback 저장
- [ ] 지원신청서 텍스트 생성/복사 여부는 필요 시 검토

---

## 17. 성능 개선 기준

### 17.1 DB/Query

- [ ] `select_related("user")` 필요한 곳 유지.
- [ ] export queryset에서 필요한 필드만 가져오는가?
- [ ] approval/efficiency 최신 ym 조회에 적절한 index가 있는가?
- [ ] CollectRecord 조회에 `ym`, `part`, `bizmoon`, `branch`, `emp_id` 조건 index가 적절한가?
- [ ] Collect feedback 최신값 annotate가 N+1을 제거하는가?
- [ ] `_build_deposit_map()`이 bulk IN query로 동작하는가?
- [ ] leader scope 계산이 매 요청마다 과도한 쿼리를 만들지 않는가?

### 17.2 Upload

- [ ] deposit handlers의 row-by-row `update_or_create`를 bulk upsert로 전환할 수 있는가?
- [ ] 삭제 후 bulk_create 구조가 필요한 범위만 삭제하는가?
- [ ] raw matrix를 중복 읽는 부분을 줄일 수 있는가?
- [ ] DataFrame copy가 불필요하게 큰 범위를 복사하지 않는가?
- [ ] missing_sample만 저장하고 전체 fail rows를 저장하지 않아도 되는가?
- [ ] cache payload 크기를 제한하는가?

### 17.3 Download/Export

- [ ] pandas DataFrame → BytesIO 방식이 데이터량 대비 적절한가?
- [ ] 대량 export는 openpyxl write_only 또는 streaming이 필요한가?
- [ ] 클라이언트 HTML `.xls` export가 대량 테이블에서 브라우저를 멈추지 않는가?
- [ ] SheetJS export에서 전체 탭 데이터를 메모리에 보관해도 되는가?

### 17.4 Frontend 렌더링

- [ ] collect_home.js가 큰 rows를 `innerHTML` 전체 재렌더하지 않는 대안이 필요한가?
- [ ] 정렬/필터가 매번 전체 배열을 순회해도 되는 규모인가?
- [ ] branch filter/keyword filter는 서버 처리로 옮겨야 하는가?
- [ ] deposit surety/other rows가 많을 때 pagination이 필요한가?
- [ ] 중복 event binding이 없는가?
- [ ] BFCache 복원 시 재초기화/중복 fetch가 없는가?

### 17.5 Static/CSP

- [ ] inline script를 외부 JS로 분리할 수 있는가?
- [ ] inline style을 CSS class로 이동할 수 있는가?
- [ ] `vendor/xlsx`는 필요한 페이지에서만 로드되는가?
- [ ] `CommissionCommon` 유틸이 모든 페이지에서 중복 없이 순서대로 로드되는가?

---

## 18. 패치 유형별 응답 기준

### 18.1 버그 원인 분석 요청

사용자가 “원인 분석”을 요청하면 다음 형식으로 답합니다.

1. 현상 요약
2. 원인 후보 Top N
3. 각 원인을 뒷받침하는 코드/규약 근거
4. 원인 확정에 필요한 관측 포인트
   - Network tab
   - response payload
   - console error
   - server log
   - 권한 계정
   - URL/query params
5. 사용자가 “해결책 금지”라고 하면 코드/패치 제안 금지

### 18.2 코드 수정/패치 요청

반드시 diff 패치 형식으로 답합니다.

포함 요소:

1. 변경 목적
2. 수정 파일 목록 + 영향도
3. 회귀 위험
4. diff
5. 로컬 검증 체크리스트
6. 운영 배포 주의사항

### 18.3 리팩토링 요청

기능 변화 0을 명시합니다.

반드시 설명할 것:

- 변경 전/후 동일 보장 포인트
- 삭제/통합 대상의 대체 근거
- URL/DOM/data-* 영향 없음 여부
- 권한 스코프 변경 없음 여부
- 업로드 registry 영향 없음 여부
- CSS scope 영향 없음 여부

### 18.4 기능 확장 설계 요청

다음 항목을 포함합니다.

1. 데이터 모델 영향
2. URL/API 계약
3. JSON schema
4. 프론트 dataset/DOM 계약
5. 권한 정책
6. audit log
7. migration/backfill
8. rollback
9. MVP 단계
10. 확장 단계

---

## 19. 회귀 위험 Top 체크리스트

패치 전 항상 점검합니다.

### 19.1 URL/Import

- [ ] 기존 URL name 변경 없음
- [ ] `commission.views.__getattr__` lazy export 영향 없음
- [ ] shim import 경로 유지
- [ ] `app_name="commission"` 유지
- [ ] reverse 후보 fallback 영향 없음

### 19.2 권한

- [ ] superuser 업로드 유지
- [ ] head/leader scope 우회 없음
- [ ] basic 본인 조회 정책 유지
- [ ] inactive 차단 유지
- [ ] 다운로드 권한 보강 시 기존 superuser workflow 깨짐 없음

### 19.3 Upload

- [ ] registry upload_type 문자열 변경 없음
- [ ] `SUPPORTED_UPLOAD_TYPES` 자동 생성 유지
- [ ] upload handler 반환 dict key 호환 유지
- [ ] missing_users/missing_sample 유지
- [ ] fail_download_url 프론트 호환 유지
- [ ] upload log count 유지

### 19.4 Deposit Home

- [ ] `#deposit-home` 유지
- [ ] dataset URL 유지
- [ ] data-bind 유지
- [ ] alias 제거 없음
- [ ] `suretyTableBody`, `otherTableBody` 유지
- [ ] search_user_modal 연동 유지
- [ ] support modal 텍스트 생성 유지

### 19.5 Approval Home

- [ ] `#approval-home` 유지
- [ ] `#efficiencyExcessTable`, `#approvalPendingTable` 유지
- [ ] `data-export-table`, `data-export-name` 유지
- [ ] `_approval_upload_modal.html` form id/name/action 유지
- [ ] fail download 영역 유지

### 19.6 Collect Home

- [ ] `#collect-home` 유지
- [ ] dataset URL 유지
- [ ] `collectTableHead`, `collectTableBody` 유지
- [ ] 탭 `data-tab` 값 유지
- [ ] feedback modal id 유지
- [ ] sms modal id 유지
- [ ] excel upload modal id 유지
- [ ] SheetJS 로드 순서 유지
- [ ] CSS nth-child와 JS 컬럼 순서 정합성 유지

### 19.7 CSS

- [ ] commission.css scope 외 전역 영향 없음
- [ ] collect nth-child 컬럼폭 깨짐 없음
- [ ] mobile scroll 유지
- [ ] ellipsis modal UX 유지
- [ ] DataTables 관련 전역 CSS와 충돌 없음

---

## 20. 로컬 검증 체크리스트

패치 후 최소 검증은 다음을 수행합니다.

### 20.1 Django

```bash
python manage.py check
python manage.py test commission
```

테스트가 없으면 최소 수동 검증으로 대체합니다.

### 20.2 Deposit Home

- [ ] `/commission/deposit/` 진입
- [ ] 대상자 검색
- [ ] `?user=사번` URL 반영
- [ ] 인적사항 렌더
- [ ] 주요지표 렌더
- [ ] 보증보험 table 렌더
- [ ] 기타채권 table 렌더
- [ ] 긴 증권번호/비고 클릭 시 TextViewer 열림
- [ ] 지원신청서 버튼 활성화
- [ ] 지원신청서 텍스트 모달 열림
- [ ] 초기화 버튼 정상
- [ ] 권한 없는 대상자 API 403 확인

### 20.3 Deposit Upload

- [ ] part 미선택 시 오류
- [ ] upload_type 미선택 시 오류
- [ ] 파일 미선택 시 오류
- [ ] 허용 파일 업로드 성공
- [ ] 미존재 사용자 missing_sample 표시
- [ ] fail_download_url 동작
- [ ] 업로드 로그 갱신
- [ ] temp 파일 삭제
- [ ] 서버 로그에 예외 기록

### 20.4 Approval Home

- [ ] `/commission/approval/` 진입
- [ ] year/month/part 조회
- [ ] 지점효율 초과 table 표시
- [ ] 수수료 미결 table 표시
- [ ] 클라이언트 엑셀 다운로드
- [ ] approval upload modal 열림
- [ ] ym/kind/file 검증
- [ ] 업로드 성공 후 reload
- [ ] fail download 표시

### 20.5 Approval/Efficiency Download

- [ ] ym 있는 다운로드
- [ ] ym 없는 최신 다운로드
- [ ] 데이터 없을 때 404 JSON
- [ ] 권한 없는 사용자 차단
- [ ] 파일명 한글/영문 정상
- [ ] 대량 다운로드 시간 확인

### 20.6 Collect Home

- [ ] `/commission/collect/` 진입
- [ ] 월도 목록 표시
- [ ] 전체 탭 조회
- [ ] 신규/장기3/장기6/장기12 탭 조회
- [ ] 부문/부서 필터
- [ ] 영업가족 드롭다운 필터
- [ ] 키워드 검색
- [ ] 정렬 토글
- [ ] 엑셀 다운로드
- [ ] 피드백 관리 모달 열림
- [ ] 대상자 검색 후 피드백 조회
- [ ] 피드백 생성/수정/삭제
- [ ] 드롭다운 피드백 저장
- [ ] 안내문자 모달/복사
- [ ] head/leader scope 확인
- [ ] superuser hq feedback 저장 확인

### 20.7 Security

- [ ] CSRF 누락 POST 차단
- [ ] 권한 없는 다운로드 차단
- [ ] 타 지점/타 팀 emp_id 접근 차단
- [ ] fail token owner mismatch 차단
- [ ] 업로드 허용 외 파일 차단
- [ ] innerHTML XSS payload 무해화 확인

---

## 21. 운영 배포 체크리스트

- [ ] migration 필요 여부 확인
- [ ] static collect 필요 여부 확인
- [ ] Whitenoise Manifest static path 정상
- [ ] CSP report 확인
- [ ] Nginx `/media/` 직접 접근 금지 유지
- [ ] Redis cache TTL 정책 확인
- [ ] Celery worker 필요 여부 확인
- [ ] upload temp/result cleanup 정책 확인
- [ ] audit log 테이블 용량 확인
- [ ] 에러 로그 traceback 확인
- [ ] rollback 절차 준비

---

## 22. 향후 우선순위 로드맵

### 22.1 즉시 조치급 후보

1. `download_upload_fail_excel` token owner/scope binding
2. approval/efficiency 다운로드 권한 데코레이터 추가
3. `upload_excel`, `approval_upload_excel`의 `csrf_exempt` 제거 검토
4. 서버단 업로드 파일 크기/확장자/MIME 검증
5. Collect feedback/dropdown 저장의 서버 scope 검증 강화

### 22.2 빠른 보완 권장

1. fail token audit log
2. upload temp deletion failure logging
3. inline script/style 제거로 CSP 강화 준비
4. collect_home.js fetch JSON 처리 공통화
5. client fail_download_url same-origin 검증
6. approval_home_export title/baseName escape 보강

### 22.3 성능 개선 후보

1. deposit handlers row-by-row upsert bulk화
2. approval/efficiency raw matrix 중복 read 최적화
3. 대량 export streaming/write_only 검토
4. collect table server-side pagination/filtering 검토
5. collect_home.js innerHTML 전체 재렌더 최적화
6. Deposit API 동일 user 캐싱 또는 조건부 재조회

### 22.4 구조 개선 후보

1. Commission permission policy 모듈 신설
2. Commission upload validation util 신설
3. Download service 공통화
4. Collect API response schema 문서화
5. CommissionCommon과 common/manage/http.js 역할 정리
6. inline Bootstrap validation script 외부화

---

## 23. 절대 금지 패턴

- [ ] URL name 변경
- [ ] upload_type 문자열 변경
- [ ] `CustomUser.pk == 사번 문자열` 규약 변경
- [ ] `file.url` 직접 노출
- [ ] token만으로 다운로드 허용
- [ ] 권한 완화로 임시 해결
- [ ] registry 우회 업로드 구현
- [ ] 공용 유틸 중복 생성
- [ ] DOM id/data-* 변경 후 광역 수정
- [ ] 템플릿에서 권한 숨김만 하고 서버 검증 생략
- [ ] 운영 설정/Whitenoise/CSP/SSL 임의 완화
- [ ] 사용자 입력을 escape 없이 innerHTML 삽입
- [ ] 업로드 파일을 검증 없이 parser에 전달

---

## 24. 새 채팅에서 이 문서를 사용할 때의 기준 문장

새로운 채팅에서 Commission 앱 이슈를 다룰 때는 다음 기준으로 접근합니다.

```text
이 이슈는 django_ma commission 앱 기준 지침서에 따라 분석한다.
기존 URL name, 템플릿 DOM id/data-* 계약, CommissionCommon 공통 유틸,
upload_handlers.registry SSOT, upload_utils SSOT, CustomUser 사번 PK 규약을 유지한다.
보안/권한/스코프를 우선 확인하고, 기능 변화 0을 기본값으로 한다.
패치가 필요하면 diff 형식으로만 제시한다.
```

---

## 25. 빠른 이슈 대응 맵

| 증상 | 우선 확인 파일 |
|---|---|
| 채권관리 대상자 검색 후 데이터 안 나옴 | `deposit_home.js`, `api_deposit_impl.py`, `search_user_modal.js` |
| 지원신청서 버튼 비활성 | `deposit_home.js`, `target.id` bind, query `?user=` |
| 보증보험/기타채권 표 안 나옴 | API response rows 구조, `Net.arrayRows()`, `suretyTableBody`, `otherTableBody` |
| approval 업로드 실패 | `_approval_upload_modal.html`, `approval_excel_upload.js`, `views/approval.py`, `_ym.py` |
| fail download 안 됨 | `utils_fail_excel.py`, `downloads.py`, fail_download_url |
| 환수관리 조회 안 됨 | `collect_home.js`, `api_collect_list`, `services/collect.py` |
| 환수관리 지점 필터 이상 | `_allTabData`, `refreshBranchSelect`, `applyBranchFilter` |
| 피드백 저장 안 됨 | `api_collect_feedback_create/update/delete`, `services.collect`, CSRF |
| dropdown feedback 저장 안 됨 | `api_collect_dropdown_feedback_save`, `buildDropdownCell`, 권한 grade |
| 엑셀 다운로드 깨짐 | `approval_home_export.js`, `collect_home.js` SheetJS, server downloads |
| 모바일 표 깨짐 | `commission.css`, `.commission-table-scroll`, table min-width |
| CSP 경고 | inline script/style, `_approval_upload_modal.html`, `_modals.js`, templates |

---

## 26. 결론

Commission 앱은 단순 조회 앱이 아니라 다음 요소가 결합된 민감 운영 앱입니다.

- 대량 엑셀 업로드
- 채권/수수료/환수 민감정보
- 대상자 기반 권한 스코프
- fail token 다운로드
- 프론트 data-bind/DOM 계약
- 환수 피드백 이력
- 클라이언트/서버 Excel export

따라서 향후 모든 작업은 다음 순서로 진행합니다.

1. 권한/스코프 확인
2. URL/DOM/API 계약 확인
3. SSOT 재사용 확인
4. 기능 변화 0 보장
5. 보안 개선
6. 성능 개선
7. 회귀 테스트
8. 운영 배포 주의사항 정리
