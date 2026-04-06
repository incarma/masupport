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
 *
 * [변경 이력]
 * - sortKey/sortDir 정렬 상태 추가 + AbortController 누적 방지
 * - EXTRA_COLS: bond_total/bond_surety/other_total/refund_expected 컬럼 추가
 * - _searchingUser 플래그: 피드백 모달 ↔ 검색 모달 전환 시 state 보존
 * - feedbackSearchUserBtn: JS로 searchUserModal 직접 오픈 (data-bs-toggle 금지)
 * - searchUserModal hidden 시 feedbackManagerModal 자동 복원
 * - state.branch + 영업가족 드랍다운 동적 갱신 + 클라이언트 필터링
 * - _allTabData 캐시 + SheetJS 기반 엑셀 다운로드 (탭별 시트)
 * =============================================================================
 */

// ============================================================
// 0) Boot Guard — root 없으면 즉시 종료
// ============================================================
const root = document.getElementById("collect-home");
if (!root) throw new Error("[collect_home] #collect-home not found");

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
  tab:             "all",
  ym:              ds.defaultYm || "",
  part:            "",
  bizmoon:         "",
  branch:          "",            // 영업가족(지점) 필터
  selectedEmpId:   "",
  selectedEmpName: "",
  sortKey:         "",
  sortDir:         "asc",
};

// ============================================================
// 3) 유틸 함수
// ============================================================

function getCSRF() {
  return (
    window.csrfToken ||
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    ""
  );
}

function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function fmtMoney(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("ko-KR");
}

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
  return res.json().catch(() => ({}));
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
// 6) 탭별 thead 컬럼 정의
// ============================================================

const COMMON_COLS = [
  { label: "부서",     sortKey: "part" },
  { label: "부문",     sortKey: "bizmoon" },
  { label: "영업가족", sortKey: "branch" },
  { label: "사원명",   sortKey: "emp_name" },
  { label: "사번",     sortKey: "emp_id" },
  { label: "재직상태", sortKey: "work_status" },
];

// 채권합계: CollectRecord.surety_bond_total (엑셀 "보증채권합계" 컬럼 — 가장 안정적)
// 보증합계: surety_bond_detail 파싱 '보증:' 값
// 기타합계: DepositSummary.other_total
// 환수예상: DepositSummary.refund_expected
const EXTRA_COLS = [
  { label: "채권합계",  money: true, sortKey: "bond_total" },
  { label: "보증합계",  money: true, sortKey: "bond_surety" },
  { label: "기타합계",  money: true, sortKey: "other_total" },
  { label: "환수예상",  money: true, sortKey: "refund_expected" },
];

const TAB_COLS = {
  all: [
    ...COMMON_COLS,
    ...EXTRA_COLS,
    { label: "당월 최종지급액",     money: true, sortKey: "final_payment" },
    { label: "최신 피드백" },
  ],
  new: [
    ...COMMON_COLS,
    ...EXTRA_COLS,
    { label: "전월 최종지급액",     money: true, sortKey: "prev_payment" },
    { label: "당월 최종지급액",     money: true, sortKey: "final_payment" },
    { label: "최신 피드백" },
  ],
  long3: [
    ...COMMON_COLS,
    ...EXTRA_COLS,
    { label: "2개월전 최종지급액",  money: true, sortKey: "oldest_payment" },
    { label: "당월 최종지급액",     money: true, sortKey: "final_payment" },
    { label: "최신 피드백" },
  ],
  long6: [
    ...COMMON_COLS,
    ...EXTRA_COLS,
    { label: "5개월전 최종지급액",  money: true, sortKey: "oldest_payment" },
    { label: "당월 최종지급액",     money: true, sortKey: "final_payment" },
    { label: "최신 피드백" },
  ],
  long12: [
    ...COMMON_COLS,
    ...EXTRA_COLS,
    { label: "11개월전 최종지급액", money: true, sortKey: "oldest_payment" },
    { label: "당월 최종지급액",     money: true, sortKey: "final_payment" },
    { label: "최신 피드백" },
  ],
};

// ============================================================
// 6-A) 정렬 상태 및 리스너 누적 방지
// ============================================================

/** 마지막 렌더링된 rows 캐시 — 정렬 재적용 시 사용 */
let _lastRows = [];

/**
 * 정렬 클릭 리스너 누적 방지용 AbortController.
 * renderTableHead 호출마다 이전 컨트롤러 abort() 후 새로 발급.
 */
let _sortAbortCtrl = new AbortController();

function sortRows(rows) {
  if (!state.sortKey) return rows;
  const key = state.sortKey;
  const dir = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[key] ?? "";
    const vb = b[key] ?? "";
    if (typeof va === "number" && typeof vb === "number") {
      return (va - vb) * dir;
    }
    return String(va).localeCompare(String(vb), "ko") * dir;
  });
}

function renderTableHead(tab) {
  const thead = document.getElementById("collectTableHead");
  if (!thead) return;
  const cols = TAB_COLS[tab] || TAB_COLS.all;

  _sortAbortCtrl.abort();
  _sortAbortCtrl = new AbortController();

  thead.innerHTML = `<tr>${
    cols.map(c => {
      const cls = `text-nowrap${c.money ? " text-end" : ""}`;
      if (!c.sortKey) {
        return `<th class="${cls} collect-th-feedback">${esc(c.label)}</th>`;
      }
      const isActive = state.sortKey === c.sortKey;
      const icon = isActive ? (state.sortDir === "asc" ? " ▲" : " ▼") : " ⇅";
      return `<th class="${cls} collect-sort-th"
                  style="cursor:pointer;user-select:none;"
                  data-sort-key="${esc(c.sortKey)}">${esc(c.label)}${icon}</th>`;
    }).join("")
  }</tr>`;

  thead.addEventListener("click", e => {
    const th = e.target.closest("[data-sort-key]");
    if (!th) return;
    const key = th.dataset.sortKey;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = "asc";
    }
    renderTableHead(tab);
    renderCollectTable(_lastRows, tab);
  }, { signal: _sortAbortCtrl.signal });
}

// ============================================================
// 6-B) 탭별 데이터 캐시 — 영업가족 필터 + 엑셀 다운로드 공용
// ============================================================

/**
 * 탭별 서버 응답 원본 rows 캐시 (영업가족 필터 전 데이터).
 * 조회 버튼 클릭 / 탭 전환 시 해당 탭 데이터 덮어씀.
 */
const _allTabData = {
  all:    [],
  new:    [],
  long3:  [],
  long6:  [],
  long12: [],
};

/**
 * 영업가족 드랍다운 동적 갱신.
 * 전체탭 조회 결과(rows)에서 고유 branch 값을 추출하여 옵션 구성.
 * 현재 선택값 유지.
 */
function refreshBranchSelect(rows) {
  const sel = document.getElementById("branchSelect");
  if (!sel) return;

  const current = sel.value;
  const branches = [...new Set(
    rows.map(r => r.branch || "").filter(Boolean)
  )].sort((a, b) => a.localeCompare(b, "ko"));

  sel.innerHTML =
    `<option value="">전체</option>` +
    branches.map(b =>
      `<option value="${esc(b)}"${b === current ? " selected" : ""}>${esc(b)}</option>`
    ).join("");
}

/**
 * 클라이언트 사이드 영업가족 필터링.
 * state.branch가 비어있으면 전체 반환.
 */
function applyBranchFilter(rows) {
  if (!state.branch) return rows;
  return rows.filter(r => (r.branch || "") === state.branch);
}

// ============================================================
// 6-C) 엑셀 다운로드 (SheetJS)
// ============================================================

/** 탭 컬럼 레이블 배열 반환 (엑셀 헤더용) */
function getTabHeaders(tab) {
  return (TAB_COLS[tab] || TAB_COLS.all).map(c => c.label);
}

/**
 * row 객체를 탭 컬럼 순서에 맞는 값 배열로 변환 (엑셀 데이터용).
 * money 컬럼은 숫자 그대로 → 엑셀에서 숫자 셀로 인식.
 */
function rowToArray(row, tab) {
  return (TAB_COLS[tab] || TAB_COLS.all).map(c => {
    if (!c.sortKey) return row.latest_feedback || "";
    const v = row[c.sortKey];
    if (c.money) return typeof v === "number" ? v : (Number(v) || 0);
    return v ?? "";
  });
}

/**
 * SheetJS 기반 엑셀 다운로드.
 * 전체/신규/장기3/6/12 탭 데이터를 시트별로 구분한 1개 파일 생성.
 * 조회된 데이터가 없는 탭은 시트 생성 생략.
 */
function downloadExcel() {
  if (typeof XLSX === "undefined") {
    alert("엑셀 라이브러리를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
    return;
  }

  const TAB_LABELS = {
    all:    "전체",
    new:    "신규",
    long3:  "장기3개월",
    long6:  "장기6개월",
    long12: "장기12개월",
  };

  const wb = XLSX.utils.book_new();
  let hasData = false;

  for (const [tab, label] of Object.entries(TAB_LABELS)) {
    const rows = _allTabData[tab];
    if (!rows || rows.length === 0) continue;
    hasData = true;

    const headers   = getTabHeaders(tab);
    const sheetData = [headers, ...rows.map(r => rowToArray(r, tab))];
    const ws        = XLSX.utils.aoa_to_sheet(sheetData);

    ws["!cols"] = headers.map(() => ({ wch: 15 }));
    XLSX.utils.book_append_sheet(wb, ws, label);
  }

  if (!hasData) {
    alert("다운로드할 데이터가 없습니다. 먼저 조회해주세요.");
    return;
  }

  const ym    = state.ym   || "전체";
  const part  = state.part || "전체부서";
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  XLSX.writeFile(wb, `환수관리_${ym}_${part}_${today}.xlsx`);
}

// ============================================================
// 6-D) 안내문자 스크립트 생성
// ============================================================

/** 입금계좌 — SSOT (변경 시 이 상수만 수정) */
const SMS_ACCOUNT = "027-115958-01-049 기업은행(인카금융서비스)";

/**
 * 대상자 이름과 최종지급액(final_payment)으로 안내문자 스크립트 생성.
 * final_payment는 음수이므로 그대로 천단위 콤마 포맷으로 출력.
 */
function buildSmsTemplate(empName, finalPayment) {
  const name   = empName || "대상자";
  const amount = fmtMoney(finalPayment) + "원";   // 음수 포함 그대로 출력

  return `${name}님 안녕하세요. 인카금융서비스 입니다. ${name}님의 현재 환수금액 및 입금계좌를 안내드립니다.

* 환수금액: ${amount}
* 입금계좌: ${SMS_ACCOUNT}

※ 환수금액이 정상적으로 상환되지 않을 경우 추후 보증보험 청구 등으로 신용상의 불이익이 있을 수 있습니다.
※ 환수금액 입금 시 처리내역 확인을 위해 반드시 연락 바랍니다.
※ 환수 관련 문의사항이 있는 경우 근무하셨던 본부(지점) 관리자에게 연락 바랍니다.`;
}

// ============================================================
// 7) 테이블 본문 렌더링
// ============================================================

function moneyTd(val) {
  const n = Number(val);
  const cls = Number.isFinite(n) && n < 0 ? " amount-negative" : "";
  return `<td class="text-end text-nowrap${cls}">${fmtMoney(val)}</td>`;
}

function buildRowHtml(row, tab) {
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
    <td class="text-nowrap">${esc(row.work_status || "-")}</td>
    ${moneyTd(row.bond_total      ?? 0)}
    ${moneyTd(row.bond_surety     ?? 0)}
    ${moneyTd(row.other_total     ?? 0)}
    ${moneyTd(row.refund_expected ?? 0)}`;

  let moneyCells = "";
  if (tab === "all") {
    moneyCells = moneyTd(row.final_payment);
  } else if (tab === "new") {
    moneyCells = moneyTd(row.prev_payment) + moneyTd(row.final_payment);
  } else {
    moneyCells = moneyTd(row.oldest_payment) + moneyTd(row.final_payment);
  }

  const fbCell = row.latest_feedback
    ? `<td class="collect-td-feedback"><span class="collect-feedback-cell"
               data-emp-id="${esc(row.emp_id)}"
               data-emp-name="${esc(row.emp_name || "")}"
               title="${esc(row.latest_feedback)}">
         ${esc(row.latest_feedback)}
       </span></td>`
    : `<td class="collect-td-feedback text-muted small">-</td>`;

  return `<tr>${commonCells}${moneyCells}${fbCell}</tr>`;
}

function renderCollectTable(rows, tab) {
  _lastRows = rows;
  const sorted = sortRows(rows);
  const tbody  = document.getElementById("collectTableBody");
  if (!tbody) return;

  if (!sorted || sorted.length === 0) {
    const colCount = (TAB_COLS[tab] || TAB_COLS.all).length;
    tbody.innerHTML = `
      <tr>
        <td colspan="${colCount}" class="text-center text-muted py-4">
          해당 조건의 환수 대상자가 없습니다.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = sorted.map(r => buildRowHtml(r, tab)).join("");
}

// ============================================================
// 8) 환수 목록 조회
// ============================================================
async function fetchCollectList() {
  if (!state.ym) return;

  const tbody    = document.getElementById("collectTableBody");
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

    const rawRows = data.data?.rows ?? [];

    // 전체탭 조회 시 영업가족 드랍다운 갱신 (서버 원본 rows 기준)
    if (state.tab === "all") {
      refreshBranchSelect(rawRows);
    }

    // 탭별 캐시 저장 (엑셀 다운로드 — 영업가족 필터 전 원본)
    _allTabData[state.tab] = rawRows;

    // 영업가족 필터 적용 후 렌더링
    const filteredRows = applyBranchFilter(rawRows);

    renderTableHead(state.tab);
    renderCollectTable(filteredRows, state.tab);

    // 엑셀 다운로드 버튼 활성화
    const dlBtn = document.getElementById("collectExcelDownloadBtn");
    if (dlBtn) dlBtn.disabled = false;

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

    const yms     = data.data.yms;
    const current = ymSelect.value;

    ymSelect.innerHTML = yms.map(ym =>
      `<option value="${esc(ym)}"${ym === current ? " selected" : ""}>${esc(ym)}</option>`
    ).join("");

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

  const currentUserId = String(ds.currentUserId || "");

  container.innerHTML = feedbacks.map(fb => {
    const isMine = String(fb.author_id) === currentUserId;

    const modifiedMark = fb.is_modified
      ? `<span class="collect-feedback-modified ms-1">(수정됨: ${esc(fb.updated_at)})</span>`
      : "";

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
  // 안내문자 버튼 활성/비활성 연동
  const smsBtn = document.getElementById("openSmsTemplateBtn");
  if (!empId) {
    el.textContent = "대상자를 선택해주세요.";
    if (smsBtn) smsBtn.disabled = true;
    return;
  }
  el.innerHTML = `<strong>${esc(empName || empId)}</strong> <span class="text-muted">(${esc(empId)})</span>`;
  if (smsBtn) smsBtn.disabled = false;
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
      state.tab     = btn.dataset.tab;
      state.branch  = "";     // 탭 전환 시 영업가족 필터 초기화
      state.sortKey = "";
      state.sortDir = "asc";
      const bSel = document.getElementById("branchSelect");
      if (bSel) bSel.value = "";
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
      state.branch  = "";     // 조회 버튼 클릭 시 영업가족 필터 초기화
      state.sortKey = "";
      state.sortDir = "asc";
      // 영업가족 드랍다운 초기화 (새 조회 결과로 재구성)
      const bSel = document.getElementById("branchSelect");
      if (bSel) bSel.innerHTML = `<option value="">전체</option>`;
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

  // ── 영업가족(지점) 드랍다운 변경 — 클라이언트 필터링 ─────
  // 서버 재요청 없이 _allTabData[현재탭] 캐시에서 필터링하여 재렌더링
  const branchSel = document.getElementById("branchSelect");
  if (branchSel) {
    branchSel.addEventListener("change", () => {
      state.branch  = branchSel.value;
      state.sortKey = "";
      state.sortDir = "asc";
      const cached   = _allTabData[state.tab] ?? [];
      const filtered = applyBranchFilter(cached);
      renderTableHead(state.tab);
      renderCollectTable(filtered, state.tab);
    });
  }

  // ── 엑셀 다운로드 버튼 ────────────────────────────────────
  // 조회 완료 후 활성화됨 (초기 disabled)
  const dlBtn = document.getElementById("collectExcelDownloadBtn");
  if (dlBtn) {
    dlBtn.addEventListener("click", () => {
      downloadExcel();
    });
  }

  // ── 안내문자 버튼 — 피드백 모달에서 대상자 선택 시 활성화 ──
  // 클릭 시: state의 selectedEmpId/Name + 현재 탭 rows에서 final_payment 조회
  const smsBtn = document.getElementById("openSmsTemplateBtn");
  if (smsBtn) {
    smsBtn.addEventListener("click", () => {
      if (!state.selectedEmpId) {
        alert("대상자를 먼저 선택해주세요.");
        return;
      }

      // 현재 탭 캐시에서 대상자 row 탐색 (전체탭 우선, 없으면 다른 탭 순서로)
      const tabOrder = ["all", "new", "long3", "long6", "long12"];
      let targetRow = null;
      for (const tab of tabOrder) {
        const found = (_allTabData[tab] ?? []).find(
          r => r.emp_id === state.selectedEmpId
        );
        if (found) { targetRow = found; break; }
      }

      const finalPayment = targetRow ? (targetRow.final_payment ?? 0) : 0;
      const tmpl = buildSmsTemplate(state.selectedEmpName, finalPayment);

      // 안내문자 모달 렌더링
      const bodyEl = document.getElementById("smsTemplateBody");
      if (bodyEl) bodyEl.textContent = tmpl;

      // 피드백 모달 위에 안내문자 모달 오픈
      // Bootstrap 중첩 모달 우회: 피드백 모달은 닫지 않음
      // smsTemplateModal은 z-index가 더 높게 렌더됨 (Bootstrap 기본 동작)
      getOrCreateModal("smsTemplateModal")?.show();
    });
  }

  // ── 복사 버튼 — Clipboard API 우선, fallback: execCommand ──
  const smsCopyBtn = document.getElementById("smsCopyBtn");
  if (smsCopyBtn) {
    smsCopyBtn.addEventListener("click", async () => {
      const bodyEl = document.getElementById("smsTemplateBody");
      const text   = bodyEl?.textContent || "";
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        // 복사 완료 피드백 (버튼 텍스트 일시 변경)
        smsCopyBtn.textContent = "복사 완료 ✓";
        smsCopyBtn.classList.replace("btn-primary", "btn-success");
        setTimeout(() => {
          smsCopyBtn.textContent = "복사";
          smsCopyBtn.classList.replace("btn-success", "btn-primary");
        }, 2000);
      } catch {
        // Clipboard API 실패 시 fallback
        try {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.opacity  = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
          smsCopyBtn.textContent = "복사 완료 ✓";
          smsCopyBtn.classList.replace("btn-primary", "btn-success");
          setTimeout(() => {
            smsCopyBtn.textContent = "복사";
            smsCopyBtn.classList.replace("btn-success", "btn-primary");
          }, 2000);
        } catch {
          alert("복사에 실패했습니다. 텍스트를 직접 선택하여 복사해주세요.");
        }
      }
    });
  }

  // ── 피드백 관리 버튼 ──────────────────────────────────────
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

  // ── 피드백 저장 버튼 ──────────────────────────────────────
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
        fetchCollectList();
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

      const editBtn = e.target?.closest?.(".feedback-edit-btn");
      if (editBtn) {
        const itemEl = editBtn.closest(".collect-feedback-item");
        startFeedbackEdit(itemEl, editBtn.dataset.feedbackId, editBtn.dataset.content);
        return;
      }

      const cancelBtn = e.target?.closest?.(".feedback-edit-cancel-btn");
      if (cancelBtn) {
        cancelFeedbackEdit(cancelBtn.closest(".collect-feedback-item"));
        return;
      }

      const saveBtn = e.target?.closest?.(".feedback-edit-save-btn");
      if (saveBtn) {
        if (saveBtn.dataset.submitting === "1") return;
        const itemEl   = saveBtn.closest(".collect-feedback-item");
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

  // ============================================================
  // 피드백 모달 ↔ 대상자 검색 모달 연동
  //
  // [문제] Bootstrap 5는 모달 중첩 미지원.
  //   data-bs-toggle로 searchUserModal 오픈 시 feedbackManagerModal이
  //   자동 닫히고 hidden.bs.modal 발동 → state 초기화 → 복원 불가.
  //
  // [해결] _searchingUser 플래그:
  //   1. feedbackSearchUserBtn 클릭 → 플래그 ON + searchUserModal JS 직접 오픈
  //   2. feedbackManagerModal hidden.bs.modal → 플래그 ON이면 초기화 생략
  //   3. userSelected 이벤트 → 플래그 ON이면 대상자 state 갱신
  //   4. searchUserModal hidden.bs.modal → 플래그 OFF + feedbackManagerModal 재오픈
  // ============================================================

  let _searchingUser = false;

  // ── 피드백 대상자 검색 버튼 ──────────────────────────────
  // data-bs-toggle 방식 금지: feedbackManagerModal 자동 닫힘 + state 초기화 부작용
  const feedbackSearchBtn = document.getElementById("feedbackSearchUserBtn");
  if (feedbackSearchBtn) {
    feedbackSearchBtn.addEventListener("click", () => {
      const searchModalEl = document.getElementById("searchUserModal");
      if (!searchModalEl) return;
      _searchingUser = true;
      bootstrap.Modal.getOrCreateInstance(searchModalEl).show();
    });
  }

  // ── 피드백 모달 닫힘 → 상태 초기화 ──────────────────────
  const fbModal = document.getElementById("feedbackManagerModal");
  if (fbModal) {
    fbModal.addEventListener("hidden.bs.modal", () => {
      if (_searchingUser) return;   // 검색 중 자동 닫힘이면 초기화 생략

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

  // ── userSelected 이벤트 수신 ─────────────────────────────
  // _searchingUser 플래그 기준으로 피드백 모달 컨텍스트 여부 판단
  document.addEventListener("userSelected", e => {
    if (!_searchingUser) return;

    const selected = e.detail;
    if (!selected?.id) return;

    state.selectedEmpId   = String(selected.id);
    state.selectedEmpName = selected.name || "";
    updateTargetDisplay(state.selectedEmpId, state.selectedEmpName);
    fetchFeedbacks(state.selectedEmpId);
  });

  // ── searchUserModal 닫힘 → feedbackManagerModal 복원 ────────
  const searchModalEl = document.getElementById("searchUserModal");
  if (searchModalEl) {
    searchModalEl.addEventListener("hidden.bs.modal", () => {
      if (_searchingUser) {
        _searchingUser = false;
        getOrCreateModal("feedbackManagerModal")?.show();
      }
    });
  }

  // ── 업로드 완료 후 월도 드랍다운 + 테이블 자동 갱신 ──────
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
  renderTableHead(state.tab);
  if (state.ym) fetchCollectList();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}