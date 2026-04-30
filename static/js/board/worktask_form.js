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
// [3] 관련인물 검색 모달 연동
//     search_user_modal.js SSOT 경유 — userSelected 이벤트 수신
// =============================================================================
(function _initRelatedUserSearch() {
  const searchBtn = document.getElementById("btn-search-related-user");
  if (!searchBtn) return;

  const tagsEl   = document.getElementById("related-users-tags");
  const hiddenEl = document.getElementById("related-users-hidden-inputs");
  if (!tagsEl || !hiddenEl) return;

  // 이미 선택된 uid 집합 (중복 추가 방지)
  const selected = new Set(
    Array.from(hiddenEl.querySelectorAll("input[name='related_users']"))
      .map((el) => el.value)
  );
  tagsEl.querySelectorAll("[data-uid]").forEach((el) => selected.add(el.dataset.uid));

  /**
   * search_user_modal.js 가 dispatch 하는 "userSelected" 이벤트 수신.
   * SSOT: accounts/search_api.py 경유 결과만 사용.
   * ⚠️ 프론트에서 범위 직접 필터링 금지.
   */
  window.addEventListener("userSelected", function (e) {
    const user = e.detail;
    if (!user?.id) return;

    const uid = String(user.id);
    if (selected.has(uid)) return;
    selected.add(uid);

    // 태그 생성
    const tag = document.createElement("span");
    tag.className   = "worktask-related-user-tag";
    tag.dataset.uid = uid;
    tag.innerHTML   = `
      ${_esc(user.name || uid)}
      <small class="text-muted ms-1">(${_esc(uid)})</small>
      <button type="button"
              class="btn-close btn-close-sm ms-1 worktask-remove-user"
              data-uid="${_esc(uid)}" aria-label="제거"></button>
    `;
    tagsEl.appendChild(tag);

    // hidden input 추가
    const hidden = Object.assign(document.createElement("input"), {
      type:  "hidden",
      name:  "related_users",
      value: uid,
      id:    `hidden-uid-${uid}`,
    });
    hiddenEl.appendChild(hidden);

    // 새로 추가된 태그의 제거 버튼 이벤트
    tag.querySelector(".worktask-remove-user").addEventListener("click", function () {
      const removeUid = this.dataset.uid;
      selected.delete(removeUid);
      tag.remove();
      document.getElementById(`hidden-uid-${removeUid}`)?.remove();
    });
  });

  // ✅ 모달 오픈은 search_user_modal.js SSOT에 완전 위임.
  // 버튼의 .btnOpenSearch 클래스 → search_user_modal.js document 캡처 핸들러가 처리.
})();


// =============================================================================
// [4] 폼 중복 제출 방지
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