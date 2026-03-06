# django_ma/docs/02_apps/commission.md

# Commission 앱 가이드 (commission.md)

-----------------------------------------------------------------------

## 1. Commission 앱 개요

commission 앱은 django_ma 내부 운영에서 사용하는 **수수료(Commission) 업무 플랫폼**이며,
다음 3개 도메인을 중심으로 설계되어 있습니다.

- **Deposit(채권관리)**: 대상자 기반 채권/보증/기타/지표 조회 + 지원신청서(PDF/텍스트) 지원
- **Approval(수수료결재)**: 월도/부서 기준 미결 현황 조회 + 엑셀 업로드/다운로드
- **Efficiency(지점효율)**: 월도/부서 기준 지급 초과 현황 조회 + 엑셀 업로드/다운로드

> ⚠️ Commission 앱은 “엑셀 업로드(대량 데이터) + 민감 재무 데이터(채권/수수료)”가 결합된 운영 앱입니다.  
> 따라서 **보안(권한/노출) + 운영 안정성(업로드/로그/실패복구)**를 최우선으로 합니다.

-----------------------------------------------------------------------

## 2. 앱의 책임 (Responsibility)

Commission 앱의 핵심 책임은 다음과 같습니다.

1) **엑셀 업로드 기반 데이터 갱신(SSOT Registry 기반)**
- 업로드 타입(최종지급액/환수지급예상/보증보험/기타채권/통산손·생보/응당손·생보/결재/효율 등)을 SSOT로 정의
- 실패 행(fail rows)은 **fail_token**으로 엑셀 다운로드 제공

2) **권한 기반 조회**
- 사용자의 등급/스코프에 따라 조회 범위를 제한
- “본인 vs 관리자”를 명확히 분리 (서버에서 최종 판정)

3) **UI 계약 기반 프론트 운영**
- 템플릿의 `id / data-* / tbody id`는 JS가 직접 의존 → **변경 금지 계약**
- 공용 프론트 유틸(`window.CommissionCommon.*`)은 “추가만” 수행 (기능 영향 0)

-----------------------------------------------------------------------

## 3. 디렉터리 구조 (최종 기준)

> 아래 구조는 “SSOT 분리 + 업로드/유틸 재사용”을 목표로 유지됩니다.

### 3.1 Backend (권장 기준)

commission/
├── models.py
├── urls.py
├── admin.py
├── apps.py
│
├── views/
│   ├── __init__.py          # lazy re-export surface (SSOT)
│   ├── pages.py             # HTML page views (deposit/approval)
│   ├── api_deposit.py       # shim (impl 우선, fallback)
│   ├── api_deposit_impl.py  # deposit 도메인 실제 구현 (권한/조회)
│   ├── api_upload.py        # registry 기반 업로드 엔드포인트
│   ├── approval.py          # approval/efficiency 업로드 공통
│   ├── downloads.py         # fail token / export 다운로드
│   ├── constants.py         # 업로드 카테고리/threshold 등 상수
│   ├── utils_json.py        # JSON 응답/Content-Disposition SSOT
│   ├── utils_excel.py       # excel 생성 유틸(필요 시)
│   └── utils_fail_excel.py  # fail token cache + xlsx 생성
│
├── upload_handlers/         # “업로드 비즈니스 로직” (SSOT)
│   ├── __init__.py          # public surface + SSOT _update_upload_log re-export
│   ├── registry.py          # UploadSpec registry (SSOT)
│   ├── deposit.py           # 채권 업로드 핸들러들
│   ├── approval.py          # 결재 업로드 핸들러
│   └── efficiency.py        # 효율 업로드 핸들러
│
└── upload_utils/            # “엑셀 파싱/탐지/변환/DB helper” (SSOT)
    ├── __init__.py
    ├── upload_utils.py      # legacy shim (공식 export)
    ├── _readers.py
    ├── _detect.py
    ├── _convert.py
    └── _db.py

-----------------------------------------------------------------------

## 4. URL 구조

> URL name / route는 views/pages/api/downloads 단위로 책임이 분리되어야 합니다.

### 4.1 Pages

- `/commission/deposit/` : 채권관리(Deposit Home)
- `/commission/approval/` : 수수료결재(Approval Home)

### 4.2 Upload

- `/commission/upload-excel/` : 채권 업로드(Registry 기반)
- `/commission/approval/upload-excel/` : 결재/효율 업로드(kind=approval|efficiency)

### 4.3 API

- Deposit 조회 API (대상자/요약/보증보험/기타채권)
- 지원신청서 API(텍스트/또는 PDF 제공)

### 4.4 Downloads

- fail_token 엑셀 다운로드
- approval/effectiveness 테이블 export 다운로드(프론트에서 .xls 생성도 지원)

-----------------------------------------------------------------------

## 5. 핵심 개념 정리

### (1) Upload Registry (SSOT)
- “업로드 타입 문자열”을 키로, 업로드 모드(df/file) 및 핸들러를 정의
- 신규 업로드 타입 추가는 **registry에만 추가**하는 방식이 원칙

### (2) Upload Utils (SSOT)
- Reader: 엑셀/HTML/CSV 편차 대응
- Detect: 컬럼 탐지(별칭/스코어링/금칙어/특화 탐지)
- Convert: 숫자/날짜/사번 정규화(예: 1234567.0 → "1234567")
- DB: bulk 조회/업로드 로그 갱신 유틸

### (3) Deposit Home UI Contract
- 템플릿의 `data-bind`, `data-type="money|percent"`, `tbody id`는 JS 렌더 계약
- 대상자 전환은 pushState/popstate 기반

### (4) Fail Token
- 업로드 실패 행을 cache에 저장하고 토큰으로 다운로드 제공
- 운영 안전을 위해 “권한 체크 + TTL + 레이트리밋”을 권장

-----------------------------------------------------------------------

## 6. 템플릿 구조 및 상속 규칙

Commission 템플릿은 `base.html`을 상속하며,
앱 CSS는 반드시 `{% block app_css %}`에서만 로드합니다. (프로젝트 규칙)

### 6.1 Approval Upload Modal (DOM 계약)

- Form id/action/field name은 JS가 직접 의존하므로 변경 금지:
  - `form#approvalUploadForm`
  - fields: `ym`, `part`, `kind`, `excel_file`
  - result area: `#approvalUploadResult`
  - fail download: `#approvalFailDownloadWrap`, `#approvalFailDownloadLink`
  - submit button: `#approvalUploadSubmitBtn`

> 모달 내부 inline script는 “Bootstrap validity 표시”만 수행하며,  
> 업로드/중복제출 방지는 `approval_excel_upload.js`가 SSOT입니다.

### 6.2 Approval Home (Export 계약)

- root: `#approval-home` dataset
  - `data-selected-ym`, `data-selected-part`
- export table id(변경 금지):
  - `#efficiencyExcessTable`
  - `#approvalPendingTable`
- export button contract:
  - `data-export-table`, `data-export-name`

### 6.3 Deposit Home (FINAL Contract)

- root: `#deposit-home` dataset url (변경 금지)
  - user/summary/surety/other/reset/support-pdf
- buttons:
  - `#resetUserBtn`, `#supportPdfBtn`
- bind targets:
  - `data-bind="target.*"`, `data-bind="summary.*"`
  - formatter hint: `data-type="money|percent"`
- tables:
  - surety tbody: `#suretyTableBody`
  - other tbody: `#otherTableBody`
- upload summary contract:
  - `data-upload-date`, `data-upload-type`, `data-part`
- upload modals:
  - `#excelUploadModal`, `#excelUploadResultModal`, `#uploadToast`

-----------------------------------------------------------------------

## 7. JavaScript 구조

Commission 앱은 “공용 유틸(전역 추가-only) + 페이지 엔트리” 구조로 운영합니다.

### 7.1 공용 유틸 (기능 영향 0)

- `static/js/commission/_dom.js`
- `static/js/commission/_format.js`
- `static/js/commission/_net_json.js`
- `static/js/commission/_modals.js`

원칙:
- `window.CommissionCommon.*` 네임스페이스에만 기능을 “추가”
- 기존 페이지 동작을 바꾸지 않는다(호환 유지)

### 7.2 페이지/기능 스크립트

- `static/js/commission/approval_excel_upload.js`
  - 업로드 submit lock(`dataset.submitting`) + selector fallback
  - FormData 강제 set(`excel_file`) + fail download 링크 표시
  - 성공 후 모달 닫기/토스트/리로드 플로우

- `static/js/commission/approval_home_export.js`
  - `data-export-*`로 지정된 테이블을 .xls로 다운로드
  - 파일명: ym/part/타임스탬프 반영

- `static/js/commission/deposit_home.js` (type="module")
  - dataset URL 기반 fetch & render
  - data-bind 바인딩 + alias map(서버 응답 mismatch 흡수)
  - pushState/popstate 대상자 전환
  - ellipsis modal + 지원신청서 모달(복사/미리보기)

-----------------------------------------------------------------------

## 8. CSS 설계 원칙

파일:
- `static/css/apps/commission.css`

### 8.1 Deposit (채권현황) 정책
- `.deposit-maxw` : 레이아웃 기준 폭
- `.ellipsis-cell` : JS 모달(전체보기) UX를 위한 말줄임
- `#suretyTable`, `#otherTable` : `table-layout: fixed` + `colgroup(%) 폭` 고정
- 금액 컬럼(3열) 우측 정렬
- 클릭 UX(증권번호/비고)는 cursor pointer 유지

### 8.2 Approval (결재/효율) 정책
- `.commission-table-scroll` : 가로 스크롤 래퍼
- `.commission-nowrap-table` : width=max-content + nowrap(줄바꿈 금지) 정책
- `.money-cell` : nowrap 보장(전역과 충돌 방지)

-----------------------------------------------------------------------

## 9. 보안 설계 (필수 원칙)

### 9.1 권한(Access Control)
- “민감 데이터 최종 판정”은 반드시 서버(View/API)에서 수행
- 프론트는 서버 판단을 신뢰하며, UI만 보조

권장:
- scope(부서/지점/채널) 정책을 SSOT 함수로 통일
- head 권한 범위는 운영에서 사고가 잦으므로 테스트로 고정

### 9.2 업로드 보안
- 서버단에서 확장자만 믿지 말고,
  - 파일 시그니처/콘텐츠 타입 점검
  - 최대 파일 크기 제한
  - 업로드 레이트리밋(운영 안정성)
을 권장

### 9.3 Fail Token 보호
- 토큰 기반 다운로드는 편하지만 유출 위험이 있으므로,
  - “생성자/업로드 세션과 토큰 결합”
  - TTL 유지
  - 요청자 권한 체크
를 권장

### 9.4 XSS/HTML 처리
- 업로드 결과/에러 텍스트는 escape 처리 원칙
- 서버에서 내려주는 문자열을 클라이언트에서 innerHTML로 직접 주입 시 주의

-----------------------------------------------------------------------

## 10. 운영 포인트 (Do-Not-Break 리스트)

아래는 운영 안정성 상 “변경 시 회귀 위험”이 큰 영역입니다.

### 10.1 업로드 SSOT
- `upload_handlers/registry.py`
- `upload_utils/*`
- `_update_upload_log` SSOT 흐름

### 10.2 템플릿 DOM 계약
- approval 업로드 모달: `#approvalUploadForm` 및 result/fail 영역 id
- approval 테이블 id: `#efficiencyExcessTable`, `#approvalPendingTable`
- deposit root dataset URL, data-bind, tbody id, modal id

### 10.3 프론트 공용 유틸
- `window.CommissionCommon.*`는 “추가-only” 원칙 유지

### 10.4 CSS 테이블 정책
- deposit: fixed layout + colgroup 폭
- approval: nowrap + 가로스크롤

-----------------------------------------------------------------------

## 11. 신규 기능 추가 패턴 (확장 설계 원칙)

### 11.1 신규 업로드 타입 추가
1) `upload_handlers/registry.py`에 UploadSpec 추가
2) 핸들러 구현(가능하면 deposit.py / approval.py / efficiency.py 중 적절한 곳)
3) fail token / upload log 갱신 흐름 유지
4) pages.py(업로드 타입 목록 노출) 및 템플릿 select 반영(필요 시)

### 11.2 비동기 업로드(고도화)
- Celery task로 업로드 처리 분리
- 진행률/결과/실패목록 다운로드(토큰) 표준화

### 11.3 감사(Audit) 로그 통합
- 업로드/다운로드/지원신청서 생성은 “중요 이벤트”
- actor, action, target(ym/part/kind), row_count, success/fail, fail_token 등을 기록

### 11.4 리포팅/지표 API 확장
- 월도 기준 집계(부서/지점별)
- 미결/초과 지표 대시보드화(dash 앱과 연동 가능)

-----------------------------------------------------------------------

## 12. 요약

Commission 앱은 “대량 엑셀 업로드 + 민감 재무 데이터”라는 운영 리스크가 큰 영역을
SSOT(Registry/Utils/DOM 계약)로 안정화한 구조입니다.

핵심 원칙:
- 업로드는 Registry/Utils SSOT로만 확장
- 권한은 서버에서 최종 판정
- 템플릿 DOM 계약은 변경 금지
- 공용 JS는 추가-only
- 테이블 폭 정책(colgroup/nowrap)을 유지

이 원칙을 지키면,
- 장기 운영
- 인수인계
- 기능 확장
이 모두 안정적으로 가능합니다.