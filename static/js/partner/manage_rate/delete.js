// django_ma/static/js/partner/manage_rate/delete.js
// ======================================================
// ✅ 요율변경 - 삭제 로직 (FINAL)
// - superuser/head: 삭제 가능
// - leader: 삭제 불가 (버튼 자체는 fetch.js에서 렌더 X + 바인딩도 X)
// - 삭제 후 현재 조건으로 재조회
// ======================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, selectedYM } from "./utils.js";
import { fetchData } from "./fetch.js";

import { getCSRFToken } from "../../common/manage/csrf.js";
import { getDatasetUrl } from "../../common/manage/dataset.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

const BOUND_KEY = "rateDeleteBound";

/* ======================================================
   grade/branch/ym helpers
====================================================== */
function getGrade() {
  return String(els.root?.dataset?.userGrade || window.currentUser?.grade || "").trim();
}

function canDelete() {
  const g = getGrade();
  return g === "superuser" || g === "head";
}

function getEffectiveBranch() {
  const grade = getGrade();
  if (grade === "superuser") return String(els.branchSelect?.value || "").trim();
  return String(window.currentUser?.branch || els.root?.dataset?.defaultBranch || "").trim();
}

function buildFetchPayload() {
  const ym = selectedYM(els.yearSelect, els.monthSelect);
  return {
    ym,
    branch: getEffectiveBranch(),
    grade: getGrade(),
    level: String(els.root?.dataset?.userLevel || "").trim(),
    team_a: String(els.root?.dataset?.teamA || "").trim(),
    team_b: String(els.root?.dataset?.teamB || "").trim(),
    team_c: String(els.root?.dataset?.teamC || "").trim(),
  };
}

/* ======================================================
   URL helpers
====================================================== */
function getDeleteUrl() {
  return getDatasetUrl(els.root, ["deleteUrl", "dataDeleteUrl", "deleteURL", "dataDeleteURL"]);
}

/* ======================================================
   Event binding (once)
====================================================== */
export function attachDeleteHandlers() {
  if (!els.root) return;

  // ✅ leader는 버튼도 없고, 이벤트 바인딩 자체도 불필요
  if (!canDelete()) return;

  // ✅ 중복 바인딩 방지
  if (els.root.dataset[BOUND_KEY] === "1") return;
  els.root.dataset[BOUND_KEY] = "1";

  document.addEventListener("click", handleDeleteClick);
}

/* ======================================================
   Click handler
====================================================== */
async function handleDeleteClick(e) {
  const btn = e.target?.closest?.(".btnDeleteRow");
  if (!btn || !els.root) return;

  // ✅ 방어: 혹시 DOM이 생겼더라도 권한 없으면 즉시 차단
  if (!canDelete()) {
    alertBox("삭제 권한이 없습니다.");
    return;
  }

  const id = String(btn.dataset.id || "").trim();
  if (!id) return;

  if (!confirm("해당 데이터를 삭제하시겠습니까?")) return;

  const deleteUrl = getDeleteUrl();
  if (!deleteUrl) {
    alertBox("삭제 URL이 설정되어 있지 않습니다. (data-delete-url 확인)");
    return;
  }

  showLoading("삭제 중...");

  try {
    const res = await fetch(deleteUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify({ id }),
    });

    const data = await readJsonOrThrow(res, "삭제 실패");
    if (!isSuccessJson(data)) throw new Error(data.message || "삭제 실패");

    alertBox("삭제가 완료되었습니다.");

    // ✅ 삭제 후 재조회
    await fetchData(buildFetchPayload());
  } catch (err) {
    console.error("❌ [rate/delete] 오류:", err);
    alertBox(err?.message || "삭제 중 오류가 발생했습니다.");
  } finally {
    hideLoading();
  }
}
