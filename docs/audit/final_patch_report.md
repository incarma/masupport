# 보안·품질 개선 최종 보고서

> 작성일: 2026-05-06
> 패치 커밋(HEAD): 14cdb78 (STEP 1 반영 기준)
> 미커밋 변경(STEP 2~4): `git diff HEAD` 7개 파일
> 기준 감사 파일: `security_checklist.md`, `quality_checklist.md`

---

## 1. RULE별 패치 요약

| RULE ID | 내용 | 상태 | 수정 파일 수 | 비고 |
|---------|------|------|------------|------|
| RULE-S-01 | grade 변경 audit 로그 | ✅ | 1 | `partner/views/subadmin.py` — `PARTNER_LEADER_ADD/DELETE` 삽입 |
| RULE-S-02 | 계정 업로드 audit 로그 | ✅ | 1 | `accounts/tasks.py` — `ACCOUNTS_EXCEL_UPLOAD` 삽입 (line 486) |
| RULE-S-03 | @csrf_exempt 제거 | ✅ | 2 | `commission/views/api_upload.py`, `approval.py` |
| RULE-S-04 | ACTION 상수 추가 | ✅ | 1 | `audit/constants.py` — `COMMISSION_EXCEL_UPLOAD` 추가 |
| RULE-S-05 | grade audit 상수 연결 | ⚠️ | 1 | `PARTNER_LEADER_ADD/DELETE` 연결 완료; `ACCOUNTS_GRADE_UPDATE`는 사용처 0건 잔존 |
| RULE-Q-01 | CSRF 공통 유틸 통합 | ⚠️ | 11 | STEP 2 대상 11개 파일 완료; 잔존 10개 파일 미처리 |
| RULE-Q-02 | CSS 스코프 수정 | ⚠️ | 2 | `commission.css` 4개 클래스, `partner.css` 1개 클래스 완료; `manual.css :root` 보류 |
| RULE-Q-03 | JSON 헬퍼 중복 제거 | ✅ | 1 | `api_deposit_impl.py` — `_json_err` SSOT alias 교체 |

---

## 2. 자동 점검 결과

### `python manage.py check` 출력
```
System check identified no issues (0 silenced).
```

### `bash scripts/harness/run_all.sh` 출력 요약 (2026-05-06 11:27:28 / 커밋 14cdb78)

#### [1/4] 보안 위반 탐지

```
❌ [S-B-04] 뷰에서 CustomUser.objects.filter/all() 직접 사용 — 21개 위치
❌ [S-S-05] 상수 'ACCOUNTS_GRADE_UPDATE' 정의됨 → log_action 호출 없음 (0건)
→ ❌ 보안 위반 2건 발견 (모두 이번 패치 범위 외)
```

#### [2/4] 코드 품질 위반 탐지

```
❌ [Q-01] CSRF 토큰 재구현 — 10개 파일 (board/commission/dash/landing/manual/partner)
❌ [Q-02a] :root 전역 변수 — index.css, manual.css
❌ [Q-02b] commission.css 전역 클래스 — .deposit-maxw 등 19개 (collect 관련)
❌ [URL-01] JS 내 URL 하드코딩 — 폴백 패턴 포함 19개 위치
→ 모두 이번 패치 범위 외 또는 보류 항목
```

#### [3/4] Celery task 이름 정합성
```
✅ [OK] beat_schedule 9건 ↔ @shared_task(name=) 15건 — 모두 일치
```

#### [4/4] CSS 스코프 위반 탐지
```
[NG] board.css: .cn-loading-overlay 등 board-scope 외 10건 (이번 범위 아님)
[NG] partner.css: .esign-col-*, .structure-col-* 등 22건 (이번 범위 아님)
[OK] base.css: 금지 패턴 없음
[NG] :root 전역 변수 — index.css, manual.css (이번 범위 아님 / 보류)
→ ❌ CSS 스코프 위반 34건 (STEP 3 대상 5건은 해소됨)
```

---

## 3. PR 체크리스트 결과

### 공통 항목

| 항목 | 결과 | 비고 |
|------|------|------|
| 권한 스코프 변경 여부 | ✅ | 모든 STEP에서 권한 로직 변경 없음 |
| URL namespace 깨짐 여부 | ✅ | URL 변경 없음 |
| 템플릿 `data-*` 속성 변경 여부 | ✅ | `csrf_window.js` 추가만, dataset 속성 변경 없음 |
| 감사 로그 필요 행위 누락 여부 | ⚠️ | PARTNER_LEADER, ACCOUNTS_EXCEL_UPLOAD 추가 완료; `ACCOUNTS_GRADE_UPDATE` 사용처 0건 잔존 |
| JSON 응답 형식 앱 규약 일치 여부 | ✅ | `{"ok": false, "message": ...}` 구조 동일 확인 |

### JS 변경 포함 항목 (STEP 2)

| 항목 | 결과 | 비고 |
|------|------|------|
| AJAX URL이 `dataset`에서 읽는가 (하드코딩 금지) | ✅ | STEP 2 대상 파일 모두 URL 하드코딩 없음; 잔존 URL-01 위반은 범위 외 |
| BFCache 가드 (`root.dataset.inited`) 있는가 | ✅ | STEP 2 수정 대상 파일에서 기존 가드 유지 |
| CSRF는 `common/manage/csrf.js` 사용하는가 | ⚠️ | STEP 2 대상 11개 해소; 잔존 10개 파일 미처리 |

### CSS 변경 포함 항목 (STEP 3)

| 항목 | 결과 | 비고 |
|------|------|------|
| 모든 CSS 규칙이 앱 스코프 루트 하위에 있는가 | ⚠️ | commission.css 4개 + partner.css 1개 해소; manual.css `:root` 보류 |
| `base.css` / `fixes.css` 수정 없는가 | ✅ | run_all.sh `[OK] static/css/base.css: 금지 패턴 없음` 확인 |

---

## 4. 미완료·수동 검토 필요 항목

| 항목 | 사유 | 권고 조치 |
|------|------|---------|
| `ACCOUNTS_GRADE_UPDATE` 미사용 (S-S-05 잔존) | `process_users_excel_task`에서 row별 grade 변경 카운트 추적 미구현 | `accounts/tasks.py`에서 grade 변경된 row 수 집계 후 `log_action(ACTION.ACCOUNTS_GRADE_UPDATE, meta={...})` 추가 |
| `S-B-04` `CustomUser.objects.filter()` 직접 사용 21건 | 검색 목적 외 내부 로직 조회 포함, 광범위한 구조적 문제 | 검색 목적 뷰만 우선 `search_api.py` 경유로 전환, 내부 조회는 별도 판단 |
| RULE-Q-01 잔존 10개 파일 | STEP 2 범위 외 pre-existing 위반 | 별도 배치: `board/common/comment_edit.js`, `detail_inline_update.js`, `inline_update.js`, `commission/approval_excel_upload.js`, `collect_notice.js`, `dash/sales_upload.js`, `landing/index.js`, `manual/create_manual_modal.js`, `manual/_shared.js`, `partner/manage_table.js` |
| `manual.css :root` 전역 변수 (RULE-Q-02 보류) | `:root` 단순 이동 시 `.manual-subnav .subnav-inner`가 변수를 상속받지 못해 레이아웃 파괴 | `:root` 삭제 후 `#manual-detail`에 변수 유지 + `.manual-subnav`의 `var()` 참조를 하드코딩(`72vw`, `1200px`)으로 교체 |
| `commission.css` collect 영역 전역 클래스 19개 (Q-02b 잔존) | STEP 3 범위에서 deposit/info-table만 처리, collect 관련 미처리 | `#collect-home` 스코프 하위로 이동 (`.collect-wide`, `.collect-filter-bar` 등) |
| `board.css` CSS-SCOPE-01 위반 10건 | `#collect-notice` 관련 규칙이 `.board-scope` 외부에 위치 | `#collect-notice` 구조 확인 후 `.board-scope #collect-notice` 또는 별도 CSS 파일로 이동 |
| `partner.css` CSS-SCOPE-02 위반 22건 | `.esign-col-*`, `.structure-col-*` 등이 스코프 루트 외부 | 각 ID 스코프 하위로 이동 (`#esign-confirm`, `#structure-*` 등) |

---

## 5. 배포 시 주의사항

> `DEPLOY_CHECKLIST.md` 기준으로 이번 패치에 해당하는 항목만 기재

| 항목 | 판단 | 비고 |
|------|------|------|
| `collectstatic` 필요 여부 | **필요** | JS 7개 파일, CSS 2개 파일, template 1개 파일 변경 |
| `migrate` 필요 여부 | 불필요 | 모델 변경 없음 |
| Celery 재시작 필요 여부 | **필요** | `accounts/tasks.py` 변경 있음 (STEP 1 — worker 재시작 필요) |
| `.env.prod` 민감정보 확인 | 해당 없음 | 이번 패치에서 환경변수 변경 없음 |
| Celery beat_schedule 이름 일치 | ✅ | run_all.sh [3/4] 통과 확인 |

### 배포 후 3종 계정 검증 항목

| 계정 | 검증 항목 |
|------|---------|
| `superuser` | ① 파트너 중간관리자 추가/삭제 후 audit 로그 생성 확인 ② commission 엑셀 업로드 후 audit 로그 생성 확인 ③ accounts 엑셀 업로드 후 audit 로그 생성 확인 |
| `head` | commission 수수료/approval 엑셀 업로드 시 CSRF 오류 없이 정상 처리 확인 |
| `basic` | commission 업로드 엔드포인트 접근 시 403 정상 반환 확인 |

---

## 6. 패치 대상 파일 전체 목록 (STEP 1~4)

| STEP | 파일 | 변경 유형 | 커밋 여부 |
|------|------|---------|---------|
| S-01 | `partner/views/subadmin.py` | audit log 추가 | ✅ 커밋됨 |
| S-02 | `accounts/tasks.py` | audit log 추가 | ✅ 커밋됨 |
| S-03 | `commission/views/api_upload.py` | @csrf_exempt 제거 | ✅ 커밋됨 |
| S-03 | `commission/views/approval.py` | @csrf_exempt 제거 | ✅ 커밋됨 |
| S-04 | `audit/constants.py` | ACTION 상수 추가 | ✅ 커밋됨 |
| Q-01 | `static/js/commission/collect_home.js` | CSRF SSOT (ESM import) | ⏳ 미커밋 |
| Q-01 | `static/js/board/collateral.js` | CSRF SSOT (window.csrfToken) | ⏳ 미커밋 |
| Q-01 | `static/js/excel_upload.js` | CSRF SSOT (window.csrfToken) | ⏳ 미커밋 |
| Q-01 | `static/js/dash/dash_retention_page.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `static/js/partner/esign_confirm/fetch.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `static/js/partner/esign_confirm/save.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `static/js/partner/esign_confirm/sign.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `static/js/partner/manage_grades/index.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `static/js/utils/file_upload_utils.js` | CSRF SSOT | ✅ 커밋됨 |
| Q-01 | `commission/templates/commission/deposit_home.html` | csrf_window.js 추가 | ⏳ 미커밋 |
| Q-01 | (기타 템플릿 9개) | csrf_window.js 추가 | ✅ 커밋됨 |
| Q-02 | `static/css/apps/commission.css` | CSS 스코프 4개 클래스 | ⏳ 미커밋 |
| Q-02 | `static/css/apps/partner.css` | CSS 스코프 1개 클래스 | ⏳ 미커밋 |
| Q-03 | `commission/views/api_deposit_impl.py` | JSON 헬퍼 SSOT alias | ⏳ 미커밋 |

> ⏳ 미커밋 7개 파일 (`git diff HEAD`): 배포 전 커밋 필요

---

## STEP 6~9 추가 패치 요약

> 갱신일: 2026-05-06
> 최종 커밋: 313c298

### 전체 RULE 최종 상태표

| RULE ID | 내용 | 최종 상태 | 처리 STEP | 잔존 이슈 |
|---------|------|---------|---------|---------|
| RULE-S-01 | grade 변경 audit 로그 | ✅ | STEP 1 | — |
| RULE-S-02 | 계정 업로드 audit 로그 | ✅ | STEP 1 | — |
| RULE-S-03 | @csrf_exempt 제거 | ✅ | STEP 1 | — |
| RULE-S-04 | ACTION 상수 추가 | ✅ | STEP 1 | — |
| RULE-S-05 | grade audit 상수 연결 | ⚠️ | STEP 1 | `ACCOUNTS_GRADE_UPDATE` 사용처 0건 잔존 — row별 grade 변경 집계 미구현 |
| S-E-02 | worktask 다운로드 audit | ✅ | STEP 6 | — |
| S-F-04 | ForcePassword 설정 | ✅ | STEP 6 | `.env.prod`에 `FORCE_PASSWORD_CHANGE_ENABLED=True` 및 SCOPE_* 설정 필요 |
| RULE-Q-01 | CSRF 공통 유틸 (21개) | ⚠️ | STEP 2+7 | `comment_edit.js:67` — false positive (form POST용 hidden input `name` 속성, CSRF 재구현 아님) |
| RULE-Q-02 | CSS 스코프 수정 | ⚠️ | STEP 3+8 | `board.css` 10건, `partner.css` 22건, `index.css :root`, `commission.css` collect 19건 잔존 |
| RULE-Q-03 | JSON 헬퍼 중복 제거 | ✅ | STEP 4 | — |
| Q-F-05 | board/task 이름 혼동 | ✅ | STEP 9 | — |

---

### run_all.sh 최종 결과 (커밋 313c298 / 2026-05-06 20:33:56)

#### [1/4] 보안 위반 탐지

```
❌ [S-B-04] 뷰에서 CustomUser.objects.filter/all() 직접 사용 — 21건
   (이번 패치 범위 외 — 구조적 리팩토링 별도 작업 필요)
❌ [S-S-05] 상수 'ACCOUNTS_GRADE_UPDATE' 정의됨 → log_action 호출 없음 (0건)
   (이번 패치 범위 외 — row별 grade 변경 집계 미구현)
→ ❌ 보안 위반 2건 (모두 이번 패치 범위 외)
```

#### [2/4] 코드 품질 위반 탐지

```
❌ [Q-01] static/js/board/common/comment_edit.js:67: csrfInput.name = "csrfmiddlewaretoken";
   → false positive: form POST용 hidden input name 속성 설정 (CSRF 재구현 아님)
❌ [Q-02a] static/css/apps/index.css:6: :root { (이번 범위 아님)
❌ [Q-02b] commission.css 전역 클래스 19건 — collect 관련 (이번 범위 아님)
❌ [URL-01] JS 내 URL 하드코딩 폴백 패턴 19건 (이번 범위 아님)
→ 이번 패치 범위 외 / false positive
```

#### [3/4] CSS 스코프 위반 탐지

```
[NG] board.css: .cn-loading-overlay 등 10건 (이번 범위 아님)
[NG] partner.css: .esign-col-*, .structure-col-* 등 22건 (이번 범위 아님)
[OK] base.css: 금지 패턴 없음
[NG] index.css: :root (이번 범위 아님)
→ manual.css :root 위반 ✅ 해소됨 (STEP 8)
→ 잔존 CSS 스코프 위반 33건 (모두 이번 범위 아님)
```

#### [4/4] Celery task 이름 정합성

```
beat_schedule 9건 ↔ @shared_task(name=) 15건 — 불일치 0건
  [generate-monthly-worktasks] -> board.tasks.generate_monthly_worktasks
    등록 위치: board/tasks/worktask_tasks.py:37 ✅ (STEP 9 이동 완료)
  [notify-due-worktasks] -> board.tasks.notify_due_worktasks
    등록 위치: board/tasks/worktask_tasks.py:76 ✅ (STEP 9 이동 완료)
[OK] Celery task 이름 점검 통과
```

---

### 잔존 이슈 및 향후 과제

| 항목 | 우선순위 | 설명 | 담당 제안 |
|------|---------|------|---------|
| `ACCOUNTS_GRADE_UPDATE` 미사용 (S-S-05) | 중 | `process_users_excel_task`에서 row별 grade 변경 집계 후 `log_action` 추가 | accounts 담당 |
| `S-B-04` CustomUser 직접 조회 21건 | 저 | 검색 목적 뷰만 `search_api.py` 경유, 내부 조회는 개별 판단 | 구조적 리팩토링 (별도 스프린트) |
| `comment_edit.js:67` false positive | 해소 불필요 | form POST용 hidden input name 속성 — CSRF 재구현 아님, lint 과잉 매칭 | lint 예외처리 or 주석 추가 |
| `commission.css` collect 전역 클래스 19건 | 저 | `#collect-home` 스코프 하위로 이동 | commission 담당 |
| `board.css` CSS-SCOPE-01 위반 10건 | 저 | `#collect-notice` 관련 규칙을 `.board-scope` 내부로 이동 | board 담당 |
| `partner.css` CSS-SCOPE-02 위반 22건 | 저 | `.esign-col-*`, `.structure-col-*` 등을 각 ID 스코프 하위로 이동 | partner 담당 |
| `index.css :root` CSS-SCOPE-04 위반 | 저 | `:root` 변수를 페이지 루트 ID 하위로 이동 | 공통 담당 |

---

### STEP 6~9 변경 파일 전체 목록

| STEP | 파일 | 변경 유형 | 커밋 |
|------|------|---------|------|
| STEP 6 | `board/views/worktasks.py` | worktask_att_download audit log 4개 분기 추가 | 313c298 |
| STEP 6 | `web_ma/settings.py` | FORCE_PASSWORD_CHANGE 주석 추가 | 313c298 |
| STEP 6 | `docs/harness/DEPLOY_CHECKLIST.md` | S-F-04 체크 항목 2건 추가 | 313c298 |
| STEP 7 | `static/js/commission/collect_notice.js` | CSRF SSOT (ESM import) | 313c298 |
| STEP 7 | `static/js/dash/sales_upload.js` | CSRF SSOT (ESM import) | 313c298 |
| STEP 7 | `static/js/board/common/comment_edit.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/board/common/detail_inline_update.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/board/common/inline_update.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/commission/approval_excel_upload.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/landing/index.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/manual/_shared.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/manual/create_manual_modal.js` | CSRF SSOT (window.csrfToken) | 313c298 |
| STEP 7 | `static/js/partner/manage_table.js` | CSRF 헤더 방식 전환 | 313c298 |
| STEP 7 | 템플릿 10개 | csrf_window.js 추가 | 313c298 |
| STEP 8 | `static/css/apps/manual.css` | :root → #manual-detail 스코프 이동 | 313c298 |
| STEP 9 | `board/task.py` | deprecation re-export 래퍼로 교체 | 313c298 |
| STEP 9 | `board/tasks/__init__.py` | worktask_tasks re-export 추가 | 313c298 |
| STEP 9 | `board/tasks/worktask_tasks.py` | 신규 생성 (task.py에서 이동) | 313c298 |
| STEP 9 | `web_ma/celery.py` | 주석 파일명 수정 | 313c298 |

---

### 배포 전 최종 체크리스트

DEPLOY_CHECKLIST.md 기준 이번 패치(STEP 1~9) 전체 해당 항목:

- [ ] `python manage.py check` 통과 ← **확인됨**: `System check identified no issues (0 silenced)`
- [ ] `python manage.py collectstatic --noinput` 실행 (JS 21개 파일, CSS 3개 파일, template 20개 파일 변경)
- [ ] `migrate` 불필요 (모델 변경 없음)
- [ ] Celery worker 재시작 필요 (`accounts/tasks.py`, `board/tasks/worktask_tasks.py` 변경)
- [ ] Celery beat 재시작 권장 (`web_ma/celery.py` 주석 수정, beat_schedule 변경 없음)
- [ ] `.env.prod`에 `FORCE_PASSWORD_CHANGE_ENABLED=True` 확인 → [S-F-04]
- [ ] `FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES`, `SCOPE_PARTS`, `SCOPE_CHANNELS` 중 하나 이상 설정 확인 → [S-F-04]
- [ ] 배포 후 3종 계정(superuser / head / basic) 검증:
  - WorkTask 첨부 다운로드 → audit log 기록 확인 (성공/403/404 각 분기)
  - commission 업로드 페이지 → CSRF 오류 없음 확인
  - partner grade 변경 → audit log 기록 확인
  - manual 에디터 → comment/section/block AJAX CSRF 정상 동작 확인
- [ ] 서버 로그에 `AttributeError(ACTION.XXX)` 없음 확인
