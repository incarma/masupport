/**
 * static/js/board/worktask_list.js
 * =============================================================================
 * WorkTask 목록 페이지 전용 JS.
 *
 * 역할:
 *   - 인라인 셀 편집 (분류 / 우선순위 / 시작일 / 마감일 / 상태)
 *   - 삭제 처리
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


// =============================================================================
// 초기화
// =============================================================================
function _init() {
  _initCalendar();
  _bindDeleteButtons();
  _bindInlineEdit();
  _renderDdays();
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
// 인라인 셀 편집 (분류 / 우선순위 / 시작일 / 마감일 / 상태)
// =============================================================================
function _bindInlineEdit() {
  // 분류 옵션 파싱 — CSP 안전 data 블록에서 읽음
  let categoryOptions = [];
  try {
    const optEl = document.getElementById("worktask-category-options");
    if (optEl) categoryOptions = JSON.parse(optEl.textContent);
  } catch (_) {}

  let statusOptions = [];
  try {
    const statusEl = document.getElementById("worktask-status-options");
    if (statusEl) statusOptions = JSON.parse(statusEl.textContent);
  } catch (_) {}

  document.querySelectorAll(".worktask-cell-edit").forEach((cell) => {
    if (cell.dataset.editBound === "1") return;
    cell.dataset.editBound = "1";
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
          o.dataset.order = opt.order || "0";
          o.dataset.label = opt.label || "";
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

      } else if (field === "status") {
        editor = document.createElement("select");
        editor.className = "form-select form-select-sm worktask-status-select";
        statusOptions.forEach((opt) => {
          const o = document.createElement("option");
          o.value = opt.value;
          o.textContent = opt.label;
          if (opt.value === value) o.selected = true;
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
      const previousHTML = display.innerHTML;

      const restoreDisplay = () => {
        delete cell.dataset.editing;
        const orig = document.createElement("span");
        orig.className = "worktask-cell-display";
        orig.innerHTML = previousHTML;
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
              const labelMap = { high: "상", mid: "중", low: "하" };
              const badge = document.createElement("span");
              badge.className = "worktask-priority-badge";
              badge.dataset.priority = newVal;
              badge.textContent = result.display || labelMap[newVal] || newVal || "-";
              newDisplay.appendChild(badge);
            } else if (field === "status") {
              const selectedOpt = editor.options[editor.selectedIndex];
              const badge = document.createElement("span");
              badge.className = "worktask-badge status-badge";
              badge.id = `status-badge-${pk}`;
              badge.dataset.status = newVal;
              badge.textContent = result.display || selectedOpt?.textContent || newVal;
              newDisplay.appendChild(badge);

              const row = document.querySelector(`.worktask-row[data-pk="${pk}"]`);
              if (row) {
                row.dataset.status = newVal;
                row.classList.toggle("worktask-done", newVal === "done" || newVal === "skipped");
              }
            } else if (field === "category") {
              const selectedOpt = editor.options[editor.selectedIndex];
              const badge = document.createElement("span");
              badge.className = "worktask-category-badge";
              badge.textContent = result.display || selectedOpt?.textContent || newVal || "-";
              newDisplay.appendChild(badge);
            } else {
              // start_date / due_date
              if (newVal) {
                const dateText = document.createElement("span");
                dateText.textContent = result.display || newVal;
                newDisplay.appendChild(dateText);

                if (field === "due_date") {
                  const dday = document.createElement("small");
                  dday.className = "worktask-dday-badge ms-1";
                  dday.dataset.dday = newVal;
                  newDisplay.appendChild(dday);
                }
              } else {
                newDisplay.innerHTML = `<span class="text-muted">-</span>`;
              }
            }
            editor.replaceWith(newDisplay);
            if (field === "due_date") _renderDdays();

          } else {
            alert(result.error || "저장 실패");
            restoreDisplay();
          }

        } catch (err) {
          console.error("[worktask_list] inline update error:", err);
          alert("네트워크 오류가 발생했습니다.");
          restoreDisplay();
        }
      };

      editor.addEventListener("change", save);
      editor.addEventListener("blur",   save);
      editor.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
          restoreDisplay();
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
// 캘린더 렌더링
// =============================================================================
function _initCalendar() {
  const root = document.getElementById("worktask-calendar");
  const toggle = document.getElementById("worktask-calendar-toggle");
  const prevBtn = document.getElementById("worktask-calendar-prev");
  const nextBtn = document.getElementById("worktask-calendar-next");
  const todayBtn = document.getElementById("worktask-calendar-today");
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  const items = _readCalendarItems();
  let view = boot.dataset.calendarView || root.dataset.view || "week";

  root.dataset.view = view;
  _renderCalendar(root, items, view);
  _syncCalendarHeader(view);

  toggle?.addEventListener("click", () => {
    view = view === "week" ? "month" : "week";
    _moveCalendar({ view, anchor: boot.dataset.calendarAnchor || boot.dataset.calendarToday });
  });

  prevBtn?.addEventListener("click", () => _shiftCalendar(view, -1));
  nextBtn?.addEventListener("click", () => _shiftCalendar(view, 1));
  todayBtn?.addEventListener("click", () => _moveCalendar({
    view,
    anchor: boot.dataset.calendarToday,
  }));
}

function _shiftCalendar(view, amount) {
  const anchor = _dateFromKey(boot.dataset.calendarAnchor || boot.dataset.calendarToday);
  if (!anchor) return;

  if (view === "month") {
    anchor.setMonth(anchor.getMonth() + amount);
  } else {
    anchor.setDate(anchor.getDate() + amount * 7);
  }

  _moveCalendar({ view, anchor: _dateKey(anchor) });
}

function _moveCalendar({ view, anchor }) {
  const url = new URL(window.location.href);
  url.searchParams.set("cal_view", view);
  url.searchParams.set("cal_anchor", anchor);
  window.location.href = url.toString();
}

function _syncCalendarHeader(view) {
  const title = document.getElementById("worktask-calendar-title");
  const subtitle = document.getElementById("worktask-calendar-subtitle");
  const toggle = document.getElementById("worktask-calendar-toggle");
  const todayBtn = document.getElementById("worktask-calendar-today");

  const anchor = _dateFromKey(boot.dataset.calendarAnchor || boot.dataset.calendarToday);
  const todayKey = boot.dataset.calendarToday;
  const anchorKey = boot.dataset.calendarAnchor || todayKey;
  if (!anchor) return;

  if (view === "month") {
    if (title) title.textContent = `${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월`;
    if (subtitle) subtitle.textContent = "월간 캘린더";
    if (toggle) {
      toggle.textContent = "↩ 주간";
      toggle.setAttribute("aria-label", "주간 캘린더로 전환");
    }
  } else {
    const weekNo = _weekOfMonth(anchor);
    if (title) title.textContent = `${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월 ${weekNo}주차`;
    if (subtitle) subtitle.textContent = "주간 캘린더";
    if (toggle) {
      toggle.textContent = "🗓 월간";
      toggle.setAttribute("aria-label", "월간 캘린더로 전환");
    }
  }

  todayBtn?.classList.toggle("d-none", anchorKey === todayKey);
}

function _weekOfMonth(d) {
  const first = new Date(d.getFullYear(), d.getMonth(), 1);
  const firstMondayOffset = (first.getDay() + 6) % 7;
  return Math.ceil((d.getDate() + firstMondayOffset) / 7);
}

function _readCalendarItems() {
  const el = document.getElementById("worktask-calendar-items");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent || "[]");
  } catch (e) {
    console.warn("[worktask_list] calendar json parse failed", e);
    return [];
  }
}

function _renderCalendar(root, items, view) {
  const startKey = view === "month"
    ? boot.dataset.calendarMonthStart
    : boot.dataset.calendarWeekStart;
  const endKey = view === "month"
    ? boot.dataset.calendarMonthEnd
    : boot.dataset.calendarWeekEnd;
  const todayKey = boot.dataset.calendarToday;

  const start = _dateFromKey(startKey);
  const end = _dateFromKey(endKey);
  if (!start || !end) return;

  const dayKeys = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const day = d.getDay(); // 0=일, 6=토
    if (day !== 0 && day !== 6) {
      dayKeys.push(_dateKey(d));
    }
  }

  const html = [];

  html.push(`<div class="worktask-calendar-head">`);
  const dayNames = ["월", "화", "수", "목", "금"];
  dayNames.forEach((name) => {
    html.push(`<div class="worktask-calendar-weekday">${name}</div>`);
  });
  html.push(`</div>`);

  html.push(`<div class="worktask-calendar-grid worktask-calendar-grid-${view}">`);

  dayKeys.forEach((key) => {
    const dayItems = items.filter((item) => item.start <= key && item.end >= key);
    const dateObj = _dateFromKey(key);
    const dateLabel = dateObj ? dateObj.getDate() : key;

    html.push(`
      <div class="worktask-calendar-day${key === todayKey ? " is-today" : ""}">
        <div class="worktask-calendar-date">${dateLabel}</div>
        <div class="worktask-calendar-items">
    `);

    dayItems.forEach((item) => {
      const isSpan = item.display_type === "span";
      html.push(`
        <a class="worktask-calendar-item priority-${_escAttr(item.priority)}${isSpan ? " is-span" : ""}"
           href="/board/worktasks/${encodeURIComponent(item.id)}/"
           title="${_escAttr(item.title)}">
          ${_escHtml(item.title)}
        </a>
      `);
    });

    html.push(`
        </div>
      </div>
    `);
  });

  html.push(`</div>`);
  root.innerHTML = html.join("");
  _syncCalendarHeader(view);
}

function _dateFromKey(key) {
  if (!key) return null;
  const d = new Date(`${key}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function _dateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function _escHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function _escAttr(v) {
  return _escHtml(v).replaceAll("`", "&#096;");
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