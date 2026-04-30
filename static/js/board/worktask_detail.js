/**
 * static/js/board/worktask_detail.js
 * =============================================================================
 * WorkTask 상세 / 등록 / 수정 페이지 공용 JS.
 *
 * 역할:
 *   - 상세: 인라인 완료/건너뜀 AJAX + badge 즉시 갱신
 *   - 등록/수정: 관련 인물 검색 모달 연동 + 태그 UI 관리
 *   - 폼 중복 제출 방지
 *
 * 공용 모듈 재사용:
 *   CSRF       → static/js/common/manage/csrf.js
 *   유저 검색  → static/js/common/search_user_modal.js SSOT
 *                (window "userSelected" 커스텀 이벤트 수신)
 *
 * 구현 규칙:
 *   - DOM 가드: context 별 boot/form 엘리먼트 확인 후 진행
 *   - 중복 바인딩 방지: dataset.inited = "1"
 *   - 중복 제출 방지: dataset.submitting = "1"
 *   - 관련인물 검색: 프론트에서 범위 직접 필터링 금지 (서버 SSOT)
 * =============================================================================
 */

import { getCSRFToken } from "../common/manage/csrf.js";

// =============================================================================
// [1] 상세 페이지 — 인라인 상태 변경
// =============================================================================
(function _initDetailPage() {
  const boot = document.getElementById("worktaskDetailBoot");
  if (!boot || boot.dataset.inited === "1") return;
  boot.dataset.inited = "1";

  const doneBtn = document.getElementById("btn-detail-done");
  const skipBtn = document.getElementById("btn-detail-skip");

  async function _handleChange(btn, url) {
    if (btn.dataset.submitting === "1") return;
    btn.dataset.submitting = "1";
    btn.disabled = true;

    try {
      const res  = await fetch(url, {
        method:  "POST",
        headers: {
          "X-CSRFToken":      getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const data = await _safeJson(res);

      if (data.ok) {
        // 상태 badge 갱신
        const badge = document.getElementById("detail-status-badge");
        if (badge) {
          badge.dataset.status = data.status;
          badge.textContent    = data.status_display;
        }
        // 버튼 그룹 제거 (완료/건너뜀 후 재처리 불필요)
        document.getElementById("detail-action-btns")?.remove();
      } else {
        alert(data.error || "처리 중 오류가 발생했습니다.");
        btn.dataset.submitting = "";
        btn.disabled = false;
      }
    } catch (e) {
      console.error("[worktask_detail] status change error:", e);
      alert("네트워크 오류가 발생했습니다.");
      btn.dataset.submitting = "";
      btn.disabled = false;
    }
  }

  doneBtn?.addEventListener("click", () =>
    _handleChange(doneBtn, boot.dataset.doneUrl)
  );
  skipBtn?.addEventListener("click", () =>
    _handleChange(skipBtn, boot.dataset.skipUrl)
  );
})();


// =============================================================================
// [2] 등록/수정 폼 — 관련 인물 검색 모달 연동
// =============================================================================
(function _initRelatedUserSearch() {
  const searchBtn     = document.getElementById("btn-search-related-user");
  if (!searchBtn) return; // 등록/수정 폼이 아니면 종료

  const tagsEl        = document.getElementById("related-users-tags");
  const hiddenEl      = document.getElementById("related-users-hidden-inputs");
  if (!tagsEl || !hiddenEl) return;

  // 이미 선택된 uid 집합 (중복 추가 방지)
  const selected = new Set(
    Array.from(hiddenEl.querySelectorAll("input[name='related_users']"))
      .map((el) => el.value)
  );
  // 수정 폼 초기 태그에서도 수집
  tagsEl.querySelectorAll("[data-uid]").forEach((el) => selected.add(el.dataset.uid));

  /**
   * search_user_modal.js 가 발행하는 "userSelected" 이벤트 수신.
   * SSOT: accounts/search_api.py 경유한 결과만 사용.
   * ⚠️ 프론트에서 범위 직접 필터링 금지.
   */
  window.addEventListener("userSelected", function (e) {
    const user = e.detail;
    if (!user?.id) return;

    const uid = String(user.id);
    if (selected.has(uid)) return; // 중복 추가 방지
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

    // 제거 버튼 이벤트
    tag.querySelector(".worktask-remove-user").addEventListener("click", function () {
      const removeUid = this.dataset.uid;
      selected.delete(removeUid);
      tag.remove();
      document.getElementById(`hidden-uid-${removeUid}`)?.remove();
    });
  });

  // 검색 모달 열기
  searchBtn.addEventListener("click", () => {
    const modalEl = document.getElementById("searchUserModal");
    if (!modalEl) { console.warn("[worktask_detail] searchUserModal not found"); return; }
    const modal =
      window.bootstrap?.Modal?.getInstance?.(modalEl) ||
      new window.bootstrap.Modal(modalEl);
    modal.show();
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
      if (this.dataset.submitting === "1") { return false; }
      this.dataset.submitting = "1";
      const btn = this.querySelector('[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = "저장 중..."; }
    });
  });
})();


// =============================================================================
// 유틸
// =============================================================================
async function _safeJson(res) {
  const text = await res.text().catch(() => "");
  if (!text) return {};
  try { return JSON.parse(text); }
  catch { return { _raw: text.slice(0, 200) }; }
}

function _esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}