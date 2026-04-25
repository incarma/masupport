import { getCSRFToken } from "../common/manage/csrf.js";
import { readJsonOrThrow, isSuccessJson } from "../common/manage/http.js";

/**
 * django_ma/static/js/partner/manage_table.js
 * ============================================================
 * ✅ Table Management (Final Refactor)
 * ------------------------------------------------------------
 * - mainTable: DataTables 사용 금지(정책 유지)
 * - rateUserTable: DataTables 있으면 사용, 없으면 plain fallback
 * - 컬럼폭 고정 + 말줄임 + hover title:
 *   · CSS(table-layout:fixed + ellipsis)
 *   · JS(셀 title 자동 주입) + DataTables draw마다 재적용
 * - superuser: 검색 버튼으로 조회
 * - head: 자동조회
 * - 안전장치: root 1회 초기화, $ is not defined 차단
 * ============================================================
 */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("manage-table");
  if (!root) return;
  if (root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  /* ==========================================================
   * 0) DOM Refs / State
   * ========================================================== */
  const els = {
    part: document.getElementById("partSelect"),
    branch: document.getElementById("branchSelect"),
    btnSearch: document.getElementById("btnSearch"),

    btnToggleEdit: document.getElementById("btnToggleEdit"),
    btnAdd: document.getElementById("btnAddRow"),
    btnSave: document.getElementById("btnSave"),
    btnReset: document.getElementById("btnReset"),

    btnDownloadExcel: document.getElementById("btnDownloadExcel"),
    btnUploadExcel: document.getElementById("btnUploadExcel"),
    btnDownloadTemplate: document.getElementById("btnDownloadTemplate"),
    inputExcel: document.getElementById("rateExcelInput"),

    tableBody: document.getElementById("tableBody"),
    overlay: document.getElementById("loadingOverlay"),
    overlayText: document.querySelector("#loadingOverlay .loading-text"),

    rateUserTable: document.getElementById("rateUserTable"),
  };

  const userGrade = String(root.dataset.userGrade || "").trim();
  const userBranch = String(root.dataset.branch || "").trim();

  let editMode = false;
  let dtInstance = null;

  /* ==========================================================
   * 1) Helpers (UI / Env / Security)
   * ========================================================== */
  function isSuper() {
    return userGrade === "superuser";
  }
  function isMain() {
    return userGrade === "head";
  }

  function alertBox(msg) {
    window.alert(msg);
  }

  function showLoading(msg = "처리 중...") {
    if (!els.overlay) return;
    if (els.overlayText) els.overlayText.textContent = msg;
    els.overlay.hidden = false;
  }
  function hideLoading() {
    if (!els.overlay) return;
    els.overlay.hidden = true;
  }

  function enc(v) {
    return encodeURIComponent(v ?? "");
  }

  function urls() {
    const tableFetch = String(root.dataset.fetchUrl || "").trim();
    const tableSave = String(root.dataset.saveUrl || "").trim();
    const rateTemplate =
      String(root.dataset.rateTemplateUrl || "").trim() ||
      "/static/excel/%EC%96%91%EC%8B%9D_%ED%85%8C%EC%9D%B4%EB%B8%94%EA%B4%80%EB%A6%AC.xlsx";

    return {
      tableFetch,
      tableSave,
      rateList: String(root.dataset.rateListUrl || "/partner/ajax/rate-userlist/").trim(),
      rateExcel: String(root.dataset.rateExcelUrl || "/partner/ajax/rate-userlist-excel/").trim(),
      rateUpload: String(root.dataset.rateUploadUrl || "/partner/ajax/rate-userlist-upload/").trim(),
      rateTemplate,
    };
  }

  /* ---------------- jQuery / DataTables Safe Access ---------------- */
  function hasJQ() {
    return typeof window.jQuery === "function" && typeof window.$ === "function";
  }
  function hasDT() {
    return hasJQ() && !!(window.$.fn && window.$.fn.DataTable);
  }

  /* ---------------- HTML Escape ---------------- */
  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  /* ==========================================================
   * 2) UX: Ellipsis + Hover Title
   * - DataTables는 DOM을 계속 갈아끼우므로 draw마다 재적용 필요
   * ========================================================== */
  function applyCellTitles(tableEl) {
    if (!tableEl) return;

    const cells = tableEl.querySelectorAll("tbody td");
    cells.forEach((td) => {
      // 편집요소가 있으면 title 적용은 스킵(의도치 않은 UX 방지)
      if (td.querySelector("input, select, textarea, button, a")) return;

      const text = (td.textContent || "").trim();
      if (!text) {
        td.removeAttribute("title");
        return;
      }
      if (td.getAttribute("title") !== text) td.setAttribute("title", text);
    });
  }

  /* ==========================================================
   * 3) Policy: mainTable DataTables 차단
   * ========================================================== */
  function blockDTOnlyForMainTable() {
    if (!hasDT()) return;

    const $ = window.$;
    $.fn.dataTable.ext.errMode = "none";

    if ($.fn.DataTable.__mainTableBlocked) return;

    const original = $.fn.DataTable;
    function patchedDataTable(...args) {
      const id = this?.attr?.("id");
      if (id === "mainTable") {
        console.warn("[manage_table] DataTables blocked for #mainTable");
        return this;
      }
      return original.apply(this, args);
    }
    patchedDataTable.__mainTableBlocked = true;
    $.fn.DataTable = patchedDataTable;
  }

  /* ==========================================================
   * 4) Branch Resolve (Superuser UI vs head fixed)
   * ========================================================== */
  function resolveBranchFromUI() {
    if (isSuper()) return String(els.branch?.value || "").trim();
    if (isMain()) return userBranch;
    return "";
  }

  /* ==========================================================
   * 5) Main Boot
   * ========================================================== */
  blockDTOnlyForMainTable();
  bindGlobalClickDelegation();
  bindTopButtons();
  bindRateCellGuards();

  // head: 자동조회
  if (isMain() && userBranch) {
    setTimeout(() => {
      const b = resolveBranchFromUI();
      if (!b) return;
      fetchTables(b);
      loadRateUserTable(b);
    }, 250);
  }

  // superuser: 검색 버튼으로 조회
  if (isSuper() && els.btnSearch) {
    els.btnSearch.addEventListener("click", () => {
      const b = resolveBranchFromUI();
      if (!b) return alertBox("지점을 선택해주세요.");
      fetchTables(b);
      loadRateUserTable(b);
    });
  }

  /* ==========================================================
   * 6) Top Buttons (Edit/Add/Save/Reset + Excel)
   * ========================================================== */
  function bindTopButtons() {
    // 6-1) 수정 모드 토글
    els.btnToggleEdit?.addEventListener("click", () => {
      editMode = !editMode;
      els.btnToggleEdit.textContent = editMode ? "읽기 모드 전환" : "수정 모드 전환";

      document.querySelectorAll("#mainTable .editable").forEach((td) => {
        td.contentEditable = String(editMode);
      });

      document
        .querySelectorAll("#mainTable .btnDeleteRow, #mainTable .btnMoveUp, #mainTable .btnMoveDown")
        .forEach((btn) => {
          const isDelete = btn.classList.contains("btnDeleteRow");
          btn.disabled = !editMode;
        });
    });

    // 6-2) 행 추가
    els.btnAdd?.addEventListener("click", () => {
      const b = resolveBranchFromUI();
      if (!b) return alertBox("지점을 먼저 선택해주세요.");

      const order = (els.tableBody?.querySelectorAll("tr.data-row")?.length || 0) + 1;
      const tr = document.createElement("tr");
      tr.className = "data-row";
      tr.dataset.order = String(order);
      tr.innerHTML = `
        <td class="order-cell">${order}</td>
        <td>${escapeHtml(b)}</td>
        <td class="editable" contenteditable="${editMode}"></td>
        <td class="editable rate-cell" contenteditable="${editMode}">%</td>
        <td>
          <button class="btn btn-outline-secondary btn-sm btnMoveUp" ${!editMode ? "disabled" : ""}>▲</button>
          <button class="btn btn-outline-secondary btn-sm btnMoveDown" ${!editMode ? "disabled" : ""}>▼</button>
        </td>
        <td>
          <button class="btn btn-sm btn-danger btnDeleteRow" ${!editMode ? "disabled" : ""}>삭제</button>
        </td>
      `;
      els.tableBody?.appendChild(tr);
      updateOrderNumbers();
    });

    // 6-3) 저장
    els.btnSave?.addEventListener("click", async () => {
      const b = resolveBranchFromUI();
      if (!b) return alertBox("지점 정보가 없습니다.");

      const u = urls();
      if (!u.tableSave) return alertBox("saveUrl이 설정되지 않았습니다.(data-save-url)");

      const rows = collectMainRows().filter((r) => r.table && r.rate && r.rate !== "%");
      if (rows.length === 0) return alertBox("저장할 데이터가 없습니다.");

      showLoading("저장 중...");
      try {
        const res = await fetch(u.tableSave, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({ branch: b, rows }),
        });

        const data = await readJsonOrThrow(res, "저장 실패");
        if (isSuccessJson(data)) {
          alertBox(`저장 완료 (${rows.length}건)`);
          await fetchTables(b);
        } else {
          throw new Error(data?.message || "저장 실패");
        }
      } catch (err) {
        alertBox("저장 중 오류 발생: " + (err?.message || err));
      } finally {
        hideLoading();
      }
    });

    // 6-4) 초기화(재조회)
    els.btnReset?.addEventListener("click", async () => {
      const b = resolveBranchFromUI();
      if (!b) return alertBox("지점을 먼저 선택해주세요.");
      if (!confirm("테이블을 초기화(재조회)하시겠습니까?")) return;
      await fetchTables(b);
    });

    // 6-5) 엑셀 다운로드
    els.btnDownloadExcel?.addEventListener("click", () => {
      const b = resolveBranchFromUI();
      if (!b) return alertBox("지점을 먼저 선택해주세요.");
      const u = urls();
      window.location.href = `${u.rateExcel}?branch=${enc(b)}`;
    });

    // 6-6) 양식 다운로드(정적)
    els.btnDownloadTemplate?.addEventListener("click", () => {
      const u = urls();
      if (!u.rateTemplate) return alertBox("양식 파일 경로가 설정되지 않았습니다.");
      const b = resolveBranchFromUI();
      window.location.href = b ? `${u.rateTemplate}?branch=${enc(b)}` : u.rateTemplate;
    });

    // 6-7) 엑셀 업로드
    if (els.btnUploadExcel && els.inputExcel) {
      els.btnUploadExcel.addEventListener("click", () => els.inputExcel.click());

      els.inputExcel.addEventListener("change", async (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;

        if (!confirm("선택한 엑셀의 '업로드' 시트를 기준으로 요율현황을 갱신하시겠습니까?")) {
          els.inputExcel.value = "";
          return;
        }

        const b = resolveBranchFromUI();
        if (!b) {
          els.inputExcel.value = "";
          return alertBox("지점을 먼저 선택해주세요.");
        }

        const u = urls();
        const formData = new FormData();
        formData.append("excel_file", file);
        formData.append("branch", b);
        formData.append("csrfmiddlewaretoken", getCSRFToken());

        showLoading("업로드 중...");
        try {
          const res = await fetch(u.rateUpload, { method: "POST", body: formData });
          const data = await readJsonOrThrow(res, "업로드 실패");

          if (isSuccessJson(data)) {
            alertBox(data.message || "업로드 완료");
            await loadRateUserTable(b);
          } else {
            throw new Error(data?.message || "업로드 실패");
          }
        } catch (err) {
          alertBox("엑셀 업로드 중 오류 발생: " + (err?.message || err));
        } finally {
          hideLoading();
          els.inputExcel.value = "";
        }
      });
    }
  }

  /* ==========================================================
   * 7) mainTable: collect / render / ordering
   * ========================================================== */
  function collectMainRows() {
    const rows = Array.from(els.tableBody?.querySelectorAll("tr.data-row") || []);
    return rows.map((tr) => {
      const tds = tr.querySelectorAll("td");
      return {
        order: parseInt(tr.dataset.order || "0", 10) || 0,
        branch: (tds[1]?.textContent || "").trim(),
        table: (tds[2]?.textContent || "").trim(),
        rate: (tds[3]?.textContent || "").trim(),
      };
    });
  }

  function renderMainTable(rows = [], branch) {
    if (!els.tableBody) return;

    els.tableBody.innerHTML = "";
    const safeRows = rows && rows.length ? rows : [{ order: 1, branch, table: "", rate: "" }];

    safeRows.forEach((r, idx) => {
      const order = r.order || idx + 1;
      const tr = document.createElement("tr");
      tr.className = "data-row";
      tr.dataset.order = String(order);

      tr.innerHTML = `
        <td class="order-cell">${order}</td>
        <td>${escapeHtml((r.branch || branch || "").trim())}</td>
        <td class="editable" contenteditable="${editMode}">${escapeHtml(r.table || "")}</td>
        <td class="editable rate-cell" contenteditable="${editMode}">${escapeHtml(r.rate || "")}</td>
        <td>
          <button class="btn btn-outline-secondary btn-sm btnMoveUp" ${!editMode ? "disabled" : ""}>▲</button>
          <button class="btn btn-outline-secondary btn-sm btnMoveDown" ${!editMode ? "disabled" : ""}>▼</button>
        </td>
        <td>
          <button class="btn btn-sm btn-danger btnDeleteRow" ${!editMode ? "disabled" : ""}>삭제</button>
        </td>
      `;
      els.tableBody.appendChild(tr);
    });

    updateOrderNumbers();
  }

  function updateOrderNumbers() {
    const rows = els.tableBody?.querySelectorAll("tr.data-row") || [];
    rows.forEach((row, idx) => {
      row.dataset.order = String(idx + 1);
      const cell = row.querySelector(".order-cell");
      if (cell) cell.textContent = String(idx + 1);
    });
  }

  /* ==========================================================
   * 8) Delegation: ▲/▼/삭제 (mainTable)
   * ========================================================== */
  function bindGlobalClickDelegation() {
    document.addEventListener("click", (e) => {
      if (!editMode) return;

      const upBtn = e.target.closest(".btnMoveUp");
      const downBtn = e.target.closest(".btnMoveDown");
      const delBtn = e.target.closest(".btnDeleteRow");

      if (upBtn) {
        const row = upBtn.closest("tr");
        const prev = row?.previousElementSibling;
        if (row && prev) row.parentNode.insertBefore(row, prev);
        updateOrderNumbers();
        return;
      }

      if (downBtn) {
        const row = downBtn.closest("tr");
        const next = row?.nextElementSibling;
        if (row && next) next.after(row);
        updateOrderNumbers();
        return;
      }

      if (delBtn) {
        if (!confirm("해당 행을 삭제하시겠습니까?")) return;
        delBtn.closest("tr")?.remove();
        updateOrderNumbers();
      }
    });
  }

  /* ==========================================================
   * 9) rate-cell 입력 가드 (0~100 + % 유지)
   * ========================================================== */
  function bindRateCellGuards() {
    if (!els.tableBody) return;

    els.tableBody.addEventListener(
      "focus",
      (e) => {
        const cell = e.target.closest(".rate-cell");
        if (!cell || !editMode) return;

        const val = cell.textContent.trim();
        if (!val) {
          cell.textContent = "%";
          placeCaretAtStart(cell);
        } else if (!val.endsWith("%")) {
          cell.textContent = val + "%";
          placeCaretBeforePercent(cell);
        }
      },
      true
    );

    els.tableBody.addEventListener("input", (e) => {
      const cell = e.target.closest(".rate-cell");
      if (!cell || !editMode) return;

      let num = cell.textContent.replace(/[^0-9]/g, "");
      if (num === "") num = "0";

      let intVal = parseInt(num, 10);
      if (isNaN(intVal)) intVal = 0;
      if (intVal > 100) intVal = 100;

      cell.textContent = intVal + "%";
      placeCaretBeforePercent(cell);
    });

    els.tableBody.addEventListener(
      "blur",
      (e) => {
        const cell = e.target.closest(".rate-cell");
        if (!cell || !editMode) return;

        const val = cell.textContent.trim();
        if (val === "%") {
          cell.textContent = "";
          return;
        }

        if (!val.endsWith("%")) {
          let n = parseInt(val.replace(/[^0-9]/g, ""), 10);
          if (isNaN(n) || n < 0) n = 0;
          if (n > 100) n = 100;
          cell.textContent = n + "%";
        }
      },
      true
    );
  }

  function placeCaretBeforePercent(el) {
    const sel = window.getSelection();
    const range = document.createRange();
    const textNode = el.firstChild;
    if (!textNode) return;
    const pos = Math.max(0, textNode.length - 1);
    range.setStart(textNode, pos);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function placeCaretAtStart(el) {
    const sel = window.getSelection();
    const range = document.createRange();
    const textNode = el.firstChild;
    if (!textNode) return;
    range.setStart(textNode, 0);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  /* ==========================================================
   * 10) Fetch TableSetting (mainTable)
   * ========================================================== */
  async function fetchTables(branch) {
    if (!branch) return;

    const u = urls();
    if (!u.tableFetch) return alertBox("fetchUrl이 설정되지 않았습니다.(data-fetch-url)");

    showLoading("데이터 불러오는 중...");
    try {
      const res = await fetch(`${u.tableFetch}?branch=${enc(branch)}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await readJsonOrThrow(res, "테이블 조회 실패");

      const rows = data?.status === "success" ? (data.rows || []) : [];
      renderMainTable(rows, branch);
    } catch (err) {
      alertBox("데이터 조회 오류: " + (err?.message || err));
      renderMainTable([], branch);
    } finally {
      hideLoading();
    }
  }

  /* ==========================================================
   * 11) RateUserList (rateUserTable)
   *  - DataTables 있으면 DT 렌더링 + draw마다 title 적용
   *  - 없으면 plain 렌더링 + title 적용
   * ========================================================== */
  async function loadRateUserTable(branch) {
    if (!branch || !els.rateUserTable) return;

    let payload;
    try {
      const u = urls();
      const res = await fetch(`${u.rateList}?branch=${enc(branch)}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      payload = await readJsonOrThrow(res, "요율현황 조회 실패");
    } catch (err) {
      console.error("요율현황 로드 실패(fetch)", err);
      renderRateUserPlain([]);
      return;
    }

    const rows = Array.isArray(payload?.data) ? payload.data : [];

    // 11-1) DataTables 렌더
    if (hasDT()) {
      const $ = window.$;

      try {
        if (dtInstance && typeof dtInstance.destroy === "function") {
          dtInstance.destroy(true);
          dtInstance = null;
        }
      } catch (_) {}

      dtInstance = $("#rateUserTable").DataTable({
        destroy: true,
        autoWidth: false, // ✅ colgroup 폭 유지 핵심
        searching: true,
        paging: true,
        pageLength: 10,
        lengthChange: true,
        order: [[0, "asc"]],
        info: false,
        language: {
          lengthMenu: "_MENU_개씩 보기",
          search: "검색:",
          zeroRecords: "데이터가 없습니다.",
          infoEmpty: "데이터 없음",
          paginate: { next: "다음", previous: "이전" },
        },
      });

      // draw마다 title 재적용 (검색/페이징/정렬 모두 포함)
      dtInstance.off("draw.manage_table_titles");
      dtInstance.on("draw.manage_table_titles", () => applyCellTitles(els.rateUserTable));

      dtInstance.clear();
      rows.forEach((u) => {
        dtInstance.row.add([
          u.branch || "",
          u.team_a || "",
          u.team_b || "",
          u.team_c || "",
          u.name || "",
          u.id || "",
          u.non_life_table || "",
          u.life_table || "",
        ]);
      });

      dtInstance.draw();

      // 초기 1회 보장
      applyCellTitles(els.rateUserTable);
      return;
    }

    // 11-2) Plain 렌더
    renderRateUserPlain(rows);
  }

  function renderRateUserPlain(rows) {
    const tbody = els.rateUserTable?.querySelector("tbody");
    if (!tbody) return;

    tbody.innerHTML = "";
    rows.forEach((u) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(u.branch || "")}</td>
        <td>${escapeHtml(u.team_a || "")}</td>
        <td>${escapeHtml(u.team_b || "")}</td>
        <td>${escapeHtml(u.team_c || "")}</td>
        <td>${escapeHtml(u.name || "")}</td>
        <td>${escapeHtml(u.id || "")}</td>
        <td>${escapeHtml(u.non_life_table || "")}</td>
        <td>${escapeHtml(u.life_table || "")}</td>
      `;
      tbody.appendChild(tr);
    });

    // plain에서도 hover title 적용
    applyCellTitles(els.rateUserTable);
  }
});
