// django_ma/static/js/commission/approval_home_export.js
(function () {
  "use strict";

  const C = window.CommissionCommon || {};
  const Dom = C.dom || null;
  const text = Dom?.text || ((v) => (v === null || v === undefined ? "" : String(v)).trim());

  function pad2(n) {
    n = String(n || "");
    return n.length === 1 ? "0" + n : n;
  }

  function nowStamp() {
    const d = new Date();
    return (
      d.getFullYear() +
      pad2(d.getMonth() + 1) +
      pad2(d.getDate()) +
      "_" +
      pad2(d.getHours()) +
      pad2(d.getMinutes())
    );
  }

  function safeText(s) {
    return String(s || "").replace(/\s+/g, " ").trim();
  }

  function normalizeInteractiveCells(tableEl) {
    const clone = tableEl.cloneNode(true);

    clone.querySelectorAll("input").forEach((inp) => {
      const td = inp.closest("td,th");
      if (!td) return;
      const val =
        inp.type === "checkbox" ? (inp.checked ? "Y" : "N") : safeText(inp.value);
      td.textContent = val;
    });

    clone.querySelectorAll("select").forEach((sel) => {
      const td = sel.closest("td,th");
      if (!td) return;
      const opt =
        sel.options && sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex] : null;
      td.textContent = opt ? safeText(opt.textContent) : "";
    });

    clone.querySelectorAll("textarea").forEach((ta) => {
      const td = ta.closest("td,th");
      if (!td) return;
      td.textContent = safeText(ta.value);
    });

    clone.querySelectorAll("button, a.btn").forEach((b) => b.remove());

    return clone;
  }

  function buildExcelHtml(tableEl, title) {
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>${title}</title>
</head>
<body>
${tableEl.outerHTML}
</body>
</html>`;
  }

  function downloadAsXls(filename, contentHtml) {
    const blob = new Blob([contentHtml], {
      type: "application/vnd.ms-excel;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function buildFilename(root, baseName) {
    const ym = safeText(root?.dataset?.selectedYm);
    const part = safeText(root?.dataset?.selectedPart);
    const stamp = nowStamp();

    const pieces = [];
    if (ym) pieces.push(ym);
    if (part) pieces.push(part);
    pieces.push(baseName);
    pieces.push(stamp);

    return pieces.join("_") + ".xls";
  }

  function onClickExport(e) {
    const btn = e.target.closest("[data-export-table]");
    if (!btn) return;

    const selector = text(btn.getAttribute("data-export-table"));
    const baseName = text(btn.getAttribute("data-export-name")) || "export";
    const root = document.getElementById("approval-home") || document;

    const table = selector ? document.querySelector(selector) : null;
    if (!table) {
      alert("내보낼 테이블을 찾지 못했습니다: " + selector);
      return;
    }

    const normalized = normalizeInteractiveCells(table);
    const html = buildExcelHtml(normalized, baseName);
    const filename = buildFilename(root, baseName);

    downloadAsXls(filename, html);
  }

  document.addEventListener("click", onClickExport);
})();