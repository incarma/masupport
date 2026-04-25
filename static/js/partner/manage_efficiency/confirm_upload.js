// django_ma/static/js/partner/manage_efficiency/confirm_upload.js
//
// ✅ confirm_group_id 기반 업로드
// - 업로드 성공 시 서버가 confirm_group_id 생성하여 내려줌
// - UI: confirmFileName, confirmGroupId 세팅
// - (legacy confirmAttachmentId는 비움 or 유지 가능)

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, getCSRFToken, selectedYM } from "./utils.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

function str(v) {
  return String(v ?? "").trim();
}

function getRoot() {
  return els.root || document.getElementById("manage-efficiency");
}

function getUploadUrl() {
  const ds = getRoot()?.dataset || {};
  return str(ds.efficiencyConfirmUploadUrl || ds.efficiencyConfirmUpload || "");
}

function getGrade() {
  return str(window.currentUser?.grade || getRoot()?.dataset?.userGrade || "");
}

function getBranch() {
  const grade = getGrade();
  if (grade === "superuser") return str(els.branch?.value || "");
  return str(window.currentUser?.branch || getRoot()?.dataset?.branch || "");
}

function getPart() {
  return str(window.currentUser?.part || getRoot()?.dataset?.part || "");
}

export function initConfirmUploadHandlers() {
  if (window.__effConfirmUploadBound) return;
  window.__effConfirmUploadBound = true;

  const btn = els.btnConfirmUploadDo;
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const url = getUploadUrl();
    if (!url) return alertBox("업로드 URL이 없습니다. (data-efficiency-confirm-upload-url)");

    const file = els.confirmFileInput?.files?.[0];
    if (!file) return alertBox("업로드할 파일을 선택해주세요.");

    const ym = selectedYM(els.year, els.month);
    if (!ym) return alertBox("연도/월도를 확인해주세요.");

    const grade = getGrade();
    const branch = getBranch();
    const part = getPart();

    if (grade === "superuser" && !branch) return alertBox("지점을 먼저 선택하세요.");

    const fd = new FormData();
    fd.append("file", file);
    fd.append("month", ym);
    fd.append("branch", branch);
    fd.append("part", part);

    showLoading("확인서 업로드 중...");
    try {
      const res = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: fd,
      });

      const data = await readJsonOrThrow(res, "업로드 실패");
      if (!isSuccessJson(data)) throw new Error(data.message || "업로드 실패");

      const gid = str(data.confirm_group_id);
      const fileName = str(data.file_name);

      if (!gid) throw new Error("confirm_group_id가 내려오지 않았습니다.");

      if (els.confirmGroupId) els.confirmGroupId.value = gid;
      if (els.confirmFileName) els.confirmFileName.value = fileName || "업로드 완료";

      // legacy는 비움(정책: group 기반)
      if (els.confirmAttachmentId) els.confirmAttachmentId.value = "";

      alertBox(`✅ 업로드 완료\n그룹ID: ${gid}`);

      // 모달 닫기
      const modalEl = document.getElementById("confirmUploadModal");
      if (modalEl && window.bootstrap?.Modal) {
        const instance = window.bootstrap.Modal.getInstance(modalEl) || new window.bootstrap.Modal(modalEl);
        instance.hide();
      }
    } catch (e) {
      console.error(e);
      alertBox(e?.message || "업로드 중 오류");
    } finally {
      hideLoading();
    }
  });
}
