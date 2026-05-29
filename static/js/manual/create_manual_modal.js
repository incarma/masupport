// django_ma/static/js/manual/create_manual_modal.js
// ============================================================================
// Create Manual Modal
// - 매뉴얼 생성 전용
// - CSRF / access radio / redirect 처리
// ============================================================================

(() => {
  function initCreateManualModal() {
    const S = window.ManualShared;
    if (!S) {
      console.error("[create_manual_modal] ManualShared not loaded");
      return;
    }

    const modal = document.getElementById("createManualModal");
    if (!modal || modal.dataset.inited === "1") return;
    modal.dataset.inited = "1";

    const form = modal.querySelector("#createManualForm");
    const input = modal.querySelector("#manualTitleInput");
    const errBox = modal.querySelector("#manualCreateError");
    const btn = modal.querySelector("#btnCreateManualConfirm");

    const createUrl = S.toStr(modal.dataset.createUrl);
    if (!form || !input || !btn || !createUrl) return;

    function reset() {
      S.clearErrorBox(errBox);
      input.value = "";
      S.setBtnLoading(btn, false, null, "만들기");
      form.querySelector("#manualAccessNormal").checked = true;
    }

    modal.addEventListener("shown.bs.modal", () => {
      reset();
      input.focus();
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      S.clearErrorBox(errBox);

      const title = S.toStr(input.value);
      if (!title) return S.showErrorBox(errBox, "매뉴얼 이름을 입력해주세요.");
      if (title.length > 80) return S.showErrorBox(errBox, "80자 이하여야 합니다.");

      const access = S.toStr(form.querySelector('input[name="manualAccess"]:checked')?.value);

      S.setBtnLoading(btn, true, "생성중...");

      try {
        const data = await S.postJson(createUrl, { title, access }, S.getCSRFTokenFromForm(null));

        const redirectUrl = S.toStr(data.redirect_url);
        if (redirectUrl) {
          window.location.href = redirectUrl;
        } else {
          window.location.reload();
        }
      } catch (err) {
        console.error("[create_manual_modal] create failed:", err);
        S.showErrorBox(errBox, err?.message || "매뉴얼 생성 중 오류가 발생했습니다.");
        S.setBtnLoading(btn, false, null, "만들기");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCreateManualModal, { once: true });
  } else {
    initCreateManualModal();
  }
})();
