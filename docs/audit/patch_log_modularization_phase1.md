# 모듈화 Phase 1 패치 로그
> 날짜: 2026-05-07
> 기준 리포트: duplicate_detection_report_20260507.md
> 목표: Phase 1 항목 (기능 변화 0 보장 모듈화)

## 완료 항목

| STEP | 항목 ID | 작업 내용 | 변경 파일 | 결과 |
|------|--------|---------|---------|------|
| A-P1-01 | CSRF 중복 | industry_info.js 로컬 `getCSRFToken()` 제거 → `window.csrfToken` 교체, 템플릿에 `csrf_window.js` 추가 | 1 JS + 1 template | ✅ |
| A-P1-02 | board JSON SSOT | `board/views/_json.py` 신설 + `forms.py` / `collateral.py` / `worktasks.py` import 교체 | 1 신설 + 3 수정 | ✅ |
| A-P1-03 | esign 헬퍼 | `esign.py` 로컬 `_ok` / `_err` 제거 → `responses.py` SSOT `json_ok as _ok` / `json_err as _err` 알리아스 import | 1 | ✅ |
| D-P2-05 | URL 하드코딩 | `worktask_list.js` 하드코딩 `/board/worktasks/${id}/` → `_buildActionUrl(boot.dataset.detailUrl, item.id)`, 템플릿에 `data-detail-url` 추가 | 1 JS + 1 template | ✅ |
| E-P2-04 | CSS 스코프 | `manual.css` Section 3 전역 클래스 11개 `#manual-detail` 하위 스코핑 | 1 CSS | ✅ |

## 건너뛴 항목 및 사유

### A-P1-02 부분 제외
| 파일 | 대상 함수 | 사유 |
|------|----------|------|
| `board/views/worktasks.py` | `_err` | JS(`worktask_list.js`, `worktask_detail.js`)가 `result.error` 키 소비 — "message"로 변경 시 프론트 깨짐 |
| `board/views/industry_info.py` | `_json_ok`, `_json_err` | `"data"` 래핑 구조로 응답 포맷 상이 |

### A-P1-03 부분 제외
| 대상 | 사유 |
|------|------|
| `esign.py` `_parse_json` | `responses.py` `parse_json_body`와 API 다름 (tuple 반환 vs dict 반환) — 대체 불가 |

### E-P2-04 부분 제외
| 클래스 | 사유 |
|--------|------|
| `.manual-badge-admin`, `.manual-badge-staff` | `manual_list.html` + `manual_detail.html` 두 페이지에서 공용 |
| Section 2 list 전체 클래스 | `manual_list.html`에 root ID 없음 |
| `sortable-ghost`, `manual-sort-ghost`, `manual-sort-chosen` | Sortable.js가 동적 주입 |
| `manual-fab` | `#manual-detail` DOM 외부 |
| `manual-viewer-img`, `manual-block-modal`, `manual-quill-editor` 등 modal 클래스 | 슈퍼유저 partial이 `#manual-detail` 외부에 include |
| `.navbar .dropdown-menu` | 글로벌 navbar 오버라이드 — 건드리지 않음 |
| `.manual-subnav` | `:root` 변수 참조 이슈 (보류 유지) |

## 회귀 점검 결과

| 항목 | 결과 |
|------|------|
| 권한 스코프 변경 여부 | ✅ 없음 (뷰 데코레이터 미변경) |
| URL reverse / 네임스페이스 | ✅ 이상 없음 (`{% url %}` 추가로 오히려 강화) |
| 템플릿 dataset / DOM id 변경 | ✅ dataset 추가만, 기존 id 변경 없음 |
| 첨부 다운로드 정책 | ✅ 관련 파일 미변경 |
| 업로드 레지스트리/컬럼 탐지 영향 | ✅ 관련 파일 미변경 |
| DataTables 정책 | ✅ 해당 없음 |
| CSS 스코프 누수 신규 발생 | ✅ 없음 (기존 전역 → 스코프 축소만 수행) |
| 운영 환경(Manifest / SECURE_SSL_REDIRECT) 영향 | ✅ 없음 |
| JSON 응답 형식 앱 규약 준수 | ✅ 모든 교체에서 응답 포맷 동일 |
| `python manage.py check` | ✅ 0 issues |
| git diff 변경 금지 파일 포함 여부 | ✅ 없음 |

## 미완료 항목 (Phase 2 이관)

| 항목 ID | 내용 | 이관 사유 |
|--------|------|---------|
| B-P2-01 | commission deposit 서비스 레이어 신설 | 영향 파일 8개+, API 계약 검증 필요 |
| B-P2-02 | commission services/deposit.py 신설 | 대규모 ORM 이전 작업, 회귀 위험 |
| C-P2-03 | partner efficiency 권한 분기 헬퍼 추출 | 권한 로직 동등성 검증 프로세스 필요 |
| B-P3-01 | commission 전체 서비스 레이어 완성 | Phase 3 — 별도 설계 세션 필요 |
| D-P3-02 | board/dash IIFE `readJsonOrThrow` 적용 | ESM 전환 가능성, 템플릿 로드 순서 영향 |
| E-P3-03 | index.css `:root` 정리 | 랜딩 페이지 시각 영향, 별도 확인 필요 |

## 변경 파일 요약

```
board/views/_json.py                     (신설 — board JSON SSOT)
board/views/collateral.py                (로컬 헬퍼 제거 → _json.py import)
board/views/forms.py                     (로컬 헬퍼 제거 → _json.py import)
board/views/worktasks.py                 (_ok 제거 → _json.py import, _err 로컬 유지)
board/templates/board/industry_info.html (csrf_window.js 로드 추가)
board/templates/board/worktask_list.html (data-detail-url 추가)
partner/views/esign.py                   (로컬 _ok/_err 제거 → responses.py import)
static/css/apps/manual.css              (Section 3 클래스 11개 #manual-detail 스코핑)
static/js/board/industry_info.js        (getCSRFToken() 제거 → window.csrfToken)
static/js/board/worktask_list.js        (하드코딩 URL → dataset 참조)
```
