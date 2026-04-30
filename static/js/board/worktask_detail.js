/**
 * static/js/board/worktask_detail.js
 * =============================================================================
 * WorkTask 상세 / 등록 / 수정 페이지 공용 JS.
 *
 * 역할:
 *   - 상세: 인라인 완료/건너뜀 AJAX + badge 즉시 갱신
 *   - 상세: D-day 렌더링 (CSP 대응 — 인라인 스크립트 대체)
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
  const resetBtn = document.getElementById("btn-detail-reset");

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
        const badge = document.getElementById("detail-status-badge");
        if (badge) {
          badge.dataset.status = data.status;
          badge.textContent    = data.status_display;
        }
        // 상태에 따라 버튼 영역 갱신
        if (data.status === "done" || data.status === "skipped") {
          document.getElementById("detail-action-btns")?.remove();
        } else {
          // 대기로 복원 시 페이지 새로고침으로 버튼 구조 복원
          location.reload();
        }
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
  resetBtn?.addEventListener("click", () => {
    const url = resetBtn.dataset.resetUrl;
    if (url) _handleChange(resetBtn, url);
  });
})();


// =============================================================================
// [2] 등록/수정 폼 — 관련 인물 검색 모달 연동
// =============================================================================
(function _initRelatedUserSearch() {
  const searchBtn = document.getElementById("btn-search-related-user");
  if (!searchBtn) return;

  const tagsEl   = document.getElementById("related-users-tags");
  const hiddenEl = document.getElementById("related-users-hidden-inputs");
  if (!tagsEl || !hiddenEl) return;

  const selected = new Set(
    Array.from(hiddenEl.querySelectorAll("input[name='related_users']"))
      .map((el) => el.value)
  );
  tagsEl.querySelectorAll("[data-uid]").forEach((el) => selected.add(el.dataset.uid));

  window.addEventListener("userSelected", function (e) {
    const user = e.detail;
    if (!user?.id) return;

    const uid = String(user.id);
    if (selected.has(uid)) return;
    selected.add(uid);

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

    const hidden = Object.assign(document.createElement("input"), {
      type:  "hidden",
      name:  "related_users",
      value: uid,
      id:    `hidden-uid-${uid}`,
    });
    hiddenEl.appendChild(hidden);

    tag.querySelector(".worktask-remove-user").addEventListener("click", function () {
      const removeUid = this.dataset.uid;
      selected.delete(removeUid);
      tag.remove();
      document.getElementById(`hidden-uid-${removeUid}`)?.remove();
    });
  });

  // ✅ 모달 오픈은 search_user_modal.js SSOT에 완전 위임.
  // 버튼의 .btnOpenSearch 클래스 → search_user_modal.js document 캡처 핸들러가 처리.
  // worktask_detail.js 에서 modal.show() 직접 호출 금지.
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
// [4] D-day 렌더링 — CSP 대응 (인라인 스크립트 대체)
//     worktask_detail.html 의 data-due 속성에서 날짜를 읽는다.
// =============================================================================
(function _initDday() {
  const el = document.getElementById("detail-dday");
  if (!el || !el.dataset.due) return;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(el.dataset.due);
  due.setHours(0, 0, 0, 0);
  const diff = Math.round((due - today) / 86400000);

  if      (diff > 0)  el.textContent = `D-${diff}`;
  else if (diff === 0) el.textContent = "D-day";
  else                el.textContent = `D+${Math.abs(diff)} 초과`;
})();

// =============================================================================
// [5] 상세 페이지 — 삭제 버튼
// =============================================================================
(function _initDeleteBtn() {
  const btn = document.querySelector(".worktask-delete-btn");
  if (!btn) return;

  btn.addEventListener("click", async function () {
    if (this.dataset.submitting === "1") return;

    const title = this.dataset.title || "이 업무";
    if (!confirm(`"${title}" 을(를) 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    this.dataset.submitting = "1";
    this.disabled = true;

    const url         = this.dataset.deleteUrl;
    const redirectUrl = this.dataset.redirectUrl;

    if (!url) {
      alert("삭제 URL이 없습니다.");
      this.dataset.submitting = "";
      this.disabled = false;
      return;
    }

    try {
      const res    = await fetch(url, {
        method:  "POST",
        headers: {
          "X-CSRFToken":      getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const data = await _safeJson(res);

      if (data.ok) {
        location.href = redirectUrl || data.redirect_url || "/board/worktasks/";
      } else {
        alert(data.error || "삭제 중 오류가 발생했습니다.");
        this.dataset.submitting = "";
        this.disabled = false;
      }
    } catch (e) {
      console.error("[worktask_detail] delete error:", e);
      alert("네트워크 오류가 발생했습니다.");
      this.dataset.submitting = "";
      this.disabled = false;
    }
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