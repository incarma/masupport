// django_ma/static/js/board/common/inline_update.js
// =========================================================
// Board Common Inline Update (LIST) (FINAL)
// - post_list / task_list 공용
// - handler/status select 인라인 변경 AJAX
// - status_updated_at(td.status-updated-at) 갱신
// - onSuccess 공식 지원 (예: status_ui 재적용)
//
// ✅ CSS 모듈화 대응
// - 인라인 style(pointerEvents/opacity) 주입 제거
// - disabled + aria-busy + classList('is-busy') 토글 방식
// =========================================================

(function () {
  "use strict";

  const Board = (window.Board = window.Board || {});
  Board.Common = Board.Common || {};

  const INIT_FLAG = "__boardListInlineUpdateBound";
  const PAGE_SHOW_FLAG = "__boardListInlineUpdatePageShowBound";
  const CTX_KEY = "__boardListInlineUpdateContexts";

  /* =========================================================
   * 1) Utilities
   * ========================================================= */
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeJson(res) {
    return res.json().catch(() => null);
  }

  function getCsrfFromForm(form) {
    return form?.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
  }

  function isHtmlResponse(res) {
    return (res.headers.get("content-type") || "").toLowerCase().includes("text/html");
  }

  async function readErrorMessage(res, data) {
    if (data?.message) return data.message;
    if (data?.error) return data.error;

    if (res.status === 401 || res.status === 403) {
      if (isHtmlResponse(res)) {
        return "세션이 만료되었거나 접근 권한이 없습니다. 다시 로그인 후 시도해주세요.";
      }
      return "권한이 없거나 세션이 만료되었습니다.";
    }

    if (isHtmlResponse(res)) {
      return "요청 처리 중 로그인 페이지 또는 오류 페이지가 반환되었습니다. 다시 로그인 후 시도해주세요.";
    }
    return `변경 실패 (HTTP ${res.status})`;
  }

  function setBusy(selectEl, busy) {
    if (!selectEl) return;

    // ✅ 인라인 style 대신: disabled + class
    if (busy) selectEl.setAttribute("disabled", "disabled");
    else selectEl.removeAttribute("disabled");

    selectEl.setAttribute("aria-busy", busy ? "true" : "false");
    selectEl.classList.toggle("is-busy", !!busy);
  }

  function showAlert(alertHost, message, type = "success") {
    if (!alertHost) return window.alert(message || "");
    alertHost.innerHTML = `
      <div class="alert alert-${type} alert-dismissible fade show text-center" role="alert">
        ${escapeHtml(message || "")}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      </div>
    `;

    window.setTimeout(() => {
      const el = qs(".alert", alertHost);
      if (!el) return;
      try {
        bootstrap.Alert.getOrCreateInstance(el).close();
      } catch {
        el.remove();
      }
    }, 2500);
  }

  function getContexts() {
    if (!Array.isArray(Board.Common[CTX_KEY])) {
      Board.Common[CTX_KEY] = [];
    }
    return Board.Common[CTX_KEY];
  }

  function registerContext(ctx) {
    const contexts = getContexts();
    const exists = contexts.some((item) => item.bootId === ctx.bootId);
    if (!exists) contexts.push(ctx);
  }

  function resetBusyState() {
    document.querySelectorAll("form.inline-update-form").forEach((form) => {
      form.dataset.submitting = "0";
    });
    document
      .querySelectorAll("form.inline-update-form select[name='handler'], form.inline-update-form select[name='status']")
      .forEach((sel) => setBusy(sel, false));
  }

  function bindPageShowReset() {
    if (document.body.dataset[PAGE_SHOW_FLAG] === "1") return;
    document.body.dataset[PAGE_SHOW_FLAG] = "1";
    window.addEventListener("pageshow", resetBusyState);
  }

  async function sendUpdate({ updateUrl, form, idKey, idValue, actionType, value }) {
    if (!updateUrl) throw new Error("AJAX update URL이 없습니다. (boot data-update-url 확인)");

    const csrf = getCsrfFromForm(form);
    if (!csrf) throw new Error("CSRF 토큰을 폼에서 찾을 수 없습니다.");

    const body = new URLSearchParams();
    body.set(idKey, idValue);
    body.set("action_type", actionType);
    body.set("value", value);

    const res = await fetch(updateUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body.toString(),
      credentials: "same-origin",
    });

    const data = await safeJson(res);
    if (res.redirected || isHtmlResponse(res)) {
      throw new Error(await readErrorMessage(res, data));
    }

    if (!res.ok || !data?.ok) {
      const fallback = await readErrorMessage(res, data);
      throw new Error(fallback);
    }
    return data;
  }

  /* =========================================================
   * 2) Public init
   * ========================================================= */
  /**
   * initListInlineUpdate
   * @param {Object} opts
   * @param {string} opts.bootId - "postListBoot" | "taskListBoot"
   * @param {string} opts.idKey  - "post_id" | "task_id"
   * @param {Function} [opts.onSuccess] - (data, ctx) => void
   */
  Board.Common.initListInlineUpdate = function initListInlineUpdate(opts) {
    const bootId = opts?.bootId;
    const idKey = opts?.idKey;
    const onSuccess = typeof opts?.onSuccess === "function" ? opts.onSuccess : null;
    if (!bootId || !idKey) return;

    const bind = () => {
      // 중복 바인딩 방지(LIST 페이지는 1회만)
      const boot = document.getElementById(bootId);
      if (!boot || boot.dataset.boardListInlineUpdateInited === "1") return;
      boot.dataset.boardListInlineUpdateInited = "1";

      const updateUrl = boot?.dataset?.updateUrl || "";
      const alertHost = document.getElementById("inlineUpdateAlertHost");

      // updateUrl 없으면(비권한/일반화면) 조용히 종료
      if (!updateUrl) return;
      registerContext({ bootId, idKey, updateUrl, onSuccess });

      // 초기 prevValue 세팅
      bindPageShowReset();
      document
        .querySelectorAll(
          "form.inline-update-form select[name='handler'], form.inline-update-form select[name='status']"
        )
        .forEach((s) => (s.dataset.prevValue = s.value));
      
      // 전역 change handler는 1회만
      if (document.body.dataset[INIT_FLAG] === "1") return;
      document.body.dataset[INIT_FLAG] = "1";

      document.addEventListener("change", async (e) => {
        const sel = e.target;
        if (!(sel instanceof HTMLSelectElement)) return;

        const form = sel.closest("form.inline-update-form");
        if (!form) return;

        const fieldName = sel.getAttribute("name");
        if (fieldName !== "handler" && fieldName !== "status") return;

        const contexts = getContexts();
        const ctx = contexts.find((item) => {
          const currentBoot = document.getElementById(item.bootId);
          return currentBoot && document.contains(currentBoot);
        });
        if (!ctx?.updateUrl || !ctx?.idKey) return;

        const currentOnSuccess = typeof ctx.onSuccess === "function" ? ctx.onSuccess : null;
        const currentAlertHost = document.getElementById("inlineUpdateAlertHost");
        const updateUrl = ctx.updateUrl;
        const idKey = ctx.idKey;

        const idValue = qs(`input[name="${idKey}"]`, form)?.value || "";
        const actionType = qs('input[name="action_type"]', form)?.value || "";

        if (!idValue || !actionType) {
          showAlert(alertHost, `필수값(${idKey}/action_type)이 없습니다.`, "danger");
          return;
        }

        if (form.dataset.submitting === "1") return;
        form.dataset.submitting = "1";

        const prev = sel.dataset.prevValue ?? sel.value;
        sel.dataset.prevValue = sel.value;

        setBusy(sel, true);

        try {
          const data = await sendUpdate({
            updateUrl,
            form,
            idKey,
            idValue,
            actionType,
            value: sel.value,
          });

          // 상태변경일 갱신
          if (data.status_updated_at) {
            const tr = sel.closest("tr");
            const td = tr?.querySelector("td.status-updated-at");
            if (td) td.textContent = data.status_updated_at;
          }

          // 서버가 status를 돌려주면 확정 반영
          if (fieldName === "status" && data.status) {
            sel.value = data.status;
            sel.dataset.prevValue = data.status;
            sel.dataset.status = data.status;
          }

          showAlert(currentAlertHost, data.message || "변경되었습니다.", "success");

          // 공식 onSuccess
          if (currentOnSuccess) {
            try {
              currentOnSuccess(data, { sel, form, fieldName, idKey, idValue, actionType, updateUrl });
            } catch {
              /* ignore */
            }
          }
        } catch (err) {
          sel.value = prev;
          sel.dataset.prevValue = prev;
          sel.dataset.status = prev;
          showAlert(currentAlertHost, err?.message || "변경 실패", "danger");
        } finally {
          setBusy(sel, false);
          form.dataset.submitting = "0";
        }
      });
    };

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bind, { once: true });
    } else {
      bind();
    }
  };
})();
