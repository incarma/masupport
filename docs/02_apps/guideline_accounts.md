# accounts 앱 상세 문서 (FINAL)

## 1. 앱의 책임 (Responsibility)

`accounts` 앱은 **django_ma 시스템 전반의 사용자 식별·권한·접근 제어의 기준점(SSOT)** 역할을 한다.  
모든 앱(board / partner / manual / commission / dash 등)은 accounts 앱의 정책과 데이터를 **전제로** 동작한다.

### 핵심 책임 요약

- **CustomUser 모델** 정의 및 사용자 식별 기준 제공
- 사용자 **등급(grade)** / **상태(status)** 정책의 단일 기준
- 로그인 / 접근 제어의 최종 관문
- **권한 범위 기반 사용자 검색 API (SSOT)**
- 관리자용 **엑셀 업로드·다운로드**
  - Celery 기반 **비동기 처리**
  - **진행률 polling**
  - **결과 리포트 다운로드**
- grade 변경 시 **SubAdminTemp 자동 동기화**
- 검색/표시용 **affiliation_display(소속 표기 문자열)** 제공

---

## 2. 전체 구조 개요

accounts 앱은 다음과 같은 레이어로 구성된다.

accounts/
├── admin.py
├── apps.py
├── constants.py
├── decorators.py
├── forms.py
├── models.py
├── search_api.py
├── services/
│   └── users_excel_import.py
├── signals.py
├── tasks.py
├── urls.py
├── utils.py
├── views.py
└── templates/
    └── admin/accounts/customuser/
        ├── change_list.html
        └── upload__excel.html

## 3. 주요 파일별 역할 설명

### 3.1 models.py

#### CustomUser 모델 (SSOT)

- 시스템 전반에서 사용하는 **유일한 사용자 모델**
- `USERNAME_FIELD = "id"` (사번 기반 로그인)
- 주요 필드:
  - `id` : 사번 (PK / 로그인 ID)
  - `name` : 성명
  - `grade` : 사용자 등급
  - `status` : 재직 상태
  - `branch / part / team_*` : 소속 정보

#### 핵심 정책

- `inactive` 상태 → **무조건 `is_active = False`**
- Django 인증 / 세션 레벨에서 자동 차단

---

### 3.2 constants.py

- accounts 앱 전반에서 사용하는 **SSOT 상수 정의**
- 포함 범위:
  - 캐시 key prefix
  - 엑셀 Content-Type
  - 업로드/결과 리포트 관련 상수

> ⚠️ 엑셀 업로드, 진행률 polling, 결과 다운로드 로직에서  
> **하드코딩 금지 – 반드시 constants 참조**

---

### 3.3 decorators.py

#### `grade_required` 접근 제어 데코레이터

- 뷰 레벨 권한 제어의 **표준 방식**
- 주요 기능:
  - 허용 grade 검증
  - **inactive 계정 전면 차단**
  - alias_map 지원  
    - 예: `head`, `leader` → 내부적으로 허용 grade 묶음 처리

---

### 3.4 forms.py

- **ExcelUploadForm**
  - 관리자 사용자 엑셀 업로드용 폼
- **ActiveOnlyAuthenticationForm**
  - inactive 계정 로그인 차단 보강
  - 인증 단계에서 선제 차단

---

### 3.5 search_api.py (중요)

#### 사용자 검색 API – SSOT

- 시스템 내 **모든 사용자 검색의 단일 기준**
- 서버에서 권한·지점·부서·팀 범위를 **강제 제한**

#### 주요 특징

- 요청자 grade에 따라 검색 범위 자동 제한
- SubAdminTemp 정보 결합
- **`affiliation_display` 필드 생성**
  - 예: `지점 > 팀A`
  - 공통 검색 모달에서 그대로 사용

> 📌 board / partner / commission / deposit 등  
> **모든 사용자 검색은 반드시 이 API를 경유**

---

### 3.6 utils.py

- **`build_affiliation_display`**
  - 사용자 소속 정보를 사람이 읽기 쉬운 문자열로 변환
  - 검색 API / 프론트 표시용 SSOT

---

### 3.7 signals.py

#### CustomUser ↔ SubAdminTemp 자동 동기화

- `CustomUser.grade` 변경 시 자동 실행
- 정책:
  - 중간관리자 / 권한관리 대상 → SubAdminTemp 자동 생성
  - grade 변경 시 정보 동기화 유지

> 📌 관리자 UI, 엑셀 업로드 이후에도  
> **권한 데이터 불일치 방지**

---

### 3.8 services/users_excel_import.py (핵심)

#### 엑셀 업로드 비즈니스 로직 SSOT

- 엑셀 업로드 로직의 **모든 규칙이 이 파일에 집중**
- 주요 기능:
  - REQUIRED_COLS 기반 시트 자동 선택
  - 사번 / 날짜 / 값 정규화
  - grade / status / channel 정책 적용
  - **관리자 등급 보호 (강등 방지)**
  - 보호필드 / 보호등급 정책
  - 대용량 batch transaction

> ⚠️ `tasks.py`, `admin.py`는  
> **이 서비스만 호출해야 하며 직접 파싱/업서트 금지**

---

### 3.9 tasks.py

#### `process_users_excel_task`

- Celery 기반 사용자 엑셀 업로드 비동기 task
- 처리 흐름:
  1. 엑셀 수신
  2. `users_excel_import` 서비스 호출
  3. 대량 사용자 upsert
  4. **결과 리포트 엑셀 생성**
  5. cache에 진행률 / 상태 기록

#### 캐시 상태(JSON) 계약

```json
{
  "percent": 80,
  "status": "RUNNING",
  "error": "",
  "download_url": ""
}
```

### 3.10 views.py

`accounts.views`는 **프론트(UI) ↔ 백엔드 로직을 연결하는 얇은 컨트롤러 레이어**이다.  
실제 비즈니스 로직은 `services`, 비동기 처리는 `tasks`에 위임한다.

#### 주요 책임

- 엑셀 업로드 **진행률 조회 API**
- 엑셀 업로드 **결과 리포트 다운로드**
- 사용자 검색 API wrapper
- 로그인 / 세션 보조 뷰 제공

#### 핵심 뷰 구성

- **upload_progress**
  - Celery task 진행 상태를 cache에서 조회
  - 진행률 / 상태 / 에러 / 다운로드 URL 반환
- **upload_result**
  - 업로드 완료 후 생성된 결과 리포트 다운로드
- **api_search_user**
  - `search_api.py`를 호출하는 wrapper
  - legacy URL 대응 및 공통 인터페이스 제공

> ⚠️ views.py는  
> **파싱·업서트·권한 판단 로직을 포함하지 않는다.**

---

### 3.11 admin.py

#### Django Admin 확장 레이어

`accounts.admin`은 **관리자 전용 UX**를 위해 Django Admin을 확장한다.

#### 제공 기능

- CustomUser Admin 커스터마이징
- 전체 사용자 엑셀 다운로드
- 사용자 엑셀 업로드 시작
- Celery 기반 비동기 task 연동

#### 커스텀 Admin URL

- 사용자 전체 엑셀 다운로드
- 엑셀 업로드 전용 페이지
- 업로드 진행률 조회 API

#### Admin 템플릿 연계

- **`admin/accounts/customuser/change_list.html`**
  - object-tools 버튼이 세로로 깨지는 문제 방어
  - 다운로드 / 업로드 버튼 일관 배치

- **`admin/accounts/customuser/upload__excel.html`**
  - 엑셀 업로드 폼
  - 진행률 표시 박스
  - 결과 다운로드 버튼
  - JS polling 계약 포함

---

## 4. 관리자 엑셀 업로드 흐름

accounts 앱의 엑셀 업로드는 **비동기 + 진행률 기반 UX**를 기본으로 한다.

### 전체 플로우

관리자 업로드 요청
 → Celery task 생성 (task_id)
 → 진행률 polling
 → SUCCESS / FAILURE
 → 결과 리포트 다운로드

### 프론트–백엔드 계약

**Template (upload__excel.html)**
-  #uploadProgressBox
- data-task-id
- data-progress-url

****JavaScript (admin_upload_progress.js)**
- polling 주기: 1초
- BFCache 재진입 중복 실행 방지
- 상태 변화에 따른 UI 업데이트

**서버 응답(JSON)**

```json
{
  "percent": 100,
  "status": "SUCCESS",
  "error": "",
  "download_url": "/accounts/upload-result/?task_id=..."
}
```

---

## 5. 사용자 검색 API 계약

accounts 앱의 사용자 검색 API는  
**django_ma 전체 시스템에서 사용하는 “유일한 사용자 검색 기준(SSOT)”**이다.

board / partner / commission / manual 등  
모든 앱의 사용자 검색은 반드시 이 API를 경유해야 한다.

---

### 5.1 API 개요

- 목적:
  - 권한 범위 내 사용자 검색을 **서버에서 강제**
  - 프론트엔드에서 권한 판단 로직 제거
- 특징:
  - 요청자 grade 기반 자동 필터링
  - SubAdminTemp 결합
  - 소속 표시용 `affiliation_display` 제공

---

### 5.2 요청(Request)

#### 기본 Endpoint

GET /accounts/api/search-user/
(legacy URL이 존재하더라도 내부적으로 동일 로직을 사용)

### 5.2 요청 파라미터

| 파라미터 | 필수 | 타입 | 설명 |
|--------|:---:|------|------|
| `q` | ✅ | string | 검색어 (사번 또는 성명) |
| `scope` | ❌ | string | 검색 범위 (`default`, `branch`) |
| `branch` | ❌ | string | 검색 대상 지점 (superuser 전용) |

---

### 5.3 파라미터 동작 규칙

- `q`
  - 부분 검색 지원
  - 사번 / 성명 모두 매칭
- `scope`
  - 기본값: `default`
  - `branch` 사용 시:
    - superuser만 허용
    - 일반 사용자는 서버에서 강제 무시
- `branch`
  - `scope=branch`일 때만 의미 있음
  - superuser 외 사용자는 서버에서 강제 제거

> ⚠️ 권한 검증은 **항상 서버(search_api.py)** 에서 수행한다.

---

### 5.4 권한 기반 검색 제한 정책

서버는 요청자의 grade를 기준으로  
검색 결과를 **강제로 필터링**한다.

| 요청자 grade | 검색 가능 범위 |
|------------|---------------|
| superuser | 전체 사용자 |
| head | 소속 부문 / 지점 |
| leader | 소속 지점 / 팀 |
| 일반 사용자 | 제한된 범위 또는 본인 관련 사용자 |

> 📌 프론트엔드에서는  
> **이 범위를 추론하거나 제한하지 않는다.**

---

### 5.5 응답 형식 (Response)

#### 기본 응답 구조

```json
[
  {
    "id": "A12345",
    "name": "홍길동",
    "branch": "서울지점",
    "rank": "팀장",
    "part": "영업부",
    "team_1": "팀A",
    "team_2": "",
    "team_3": "",
    "affiliation_display": "서울지점 > 팀A"
  }
]
```

### 5.6 응답 필드 정의

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 사번(사용자 식별자) |
| `name` | string | 사용자 성명 |
| `branch` | string | 지점명 |
| `rank` | string | 직급 |
| `part` | string | 부문 |
| `team_1` | string | 팀 정보 (1단계) |
| `team_2` | string | 팀 정보 (2단계) |
| `team_3` | string | 팀 정보 (3단계) |
| `affiliation_display` | string | **소속 표시용 표준 문자열(SSOT)** |

---

### 5.7 affiliation_display 사용 규칙 (중요)

`affiliation_display`는 사용자 소속 정보를  
**UI에서 일관되게 표시하기 위한 단일 기준 필드**이다.

#### 생성 위치

- `accounts.utils.build_affiliation_display`

#### 생성 규칙

- 비어 있는 팀 단계(`team_2`, `team_3` 등)는 자동 제거
- 사람이 읽기 쉬운 문자열로 조합
- 구분자는 `" > "` 사용

#### 예시

서울지점 > 팀A
부산지점 > 영업1팀

> ⚠️ **프론트엔드에서는**
> - `team` 필드를 직접 조합하거나 재가공하지 않는다.
> - 소속 표시는 **반드시 `affiliation_display`를 그대로 사용한다.**

---

### 5.8 프론트엔드 연동 계약

#### 사용 컴포넌트

- **Template**
  - `templates/components/search_user_modal.html`
- **JavaScript**
  - `static/js/common/search_user_modal.js`

#### 프론트엔드 동작 규칙

- 검색 결과 렌더링 시:
  - `name (id)` + `affiliation_display` 형식으로 표시
- 검색 결과 선택 시:
  - 현재 활성 입력 행(activeRow)에 값 자동 입력
  - `userSelected` 커스텀 이벤트 dispatch
- 권한/범위 판단:
  - **프론트엔드에서는 절대 수행하지 않음**
  - 모든 범위 제한은 서버(accounts.search_api)가 담당

---

### 5.9 금지 사항 (중요)

다음 구현은 **절대 허용되지 않는다.**

- 프론트엔드에서 사용자 전체 목록을 조회한 뒤 필터링
- 앱별로 별도의 사용자 검색 API 구현
- `team_*` 필드를 조합하여 소속 문자열 생성
- `affiliation_display`를 프론트엔드에서 재가공
- grade / branch 조건을 JavaScript에서 판단

➡️ 위 행위는 **보안·권한 사고의 직접적인 원인**이 된다.

---

## 6. 핵심 비즈니스 규칙 (요약)

- `inactive` 계정은 **어떤 경우에도 로그인 및 접근 불가**
- 사용자 검색 결과는  
  **항상 요청자의 권한 범위 내에서만 반환**
- 엑셀 업로드 시:
  - 관리자 등급은 강등되지 않도록 보호
  - 보호필드 값은 업로드 데이터에 있어도 무시
  - 정책 위반 데이터는 자동 정정 또는 제외
- 사용자 / 권한 / 소속 정책의 **최종 결정권은 accounts 앱**에 있다.

---

## 7. 결론

`accounts` 앱은 단순 인증 모듈이 아니라  
**django_ma 전체 시스템의 사용자·권한·조직 정보를 지배하는 기준 레이어**이다.

- 다른 앱은 accounts 정책을 신뢰하고
- accounts는 모든 규칙을 서버에서 강제한다.

➡️ **accounts 정책을 우회하는 구현은 허용되지 않는다.**

