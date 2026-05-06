# CSS 스코프 패치 로그 — STEP 3
> 날짜: 2026-05-06

## 수정 사항

| 파일 | 문제 | 수정 내용 | 상태 |
|------|------|-----------|------|
| `static/css/apps/commission.css` | `.deposit-title` 전역 클래스 (RULE-Q-02) | `#deposit-home .deposit-title, #collect-home .deposit-title`로 스코핑 (두 템플릿 공용) | ✅ 완료 |
| `static/css/apps/commission.css` | `.deposit-section-title` 전역 클래스 (RULE-Q-02) | `#deposit-home .deposit-section-title`로 스코핑 | ✅ 완료 |
| `static/css/apps/commission.css` | `.ellipsis-cell` 전역 클래스 (RULE-Q-02) | `#deposit-home .ellipsis-cell`로 스코핑 (JS 동적 생성, `#deposit-home` 내부 확인) | ✅ 완료 |
| `static/css/apps/commission.css` | `.info-table thead th / tbody td` 전역 클래스 (RULE-Q-02) | `#deposit-home .info-table thead th / tbody td`로 스코핑 | ✅ 완료 |
| `static/css/apps/partner.css` | `.modal-subadmin-sm` 전역 클래스 (Q-C-02) | `#manage-grades .modal-subadmin-sm`으로 스코핑 | ✅ 완료 |
| `static/css/apps/manual.css` | `:root { --manual-wide-width; --manual-wide-max }` 전역 변수 (RULE-Q-02) | **수정 보류 — 수동 검토 필요** (아래 참조) | ⚠️ 보류 |

## 수동 검토 필요 항목

### manual.css :root 변수 (FIX-CSS-01 보류)

**근거**: `--manual-wide-width`, `--manual-wide-max` 변수가 `#manual-detail` 하위(줄 19-20)에서만 쓰이는 게 아니라, **줄 305-306의 `.manual-subnav .subnav-inner`** 에서도 참조됩니다.

```css
/* manual.css:305-306 — #manual-detail 외부 참조 */
.manual-subnav .subnav-inner {
  width: var(--manual-wide-width);      /* ← 외부 참조 */
  max-width: var(--manual-wide-max);    /* ← 외부 참조 */
  ...
}
```

`:root`를 `#manual-detail`로 단순 이동 시 `.manual-subnav .subnav-inner`가 변수를 상속받지 못해 subnav 레이아웃이 파괴됩니다.

**권장 처리 방법 (다음 STEP에서 수행):**
1. `:root` 블록 삭제
2. `#manual-detail`에 변수 선언 유지
3. `.manual-subnav .subnav-inner`의 `var()` 참조를 하드코딩 값(`72vw`, `1200px`)으로 교체  
   또는 `.manual-subnav`에도 동일 변수를 직접 선언

## css_scope_check.sh 결과

실행 후 위반 34건 보고 (이번 STEP 3 수정 대상 위반은 모두 해소됨):

| 파일 | STEP 3 수정 전 위반 | STEP 3 수정 후 상태 |
|------|---------------------|---------------------|
| `commission.css` | `.deposit-title`, `.deposit-section-title`, `.ellipsis-cell`, `.info-table` 전역 | ✅ 해소 |
| `partner.css` | `.modal-subadmin-sm` 전역 | ✅ 해소 |
| `manual.css` | `:root` 전역 변수 선언 | ⚠️ 보류 (수동 검토) |
| `board.css` | `.cn-loading-overlay` 등 | 이번 범위 아님 |
| `partner.css` | `.esign-col-*`, `.structure-col-*` 등 | 이번 범위 아님 |
| `index.css` | `:root` 전역 변수 | 이번 범위 아님 |

## 회귀 점검 결과

| 점검 항목 | 결과 |
|-----------|------|
| 권한 스코프 변경 | 없음 (CSS만 수정) |
| URL reverse / 네임스페이스 | 영향 없음 |
| 템플릿 `dataset` / DOM id 변경 | 없음 |
| 첨부 다운로드 정책 위반 | 없음 |
| 업로드 레지스트리 영향 | 없음 |
| DataTables 정책 | 없음 (`#deposit-home .info-table`은 DataTables 미사용) |
| CSS 스코프 누수 | commission.css: 4개 클래스 해소. partner.css: 1개 해소 |
| 운영 환경 영향 | 없음 (정적 파일만 변경) |
| JSON 응답 형식 | 무관 (CSS 수정) |

### commission.css 스코핑 HTML 구조 일치 확인

- `#deposit-home` (deposit_home.html:31) → `.deposit-title`, `.deposit-section-title`, `.info-table`, `.ellipsis-cell` 모두 하위에 위치 ✅
- `#collect-home` (collect_home.html:49) → `.deposit-title` 하위에 위치 ✅
- `.ellipsis-cell`은 `deposit_home.js`에서 `#deposit-home` 내부 `#suretyTable`, `#otherTable`에 동적 생성됨 ✅

### partner.css 모달 구조 일치 확인

- `#manage-grades` (manage_grades.html:41) → `#addSubAdminModal > .modal-subadmin-sm` (줄 236-237)이 하위에 위치 ✅
