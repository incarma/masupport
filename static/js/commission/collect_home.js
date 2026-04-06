/**
 * django_ma/static/js/commission/collect_home.js
 * =============================================================================
 * 환수관리(Collect Home) 페이지 전용 JS — type="module"
 *
 * [설계 원칙]
 * - id="collect-home" Boot div의 dataset만 읽는다 (하드코딩 URL 금지)
 * - 모든 fetch: credentials:"same-origin" + X-Requested-With + X-CSRFToken
 * - 중복 제출 방지: btn.dataset.submitting = "1" 패턴 필수
 * - BFCache 대응: pageshow 이벤트
 * - DOM 존재 가드: if (!el) return 필수
 * - search_user_modal.js의 userSelected 이벤트 수신으로 대상자 선택 처리
 * - 중복 초기화 방지: root.dataset.inited === "1" 가드
 * =============================================================================
 */

// ============================================================
// 0) Boot Guard — root 없으면 즉시 종료
// ============================================================
const root = document.getElementById("collect-home");
if (!root) throw new Error("[collect_home] #collect-home not found");

// 중복 초기화 방지 (BFCache/재진입 대비)
if (root.dataset.inited === "1") throw new Error("[collect_home] already inited");
root.dataset.inited = "1";

const ds = root.dataset;

// ============================================================
// 1) URL Config — dataset에서만 읽기 (SSOT)
// ============================================================
const URLS = {
  list:           ds.apiListUrl,
  ymList:         ds.apiYmListUrl,
  feedbackList:   ds.apiFeedbackListUrl,
  feedbackCreate: ds.apiFeedbackCreateUrl,
  feedbackUpdate: ds.apiFeedbackUpdateUrl,
  feedbackDelete: ds.apiFeedbackDeleteUrl,
};

// ============================================================
// 2) 상태 관리
// ============================================================
const state = {
  tab:             "all",         // 현재 활성 탭
  ym:              ds.defaultYm || "", // 현재 선택 월도 (YYYYMM)
  part:            "",
  bizmoon:         "",
  selectedEmpId:   "",            // 피드백 모달 대상자 사번
  selectedEmpName: "",            // 피드백 모달 대상자 성명
};

// ============================================================
// 3) 유틸 함수
// ============================================================

/** CSRF 토큰 — window.csrfToken → form hidden → cookie 우선순위 */
function getCSRF() {
  return (
    window.csrfToken ||
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    ""
  );
}

/** XSS 방어용 HTML escape */
function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/** 금액 천단위 콤마 포맷 */
function fmtMoney(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("ko-KR");
}

/** Bootstrap Modal 인스턴스 가져오기 또는 새로 생성 */
function getOrCreateModal(id) {
  const el = document.getElementById(id);
  if (!el || !window.bootstrap?.Modal) return null;
  return bootstrap.Modal.getOrCreateInstance(el);
}

// ============================================================
// 4) GET fetch 헬퍼
// ============================================================
async function apiFetch(url, params = {}) {
  const u = new URL(url, location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined) u.searchParams.set(k, String(v));
  });
  const res = await fetch(u.toString(), {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  const data = await res.json().catch(() => ({}));
  return data;
}

// ============================================================
// 5) POST fetch 헬퍼
// ============================================================
async function apiPost(url, payload = {}) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type":     "application/json",
      "X-CSRFToken":      getCSRF(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(payload),
  });
  return res.json().catch(() => ({}));
}

// ============================================================
// 6) 탭별 thead HTML
// ============================================================

/** 탭별 컬럼 정의 */
const TAB_COLS = {
  all: [
    { label: "부서" },    { label: "부문" },     { label: "영업가족" },
    { label: "사원명" },  { label: "사번" },     { label: "재직상태" },
    { label: "당월 최종지급액", money: true },
    { label: "최신 피드백" },
  ],
  new: [
    { label: "부서" },    { label: "부문" },     { label: "영업가족" },
    { label: "사원명" },  { label: "사번" },     { label: "재직상태" },
    { label: "전월 최종지급액", money: true },
    { label: "당월 최종지급액", money: true },
    { label: "최신 피드백" },
  ],
  long3: [
    { label: "부서" },    { label: "부문" },     { label: "영업가족" },
    { label: "사원명" },  { label: "사번" },     { label: "재직상태" },
    { label: "2개월전 최종지급액", money: true },
    { label: "당월 최종지급액", money: true },
    { label: "최신 피드백" },
  ],
  long6: [
    { label: "부서" },    { label: "부문" },     { label: "영업가족" },
    { label: "사원명" },  { label: "사번" },     { label: "재직상태" },
    { label: "5개월전 최종지급액", money: true },
    { label: "당월 최종지급액", money: true },
    { label: "최신 피드백" },
  ],
  long12: [
    { label: "부서" },    { label: "부문" },     { label: "영업가족" },
    { label: "사원명" },  { label: "사번" },     { label: "재직상태" },
    { label: "11개월전 최종지급액", money: true },
    { label: "당월 최종지급액", money: true },
    { label: "최신 피드백" },
  ],
};

function renderTableHead(tab) {
  const thead = document.getElementById("collectTableHead");
  if (!thead) return;
  const cols = TAB_COLS[tab] || TAB_COLS.all;
  thead.innerHTML = `<tr>${
    cols.map(c =>
      `<th class="text-nowrap${c.money ? " text-end" : ""}">${esc(c.label)}</th>`
    ).join("")
  }</tr>`;
}

// ============================================================
// 7) 테이블 본문 렌더링
// ============================================================

/** 금액 td (음수 → .amount-negative 강조) */
function moneyTd(val) {
  const n = Number(val);
  const cls = Number.isFinite(n) && n < 0 ? " amount-negative" : "";
  return `<td class="text-end text-nowrap${cls}">${fmtMoney(val)}</td>`;
}

function buildRowHtml(row, tab) {
  // 공통 셀
  const commonCells = `
    <td class="text-nowrap">${esc(row.part    || "-")}</td>
    <td class="text-nowrap">${esc(row.bizmoon || "-")}</td>
    <td class="text-nowrap">${esc(row.branch  || "-")}</td>
    <td class="text-nowrap">${esc(row.emp_name || "-")}</td>
    <td class="text-nowrap">
      <span class="collect-emp-id-cell"
            data-emp-id="${esc(row.emp_id)}"
            data-emp-name="${esc(row.emp_name || "")}">
        ${esc(row.emp_id)}
      </span>
    </td>
    <td class="text-nowrap">${esc(row.work_status || "-")}</td>`;

  // 탭별 금액 셀
  let moneyCells = "";
  if (tab === "all") {
    moneyCells = moneyTd(row.final_payment);
  } else if (tab === "new") {
    moneyCells = moneyTd(row.prev_payment) + moneyTd(row.final_payment);
  } else {
    // long3 / long6 / long12
    moneyCells = moneyTd(row.oldest_payment) + moneyTd(row.final_payment);
  }

  // 최신 피드백 셀 (말줄임, 클릭 시 피드백 모달 오픈)
  const fbCell = row.latest_feedback
    ? `<td><span class="collect-feedback-cell"
               data-emp-id="${esc(row.emp_id)}"
               data-emp-name="${esc(row.emp_name || "")}"
               title="${esc(row.latest_feedback)}">
         ${esc(row.latest_feedback)}
       </span></td>`
    : `<td class="text-muted small">-</td>`;

  return `<tr>${commonCells}${moneyCells}${fbCell}</tr>`;
}

function renderCollectTable(rows, tab) {
  const tbody = document.getElementById("collectTableBody");
  if (!tbody) return;

  if (!rows || rows.length === 0) {
    const colCount = (TAB_COLS[tab] || TAB_COLS.all).length;
    tbody.innerHTML = `
      <tr>
        <td colspan="${colCount}" class="text-center text-muted py-4">
          해당 조건의 환수 대상자가 없습니다.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = rows.map(r => buildRowHtml(r, tab)).join("");
}

// ============================================================
// 8) 환수 목록 조회
// ============================================================
async function fetchCollectList() {
  if (!state.ym) return;

  const tbody = document.getElementById("collectTableBody");
  const colCount = (TAB_COLS[state.tab] || TAB_COLS.all).length;
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="${colCount}" class="text-center text-muted py-4">조회 중...</td>
      </tr>`;
  }

  try {
    const data = await apiFetch(URLS.list, {
      tab:     state.tab,
      ym:      state.ym,
      part:    state.part,
      bizmoon: state.bizmoon,
    });

    if (!data.ok) {
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="${colCount}" class="text-center text-danger py-4">
              ${esc(data.message || "조회 실패")}
            </td>
          </tr>`;
      }
      return;
    }

    renderTableHead(state.tab);
    renderCollectTable(data.data?.rows ?? [], state.tab);

  } catch (err) {
    console.error("[collect_home] fetchCollectList 오류:", err);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="${colCount}" class="text-center text-danger py-4">
            조회 중 오류가 발생했습니다.
          </td>
        </tr>`;
    }
  }
}

// ============================================================
// 9) 월도 목록 갱신 (업로드 후 드롭다운 동적 갱신용)
// ============================================================
async function refreshYmSelect() {
  const ymSelect = document.getElementById("ymSelect");
  if (!ymSelect) return;

  try {
    const data = await apiFetch(URLS.ymList);
    if (!data.ok || !data.data?.yms?.length) return;

    const yms = data.data.yms;
    const current = ymSelect.value;

    ymSelect.innerHTML = yms.map(ym =>
      `<option value="${esc(ym)}"${ym === current ? " selected" : ""}>${esc(ym)}</option>`
    ).join("");

    // 현재 선택값이 목록에 없으면 첫 번째로
    if (!yms.includes(current) && yms.length) {
      ymSelect.value = yms[0];
      state.ym = yms[0];
    }
  } catch (err) {
    console.error("[collect_home] refreshYmSelect 오류:", err);
  }
}

// ============================================================
// 10) 피드백 목록 렌더링
// ============================================================
function renderFeedbackList(feedbacks) {
  const container = document.getElementById("feedbackListBody");
  if (!container) return;

  if (!feedbacks || feedbacks.length === 0) {
    container.innerHTML = `<div class="text-muted small text-center py-3">등록된 피드백이 없습니다.</div>`;
    return;
  }

  // data-current-user-id: 본인 여부 판단 (서버 재검증 필수)
  const currentUserId = String(ds.currentUserId || "");

  container.innerHTML = feedbacks.map(fb => {
    const isMine = String(fb.author_id) === currentUserId;

    const modifiedMark = fb.is_modified
      ? `<span class="collect-feedback-modified ms-1">(수정됨: ${esc(fb.updated_at)})</span>`
      : "";

    // 수정·삭제 버튼: 본인 것만 노출 (서버에서 최종 재검증)
    const actionBtns = isMine ? `
      <div class="collect-feedback-actions mt-1">
        <button type="button"
                class="btn btn-outline-secondary btn-sm feedback-edit-btn"
                data-feedback-id="${fb.id}"
                data-content="${esc(fb.content)}">수정</button>
        <button type="button"
                class="btn btn-outline-danger btn-sm feedback-delete-btn"
                data-feedback-id="${fb.id}">삭제</button>
      </div>` : "";

    return `
      <div class="collect-feedback-item" data-feedback-id="${fb.id}">
        <div class="d-flex justify-content-between align-items-start">
          <div class="small text-muted">
            <strong>${esc(fb.author_name)}</strong>(${esc(String(fb.author_id))})
            · ${esc(fb.created_at)}${modifiedMark}
          </div>
        </div>
        <div class="feedback-content-area mt-1 small">${esc(fb.content)}</div>
        ${actionBtns}
      </div>`;
  }).join("");
}

// ============================================================
// 11) 피드백 목록 조회
// ============================================================
async function fetchFeedbacks(empId) {
  const container = document.getElementById("feedbackListBody");
  if (!container) return;
  if (!empId) {
    container.innerHTML = `<div class="text-muted small text-center py-3">대상자를 선택해주세요.</div>`;
    return;
  }

  container.innerHTML = `<div class="text-muted small text-center py-3">조회 중...</div>`;

  try {
    const data = await apiFetch(URLS.feedbackList, { emp_id: empId });
    if (!data.ok) {
      container.innerHTML = `<div class="text-danger small text-center py-3">${esc(data.message || "조회 실패")}</div>`;
      return;
    }
    renderFeedbackList(data.data?.feedbacks ?? []);
  } catch (err) {
    console.error("[collect_home] fetchFeedbacks 오류:", err);
    container.innerHTML = `<div class="text-danger small text-center py-3">오류가 발생했습니다.</div>`;
  }
}

// ============================================================
// 12) 대상자 선택 표시 갱신
// ============================================================
function updateTargetDisplay(empId, empName) {
  const el = document.getElementById("selectedTargetDisplay");
  if (!el) return;
  if (!empId) {
    el.textContent = "대상자를 선택해주세요.";
    return;
  }
  el.innerHTML = `<strong>${esc(empName || empId)}</strong> <span class="text-muted">(${esc(empId)})</span>`;
}

// ============================================================
// 13) 피드백 수정 인라인 처리
// ============================================================
function startFeedbackEdit(itemEl, feedbackId, originalContent) {
  if (!itemEl || itemEl.dataset.editing === "1") return;
  itemEl.dataset.editing = "1";

  const contentArea = itemEl.querySelector(".feedback-content-area");
  if (contentArea) contentArea.hidden = true;

  const editDiv = document.createElement("div");
  editDiv.className = "feedback-edit-area mt-1";
  editDiv.innerHTML = `
    <textarea class="form-control form-control-sm mb-1" rows="3"
              maxlength="2000">${esc(originalContent)}</textarea>
    <div class="d-flex gap-1 justify-content-end">
      <button type="button"
              class="btn btn-primary btn-sm feedback-edit-save-btn"
              data-feedback-id="${feedbackId}">저장</button>
      <button type="button"
              class="btn btn-outline-secondary btn-sm feedback-edit-cancel-btn"
              data-feedback-id="${feedbackId}">취소</button>
    </div>`;
  itemEl.appendChild(editDiv);
}

function cancelFeedbackEdit(itemEl) {
  if (!itemEl) return;
  itemEl.dataset.editing = "";
  const editDiv = itemEl.querySelector(".feedback-edit-area");
  if (editDiv) editDiv.remove();
  const contentArea = itemEl.querySelector(".feedback-content-area");
  if (contentArea) contentArea.hidden = false;
}

// ============================================================
// 14) 이벤트 바인딩
// ============================================================
function bindEvents() {

  // ── 탭 클릭 ──────────────────────────────────────────────
  const tabsEl = document.getElementById("collectTabs");
  if (tabsEl) {
    tabsEl.addEventListener("click", e => {
      const btn = e.target?.closest?.("[data-tab]");
      if (!btn) return;
      tabsEl.querySelectorAll("[data-tab]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.tab = btn.dataset.tab;
      fetchCollectList();
    });
  }

  // ── 조회 버튼 ─────────────────────────────────────────────
  const searchBtn = document.getElementById("collectSearchBtn");
  if (searchBtn) {
    searchBtn.addEventListener("click", () => {
      state.ym      = document.getElementById("ymSelect")?.value      || "";
      state.part    = document.getElementById("partSelect")?.value    || "";
      state.bizmoon = document.getElementById("bizmoonSelect")?.value || "";
      fetchCollectList();
    });
  }

  // ── 월도 드롭다운 변경 → 즉시 조회 ───────────────────────
  const ymSelect = document.getElementById("ymSelect");
  if (ymSelect) {
    ymSelect.addEventListener("change", () => {
      state.ym = ymSelect.value;
      fetchCollectList();
    });
  }

  // ── 피드백 관리 버튼 (대상자 미선택 상태로 모달 오픈) ─────
  const openFbBtn = document.getElementById("openFeedbackManagerBtn");
  if (openFbBtn) {
    openFbBtn.addEventListener("click", () => {
      state.selectedEmpId   = "";
      state.selectedEmpName = "";
      updateTargetDisplay("", "");
      fetchFeedbacks("");
      const textarea = document.getElementById("feedbackContent");
      if (textarea) textarea.value = "";
      getOrCreateModal("feedbackManagerModal")?.show();
    });
  }

  // ── 테이블 사번 / 피드백 셀 클릭 → 피드백 모달 오픈 ──────
  const tbody = document.getElementById("collectTableBody");
  if (tbody) {
    tbody.addEventListener("click", e => {
      const cell = e.target?.closest?.(".collect-emp-id-cell, .collect-feedback-cell");
      if (!cell) return;
      state.selectedEmpId   = cell.dataset.empId   || "";
      state.selectedEmpName = cell.dataset.empName || "";
      updateTargetDisplay(state.selectedEmpId, state.selectedEmpName);
      fetchFeedbacks(state.selectedEmpId);
      const textarea = document.getElementById("feedbackContent");
      if (textarea) textarea.value = "";
      getOrCreateModal("feedbackManagerModal")?.show();
    });
  }

  // ── 피드백 저장 버튼 (dataset.submitting 중복 제출 방지) ──
  const submitBtn = document.getElementById("feedbackSubmitBtn");
  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      if (submitBtn.dataset.submitting === "1") return;
      if (!state.selectedEmpId) { alert("대상자를 먼저 선택해주세요."); return; }

      const textarea = document.getElementById("feedbackContent");
      const content  = (textarea?.value || "").trim();
      if (!content) { alert("피드백 내용을 입력해주세요."); return; }

      submitBtn.dataset.submitting = "1";
      submitBtn.disabled = true;

      try {
        const data = await apiPost(URLS.feedbackCreate, {
          emp_id: state.selectedEmpId,
          content,
        });
        if (!data.ok) { alert(data.message || "저장에 실패했습니다."); return; }
        if (textarea) textarea.value = "";
        await fetchFeedbacks(state.selectedEmpId);
        fetchCollectList(); // 테이블 최신 피드백 컬럼 갱신
      } catch (err) {
        console.error("[collect_home] feedbackCreate 오류:", err);
        alert("저장 중 오류가 발생했습니다.");
      } finally {
        submitBtn.dataset.submitting = "0";
        submitBtn.disabled = false;
      }
    });
  }

  // ── 피드백 목록 이벤트 위임 (수정·삭제·저장·취소) ─────────
  const fbListBody = document.getElementById("feedbackListBody");
  if (fbListBody) {
    fbListBody.addEventListener("click", async e => {

      // 수정 버튼
      const editBtn = e.target?.closest?.(".feedback-edit-btn");
      if (editBtn) {
        const itemEl = editBtn.closest(".collect-feedback-item");
        startFeedbackEdit(itemEl, editBtn.dataset.feedbackId, editBtn.dataset.content);
        return;
      }

      // 수정 취소
      const cancelBtn = e.target?.closest?.(".feedback-edit-cancel-btn");
      if (cancelBtn) {
        cancelFeedbackEdit(cancelBtn.closest(".collect-feedback-item"));
        return;
      }

      // 수정 저장 (dataset.submitting 패턴)
      const saveBtn = e.target?.closest?.(".feedback-edit-save-btn");
      if (saveBtn) {
        if (saveBtn.dataset.submitting === "1") return;
        const itemEl  = saveBtn.closest(".collect-feedback-item");
        const textarea = itemEl?.querySelector?.("textarea");
        const content  = (textarea?.value || "").trim();
        if (!content) { alert("내용을 입력해주세요."); return; }

        saveBtn.dataset.submitting = "1";
        saveBtn.disabled = true;
        try {
          const data = await apiPost(URLS.feedbackUpdate, {
            feedback_id: Number(saveBtn.dataset.feedbackId),
            content,
          });
          if (!data.ok) { alert(data.message || "수정에 실패했습니다."); return; }
          await fetchFeedbacks(state.selectedEmpId);
          fetchCollectList();
        } catch (err) {
          console.error("[collect_home] feedbackUpdate 오류:", err);
          alert("수정 중 오류가 발생했습니다.");
        } finally {
          saveBtn.dataset.submitting = "0";
          saveBtn.disabled = false;
        }
        return;
      }

      // 삭제 버튼
      const deleteBtn = e.target?.closest?.(".feedback-delete-btn");
      if (deleteBtn) {
        if (!confirm("피드백을 삭제하시겠습니까?")) return;
        if (deleteBtn.dataset.submitting === "1") return;
        deleteBtn.dataset.submitting = "1";
        deleteBtn.disabled = true;
        try {
          const data = await apiPost(URLS.feedbackDelete, {
            feedback_id: Number(deleteBtn.dataset.feedbackId),
          });
          if (!data.ok) { alert(data.message || "삭제에 실패했습니다."); return; }
          await fetchFeedbacks(state.selectedEmpId);
          fetchCollectList();
        } catch (err) {
          console.error("[collect_home] feedbackDelete 오류:", err);
          alert("삭제 중 오류가 발생했습니다.");
        } finally {
          deleteBtn.dataset.submitting = "0";
          deleteBtn.disabled = false;
        }
      }
    });
  }

  // ── 피드백 모달 닫힘 → 상태 초기화 ──────────────────────
  const fbModal = document.getElementById("feedbackManagerModal");
  if (fbModal) {
    fbModal.addEventListener("hidden.bs.modal", () => {
      state.selectedEmpId   = "";
      state.selectedEmpName = "";
      updateTargetDisplay("", "");
      const container = document.getElementById("feedbackListBody");
      if (container) {
        container.innerHTML = `<div class="text-muted small text-center py-3">대상자를 선택하면 피드백 이력이 표시됩니다.</div>`;
      }
      const textarea = document.getElementById("feedbackContent");
      if (textarea) textarea.value = "";
    });
  }

  // ── search_user_modal.js userSelected 이벤트 수신 ─────────
  // collect-home root가 있는 페이지에서만 처리 (다른 페이지 오염 방지)
  // search_user_modal.js의 collect-home 분기가 발행하는 CustomEvent
  document.addEventListener("userSelected", e => {
    // 피드백 모달이 열려 있을 때만 처리
    const fbModalEl = document.getElementById("feedbackManagerModal");
    if (!fbModalEl?.classList.contains("show")) return;

    const selected = e.detail;
    if (!selected?.id) return;

    state.selectedEmpId   = String(selected.id);
    state.selectedEmpName = selected.name || "";
    updateTargetDisplay(state.selectedEmpId, state.selectedEmpName);
    fetchFeedbacks(state.selectedEmpId);
  });

  // ── 업로드 완료 후 월도 드롭다운 + 테이블 자동 갱신 ──────
  // excel_upload.js가 새로고침 버튼을 클릭하기 전에 갱신되도록
  // excelUploadResultModal이 닫힐 때 refreshYmSelect 호출
  const resultModal = document.getElementById("excelUploadResultModal");
  if (resultModal) {
    resultModal.addEventListener("hidden.bs.modal", async () => {
      await refreshYmSelect();
      if (state.ym) fetchCollectList();
    });
  }

  // ── BFCache 대응: 뒤로가기 복원 시 재조회 ─────────────────
  window.addEventListener("pageshow", e => {
    if (e.persisted) fetchCollectList();
  });
}

// ============================================================
// 15) 초기화
// ============================================================
function init() {
  bindEvents();
  // 초기 thead 렌더링
  renderTableHead(state.tab);
  // 데이터가 있으면 자동 조회
  if (state.ym) fetchCollectList();
}

// DOMContentLoaded 이후 실행 보장
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}