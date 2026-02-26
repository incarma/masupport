// django_ma/static/js/commission/_format.js
// Commission 공용 포맷/escape 유틸 (전역 네임스페이스에 "추가"만 함)

(() => {
  "use strict";

  const root = (window.CommissionCommon = window.CommissionCommon || {});
  const dom = root.dom || null;

  const toText = (v) => (v === null || v === undefined ? "" : String(v));

  function stripCommas(v) {
    return toText(v).replace(/,/g, "").trim();
  }

  function comma(v) {
    const s = toText(v).trim();
    if (!s || s === "-" || s.toLowerCase() === "nan") return "-";

    const cleaned = s.replace(/,/g, "");
    const num = Number(cleaned);
    if (!Number.isFinite(num)) return s;
    return Math.trunc(num).toLocaleString("ko-KR");
  }

  function percent(v) {
    const s = toText(v).trim();
    if (!s || s === "-" || s.toLowerCase() === "nan") return "-";

    const cleaned = s.replace(/,/g, "");
    const num = Number(cleaned);
    if (!Number.isFinite(num)) return s;
    return `${num.toFixed(2)}%`;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  root.format = Object.freeze({
    toText,
    stripCommas,
    comma,
    percent,
    escapeHtml,

    // optional convenience (consumer에서 있으면 사용)
    safeSetText: dom?.safeSetText,
  });
})();