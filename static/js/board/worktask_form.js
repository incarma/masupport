/**
 * static/js/board/worktask_form.js
 * =============================================================================
 * WorkTask 등록(create) / 수정(edit) 폼 전용 JS.
 *
 * worktask_detail.js 에서 폼 관련 기능을 분리.
 * 인라인 스크립트 대체 (CSP 'unsafe-inline' 미사용 대응).
 *
 * 포함 기능:
 *   [1] 반복 유형 'custom' 토글
 *   [2] 기존 관련인물 태그 제거 (edit 폼 초기 태그)
 *   [2-1] 영업가족 지점 추가/삭제
 *   [3] 폼 중복 제출 방지
 * =============================================================================
 */

(function () {
  "use strict";

  /* BFCache 가드 */
  if (document.body.dataset.__boardWorktaskFormInited === "1") return;
  document.body.dataset.__boardWorktaskFormInited = "1";

  /* ── 유틸 ───────────────────────────────────────────────── */
  function escHtml(v) {
    return String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  // ===========================================================================
  // [1] 반복 유형 custom 토글
  // ===========================================================================
  (function initRecurrenceToggle() {
    const sel   = document.getElementById("id_recurrence_type");
    const group = document.getElementById("recurrence-day-group");
    if (!sel || !group) return;

    function toggle() {
      group.classList.toggle("d-none", sel.value !== "custom");
    }
    sel.addEventListener("change", toggle);
    toggle();
  })();

  // ===========================================================================
  // [2] 기존 관련인물 태그 제거 (edit 폼 — 서버에서 렌더된 초기 태그)
  // ===========================================================================
  (function initExistingTagRemove() {
    document.querySelectorAll(".worktask-remove-user").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const uid = this.dataset.uid;
        this.closest(".worktask-related-user-tag")?.remove();
        document.getElementById("hidden-uid-" + uid)?.remove();
      });
    });
  })();

  // ===========================================================================
  // [2-1] 영업가족 지점 추가/삭제
  // ===========================================================================
  (function initFamilyBranches() {
    const tagsWrap  = document.getElementById("family-branches-tags");
    const hiddenWrap = document.getElementById("family-branches-hidden-inputs");
    const select    = document.getElementById("worktaskFamilyBranchSelect");
    const btnConfirm = document.getElementById("btn-confirm-family-branch");
    const modalEl   = document.getElementById("worktaskFamilyBranchModal");

    if (!tagsWrap || !hiddenWrap || !select || !btnConfirm) return;

    const selected = new Set();

    tagsWrap.querySelectorAll(".worktask-family-branch-tag").forEach((tag) => {
      const branch = String(tag.dataset.branch || "").trim();
      if (branch) selected.add(branch);
    });

    function makeSafeId(branch) {
      return "hidden-family-branch-" + encodeURIComponent(branch).replaceAll("%", "");
    }

    function addBranch(branch) {
      branch = String(branch || "").trim();
      if (!branch || selected.has(branch)) return;

      selected.add(branch);

      const tag = document.createElement("span");
      tag.className = "worktask-family-branch-tag";
      tag.dataset.branch = branch;
      tag.innerHTML = `${escHtml(branch)}
        <button type="button"
                class="btn-close btn-close-sm ms-1 worktask-remove-family-branch"
                data-branch="${escHtml(branch)}" aria-label="제거"></button>`;

      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "family_branches";
      input.value = branch;
      input.id = makeSafeId(branch);

      tagsWrap.appendChild(tag);
      hiddenWrap.appendChild(input);
    }

    function removeBranch(branch) {
      branch = String(branch || "").trim();
      if (!branch) return;

      selected.delete(branch);
      tagsWrap.querySelectorAll(".worktask-family-branch-tag").forEach((el) => {
        if (el.dataset.branch === branch) el.remove();
      });
      hiddenWrap.querySelectorAll('input[name="family_branches"]').forEach((el) => {
        if (el.value === branch) el.remove();
      });
    }

    btnConfirm.addEventListener("click", function () {
      const branch = select.value;
      if (!branch) {
        alert("추가할 지점을 선택해 주세요.");
        return;
      }

      addBranch(branch);
      select.value = "";

      if (window.bootstrap && modalEl) {
        const modal = window.bootstrap.Modal.getInstance(modalEl);
        modal?.hide();
      }
    });

    tagsWrap.addEventListener("click", function (e) {
      const btn = e.target.closest(".worktask-remove-family-branch");
      if (!btn) return;
      removeBranch(btn.dataset.branch);
    });
  })();

  // ===========================================================================
  // [3] 폼 중복 제출 방지
  // ===========================================================================
  (function initFormSubmitLock() {
    ["worktaskCreateForm", "worktaskEditForm"].forEach((id) => {
      const form = document.getElementById(id);
      if (!form) return;

      form.addEventListener("submit", function () {
        if (this.dataset.submitting === "1") return false;
        this.dataset.submitting = "1";
        const btn = this.querySelector('[type="submit"]');
        if (btn) { btn.disabled = true; btn.textContent = "저장 중..."; }
      });
    });
  })();

})();
