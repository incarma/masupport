// django_ma/static/js/partner/manage_rate/fetch.js
// =========================================================
// ✅ Fetch + Render (Refactor Final)
// - DataTables 렌더
// - 처리일자 인라인 저장
// - ✅ 삭제 버튼: superuser/head만 렌더링 (leader는 버튼 DOM 생성 X)
// =========================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox } from "./utils.js";
import { resetInputSection } from "./input_rows.js";
import { getCSRFToken } from "../../common/manage/csrf.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

let mainDT = null;
let delegationBound = false;
let resizeBound = false;

/* =========================================================
   Dataset/URL helpers
========================================================= */
function toDashed(camel) {
  return String(camel || "").replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
}

function pickDatasetUrl(root, keys = []) {
  if (!root) return "";

  const ds = root.dataset || {};
  for (const k of keys) {
    const v = ds?.[k];
    if (v && String(v).trim()) return String(v).trim();
  }

  for (const k of keys) {
    const attr = `data-${toDashed(k)}`;
    const v = root.getAttribute?.(attr);
    if (v && String(v).trim()) return String(v).trim();
  }

  return "";
}

function getFetchBaseUrl() {
  return pickDatasetUrl(els.root, ["fetchUrl", "dataFetchUrl", "fetchURL", "dataFetchURL"]);
}

function getUpdateProcessDateUrl() {
  return pickDatasetUrl(els.root, ["updateProcessDateUrl", "dataUpdateProcessDateUrl", "updateProcessDateURL"]);
}

/* =========================================================
   Grade / Permission
========================================================= */
function getUserGrade() {
  return String(els.root?.dataset?.userGrade || window.currentUser?.grade || "").trim();
}

function canEditProcessDate() {
  const g = getUserGrade();
  return g === "superuser" || g === "head";
}

function canRenderDeleteButton() {
  const g = getUserGrade();
  return g === "superuser" || g === "head";
}

/* =========================================================
   Normalizers / Escapes
========================================================= */
function normalizeYM(ym) {
  const s = String(ym || "").trim();
  if (!s) return "";
  if (/^\d{4}-\d{2}$/.test(s)) return s;

  const digits = s.replaceAll("-", "").replaceAll("/", "").replaceAll(".", "");
  if (/^\d{6}$/.test(digits)) return `${digits.slice(0, 4)}-${digits.slice(4, 6)}`;
  if (s.length >= 6) return `${s.slice(0, 4)}-${s.slice(-2)}`;
  return s;
}

function escapeHtml(v) {
  const s = String(v ?? "");
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(v) {
  return escapeHtml(v);
}

function squeezeSpaces(s) {
  return String(s || "")
    .replaceAll(">", " ")
    .replace(/\s+/g, " ")
    .trim();
}

/* =========================================================
   UI helpers
========================================================= */
function revealSections() {
  if (els.inputSection) els.inputSection.hidden = false;
  if (els.mainSheet) els.mainSheet.hidden = false;

  requestAnimationFrame(() => requestAnimationFrame(() => adjustDT()));
}

function safeResetInput() {
  try {
    resetInputSection();
  } catch (e) {
    console.warn("[rate/fetch] resetInputSection 실패(무시):", e);
  }
}

/* =========================================================
   Tooltip (Bootstrap 5) - DT redraw 대응
   편제변경 fetch.js 동일 방식
========================================================= */
function initTooltipsInMainTable() {
  if (!window.bootstrap?.Tooltip) return;
  const scope = els.mainTable?.closest?.("#mainSheet") || els.root || document;
  scope.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
    const inst = window.bootstrap.Tooltip.getInstance(el);
    if (inst) inst.dispose();
    new window.bootstrap.Tooltip(el, {
      trigger: "hover focus",
      container: "body",
      boundary: "viewport",
    });
  });
}

/* =========================================================
   Server calls (process_date)
========================================================= */
async function updateProcessDate(id, value) {
  const url = getUpdateProcessDateUrl();
  if (!url) throw new Error("update_process_date_url 누락 (data-update-process-date-url 확인)");

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    credentials: "same-origin",
    body: JSON.stringify({
      id,
      process_date: value || "",
      kind: "rate",
    }),
  });

  const data = await readJsonOrThrow(res, "처리일자 저장 실패");
  if (!isSuccessJson(data)) throw new Error(data.message || "처리일자 저장 실패");
  return data;
}

/* =========================================================
   Render helpers
========================================================= */
/* ✅ 말줄임 + Bootstrap Tooltip — 편제변경 renderEllipsisCell 동일 방식
   요청자/대상자/소속/비고 공통 사용 */
function renderEllipsisCell(val) {
  const raw = String(val ?? "").trim();
  if (!raw) return "";
  const esc = escapeAttr(raw);
  return `<span class="dt-ellipsis"
               data-bs-toggle="tooltip"
               data-bs-placement="top"
               data-bs-title="${esc}"
               tabindex="0">${escapeHtml(raw)}</span>`;
}

function renderAfterCell(val) {
  const v = String(val ?? "").trim();
  if (!v) return "";
  return `<span class="cell-after">${escapeHtml(v)}</span>`;
}

/**
 * ✅ 삭제 버튼 렌더링 규칙 (최종)
 * - superuser/head: 표시
 * - leader: 미표시(버튼 DOM 생성 X)
 */
function buildActionButtons(row) {
  if (!canRenderDeleteButton()) return "";

  const id = String(row?.id || "").trim();
  if (!id) return "";

  return `
    <button type="button"
            class="btn btn-sm btn-outline-danger btnDeleteRow"
            data-id="${escapeAttr(id)}">
      삭제
    </button>
  `;
}

function renderProcessDateCell(_value, _type, row) {
  const val = String(row?.process_date || "").trim();

  // leader는 입력 UI가 의미가 없고 권한도 없으므로 텍스트로만 표시
  if (!canEditProcessDate()) {
    return `<span>${escapeHtml(val)}</span>`;
  }

  return `
    <input type="date"
           class="form-control form-control-sm processDateInput"
           data-id="${escapeAttr(row?.id || "")}"
           value="${escapeAttr(val)}" />
  `;
}

/* =========================================================
   DataTables columns
========================================================= */
const MAIN_COLUMNS = [
  // 요청자 — 정렬 가능
  { data: "rq_display", defaultContent: "", width: "88px",
    render: (v) => renderEllipsisCell(v) },
  // 대상자 — 정렬 가능
  { data: "tg_display",     defaultContent: "", width: "88px",
    render: (v) => renderEllipsisCell(v) },
  // 소속 — 정렬 가능
  { data: "tg_affiliation", defaultContent: "-", width: "120px",
    render: (v) => renderEllipsisCell(v || "-") },
  // 손보테이블(변경전) — 정렬 가능
  { data: "before_ftable",  defaultContent: "", width: "70px" },
  // 손보요율(변경전) — 정렬 가능
  { data: "before_frate",   defaultContent: "", width: "70px" },
  // 손보테이블(변경후) — 정렬 가능
  { data: "after_ftable",   defaultContent: "", width: "70px", render: (v) => renderAfterCell(v) },
  // 손보요율(변경후) — 정렬 가능
  { data: "after_frate",    defaultContent: "", width: "70px" },
  // 생보테이블(변경전) — 정렬 가능
  { data: "before_ltable",  defaultContent: "", width: "70px" },
  // 생보요율(변경전) — 정렬 가능
  { data: "before_lrate",   defaultContent: "", width: "70px" },
  // 생보테이블(변경후) — 정렬 가능
  { data: "after_ltable",   defaultContent: "", width: "70px", render: (v) => renderAfterCell(v) },
  // 생보요율(변경후) — 정렬 가능
  { data: "after_lrate",    defaultContent: "", width: "70px" },
  // 비고 — 정렬 가능
  { data: "memo", defaultContent: "", width: "120px",
    render: (v) => renderEllipsisCell(v) },
  // 요청일자 — 정렬 가능 (YYYY-MM-DD 사전순 = 날짜순)
  { data: "request_date", defaultContent: "", width: "82px" },
  // 처리일자 — 정렬 불필요 (date input UI)
  {
    data: "process_date",
    width: "120px",
    orderable: false,
    searchable: false,
    render: renderProcessDateCell,
    defaultContent: "",
  },
  // 삭제 — 정렬 불필요
  {
    data: "id",
    width: "70px",
    orderable: false,
    searchable: false,
    render: (_id, _type, row) => buildActionButtons(row),
    defaultContent: "",
  },
];

const MAIN_COLSPAN = MAIN_COLUMNS.length;

function canUseDataTables() {
  return !!(els.mainTable && window.jQuery && window.jQuery.fn?.DataTable);
}

function adjustDT() {
  if (!mainDT) return;
  try {
    mainDT.columns.adjust();
    mainDT.draw(false);
  } catch (_) {}
}

function destroyIfExists() {
  try {
    if (els.mainTable && window.jQuery?.fn?.DataTable?.isDataTable?.(els.mainTable)) {
      window.jQuery(els.mainTable).DataTable().clear().destroy();
    }
  } catch (_) {}
  mainDT = null;
}

function needRebuildDT() {
  if (!els.mainTable) return false;
  const thCount = els.mainTable.querySelectorAll("thead th").length;
  return thCount && thCount !== MAIN_COLUMNS.length;
}

function ensureMainDT() {
  if (!canUseDataTables()) return null;

  if (needRebuildDT()) {
    destroyIfExists();
  }
  if (mainDT) return mainDT;

  destroyIfExists();

  mainDT = window.jQuery(els.mainTable).DataTable({
    paging: true,
    searching: true,
    info: true,
    ordering: true,
    order: [[12, "desc"]],   // ✅ 기본 정렬: 요청일자(13번째 컬럼, index 12) 내림차순
    pageLength: 10,
    lengthChange: true,

    autoWidth: false,
    scrollX: false,
    destroy: false,

    dom: "<'rate-dt-top d-flex align-items-center mb-2'<''l><'ms-auto'f>>rt<'rate-dt-bottom d-flex align-items-center mt-2'<''i><'ms-auto'p>>",
    language: {
      emptyTable: "데이터가 없습니다.",
      search: "검색:",
      searchPlaceholder: "검색어 입력",
      lengthMenu: "_MENU_개씩 보기",
      info: "_TOTAL_건 중 _START_ ~ _END_",
      infoEmpty: "0건",
      paginate: { previous: "이전", next: "다음" },
    },
    columns: MAIN_COLUMNS,
    drawCallback: () => {
      initTooltipsInMainTable();
      requestAnimationFrame(() => adjustDT());
    },
  });

  return mainDT;
}

/* =========================================================
   Fallback render
========================================================= */
function renderMainSheetFallback(rows) {
  if (!els.mainTable) return;
  const tbody = els.mainTable.querySelector("tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!rows?.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="${MAIN_COLSPAN}" class="text-center text-muted">데이터가 없습니다.</td>`;
    tbody.appendChild(tr);
    return;
  }

  const canProcEdit = canEditProcessDate();

  rows.forEach((r) => {
    const tr = document.createElement("tr");
    const proc = String(r.process_date || "").trim();

    tr.innerHTML = `
      <td>${escapeHtml(r.rq_display || "")}</td>
      <td>${escapeHtml(r.tg_display || "")}</td>
      <td>${escapeHtml(r.tg_affiliation || "-")}</td>

      <td>${escapeHtml(r.before_ftable || "")}</td>
      <td class="text-center">${escapeHtml(r.before_frate || "")}</td>

      <td>${renderAfterCell(r.after_ftable || "")}</td>
      <td class="text-center">${escapeHtml(r.after_frate || "")}</td>

      <td>${escapeHtml(r.before_ltable || "")}</td>
      <td class="text-center">${escapeHtml(r.before_lrate || "")}</td>

      <td>${renderAfterCell(r.after_ltable || "")}</td>
      <td class="text-center">${escapeHtml(r.after_lrate || "")}</td>

      <td>${escapeHtml(r.memo || "")}</td>
      <td class="text-center">${escapeHtml(r.request_date || "")}</td>

      <td class="text-center">
        ${
          canProcEdit
            ? `<input type="date"
                      class="form-control form-control-sm processDateInput"
                      data-id="${escapeAttr(r.id || "")}"
                      value="${escapeAttr(proc)}" />`
            : `<span>${escapeHtml(proc)}</span>`
        }
      </td>

      <td class="text-center">${buildActionButtons(r)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderMainSheet(rows) {
  const dt = ensureMainDT();
  if (dt) {
    dt.clear();
    if (rows?.length) dt.rows.add(rows);
    dt.draw();
    requestAnimationFrame(() => adjustDT());
    return;
  }
  renderMainSheetFallback(rows);
}

/* =========================================================
   Delegation + Resize (once)
========================================================= */
function bindDelegationOnce() {
  if (delegationBound) return;
  delegationBound = true;

  document.addEventListener("change", async (e) => {
    const t = e.target;
    if (!t?.classList?.contains("processDateInput")) return;
    if (!els.mainTable || !els.mainTable.contains(t)) return;
    if (!canEditProcessDate()) return;

    const id = String(t.dataset.id || "").trim();
    const value = String(t.value || "").trim();
    if (!id) return;

    showLoading("처리일자 저장 중...");
    try {
      await updateProcessDate(id, value);
    } catch (err) {
      console.error(err);
      alertBox(err?.message || "처리일자 저장 실패");
    } finally {
      hideLoading();
    }
  });
}

function bindResizeOnce() {
  if (resizeBound) return;
  resizeBound = true;

  window.addEventListener("resize", () => requestAnimationFrame(() => adjustDT()), { passive: true });
}

/* =========================================================
   Normalize row
========================================================= */
function formatNameId(name, id) {
  const n = String(name || "").trim();
  const i = String(id || "").trim();
  if (!n && !i) return "";
  if (!i) return n;
  if (!n) return `(${i})`;
  return `${n}(${i})`;
}

function joinTeams(a, b, c) {
  const arr = [a, b, c].map((x) => String(x ?? "").trim()).filter((x) => x && x !== "-");
  return arr.length ? arr.join(" ") : "-";
}

function normalizeRateRow(row = {}) {
  const requester_name = row.requester_name || row.rq_name || "";
  const requester_id = row.requester_id || row.rq_id || "";

  const target_name = row.target_name || row.tg_name || "";
  const target_id = row.target_id || row.tg_id || "";

  const rawAff =
    String(row.tg_affiliation || row.target_affiliation || "").trim() ||
    joinTeams(row.tg_team_a, row.tg_team_b, row.tg_team_c);

  const tgAff = squeezeSpaces(rawAff) || "-";

  return {
    id: row.id || "",
    rq_display: formatNameId(requester_name, requester_id),
    tg_display: formatNameId(target_name, target_id),
    tg_affiliation: tgAff,

    before_ftable: row.before_ftable || "",
    before_frate: row.before_frate || "",

    after_ftable: row.after_ftable || "",
    after_frate: row.after_frate || "",

    before_ltable: row.before_ltable || "",
    before_lrate: row.before_lrate || "",

    after_ltable: row.after_ltable || "",
    after_lrate: row.after_lrate || "",

    memo: row.memo || "",

    request_date: row.request_date || row.created_date || row.created_at || "",
    process_date: row.process_date || "",
  };
}

/* =========================================================
   Fetch
========================================================= */
export async function fetchData(payload = {}) {
  if (!els.root) return;

  window.__lastRateFetchPayload = payload;

  bindDelegationOnce();
  bindResizeOnce();

  const baseUrl = getFetchBaseUrl();
  if (!baseUrl) {
    console.warn("[rate/fetch] fetchUrl 누락", els.root?.dataset);
    revealSections();
    safeResetInput();
    renderMainSheet([]);
    return;
  }

  const ym = normalizeYM(payload.ym);
  const branch = String(payload.branch || "").trim();

  const url = new URL(baseUrl, window.location.origin);
  url.searchParams.set("month", ym);
  url.searchParams.set("branch", branch);

  showLoading("데이터를 불러오는 중입니다...");
  try {
    const res = await fetch(url.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    });
    const data = await readJsonOrThrow(res, "조회 실패");
    const rawRows = Array.isArray(data?.rows) ? data.rows : [];

    revealSections();

    if (!isSuccessJson(data)) {
      safeResetInput();
      renderMainSheet([]);
      return;
    }

    const rows = rawRows.map(normalizeRateRow);
    safeResetInput();
    renderMainSheet(rows);

    setTimeout(() => adjustDT(), 0);
  } catch (err) {
    console.error("❌ [rate/fetch] 예외:", err);
    revealSections();
    safeResetInput();
    renderMainSheet([]);
  } finally {
    hideLoading();
  }
}
