# CSS manual.css :root 변수 스코핑 로그 — STEP 8
> 날짜: 2026-05-06

## 선택된 전략과 근거

**전략 B — 공통 조상 `#manual-detail`에 변수 선언**

STEP 3에서 "`.manual-subnav .subnav-inner`가 `#manual-detail` 외부에서 참조"로 보류했으나,
`manual/templates/manual/manual_detail.html` 실제 DOM 구조를 확인한 결과:

```
div.container-fluid.my-5
  div#manual-detail          ← 줄 22
    div#manualDetailTop
      div.manual-subnav      ← 줄 39 (INSIDE #manual-detail!)
        div.subnav-inner     ← 변수 참조 대상
```

`.manual-subnav .subnav-inner`는 `#manual-detail` 내부에 위치한다.
CSS 커스텀 프로퍼티는 선언 요소 자신과 모든 자손에 상속되므로,
`:root` 대신 `#manual-detail`에 변수를 선언해도 `.subnav-inner`가 올바르게 상속받는다.
CSS 자기참조(`width: var(--manual-wide-width)` — 자신이 선언한 변수 사용)는 유효한 표준 CSS.

하드코딩(전략 A) 없이 값 일관성을 유지할 수 있으므로 전략 B 선택.

## 수정 내용 (before/after)

### Before (줄 12-23)
```css
:root{
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px; /* 필요 시 조절 */
}

/* wide layout */
#manual-detail{
  width: var(--manual-wide-width);
  max-width: var(--manual-wide-max);
  margin-left: auto;
  margin-right: auto;
}
```

### After (줄 12-20)
```css
/* wide layout — 변수를 #manual-detail 스코프에 선언; .subnav-inner도 동일 DOM 하위에서 상속 */
#manual-detail{
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px;
  width: var(--manual-wide-width);
  max-width: var(--manual-wide-max);
  margin-left: auto;
  margin-right: auto;
}
```

`.manual-subnav .subnav-inner`의 `var()` 참조는 변경 없음 (줄 302-303).

## css_scope_check.sh 결과

```
[NG] [CSS-SCOPE-04] apps/*.css: :root 전역 변수 선언 (앱 루트 ID 하위로 이동 필요)
     static/css/apps/index.css:6: :root {
```

- **manual.css :root 위반: 0건** ✅ (STEP 3 보류 항목 해소)
- 잔존 위반 (이번 범위 아님):
  - `board.css`: `.cn-loading-overlay`, `#collect-notice .cn-*` (CSS-SCOPE-01) — 33건 → 이번 범위 아님
  - `partner.css`: `.esign-col-*`, `.structure-col-*` 등 (CSS-SCOPE-02) — 이번 범위 아님
  - `index.css`: `:root` (CSS-SCOPE-04) — 이번 범위 아님

## 회귀 점검 결과

| 점검 항목 | 결과 |
|-----------|------|
| `#manual-detail` 하위 `var()` 참조 동작 | ✅ 자신에 선언된 변수 — CSS 표준 자기참조 유효 |
| `.manual-subnav .subnav-inner` width/max-width | ✅ DOM 상 `#manual-detail` 내부 → 상속 정상 |
| `:root` 삭제 후 다른 파일 참조 없음 | ✅ `grep -rn "manual-wide-width\|manual-wide-max" static/ templates/` → manual.css 외 없음 |
| 권한 스코프 변경 | 없음 (CSS만 수정) |
| URL reverse / 네임스페이스 | 영향 없음 |
| 템플릿 `dataset` / DOM id 변경 | 없음 |
| 첨부 다운로드 정책 위반 | 없음 |
| 업로드 레지스트리 영향 | 없음 |
| DataTables 정책 | 없음 |
| CSS 스코프 누수 | manual.css :root 위반 해소 — 스코프 누수 없음 |
| 운영 환경 영향 | 없음 (정적 파일만 변경) |
| JSON 응답 형식 | 무관 (CSS 수정) |
