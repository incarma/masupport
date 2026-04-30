/**
 * static/js/board/worktask_list.js
 * =============================================================================
 * WorkTask 목록 페이지 전용 JS.
 *
 * 역할:
 *   - AJAX 완료(done) / 건너뜀(skip) 처리 → 행 UI 즉시 갱신
 *   - 마감 임박 알림 폴링 (notify-check API) → 배너 표시
 *   - D-day 계산 렌더링
 *   - BFCache(뒤로가기) 대응
 *
 * Boot 패턴 (worktask.md §7.2):
 *   id="worktaskListBoot" 의 data-* 만 읽는다.
 *   done-url / skip-url 에는 pk placeholder "0" 이 있으며,
 *   실제 실행 시 buildActionUrl() 로 교체한다.
 *
 * 공용 모듈 재사용:
 *   CSRF → static/js/common/manage/csrf.js  (중복 구현 금지)
 *
 * 구현 규칙:
 *   - DOM 가드: boot 없으면 즉시 종료
 *   - 중복 바인딩 방지: dataset.inited = "1"
 *   - 중복 제출 방지: dataset.submitting = "1"
 *   - BFCache 대응: pageshow 이벤트
 * =============================================================================
 */

import { getCSRFToken } from "../common/manage/csrf.js";

// =============================================================================
// Boot 가드 — 이 페이지가 아니면 조용히 종료
// =============================================================================
const boot = document.getElementById("worktaskListBoot");
if (!boot) {
  // ES module 에서 throw 하면 에러 로그가 남으므로 조용히 종료
  // (다른 페이지에서 이 모듈을 실수로 로드했을 때 방어)
  console.debug("[worktask_list] boot element not found — skip");
  // eslint-disable-next-line no-throw-literal
  throw "[worktask_list] no-op exit";
}

// 중복 바인딩 방지
if (boot.dataset.inited === "1") {
  console.debug("[worktask_list] already inited — skip");
} else {
  boot.dataset.inited = "1";
  _init();
}

// BFCache 대응: 뒤로가기 복귀 시 알림 배너만 재폴링
window.addEventListener("pageshow", (e) => {
  if (e.persisted) _pollNotify();
});

// =============================================================================
// 초기화
// =============================================================================
function _init() {
  _bindDoneButtons();
  _bindSkipButtons();
  _renderDdays();
  _pollNotify();
}

// =============================================================================
// 완료 버튼 바인딩
// =============================================================================
function _bindDoneButtons() {
  document.querySelectorAll(".worktask-done-btn").forEach((btn) => {
    btn.addEventListener("click", async function () {
      if (this.dataset.submitting === "1") return;
      await _handleAction(this, boot.dataset.doneUrl, "done");
    });
  });
}

// =============================================================================
// 건너뜀 버튼 바인딩
// =============================================================================
function _bindSkipButtons() {
  document.querySelectorAll(".worktask-skip-btn").forEach((btn) => {
    btn.addEventListener("click", async function () {
      if (this.dataset.submitting === "1") return;
      await _handleAction(this, boot.dataset.skipUrl, "skipped");
    });
  });
}

// =============================================================================
// AJAX 액션 공통 처리
// =============================================================================
async function _handleAction(btn, urlTemplate, expectedStatus) {
  const pk = btn.dataset.pk;
  if (!pk) return;

  btn.dataset.submitting = "1";
  btn.disabled = true;

  try {
    const url    = _buildActionUrl(urlTemplate, pk);
    const result = await _postJson(url);

    if (result.ok) {
      _updateRowStatus(pk, result.status, result.status_display);
    } else {
      alert(result.error || "처리 중 오류가 발생했습니다.");
    }
  } catch (e) {
    console.error("[worktask_list] action error:", e);
    alert("네트워크 오류가 발생했습니다.");
  } finally {
    btn.dataset.submitting = "";
    btn.disabled = false;
  }
}

// =============================================================================
// 행 상태 즉시 갱신
// =============================================================================
function _updateRowStatus(pk, status, statusDisplay) {
  const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
  if (!row) return;

  // 상태 badge 갱신
  const badge = document.getElementById(`status-badge-${pk}`);
  if (badge) {
    badge.dataset.status = status;
    badge.textContent    = statusDisplay;
  }

  // 완료/건너뜀이면 행 흐림 처리 + 버튼 제거
  row.dataset.status = status;
  if (status === "done" || status === "skipped") {
    row.classList.add("worktask-done");
    const actionCell = row.querySelector("td:last-child");
    if (actionCell) {
      actionCell.innerHTML = '<span class="text-muted small">처리됨</span>';
    }
  }
}

// =============================================================================
// D-day 렌더링
// =============================================================================
function _renderDdays() {
  const dueDates = window.__worktaskDueDates || {};
  const today    = new Date();
  today.setHours(0, 0, 0, 0);

  Object.entries(dueDates).forEach(([pk, dueDateStr]) => {
    const el = document.getElementById(`dday-${pk}`);
    if (!el || !dueDateStr) return;

    const due  = new Date(dueDateStr);
    due.setHours(0, 0, 0, 0);
    const diff = Math.round((due - today) / 86400000);

    if      (diff > 0)  el.textContent = `D-${diff}`;
    else if (diff === 0) el.textContent = "D-day";
    else                el.textContent = `D+${Math.abs(diff)}`;
  });
}

// =============================================================================
// 알림 폴링
// =============================================================================
async function _pollNotify() {
  const url = boot.dataset.notifyUrl;
  if (!url) return;

  try {
    const res  = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!res.ok) return;
    const data = await _safeJson(res);

    if (data.ok && data.count > 0) {
      _showBanner(data.count, data.items || []);
    } else {
      _hideBanner();
    }
  } catch (e) {
    console.warn("[worktask_list] notify poll failed:", e);
  }
}

function _showBanner(count, items) {
  const banner = document.getElementById("worktask-notify-banner");
  const text   = document.getElementById("worktask-notify-text");
  if (!banner || !text) return;

  const preview = items.slice(0, 3).map((i) => `"${i.title}"`).join(", ");
  const extra   = count > 3 ? ` 외 ${count - 3}건` : "";
  text.textContent = `⚠️ 마감 임박 업무 ${count}건: ${preview}${extra}`;
  banner.classList.remove("d-none");
}

function _hideBanner() {
  document.getElementById("worktask-notify-banner")?.classList.add("d-none");
}

// =============================================================================
// 유틸
// =============================================================================

/**
 * URL 템플릿의 "/0/" pk placeholder 를 실제 pk 로 치환.
 * data-done-url="/board/worktasks/0/done/" → "/board/worktasks/42/done/"
 */
function _buildActionUrl(template, pk) {
  return template.replace(/\/0\//, `/${pk}/`);
}

/** CSRF 포함 POST + JSON 파싱 */
async function _postJson(url) {
  const res = await fetch(url, {
    method:  "POST",
    headers: {
      "X-CSRFToken":        getCSRFToken(),
      "X-Requested-With":   "XMLHttpRequest",
    },
  });
  return _safeJson(res);
}

/** 안전한 JSON 파싱 (파싱 실패 시 빈 객체 반환) */
async function _safeJson(res) {
  const text = await res.text().catch(() => "");
  if (!text) return {};
  try { return JSON.parse(text); }
  catch { return { _raw: text.slice(0, 200) }; }
}