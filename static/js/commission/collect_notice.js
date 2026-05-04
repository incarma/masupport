/**
 * static/js/commission/collect_notice.js
 * ──────────────────────────────────────
 * 환수내역 안내자료 제작 페이지 전용 JS (ESM, type="module")
 *
 * [라이브러리]
 *   window.XLSX : SheetJS 0.18.5 — raw xlsx 파싱 + 결과 xlsx 생성 (단일)
 *   ※ ExcelJS 제거 — unsafe-eval CSP 위반으로 이 프로젝트에서 사용 불가
 *
 * [스타일 정책]
 *   SheetJS 커뮤니티 버전은 테두리/배경색 미지원.
 *   A1 제목(bold), 3행 헤더(bold)만 적용 가능한 범위에서 구현.
 *   데이터 정확성이 스타일보다 우선.
 *
 * [서버 통신 / CSRF]
 *   없음 — 클라이언트 전용 처리
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
    // Step 4: SheetJS 파싱 + 전처리
    const allRows = await _parseAndMergeRows(rows);
    if (allRows.length === 0) {
      alert("처리할 데이터가 없습니다.\n(지급금액이 모두 0이거나 유효 데이터가 없습니다.)");
      return;
    }

    // Step 5: SheetJS xlsx 생성
    const name   = document.getElementById("targetName")  .value.trim();
    const branch = document.getElementById("targetBranch").value.trim();
    const baseYm = _titleYm();
    const [YYYY, MM] = baseYm.split("-");

    const { blob, filename } = _buildXlsx(allRows, { name, branch, YYYY, MM });
    storeResult(blob, filename, allRows.length);

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
// 8. SheetJS 파싱 및 전처리
// ─────────────────────────────────────────────────────────────────────────────

async function _parseAndMergeRows(rows) {
  const merged = [];
  for (const row of rows) {
    const file    = row.querySelector(".notice-row-file-input").files[0];
    const ym      = _rowYm(row);
    const rawRows = await _parseXlsx(file);
    merged.push(..._cleanRows(rawRows, ym));
  }
  merged.sort((a, b) => a._ym.localeCompare(b._ym));
  return merged;
}

function _parseXlsx(file) {
  return new Promise((resolve, reject) => {
    const reader  = new FileReader();
    reader.onload = (e) => {
      try {
        const wb   = window.XLSX.read(e.target.result, { type: "array" });
        const ws   = wb.Sheets[wb.SheetNames[0]];
        const data = window.XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
        resolve(data);
      } catch (err) {
        reject(new Error(`파일 파싱 실패: ${file.name} — ${err.message}`));
      }
    };
    reader.onerror = () => reject(new Error(`파일 읽기 실패: ${file.name}`));
    reader.readAsArrayBuffer(file);
  });
}

/**
 * 전처리 규칙 (가이드맵 §2-3 + §9-1 정정):
 *   1) 헤더 행(index 0) 제거
 *   2) "전체 N건" 합계 행 제거
 *   3) 지급금액(index 12) = 0 또는 빈 값 행 제거
 *
 * 열 매핑:
 *   idx  1 → 항목구분  idx  4 → 상품명     idx  5 → 증권번호(마스킹)
 *   idx  6 → 계약자(마스킹)  idx  7 → 수납구분  idx  8 → 영수일
 *   idx  9 → 회차     idx 10 → 영수보험료  idx 11 → 지급율
 *   idx 12 → 지급금액(§9-1 정정)  idx 13 → 보험계약일
 *   idx 14 → 모집자(마스킹)  idx 15 → 지급자(마스킹)
 */
function _cleanRows(rawRows, ym) {
  const result = [];
  for (let i = 0; i < rawRows.length; i++) {
    const row = rawRows[i];
    if (i === 0) continue;
    if (/^전체\s*\d+\s*건/.test(String(row[0] ?? "").trim())) continue;
    const pay = row[12];
    if (pay === "" || pay === null || pay === undefined) continue;
    if (typeof pay === "number" && pay === 0) continue;
    if (String(pay).trim() === "0") continue;

    result.push({
      _ym:      ym,
      항목구분:  _str(row[1]),
      상품명:    _str(row[4]),
      증권번호:  _maskPolicy(_str(row[5])),
      계약자:    _maskName(_str(row[6])),
      수납구분:  _str(row[7]),
      영수일:    _str(row[8]),
      회차:      _str(row[9]),
      영수보험료: _money(row[10]),
      지급율:    _rate(row[11]),
      지급금액:  _money(row[12]),
      보험계약일: _str(row[13]),
      모집자:    _maskName(_stripParenId(_str(row[14]))),
      지급자:    _maskName(_stripParenId(_str(row[15]))),
    });
  }
  return result;
}


// ─────────────────────────────────────────────────────────────────────────────
// 9. SheetJS xlsx 생성 (ExcelJS 대체)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * SheetJS로 결과 xlsx 생성.
 *
 * 구조:
 *   1행: 제목 (A1 — A1:N1 병합, bold 적용 가능 범위)
 *   2행: 빈 행
 *   3행: 헤더 (14열, bold)
 *   4행~: 데이터
 *
 * 스타일 한계 (SheetJS 커뮤니티):
 *   - bold/폰트크기 : 부분 지원 (xlsx 파일에 적용되나 Excel 렌더 보장 불가)
 *   - 테두리/배경색 : 미지원 (ExcelJS 필요, 현재 CSP 제약으로 사용 불가)
 *
 * @param {object[]} rows
 * @param {{name:string, branch:string, YYYY:string, MM:string}} meta
 * @returns {{blob: Blob, filename: string}}
 */
function _buildXlsx(rows, { name, branch, YYYY, MM }) {
  const XLSX     = window.XLSX;
  const wb       = XLSX.utils.book_new();

  // ── 헤더 정의 ────────────────────────────────────────────────────────────
  const HEADERS = [
    "월도", "항목구분", "상품명", "증권번호", "계약자",
    "수납구분", "영수일", "회차", "영수보험료", "지급율(환수율)",
    "지급금액(환수금액)", "보험계약일", "모집자", "지급자",
  ];

  // ── 워크시트 데이터 조립 ──────────────────────────────────────────────────
  // 1행: 제목
  const titleText = `${branch} ${name} ${YYYY}년 ${_pad2(MM)}월 기준 환수내역`;

  // 3행: 헤더
  // 4행~: 데이터
  const dataRows = rows.map((d) => [
    d._ym,        // A: 월도
    d.항목구분,    // B
    d.상품명,      // C
    d.증권번호,    // D
    d.계약자,      // E
    d.수납구분,    // F
    d.영수일,      // G
    d.회차,        // H
    d.영수보험료,  // I
    d.지급율,      // J
    d.지급금액,    // K
    d.보험계약일,  // L
    d.모집자,      // M
    d.지급자,      // N
  ]);

  // aoa_to_sheet: 2D 배열 → 워크시트
  const aoaData = [
    [titleText, "", "", "", "", "", "", "", "", "", "", "", "", ""], // 1행: 제목
    [],                                                              // 2행: 빈 행
    HEADERS,                                                         // 3행: 헤더
    ...dataRows,                                                     // 4행~: 데이터
  ];

  const ws = XLSX.utils.aoa_to_sheet(aoaData);

  // ── 컬럼 폭 설정 ──────────────────────────────────────────────────────────
  ws["!cols"] = [
    { wch: 10 },  // A 월도
    { wch: 12 },  // B 항목구분
    { wch: 50 },  // C 상품명
    { wch: 18 },  // D 증권번호
    { wch: 10 },  // E 계약자
    { wch: 10 },  // F 수납구분
    { wch: 13 },  // G 영수일
    { wch:  7 },  // H 회차
    { wch: 14 },  // I 영수보험료
    { wch: 12 },  // J 지급율
    { wch: 15 },  // K 지급금액
    { wch: 13 },  // L 보험계약일
    { wch: 10 },  // M 모집자
    { wch: 10 },  // N 지급자
  ];

  // ── A1:N1 병합 (제목 행) ──────────────────────────────────────────────────
  ws["!merges"] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 13 } }];

  // ── A1 제목 셀 스타일 (bold, 16pt) ───────────────────────────────────────
  // SheetJS 커뮤니티 버전에서 스타일 객체를 직접 주입하는 방식
  // (xlsx 파일 내 XML에 반영되나 Excel의 렌더링 보장은 PRO 버전 기준)
  if (ws["A1"]) {
    ws["A1"].s = {
      font: { bold: true, sz: 16, name: "맑은 고딕" },
      alignment: { horizontal: "left", vertical: "center" },
    };
  }

  // ── 3행 헤더 셀 스타일 (bold) ─────────────────────────────────────────────
  const colLetters = "ABCDEFGHIJKLMN".split("");
  colLetters.forEach((col) => {
    const cellAddr = `${col}3`;
    if (ws[cellAddr]) {
      ws[cellAddr].s = {
        font: { bold: true, sz: 10, name: "맑은 고딕" },
        alignment: { horizontal: "center", vertical: "center" },
      };
    }
  });

  // ── 행 높이 설정 ──────────────────────────────────────────────────────────
  ws["!rows"] = [
    { hpt: 22 }, // 1행: 제목
    { hpt: 6  }, // 2행: 빈 행
    { hpt: 18 }, // 3행: 헤더
  ];

  // ── 워크북에 시트 추가 + Blob 생성 ───────────────────────────────────────
  XLSX.utils.book_append_sheet(wb, ws, "환수내역");

  const wbOut   = XLSX.write(wb, { bookType: "xlsx", type: "array" });
  const blob    = new Blob([wbOut], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const filename = `환수내역_${name}_${YYYY}년${_pad2(MM)}월.xlsx`;

  return { blob, filename };
}


// ─────────────────────────────────────────────────────────────────────────────
// 10. 데이터 정규화 / 마스킹
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