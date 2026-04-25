// django_ma/static/js/partner/manage_structure/save.js
// =========================================================
// ✅ Structure - Save (manage_rate/save.js 패턴 동일 적용)
// - pad2 import 추가 / selectedYM 제거(직접 구성으로 통일)
// - branch 빈 문자열 검증 / credentials 추가
// - 저장 성공 → resetInputSection → fetchData 재조회
// =========================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, getCSRFToken, pad2 } from "./utils.js";
import { fetchData } from "./fetch.js";
import { resetInputSection } from "./input_rows.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

/* =========================================================
   Small helpers
========================================================= */
function toStr(v) {
  return String(v ?? "").trim();
}

/* =========================================================
   URL helpers
========================================================= */
function getSaveUrl() {
  // ManageStructureBoot 우선, dataset 폴백
  const fromBoot = toStr(window.ManageStructureBoot?.dataSaveUrl);
  if (fromBoot) return fromBoot;
  return toStr(
    els.root?.dataset?.dataSaveUrl ||
    els.root?.dataset?.dataDataSaveUrl ||
    ""
  );
}

/* =========================================================
   Context: grade / branch / ym
   (manage_rate/save.js getEffectiveBranch/getEffectiveYM 동일 패턴)
========================================================= */
function getGrade() {
  return toStr(els.root?.dataset?.userGrade || window.currentUser?.grade || "");
}

function getEffectiveBranch() {
  if (getGrade() === "superuser") {
    return (
      toStr(els.branch?.value) ||
      toStr(document.getElementById("branchSelect")?.value) ||
      ""
    );
  }
  return (
    toStr(window.currentUser?.branch) ||
    toStr(els.root?.dataset?.defaultBranch) ||
    ""
  );
}

function getEffectiveYM() {
  const y =
    toStr(els.year?.value) ||
    toStr(els.root?.dataset?.selectedYear) ||
    toStr(window.ManageStructureBoot?.selectedYear) ||
    toStr(window.ManageStructureBoot?.currentYear) ||
    String(new Date().getFullYear());

  const mRaw =
    toStr(els.month?.value) ||
    toStr(els.root?.dataset?.selectedMonth) ||
    toStr(window.ManageStructureBoot?.selectedMonth) ||
    toStr(window.ManageStructureBoot?.currentMonth) ||
    String(new Date().getMonth() + 1);

  const ym = `${y}-${pad2(mRaw)}`;   // ✅ pad2 사용
  if (!/^\d{4}-\d{2}$/.test(ym)) return "";
  return ym;
}

/* =========================================================
   Payload build
========================================================= */
function buildPayload(rows) {
  const out = [];
  const seen = new Set();

  for (const row of rows) {
    const tg_id = toStr(row.querySelector("[name='tg_id']")?.value);
    const tg_name = toStr(row.querySelector("[name='tg_name']")?.value);

    if (!tg_id) {
      alertBox("대상자를 선택해주세요.");
      return null;
    }

    if (seen.has(tg_id)) {
      alertBox(`중복 대상자가 있습니다: ${tg_name || tg_id}`);
      return null;
    }
    seen.add(tg_id);

    out.push({
      requester_id: toStr(row.querySelector("[name='rq_id']")?.value),
      requester_name: toStr(row.querySelector("[name='rq_name']")?.value),
      target_id: tg_id,
      target_name: tg_name,
      tg_branch: toStr(row.querySelector("[name='tg_branch']")?.value),
      tg_rank: toStr(row.querySelector("[name='tg_rank']")?.value),
      chg_branch: toStr(row.querySelector("[name='chg_branch']")?.value),
      chg_rank: toStr(row.querySelector("[name='chg_rank']")?.value),
      memo: toStr(row.querySelector("[name='memo']")?.value),
      or_flag: !!row.querySelector("[name='or_flag']")?.checked,
    });
  }

  if (!out.length) {
    alertBox("저장할 데이터가 없습니다.");
    return null;
  }

  return out;
}

/* =========================================================
   Save (public) — manage_rate/save.js 동일 구조
========================================================= */
export async function saveRows() {
  const saveUrl = getSaveUrl();
  if (!saveUrl || saveUrl.includes("undefined")) {
    alertBox("저장 URL을 찾지 못했습니다. (ManageStructureBoot.dataSaveUrl 확인)");
    return;
  }

  const rows = Array.from(
    els.inputTable?.querySelectorAll("tbody tr.input-row") || []
  );
  const payloadRows = buildPayload(rows);
  if (!payloadRows) return;  // 유효성 실패 — alertBox는 buildPayload 내부에서 표시

  const month = getEffectiveYM();
  const branch = getEffectiveBranch();
  const part = toStr(window.currentUser?.part) || "-";

  if (!month) {
    alertBox("월 정보가 올바르지 않습니다. (연도/월도 선택 상태 확인)");
    return;
  }
  if (!branch) {
    alertBox("지점 정보가 없습니다. (superuser는 지점을 선택해야 합니다)");
    return;
  }

  showLoading("저장 중...");

  try {
    const res = await fetch(saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",   // ✅ manage_rate/save.js 동일
      body: JSON.stringify({ rows: payloadRows, month, branch, part }),
    });

    const result = await readJsonOrThrow(res, "저장 실패");
    if (!isSuccessJson(result)) {
      alertBox(result.message || "저장 중 오류가 발생했습니다.");
      return;
    }

    // ✅ alert 블로킹 완전 제거
    //    alert → DOM 조작 → dt.draw() 순서에서 DataTables 렌더가 깨지는 원인
    //    loading 오버레이로 비블로킹 피드백 대체
    resetInputSection();
    await fetchData(month, branch);

    // 재조회 완료 후 비블로킹 메시지 (로딩 오버레이 1.5초 재활용)
    const count = result.saved_count ?? result.count ?? payloadRows.length;
    showLoading(`✅ ${count}건 저장 완료`);
    setTimeout(() => hideLoading(), 1500);

    document.getElementById("mainSheet")?.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    console.error("❌ [structure/save] error:", err);
    alertBox(err?.message || "저장 중 오류가 발생했습니다.");
  } finally {
    // ✅ showLoading(완료 메시지) 이후 setTimeout hideLoading과 충돌하지 않도록
    //    finally에서는 hideLoading 호출하지 않음
    // 
  }
}