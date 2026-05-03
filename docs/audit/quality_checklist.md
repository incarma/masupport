# django_ma 코드 품질 감사 체크리스트
> 생성일: 2026-05-03  
> 점검 브랜치/커밋: develop / 5e7e7f1  
> 점검 범위: 전체 앱 백엔드(Python) + 프론트엔드(JS/CSS)

---

## 요약 대시보드

| 카테고리 | 항목 수 | 🔴 위반 | 🟡 확인필요 | ✅ 준수 | ➖ 해당없음 |
|----------|---------|---------|------------|--------|-----------|
| Q-A. 아키텍처 레이어 준수 | 5 | 0 | 2 | 3 | 0 |
| Q-B. 프론트엔드 공통 유틸 | 6 | 1 | 2 | 2 | 1 |
| Q-C. CSS 스코프 및 구조 | 5 | 1 | 1 | 3 | 0 |
| Q-D. DB 트랜잭션 및 성능 | 6 | 0 | 2 | 4 | 0 |
| Q-E. 예외 처리 품질 | 3 | 0 | 1 | 2 | 0 |
| Q-F. 중복 코드 및 모듈화 | 5 | 1 | 1 | 3 | 0 |
| Q-G. 운영 안정성 | 4 | 0 | 0 | 4 | 0 |
| **합계** | **34** | **3** | **9** | **21** | **1** |

---

## 🔴 개선 필요 항목 상위 목록

| 항목 ID | 설명 | 위반 파일/위치 | 예상 개선 공수 |
|---------|------|--------------|--------------|
| Q-B-01 | CSRF 토큰 구현 12+ 파일에 중복 분산 | static/js/board/collateral.js, states_form.js, support_form.js, dash/dash_retention_page.js, commission/collect_home.js, partner/esign_confirm/*.js 등 | 중 |
| Q-C-05 | manual.css에서 전역 :root 토큰 재정의 | static/css/apps/manual.css:12 | 소 |
| Q-F-01 | commission/views/api_deposit_impl.py에 `_json_err` 로컬 재정의 (utils_json._json_error와 중복) | commission/views/api_deposit_impl.py:63 | 소 |

---

## 상세 점검 결과

### Q-A. 아키텍처 레이어 준수

#### Q-A-01. board 앱 서비스 레이어 위반 여부
- **판정**: ✅ 준수
- **점검 방법**: board/views/posts.py, board/views/tasks.py, board/views/worktasks.py, board/services/ 전체 읽기
- **근거**:
  - `board/views/posts.py`: ORM 직접 호출은 `Post`, `Attachment`, `Comment` 오브젝트 수준에 그침. 리스팅 로직은 `board.services.listing`, 첨부 저장은 `board.services.attachments.save_attachments`, 댓글은 `board.services.comments.handle_comments_actions`, 인라인 업데이트는 `board.services.inline_update.inline_update_common` 경유
  - `board/views/worktasks.py`: 서비스 SSOT 원칙 명문화(주석 포함). `wt_svc.get_user_queryset`, `wt_svc.create_task`, `wt_svc.update_task` 경유. ORM 직접 호출 없음
  - `board/services/worktasks.py`: 소유자 격리 SSOT 함수 집중화 (`get_user_queryset`, `get_user_task`)
- **권장 조치**: 없음

#### Q-A-02. commission 앱 서비스 레이어 위반 여부
- **판정**: 🟡 확인필요
- **점검 방법**: commission/views/api_collect.py, commission/views/api_deposit_impl.py 읽기
- **근거**:
  - `commission/views/api_collect.py`: 비즈니스 로직을 `commission.services.collect` 서비스로 위임하여 규약 준수 (`svc.get_collect_list`, `svc.get_feedbacks` 등)
  - `commission/views/api_deposit_impl.py`: 서비스 레이어 없이 뷰 내에서 `DepositSummary.objects.aggregate`, `DepositSurety.objects.filter` 등 ORM 직접 조회 다수 존재. `commission/services/` 디렉터리에 `collect.py`는 있으나 deposit 도메인은 서비스 레이어 없이 뷰에서 직접 ORM 처리 중
- **위반 상세**: `commission/views/api_deposit_impl.py` 전체가 서비스 레이어 없는 ORM 직접 처리
- **권장 조치**: `commission/services/deposit.py` 서비스 모듈 분리 검토 (기능 변경 없이 레이어만 분리)

#### Q-A-03. partner 앱 서비스/정책 레이어 구성 현황
- **판정**: 🟡 확인필요
- **점검 방법**: partner/views/structure.py, partner/views/rate.py, partner/views/efficiency.py, partner/services/ 읽기
- **근거**:
  - `partner/services/` 디렉터리에 `esign_service.py`, `pdf_service.py` 존재하여 PDF/eSign 도메인은 서비스 분리됨
  - 그러나 `partner/views/structure.py`, `partner/views/rate.py`, `partner/views/efficiency.py`는 뷰 내에서 `StructureChange.objects.filter`, `RateChange.objects.filter` 등 ORM 직접 처리. 전용 서비스 레이어 없음
  - `partner/views/responses.py`에 JSON 헬퍼 분리, `partner/views/utils.py`에 유틸 분리는 긍정적
- **권장 조치**: 구조변경/요율 도메인 서비스 레이어 분리 중기 과제로 검토

#### Q-A-04. JSON 응답 형식 앱별 일관성
- **판정**: ✅ 준수 (설계 의도 확인)
- **점검 방법**: partner/views/responses.py, commission/views/utils_json.py, board/views/worktasks.py, dash/viewmods/utils/json.py 읽기
- **근거**:
  - `partner` 앱: `{"status": "success"}` / `{"status": "error"}` 형식 (`partner/views/responses.py`)
  - `board`, `commission`, `dash`, `manual` 앱: `{"ok": true}` / `{"ok": false}` 형식
  - 앱 간 일관성 부재는 `static/js/common/manage/http.js`의 `isSuccessJson` 함수가 `data?.status === "success"` 분기를 명시적으로 처리하여 partner 전용 JS와의 호환성을 보장하고 있음
  - board/commission/dash 앱의 JS 파일들은 `data.ok`를 직접 확인하거나 `readJsonOrThrow` 사용. 두 규약이 공존하는 것은 설계 의도로 보임
- **권장 조치**: 장기적으로 전사 통합 응답 헬퍼 도입 검토 권장 (현재는 운영 가능한 수준)

#### Q-A-05. 공통 JSON 응답 헬퍼 미사용 중복 구현
- **판정**: ✅ 준수 (앱 내 SSOT 존재)
- **점검 방법**: 앱별 JSON 헬퍼 파일 확인
- **근거**:
  - `commission/views/utils_json.py`: `_json_error`, `_json_ok` — commission 앱 SSOT
  - `partner/views/responses.py`: `json_ok`, `json_err` — partner 앱 SSOT
  - `dash/viewmods/utils/json.py`: `json_err` — dash 앱 SSOT
  - `board/views/industry_info.py`: 인라인 `_ok`, `_err` 헬퍼
  - `board/views/worktasks.py`: 인라인 `_ok`, `_err` 헬퍼 (중복이나 같은 앱 내 일관성 있음)
  - 단, `commission/views/api_deposit_impl.py:63`에 `_json_err`이 별도로 재정의 (utils_json과 중복 — Q-F-01에서 다룸)

---

### Q-B. 프론트엔드 공통 유틸

#### Q-B-01. CSRF 토큰 중복 구현 여부
- **판정**: 🔴 위반
- **점검 방법**: Grep `getCookie|csrfmiddlewaretoken|document.cookie.*csrf` in static/js/
- **근거**:
  - 공통 CSRF 모듈: `static/js/common/manage/csrf.js` (`getCSRFToken()`) 및 `static/js/common/csrf_window.js` 존재
  - 그러나 다음 파일들이 공통 모듈 미사용, 독자적으로 CSRF 구현:
    - `static/js/board/collateral.js:38-43` — 인라인 `getCSRF()` 함수
    - `static/js/board/states_form.js:30-37` — 인라인 `getCsrfToken()` 함수
    - `static/js/board/support_form.js:36-37` — 인라인 구현
    - `static/js/dash/dash_retention_page.js:19-21` — 인라인 구현
    - `static/js/commission/collect_home.js:72-79` — 인라인 구현 (ESM 파일임에도 `getCSRFToken`을 import하지 않음)
    - `static/js/partner/esign_confirm/fetch.js:12-13`, `save.js:25-26`, `sign.js:14-15` — 인라인 구현
    - `static/js/partner/manage_grades/index.js:38-43` — 자체 `getCookie()` 구현
    - `static/js/utils/file_upload_utils.js:51-70` — 자체 `getCookie()` 구현
    - `static/js/excel_upload.js:22-23` — 인라인 구현
  - ESM 모듈 파일들(`collect_home.js` 등)은 `getCSRFToken`을 `../../common/manage/csrf.js`에서 `import` 가능함에도 미사용
- **권장 조치**: ESM 파일은 `import { getCSRFToken } from "../../common/manage/csrf.js"` 통일. IIFE 파일은 `window.csrfToken` 우선 + 공통 fallback 패턴으로 통일

#### Q-B-02. fetch JSON 응답 직접 파싱 (readJsonOrThrow 미사용)
- **판정**: 🟡 확인필요
- **점검 방법**: Grep `.json()` in static/js/, 24개 파일 발견
- **근거**:
  - `static/js/common/manage/http.js`의 `readJsonOrThrow()`가 공통 JSON 파싱 헬퍼로 제공됨
  - Partner 앱 ESM 파일들(`manage_structure/fetch.js`, `manage_structure/save.js`, `manage_rate/fetch.js`, `manage_rate/save.js`, `manage_rate/delete.js`, `manage_efficiency/fetch.js`, `manage_efficiency/delete.js`, `manage_efficiency/confirm_upload.js`, `manage_table.js`)은 `readJsonOrThrow` 정상 사용
  - 그러나 board/commission/dash의 대부분 JS 파일은 직접 `res.json()` 또는 `await res.json()` 사용 (로그인 만료/HTML 응답 방어 없음):
    - `static/js/board/collateral.js`, `static/js/board/industry_info.js`
    - `static/js/dash/dash_retention_page.js`, `static/js/commission/deposit_home.js`
    - `static/js/commission/_net_json.js`
  - IIFE 방식 파일들은 ESM import 불가 특성상 구조적 한계 존재
- **권장 조치**: IIFE 파일용 전역 `window.readJsonOrThrow` 헬퍼 노출 또는 각 파일에 인라인 방어 코드 추가

#### Q-B-03. 로딩 오버레이 중복 구현
- **판정**: ✅ 준수
- **점검 방법**: Grep `loadingOverlay` in static/js/
- **근거**:
  - `static/js/common/manage/loading.js`에 `showLoading()`, `hideLoading()` 공통 유틸 존재
  - `static/js/board/states_form.js`, `static/js/board/support_form.js`, `static/js/partner/manage_structure/dom_refs.js`, `static/js/partner/manage_rate/dom_refs.js`, `static/js/partner/manage_efficiency/dom_refs.js`에서 `#loadingOverlay` DOM 참조
  - Partner ESM 파일들은 `loading.js`에서 `import { showLoading, hideLoading }` 사용
  - board 폼 파일들은 직접 `hidden` 토글하나 규모가 작아 허용 가능 수준
- **권장 조치**: 없음 (현재 수준 적절)

#### Q-B-04. JS 내 URL 하드코딩
- **판정**: 🟡 확인필요
- **점검 방법**: Grep `"/board/|"/commission/|"/partner/|"/dash/|"/manual/` in static/js/
- **근거**:
  - `static/js/board/worktask_list.js:454`: `href="/board/worktasks/${encodeURIComponent(item.id)}/"` — 캘린더 아이템 링크 하드코딩
  - `static/js/board/worktask_list.js:549` (view): `redirect_url=f"/board/worktasks/"` — 서버 뷰에서도 하드코딩
  - `static/js/board/worktask_detail.js:166`: `location.href = redirectUrl || data.redirect_url || "/board/worktasks/"` — fallback URL 하드코딩
  - `static/js/board/collateral.js:541`: `_deleteBase = root.dataset.deleteBaseUrl || "/board/collateral/"` — dataset 우선 후 fallback
  - `static/js/dash/dash_sales_page.js:11`: `"/dash/api/forecast/"` — fallback 하드코딩
  - `static/js/dash/dash_retention_page.js:26-27`: `/dash/api/retention/` 등 fallback
  - `static/js/commission/deposit_home.js:38-41`: 여러 URL fallback 하드코딩
  - `static/js/partner/manage_table.js:95-97`, `static/js/common/part_branch_selector.js:129-131`, `static/js/partner/manage_grades/index.js:94-96` 등에서 fallback URL 하드코딩
  - 대부분 `dataset 우선 || fallback` 패턴이나 dataset이 비면 하드코딩 URL로 동작 → URL 변경 시 JS 파일도 수정 필요
- **권장 조치**: `data-*` dataset만 사용하고 fallback 하드코딩 제거. 템플릿에서 `{% url %}` 태그로 주입 강제화

#### Q-B-05. BFCache 재진입 가드 누락
- **판정**: ✅ 준수
- **점검 방법**: Grep `dataset.inited|window.__.*Inited` in static/js/
- **근거**:
  - `static/js/board/worktask_list.js:39-42`: `boot.dataset.inited === "1"` 가드 + `pageshow` 대응
  - `static/js/board/collateral.js:536-537`: `root.dataset.inited === "1"` 가드
  - `static/js/board/industry_info.js:7-8`: `root.dataset.inited === "1"` 가드
  - `static/js/dash/dash_retention_page.js:13-14, 550`: 가드 + pageshow 초기화
  - `static/js/commission/collect_home.js:32-33`: 가드 (ESM throw 패턴)
  - `static/js/partner/manage_table.js:23-24`, `static/js/partner/manage_efficiency/index.js:56-57`: 가드
  - `static/js/common/manage_boot.js:26-28`: `window.__manageBootInited` 전역 네임스페이스 가드
- **권장 조치**: 없음

#### Q-B-06. IIFE vs ESM 혼용 오류
- **판정**: ➖ 해당없음
- **점검 방법**: JS 파일 패턴 확인
- **근거**: 프로젝트는 두 패턴을 의도적으로 혼용. IIFE는 단순 독립 페이지용, ESM은 partner/board 복잡 모듈용으로 구분됨. 같은 파일 내 혼용 사례 없음. 템플릿에서 `type="module"` 미사용이 보이나 이는 별도 번들러 없는 직접 서빙 구조의 한계이며 현 아키텍처 내 허용 범위로 판단

---

### Q-C. CSS 스코프 및 구조

#### Q-C-01. board.css 스코프 누수
- **판정**: ✅ 준수
- **점검 방법**: static/css/apps/board.css 전체 읽기
- **근거**:
  - 파일 상단 주석: "[No-Leak Policy] 모든 규칙은 .board-scope 하위에서만 적용된다"
  - 확인된 모든 CSS 규칙이 `.board-scope .xxx { }` 형식 준수
  - Design Tokens도 `.board-scope { ... }` 내부에 정의하여 전역 오염 없음
- **권장 조치**: 없음

#### Q-C-02. partner.css 스코프 누수
- **판정**: ✅ 준수
- **점검 방법**: static/css/apps/partner.css 상단 100줄 읽기
- **근거**:
  - 모든 규칙이 `#manage-structure`, `#manage-rate`, `#manage-efficiency`, `#esign-confirm` 등 특정 ID 하위로 스코핑됨
  - 유일한 전역 규칙: `.modal-subadmin-sm { max-width: 35%; }` — 모달 전용이나 전역 노출. 영향은 최소화되어 있으나 엄밀히는 스코핑 아님
- **위반 상세**: partner.css의 `.modal-subadmin-sm`이 전역 노출 (라인 52-54)
- **권장 조치**: `#manage-grades .modal-subadmin-sm` 또는 `[id^="manage-"] .modal-subadmin-sm`으로 스코핑 (영향도 낮아 선택적 개선)

#### Q-C-03. commission/dash/manual.css 스코프 누수
- **판정**: 🔴 위반
- **점검 방법**: static/css/apps/manual.css, commission.css, dash.css 읽기
- **근거**:
  - `static/css/apps/manual.css:12-15`: `:root { --manual-wide-width: 72vw; --manual-wide-max: 1200px; }` — 전역 CSS 변수 재정의. `base.css`의 `:root` 토큰 공간에 manual 전용 변수를 전역으로 추가함 (CSS 변수는 `#manual-detail` 하위로 스코핑 불가하나, 변수 네이밍 충돌 가능성과 전역 오염 원칙 위반)
  - `static/css/apps/commission.css`: `.info-table`, `.ellipsis-cell`, `.deposit-title`, `.deposit-section-title` 등 전역 클래스 정의. `#suretyTable`, `#otherTable` 등 ID 기반 규칙 혼재
  - `static/css/apps/dash.css`: `#dash-sales` ID 하위로 스코핑 — 준수
- **위반 상세**: manual.css의 `:root` 전역 변수 선언(12줄), commission.css의 전역 클래스 `.info-table`, `.ellipsis-cell` 등
- **권장 조치**: manual.css `:root` 변수를 `#manual-detail { --manual-wide-width: 72vw; }` 방식으로 변환. commission.css 전역 클래스를 페이지별 ID 스코프 하위로 이동

#### Q-C-04. base.css 앱 전용 규칙 오염
- **판정**: ✅ 준수
- **점검 방법**: static/css/base.css 읽기 (상단 100줄)
- **근거**:
  - 파일 헤더에 "제외: partner/board/manual/commission 페이지 전용 규칙 → apps/*" 명시
  - 읽은 범위 내 navbar, 전역 토큰, 공통 typography만 포함. 앱 전용 규칙 없음
- **권장 조치**: 없음

#### Q-C-05. fixes.css 남용
- **판정**: 🟡 확인필요
- **점검 방법**: static/css/fixes.css 전체 읽기
- **근거**:
  - 파일은 39줄로 짧고 역할이 명확함: `#mainSheet min-width 0`, `#manage-efficiency #mainTable` 방어, 개인정보 워터마크
  - `#manage-efficiency #mainTable`는 스코핑이 되어 있어 안전
  - 개인정보 워터마크(`.privacy-watermark`)는 전역 적용 의도이므로 fixes.css 위치 적절
  - 파일 헤더에 "정말 전역이어야 하는 최소한의 방어만"이라고 명시되어 있으나, 앞으로 증가 방지 모니터링 필요
- **권장 조치**: 현재 수준은 적절. 향후 fixes.css 항목 추가 시 반드시 코드 리뷰

---

### Q-D. DB 트랜잭션 및 성능

#### Q-D-01. bulk 처리 없이 row-by-row save() 사용
- **판정**: 🟡 확인필요
- **점검 방법**: `board/services/worktasks.py` generate_monthly_tasks 함수 읽기 (offset 395)
- **근거**:
  - `board/services/worktasks.py:409-432` `generate_monthly_tasks` 함수: 반복 원본 템플릿을 loop하며 `WorkTask.objects.create` 개별 호출. 각 루프 내에 `transaction.atomic()` 래핑 및 `WorkTask.objects.filter().exists()` 중복 체크가 있어 N개 템플릿에 대해 N번 DB 트랜잭션 발생
  - 단, 이 함수는 월 1회 Celery 배치에서만 실행되므로 실제 성능 영향 낮음
  - `commission/upload_handlers/deposit.py`, `approval.py`: `bulk_create` 정상 사용
- **위반 상세**: `board/services/worktasks.py:418` — 루프 내 `WorkTask.objects.create` (Celery 배치 한정)
- **권장 조치**: 성능 크리티컬하지 않으나 `bulk_create`로 개선 가능. `(unique_together=(template_task, target_ym))` 제약이 있으면 `ignore_conflicts=True` 옵션 검토

#### Q-D-02. transaction.atomic() 누락
- **판정**: ✅ 준수
- **점검 방법**: Grep `transaction.atomic` 전체 검색
- **근거**:
  - `board/views/posts.py:427, 508`: `with transaction.atomic()` 래핑 (post 생성/수정)
  - `board/views/tasks.py:327, 402`: `with transaction.atomic()` 래핑
  - `board/services/worktasks.py:254, 307, 417`: 생성/수정/배치 모두 atomic
  - `partner/views/structure.py:125, 183, 263, 271`: `@transaction.atomic` 데코레이터
  - `partner/views/rate.py:142, 245`, `partner/views/efficiency.py:325, 471, 514`, `partner/views/grades.py:160`, `partner/views/process_date.py:74, 88, 102`
  - `commission/views/approval.py:153`, `commission/views/api_upload.py:101`
  - `dash/services/agg.py:60`, `dash/services/retention.py:139, 200`
- **권장 조치**: 없음

#### Q-D-03. N+1 쿼리 위험
- **판정**: ✅ 준수
- **점검 방법**: Grep `select_related|prefetch_related` 전체 검색
- **근거**:
  - `board/services/worktasks.py:158-159`: `select_related("category", "owner").prefetch_related("related_users", "attachments")` — 목록 N+1 차단
  - `board/services/worktasks.py:481`: `select_related("owner", "category")` — 알림 배치
  - `partner/views/rate.py:72`, `partner/views/efficiency.py:183, 263`, `partner/views/esign.py:114, 425`
  - `manual/views/block.py:87, 135`, `manual/views/attachment.py:48, 85, 104, 139`
  - `commission/views/downloads.py:86, 128`, `commission/views/pages.py:197, 209`
  - `board/task.py:108`: notify 배치 내 `owner = tasks[0].owner` — 주석에 "select_related로 이미 로드"라고 명시되어 있으나 `get_pending_notify_tasks()`의 `select_related("owner")` 덕분에 실제 N+1 없음
- **권장 조치**: 없음

#### Q-D-04. Celery beat_schedule "task" name 불일치
- **판정**: ✅ 준수
- **점검 방법**: web_ma/celery.py, board/tasks/__init__.py, board/task.py, board/tasks/industry_info.py 읽기
- **근거**:
  - `board.tasks.industry_info.collect_board_industry_news`: celery.py line 60 ↔ industry_info.py의 `@shared_task(name="board.tasks.industry_info.collect_board_industry_news")` 일치
  - `board.tasks.industry_info.cleanup_old_industry_articles`: celery.py line 69 ↔ industry_info.py line 224 일치
  - `board.tasks.generate_monthly_worktasks`: celery.py line 103 ↔ board/task.py line 35 일치
  - `board.tasks.notify_due_worktasks`: celery.py line 110 ↔ board/task.py line 74 일치
  - `dash.tasks.build_sales_aggs_hourly`, `build_sales_forecasts_daily`, `build_sales_forecasts_hourly`: dash/tasks.py 확인 필요하나 tasks.py가 autodiscover 범위에 있음
- **권장 조치**: 없음

#### Q-D-05. board/tasks/ autodiscover 설정
- **판정**: ✅ 준수
- **점검 방법**: web_ma/celery.py 읽기
- **근거**:
  - `celery.py:29`: `app.autodiscover_tasks()` — INSTALLED_APPS 기반
  - `celery.py:32`: `app.autodiscover_tasks(["board.tasks"])` — board.tasks 패키지 명시적 추가. 주석에 "board/tasks/는 패키지 구조이므로 autodiscover_tasks() 단독 탐색 불가"라고 설명 포함
- **권장 조치**: 없음

#### Q-D-06. Celery task 멱등성
- **판정**: 🟡 확인필요
- **점검 방법**: board/tasks/industry_info.py, board/task.py, board/services/worktasks.py 읽기
- **근거**:
  - `collect_board_industry_news`: `_with_task_lock` 함수로 Redis 분산 락 적용 + `update_or_create(normalized_hash=...)` 멱등성 보장 — 준수
  - `cleanup_old_industry_articles`: `_with_task_lock` 적용, 재실행 안전
  - `generate_monthly_worktasks`: 루프 내 `WorkTask.objects.filter(template_task=tmpl, target_ym=target_ym).exists()` 중복 체크로 멱등성 보장 — 준수
  - `notify_due_worktasks`: `is_notified=False` 필터 + 발송 후 `update(is_notified=True)` — 멱등성 보장
  - `CELERY_TASK_ACKS_LATE = True` (settings.py:384): 최소 1회 실행 보장 — 각 태스크의 멱등성 설계 중요
  - dash 태스크들은 `dash/tasks.py` 미읽음 — 추가 확인 필요
- **권장 조치**: dash 태스크 멱등성 별도 확인 권장

---

### Q-E. 예외 처리 품질

#### Q-E-01. 예외 삼키기 패턴 (except: pass)
- **판정**: ✅ 준수
- **점검 방법**: Grep `except.*pass` in *.py
- **근거**:
  - `except.*pass` 패턴: 검색 결과 실제 `pass` 사용 없음. `except Exception: return "-"` 등 변환 반환 패턴만 존재
  - `commission/views/_files.py:59`: "기존 코드의 finally: try delete except pass 패턴을 SSOT화" — 이미 리팩토링됨을 주석에서 확인
  - `commission/upload_utils/_convert.py`, `_readers.py`: 데이터 변환 함수의 예외 처리는 `return default_value` 패턴 — 변환 실패 시 기본값 반환, 적절한 처리
- **권장 조치**: 없음

#### Q-E-02. 사용자 메시지/서버 로그 분리 여부
- **판정**: ✅ 준수
- **점검 방법**: commission/views/api_collect.py, board/views/posts.py 읽기
- **근거**:
  - `commission/views/api_collect.py`: `except Exception: logger.exception("...") → return _json_error("일반 메시지")` 패턴 일관 적용. 서버 에러 상세를 사용자에게 노출하지 않음
  - `board/views/posts.py:116-117`: `_log_post_action` 실패 시 `logger.exception` 사용
  - 대부분의 뷰에서 `logger.exception` → 서버 로그, `return _json_error("일반 메시지")` → 클라이언트 구조 준수
- **권장 조치**: 없음

#### Q-E-03. 뷰의 예외 핸들링 일관성
- **판정**: 🟡 확인필요
- **점검 방법**: Grep `except Exception` in *.py 전체 (80개 이상 발견)
- **근거**:
  - `commission/views/api_deposit_impl.py:27, 34, 46, 56, 59`: 여러 헬퍼 함수에 `except Exception: return "-"` / `return ""` / `return 0` 패턴. 각 함수가 변환 목적으로 사용되므로 의도적이나 일부는 `AttributeError`나 `TypeError`만 잡아도 충분한 경우 있음
  - `partner/views/structure.py:51, 175, 208, 245`: `except Exception as e: logger.error(...)` — 로그는 남기나 상세 에러 타입 구분 없음
  - `partner/views/ratetable.py:367, 374, 382`: 중첩 `except Exception` 블록으로 개별 행 처리 실패 시 계속 진행 — 의도적인 내결함성 설계로 보임
  - 전반적으로 except 범위가 넓어 프로그래밍 오류를 조용히 처리할 가능성 있으나, 모두 로그를 남기고 있어 탐지 가능
- **권장 조치**: 가능한 경우 구체적인 예외 타입 (ValueError, TypeError 등)으로 좁히는 점진적 리팩토링 권장

---

### Q-F. 중복 코드 및 모듈화

#### Q-F-01. 유사한 기능의 중복 구현
- **판정**: 🔴 위반
- **점검 방법**: commission/views/api_deposit_impl.py:63 vs commission/views/utils_json.py 비교
- **근거**:
  - `commission/views/utils_json.py:11-13`: `def _json_error(message, status=400, **extra)` — commission 앱 SSOT
  - `commission/views/api_deposit_impl.py:63-64`: `def _json_err(message, *, status=400)` — 같은 앱 내 재정의. 이름도 다르고 signature도 약간 다름
  - 두 함수의 기능이 동일하나 별도 구현됨. `api_deposit_impl.py`가 `utils_json._json_error`를 import하지 않고 로컬 재정의
- **위반 상세**: `commission/views/api_deposit_impl.py:63-64` — `utils_json._json_error`와 중복
- **권장 조치**: `from commission.views.utils_json import _json_error as _json_err` 로 교체하거나 `_json_error` 직접 사용

#### Q-F-02. views/__init__.py 재export 구조 누락
- **판정**: ✅ 준수
- **점검 방법**: board/views/__init__.py, partner/views/__init__.py, manual/views/__init__.py, commission/views/__init__.py 읽기
- **근거**:
  - `board/views/__init__.py`: 명시적 re-export 구조 (주석 포함, `__all__` 미사용이나 명시적 import로 대체)
  - `partner/views/__init__.py`: 모든 서브모듈에서 명시적 re-export
  - `manual/views/__init__.py`: `__all__` 포함 명시적 re-export
  - `commission/views/__init__.py`: lazy import 헬퍼 방식으로 안전 로딩 (501 stub 패턴)
- **권장 조치**: 없음

#### Q-F-03. 템플릿 URL 하드코딩
- **판정**: ✅ 준수
- **점검 방법**: Grep `href="/board/|href="/commission/|action="/board/"` in templates/ *.html
- **근거**: 검색 결과 0건. 템플릿에서는 `{% url %}` 태그를 사용하고 있음
- **권장 조치**: 없음

#### Q-F-04. 주석 처리된 코드 잔존
- **판정**: ✅ 준수
- **점검 방법**: Grep `# TODO|# FIXME|# HACK` in *.py
- **근거**: 검색 결과 0건. 작업 중 주석(TODO/FIXME)이 남아있지 않음
- **권장 조치**: 없음

#### Q-F-05. 미사용 import / dead code
- **판정**: 🟡 확인필요
- **점검 방법**: board/views/__init__.py 읽기 (noqa 주석 확인)
- **근거**:
  - `board/views/__init__.py:27-34`: `# noqa: F811` 주석으로 중복 import 허용 명시. 서브모듈 `__all__` 미정의 시 안전 보호 목적
  - Python flake8/pylint 기반 전수 검사를 실행한 것은 아니므로 전체 dead code 확인은 제한적
  - `board/task.py`와 `board/tasks/` 패키지가 공존: task.py는 WorkTask 전용, tasks/ 패키지는 industry_info 전용으로 역할 분리됨. 단, `board/tasks/__init__.py`는 industry_info의 함수만 re-export하고 있어 board/task.py의 함수는 별도 autodiscover로 등록됨 — 혼동 가능
- **권장 조치**: flake8/isort 등 정적 분석 도구 CI 통합 권장. `board/task.py` vs `board/tasks/` 이름 혼동 방지를 위해 `board/tasks/worktask_tasks.py`로 이동 검토

---

### Q-G. 운영 안정성

#### Q-G-01. 로거 설정 유효성
- **판정**: ✅ 준수
- **점검 방법**: web_ma/settings.py LOGGING 섹션 읽기
- **근거**:
  - `django.request`: ERROR → `error_file`, `console` — 500 traceback 확보
  - `django.security`, `django.security.csrf`: 별도 로거 설정
  - `accounts.access`, `commission`, `partner`, `dash`, `audit`, `web_ma.celery`, `celery` 앱별 로거 설정
  - `root`: ERROR → `error_file`, `console` — 누락 방지
  - RotatingFileHandler: `maxBytes=10MB`, `backupCount=5-10` — 용량 폭주 방지
- **권장 조치**: 없음

#### Q-G-02. 운영 설정 IS_PROD 게이트 준수
- **판정**: ✅ 준수
- **점검 방법**: web_ma/settings.py 전체 읽기
- **근거**:
  - `IS_PROD = APP_ENV in ("prod", "production") and not DEBUG` (line 113)
  - `if IS_PROD: STATICFILES_STORAGE = "whitenoise..."` (line 307-308)
  - `SESSION_COOKIE_SECURE = IS_PROD`, `CSRF_COOKIE_SECURE = IS_PROD` (line 324-325)
  - `if IS_PROD: SESSION_COOKIE_DOMAIN = ".ma-support.kr"` (line 328-330)
  - `REDIS_URL/CACHES`: IS_PROD 분기
  - Fail-fast: `APP_ENV=prod이면 DEBUG=True 차단` (line 103-104), `dev + runserver + DEBUG=False 차단` (line 106-110)
  - `DEBUG && 운영 DB 감지 차단` (line 228-229)
- **권장 조치**: 없음

#### Q-G-03. collectstatic 자동화 여부
- **판정**: ✅ 준수
- **점검 방법**: settings.py, CLAUDE.md 확인
- **근거**:
  - `IS_PROD`에서 `CompressedManifestStaticFilesStorage` 적용
  - CLAUDE.md에 `bash build.sh` 빌드 명령 및 `collectstatic --noinput` 명시
  - Docker 스택 구성에 gunicorn/nginx 포함으로 운영 배포 자동화 전제
- **권장 조치**: 없음

#### Q-G-04. CELERY_TASK_ACKS_LATE 설정
- **판정**: ✅ 준수
- **점검 방법**: web_ma/settings.py Celery 섹션 읽기
- **근거**:
  - `CELERY_TASK_ACKS_LATE = True` (settings.py:384) — 설정됨
  - `CELERY_TASK_REJECT_ON_WORKER_LOST = True` (line 385) — 워커 장애 시 메시지 반환
  - `CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True` (line 386)
  - 주석에 "중요한 task는 반드시 idempotent 구조여야 한다" 명시 (line 368-369)
  - visibility_timeout: 1시간 설정 (line 376-381)
- **권장 조치**: 없음

---

## 개선 우선순위 로드맵

### 🔴 즉시 개선 (회귀/장애 위험)
없음 — 현재 장애 위험 수준의 즉각 조치 필요 항목 없음

### 🟠 단기 개선 (코드 건강도)

**Q-B-01: CSRF 토큰 중복 구현 통일 (공수: 중)**
- 대상: `board/collateral.js`, `board/states_form.js`, `board/support_form.js`, `dash/dash_retention_page.js`, `commission/collect_home.js`, `partner/esign_confirm/*.js` 등
- 방법: ESM 파일은 `import { getCSRFToken } from "../../common/manage/csrf.js"` 통일. IIFE 파일은 `window.csrfToken` 우선 패턴 유지
- 기대효과: 중복 제거, CSRF 처리 변경 시 단일 위치 수정

**Q-F-01: commission/views/api_deposit_impl.py 로컬 _json_err 제거 (공수: 소)**
- 대상: `commission/views/api_deposit_impl.py:63-64`
- 방법: `from commission.views.utils_json import _json_error` 후 `_json_err = _json_error` alias 또는 직접 교체
- 기대효과: commission 앱 내 JSON 응답 SSOT 일원화

### 🟡 중기 개선 (유지보수성)

**Q-A-02: commission deposit 도메인 서비스 레이어 분리 (공수: 중~대)**
- 대상: `commission/views/api_deposit_impl.py` 전체 ORM 로직
- 방법: `commission/services/deposit.py` 모듈 생성, 뷰는 서비스 호출로 전환
- 기대효과: 아키텍처 일관성, 단위 테스트 용이성

**Q-A-03: partner structure/rate 서비스 레이어 분리 (공수: 대)**
- 대상: `partner/views/structure.py`, `partner/views/rate.py`, `partner/views/efficiency.py`의 ORM 직접 처리
- 방법: `partner/services/structure.py`, `partner/services/rate.py` 등 서비스 분리
- 기대효과: 레이어 구조 완성, 뷰 경량화

**Q-C-03: manual.css :root 전역 변수 → 스코프 변수로 변환 (공수: 소)**
- 대상: `static/css/apps/manual.css:12-15`
- 방법: `:root { ... }` → `#manual-detail { ... }` 변환 (단, CSS 변수 스코프 제약 고려)
- 기대효과: 전역 네임스페이스 오염 감소

**Q-B-04: JS URL fallback 하드코딩 제거 (공수: 중)**
- 대상: `board/worktask_list.js:454`, `board/worktask_detail.js:166`, `dash/dash_sales_page.js:11`, `commission/deposit_home.js:38-41` 등
- 방법: 템플릿에서 `{% url %}` 태그로 dataset 주입 강제화, fallback URL 제거
- 기대효과: URL 변경 시 JS 파일 수정 불필요

### 🟢 선택적 개선 (코드 정리)

**Q-E-03: 광범위한 except Exception 좁히기 (공수: 대)**
- 대상: `commission/views/api_deposit_impl.py`, `partner/views/structure.py`, `partner/views/ratetable.py`
- 방법: 구체적 예외 타입 (ValueError, AttributeError 등) 으로 좁히기
- 기대효과: 프로그래밍 오류 조기 발견

**Q-D-01: generate_monthly_tasks bulk_create 전환 (공수: 소)**
- 대상: `board/services/worktasks.py:409-432`
- 방법: 루프 대신 bulk_create + ignore_conflicts 전환 (Celery 배치 성능 최적화)
- 기대효과: 월별 배치 실행 DB 부하 감소 (현실적 영향 낮음)

**Q-F-05: board/task.py → board/tasks/worktask_tasks.py 이동 (공수: 소)**
- 대상: `board/task.py` 파일
- 방법: `board/tasks/` 패키지로 이동, celery.py autodiscover 경로 조정
- 기대효과: 패키지 구조 일관성 (`board/tasks/` 하위 단일화)
