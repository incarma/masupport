// django_ma/static/js/partner/manage_structure/index.js
// =========================================================
// ✅ Manage Structure - Index (FINAL, 정리본)
// - manage_boot 초기화(boot/권한/auto payload)
// - 동적 import(fetch/input_rows) + STATIC_VERSION cache buster
// - 검색 버튼 1회 바인딩
// - autoLoad 단 1회만 수행 (reload stash 복구 우선)
// =========================================================

import { initManageBoot } from "../../common/manage_boot.js";
import { pad2 } from "../../common/manage/ym.js";

const FILTER_KEY = "__manage_structure_filters__";

/* ---------------------------------------------------------
   Helpers
--------------------------------------------------------- */
function toStr(v) {
  return String(v ?? "").trim();
}

function safeNum(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function buildYM(y, m) {
  return `${y}-${pad2(m)}`;
}

function getStaticV() {
  const v = toStr(window.STATIC_VERSION);
  return v ? `?v=${encodeURIComponent(v)}` : "";
}

/* ---------------------------------------------------------
   Dynamic module loader
--------------------------------------------------------- */
async function loadPageModules() {
  // ✅ ?v= 쿼리스트링 제거 — 버전마다 다른 모듈 인스턴스가 생성되어
  //    모듈 스코프 변수(delegationBound 등)가 각각 초기화되는 문제 방지
  //    캐시 무효화는 HTML <script> 태그의 ?v={% now 'U' %}로 충분함
  const [{ fetchData }, { initInputRowEvents }] = await Promise.all([
    import("./fetch.js"),
    import("./input_rows.js"),
  ]);
  return { fetchData, initInputRowEvents };
}

/* ---------------------------------------------------------
   Filter stash/restore (reload UX)
--------------------------------------------------------- */
function stashFiltersForReload() {
  try {
    const data = {
      y: toStr(document.getElementById("yearSelect")?.value),
      m: toStr(document.getElementById("monthSelect")?.value),
      channel: toStr(document.getElementById("channelSelect")?.value),
      part: toStr(document.getElementById("partSelect")?.value),
      branch: toStr(document.getElementById("branchSelect")?.value),
    };
    sessionStorage.setItem(FILTER_KEY, JSON.stringify(data));
  } catch (e) {
    console.warn("⚠️ stashFiltersForReload failed:", e);
  }
}

function restoreFiltersAfterReload() {
  try {
    const raw = sessionStorage.getItem(FILTER_KEY);
    if (!raw) return null;

    sessionStorage.removeItem(FILTER_KEY);

    const data = JSON.parse(raw || "{}");

    const ySel = document.getElementById("yearSelect");
    const mSel = document.getElementById("monthSelect");
    if (ySel && data.y) ySel.value = data.y;
    if (mSel && data.m) mSel.value = data.m;

    const channelSel = document.getElementById("channelSelect");
    const partSel = document.getElementById("partSelect");
    const branchSel = document.getElementById("branchSelect");
    if (channelSel && data.channel) channelSel.value = data.channel;
    if (partSel && data.part) partSel.value = data.part;
    if (branchSel && data.branch) branchSel.value = data.branch;

    return data;
  } catch (e) {
    console.warn("⚠️ restoreFiltersAfterReload failed:", e);
    return null;
  }
}

/* ---------------------------------------------------------
   Branch resolver (fetch scope)
--------------------------------------------------------- */
function getBranchForFetch(boot) {
  if (boot?.userGrade === "superuser") {
    return toStr(document.getElementById("branchSelect")?.value) || "";
  }
  return toStr(window.currentUser?.branch || "");
}

/* ---------------------------------------------------------
   UI helpers
--------------------------------------------------------- */
function showSections() {
  document.getElementById("inputSection")?.removeAttribute("hidden");
  document.getElementById("mainSheet")?.removeAttribute("hidden");
}

/* ---------------------------------------------------------
   Search binding
--------------------------------------------------------- */
function bindSearchButton(fetchData, boot) {
  const btn = document.getElementById("btnSearchPeriod") || document.getElementById("btnSearch");
  if (!btn || btn.__bound) return;
  btn.__bound = true;

  btn.addEventListener("click", async () => {
    const ySel = document.getElementById("yearSelect");
    const mSel = document.getElementById("monthSelect");

    const y = safeNum(ySel?.value, safeNum(boot?.currentYear, new Date().getFullYear()));
    const m = safeNum(mSel?.value, safeNum(boot?.currentMonth, new Date().getMonth() + 1));

    const ym = buildYM(y, m);
    const branch = getBranchForFetch(boot);

    if (boot?.userGrade === "superuser" && !branch) {
      alert("지점을 먼저 선택하세요.");
      return;
    }

    showSections();
    await fetchData(ym, branch);
  });
}

/* ---------------------------------------------------------
   Auto-load (once)
--------------------------------------------------------- */
async function runAutoLoadOnce(fetchData, boot) {
  if (window.__structureAutoLoaded) return;
  window.__structureAutoLoaded = true;

  // 1) reload 복구 우선
  const restored = restoreFiltersAfterReload();
  if (restored) {
    const y = safeNum(restored.y, safeNum(boot?.selectedYear || boot?.currentYear, new Date().getFullYear()));
    const m = safeNum(restored.m, safeNum(boot?.selectedMonth || boot?.currentMonth, new Date().getMonth() + 1));
    const ym = buildYM(y, m);

    const branch =
      boot?.userGrade === "superuser"
        ? toStr(restored.branch) || getBranchForFetch(boot)
        : getBranchForFetch(boot);

    if (boot?.userGrade === "superuser" && !branch) return;
    if (!branch) return;

    showSections();
    await fetchData(ym, branch);
    return;
  }

  // 2) manage_boot auto payload
  const payload = window.__manageBootAutoPayload?.structure || {};
  let ym = toStr(payload.ym || "");
  let branch = toStr(payload.branch || "");

  if (!ym) {
    const ySel = document.getElementById("yearSelect");
    const mSel = document.getElementById("monthSelect");
    const y = safeNum(ySel?.value, safeNum(boot?.selectedYear || boot?.currentYear, new Date().getFullYear()));
    const m = safeNum(mSel?.value, safeNum(boot?.selectedMonth || boot?.currentMonth, new Date().getMonth() + 1));
    ym = buildYM(y, m);
  }

  if (!branch) branch = getBranchForFetch(boot);

  if (boot?.userGrade === "superuser" && !branch) return;
  if (!branch) return;

  showSections();
  await fetchData(ym, branch);
}

/* ---------------------------------------------------------
   Expose helpers (optional usage)
--------------------------------------------------------- */
function exposeReloadHelpers() {
  window.__manageStructure = window.__manageStructure || {};
  window.__manageStructure.stashFiltersForReload = stashFiltersForReload;
}

/* ---------------------------------------------------------
   Init (IIFE)
--------------------------------------------------------- */
(async function init() {
  const ctx = initManageBoot("structure") || {};
  const boot = ctx.boot || window.ManageStructureBoot || {};

  exposeReloadHelpers();

  const { fetchData, initInputRowEvents } = await loadPageModules();

  try {
    initInputRowEvents();
  } catch (e) {
    console.error("❌ initInputRowEvents error:", e);
  }

  bindSearchButton(fetchData, boot);

  try {
    await runAutoLoadOnce(fetchData, boot);
  } catch (e) {
    console.error("❌ autoLoad fetch error:", e);
  }
})();
