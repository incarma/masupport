// django_ma/static/js/partner/manage_rate/index.js
// =========================================================
// ✅ Manage Rate - Index (Refactor Final)
// - 검색/자동조회/모달/입력행 초기화
// - ✅ 삭제 이벤트 핸들러 연결(attachDeleteHandlers)
//   -> leader는 delete.js 내부에서 바인딩 자체를 하지 않음
// =========================================================

import { els } from "./dom_refs.js";
import { fetchData } from "./fetch.js";
import { pad2, alertBox } from "./utils.js";
import { initInputRowEvents } from "./input_rows.js";
import { attachDeleteHandlers } from "./delete.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

/* =========================================================
   constants / guards
========================================================= */
const AUTOLOAD_GRADES = new Set(["head", "leader"]);
const INIT_DATAKEY = "manageRateIndexInited";
const ELLIPSIS_DATAKEY = "ellipsisTitleBound";
const AUTOLOAD_FLAG = "__manageRateAutoLoaded";

/* =========================================================
   dataset helpers
========================================================= */
function ds(key, fallback = "") {
  return String(els.root?.dataset?.[key] ?? fallback).trim();
}

function getGrade() {
  return ds("userGrade", window.currentUser?.grade || "");
}

function getDefaultBranch() {
  return ds("defaultBranch", window.currentUser?.branch || "");
}

function getEffectiveBranch() {
  const grade = getGrade();
  if (grade === "superuser") return String(els.branchSelect?.value || "").trim();
  return getDefaultBranch();
}

function getYMFromSelectors() {
  const y = String(els.yearSelect?.value || "").trim();
  const m = String(els.monthSelect?.value || "").trim();
  if (!y || !m) return "";
  return `${y}-${pad2(m)}`;
}

function buildFetchPayload(ym) {
  return {
    ym,
    branch: getEffectiveBranch(),
    grade: getGrade(),
    level: ds("userLevel"),
    team_a: ds("teamA"),
    team_b: ds("teamB"),
    team_c: ds("teamC"),
  };
}

/* =========================================================
   requester autofill
========================================================= */
function fillRequesterRow(row) {
  const u = window.currentUser || {};
  const set = (name, val) => {
    const el = row?.querySelector?.(`[name="${name}"]`);
    if (el) el.value = val ?? "";
  };
  set("rq_name", u.name || "");
  set("rq_id", u.id || "");
}

function fillRequesterAllRows() {
  document
    .querySelectorAll("#inputTable tbody tr.input-row")
    .forEach((row) => fillRequesterRow(row));
}

/* =========================================================
   period dropdown
========================================================= */
function fillDropdown(el, start, end, selected, suffix) {
  if (!el) return;
  el.innerHTML = "";
  for (let v = start; v <= end; v++) {
    const opt = document.createElement("option");
    opt.value = String(v);
    opt.textContent = `${v}${suffix}`;
    el.appendChild(opt);
  }
  el.value = String(selected);
}

function getBootPeriod() {
  const boot = window.ManageRateBoot || {};
  const now = new Date();

  const y = Number(boot.selectedYear || boot.currentYear || now.getFullYear());
  const m = Number(boot.selectedMonth || boot.currentMonth || now.getMonth() + 1);

  return { y, m };
}

function initPeriodDropdowns() {
  const now = new Date();
  const baseY = now.getFullYear();
  const { y: selectedY, m: selectedM } = getBootPeriod();

  fillDropdown(els.yearSelect, baseY - 1, baseY + 1, selectedY, "년");
  fillDropdown(els.monthSelect, 1, 12, selectedM, "월");
}

/* =========================================================
   search
========================================================= */
async function runSearch({ ym, branch } = {}) {
  const finalYM = ym || getYMFromSelectors();
  const finalBranch = branch || getEffectiveBranch();

  if (!finalYM) return alertBox("연도·월도를 선택해주세요.");

  const grade = getGrade();
  if (grade === "superuser" && !finalBranch) return alertBox("부서/지점을 선택해주세요.");
  if (!finalBranch) return alertBox("지점 정보가 없습니다.");

  try {
    await fetchData(buildFetchPayload(finalYM));
  } catch (err) {
    console.error("❌ [rate/index] fetchData 실패:", err);
    alertBox("데이터 조회 중 오류가 발생했습니다.");
  }
}

function resolveSearchButton() {
  return (
    els.btnSearch ||
    els.btnSearchPeriod ||
    document.getElementById("btnSearchPeriod") ||
    document.getElementById("btnSearch")
  );
}

function initSearchButton() {
  const btn = resolveSearchButton();
  if (!btn) return;
  if (btn.dataset.bound === "1") return;
  btn.dataset.bound = "1";

  btn.addEventListener("click", () => runSearch());
}

/* =========================================================
   superuser part/branch loader (대기형)
========================================================= */
function initSuperuserPartsBranchesWait() {
  if (getGrade() !== "superuser") return;

  const tryLoad = (retry = 0) => {
    if (typeof window.loadPartsAndBranches !== "function") {
      if (retry < 12) return setTimeout(() => tryLoad(retry + 1), 250);
      return;
    }
    window.loadPartsAndBranches("manage-rate");
  };

  tryLoad(0);
}

/* =========================================================
   table check modal
========================================================= */
function getTableFetchUrl(branch) {
  const base = ds("tableFetchUrl");
  if (!base) return "";
  const url = new URL(base, window.location.origin);
  url.searchParams.set("branch", branch);
  return url.toString();
}

function escapeAttr(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTableCheckHTML(rows) {
  const tbody = rows
    .map((r) => {
      const t = r.table || r.table_name || "-";
      const rate = r.rate ?? "-";
      return `
        <tr>
          <td class="text-truncate" title="${escapeAttr(t)}">${escapeAttr(t)}</td>
          <td class="text-center">${escapeAttr(rate)}</td>
        </tr>`;
    })
    .join("");

  return `
    <div class="table-responsive rate-table-check-scroll">
      <table class="table table-sm table-bordered align-middle mb-0 rate-table-check-table">
        <colgroup>
          <col class="rate-table-col-name">
          <col class="rate-table-col-rate">
        </colgroup>
        <thead class="table-light">
          <tr>
            <th class="text-center">테이블명</th>
            <th class="text-center">요율(%)</th>
          </tr>
        </thead>
        <tbody>${tbody}</tbody>
      </table>
    </div>`;
}

function showBootstrapModal(modalEl) {
  const bs = window.bootstrap;
  if (!bs?.Modal) return false;
  const inst = bs.Modal.getInstance(modalEl) || new bs.Modal(modalEl);
  inst.show();
  return true;
}

let __rateTableOverlayEl = null;

function ensureFallbackOverlay() {
  if (__rateTableOverlayEl) return __rateTableOverlayEl;

  const wrap = document.createElement("div");
  wrap.id = "rateTableCheckOverlay";
  wrap.className = "rate-table-check-overlay";
  wrap.setAttribute("aria-hidden", "true");

  wrap.innerHTML = `
    <div class="rate-table-check-modal" role="dialog" aria-modal="true" aria-label="테이블 확인">
      <div class="rate-table-check-header">
        <div class="rate-table-check-title">테이블 확인</div>
        <button type="button" id="rateTableOverlayClose" class="rate-table-check-close" aria-label="close">✕</button>
      </div>
      <div id="rateTableOverlayBody" class="rate-table-check-body"></div>
    </div>
  `;

  wrap.addEventListener("click", (e) => {
    if (e.target === wrap) hideFallbackOverlay();
  });

  document.body.appendChild(wrap);

  wrap.querySelector("#rateTableOverlayClose")?.addEventListener("click", hideFallbackOverlay);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideFallbackOverlay();
  });

  __rateTableOverlayEl = wrap;
  return wrap;
}

function showFallbackOverlay(html) {
  const wrap = ensureFallbackOverlay();
  const body = wrap.querySelector("#rateTableOverlayBody");
  if (body) body.innerHTML = html;

  wrap.classList.add("is-open");
  wrap.setAttribute("aria-hidden", "false");
}

function hideFallbackOverlay() {
  if (!__rateTableOverlayEl) return;
  __rateTableOverlayEl.classList.remove("is-open");
  __rateTableOverlayEl.setAttribute("aria-hidden", "true");
}

function initTableCheckModal() {
  const btnCheck = document.getElementById("btnCheckTable");
  const modalBody = document.getElementById("tableCheckBody");
  const modalEl = document.getElementById("tableCheckModal");
  if (!btnCheck) return;

  if (btnCheck.dataset.bound === "1") return;
  btnCheck.dataset.bound = "1";

  btnCheck.addEventListener("click", async () => {
    const branch = getEffectiveBranch();
    if (!branch) return alertBox("지점 정보가 없습니다. 부서/지점을 먼저 선택하세요.");

    const url = getTableFetchUrl(branch);
    if (!url) return alertBox("테이블 조회 URL이 없습니다. (data-table-fetch-url 확인)");

    const loadingHTML = `<div class="py-4 text-muted">불러오는 중...</div>`;

    let useBootstrap = false;
    if (modalBody && modalEl) {
      modalBody.innerHTML = loadingHTML;
      useBootstrap = showBootstrapModal(modalEl);
    }
    if (!useBootstrap) showFallbackOverlay(loadingHTML);

    try {
      const res = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      const data = await readJsonOrThrow(res, "테이블 조회 실패");
      if (!isSuccessJson(data)) throw new Error(data.message || "조회 실패");

      const rows = Array.isArray(data.rows) ? data.rows : [];
      const html = rows.length
        ? renderTableCheckHTML(rows)
        : `<div class="py-4 text-muted">등록된 테이블이 없습니다.</div>`;

      if (useBootstrap && modalBody) modalBody.innerHTML = html;
      else showFallbackOverlay(html);
    } catch (err) {
      console.error("❌ [rate/index] 테이블 확인 실패:", err);
      const errHTML = `<div class="py-4 text-danger">테이블 정보를 불러오지 못했습니다.</div>`;
      if (useBootstrap && modalBody) modalBody.innerHTML = errHTML;
      else showFallbackOverlay(errHTML);
    }
  });
}

/* =========================================================
   autoload
========================================================= */
function markAutoLoaded() {
  window[AUTOLOAD_FLAG] = true;
}
function isAutoLoaded() {
  return window[AUTOLOAD_FLAG] === true;
}

function shouldAutoLoadByBootOrGrade() {
  const boot = window.ManageRateBoot || {};
  const grade = getGrade();

  if (boot.autoLoad === true) return true;
  if (boot.autoLoad === false) return false;

  return AUTOLOAD_GRADES.has(grade);
}

function buildFallbackYM() {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}`;
}

function initAutoLoadAssist() {
  if (isAutoLoaded()) return;
  if (window.__manageBootInited?.rate) return;

  const grade = getGrade();
  if (!(grade === "superuser" || AUTOLOAD_GRADES.has(grade))) return;
  if (!shouldAutoLoadByBootOrGrade()) return;

  const branch = getEffectiveBranch();
  if (!branch) return;

  const ym = getYMFromSelectors() || buildFallbackYM();

  markAutoLoaded();
  setTimeout(() => runSearch({ ym, branch }), 250);
}

/* =========================================================
   ellipsis title behavior
========================================================= */
function attachEllipsisTitleBehavior() {
  const root = els.root;
  if (!root) return;

  if (root.dataset[ELLIPSIS_DATAKEY] === "1") return;
  root.dataset[ELLIPSIS_DATAKEY] = "1";

  const setTitle = (el) => {
    if (!el) return;

    if (el.tagName === "SELECT") {
      const opt = el.selectedOptions?.[0];
      el.title = opt ? String(opt.textContent || "").trim() : "";
      return;
    }

    if ("value" in el) el.title = String(el.value || "").trim();
  };

  root
    .querySelectorAll("#inputTable input, #inputTable select, #mainTable input, #mainTable select")
    .forEach(setTitle);

  const handler = (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    if (!t.matches("#inputTable input, #inputTable select, #mainTable input, #mainTable select")) return;
    setTitle(t);
  };

  root.addEventListener("input", handler, true);
  root.addEventListener("change", handler, true);
  root.addEventListener("focusin", handler, true);
  root.addEventListener("mouseover", handler, true);
}

/* =========================================================
   init
========================================================= */
function init() {
  if (!els.root) return;

  if (els.root.dataset[INIT_DATAKEY] === "1") return;
  els.root.dataset[INIT_DATAKEY] = "1";

  initPeriodDropdowns();
  initInputRowEvents();
  fillRequesterAllRows();

  initSuperuserPartsBranchesWait();
  initSearchButton();
  initTableCheckModal();

  // ✅ 내부에서 leader면 바인딩하지 않도록 처리됨
  attachDeleteHandlers();

  initAutoLoadAssist();
  attachEllipsisTitleBehavior();
}

document.addEventListener("DOMContentLoaded", () => {
  try {
    init();
  } catch (err) {
    console.error("❌ [manage_rate/index.js 초기화 오류]", err);
  }
});

export { fillRequesterRow, fillRequesterAllRows, runSearch };
