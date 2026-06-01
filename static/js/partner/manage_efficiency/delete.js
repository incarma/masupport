// django_ma/static/js/partner/manage_efficiency/delete.js
// =========================================================
// ✅ Delete handlers (event delegation, single bind) FINAL
// - data-action="delete-row"   + data-row-id="..."
// - data-action="delete-group" + data-group-id="confirm_group_id(or group_key)"
// - dataset URL 키 혼재 대비(여러 후보 OR)
// - superuser/head/leader 브랜치 탐색 통합
// - 삭제 후: 마지막 조회 캐시(__lastEfficiencyYM/__lastEfficiencyBranch) 우선 재조회
// - ❗payload 키 통일:
//    · row: { id }
//    · group: { group_id }  (fetch.js / views.py 기준과 통일)
// =========================================================

import { showLoading, hideLoading, alertBox, getCSRFToken } from "./utils.js";
import { fetchData } from "./fetch.js";
import { els } from "./dom_refs.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";
import { getDatasetValue } from "../../common/manage/dataset.js";
import { toStr } from "../../common/manage/text.js";

function str(v) {
  return toStr(v);
}

function getRoot() {
  return (
    els.root ||
    document.getElementById("manage-efficiency") ||
    document.getElementById("manage-calculate") ||
    document.getElementById("manage-structure") ||
    null
  );
}

function dsPick(ds, keys) {
  // ✅ 기존 호출부 호환: dataset 객체만 들어오므로 임시 root 객체로 감싸서 공통 resolver 사용
  return getDatasetValue({ dataset: ds }, keys, "");
}

function getDeleteRowUrl() {
  const ds = getRoot()?.dataset || {};
  return dsPick(ds, ["dataDeleteRowUrl", "deleteRowUrl", "dataDataDeleteRowUrl", "dataDeleteRow"]);
}

function getDeleteGroupUrl() {
  const ds = getRoot()?.dataset || {};
  return dsPick(ds, ["dataDeleteGroupUrl", "deleteGroupUrl", "dataDataDeleteGroupUrl", "dataDeleteGroup"]);
}

function getUserGrade() {
  const root = getRoot();
  return str(root?.dataset?.userGrade) || str(window?.currentUser?.grade);
}

function getBranchSmart() {
  const root = getRoot();
  const grade = getUserGrade();
  const user = window?.currentUser || {};
  const boot = window?.ManageefficiencyBoot || {};

  // superuser는 select 우선
  if (grade === "superuser") {
    return (
      str(els.branch?.value) ||
      str(root?.dataset?.branch) ||
      str(user.branch) ||
      str(boot.branch) ||
      ""
    );
  }

  // main/sub는 user.branch 우선 (select가 없을 수 있음)
  return (
    str(user.branch) ||
    str(boot.branch) ||
    str(root?.dataset?.branch) ||
    str(root?.dataset?.userBranch) ||
    ""
  );
}

function getYMSmart() {
  // select가 있으면 사용
  const y = str(els.year?.value);
  const m = str(els.month?.value);
  if (y && m) return `${y}-${m.padStart(2, "0")}`;

  // 마지막 조회 캐시 fallback
  return str(window.__lastEfficiencyYM);
}

async function refreshAfterDelete() {
  const ym = str(window.__lastEfficiencyYM) || getYMSmart();
  const br = str(window.__lastEfficiencyBranch) || getBranchSmart();
  if (ym && br) await fetchData(ym, br);
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    credentials: "same-origin",
    body: JSON.stringify(body || {}),
  });

  const data = await readJsonOrThrow(res, "요청 실패");
  if (!isSuccessJson(data)) throw new Error(data.message || "요청 실패");
  return data;
}

function getClickContainer() {
  // ✅ 아코디언 영역으로 이벤트 위임 범위를 제한(전역 document 클릭 방지)
  return (
    document.getElementById("confirmGroupsAccordion") ||
    document.getElementById("confirmGroups") ||
    getRoot() ||
    document
  );
}

export function attachEfficiencyDeleteHandlers() {
  const root = getRoot();
  if (!root) return;

  const container = getClickContainer();

  // ✅ 중복 바인딩 방지(컨테이너 기준)
  if (container.dataset.effDeleteInited === "1") return;
  container.dataset.effDeleteInited = "1";

  container.addEventListener("click", async (e) => {
    const btn = e.target?.closest?.("button[data-action]");
    if (!btn) return;

    const action = str(btn.dataset.action);

    // -------------------------------------------------
    // ✅ Row delete
    // -------------------------------------------------
    if (action === "delete-row") {
      const rowId = str(btn.dataset.rowId);
      if (!rowId) return;

      // leader이면 disabled 처리되어야 하지만 혹시 몰라서 한번 더 방어
      if (getUserGrade() === "leader") return;

      if (!confirm("해당 행을 삭제할까요?")) return;

      const url = getDeleteRowUrl();
      if (!url) return alertBox("행 삭제 URL이 없습니다. (data-data-delete-row-url 확인)");

      try {
        showLoading("삭제 중...");
        btn.disabled = true;

        await postJson(url, { id: rowId });
        await refreshAfterDelete();
      } catch (err) {
        console.error(err);
        alertBox(err?.message || "삭제 중 오류");
      } finally {
        btn.disabled = false;
        hideLoading();
      }
      return;
    }

    // -------------------------------------------------
    // ✅ Group delete
    // -------------------------------------------------
    if (action === "delete-group") {
      const gid = str(btn.dataset.groupId);
      if (!gid) return;

      // leader은 UI에서 버튼이 없어야 함. 그래도 방어
      if (getUserGrade() === "leader") return;

      if (!confirm("이 그룹 전체를 삭제할까요?\n(그룹 내 저장된 행/첨부도 함께 삭제됩니다)")) return;

      const url = getDeleteGroupUrl();
      if (!url) return alertBox("그룹 삭제 URL이 없습니다. (data-data-delete-group-url 확인)");

      try {
        showLoading("그룹 삭제 중...");
        btn.disabled = true;

        // ✅ payload 키 통일: group_id
        await postJson(url, { group_id: gid });
        await refreshAfterDelete();
      } catch (err) {
        console.error(err);
        alertBox(err?.message || "그룹 삭제 중 오류");
      } finally {
        btn.disabled = false;
        hideLoading();
      }
    }
  });
}
