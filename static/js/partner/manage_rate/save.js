// django_ma/static/js/partner/manage_rate/save.js
// ======================================================
// ✅ Manage Rate - Save
// - Validates rows
// - Resolves month/branch reliably (superuser branchSelect priority)
// - POST JSON
// - On success: reset input + re-fetch main sheet
// ======================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, pad2 } from "./utils.js";
import { fetchData } from "./fetch.js";
import { resetInputSection } from "./input_rows.js";

import { getCSRFToken } from "../../common/manage/csrf.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";
import { getDatasetUrl } from "../../common/manage/dataset.js";

/* ======================================================
   URL helpers (legacy keys supported)
====================================================== */
function pickUrl(root, keys = [], fallback = "") {
  // ✅ saveUrl/dataSaveUrl/data-data-save-url 후보 탐색 공통화
  return getDatasetUrl(root, keys, fallback);
}

function getRoot() {
  return els.root || document.getElementById("manage-rate") || document.querySelector("[id='manage-rate']");
}

function getSaveUrl(root) {
  return pickUrl(root, ["saveUrl", "dataSaveUrl", "dataDataSaveUrl"], "");
}

/* ======================================================
   Context: grade / branch / ym (same behavior)
====================================================== */
function getGrade(root) {
  return String(root?.dataset?.userGrade || window.currentUser?.grade || "").trim();
}

function getEffectiveBranch(root) {
  const grade = getGrade(root);

  if (grade === "superuser") {
    const v = String(els.branchSelect?.value || document.getElementById("branchSelect")?.value || "").trim();
    if (v) return v;
  }

  return (
    String(root?.dataset?.defaultBranch || "").trim() ||
    String(window.currentUser?.branch || "").trim() ||
    ""
  );
}

function getEffectiveYM(root) {
  const y =
    String(els.yearSelect?.value || document.getElementById("yearSelect")?.value || "").trim() ||
    String(root?.dataset?.selectedYear || "").trim();

  const mRaw =
    String(els.monthSelect?.value || document.getElementById("monthSelect")?.value || "").trim() ||
    String(root?.dataset?.selectedMonth || "").trim();

  const m = pad2(mRaw);
  const ym = `${y}-${m}`;

  if (!/^\d{4}-\d{2}$/.test(ym)) return "";
  return ym;
}

/* ======================================================
   Payload build (row validation identical)
====================================================== */
function buildPayloadFromRows(rows) {
  const payload = [];
  const seenTargets = new Set();

  for (const row of rows) {
    const rq_id = row.querySelector("[name='rq_id']")?.value.trim() || "";
    const rq_name = row.querySelector("[name='rq_name']")?.value.trim() || "";

    const tg_id = row.querySelector("[name='tg_id']")?.value.trim() || "";
    const tg_name = row.querySelector("[name='tg_name']")?.value.trim() || "";

    const after_ftable = row.querySelector("[name='after_ftable']")?.value.trim() || "";
    const after_ltable = row.querySelector("[name='after_ltable']")?.value.trim() || "";
    const memo = row.querySelector("[name='memo']")?.value.trim() || "";

    if (!tg_id) {
      alertBox("대상자를 선택해주세요.");
      return null;
    }

    if (!after_ftable || !after_ltable) {
      alertBox("변경후 손보/생보 테이블은 필수입니다.");
      return null;
    }

    if (seenTargets.has(tg_id)) {
      alertBox(`중복 대상자가 있습니다: ${tg_name || tg_id}`);
      return null;
    }
    seenTargets.add(tg_id);

    payload.push({
      requester_id: rq_id,
      requester_name: rq_name,
      target_id: tg_id,
      target_name: tg_name,
      after_ftable,
      after_ltable,
      memo,
    });
  }

  if (!payload.length) {
    alertBox("저장할 데이터가 없습니다.");
    return null;
  }

  return payload;
}

/* ======================================================
   Save (public)
====================================================== */
export async function saveRows() {
  const root = getRoot();
  const saveUrl = getSaveUrl(root);

  if (!saveUrl || saveUrl.includes("undefined")) {
    alertBox("저장 URL을 찾지 못했습니다. (data-save-url 확인)");
    return;
  }

  const rows = Array.from(els.inputTable?.querySelectorAll("tbody tr.input-row") || []);
  const payloadRows = buildPayloadFromRows(rows);
  if (!payloadRows) return;

  const month = getEffectiveYM(root);
  const branch = getEffectiveBranch(root);
  const part = String(window.currentUser?.part || "").trim();

  if (!month) return alertBox("월 정보가 올바르지 않습니다. (연도/월도 선택 상태 확인)");
  if (!branch) return alertBox("지점 정보가 없습니다. (superuser는 지점을 선택해야 합니다)");

  showLoading("저장 중...");

  try {
    const body = { rows: payloadRows, month, branch, part };

    const res = await fetch(saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });

    const result = await readJsonOrThrow(res, "저장 실패");
    if (!isSuccessJson(result) && result.ok !== true) {
      alertBox(result.message || "저장 중 오류가 발생했습니다.");
      return;
    }

    const count = result.saved_count ?? result.count ?? payloadRows.length;
    alertBox(`✅ ${count}건 저장 완료`);

    resetInputSection();

    // ✅ identical behavior: re-fetch using payload object
    await fetchData({
      ym: month,
      branch,
      grade: getGrade(root),
      level: String(root?.dataset?.userLevel || "").trim(),
      team_a: String(root?.dataset?.teamA || "").trim(),
      team_b: String(root?.dataset?.teamB || "").trim(),
      team_c: String(root?.dataset?.teamC || "").trim(),
    });
  } catch (err) {
    console.error("❌ [rate/save] error:", err);
    alertBox(err?.message || "저장 중 오류가 발생했습니다.");
  } finally {
    hideLoading();
  }
}
