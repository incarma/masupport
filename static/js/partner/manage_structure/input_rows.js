// django_ma/static/js/partner/manage_structure/input_rows.js
// =======================================================
// 📘 manage_structure 입력행 컨트롤 - FINAL
// - 요청자 자동 입력(rq_display + hidden rq_*)
// - 대상자 선택(공용 search_user_modal.js 이벤트) 연동
// - 대상자 10명 제한
// - 저장 후 입력 초기화 + 메인시트 갱신(fetchData)
// - 중복 바인딩 방지 + 이벤트 위임(범위 안전)
// =======================================================

import { els } from "./dom_refs.js";
import { alertBox } from "./utils.js";
import { saveRows } from "./save.js";

const MAX_ROWS = 10;
let bound = false;

export function initInputRowEvents() {
  if (bound) return;
  bound = true;

  if (!els.inputTable) return;

  els.btnAddRow?.addEventListener("click", onAddRow);
  els.btnResetRows?.addEventListener("click", onResetRows);
  els.btnSaveRows?.addEventListener("click", onSaveRows);

  // 이벤트 위임(페이지 충돌 방지: root 범위 우선)
  const root = els.root || document;
  root.addEventListener("click", onRemoveRowDelegated);
  root.addEventListener("click", onOpenSearchDelegated);

  bindSearchUserSelectionEvents();

  const firstRow = els.inputTable.querySelector(".input-row");
  if (firstRow) fillRequesterInfo(firstRow);
}

export function resetInputSection() {
  if (!els.inputTable) return;

  const tbody = els.inputTable.querySelector("tbody");
  if (!tbody) return;

  tbody.querySelectorAll(".input-row").forEach((row, idx) => {
    if (idx > 0) row.remove();
  });

  const firstRow = tbody.querySelector(".input-row");
  if (!firstRow) return;

  clearRowInputs(firstRow);
  fillRequesterInfo(firstRow);
  clearTargetInfo(firstRow);
}

function setActiveRow(row) {
  if (!row) return;
  if (els.root) els.root.__activeInputRow = row;
  row.dataset.active = "1";
}
function getActiveRow() {
  return els.root?.__activeInputRow || els.inputTable?.querySelector('.input-row[data-active="1"]') || null;
}
function clearActiveRowMark() {
  els.inputTable?.querySelectorAll('.input-row[data-active="1"]').forEach((r) => delete r.dataset.active);
}

function onAddRow() {
  const tbody = els.inputTable?.querySelector("tbody");
  if (!tbody) return;

  const rows = tbody.querySelectorAll(".input-row");
  if (rows.length >= MAX_ROWS) {
    alertBox(`대상자는 한 번에 ${MAX_ROWS}명까지 입력 가능합니다.`);
    return;
  }

  const newRow = rows[0].cloneNode(true);

  clearRowInputs(newRow);
  fillRequesterInfo(newRow);
  clearTargetInfo(newRow);
  delete newRow.dataset.active;

  tbody.appendChild(newRow);
}

function onResetRows() {
  if (!confirm("입력 내용을 모두 초기화하시겠습니까?")) return;
  resetInputSection();
}

function onSaveRows() {
  saveRows();
}

function onRemoveRowDelegated(e) {
  const btn = e.target?.closest?.(".btnRemoveRow");
  if (!btn) return;

  const row = btn.closest(".input-row");
  if (!row) return;

  const tbody = els.inputTable?.querySelector("tbody");
  if (!tbody) return;

  const rows = tbody.querySelectorAll(".input-row");
  if (rows.length <= 1) {
    alertBox("행이 하나뿐이라 삭제할 수 없습니다.");
    return;
  }

  if (els.root?.__activeInputRow === row) els.root.__activeInputRow = null;
  row.remove();
}

function onOpenSearchDelegated(e) {
  const btn = e.target?.closest?.(".btnOpenSearch");
  if (!btn) return;

  const row = btn.closest(".input-row");
  if (!row) return;

  clearActiveRowMark();
  setActiveRow(row);
}

function bindSearchUserSelectionEvents() {
  const handler = (evt) => {
    const user = evt?.detail?.user || evt?.detail || null;
    if (!user) return;
    applySelectedUserToActiveRow(user);
  };

  window.addEventListener("userSelected", handler);
  document.addEventListener("userSelected", handler);
  window.addEventListener("searchUserSelected", handler);
}

function applySelectedUserToActiveRow(user) {
  const row = getActiveRow() || els.inputTable?.querySelector(".input-row");
  if (!row) return;

  const tgName = toStr(user.name);
  const tgId = toStr(user.id);
  setTargetDisplay(row, tgName, tgId);

  // 소속(변경전): affiliation_display 우선
  const aff = toStr(user.affiliation_display);
  const branch = toStr(user.branch);
  const tgBranchEl = row.querySelector('input[name="tg_branch"]') || row.querySelector(".tg_branch");
  if (tgBranchEl) tgBranchEl.value = aff || branch || "";

  const rank = toStr(user.rank);
  const tgRankEl = row.querySelector('input[name="tg_rank"]') || row.querySelector(".tg_rank");
  if (tgRankEl) tgRankEl.value = rank || "";

  clearActiveRowMark();
  if (els.root) els.root.__activeInputRow = row;
}

function fillRequesterInfo(row) {
  const user = window.currentUser || {};

  const rqNameEl = row.querySelector('input[name="rq_name"]');
  const rqIdEl = row.querySelector('input[name="rq_id"]');
  const rqBranchEl = row.querySelector('input[name="rq_branch"]');
  const rqDispEl = row.querySelector(".rq_display");

  const rqName = toStr(user.name);
  const rqId = toStr(user.id);
  const rqBranch = toStr(user.branch);

  if (rqNameEl) rqNameEl.value = rqName;
  if (rqIdEl) rqIdEl.value = rqId;
  if (rqBranchEl) rqBranchEl.value = rqBranch;

  if (rqDispEl) rqDispEl.value = fmtPerson(rqName, rqId);
}

function setTargetDisplay(rowEl, tgName, tgId) {
  const nameEl = rowEl.querySelector('input[name="tg_name"], .tg_name');
  const idEl = rowEl.querySelector('input[name="tg_id"], .tg_id');
  const dispEl = rowEl.querySelector(".tg_display");

  if (nameEl) nameEl.value = tgName || "";
  if (idEl) idEl.value = tgId || "";
  if (dispEl) dispEl.value = fmtPerson(tgName, tgId);
}

function clearRowInputs(row) {
  row.querySelectorAll("input").forEach((el) => {
    if (el.type === "checkbox") {
      el.checked = false;
      return;
    }
    el.value = "";
  });

  row.querySelectorAll("select").forEach((sel) => {
    sel.selectedIndex = 0;
  });
}

function clearTargetInfo(row) {
  const selectors = [
    'input[name="tg_name"]',
    'input[name="tg_id"]',
    ".tg_display",
    'input[name="tg_branch"]',
    'input[name="tg_rank"]',
    'input[name="chg_branch"]',
    'input[name="chg_rank"]',
    'input[name="memo"]',
    'input[name="or_flag"]',
  ];

  selectors.forEach((sel) => {
    const el = row.querySelector(sel);
    if (!el) return;

    if (el.type === "checkbox") el.checked = false;
    else el.value = "";
  });
}

function toStr(v) {
  return String(v ?? "").trim();
}

function fmtPerson(name, id) {
  const n = toStr(name);
  const i = toStr(id);
  if (n && i) return `${n}(${i})`;
  return n || i || "";
}

function getVal(root, selector) {
  const el = root.querySelector(selector);
  return toStr(el?.value);
}
