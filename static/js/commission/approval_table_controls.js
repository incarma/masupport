// django_ma/static/js/commission/approval_table_controls.js
// 지점효율지급 초과현황 / 수수료 미결현황 테이블에
// 컬럼 정렬, 키워드 검색, 출력 개수 선택 기능을 추가한다.
(function () {
  "use strict";

  const root = document.getElementById("approval-home");
  if (!root) return;
  if (root.dataset.tblCtrl === "1") return;
  root.dataset.tblCtrl = "1";

  // 금액 컬럼 인덱스 (0-based) — 쉼표 제거 후 숫자 비교
  const TABLES = [
    {
      tableId:      "efficiencyExcessTable",
      searchId:     "effSearch",
      pageSizeId:   "effPageSize",
      countId:      "effCount",
      paginationId: "effPagination",
      moneyCols:    new Set([4]),   // 지급합계
    },
    {
      tableId:      "approvalPendingTable",
      searchId:     "pendSearch",
      pageSizeId:   "pendPageSize",
      countId:      "pendCount",
      paginationId: "pendPagination",
      moneyCols:    new Set([7]),   // 실지급
    },
  ];

  function parseNum(txt) {
    return parseFloat((txt || "").replace(/[,\s]/g, "")) || 0;
  }

  function cellText(tr, colIdx) {
    return (tr.cells[colIdx]?.textContent ?? "").trim();
  }

  function initCtrl(cfg) {
    const table      = document.getElementById(cfg.tableId);
    const searchEl   = document.getElementById(cfg.searchId);
    const pageSizeEl = document.getElementById(cfg.pageSizeId);
    const countEl    = document.getElementById(cfg.countId);
    const paginEl    = document.getElementById(cfg.paginationId);

    if (!table || !searchEl || !pageSizeEl) return;

    const tbody = table.querySelector("tbody");
    const heads = Array.from(table.querySelectorAll("thead th"));

    // 데이터 행만 추출 (colspan 행=빈 안내 행 제외)
    const allRows = Array.from(tbody.querySelectorAll("tr")).filter(
      (tr) => !tr.querySelector("td[colspan]")
    );

    // 헤더에 정렬 클래스 부여
    heads.forEach((th) => th.classList.add("aph-sortable"));

    // 상태
    let sortCol  = -1;
    let sortDir  = "asc";
    let keyword  = "";
    let pageSize = 20;
    let page     = 1;

    // ── 정렬 헤더 표시 업데이트 ──────────────────────────
    function updateSortClasses() {
      heads.forEach((th, i) => {
        th.classList.remove("aph-sort-asc", "aph-sort-desc", "aph-sortable");
        if (i === sortCol) {
          th.classList.add(sortDir === "asc" ? "aph-sort-asc" : "aph-sort-desc");
        } else {
          th.classList.add("aph-sortable");
        }
      });
    }

    // ── 정렬 ──────────────────────────────────────────────
    function sortRows(rows) {
      if (sortCol < 0) return rows;
      const isNum = cfg.moneyCols.has(sortCol);
      return [...rows].sort((a, b) => {
        const va = cellText(a, sortCol);
        const vb = cellText(b, sortCol);
        const cmp = isNum
          ? parseNum(va) - parseNum(vb)
          : va.localeCompare(vb, "ko-KR");
        return sortDir === "asc" ? cmp : -cmp;
      });
    }

    // ── 검색 필터 ─────────────────────────────────────────
    function filterRows(rows) {
      if (!keyword) return rows;
      const kw = keyword.toLowerCase();
      return rows.filter((tr) =>
        Array.from(tr.cells).some((td) =>
          td.textContent.toLowerCase().includes(kw)
        )
      );
    }

    // ── 페이지네이션 UI ───────────────────────────────────
    function renderPagination(cur, total) {
      if (!paginEl) return;
      if (total <= 1) { paginEl.innerHTML = ""; return; }

      const winStart = Math.max(1, cur - 2);
      const winEnd   = Math.min(total, winStart + 4);

      let html = '<nav aria-label="페이지 이동"><ul class="pagination pagination-sm mb-0">';

      html += `<li class="page-item${cur === 1 ? " disabled" : ""}">
        <button class="page-link" data-pg="${cur - 1}" aria-label="이전">&laquo;</button></li>`;

      for (let p = winStart; p <= winEnd; p++) {
        html += `<li class="page-item${p === cur ? " active" : ""}">
          <button class="page-link" data-pg="${p}">${p}</button></li>`;
      }

      html += `<li class="page-item${cur === total ? " disabled" : ""}">
        <button class="page-link" data-pg="${cur + 1}" aria-label="다음">&raquo;</button></li>`;

      html += "</ul></nav>";
      paginEl.innerHTML = html;

      paginEl.querySelectorAll("[data-pg]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const p = parseInt(btn.dataset.pg, 10);
          if (p >= 1 && p <= total) { page = p; render(); }
        });
      });
    }

    // ── 메인 렌더 ─────────────────────────────────────────
    function render() {
      const sorted   = sortRows(allRows);
      const filtered = filterRows(sorted);
      const total    = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      if (page > totalPages) page = totalPages;

      const start    = (page - 1) * pageSize;
      const pageRows = filtered.slice(start, start + pageSize);

      tbody.innerHTML = "";

      if (total === 0) {
        const colspan = heads.length;
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.setAttribute("colspan", colspan);
        td.className = "text-muted py-3 text-center";
        td.textContent = keyword ? "검색 결과 없음" : "데이터 없음";
        tr.appendChild(td);
        tbody.appendChild(tr);
      } else {
        pageRows.forEach((tr) => tbody.appendChild(tr));
      }

      // 카운트 표시
      if (countEl) {
        countEl.textContent = keyword
          ? `검색 ${total}개 / 전체 ${allRows.length}개`
          : `전체 ${total}개`;
      }

      renderPagination(page, totalPages);
    }

    // ── 이벤트 바인딩 ─────────────────────────────────────
    heads.forEach((th, i) => {
      th.addEventListener("click", () => {
        if (sortCol === i) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortCol = i;
          sortDir = "asc";
        }
        page = 1;
        updateSortClasses();
        render();
      });
    });

    searchEl.addEventListener("input", () => {
      keyword = searchEl.value.trim();
      page = 1;
      render();
    });

    pageSizeEl.addEventListener("change", () => {
      pageSize = parseInt(pageSizeEl.value, 10) || 20;
      page = 1;
      render();
    });

    // 초기 렌더 (데이터가 없으면 아무것도 안 함)
    if (allRows.length > 0) {
      render();
    } else {
      // 데이터 없음 행 유지, 컨트롤만 비활성
      if (countEl) countEl.textContent = "전체 0개";
      searchEl.disabled = true;
      pageSizeEl.disabled = true;
    }
  }

  TABLES.forEach(initCtrl);
})();
