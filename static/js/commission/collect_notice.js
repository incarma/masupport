import { getCSRFToken } from "../common/manage/csrf.js";
import { showLoading, hideLoading } from "../common/manage/loading.js";

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

function _setSubmitting(btn, isSubmitting) {
  if (!btn) return;
  btn.dataset.submitting = isSubmitting ? "1" : "0";
  btn.disabled = Boolean(isSubmitting);
}

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
    } else if (btn.id === "btnAddManualRow") {
      _addManualRow();
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
    } else if (btn.classList.contains("manual-row-delete")) {
      const row = btn.closest(".manual-input-row");
      if (row) {
        row.remove();
        _syncManualEmptyState();
        _resetDownload();
      }
    }
  });

  // 수기 입력 숫자/율 포맷은 입력 중 즉시 정규화한다.
  root.addEventListener("input", _onManualInput);
  root.addEventListener("change", _onManualChange);
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
// 5. 수기 입력 행 추가 / 검증 / 포맷
// ─────────────────────────────────────────────────────────────────────────────

function _addManualRow() {
  const tpl = document.getElementById("manualInputRowTemplate");
  const tbody = document.getElementById("manualInputTbody");
  if (!tpl || !tbody) return;

  const fragment = tpl.content.cloneNode(true);
  const row = fragment.querySelector(".manual-input-row");
  const ymInput = row.querySelector(".manual-ym");

  // 기본 월도는 제목 카드의 기준 연월과 동일하게 세팅
  if (ymInput) ymInput.value = _titleYm();

  tbody.appendChild(fragment);
  _syncManualEmptyState();
  _resetDownload();
}

function _syncManualEmptyState() {
  const empty = document.getElementById("manualInputEmpty");
  if (!empty) return;
  empty.hidden = _getManualRows().length > 0;
}

function _getManualRows() {
  return Array.from(document.querySelectorAll("#manualInputTbody .manual-input-row"));
}

function _digitsOnly(value) {
  return String(value || "").replace(/[^\d]/g, "");
}

/**
 * 음수 허용 숫자 정규화
 * - 맨 앞 "-" 1개만 허용
 * - 나머지 문자는 제거
 */
function _signedDigits(value) {
  const raw = String(value || "").trim();
  const negative = raw.startsWith("-");
  const digits = raw.replace(/[^\d]/g, "");

  if (!digits) {
    return negative ? "-" : "";
  }

  return negative ? `-${digits}` : digits;
}

function _commaDigits(value) {
  const digits = _digitsOnly(value);
  if (!digits) return "";
  return Number(digits).toLocaleString("ko-KR");
}

/**
 * 음수 허용 콤마 포맷
 * 예:
 * -1000 -> -1,000
 * 2500  -> 2,500
 */
function _commaSignedDigits(value) {
  const normalized = _signedDigits(value);

  if (!normalized || normalized === "-") {
    return normalized;
  }

  const negative = normalized.startsWith("-");
  const num = Number(normalized);

  if (!Number.isFinite(num)) {
    return "";
  }

  const formatted = Math.abs(num).toLocaleString("ko-KR");
  return negative ? `-${formatted}` : formatted;
}

function _normalizeRateInput(value) {
  const raw = String(value || "").replace(/[^\d.]/g, "");
  if (!raw) return "";

  let n = Number(raw);
  if (!Number.isFinite(n)) return "";
  if (n < 0) n = 0;
  if (n > 100) n = 100;

  // 10.5 같은 입력은 허용하되 불필요한 0은 제거
  const text = Number.isInteger(n) ? String(n) : String(n).replace(/0+$/, "").replace(/\.$/, "");
  return `${text}%`;
}

function _onManualInput(e) {
  const el = e.target;
  if (!el) return;

  if (el.classList.contains("manual-money-like")) {
    /**
     * 지급금액(환수금액) 컬럼만 음수 허용
     * 나머지 숫자 컬럼은 기존 정책 유지
     */
    if (el.classList.contains("manual-amount")) {
      el.value = _commaSignedDigits(el.value);
    } else {
      el.value = _commaDigits(el.value);
    }

    _resetDownload();
    return;
  }

  if (el.classList.contains("manual-rate-like")) {
    const cursorAtEnd = el.selectionStart === el.value.length;
    el.value = _normalizeRateInput(el.value);
    if (cursorAtEnd) el.selectionStart = el.selectionEnd = el.value.length;
    _resetDownload();
  }
}

function _onManualChange(e) {
  const el = e.target;
  if (!el) return;

  if (el.closest(".manual-input-row")) {
    _resetDownload();
  }
}

function _readManualValue(row, selector) {
  return String(row.querySelector(selector)?.value || "").trim();
}

function _collectManualRowsOrThrow() {
  const rows = _getManualRows();
  const out = [];

  for (const row of rows) {
    const item = {
      ym: _readManualValue(row, ".manual-ym"),
      item_type: _readManualValue(row, ".manual-item-type"),
      pay_refund: _readManualValue(row, ".manual-pay-refund"),
      product_name: _readManualValue(row, ".manual-product-name"),
      policy_no: _readManualValue(row, ".manual-policy-no"),
      contractor: _readManualValue(row, ".manual-contractor"),
      payment_type: _readManualValue(row, ".manual-payment-type"),
      receipt_date: _readManualValue(row, ".manual-receipt-date"),
      round_no: _readManualValue(row, ".manual-round-no"),
      premium: _readManualValue(row, ".manual-premium"),
      rate: _readManualValue(row, ".manual-rate"),
      amount: _readManualValue(row, ".manual-amount"),
      contract_date: _readManualValue(row, ".manual-contract-date"),
      recruiter: _readManualValue(row, ".manual-recruiter"),
      payer: _readManualValue(row, ".manual-payer"),
    };

    if (!item.ym || !item.pay_refund || !item.product_name || !item.amount) {
      throw new Error("수기 입력은 월도, 지급/환수, 상품명, 지급금액을 모두 입력해야 합니다.");
    }

    out.push(item);
  }

  return out;
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
  const btn = document.getElementById("btnMakeNotice");
  if (btn?.dataset.submitting === "1") return;

  // 유효성 검사
  const empId = document.getElementById("targetEmpId").value.trim();
  if (!empId) { alert("대상자를 먼저 선택해주세요."); return; }

  const rows = _getRows();
  const manualRows = _getManualRows();
  if (rows.length === 0 && manualRows.length === 0) {
    alert("내역 파일 또는 수기 입력 행을 1개 이상 추가해주세요.");
    return;
  }

  for (const row of rows) {
    const fi = row.querySelector(".notice-row-file-input");
    if (!fi.files || !fi.files[0]) {
      alert(`${_rowYm(row)} 행의 파일을 선택해주세요.`); return;
    }
  }

  _setSubmitting(btn, true);
  showLoading("안내자료 제작 중...");

  try {
    // Step 4: 서버 openpyxl 생성 요청
    const manualPayload = _collectManualRowsOrThrow();
    const fd = _buildExportFormData(rows, manualPayload);
    fd.set("output", "xlsx");
    const { blob, filename, rowCount } = await _postNoticeExport(fd, { output: "xlsx" });
    storeResult(blob, filename, rowCount);
  } catch (err) {
    console.error("[collect_notice] 제작 오류:", err);
    alert(`안내자료 제작 중 오류가 발생했습니다.\n${err.message || err}`);
  } finally {
    hideLoading();
    _setSubmitting(btn, false);
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


function _buildExportFormData(rows, manualPayload = []) {
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
  fd.set("no_mask", document.getElementById("chkNoMask")?.checked ? "1" : "0");

  rows.forEach((row) => {
    const file = row.querySelector(".notice-row-file-input")?.files?.[0];
    if (!file) return;
    fd.append("file_yms", _rowYm(row));
    fd.append("notice_files", file, file.name);
  });

  // 수기 입력 데이터는 JSON 문자열로 서버에 전달한다.
  fd.set("manual_rows", JSON.stringify(manualPayload));

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

function _normalizeDownloadFilename(filename, ext) {
  const safeExt = String(ext || "").replace(/^\./, "");
  if (!safeExt) return filename || "환수내역";

  const fallback = `환수내역.${safeExt}`;
  const name = String(filename || fallback).trim() || fallback;
  return name.replace(/\.(xlsx|xls|pdf)$/i, `.${safeExt}`);
}

async function _assertBlobSignature(blob, output) {
  if (output !== "pdf") return;

  const head = await blob.slice(0, 4).text().catch(() => "");
  if (head !== "%PDF") {
    throw new Error(
      "서버 응답이 PDF 형식이 아닙니다. PDF 변환 설정 또는 output 파라미터를 확인해주세요."
    );
  }
}

async function _postNoticeExport(
  formData,
  { fallbackFilename = "환수내역.xlsx", output = "xlsx" } = {}
) {
  if (!EXPORT_URL) {
    throw new Error("서버 생성 URL이 설정되지 않았습니다.");
  }

  const res = await fetch(EXPORT_URL, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCSRFToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await _readErrorMessage(res));
  }

  const ct = (res.headers.get("Content-Type") || "").toLowerCase();
  if (output === "pdf" && !ct.includes("application/pdf")) {
    throw new Error(
      `PDF 응답 형식이 올바르지 않습니다. 현재 Content-Type: ${ct || "없음"}`
    );
  }
  if (output === "xlsx" && !ct.includes("spreadsheet") && !ct.includes("excel")) {
    throw new Error(
      `엑셀 응답 형식이 올바르지 않습니다. 현재 Content-Type: ${ct || "없음"}`
    );
  }

  const blob = await res.blob();
  await _assertBlobSignature(blob, output);

  const ext = output === "pdf" ? "pdf" : "xlsx";
  const filename =
    _normalizeDownloadFilename(
      _filenameFromContentDisposition(res.headers.get("Content-Disposition")) ||
        fallbackFilename,
      ext
    );
  const rowCount = Number(res.headers.get("X-Collect-Notice-Row-Count") || "0");

  return { blob, filename, rowCount };
}


// ─────────────────────────────────────────────────────────────────────────────
// PDF 다운로드
// - 서버에서 동일한 원본 파일로 xlsx 생성 후 PDF 변환
// - A4 가로 / 모든 열 1페이지 맞춤 설정은 서버 openpyxl 인쇄설정에서 처리
// ─────────────────────────────────────────────────────────────────────────────
async function _onDownloadPdf() {
  const btn = document.getElementById("btnDownloadPdfResult");
  if (btn?.dataset.submitting === "1") return;

  const empId = document.getElementById("targetEmpId").value.trim();
  if (!empId) {
    alert("대상자를 먼저 선택해주세요.");
    return;
  }

  const rows = _getRows();
  const manualRows = _getManualRows();
  if (rows.length === 0 && manualRows.length === 0) {
    alert("내역 파일 또는 수기 입력 행을 1개 이상 추가해주세요.");
    return;
  }

  for (const row of rows) {
    const fi = row.querySelector(".notice-row-file-input");
    if (!fi.files || !fi.files[0]) {
      alert(`${_rowYm(row)} 행의 파일을 선택해주세요.`);
      return;
    }
  }

  _setSubmitting(btn, true);
  showLoading("PDF 변환 중...");

  try {
    const manualPayload = _collectManualRowsOrThrow();
    const fd = _buildExportFormData(rows, manualPayload);
    fd.set("output", "pdf");

    const { blob, filename } = await _postNoticeExport(fd, {
      fallbackFilename: "환수내역.pdf",
      output: "pdf",
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    console.error("[collect_notice] PDF 다운로드 오류:", err);
    alert(`PDF 다운로드 중 오류가 발생했습니다.\n${err.message || err}`);
  } finally {
    hideLoading();
    _setSubmitting(btn, false);
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