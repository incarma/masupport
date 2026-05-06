/**
 * static/js/commission/collect_notice.js
 * ──────────────────────────────────────
 * 환수내역 안내자료 제작 페이지 전용 JS (ESM, type="module")
 *
 * [서버 생성 정책]
 *   - 원본 엑셀 파일은 FormData로 서버 전송
 *   - 서버에서 openpyxl로 파싱/마스킹/서식 적용/xlsx 생성
 *   - 클라이언트는 결과 blob을 다운로드 카드에 연결
 *
 * [보안/통신]
 *   - same-origin credentials
 *   - X-CSRFToken
 *   - X-Requested-With
 */

// ─────────────────────────────────────────────────────────────────────────────
// 0. Boot 가드
// ─────────────────────────────────────────────────────────────────────────────

const root = document.getElementById("collect-notice");
if (!root) throw new Error("[collect_notice] 루트 요소(#collect-notice) 없음");

function _boot() {
  if (root.dataset.inited === "1") return;
  root.dataset.inited = "1";
  _init();
}

window.addEventListener("pageshow", (e) => {
  if (e.persisted) { root.dataset.inited = ""; _boot(); }
});


// ─────────────────────────────────────────────────────────────────────────────
// 1. 상수 및 상태
// ─────────────────────────────────────────────────────────────────────────────

const YEAR_RANGE   = 3;
const CURRENT_YEAR = parseInt(root.dataset.currentYear, 10) || new Date().getFullYear();
const EXPORT_URL   = root.dataset.exportUrl || "";

let _rowCounter = 0;
let _blobUrl    = null;
let _blobName   = "";

// 상수/상태 선언 이후 초기화해야 CURRENT_YEAR TDZ 오류가 발생하지 않는다.
_boot();


// ─────────────────────────────────────────────────────────────────────────────
// 2. 초기화
// ─────────────────────────────────────────────────────────────────────────────

function _init() {
  _initTitleYmSelects();
  document.addEventListener("userSelected", _onUserSelected);
  
  root.addEventListener("click", (e) => {
    const btn = e.target?.closest?.("button");
    if (!btn) return;

    if (btn.id === "btnAddRow") {
      _addRow();
    } else if (btn.id === "btnMakeNotice") {
      _onMakeNotice();
    } else if (btn.id === "btnDownloadResult") {
      _onDownload();
      } else if (btn.id === "btnDownloadPdfResult") {
      _onDownloadPdf();
    } else if (btn.id === "btnResetDownload") {
      _resetDownload();
    } else if (btn.classList.contains("notice-row-delete")) {
      const row = btn.closest(".notice-row");
      if (row) {
        row.remove();
        _syncEmptyState();
        _resetDownload();
      }
    }
  });
}

function _initTitleYmSelects() {
  const yearSel = document.getElementById("noticeTitleYear");
  const monthSel = document.getElementById("noticeTitleMonth");
  if (!yearSel || !monthSel) return;

  yearSel.innerHTML = "";
  for (let y = CURRENT_YEAR + 1; y >= CURRENT_YEAR - YEAR_RANGE; y--) {
    const opt = document.createElement("option");
    opt.value = y;
    opt.textContent = `${y}년`;
    if (y === CURRENT_YEAR) opt.selected = true;
    yearSel.appendChild(opt);
  }

  monthSel.innerHTML = "";
  const defaultMonth = new Date().getMonth() + 1;
  for (let m = 1; m <= 12; m++) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = `${m}월`;
    if (m === defaultMonth) opt.selected = true;
    monthSel.appendChild(opt);
  }

  yearSel.addEventListener("change", _resetDownload);
  monthSel.addEventListener("change", _resetDownload);
}


// ─────────────────────────────────────────────────────────────────────────────
// 3. 대상자 카드
// ─────────────────────────────────────────────────────────────────────────────

function _onUserSelected(e) {
  const { id, name, branch, affiliation_display, affiliationDisplay } = e.detail || {};
  const aff = affiliation_display || affiliationDisplay || branch || "";

  document.getElementById("targetEmpId") .value = id   || "";
  document.getElementById("targetName")  .value = name || "";
  document.getElementById("targetBranch").value = aff;

  const displayEl     = document.getElementById("targetDisplay");
  displayEl.textContent = aff ? `${name} (${aff})` : name;
  displayEl.classList.remove("text-muted");
  displayEl.classList.add("fw-semibold");

  _resetDownload();
}


// ─────────────────────────────────────────────────────────────────────────────
// 4. 행 추가 / 삭제
// ─────────────────────────────────────────────────────────────────────────────

function _addRow() {
  const row   = document.getElementById("noticeRowTemplate").cloneNode(true);
  const rowId = ++_rowCounter;
  row.id            = `noticeRow_${rowId}`;
  row.dataset.rowId = rowId;
  row.hidden        = false;

  // 연도 셀렉트
  const yearSel     = row.querySelector(".notice-row-year-select");
  yearSel.innerHTML = "";
  for (let y = CURRENT_YEAR + 1; y >= CURRENT_YEAR - YEAR_RANGE; y--) {
    const opt = document.createElement("option");
    opt.value = y; opt.textContent = `${y}년`;
    if (y === CURRENT_YEAR) opt.selected = true;
    yearSel.appendChild(opt);
  }

  // 월 셀렉트
  const monthSel     = row.querySelector(".notice-row-month-select");
  monthSel.innerHTML = "";
  const defaultMonth = new Date().getMonth() + 1;
  for (let m = 1; m <= 12; m++) {
    const opt = document.createElement("option");
    opt.value = m; opt.textContent = `${m}월`;
    if (m === defaultMonth) opt.selected = true;
    monthSel.appendChild(opt);
  }

  // 파일 input
  const fileInput  = row.querySelector(".notice-row-file-input");
  const fileNameEl = row.querySelector(".notice-row-filename");
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    fileNameEl.textContent = file ? file.name : "파일 미선택";
    fileNameEl.classList.toggle("text-muted", !file);
    _resetDownload();
  });

  document.getElementById("noticeRowList").appendChild(row);
  _syncEmptyState();
}

function _syncEmptyState() {
  document.getElementById("noticeRowEmpty").hidden = _getRows().length > 0;
}

function _getRows() {
  return Array.from(
    document.querySelectorAll("#noticeRowList .notice-row:not([hidden])")
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// 5. 다운로드 카드
// ─────────────────────────────────────────────────────────────────────────────

function storeResult(blob, filename, rowCount) {
  if (_blobUrl) URL.revokeObjectURL(_blobUrl);
  _blobUrl  = URL.createObjectURL(blob);
  _blobName = filename;

  document.getElementById("noticeDownloadInfo").textContent =
    `총 ${rowCount}건 처리 완료 · 파일명: ${filename}`;

  const card  = document.getElementById("noticeDownloadCard");
  card.hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function _resetDownload() {
  if (_blobUrl) { URL.revokeObjectURL(_blobUrl); _blobUrl = null; _blobName = ""; }
  document.getElementById("noticeDownloadCard").hidden = true;
  document.getElementById("noticeDownloadInfo").textContent = "";
}

function _onDownload() {
  if (!_blobUrl) { alert("먼저 안내자료를 제작해주세요."); return; }
  const a = document.createElement("a");
  a.href = _blobUrl; a.download = _blobName; a.click();
}


// ─────────────────────────────────────────────────────────────────────────────
// 6. 안내자료 제작 진입점
// ─────────────────────────────────────────────────────────────────────────────

async function _onMakeNotice() {
  // 유효성 검사
  const empId = document.getElementById("targetEmpId").value.trim();
  if (!empId) { alert("대상자를 먼저 선택해주세요."); return; }

  const rows = _getRows();
  if (rows.length === 0) { alert("내역 파일 행을 1개 이상 추가해주세요."); return; }

  for (const row of rows) {
    const fi = row.querySelector(".notice-row-file-input");
    if (!fi.files || !fi.files[0]) {
      alert(`${_rowYm(row)} 행의 파일을 선택해주세요.`); return;
    }
  }

  const overlay  = document.getElementById("loadingOverlay");
  overlay.hidden = false;

  try {
    // Step 4: 서버 openpyxl 생성 요청
    const fd = _buildExportFormData(rows);
    const { blob, filename, rowCount } = await _postNoticeExport(fd);
    storeResult(blob, filename, rowCount);
  } catch (err) {
    console.error("[collect_notice] 제작 오류:", err);
    alert(`안내자료 제작 중 오류가 발생했습니다.\n${err.message || err}`);
  } finally {
    overlay.hidden = true;
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 7. 유틸
// ─────────────────────────────────────────────────────────────────────────────

function _rowYm(row) {
  const y = row.querySelector(".notice-row-year-select").value;
  const m = String(row.querySelector(".notice-row-month-select").value).padStart(2, "0");
  return `${y}-${m}`;
}

function _pad2(n) { return String(n).padStart(2, "0"); }

function _titleYm() {
  const y = document.getElementById("noticeTitleYear")?.value || CURRENT_YEAR;
  const m = document.getElementById("noticeTitleMonth")?.value || (new Date().getMonth() + 1);
  return `${y}-${_pad2(m)}`;
}

function _toNumber(v) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const n = Number(String(v).replaceAll(",", "").replace("%", "").trim());
  return Number.isFinite(n) ? n : null;
}

function _money(v) {
  const n = _toNumber(v);
  if (n === null) return _str(v);
  return n.toLocaleString("ko-KR");
}

function _rate(v) {
  const s = _str(v);
  if (!s) return "";
  if (s.includes("%")) return s;
  return `${s}%`;
}


// ─────────────────────────────────────────────────────────────────────────────
// 8. 서버 openpyxl 생성 요청
// ─────────────────────────────────────────────────────────────────────────────

function _getCSRFToken() {
  return (
    window.csrfToken ||
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    ""
 );
}

function _buildExportFormData(rows) {
  const name   = document.getElementById("targetName")?.value.trim() || "";
  const branch = document.getElementById("targetBranch")?.value.trim() || "";
  const empId  = document.getElementById("targetEmpId")?.value.trim() || "";
  const baseYm = _titleYm();
  const [YYYY, MM] = baseYm.split("-");

  const fd = new FormData();
  fd.set("target_emp_id", empId);
  fd.set("target_name", name);
  fd.set("target_branch", branch);
  fd.set("title_year", YYYY);
  fd.set("title_month", MM);
  fd.set("csrfmiddlewaretoken", _getCSRFToken());

  rows.forEach((row) => {
    const file = row.querySelector(".notice-row-file-input")?.files?.[0];
    if (!file) return;
    fd.append("file_yms", _rowYm(row));
    fd.append("notice_files", file, file.name);
  });

  return fd;
}

function _filenameFromContentDisposition(headerValue) {
  const h = String(headerValue || "");
 const star = h.match(/filename\*=UTF-8''([^;]+)/i);
  if (star?.[1]) {
    try { return decodeURIComponent(star[1]); } catch { return star[1]; }
  }
  const plain = h.match(/filename="([^"]+)"/i);
  return plain?.[1] || "";
}

async function _readErrorMessage(res) {
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) {
    const data = await res.json().catch(() => null);
    return data?.message || `요청 실패 (${res.status})`;
  }
  const text = await res.text().catch(() => "");
  return text || `요청 실패 (${res.status})`;
}

async function _postNoticeExport(formData) {
  if (!EXPORT_URL) {
    throw new Error("서버 생성 URL이 설정되지 않았습니다.");
  }

  const res = await fetch(EXPORT_URL, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": _getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await _readErrorMessage(res));
  }

  const blob = await res.blob();
  const filename =
    _filenameFromContentDisposition(res.headers.get("Content-Disposition")) ||
    "환수내역.xlsx";
  const rowCount = Number(res.headers.get("X-Collect-Notice-Row-Count") || "0");

  return { blob, filename, rowCount };
}


// ─────────────────────────────────────────────────────────────────────────────
// PDF 다운로드
// - 서버에서 동일한 원본 파일로 xlsx 생성 후 PDF 변환
// - A4 가로 / 모든 열 1페이지 맞춤 설정은 서버 openpyxl 인쇄설정에서 처리
// ─────────────────────────────────────────────────────────────────────────────
async function _onDownloadPdf() {
  const empId = document.getElementById("targetEmpId").value.trim();
  if (!empId) {
    alert("대상자를 먼저 선택해주세요.");
    return;
  }

  const rows = _getRows();
  if (rows.length === 0) {
    alert("내역 파일 행을 1개 이상 추가해주세요.");
    return;
  }

  for (const row of rows) {
    const fi = row.querySelector(".notice-row-file-input");
    if (!fi.files || !fi.files[0]) {
      alert(`${_rowYm(row)} 행의 파일을 선택해주세요.`);
      return;
    }
  }

  const overlay = document.getElementById("loadingOverlay");
  overlay.hidden = false;

  try {
    const fd = _buildExportFormData(rows);
    fd.set("output", "pdf");

    const { blob, filename } = await _postNoticeExport(fd);

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "환수내역.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    console.error("[collect_notice] PDF 다운로드 오류:", err);
    alert(`PDF 다운로드 중 오류가 발생했습니다.\n${err.message || err}`);
  } finally {
    overlay.hidden = true;
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 9. 데이터 정규화 / 마스킹
// ─────────────────────────────────────────────────────────────────────────────

function _str(v) {
  if (v === null || v === undefined) return "";
  return String(v).trim();
}

/** "홍길동(2433672)" → "홍길동" */
function _stripParenId(v) {
  return v.replace(/\([^)]*\)/g, "").trim();
}

/** 이름 마스킹: "홍길동" → "홍*동", "홍길" → "홍*" */
function _maskName(name) {
  if (!name) return "";
  if (name.length === 1) return "*";
  if (name.length === 2) return name[0] + "*";
  return name[0] + "*".repeat(name.length - 2) + name[name.length - 1];
}

/** 증권번호 마스킹: 마지막 4글자만 노출 */
function _maskPolicy(policy) {
  if (!policy) return "";
  if (policy.length <= 4) return "*".repeat(policy.length);
  return "*".repeat(policy.length - 4) + policy.slice(-4);
}