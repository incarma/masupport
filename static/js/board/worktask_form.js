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
 *   [3] 관련인물 검색 모달 연동 (userSelected 이벤트)
 *   [4] 폼 중복 제출 방지
 * =============================================================================
 */

// =============================================================================
// [1] 반복 유형 custom 토글
// =============================================================================
(function _initRecurrenceToggle() {
  const sel   = document.getElementById("id_recurrence_type");
  const group = document.getElementById("recurrence-day-group");
  if (!sel || !group) return;

  function toggle() {
    group.classList.toggle("d-none", sel.value !== "custom");
  }
  sel.addEventListener("change", toggle);
  toggle(); // 초기 상태 적용
})();


// =============================================================================
// [2] 기존 관련인물 태그 제거 (edit 폼 — 서버에서 렌더된 초기 태그)
// =============================================================================
(function _initExistingTagRemove() {
  document.querySelectorAll(".worktask-remove-user").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const uid = this.dataset.uid;
      this.closest(".worktask-related-user-tag")?.remove();
      document.getElementById("hidden-uid-" + uid)?.remove();
    });
  });
})();


// =============================================================================
// [3] 폼 중복 제출 방지
// =============================================================================
(function _initFormSubmitLock() {
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


// =============================================================================
// 유틸
// =============================================================================
function _esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}