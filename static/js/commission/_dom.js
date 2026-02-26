// django_ma/static/js/commission/_dom.js
// Commission 공용 DOM/문자열 유틸 (전역 네임스페이스에 "추가"만 함)
// - 기능 영향 0: 기존 코드가 이 파일이 없어도 동작하도록 설계(consumer에서 fallback)

(() => {
  "use strict";

  const root = (window.CommissionCommon = window.CommissionCommon || {});

  // querySelector helper
  function $(sel, base = document) {
    return base ? base.querySelector(sel) : null;
  }

  // safe text
  function text(v) {
    return v === null || v === undefined ? "" : String(v).trim();
  }

  // safeSetText: empty/null -> "-"
  function safeSetText(node, value, emptyFallback = "-") {
    if (!node) return;
    const t =
      value === null || value === undefined || String(value).trim() === ""
        ? emptyFallback
        : String(value);
    node.textContent = t;
  }

  root.dom = Object.freeze({
    $,
    text,
    safeSetText,
  });
})();