// django_ma/static/js/common/manage/table_ui.js
// ======================================================
// ✅ Common Table UI Utilities
// - DataTables redraw 후 tooltip/title 재적용 공통화
// - partner manage 화면들의 ellipsis 렌더링 중복 제거
// ======================================================

import { escapeAttr, escapeHtml, toStr } from "./text.js";

/** Bootstrap Tooltip + .dt-ellipsis 공통 셀 */
export function renderEllipsisCell(value, extraClass = "") {
  const raw = toStr(value);
  if (!raw) return "";

  const cls = extraClass ? ` ${extraClass}` : "";

  return `
    <span class="dt-ellipsis${cls}"
          data-bs-toggle="tooltip"
          data-bs-placement="top"
          data-bs-title="${escapeAttr(raw)}"
          tabindex="0">${escapeHtml(raw)}</span>
  `;
}

/** 변경후 강조 셀 */
export function renderAfterEllipsisCell(value) {
  return renderEllipsisCell(value, "cell-after");
}

/** Bootstrap tooltip 재초기화 */
export function initBootstrapTooltips(scope) {
  if (!window.bootstrap?.Tooltip) return;

  const root = scope || document;
  root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
    const inst = window.bootstrap.Tooltip.getInstance(el);
    if (inst) inst.dispose();

    new window.bootstrap.Tooltip(el, {
      trigger: "hover focus",
      container: "body",
      boundary: "viewport",
    });
  });
}

/** 일반 table td title 자동 주입 */
export function applyCellTitles(tableEl) {
  if (!tableEl) return;

  tableEl.querySelectorAll("tbody td").forEach((td) => {
    // 편집/액션 요소가 있는 셀은 title 자동 주입 제외
    if (td.querySelector("input, select, textarea, button, a")) return;

    const text = toStr(td.textContent);
    if (text) td.setAttribute("title", text);
    else td.removeAttribute("title");
  });
}