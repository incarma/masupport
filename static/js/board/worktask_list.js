/**
 * static/js/board/worktask_list.js
 * =============================================================================
 * WorkTask 목록 페이지 전용 JS.
 *
 * 역할:
 *   - AJAX 완료(done) / 건너뜀(skip) / 상태해제(reset) 처리 → 행 UI 즉시 갱신
 *   - 인라인 셀 편집 (분류 / 우선순위 / 시작일 / 마감일)
 *   - 삭제 처리
 *   - 마감 임박 알림 폴링 (notify-check API) → 배너 표시
 *   - D-day 계산 렌더링
 *   - BFCache(뒤로가기) 대응
 *
 * Boot 패턴 (worktask.md §7.2):
 *   id="worktaskListBoot" 의 data-* 만 읽는다.
 *   done-url / skip-url / reset-url / delete-url / inline-url 에
 *   pk placeholder "0" 이 있으며, 실제 실행 시 _buildActionUrl() 로 교체한다.
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
  console.debug("[worktask_list] boot element not found — skip");
  throw "[worktask_list] no-op exit";
}

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
  _bindResetButtons();
  _bindDeleteButtons();
  _bindInlineEdit();
  _renderDdays();
  _pollNotify();
}


// =============================================================================
// 완료 버튼 바인딩
// =============================================================================
function _bindDoneButtons() {
  document.querySelectorAll(".worktask-done-btn").forEach((btn) => {
    // 중복 바인딩 방지
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
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
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async function () {
      if (this.dataset.submitting === "1") return;
      await _handleAction(this, boot.dataset.skipUrl, "skipped");
    });
  });
}


// =============================================================================
// AJAX 액션 공통 처리 (완료 / 건너뜀)
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
      _updateRowAfterAction(pk, result.status, result.status_display);
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
// 상태 해제 (완료/건너뜀 → 대기)
// =============================================================================
function _bindResetButtons() {
  document.querySelectorAll(".worktask-reset-btn").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async function () {
      if (this.dataset.submitting === "1") return;
      this.dataset.submitting = "1";
      this.disabled = true;

      const pk = this.dataset.pk;

      try {
        const url    = _buildActionUrl(boot.dataset.resetUrl, pk);
        const result = await _postJson(url);

        if (result.ok) {
          // 상태 badge 갱신
          const badge = document.getElementById(`status-badge-${pk}`);
          if (badge) {
            badge.dataset.status = result.status;
            badge.textContent    = result.status_display;
          }

          // 행 스타일 복원 + 액션 셀 재구성
          const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
          if (row) {
            row.dataset.status = result.status;
            row.classList.remove("worktask-done");

            const actionCell = row.querySelector("td:last-child");
            if (actionCell) {
              const titleAttr = (this.dataset.title || "").replace(/"/g, "&quot;");
              actionCell.innerHTML = `
                <button class="btn btn-success btn-sm worktask-done-btn"
                        data-pk="${pk}" title="완료">✓</button>
                <button class="btn btn-outline-secondary btn-sm worktask-skip-btn ms-1"
                        data-pk="${pk}" title="건너뜀">↷</button>
                <button class="btn btn-outline-danger btn-sm worktask-delete-btn ms-1"
                        data-pk="${pk}" data-title="${titleAttr}" title="삭제">🗑</button>
              `;
              // 새로 생성된 버튼에 이벤트 바인딩
              _bindDoneButtons();
              _bindSkipButtons();
              _bindDeleteButtons();
            }
          }
        } else {
          alert(result.error || "처리 중 오류가 발생했습니다.");
          this.dataset.submitting = "";
          this.disabled = false;
        }
      } catch (e) {
        console.error("[worktask_list] reset error:", e);
        alert("네트워크 오류가 발생했습니다.");
        this.dataset.submitting = "";
        this.disabled = false;
      }
    });
  });
}


// =============================================================================
// 삭제 버튼 바인딩
// =============================================================================
function _bindDeleteButtons() {
  document.querySelectorAll(".worktask-delete-btn").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async function () {
      if (this.dataset.submitting === "1") return;

      const title = this.dataset.title || "이 업무";
      if (!confirm(`"${title}" 을(를) 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

      this.dataset.submitting = "1";
      this.disabled = true;

      const pk = this.dataset.pk;

      try {
        const url    = _buildActionUrl(boot.dataset.deleteUrl, pk);
        const result = await _postJson(url);

        if (result.ok) {
          const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
          if (row) row.remove();
        } else {
          alert(result.error || "삭제 중 오류가 발생했습니다.");
          this.dataset.submitting = "";
          this.disabled = false;
        }
      } catch (e) {
        console.error("[worktask_list] delete error:", e);
        alert("네트워크 오류가 발생했습니다.");
        this.dataset.submitting = "";
        this.disabled = false;
      }
    });
  });
}


// =============================================================================
// 행 상태 갱신 — 완료/건너뜀 처리 후 액션 셀 교체
// =============================================================================
function _updateRowAfterAction(pk, status, statusDisplay) {
  const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
  if (!row) return;

  // 상태 badge 갱신
  const badge = document.getElementById(`status-badge-${pk}`);
  if (badge) {
    badge.dataset.status = status;
    badge.textContent    = statusDisplay;
  }

  row.dataset.status = status;

  if (status === "done" || status === "skipped") {
    row.classList.add("worktask-done");

    // 현재 행의 title 데이터 추출 (삭제 버튼에 필요)
    const existingDeleteBtn = row.querySelector(".worktask-delete-btn");
    const titleAttr = (existingDeleteBtn?.dataset?.title || "").replace(/"/g, "&quot;");

    const actionCell = row.querySelector("td:last-child");
    if (actionCell) {
      actionCell.innerHTML = `
        <button class="btn btn-outline-secondary btn-sm worktask-reset-btn"
                data-pk="${pk}" data-title="${titleAttr}" title="대기로 복원">↩</button>
        <button class="btn btn-outline-danger btn-sm worktask-delete-btn ms-1"
                data-pk="${pk}" data-title="${titleAttr}" title="삭제">🗑</button>
      `;
      // 새로 생성된 버튼에 이벤트 바인딩
      _bindResetButtons();
      _bindDeleteButtons();
    }
  }
}


// =============================================================================
// 인라인 셀 편집 (분류 / 우선순위 / 시작일 / 마감일)
// =============================================================================
function _bindInlineEdit() {
  // 분류 옵션 파싱 — CSP 안전 data 블록에서 읽음
  let categoryOptions = [];
  try {
    const optEl = document.getElementById("worktask-category-options");
    if (optEl) categoryOptions = JSON.parse(optEl.textContent);
  } catch (_) {}

  document.querySelectorAll(".worktask-cell-edit").forEach((cell) => {
    if (cell.dataset.editBound === "1") return;
    cell.dataset.editBound = "1";
    cell.style.cursor = "pointer";
    cell.title = "클릭하여 편집";

    cell.addEventListener("click", function (e) {
      if (this.dataset.editing === "1") return;
      // 이미 에디터가 활성화된 셀 내부 클릭은 무시
      if (e.target.closest("select, input")) return;

      this.dataset.editing = "1";
      const field   = this.dataset.field;
      const value   = this.dataset.value || "";
      const pk      = this.dataset.pk;
      const display = this.querySelector(".worktask-cell-display");
      if (!display) { delete this.dataset.editing; return; }

      // ── 에디터 생성 ──────────────────────────────────────
      let editor;

      if (field === "category") {
        editor = document.createElement("select");
        editor.className = "form-select form-select-sm";
        categoryOptions.forEach((opt) => {
          const o = document.createElement("option");
          o.value = opt.code;
          o.textContent = opt.label;
          if (opt.code === value) o.selected = true;
          editor.appendChild(o);
        });

      } else if (field === "priority") {
        editor = document.createElement("select");
        editor.className = "form-select form-select-sm";
        [["high", "상"], ["mid", "중"], ["low", "하"]].forEach(([v, l]) => {
          const o = document.createElement("option");
          o.value = v;
          o.textContent = l;
          if (v === value) o.selected = true;
          editor.appendChild(o);
        });

      } else {
        // start_date / due_date
        editor = document.createElement("input");
        editor.type = "date";
        editor.className = "form-control form-control-sm";
        editor.value = value;
      }

      display.replaceWith(editor);
      editor.focus();

      // ── 저장 처리 ────────────────────────────────────────
      const cell = this; // closure 캡처

      const restoreDisplay = (text) => {
        delete cell.dataset.editing;
        const orig = document.createElement("span");
        orig.className = "worktask-cell-display";
        orig.textContent = text || "—";
        editor.replaceWith(orig);
      };

      const save = async () => {
        // blur + change 둘 다 발생할 수 있으므로 중복 실행 방지
        if (editor.dataset.saving === "1") return;
        editor.dataset.saving = "1";

        const newVal = editor.value;
        delete cell.dataset.editing;

        try {
          const url    = _buildActionUrl(boot.dataset.inlineUrl, pk);
          const result = await _postJsonBody(url, { field, value: newVal });

          if (result.ok) {
            cell.dataset.value = newVal;
            const newDisplay = document.createElement("span");
            newDisplay.className = "worktask-cell-display";

            if (field === "priority") {
              const colorMap = { high: "danger", mid: "warning text-dark", low: "secondary" };
              const labelMap = { high: "상", mid: "중", low: "하" };
              newDisplay.innerHTML = `<span class="badge bg-${colorMap[newVal] || "secondary"}">${labelMap[newVal] || newVal}</span>`;

            } else if (field === "category") {
              newDisplay.innerHTML = `<span class="badge bg-secondary">${result.display || newVal}</span>`;

            } else {
              // start_date / due_date
              if (newVal) {
                newDisplay.textContent = result.display || newVal;
              } else {
                newDisplay.innerHTML = `<span class="text-muted">—</span>`;
              }
              // due_date 변경 시 D-day 재계산
              if (field === "due_date") {
                const ddayEl = cell.querySelector("[data-dday]");
                if (ddayEl) {
                  ddayEl.dataset.dday = newVal;
                  _renderDdays();
                }
              }
            }
            editor.replaceWith(newDisplay);

          } else {
            alert(result.error || "저장 실패");
            restoreDisplay(value);
          }

        } catch (err) {
          console.error("[worktask_list] inline update error:", err);
          alert("네트워크 오류가 발생했습니다.");
          restoreDisplay(value);
        }
      };

      editor.addEventListener("change", save);
      editor.addEventListener("blur",   save);
      editor.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
          restoreDisplay(value);
        }
      });
    });
  });
}


// =============================================================================
// D-day 렌더링
// =============================================================================
function _renderDdays() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  document.querySelectorAll("[data-dday]").forEach((el) => {
    const dueDateStr = el.dataset.dday;
    if (!dueDateStr) { el.textContent = ""; return; }

    const due = new Date(dueDateStr);
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
 * "/board/worktasks/0/done/" → "/board/worktasks/42/done/"
 */
function _buildActionUrl(template, pk) {
  if (!template) return "";
  return template.replace(/\/0\//, `/${pk}/`);
}

/** CSRF 포함 POST (form body) + JSON 파싱 */
async function _postJson(url) {
  const res = await fetch(url, {
    method:  "POST",
    headers: {
      "X-CSRFToken":      getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
  });
  return _safeJson(res);
}

/** CSRF 포함 POST (JSON body) + JSON 파싱 — 인라인 편집용 */
async function _postJsonBody(url, body) {
  const res = await fetch(url, {
    method:  "POST",
    headers: {
      "X-CSRFToken":      getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
      "Content-Type":     "application/json",
    },
    body: JSON.stringify(body),
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