// django_ma/static/js/manual/create_manual_modal.js
// ============================================================================
// Create Manual Modal
// - 매뉴얼 생성 전용
// - CSRF / access radio / redirect 처리
// ============================================================================

(() => {
  function initCreateManualModal() {
    const S = window.ManualShared || {};

    const toStr = S.toStr || ((v) => String(v ?? "").trim());
    const setBtnLoading = S.setBtnLoading || ((btn, isLoading, loadingText, defaultText) => {
      if (!btn) return;
      if (isLoading) {
        if (btn.dataset.oldText == null) btn.dataset.oldText = btn.textContent || defaultText || "";
        btn.disabled = true;
        if (loadingText) btn.textContent = loadingText;
      } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.oldText || defaultText || btn.textContent || "";
        delete btn.dataset.oldText;
      }
    });
    const showErrorBox = S.showErrorBox || ((errBox, msg) => {
      const m = toStr(msg) || "오류가 발생했습니다.";
      if (!errBox) return alert(m);
      errBox.textContent = m;
      errBox.classList.remove("d-none");
    });
    const clearErrorBox = S.clearErrorBox || ((errBox) => {
      if (!errBox) return;
      errBox.textContent = "";
      errBox.classList.add("d-none");
    });
    const safeReadJson = S.safeReadJson || (async (res) => {
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (!ct.includes("application/json")) {
        const text = await res.text().catch(() => "");
        return { __non_json__: true, __text__: text };
      }
      return await res.json().catch(() => ({}));
    });

    const modal = document.getElementById("createManualModal");
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = "true";

    const form = modal.querySelector("#createManualForm");
    const input = modal.querySelector("#manualTitleInput");
    const errBox = modal.querySelector("#manualCreateError");
    const btn = modal.querySelector("#btnCreateManualConfirm");

    const createUrl = toStr(modal.dataset.createUrl);
    if (!form || !input || !btn || !createUrl) return;

    function reset() {
      clearErrorBox(errBox);
      input.value = "";
      setBtnLoading(btn, false, null, "만들기");
      form.querySelector("#manualAccessNormal").checked = true;
    }

    modal.addEventListener("shown.bs.modal", () => {
      reset();
      input.focus();
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearErrorBox(errBox);

      const title = toStr(input.value);
      if (!title) return showErrorBox(errBox, "매뉴얼 이름을 입력해주세요.");
      if (title.length > 80) return showErrorBox(errBox, "80자 이하여야 합니다.");

      const csrf = window.csrfToken;
      const access = toStr(form.querySelector('input[name="manualAccess"]:checked')?.value);

      setBtnLoading(btn, true, "생성중...");

      try {
        const res = await fetch(createUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({ title, access }),
        });

        const data = await safeReadJson(res);
        if (data?.__non_json__) {
          throw new Error(`요청 실패 (HTTP ${res.status})`);
        }
        if (!res.ok || !data?.ok) {
          throw new Error(data?.message || `요청 실패 (HTTP ${res.status})`);
        }

        const redirectUrl = toStr(data.redirect_url);
        if (redirectUrl) {
          window.location.href = redirectUrl;
        } else {
          window.location.reload();
        }
      } catch (err) {
        console.error("[create_manual_modal] create failed:", err);
        showErrorBox(errBox, err?.message || "매뉴얼 생성 중 오류가 발생했습니다.");
        setBtnLoading(btn, false, null, "만들기");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCreateManualModal, { once: true });
  } else {
    initCreateManualModal();
  }
})();
