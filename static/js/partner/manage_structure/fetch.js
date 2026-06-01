// django_ma/static/js/partner/manage_structure/fetch.js
// =========================================================
// ✅ Structure - Fetch/Render (FINAL, 정리본)
// - DataTables 우선 + fallback 렌더
// - 말줄임(.dt-ellipsis), 변경후 강조(.cell-after) 유지
// - Tooltip: Bootstrap Tooltip (container: body)
// - 처리일자 저장/삭제: root 범위 이벤트 위임(충돌 방지)
// - dataset URL 키 안전화 + 서버 키 normalize
// =========================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, getCSRFToken, pad2 } from "./utils.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";
import { getDatasetUrl } from "../../common/manage/dataset.js";
import {
  toStr as commonToStr,
  escapeHtml as commonEscapeHtml,
  escapeAttr as commonEscapeAttr,
  formatNameId,
} from "../../common/manage/text.js";
import {
  renderEllipsisCell as commonRenderEllipsisCell,
  renderAfterEllipsisCell,
  initBootstrapTooltips,
} from "../../common/manage/table_ui.js";

/* =========================================================
   State
========================================================= */
let mainDT = null;
let delegationBound = false;
let resizeBound = false;

/* =========================================================
   Small helpers
========================================================= */
function toStr(v) {
  return commonToStr(v);
}

/* =========================================================
   Dataset URL helpers
========================================================= */
function dsUrl(keys = []) {
  // ✅ dataset URL 후보 탐색 공통화
  return getDatasetUrl(els.root, keys, "");
}

function getFetchUrl() {
  return dsUrl(["fetchUrl", "dataFetchUrl", "dataDataFetchUrl", "dataFetch"]);
}
function getUpdateProcessDateUrl() {
  return dsUrl(["updateProcessDateUrl", "dataUpdateProcessDateUrl", "dataUpdateProcessDate"]);
}
function getDeleteUrl() {
  return dsUrl(["deleteUrl", "dataDeleteUrl", "dataDataDeleteUrl", "dataDelete"]);
}

/* =========================================================
   Permission helpers (기존 규칙 유지)
========================================================= */
function getUserGrade() {
  return toStr(els.root?.dataset?.userGrade || window.currentUser?.grade || "");
}
function canEditProcessDate() {
  const g = getUserGrade();
  return g === "superuser" || g === "head";
}
function canDeleteRow() {
  const g = getUserGrade();
  return g === "superuser" || g === "head";
}

/* =========================================================
   UI helpers
========================================================= */
function revealSections() {
  if (els.inputSection) els.inputSection.hidden = false;
  if (els.mainSheet) els.mainSheet.hidden = false;
  // ✅ rAF 예약은 fetchData가 직접 처리하므로 여기서는 hidden 해제만 수행
}

/* =========================================================
   XSS escape
========================================================= */
function escapeHtml(v) {
  return commonEscapeHtml(v);
}
function escapeAttr(v) {
  return commonEscapeAttr(v);
}

/* =========================================================
   Tooltip (Bootstrap 5) - DT redraw 대응
========================================================= */
function initTooltipsInMainTable() {
  const scope = els.mainTable?.closest?.("#mainSheet") || els.root || document;
  initBootstrapTooltips(scope);
}

/* =========================================================
   Render helpers
========================================================= */
function fmtPerson(name, id) {
  // ✅ 기존 표시 규칙 유지
  return formatNameId(name, id).replace(/^\((.*)\)$/, "$1");
}

function renderEllipsisCell(val) {
  return commonRenderEllipsisCell(val);
}

function renderAfterEllipsis(val) {
  return renderAfterEllipsisCell(val);
}

function renderOrFlag(val) {
  const checked = !!val ? "checked" : "";
  return `
    <div class="form-check d-flex justify-content-center mb-0">
      <input class="form-check-input or-checkbox" type="checkbox" disabled ${checked}>
    </div>
  `;
}

function renderProcessDateCell(_value, _type, row) {
  const grade = getUserGrade();
  const val = toStr(row.process_date || "");

  if (grade === "leader") return renderEllipsisCell(val);

  return `
    <input type="date"
           class="form-control form-control-sm processDateInput"
           data-id="${escapeAttr(row.id || "")}"
           value="${escapeAttr(val)}"
           ${canEditProcessDate() ? "" : "disabled"} />
  `;
}

function buildActionButtons(row) {
  if (!canDeleteRow()) return "";
  return `
    <button type="button"
            class="btn btn-sm btn-outline-danger btnDeleteRow"
            data-id="${escapeAttr(row.id || "")}">
      삭제
    </button>
  `;
}

/* =========================================================
   Server calls
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
    body: JSON.stringify({ id, process_date: value || "", kind: "structure" }),
  });

  const data = await readJsonOrThrow(res, "처리일자 저장 실패");
  if (!isSuccessJson(data)) throw new Error(data.message || "처리일자 저장 실패");
  return data;
}

async function deleteStructureRow(id) {
  const url = getDeleteUrl();
  if (!url) throw new Error("delete_url 누락 (data-data-delete-url 확인)");

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ id }),
  });

  const data = await readJsonOrThrow(res, "삭제 실패");
  if (!isSuccessJson(data)) throw new Error(data.message || "삭제 실패");
  return data;
}

/* =========================================================
   DataTables columns
========================================================= */
const MAIN_COLUMNS = [
  // 요청자 — 정렬 가능 (requester_name 기준, render 결과가 HTML이므로 type: "string" 명시)
  { data: "requester_name", defaultContent: "", render: (_v, _t, r) => renderEllipsisCell(fmtPerson(r.requester_name, r.requester_id)) },
  // 대상자 — 정렬 가능
  { data: "target_name", defaultContent: "", render: (_v, _t, r) => renderEllipsisCell(fmtPerson(r.target_name, r.target_id)) },
  // 소속(변경전) — 정렬 가능
  { data: "target_branch", defaultContent: "", render: (v) => renderEllipsisCell(v) },
  // 소속(변경후) — 정렬 가능
  { data: "chg_branch", defaultContent: "", render: (v) => renderAfterEllipsis(v) },
  // 직급(변경전) — 정렬 가능
  { data: "rank", defaultContent: "", render: (v) => renderEllipsisCell(v) },
  // 직급(변경후) — 정렬 가능
  { data: "chg_rank", defaultContent: "", render: (v) => renderAfterEllipsis(v) },
  // OR — 정렬 불필요
  { data: "or_flag", defaultContent: false, className: "or-cell", orderable: false, searchable: false, render: (v) => renderOrFlag(!!v) },
  // 비고 — 정렬 가능
  { data: "memo", defaultContent: "", render: (v) => renderEllipsisCell(v) },
  // 요청일자 — 정렬 가능 (날짜 문자열 YYYY-MM-DD 형식이면 사전순 = 날짜순)
  { data: "request_date", defaultContent: "", render: (v) => renderEllipsisCell(v) },
  // 처리일자 — 정렬 불필요 (date input이므로 제외)
  { data: "process_date", orderable: false, searchable: false, render: renderProcessDateCell, defaultContent: "" },
  // 삭제 — 정렬 불필요
  { data: "id", orderable: false, searchable: false, render: (_id, _t, r) => buildActionButtons(r), defaultContent: "" },
];

const MAIN_COLSPAN = MAIN_COLUMNS.length;

/* =========================================================
   DataTables helpers
========================================================= */
function canUseDataTables() {
  return !!(els.mainTable && window.jQuery && window.jQuery.fn?.DataTable);
}

function adjustDT() {
  if (!mainDT) return;
  try {
    mainDT.columns.adjust();
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

function bindResizeOnce() {
  if (resizeBound) return;
  resizeBound = true;

  let raf = 0;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => adjustDT());
  });
}

function ensureMainDT() {
  if (!canUseDataTables()) return null;

  // ✅ manage_rate/fetch.js 동일: 매 호출마다 destroy 후 재초기화
  //    캐시된 mainDT 참조가 resetInputSection 후 깨지는 현상 방지
  destroyIfExists();

  mainDT = window.jQuery(els.mainTable).DataTable({
    paging: true,
    searching: true,
    info: true,
    ordering: true,
    order: [[8, "desc"]],   // ✅ 기본 정렬: 요청일자(9번째 컬럼, index 8) 내림차순
    pageLength: 10,
    lengthChange: true,
    autoWidth: false,
    destroy: false,
    scrollX: false,
    scrollCollapse: false,
    // 개수선택(좌) / 검색창(우) 동일 행 배치
    dom: "<'structure-dt-top d-flex align-items-center mb-2'<''l><'ms-auto'f>>rt<'structure-dt-bottom d-flex align-items-center mt-2'<''i><'ms-auto'p>>",
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

  bindResizeOnce();
  return mainDT;
}

/* =========================================================
   Fallback render (DT 미사용 시)
========================================================= */
function renderFallback(rows) {
  const tbody = els.mainTable?.querySelector("tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!rows?.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="${MAIN_COLSPAN}" class="text-center text-muted">데이터가 없습니다.</td>`;
    tbody.appendChild(tr);
    return;
  }

  const grade = getUserGrade();

  rows.forEach((r) => {
    const proc = toStr(r.process_date || "");
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${renderEllipsisCell(fmtPerson(r.requester_name, r.requester_id))}</td>
      <td>${renderEllipsisCell(fmtPerson(r.target_name, r.target_id))}</td>
      <td>${renderEllipsisCell(r.target_branch)}</td>

      <td>${renderAfterEllipsis(r.chg_branch)}</td>
      <td>${renderEllipsisCell(r.rank)}</td>
      <td>${renderAfterEllipsis(r.chg_rank)}</td>

      <td class="or-cell">${renderOrFlag(!!r.or_flag)}</td>

      <td>${renderEllipsisCell(r.memo)}</td>
      <td class="text-center">${renderEllipsisCell(r.request_date)}</td>

      <td class="text-center">
        ${
          grade === "leader"
            ? renderEllipsisCell(proc)
            : `<input type="date"
                      class="form-control form-control-sm processDateInput"
                      data-id="${escapeAttr(r.id || "")}"
                      value="${escapeAttr(proc)}"
                      ${canEditProcessDate() ? "" : "disabled"} />`
        }
      </td>

      <td class="text-center">${buildActionButtons(r)}</td>
    `;
    tbody.appendChild(tr);
  });

  initTooltipsInMainTable();
}

/* =========================================================
   Render main
========================================================= */
function renderMain(rows) {
  const dt = ensureMainDT();
  if (dt) {
    dt.clear();
    if (rows?.length) dt.rows.add(rows);
    dt.draw();
    return;
  }
  renderFallback(rows);
}

/* =========================================================
   Delegation (bind once) - ✅ root 범위로 제한
========================================================= */
function bindDelegationOnce() {
  // ✅ window 전역 플래그 — 모듈이 중복 로드되어도 delegation 1회만 바인딩 보장
  if (window.__structureDelegationBound) return;
  window.__structureDelegationBound = true;
  delegationBound = true;

  const root = els.root || document;

  // 처리일자 변경
  root.addEventListener("change", async (e) => {
    const t = e.target;
    if (!t?.classList?.contains("processDateInput")) return;
    if (!els.mainTable || !els.mainTable.contains(t)) return;
    if (!canEditProcessDate()) return;

    const id = toStr(t.dataset.id || "");
    const value = toStr(t.value || "");
    if (!id) return;

    showLoading("처리일자 저장 중...");
    try {
      await updateProcessDate(id, value);
    } catch (err) {
      console.error(err);
      (alertBox || alert)(err?.message || "처리일자 저장 실패");
    } finally {
      hideLoading();
    }
  });

  // 삭제 클릭
  root.addEventListener("click", async (e) => {
    const btn = e.target?.closest?.(".btnDeleteRow");
    if (!btn) return;
    if (!els.mainTable || !els.mainTable.contains(btn)) return;

    const id = toStr(btn.dataset.id || "");
    if (!id) {
      console.error("❌ [structure/delete] data-id 누락 — 삭제 중단");
      alertBox("삭제 대상 ID를 찾을 수 없습니다. 페이지를 새로고침 후 다시 시도해 주세요.");
      return;
    }
    if (!confirm("해당 행을 삭제할까요?")) return;

    btn.disabled = true;
    showLoading("삭제 중...");
    try {
      await deleteStructureRow(id);

      const y = toStr(els.year?.value || "");
      const m = toStr(els.month?.value || "");
      const ym = `${y}-${pad2(m)}`;

      const branch = toStr(els.branch?.value || "") || toStr(window.currentUser?.branch || "") || "";

      // 재조회
      await fetchData(ym, branch);
    } catch (err) {
      console.error(err);
      (alertBox || alert)(err?.message || "삭제 실패");
    } finally {
      hideLoading();
      btn.disabled = false;
    }
  });
}

/* =========================================================
   Normalize (서버 키 변화 흡수)
========================================================= */
function normalizeRow(row = {}) {
  return {
    // ✅ pk 키 후보를 모두 탐색 (서버 응답 키 변화 흡수)
    id: String(row.id ?? row.pk ?? row.record_id ?? "").trim(),

    requester_name: row.requester_name || row.rq_name || "",
    requester_id: row.requester_id || row.rq_id || "",
    requester_branch: row.requester_branch || row.rq_branch || "",

    target_name: row.target_name || row.tg_name || "",
    target_id: row.target_id || row.tg_id || "",
    target_branch: row.target_branch || row.tg_branch || "",

    chg_branch: row.chg_branch || row.after_branch || row.new_branch || "",
    chg_rank: row.chg_rank || row.after_rank || row.new_rank || "",

    rank: row.rank || row.target_rank || row.tg_rank || "",
    or_flag: !!row.or_flag,

    memo: row.memo || "",
    request_date: row.request_date || "",
    process_date: row.process_date || "",
  };
}

/* =========================================================
   Fetch (public)
========================================================= */
export async function fetchData(ym, branch) {
  if (!els.root) return;

  bindDelegationOnce();
  revealSections();

  // ✅ hidden→visible 전환 후 브라우저 레이아웃 페인트 완료까지 대기
  //    이 시점 이후에 dt.draw()가 실행되어야 columns.adjust()가 정상 계산됨
  await new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve))
  );

  const baseUrl = getFetchUrl();
  if (!baseUrl) {
    console.warn("⚠️ [structure/fetch] fetchUrl 누락", els.root?.dataset);
    renderMain([]);
    return;
  }

  const url = new URL(baseUrl, window.location.origin);
  url.searchParams.set("month", toStr(ym));
  url.searchParams.set("branch", toStr(branch));

  showLoading("데이터를 불러오는 중입니다...");
  try {
    const res = await fetch(url.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });

    const data = await readJsonOrThrow(res, "조회 실패");
    const rawRows = Array.isArray(data?.rows) ? data.rows : [];

    if (!isSuccessJson(data)) {
      console.warn("⚠️ [structure/fetch] server error", { status: res.status, data });
      renderMain([]);
      return;
    }

    const rows = rawRows.map(normalizeRow);
    renderMain(rows);
  } catch (err) {
    console.error("❌ [structure/fetch] 예외:", err);
    renderMain([]);
  } finally {
    hideLoading();
  }
}
