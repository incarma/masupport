// django_ma/static/js/board/common/comment_edit.js
// =========================================================
// Board Common Comment Inline Edit (post_detail / task_detail 공용)
//
// ✅ 주요 기능
// - .edit-comment-btn 클릭 → 댓글을 textarea 인라인 편집 모드로 전환
// - 저장: 기존 폼 POST 흐름 재사용(action_type=edit_comment)
// - 취소: 원문 복구(새로고침 없음)
// - CSRF: #commentEditCsrfToken 우선 → 없으면 페이지 내 csrf input fallback
//
// ✅ CSS 모듈화 대응
// - 인라인 style 제거(white-space/font-size 등)
// - 클래스 기반 UI 구성(comment-text/comment-edit-* 활용)
//
// ✅ 템플릿 전제(권장)
// - <input type="hidden" id="commentEditCsrfToken" value="{{ csrf_token }}">
// - 댓글 컨테이너: .comment-content[data-comment-id]
// - 수정 버튼: .edit-comment-btn[data-id]
// - 버튼 그룹: .edit-delete-btns
// - 본문: p.comment-text
// =========================================================

(function () {
  "use strict";

  const Board = (window.Board = window.Board || {});
  Board.Common = Board.Common || {};

  const INIT_FLAG = "__boardCommentEditInited";
  const PAGE_SHOW_FLAG = "__boardCommentEditPageShowBound";

  /* =========================================================
   * 1) Small DOM utilities
   * ========================================================= */
  function qs(sel, root = document) {
    return root.querySelector(sel);
  }

  function getCsrfToken() {
    const v = qs("#commentEditCsrfToken")?.value;
    if (v && v !== "NOTPROVIDED") return v;
    return qs("input[name='csrfmiddlewaretoken']")?.value || "";
  }

  function getOldText(container) {
    const p = qs("p.comment-text", container) || qs("p", container);
    // innerText는 줄바꿈 유지에 유리
    return String(p?.innerText || "").trim();
  }

  function normalizeText(v) {
    return String(v ?? "").replace(/\r\n/g, "\n").trim();
  }

  /* =========================================================
   * 2) UI builders
   * ========================================================= */
  function buildStaticParagraph(text) {
    const p = document.createElement("p");
    p.className = "mb-0 small comment-text";
    p.textContent = text ?? "";
    return p;
  }

  function buildEditForm({ csrf, commentId, oldText }) {
    const form = document.createElement("form");
    form.method = "post";
    form.className = "comment-edit-form comment-edit-form-js";

    // ✅ innerHTML로 textarea 값을 넣지 말고(value 사용) DOM 깨짐 방지
    const csrfInput = document.createElement("input");
    csrfInput.type = "hidden";
    csrfInput.name = "csrfmiddlewaretoken";
    csrfInput.value = csrf;

    const actInput = document.createElement("input");
    actInput.type = "hidden";
    actInput.name = "action_type";
    actInput.value = "edit_comment";

    const idInput = document.createElement("input");
    idInput.type = "hidden";
    idInput.name = "comment_id";
    idInput.value = String(commentId || "");

    const ta = document.createElement("textarea");
    ta.name = "content";
    ta.className = "form-control form-control-sm comment-edit-textarea";
    ta.rows = 7;
    ta.value = String(oldText ?? "");

    const actions = document.createElement("div");
    actions.className = "comment-edit-actions mt-2";
    const submitBtn = document.createElement("button");
    submitBtn.type = "submit";
    submitBtn.className = "btn btn-sm btn-primary";
    submitBtn.textContent = "저장";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-sm btn-outline-secondary cancel-edit";
    cancelBtn.textContent = "취소";

    actions.append(submitBtn, cancelBtn);

    form.append(csrfInput, actInput, idInput, ta, actions);
    return form;
  }

  function showActionButtons(container, visible) {
    const actionBtns = qs(".edit-delete-btns", container);
    if (!actionBtns) return;
    actionBtns.style.display = visible ? "" : "none";
  }

  function clearEditForm(container) {
    qs("form.comment-edit-form", container)?.remove();
  }

  function clearStaticText(container) {
    (qs("p.comment-text", container) || qs("p", container))?.remove();
  }

  function restoreStatic(container, oldText) {
    clearEditForm(container);
    clearStaticText(container);

    container.insertBefore(buildStaticParagraph(oldText), container.firstChild);
    showActionButtons(container, true);
    container.dataset.editing = "0";
  }

  function restoreAllEditingContainers() {
    document.querySelectorAll(".comment-content[data-editing='1']").forEach((container) => {
      const oldText = container.dataset.originalText || getOldText(container);
      restoreStatic(container, oldText);
    });
  }

  function bindPageShowReset() {
    if (document.body.dataset[PAGE_SHOW_FLAG] === "1") return;
    document.body.dataset[PAGE_SHOW_FLAG] = "1";

    window.addEventListener("pageshow", () => {
      restoreAllEditingContainers();
      document.querySelectorAll("form.comment-edit-form button[type='submit']").forEach((btn) => {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      });
      document.querySelectorAll("form.comment-edit-form").forEach((form) => {
        form.dataset.submitting = "0";
      });
    });
  }

  function enterEditMode(container, commentId, oldText) {
    const csrf = getCsrfToken();
    if (!csrf) {
      alert("CSRF 토큰을 찾지 못했습니다. 새로고침 후 다시 시도해주세요.");
      restoreStatic(container, oldText);
      return;
    }

    const normalizedOldText = normalizeText(oldText);
    if (!normalizedOldText && !getOldText(container)) {
      container.dataset.editing = "0";
      alert("댓글 내용을 불러오지 못했습니다. 새로고침 후 다시 시도해주세요.");
      return;
    }

    // 버튼 숨김 + 본문 제거
    showActionButtons(container, false);
    clearStaticText(container);

    // 편집폼 삽입
    const form = buildEditForm({ csrf, commentId, oldText: normalizedOldText });
    container.insertBefore(form, container.firstChild);

    // 취소
    qs(".cancel-edit", form)?.addEventListener("click", () => {
      restoreStatic(container, oldText);
    });

    // UX: textarea focus
    qs("textarea[name='content']", form)?.focus?.();

    form.addEventListener("submit", (e) => {
      if (form.dataset.submitting === "1") {
        e.preventDefault();
        return;
      }

      const ta = qs("textarea[name='content']", form);
      const content = normalizeText(ta?.value || "");
      if (!content) {
        e.preventDefault();
        alert("댓글 내용을 입력해주세요.");
        ta?.focus?.();
        return;
      }
      form.dataset.submitting = "1";
      const submitBtn = qs("button[type='submit']", form);
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-busy", "true");
      }
    });
  }

  /* =========================================================
   * 3) Event binding (delegation, once)
   * ========================================================= */
  function bind() {
    if (document.body.dataset[INIT_FLAG] === "1") return;
    document.body.dataset[INIT_FLAG] = "1";
    bindPageShowReset();

    document.addEventListener("click", (e) => {
      const btn = e.target?.closest?.(".edit-comment-btn");
      if (!btn) return;

      const commentId = btn.dataset.id;
      const container = btn.closest(".comment-content");
      if (!commentId || !container) return;

      if (container.dataset.editing === "1") return;
      container.dataset.editing = "1";
      container.dataset.originalText = getOldText(container);

      const oldText = container.dataset.originalText;
      enterEditMode(container, commentId, oldText);
    });
  }

  /* =========================================================
   * 4) Public init
   * ========================================================= */
  Board.Common.initCommentEdit = function initCommentEdit() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bind, { once: true });
    } else {
      bind();
    }
  };
})();
