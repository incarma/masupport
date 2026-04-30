# django_ma Commission App 보안 취약점·성능 개선 체크리스트

> 기준일: 2026-04-30  
> 대상 앱: `commission`  
> 목적: Commission 앱의 실제 보안 보완 및 성능 개선 패치를 단계적으로 진행하기 위한 우선순위 지침서입니다.  
> 범위: 백엔드 view/service/upload/download, upload_handlers/upload_utils, 템플릿 DOM 계약, Commission 프론트 JS, CSS, 운영 로그/audit까지 포함합니다.  
> 주의: 본 문서는 **패치 코드가 아닌 점검·우선순위 문서**입니다. 실제 수정은 별도 요청 시 diff 패치로 진행합니다.

---

## 0. 우선순위 등급 정의

| 등급 | 의미 | 패치 판단 기준 |
|---|---|---|
| 최상 | 즉시 조치 필요 | 권한 우회, 민감정보 다운로드, CSRF 우회, 파일 접근 등 실제 사고 가능성이 높은 항목 |
| 상 | 빠른 보완 필요 | 악용 가능성이 있거나 운영 민감정보 노출/대량 장애로 이어질 수 있는 항목 |
| 중상 | 단기 개선 권장 | 현재 구조상 취약점 또는 병목으로 커질 가능성이 높고, 패치 난이도 대비 효과가 큰 항목 |
| 중 | 계획 개선 | 현재 즉시 사고 가능성은 낮지만 안정성·성능·유지보수 측면에서 개선 가치가 있는 항목 |
| 중하 | 여유 시 개선 | 운영 영향은 제한적이나 코드 품질·가독성·장기 유지보수에 도움이 되는 항목 |
| 하 | 장기 검토 | 현재 리스크가 낮고, 대규모 구조 개편이나 정책 변경과 함께 검토할 항목 |

---

# Part A. 보안 취약점 체크리스트

---

## A-1. 최상 등급

### 1) fail token 다운로드 권한 미흡

- [ ] `download_upload_fail_excel`이 token만으로 파일을 내려주지 않는지 확인
- [ ] fail token payload에 `owner_id`를 저장하는지 확인
- [ ] 다운로드 시 `request.user.id == owner_id` 검증
- [ ] superuser 예외 허용 여부 정책화
- [ ] token TTL 유지
- [ ] token 재사용/공유/로그 노출 리스크 방어
- [ ] fail download audit log 추가

#### 관련 파일
```text
commission/views/downloads.py
commission/views/utils_fail_excel.py
commission/views/api_upload.py
commission/views/approval.py
```

#### 위험 설명
현재 fail token이 cache key로만 동작하면 token URL을 아는 사용자가 실패 목록 파일을 받을 수 있습니다. 실패 목록에는 사번, 사용자 미존재, 스코프 제외 등 민감한 내부 정보가 포함될 수 있습니다.

#### 패치 방향
1. `store_fail_rows_as_excel()`에 `owner_id`, `purpose`, `scope`, `upload_type`, `created_at` 저장
2. 다운로드 view에서 로그인/권한 검증
3. owner 불일치 시 403
4. audit log 기록

---

### 2) approval/efficiency Excel 다운로드 권한 검증 부족

- [ ] `download_approval_pending_excel`에 인증/권한 데코레이터 추가
- [ ] `download_efficiency_excess_excel`에 인증/권한 데코레이터 추가
- [ ] superuser/head/leader 다운로드 정책 결정
- [ ] head/leader 허용 시 branch/team scope 적용
- [ ] selected part를 통한 scope 우회 차단
- [ ] 다운로드 audit log 추가

#### 관련 파일
```text
commission/views/downloads.py
commission/models.py
accounts/decorators.py
audit/services.py
audit/constants.py
```

#### 위험 설명
수수료 미결, 지급 초과 데이터는 금액·사번·소속이 포함된 민감 데이터입니다. 다운로드 view에 권한 검증이 부족하면 URL 직접 접근으로 전체 데이터가 유출될 수 있습니다.

#### 패치 방향
1. `@login_required`, `@grade_required(...)` 적용
2. queryset에 사용자 권한 scope 적용
3. 다운로드 결과가 현재 사용자 권한 범위로 제한되는지 테스트
4. 감사 로그 기록

---

### 3) 업로드 API의 `csrf_exempt` 사용

- [ ] `upload_excel`의 `@csrf_exempt` 제거 가능 여부 확인
- [ ] `approval_upload_excel`의 `@csrf_exempt` 제거 가능 여부 확인
- [ ] 모든 업로드 form에 `{% csrf_token %}` 존재 확인
- [ ] JS fetch에 `X-CSRFToken` 포함 확인
- [ ] CSRF 누락 요청이 403으로 차단되는지 확인
- [ ] 운영 CSRF 쿠키 도메인/legacy cleanup 정책과 충돌 없는지 확인

#### 관련 파일
```text
commission/views/api_upload.py
commission/views/approval.py
commission/templates/commission/deposit_home.html
commission/templates/commission/collect_home.html
commission/templates/commission/_approval_upload_modal.html
static/js/excel_upload.js
static/js/commission/approval_excel_upload.js
web_ma/middleware.py
web_ma/settings.py
```

#### 위험 설명
대량 업로드 API가 CSRF 보호 없이 열려 있으면 인증된 사용자의 세션을 악용한 업로드 요청이 가능해질 수 있습니다. 수수료/채권 데이터 변경 API이므로 위험도가 높습니다.

#### 패치 방향
1. `csrf_exempt` 제거
2. form/JS CSRF 정상 전송 확인
3. 실패 시 사용자 메시지와 서버 로그 구분
4. 로컬/운영 유사 환경에서 CSRF 테스트

---

### 4) 서버단 업로드 파일 검증 부족

- [ ] 파일 크기 제한
- [ ] 확장자 allowlist
- [ ] MIME/content sniffing
- [ ] 실제 파일 header 검사
- [ ] HTML table Excel 허용 정책 확정
- [ ] CSV/TSV 허용 정책 확정
- [ ] zip bomb/대용량 Excel 방어
- [ ] 임시파일 저장 전 검증 가능한 항목 선검증
- [ ] parser 예외 메시지 내부정보 노출 방지

#### 관련 파일
```text
commission/views/api_upload.py
commission/views/approval.py
commission/views/_files.py
commission/upload_utils/_readers.py
web_ma/settings.py
```

#### 위험 설명
검증 없는 파일을 pandas/openpyxl/HTML parser에 전달하면 서버 리소스 고갈, parser 취약점 노출, 비정상 파일로 인한 장애 가능성이 있습니다.

#### 패치 방향
1. `commission/views/_upload_validation.py` 또는 유사 util 신설
2. 크기/확장자/MIME/시그니처 검사
3. views에서 temp save 전 또는 직후 검증
4. 실패 메시지 표준화
5. audit log에 실패 사유 기록

---

## A-2. 상 등급

### 5) Collect 피드백/드롭다운 저장의 서버 scope 검증 강화

- [ ] 피드백 조회 대상 emp_id가 현재 사용자 scope 안인지 검증
- [ ] 피드백 생성 대상 emp_id가 scope 안인지 검증
- [ ] 피드백 수정/삭제는 작성자 또는 허용 권한인지 검증
- [ ] dropdown feedback 저장 시 `feedback_type`별 권한 검증
- [ ] branch feedback은 head/leader만 허용
- [ ] hq feedback은 superuser만 허용
- [ ] 클라이언트 권한 표시와 서버 권한이 일치하는지 확인

#### 관련 파일
```text
commission/views/api_collect.py
commission/services/collect.py
static/js/commission/collect_home.js
audit/services.py
```

#### 위험 설명
프론트에서 드롭다운을 숨겨도 사용자가 직접 POST를 보내면 서버가 최종 차단해야 합니다. 환수 피드백은 민감한 채권/추심 메모 성격이므로 scope 우회가 심각합니다.

#### 패치 방향
1. service layer에 `can_access_emp(user, emp_id, ym=None)` 성격 정책 함수 추가
2. feedback CRUD와 dropdown 저장에 공통 적용
3. 권한 실패 시 403 반환
4. audit failure 기록

---

### 6) Deposit API의 권한 정책 정교화

- [ ] superuser/head/main_admin 외 사용자의 본인 조회만 허용되는지 확인
- [ ] leader 팀 단위 조회 허용 여부 정책 결정
- [ ] search modal 결과와 Deposit API 조회 권한 불일치 점검
- [ ] `regist`, `username` fallback 조회가 의도치 않은 사용자 조회를 허용하지 않는지 확인
- [ ] 대상자 미존재/권한 없음 메시지로 사용자 존재 여부가 과도하게 노출되지 않는지 검토

#### 관련 파일
```text
commission/views/api_deposit_impl.py
accounts/search_api.py
static/js/commission/deposit_home.js
```

#### 위험 설명
채권관리 API는 채권합계, 보증보험, 기타채권, 수수료 지표를 반환합니다. 사용자 검색에서는 보였지만 실제 조회 권한이 없는 대상자라면 API에서 차단해야 합니다.

#### 패치 방향
1. Deposit 전용 policy 함수 분리
2. head/leader/basic별 scope 명확화
3. API별 공통 resolver에 정책 적용
4. 권한 실패 응답 통일

---

### 7) fail download URL 프론트 노출 검증

- [ ] `fail_download_url`이 same-origin인지 확인
- [ ] `approval_excel_upload.js`에서 외부 URL을 링크로 세팅하지 않는지 확인
- [ ] `excel_upload.js`에서도 같은 검증 적용
- [ ] `target="_blank"` 사용 시 `rel="noopener"` 유지
- [ ] token URL이 console/log에 노출되지 않는지 확인

#### 관련 파일
```text
static/js/commission/approval_excel_upload.js
static/js/excel_upload.js
commission/views/api_upload.py
commission/views/approval.py
```

#### 위험 설명
서버가 내려주는 URL을 그대로 href에 넣으면 서버 버그 또는 응답 오염 시 외부 링크로 연결될 수 있습니다. 같은 origin 내부 다운로드만 허용해야 합니다.

#### 패치 방향
1. JS util에 same-origin URL validator 추가
2. invalid URL은 링크 표시하지 않음
3. 서버에서도 reverse URL만 생성

---

### 8) Audit log 누락

- [ ] 채권 업로드 성공/실패 audit
- [ ] approval/efficiency 업로드 성공/실패 audit
- [ ] 환수관리 업로드 성공/실패 audit
- [ ] fail 다운로드 audit
- [ ] approval/efficiency 다운로드 audit
- [ ] dropdown feedback 저장 audit
- [ ] 피드백 CRUD audit의 meta 마스킹 확인

#### 관련 파일
```text
audit/constants.py
audit/services.py
commission/views/api_upload.py
commission/views/approval.py
commission/views/downloads.py
commission/views/api_collect.py
commission/services/collect.py
```

#### 위험 설명
수수료/채권 데이터 변경과 다운로드는 사후 추적이 필수입니다. 로그가 없으면 사고 발생 시 원인과 범위를 확인하기 어렵습니다.

#### 패치 방향
1. ACTION 상수 추가 또는 기존 상수 재사용
2. log_action 호출 통일
3. meta에는 요약 정보만 저장
4. token, 상세 row, 원문 body는 저장하지 않음

---

## A-3. 중상 등급

### 9) 업로드 temp 파일 삭제 실패 무시

- [ ] `safe_delete()` 실패 시 warning log를 남기는지 확인
- [ ] temp 파일 누적 모니터링 기준 수립
- [ ] temp cleanup 주기 작업 필요 여부 검토
- [ ] 업로드 실패/성공 모두 temp 삭제 확인

#### 관련 파일
```text
commission/views/_files.py
commission/views/api_upload.py
commission/views/approval.py
web_ma/settings.py
```

#### 위험 설명
현재 삭제 실패를 완전히 무시하면 운영 중 temp 파일이 누적될 수 있습니다. 보안상 업로드 원본 파일이 서버에 남는 것도 문제입니다.

#### 패치 방향
1. `safe_delete()`에 logger.warning 추가
2. 파일명은 마스킹 또는 basename만 기록
3. 필요 시 cleanup command/task 설계

---

### 10) JSON이 아닌 응답 처리 통일 부족

- [ ] `collect_home.js`의 `apiFetch`, `apiPost`가 content-type을 검사하는지 확인
- [ ] `approval_excel_upload.js`의 `postFormData`가 JSON 아닌 응답을 방어하는지 확인
- [ ] 공용 `_net_json.js`와 중복 로직 정리 가능성 검토
- [ ] 로그인 만료 HTML 응답 시 사용자에게 명확히 안내하는지 확인

#### 관련 파일
```text
static/js/commission/_net_json.js
static/js/commission/collect_home.js
static/js/commission/approval_excel_upload.js
static/js/commission/deposit_home.js
```

#### 위험 설명
세션 만료, 권한 오류, 서버 500 페이지가 HTML로 반환되면 JS에서 `.json()` 파싱 오류가 발생하고 사용자에게 의미 없는 오류가 보일 수 있습니다.

#### 패치 방향
1. 공용 `fetchJSON`을 POST까지 확장
2. content-type guard 재사용
3. 403/401/로그인 만료 메시지 표준화

---

### 11) innerHTML 렌더링 구간 XSS 회귀 위험

- [ ] `collect_home.js`의 모든 row HTML 값에 `esc()` 적용 확인
- [ ] `deposit_home.js`의 table HTML 값에 `escapeHtml()` 적용 확인
- [ ] 서버 message를 innerHTML로 넣는 구간 확인
- [ ] upload result modal 렌더링 escape 확인
- [ ] 신규 컬럼 추가 시 escape 누락 방지

#### 관련 파일
```text
static/js/commission/collect_home.js
static/js/commission/deposit_home.js
static/js/excel_upload.js
static/js/commission/_format.js
```

#### 위험 설명
현재 주요 구간은 escape를 사용하지만, 향후 컬럼 추가나 결과 모달 개선 시 한 군데라도 escape가 빠지면 stored/reflected XSS가 될 수 있습니다.

#### 패치 방향
1. HTML 렌더 helper 사용 규칙 문서화
2. `tdText()`, `tdMoney()` 같은 안전 helper 확대
3. 서버 message는 textContent 우선

---

### 12) CSP unsafe-inline 제거 준비 부족

- [ ] `_approval_upload_modal.html`의 inline script 외부화
- [ ] collect_home.html/deposit_home.html의 inline style class화
- [ ] `_modals.js` 동적 modal innerHTML 내 inline style class화
- [ ] CSP report-only 기준으로 위반 항목 수집

#### 관련 파일
```text
commission/templates/commission/_approval_upload_modal.html
commission/templates/commission/deposit_home.html
commission/templates/commission/collect_home.html
static/js/commission/_modals.js
static/css/apps/commission.css
web_ma/settings.py
web_ma/middleware.py
```

#### 위험 설명
운영 보안 헤더 강화 시 inline script/style이 남아 있으면 CSP strict 모드 전환이 어렵습니다.

#### 패치 방향
1. inline validation script를 `approval_upload_validation.js`로 분리
2. inline style을 commission.css로 이동
3. CSP report-only에서 검증

---

## A-4. 중 등급

### 13) Excel export 데이터 scope 보장

- [ ] client export는 화면에 보이는 데이터만 포함하는지 확인
- [ ] server export는 queryset scope를 적용하는지 확인
- [ ] head/leader에게 다운로드를 허용할 경우 스코프 제한 확인
- [ ] 전체 다운로드는 superuser만 허용할지 정책 결정

#### 관련 파일
```text
static/js/commission/approval_home_export.js
static/js/commission/collect_home.js
commission/views/downloads.py
commission/views/pages.py
```

#### 위험 설명
화면에 제한된 데이터만 보이더라도 서버 다운로드가 전체 데이터를 반환하면 권한 정책이 깨집니다.

---

### 14) 오류 메시지에 내부 정보 노출 가능성

- [ ] pandas/openpyxl 원문 exception이 사용자에게 그대로 가지 않는지 확인
- [ ] `fetchJSON` non-JSON body 일부가 console에만 남는지 확인
- [ ] 서버 JSON message가 내부 경로/SQL/traceback을 포함하지 않는지 확인
- [ ] audit meta에 request body 전체를 저장하지 않는지 확인

#### 관련 파일
```text
commission/views/api_upload.py
commission/views/approval.py
commission/upload_utils/_readers.py
static/js/commission/_net_json.js
audit/services.py
```

---

### 15) Dropdown feedback 허용값 서버 검증

- [ ] `feedback_type in {"branch", "hq"}` 검증
- [ ] value가 허용 option 중 하나인지 검증
- [ ] 빈 값 허용 여부 정책화
- [ ] 프론트 option과 서버 allowlist 일치

#### 관련 파일
```text
commission/services/collect.py
commission/views/api_collect.py
static/js/commission/collect_home.js
```

---

## A-5. 중하 등급

### 16) `api_deposit.py` shim의 501 fallback 운영 노출

- [ ] 501 fallback이 운영에서 호출될 가능성 확인
- [ ] import 실패 시 logger 기록 여부 확인
- [ ] API 클라이언트에 내부 import 에러명이 노출되지 않는지 확인

#### 관련 파일
```text
commission/views/api_deposit.py
commission/views/__init__.py
```

---

### 17) `approval_home_export.js` HTML 기반 xls 생성 보안 검토

- [ ] export title/baseName escape 검토
- [ ] table clone 후 불필요한 버튼/링크 제거 확인
- [ ] a 태그 제거 범위가 충분한지 확인
- [ ] formula injection 가능성 검토

#### 관련 파일
```text
static/js/commission/approval_home_export.js
```

#### 설명
Excel formula injection은 사용자가 입력한 값이 `=`, `+`, `-`, `@`로 시작할 때 Excel에서 수식으로 해석되는 문제입니다. 현재 내부 데이터 중심이지만 피드백/메모/상품명 등 사용자 입력값이 export될 경우 검토가 필요합니다.

---

## A-6. 하 등급

### 18) Clipboard API fallback 검토

- [ ] `document.execCommand("copy")` fallback 유지 필요성 확인
- [ ] HTTPS 환경 Clipboard API 동작 확인
- [ ] 복사 실패 시 사용자 안내 적절성 확인

#### 관련 파일
```text
static/js/commission/_modals.js
static/js/commission/collect_home.js
```

---

# Part B. 성능 개선 요구사항 체크리스트

---

## B-1. 최상 등급

### 1) Deposit 업로드 row-by-row upsert 병목

- [ ] `DepositSummary.objects.update_or_create()` 반복 호출 handler 식별
- [ ] 대량 업로드 row 수 기준 성능 측정
- [ ] bulk upsert 전환 가능 필드 그룹 분류
- [ ] missing_users/missing_sample 동작 유지
- [ ] 기존 필드만 업데이트하는 semantics 유지
- [ ] transaction.atomic 범위 유지
- [ ] upload log count 유지

#### 관련 파일
```text
commission/upload_handlers/deposit.py
commission/models.py
commission/upload_utils/_db.py
```

#### 병목 설명
채권 업로드는 수천~수만 행이 될 수 있습니다. row마다 `update_or_create()`를 호출하면 DB round-trip이 폭증합니다.

#### 개선 방향
1. df 정규화 후 existing ids bulk 조회
2. 기존 DepositSummary in_bulk
3. 신규/수정 object 분리
4. `bulk_create(update_conflicts=True)` 또는 `bulk_update` 적용
5. 결과 count 기존과 동일하게 반환

---

### 2) Collect 대량 테이블 전체 렌더링 병목

- [ ] `_allTabData` row 수 확인
- [ ] 필터/정렬 시 전체 rows 순회 비용 측정
- [ ] `innerHTML` 전체 재렌더 시간 확인
- [ ] 1,000행 이상에서 브라우저 체감 성능 확인
- [ ] pagination 또는 server-side filtering 도입 여부 검토
- [ ] 탭별 데이터 캐시 전략 검토

#### 관련 파일
```text
static/js/commission/collect_home.js
commission/services/collect.py
commission/views/api_collect.py
commission/templates/commission/collect_home.html
```

#### 병목 설명
Collect 페이지는 탭별 데이터, branch filter, keyword filter, 정렬, SheetJS export를 모두 클라이언트에서 처리합니다. 데이터가 커지면 렌더링과 메모리 사용량이 급격히 증가합니다.

#### 개선 방향
1. 우선 현재 렌더 시간을 계측
2. 1차: debounce + render 최소화
3. 2차: pagination
4. 3차: server-side search/sort/filter
5. 4차: virtual scrolling 검토

---

## B-2. 상 등급

### 3) Approval/Efficiency 업로드 raw matrix 중복 읽기

- [ ] `_common_upload()`에서 row_count 산정을 위해 raw matrix 읽는 비용 확인
- [ ] handler 내부에서 동일 파일을 다시 읽는지 확인
- [ ] 한 번 읽은 raw matrix를 handler에 전달할 수 있는지 검토
- [ ] 함수 signature 변경 시 backward-compatible alias 유지

#### 관련 파일
```text
commission/views/approval.py
commission/upload_handlers/approval.py
commission/upload_handlers/efficiency.py
commission/upload_utils/_readers.py
```

#### 병목 설명
대형 Excel 파일을 row_count 계산과 실제 handler 처리에서 중복 파싱하면 업로드 시간이 증가합니다.

#### 개선 방향
1. raw matrix 1회 read
2. approval/efficiency handler가 df_raw를 받을 수 있는 optional path 추가
3. 기존 file_path API는 wrapper로 유지

---

### 4) Excel 다운로드 메모리 사용량

- [ ] pandas DataFrame → BytesIO export row 수 확인
- [ ] 다운로드 대상 row 수 상한 필요 여부 검토
- [ ] openpyxl write_only 방식 검토
- [ ] streaming response 필요 여부 검토
- [ ] `values()` 기반으로 queryset field 제한

#### 관련 파일
```text
commission/views/_excel_export.py
commission/views/downloads.py
```

#### 병목 설명
pandas DataFrame 전체를 메모리에 만들고 BytesIO로 xlsx를 생성하면 대량 데이터에서 메모리 사용량이 큽니다.

#### 개선 방향
1. field 제한
2. write_only workbook
3. chunk iteration
4. 필요 시 비동기 export

---

### 5) Collect service scope 계산 반복

- [ ] leader scope 계산 쿼리 수 확인
- [ ] `_get_allowed_emp_ids_for_leader()` 결과 캐시 가능성 검토
- [ ] SubAdminTemp 조회 최적화
- [ ] 팀 scope가 큰 경우 `emp_id__in` 성능 확인
- [ ] branch fallback 쿼리 비용 확인

#### 관련 파일
```text
commission/services/collect.py
partner/models.py
accounts/models.py
```

#### 병목 설명
leader 사용자가 탭을 바꿀 때마다 팀 scope 계산이 반복될 수 있습니다.

#### 개선 방향
1. request 단위 memoization
2. scope helper 분리
3. 필요 시 cache short TTL
4. emp_id list가 큰 경우 join/subquery 방식 검토

---

## B-3. 중상 등급

### 6) Collect 최신 피드백 Subquery 성능

- [ ] `CollectFeedback(emp_id, created_at)` index 필요 여부 확인
- [ ] `CollectDropdownFeedback(emp_id, ym, feedback_type, created_at)` index 필요 여부 확인
- [ ] annotate Subquery 실행 계획 확인
- [ ] 데이터 증가 시 materialized latest feedback 전략 검토

#### 관련 파일
```text
commission/services/collect.py
commission/models.py
```

#### 개선 방향
1. index 확인
2. explain analyze
3. 필요 시 모델 index 추가 migration
4. latest value denormalization은 장기 검토

---

### 7) Deposit API 4개 병렬 호출 구조 최적화

- [ ] `userDetail`, `summary`, `surety`, `other` 4개 API 응답 시간 측정
- [ ] 같은 user 반복 조회 캐싱 필요 여부 검토
- [ ] 통합 API로 줄일 경우 회귀 위험 검토
- [ ] 기존 URL 유지하면서 optional aggregate API 추가 가능성 검토

#### 관련 파일
```text
static/js/commission/deposit_home.js
commission/views/api_deposit_impl.py
commission/urls.py
```

#### 설명
현재 병렬 호출은 구조적으로 나쁘지 않습니다. 다만 네트워크 round-trip이 많고 API별 권한 resolver가 반복될 수 있습니다.

#### 개선 방향
1. 기존 API 유지
2. optional aggregate API 신규 추가
3. deposit_home.js는 점진적으로 aggregate 우선, fallback 기존 4개 API

---

### 8) 클라이언트 Excel export 대량 처리

- [ ] `approval_home_export.js` table clone 시간 확인
- [ ] `collect_home.js` SheetJS workbook 생성 시간 확인
- [ ] 브라우저 메모리 사용량 확인
- [ ] 서버 export로 대체할 데이터 규모 기준 수립

#### 관련 파일
```text
static/js/commission/approval_home_export.js
static/js/commission/collect_home.js
```

#### 개선 방향
1. row count 기준 warning
2. 서버 export endpoint 제공
3. 권한 scope 적용 후 서버 XLSX 생성

---

### 9) Upload fail rows cache payload 크기

- [ ] fail rows 저장 개수 제한
- [ ] missing_sample만 저장하는 현재 정책 적절성 확인
- [ ] 전체 fail rows 저장 필요 시 파일 저장소/DB 분리 검토
- [ ] Redis 메모리 사용량 확인

#### 관련 파일
```text
commission/views/utils_fail_excel.py
commission/views/api_upload.py
commission/views/approval.py
```

---

## B-4. 중 등급

### 10) CommissionCommon 네트워크 유틸 중복 정리

- [ ] `_net_json.js`와 각 페이지 fallback fetch 중복 확인
- [ ] POST JSON helper 추가 가능성 검토
- [ ] form upload helper 추가 가능성 검토
- [ ] content-type guard 공통화

#### 관련 파일
```text
static/js/commission/_net_json.js
static/js/commission/deposit_home.js
static/js/commission/collect_home.js
static/js/commission/approval_excel_upload.js
```

---

### 11) CSS nth-child 기반 collect 컬럼폭 유지보수 비용

- [ ] JS TAB_COLS와 CSS nth-child 정합성 확인
- [ ] 컬럼 추가 시 class 기반 width로 전환 가능성 검토
- [ ] 탭별 컬럼 수 차이에 따른 width 깨짐 확인

#### 관련 파일
```text
static/js/commission/collect_home.js
static/css/apps/commission.css
```

---

### 12) Approval page server/client export 역할 중복

- [ ] 화면 버튼은 client export, URL은 server export인 이중 구조 문서화
- [ ] 사용자에게 어떤 export가 공식인지 결정
- [ ] server export 권한 보강 후 client export 유지 여부 검토

#### 관련 파일
```text
commission/views/downloads.py
static/js/commission/approval_home_export.js
commission/templates/commission/approval_home.html
```

---

## B-5. 중하 등급

### 13) Legacy shim 정리 가능성

- [ ] `commission/views/api_deposit.py` shim 사용처 확인
- [ ] `commission/views/utils_excel.py` shim 사용처 확인
- [ ] `commission/upload_utils/upload_utils.py` shim 사용처 확인
- [ ] 제거가 아니라 import surface 문서화 우선

#### 관련 파일
```text
commission/views/api_deposit.py
commission/views/utils_excel.py
commission/upload_utils/upload_utils.py
commission/views/__init__.py
```

#### 설명
현재 shim은 호환성 유지에 도움이 됩니다. 성능에는 큰 영향이 없으므로 제거보다 문서화와 점진 정리가 우선입니다.

---

### 14) SupportModal/TextViewer 동적 modal 생성 중복

- [ ] deposit_home.js fallback과 `_modals.js` 중복 확인
- [ ] 공용 util 로드가 보장되는 페이지에서 fallback 축소 가능성 검토
- [ ] 단, “공용 유틸이 없어도 동작” 원칙 유지 여부 결정

#### 관련 파일
```text
static/js/commission/_modals.js
static/js/commission/deposit_home.js
```

---

### 15) 템플릿 inline style 정리

- [ ] approval title inline color class화
- [ ] collect filter inline flex style class화
- [ ] modal z-index inline style class화
- [ ] pre style class화

#### 관련 파일
```text
commission/templates/commission/approval_home.html
commission/templates/commission/collect_home.html
commission/templates/commission/deposit_home.html
static/css/apps/commission.css
```

---

## B-6. 하 등급

### 16) UI micro-optimization

- [ ] button text 변경 시 layout shift 확인
- [ ] modal 생성 시 DOM append 시점 최적화
- [ ] mobile scroll UX 개선
- [ ] table column width 미세 조정

#### 관련 파일
```text
static/js/commission/_modals.js
static/css/apps/commission.css
```

---

### 17) 장기 구조 개선: Commission permission policy 모듈

- [ ] `commission/policies.py` 신설 여부 검토
- [ ] deposit/collect/download/upload scope 함수를 한곳으로 모을지 검토
- [ ] accounts/partner scope 정책과 중복 최소화

#### 관련 파일
```text
commission/views/api_deposit_impl.py
commission/services/collect.py
commission/views/downloads.py
commission/views/api_upload.py
commission/views/approval.py
```

---

# Part C. 단계별 패치 로드맵

---

## 1단계: 최상 보안 패치

목표: 실제 정보 유출·권한 우회·CSRF 위험을 먼저 차단합니다.

- [ ] fail token owner/scope binding
- [ ] approval/efficiency 다운로드 권한 데코레이터 + scope
- [ ] upload API `csrf_exempt` 제거
- [ ] 서버단 업로드 파일 검증
- [ ] Collect feedback/dropdown 서버 scope 검증

검증:

```bash
python manage.py check
```

수동 검증:

- superuser 업로드
- CSRF 없는 POST 차단
- head/leader 다운로드 scope
- token owner mismatch 403
- Collect 타 지점 emp_id 저장 차단

---

## 2단계: 상 보안 + 감사로그

목표: 사고 추적성과 우회 방어를 강화합니다.

- [ ] download audit log
- [ ] upload failure audit log 정리
- [ ] fail_download_url same-origin 검증
- [ ] Deposit API policy 정교화
- [ ] temp delete warning log

---

## 3단계: 최상/상 성능 패치

목표: 업로드·조회·렌더링 병목을 줄입니다.

- [ ] DepositSummary row-by-row upsert bulk화
- [ ] approval/efficiency raw matrix 중복 read 제거
- [ ] Collect 대량 렌더링 계측 후 1차 최적화
- [ ] Excel 다운로드 field 제한 및 write_only 검토

---

## 4단계: 중상 안정성 패치

목표: 대량 데이터와 운영 장애 대응력을 높입니다.

- [ ] Collect latest feedback index 검토
- [ ] leader scope 계산 최적화
- [ ] fail rows cache payload 제한
- [ ] Deposit aggregate API 검토

---

## 5단계: 중/중하 구조 정리

목표: 장기 유지보수성을 개선합니다.

- [ ] CommissionCommon network util 통합
- [ ] collect CSS nth-child 의존 완화
- [ ] inline script/style 외부화
- [ ] export 역할 정리
- [ ] shim import surface 문서화

---

## 6단계: 하 등급 장기 개선

목표: UI 품질과 구조적 일관성을 보완합니다.

- [ ] modal fallback 중복 축소
- [ ] permission policy 모듈 설계
- [ ] mobile table UX 개선
- [ ] CSP strict 전환 준비

---

# Part D. 패치 전 공통 확인 질문

실제 diff 패치를 시작하기 전, 아래 정책은 확정해야 합니다.

## 1. 권한 정책

- [ ] approval/efficiency 다운로드는 superuser만 허용할 것인가?
- [ ] head/leader에게 다운로드를 허용한다면 branch/team scope로 제한할 것인가?
- [ ] Deposit API에서 leader 팀 단위 조회를 허용할 것인가?
- [ ] basic 사용자는 본인 채권정보 조회를 허용할 것인가?

## 2. 업로드 파일 정책

- [ ] 허용 확장자: `.xlsx`, `.xls`만인가?
- [ ] CSV/TSV/HTML table Excel은 계속 허용할 것인가?
- [ ] 파일 최대 크기 기준은 몇 MB인가?
- [ ] 업로드 실패 파일 원본을 보관하지 않는 정책으로 확정할 것인가?

## 3. fail token 정책

- [ ] token은 생성자 본인만 다운로드 가능한가?
- [ ] superuser는 모든 token 다운로드 가능한가?
- [ ] TTL은 1시간 유지인가?
- [ ] fail rows 전체 저장이 필요한가, sample만 저장할 것인가?

## 4. Collect 정책

- [ ] head는 본인 branch 전체 환수 대상 조회인가?
- [ ] leader는 팀 기준인가, branch fallback 유지인가?
- [ ] hq feedback은 superuser 전용으로 확정인가?
- [ ] branch feedback은 head/leader만 수정 가능한가?

---

# Part E. 최종 요약

## 보안상 최우선 5개

1. fail token owner/scope binding
2. approval/efficiency 다운로드 권한 검증
3. upload API CSRF 보호 복구
4. 서버단 파일 검증
5. Collect feedback/dropdown 서버 scope 검증

## 성능상 최우선 5개

1. Deposit upload row-by-row upsert bulk화
2. Collect 대량 table 렌더링 최적화
3. Approval/Efficiency raw matrix 중복 read 제거
4. Excel export 메모리 사용량 개선
5. Collect scope/latest feedback query 최적화

## 패치 원칙

- URL name 변경 금지
- DOM id/data-* 변경 금지
- upload registry SSOT 유지
- upload_utils SSOT 유지
- CommissionCommon 추가-only 구조 유지
- 기능 변화 0 기본값
- 패치는 diff 형식으로만 진행
