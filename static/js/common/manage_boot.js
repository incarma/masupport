// django_ma/static/js/common/manage_boot.js
// =========================================================
// ✅ Manage Boot (FINAL - No Selector Ownership / No Fetch)
// - Context별 root/boot 자동 탐색
// - Firefox select value set 안정화(옵션 보장 → value set)
// - ✅ superuser: 부문/부서/지점 로드는 part_branch_selector.js에 "위임" (충돌 방지)
// - ✅ fetch 실행은 하지 않는다 (각 페이지 index.js가 단독 실행)
// - autoLoad payload(ym/branch)를 window.__manageBootAutoPayload에 저장
// - BFCache/pageshow 포함 중복 초기화 방지
// - (옵션) inputTable 말줄임 + hover 툴팁(title) 동기화 유틸 제공
// =========================================================

import { pad2 } from "./manage/ym.js";

console.log("✅ manage_boot.js LOADED", {
  build: "2026-01-26-manageboot-final-guarded-selector-delegation",
  url: import.meta?.url,
}); 

/* =========================================================
   Global guards / namespaces
========================================================= */
const g = window;

g.__manageBootInited = g.__manageBootInited || {};
g.__manageBootCtx = g.__manageBootCtx || {};
g.__manageBootPartsLoaded = g.__manageBootPartsLoaded || {};
g.__manageBootAutoPayload = g.__manageBootAutoPayload || {};

/* =========================================================
   Ready helper
========================================================= */
function onReady(fn) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fn, { once: true });
  } else {
    fn();
  }
}

/* =========================================================
   Small utils
========================================================= */
function toStr(v) {
  return String(v ?? "").trim();
}
function readNumber(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function nowYM() {
  const d = new Date();
  return { y: d.getFullYear(), m: d.getMonth() + 1 };
}
function getGrade(user, root) {
  return toStr(user?.grade || root?.dataset?.userGrade);
}
function getBranch({ user, boot, root }) {
  return (
    toStr(user?.branch) ||
    toStr(boot?.branch) ||
    toStr(root?.dataset?.branch) ||
    toStr(root?.dataset?.userBranch) ||
    toStr(root?.dataset?.defaultBranch) ||
    ""
  );
}

/* =========================================================
   Context resolver
========================================================= */
function resolveRootId(ctxName) {
  if (ctxName === "structure") return "manage-structure";
  if (ctxName === "rate") return "manage-rate";
  if (ctxName === "efficiency") return "manage-efficiency";
  if (ctxName === "grades") return "manage-grades";
  if (ctxName === "table") return "manage-table";
  return null;
}

function resolveBoot(ctxName) {
  if (ctxName === "structure") return g.ManageStructureBoot || {};
  if (ctxName === "rate") return g.ManageRateBoot || {};
  if (ctxName === "efficiency") return g.ManageEfficiencyBoot || g.ManageefficiencyBoot || {};
  if (ctxName === "grades") return g.ManageGradesBoot || {};
  if (ctxName === "table") return g.ManageTableBoot || {};
  return {};
}

/* =========================================================
   Firefox-safe select init
========================================================= */
function ensureYearOptions(el, baseYear) {
  if (!el) return;
  if (el.options && el.options.length > 0) return;

  const y = Number(baseYear) || new Date().getFullYear();
  for (let yy = y - 2; yy <= y + 1; yy++) {
    const opt = document.createElement("option");
    opt.value = String(yy);
    opt.textContent = `${yy}년`;
    el.appendChild(opt);
  }
}

function ensureMonthOptions(el) {
  if (!el) return;
  if (el.options && el.options.length > 0) return;

  for (let mm = 1; mm <= 12; mm++) {
    const opt = document.createElement("option");
    opt.value = String(mm);
    opt.textContent = `${mm}월`;
    el.appendChild(opt);
  }
}

function setSelectValueSafe(el, value) {
  if (!el) return false;
  const v = toStr(value);
  if (!v) return false;

  const has = Array.from(el.options || []).some((o) => o.value === v);
  if (!has) return false;

  el.value = v;
  return true;
}

/* =========================================================
   Desired YM (Boot 우선)
========================================================= */
function getDesiredYM({ root, boot }) {
  const ds = root?.dataset || {};
  const { y: ny, m: nm } = nowYM();

  const y =
    readNumber(boot?.selectedYear, NaN) ||
    readNumber(boot?.currentYear, NaN) ||
    readNumber(ds?.selectedYear, NaN) ||
    readNumber(ds?.currentYear, NaN) ||
    ny;

  const m =
    readNumber(boot?.selectedMonth, NaN) ||
    readNumber(boot?.currentMonth, NaN) ||
    readNumber(ds?.selectedMonth, NaN) ||
    readNumber(ds?.currentMonth, NaN) ||
    nm;

  return { y, m };
}

function initYearMonthSelects({ root, boot }) {
  const yearEl = document.getElementById("yearSelect");
  const monthEl = document.getElementById("monthSelect");
  if (!yearEl || !monthEl) return { ok: false, yearEl, monthEl };

  const { y, m } = getDesiredYM({ root, boot });

  ensureYearOptions(yearEl, y);
  ensureMonthOptions(monthEl);

  const okY = setSelectValueSafe(yearEl, y);
  const okM = setSelectValueSafe(monthEl, m);

  // Firefox 등에서 초기 연동을 위해 change 이벤트 1회
  if (okY) yearEl.dispatchEvent(new Event("change", { bubbles: true }));
  if (okM) monthEl.dispatchEvent(new Event("change", { bubbles: true }));

  console.log("✅ [ManageBoot] year/month init:", {
    desiredY: y,
    desiredM: m,
    yearValue: yearEl.value,
    monthValue: monthEl.value,
    okY,
    okM,
  });

  return { ok: okY && okM, yearEl, monthEl };
}

function computeYMFromSelect({ root, boot }) {
  const yearEl = document.getElementById("yearSelect");
  const monthEl = document.getElementById("monthSelect");

  const { y, m } = getDesiredYM({ root, boot });
  const yy = toStr(yearEl?.value || y);
  const mm = pad2(toStr(monthEl?.value || m));
  return `${yy}-${mm}`;
}

/* =========================================================
   Show sections (payload 준비용: 보여주기만)
========================================================= */
function showSections() {
  document.getElementById("inputSection")?.removeAttribute("hidden");
  document.getElementById("mainSheet")?.removeAttribute("hidden");
}

/* =========================================================
   ✅ superuser selector loader delegation (충돌 없는 최종 가드)
   - manage_boot는 "부문/부서/지점" 로딩 로직을 소유하지 않는다.
   - part_branch_selector.js가 2단/3단을 알아서 처리하므로
     여기서는 window.loadPartsAndBranches(rootId)만 1회 호출한다.
========================================================= */
function delegateSelectorsToPartBranchSelectorOnce(rootId) {
  if (!rootId) return;

  // rootId 기준 1회만
  if (g.__manageBootPartsLoaded[rootId]) return;
  g.__manageBootPartsLoaded[rootId] = true;

  const MAX_RETRY = 12;
  const RETRY_MS = 250;

  const tryLoad = async (retry = 0) => {
    // ✅ 채널 셀렉트가 있든 없든 part_branch_selector가 판단한다.
    const fn = g.loadPartsAndBranches;

    if (typeof fn !== "function") {
      if (retry < MAX_RETRY) {
        console.warn(`⏳ [ManageBoot] loadPartsAndBranches 대기중 (${retry + 1}/${MAX_RETRY})`);
        setTimeout(() => tryLoad(retry + 1), RETRY_MS);
        return;
      }
      console.error("🚨 [ManageBoot] loadPartsAndBranches 함수가 정의되지 않았습니다.");
      return;
    }

    try {
      console.log("➡️ [ManageBoot] selector 로더 위임 호출:", { rootId });
      await fn(rootId);
      console.log("✅ [ManageBoot] selector 로더 위임 완료:", { rootId });
    } catch (e) {
      console.error("❌ [ManageBoot] selector 로더 위임 실패:", e);
    }
  };

  // part_branch_selector가 DOMContentLoaded에서 붙을 수도 있으니 약간 지연
  setTimeout(() => tryLoad(0), 150);
}

/* =========================================================
   (옵션) 말줄임 + hover 툴팁(title) 동기화
========================================================= */
export function bindEllipsisTooltips(root = document) {
  const host = root?.querySelector?.("#inputTable") ? root : document;
  const table = host.querySelector("#inputTable");
  if (!table) return;

  const syncTitle = (el) => {
    if (!el) return;
    let t = "";
    if (el.tagName === "SELECT") {
      const opt = el.options?.[el.selectedIndex];
      t = toStr(opt?.textContent || el.value);
    } else {
      t = toStr(el.value);
    }
    el.title = t;
  };

  table.querySelectorAll("input, select, textarea").forEach((el) => {
    syncTitle(el);
    el.addEventListener("input", () => syncTitle(el));
    el.addEventListener("change", () => syncTitle(el));
  });
}

/* =========================================================
   ✅ initManageBoot (NO FETCH)
   - index.js에서 fetch 실행
========================================================= */
export function initManageBoot(contextName) {
  const ctxName = toStr(contextName);
  if (!ctxName) return null;

  // 컨텍스트별 1회만 (BFCache에서도 재호출될 수 있으니, index.js는 별도 1회가드 권장)
  const rootId = resolveRootId(ctxName);
  const rootGuardKey = rootId ? `${ctxName}:${rootId}` : ctxName;

  if (g.__manageBootInited[rootGuardKey]) {
    return g.__manageBootCtx[ctxName] || {};
  }
  g.__manageBootInited[rootGuardKey] = true;

  const root = rootId ? document.getElementById(rootId) : null;

  if (!root) {
    console.warn(`⚠️ [ManageBoot] root 없음: ${rootId || ctxName}`, { ctxName, rootId });
    g.__manageBootCtx[ctxName] = {};
    return null;
  }

  const boot = resolveBoot(ctxName);
  const user = g.currentUser || {};
  const ctxObj = { root, boot, user };
  g.__manageBootCtx[ctxName] = ctxObj;

  console.group(`🔧 [ManageBoot] 초기화 (${ctxName})`);
  console.log("ROOT:", root);
  console.log("BOOT:", boot);
  console.log("USER:", user);

  // ✅ superuser: selector 로더는 part_branch_selector.js에 위임 (충돌 방지)
  onReady(() => {
    const grade = getGrade(user, root);
    if (grade === "superuser") {
      delegateSelectorsToPartBranchSelectorOnce(rootId);
    }
  });

  // year/month init + autoload payload 준비
  onReady(() => {
    const grade = getGrade(user, root);

    const autoLoad =
      typeof boot.autoLoad === "boolean"
        ? boot.autoLoad
        : ["head", "leader"].includes(grade);

    initYearMonthSelects({ root, boot });

    // ✅ payload는 head/leader만 자동 준비
    if (!autoLoad || !["head", "leader"].includes(grade)) {
      console.log("🟡 [ManageBoot] autoLoad payload skip:", { ctxName, grade, autoLoad });
      console.groupEnd();
      return;
    }

    const ym = computeYMFromSelect({ root, boot });
    const branch = getBranch({ user, boot, root });

    if (!branch) {
      console.warn("⚠️ [ManageBoot] autoLoad payload 중단: branch 없음", {
        ctxName,
        grade,
        boot,
        ds: root.dataset,
      });
      console.groupEnd();
      return;
    }

    // ✅ show는 해도 되지만, fetch는 index.js가 수행
    showSections();

    g.__manageBootAutoPayload[ctxName] = { ym, branch };
    console.log("🟢 [ManageBoot] autoLoad payload ready:", { ctxName, ym, branch });

    console.groupEnd();
  });

  return ctxObj;
}
