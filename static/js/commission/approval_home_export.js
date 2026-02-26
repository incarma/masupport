// django_ma/static/js/commission/approval_home_export.js
(function () {
  "use strict";

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

  // input/select/textarea가 테이블에 있으면 "현재 값"으로 치환
  function normalizeInteractiveCells(tableEl) {
    const clone = tableEl.cloneNode(true);

    // input
    clone.querySelectorAll("input").forEach((inp) => {
      const td = inp.closest("td,th");
      if (!td) return;
      const val =
        inp.type === "checkbox" ? (inp.checked ? "Y" : "N") : safeText(inp.value);
      td.textContent = val;
    });

    // select
    clone.querySelectorAll("select").forEach((sel) => {
      const td = sel.closest("td,th");
      if (!td) return;
      const opt = sel.options && sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex] : null;
      td.textContent = opt ? safeText(opt.textContent) : "";
    });

    // textarea
    clone.querySelectorAll("textarea").forEach((ta) => {
      const td = ta.closest("td,th");
      if (!td) return;
      td.textContent = safeText(ta.value);
    });

    // 버튼류 제거(엑셀에 필요 없음)
    clone.querySelectorAll("button, a.btn").forEach((b) => b.remove());

    return clone;
  }

  function buildExcelHtml(tableEl, title) {
    // Excel 호환 HTML (xls)
    const htmlTable = tableEl.outerHTML;

    return (
      `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>${title}</title>
</head>
<body>
${htmlTable}
</body>
</html>`
    );
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

    // 예: 2026-02_프로사업단_수수료_미결현황_20260226_1320.xls
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

    const selector = btn.getAttribute("data-export-table");
    const baseName = btn.getAttribute("data-export-name") || "export";
    const root = document.getElementById("approval-home") || document;

    const table = document.querySelector(selector);
    if (!table) {
      alert("내보낼 테이블을 찾지 못했습니다: " + selector);
      return;
    }

    // 현재 페이지에 보이는 DOM 그대로(=DB 재조회 없음)
    const normalized = normalizeInteractiveCells(table);
    const title = baseName;
    const html = buildExcelHtml(normalized, title);
    const filename = buildFilename(root, baseName);

    downloadAsXls(filename, html);
  }

  document.addEventListener("click", onClickExport);
})();