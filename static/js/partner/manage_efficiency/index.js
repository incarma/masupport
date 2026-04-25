// django_ma/static/js/partner/manage_efficiency/index.js
// =========================================================
// ✅ Manage Efficiency Entry (FINAL)
// - root 1회 초기화 가드 (중복 바인딩 방지)
// - ManageBoot(efficiency) 연동 (실패해도 동작)
// - 입력행/확인서 업로드 핸들러 연결
// - 검색(runSearch): YM/Branch 검증 + 섹션 오픈 + fetchData
// - 자동검색: head/leader 기본 autoLoad
// - superuser: branch change 시 자동 재조회
// - (선택) accordion 헤더 버튼(다운로드/삭제) 클릭 시 토글 전파 차단 + 다운로드 처리
// =========================================================

import { els } from "./dom_refs.js";
import { initInputRowEvents } from "./input_rows.js";
import { initManageBoot } from "../../common/manage_boot.js";
import { initConfirmUploadHandlers } from "./confirm_upload.js";
import { attachEfficiencyDeleteHandlers } from "./delete.js";

// ---------------------------------------------------------
// Debug
// ---------------------------------------------------------
const DEBUG = false;
const log = (...a) => DEBUG && console.log("[efficiency/index]", ...a);
const warn = (...a) => console.warn("[efficiency/index]", ...a);
const err = (...a) => console.error("[efficiency/index]", ...a);

// ---------------------------------------------------------
// Utils
// ---------------------------------------------------------
function str(v) {
  return String(v ?? "").trim();
}
function pad2(v) {
  const s = str(v);
  return s ? s.padStart(2, "0") : "";
}
function onReady(fn) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fn, { once: true });
  } else {
    fn();
  }
}

function getRoot() {
  return (
    els.root ||
    document.getElementById("manage-efficiency") ||
    document.getElementById("manage-calculate") ||
    null
  );
}

function ensureInitedOnce(root) {
  if (!root) return false;
  if (root.dataset.inited === "1") return false;
  root.dataset.inited = "1";
  return true;
}

function openSections() {
  if (els.inputSection) els.inputSection.hidden = false;
  if (els.mainSheet) els.mainSheet.hidden = false;
}

// ---------------------------------------------------------
// (Optional) Accordion Header Button Event Delegation
// - 목적: 다운로드/삭제 버튼 클릭 시 아코디언 토글이 같이 동작하는 문제 방지
// - 다운로드: data-url 있으면 새창으로 open
// - 삭제: 여기서는 "전파 차단 + 커스텀 이벤트 발행"까지만 안전하게 처리
//   (삭제 API는 프로젝트마다 달라서 fetch.js/confirm_upload.js 쪽에서 받는 걸 권장)
// ---------------------------------------------------------
function initAccordionHeaderActions(root) {
  const acc =
    document.getElementById("confirmGroupsAccordion") ||
    document.getElementById("confirmGroups");
  if (!acc) return;

  // 중복 바인딩 방지
  if (acc.dataset.headerActionsInited === "1") return;
  acc.dataset.headerActionsInited = "1";

  acc.addEventListener("click", (e) => {
    const btn = e.target?.closest?.(
      ".btnConfirmDownload, .btnConfirmDelete, [data-confirm-download], [data-confirm-delete]"
    );
    if (!btn) return;

    // ✅ 버튼 클릭이 아코디언 토글로 전파되지 않도록
    e.stopPropagation();

    // ✅ 다운로드
    const url = btn.dataset?.url || btn.getAttribute("data-url");
    const isDownload =
      btn.classList.contains("btnConfirmDownload") ||
      btn.hasAttribute("data-confirm-download");

    if (isDownload) {
      if (!url) return;
      window.open(url, "_blank");
      return;
    }

    // ✅ 삭제 (커스텀 이벤트로 위임)
    const isDelete =
      btn.classList.contains("btnConfirmDelete") ||
      btn.hasAttribute("data-confirm-delete");

    if (isDelete) {
      const groupId = btn.dataset?.groupId || btn.getAttribute("data-group-id") || "";
      const attachmentId =
        btn.dataset?.attachmentId || btn.getAttribute("data-attachment-id") || "";

      // 실제 삭제 처리(fetch)는 confirm_upload.js 또는 fetch.js 쪽에서
      // 아래 이벤트를 받아 수행하도록 권장
      const ev = new CustomEvent("efficiency:confirmDelete", {
        bubbles: true,
        detail: {
          groupId: str(groupId),
          attachmentId: str(attachmentId),
        },
      });
      root.dispatchEvent(ev);
    }
  });
}

// ---------------------------------------------------------
// Main
// ---------------------------------------------------------
onReady(() => {
  const root = getRoot();
  if (!root) {
    err("⚠️ manage-efficiency root 요소를 찾을 수 없습니다.");
    return;
  }
  if (!ensureInitedOnce(root)) return;

  attachEfficiencyDeleteHandlers();

  // 1) ManageBoot 연동(실패해도 동작)
  let ctx = {};
  try {
    ctx = initManageBoot("efficiency") || {};
  } catch (e) {
    warn("⚠️ initManageBoot('efficiency') 실패(무시):", e);
    ctx = {};
  }

  const boot = ctx.boot || window.ManageefficiencyBoot || {};
  const user = ctx.user || window.currentUser || {};

  const grade = () => str(user.grade || root.dataset.userGrade);

  const getYM = () => {
    const y = str(els.year?.value);
    const m = pad2(els.month?.value);
    return y && m ? `${y}-${m}` : "";
  };

  const getBranch = () => {
    const g = grade();

    // superuser는 셀렉트 우선(없으면 dataset/user fallback)
    if (g === "superuser") {
      return str(els.branch?.value) || str(root.dataset.branch) || str(user.branch) || "";
    }

    // head/leader는 user.branch 우선
    return (
      str(user.branch) ||
      str(boot.branch) ||
      str(root.dataset.branch) ||
      str(root.dataset.userBranch) ||
      ""
    );
  };

  // 2) 모듈 초기화 (safe)
  try {
    initInputRowEvents();
    log("✅ initInputRowEvents OK");
  } catch (e) {
    err("❌ initInputRowEvents 오류:", e);
  }

  try {
    initConfirmUploadHandlers();
    log("✅ initConfirmUploadHandlers OK");
  } catch (e) {
    err("❌ initConfirmUploadHandlers 오류:", e);
  }

  // (선택) 헤더 버튼 전파 차단/다운로드 처리
  try {
    initAccordionHeaderActions(root);
  } catch (e) {
    warn("⚠️ initAccordionHeaderActions 실패(무시):", e);
  }

  // 3) 검색 실행
  async function runSearch(trigger = "click") {
    const ym = getYM();
    const br = getBranch();
    const g = grade();

    if (!ym) { alert("연도/월도를 확인해주세요."); return; }
    if (g === "superuser") {
      if (!els.branch) { alert("지점 선택 UI가 없습니다. (superuser 템플릿 조건 확인)"); return; }
      if (!str(els.branch.value)) { alert("지점을 먼저 선택하세요."); return; }
    }
    if (!br) { alert("지점 정보를 확인할 수 없습니다. (권한/부서/지점 설정 확인)"); return; }

    openSections();

    // ✅ 캐시 버스터
    const v = root.dataset.staticVersion || String(Date.now());
    const mod = await import(`./fetch.js?v=${encodeURIComponent(v)}`);
    await mod.fetchData(ym, br);
  }

  // 4) 이벤트 바인딩
  const btnSearch = els.btnSearch || els.btnSearchPeriod || document.getElementById("btnSearchPeriod");
  btnSearch?.addEventListener("click", () => {
    runSearch("click").catch((e) => err("❌ runSearch(click) 실패:", e));
  });

  // 5) 자동조회 정책
  const g = grade();
  const shouldAuto =
    typeof boot.autoLoad === "boolean" ? boot.autoLoad : ["head", "leader"].includes(g);

  if (shouldAuto && ["head", "leader"].includes(g)) {
    runSearch("auto").catch((e) => err("❌ runSearch(auto) 실패:", e));
  }

  // 6) superuser: branch change 재조회
  if (els.branch && grade() === "superuser") {
    els.branch.addEventListener("change", () => {
      if (!str(els.branch.value)) return;
      runSearch("branch-change").catch((e) => err("❌ runSearch(branch-change) 실패:", e));
    });
  }

  // 7) (옵션) superuser: part 변경 시 branch 초기화되면 자동검색 막기
  // - part_branch_selector.js가 branch를 disabled/empty로 만들 수 있으므로
  //   여기서는 추가 처리 불필요 (branch-change에서 값 없는 경우 return 처리함)
});
