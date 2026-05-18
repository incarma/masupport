// django_ma/static/js/partner/manage_efficiency/fetch.js
// =========================================================
// ✅ Efficiency fetch + render (Accordion groups + rows) FINAL
// - grouped=1 응답(groups + rows 플랫) 지원
// - group_key(문자열) / group_pk(숫자) 모두 매칭
// - leader: 그룹삭제 버튼 숨김 + 행삭제 disabled (UI 레벨)
// - superuser/head: 각 행 처리일자(date) 수정 가능(즉시 저장)
// - ❗삭제 로직은 delete.js로 완전 분리(중복/충돌 방지)
// =========================================================

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, getCSRFToken } from "./utils.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";
import { getDatasetValue } from "../../common/manage/dataset.js";
import {
  toStr,
  escapeHtml as commonEscapeHtml,
  escapeAttr as commonEscapeAttr,
  formatCommaNumber,
} from "../../common/manage/text.js";

const DEBUG = false;
const log = (...a) => DEBUG && console.log("[efficiency/fetch]", ...a);

/* -------------------------
   Small helpers
-------------------------- */
function str(v) {
  return toStr(v);
}
function numOrNull(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function fmtNumber(n) {
  return formatCommaNumber(n, "0");
}
function escapeHtml(s) {
  return commonEscapeHtml(s);
}
function escapeAttr(s) {
  return commonEscapeAttr(s);
}

/* -------------------------
   Requester display
   - "요청자성명(요청자사번)" 형태로 통합 출력
-------------------------- */
function formatRequesterDisplay(r) {
  const name = str(r?.requester_name ?? r?.requester ?? "");
  const empId = str(r?.requester_id ?? r?.rq_id ?? r?.requester_empno ?? "");
  if (name && empId) return `${name}(${empId})`;
  return name || empId || "-";
}

/* -------------------------
   Root / grade / dataset
-------------------------- */
function getRoot() {
  return (
    els.root ||
    document.getElementById("manage-efficiency") ||
    document.getElementById("manage-calculate") ||
    null
  );
}
function getUserGrade() {
  const root = getRoot();
  return str(root?.dataset?.userGrade) || str(window?.currentUser?.grade);
}
function canAdminEdit() {
  const g = getUserGrade();
  return g === "superuser" || g === "head";
}
function isSubAdmin() {
  return getUserGrade() === "leader";
}

/**
 * dataset key들은 여러 후보를 OR로 흡수
 */
function dsPick(root, keys) {
  // ✅ dataset key 후보 탐색 공통화
  return getDatasetValue(root, keys, "");
}

function getFetchUrl() {
  const root = getRoot();
  return dsPick(root, ["fetchUrl", "dataFetchUrl", "dataFetch", "dataDataFetchUrl"]);
}
function getUpdateProcessDateUrl() {
  const root = getRoot();
  return (
    dsPick(root, ["updateProcessDateUrl", "dataUpdateProcessDateUrl", "updateProcessDate", "dataUpdateProcessDate"]) ||
    str(window?.ManageefficiencyBoot?.updateProcessDateUrl)
  );
}

function getGroupsContainer() {
  return els.accordion || document.getElementById("confirmGroupsAccordion");
}

/* -------------------------
   MAIN table colgroup widths
-------------------------- */
const MAIN_COL_KEYS = [
  "requester",
  "category",
  "amount",
  "tax",
  "ded",
  "pay",
  "content",
  "request_date",
  "process_date",
  "remove",
];

const DEFAULT_MAIN_COL_WIDTHS = {
  requester: 8,
  category: 8,
  amount: 8,
  tax: 6,
  ded: 10,
  pay: 10,
  content: 20,
  request_date: 7,
  process_date: 8,
  remove: 8,
};

function buildMainColGroup() {
  return `
    <colgroup>
      ${MAIN_COL_KEYS.map((k) => `<col data-col="${k}">`).join("")}
    </colgroup>
  `;
}

function applyMainColWidths(root, table) {
  if (!root || !table) return;

  let conf;
  try {
    conf = JSON.parse(root.dataset.mainColWidths || "{}");
    conf = { ...DEFAULT_MAIN_COL_WIDTHS, ...conf };
  } catch {
    conf = { ...DEFAULT_MAIN_COL_WIDTHS };
  }

  const entries = Object.entries(conf).filter(([, v]) => Number(v) > 0);
  const sum = entries.reduce((a, [, v]) => a + Number(v), 0);
  if (!sum) return;

  const ratios = {};
  for (const [k, v] of entries) ratios[k] = (Number(v) / sum) * 100;

  table.querySelectorAll("colgroup col[data-col]").forEach((col) => {
    const key = col.dataset.col;
    if (ratios[key]) col.style.width = `${ratios[key]}%`;
  });

  table.style.tableLayout = "fixed";
}

/* -------------------------
   Normalize group/title/rows
-------------------------- */
function normalizeGroupTitle(rawTitle, fallbackMonth, fallbackBranch) {
  const title = str(rawTitle);

  // ".... - ...." 형식이면 마지막 토큰만 사용
  if (title && title.includes(" - ")) {
    const parts = title
      .split(" - ")
      .map((x) => x.trim())
      .filter(Boolean);
    if (parts.length) return parts[parts.length - 1];
  }

  if (title) return title;

  const month = str(fallbackMonth);
  const branch = str(fallbackBranch);
  if (month && branch) return `${month} / ${branch}`;
  if (month) return month;
  if (branch) return branch;
  return "그룹";
}

function normalizeAttachment(a) {
  if (!a || typeof a !== "object") return {};
  return {
    id: a.id ?? a.pk ?? null,
    file: a.file ?? a.url ?? a.file_url ?? "",
    file_name: a.file_name ?? a.original_name ?? a.name ?? "",
  };
}

function pickRowGroupKeys(r) {
  const keys = [];

  const sCandidates = [
    r?.group_key,
    r?.confirm_group_id,
    r?.confirm_group_key,
    r?.confirm_group__confirm_group_id,
  ];
  for (const c of sCandidates) {
    const v = str(c);
    if (v) keys.push(v);
  }

  const pkCandidates = [r?.group_pk, r?.confirm_group_pk, r?.confirm_group, r?.group_id, r?.group];
  for (const c of pkCandidates) {
    const n = numOrNull(c);
    if (n !== null) keys.push(String(n));
  }

  return Array.from(new Set(keys));
}

function normalizeRow(r) {
  if (!r || typeof r !== "object") return {};
  return {
    id: r.id ?? r.pk ?? null,
    group_keys: pickRowGroupKeys(r),
    requester_name: r.requester_name ?? r.requester ?? "",
    requester_id: r.requester_id ?? r.rq_id ?? r.requester_empno ?? "",
    category: r.category ?? "",
    amount: r.amount ?? 0,
    tax: r.tax ?? r.tax_amount ?? r.withholding_tax ?? null,
    ded_name: r.ded_name ?? "",
    ded_id: r.ded_id ?? "",
    pay_name: r.pay_name ?? "",
    pay_id: r.pay_id ?? "",
    content: r.content ?? "",
    request_date: r.request_date ?? r.created_at ?? "",
    process_date: r.process_date ?? "",
  };
}

function normalizeGroup(g) {
  if (!g || typeof g !== "object") return {};
  const attachments = Array.isArray(g.attachments) ? g.attachments.map(normalizeAttachment) : [];

  const groupKey = str(g.group_key || g.confirm_group_id || g.confirm_group_key || "");
  const groupPk = numOrNull(g.group_pk ?? g.id);

  return {
    group_key: groupKey,
    group_pk: groupPk,
    title: g.title ?? "",
    month: g.month ?? "",
    branch: g.branch ?? "",
    row_count: g.row_count ?? 0,
    total_amount: g.total_amount ?? 0,
    attachments,
  };
}

function buildRowsByGroup(rows) {
  const map = Object.create(null);
  const list = Array.isArray(rows) ? rows.map(normalizeRow) : [];

  for (const r of list) {
    const keys = Array.isArray(r.group_keys) ? r.group_keys : [];
    if (!keys.length) continue;

    for (const key of keys) {
      const k = str(key);
      if (!k) continue;
      if (!map[k]) map[k] = [];
      map[k].push(r);
    }
  }
  return map;
}

function sumAmount(list) {
  let s = 0;
  for (const r of list || []) {
    const n = Number(r?.amount || 0);
    if (Number.isFinite(n)) s += n;
  }
  return s;
}

function pickPrimaryAttachment(group) {
  const atts = Array.isArray(group?.attachments) ? group.attachments : [];
  if (!atts.length) return { fileName: "", fileUrl: "", rawName: "", extraCount: 0 };

  const first = atts[0] || {};
  const rawName = str(first.file_name) || "확인서";
  const fileUrl = str(first.file);
  const extraCount = Math.max(0, atts.length - 1);

  const fileName = extraCount > 0 ? `${rawName} 외 ${extraCount}건` : rawName;
  return { fileName, fileUrl, rawName, extraCount };
}

/* -------------------------
   Process date cell
-------------------------- */
function renderProcessDateCell(r) {
  const val = str(r.process_date);
  if (!canAdminEdit()) return escapeHtml(val || "-");

  return `
    <input type="date"
           class="form-control form-control-sm js-process-date"
           data-row-id="${escapeAttr(str(r.id))}"
           data-prev-value="${escapeAttr(val)}"
           value="${escapeAttr(val)}"
           class="form-control form-control-sm js-process-date eff-process-date" />
  `;
}

/* -------------------------
   Events (process_date only) bind once
-------------------------- */
function bindHandlersOnce() {
  const acc = getGroupsContainer();
  if (!acc) return;

  if (acc.dataset.boundHandlers === "1") return;
  acc.dataset.boundHandlers = "1";

  // ✅ process_date update (admin only)
  acc.addEventListener("change", async (e) => {
    const input = e.target;
    if (!input?.classList?.contains("js-process-date")) return;
    if (!canAdminEdit()) return;

    const url = getUpdateProcessDateUrl();
    if (!url) return alertBox("처리일자 저장 URL이 없습니다. (data-update-process-date-url 확인)");

    const rowId = str(input.dataset.rowId);
    if (!rowId) return alertBox("row_id가 없습니다.");

    const process_date = str(input.value);
    const prev = str(input.dataset.prevValue);

    input.disabled = true;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ id: rowId, process_date, kind: "efficiency" }),
      });

      const data = await readJsonOrThrow(res, "처리일자 저장 실패");
      if (!isSuccessJson(data)) throw new Error(data.message || "처리일자 저장 실패");

      input.dataset.prevValue = process_date;
    } catch (err) {
      console.error("❌ update process_date error:", err);
      alertBox(err?.message || "처리일자 저장 중 오류가 발생했습니다.");
      input.value = prev; // rollback
    } finally {
      input.disabled = false;
    }
  });
}

/* -------------------------
   Render Groups (Accordion)
-------------------------- */
function renderGroups(groups, rowsByGroup) {
  const acc = getGroupsContainer();
  if (!acc) return;

  const subAdmin = isSubAdmin();
  const canDeleteGroup = canAdminEdit() && !subAdmin;

  const list = Array.isArray(groups) ? groups.map(normalizeGroup) : [];
  if (!list.length) {
    acc.innerHTML = `
      <div class="alert alert-secondary mb-0">
        표시할 지점효율 입력내용이 없습니다.
      </div>
    `;
    return;
  }

  const html = list
    .map((g, idx) => {
      const gid = str(g.group_key) || `g${idx}`;
      const gidPk = g.group_pk !== null ? String(g.group_pk) : "";

      const headingId = `heading_${escapeAttr(gid)}_${idx}`;
      const collapseId = `collapse_${escapeAttr(gid)}_${idx}`;

      // ✅ 타이틀: "요청일자 / 소속"
      const titleText = normalizeGroupTitle(g.title, g.month, g.branch);
      const headerMain = escapeHtml(titleText || "-");

      const rows = (rowsByGroup?.[gid] || []) || (gidPk ? rowsByGroup?.[gidPk] || [] : []);
      const rowCountNum = Number(g.row_count || rows.length || 0);
      const rowCountText = `${fmtNumber(rowCountNum)}건`;

      const totalAmtNum =
        (Number(g.total_amount) || 0) > 0 ? Number(g.total_amount) : Number(sumAmount(rows) || 0);
      const totalAmtText = `${fmtNumber(totalAmtNum)}원`;

      // ✅ 작은 텍스트: "건수 / 합계금액"
      const headerSub = escapeHtml(`${rowCountText} / ${totalAmtText}`);

      const { fileName, fileUrl, rawName } = pickPrimaryAttachment(g);
      const fileNameEsc = escapeAttr(fileName);
      const rawNameEsc = escapeAttr(rawName);

      const confirmFileHtml = `
        <input type="text"
               class="form-control form-control-sm confirm-file"
               value="${fileNameEsc}"
               placeholder="업로드 된 확인서 파일명"
               readonly>
      `;

      const downloadBtnHtml = fileUrl
        ? `
          <a class="btn btn-outline-success btn-sm js-confirm-download"
             href="${escapeAttr(fileUrl)}"
             download="${rawNameEsc}"
             data-group-id="${escapeAttr(gid)}">
            다운로드
          </a>
        `
        : `
          <button type="button" class="btn btn-outline-success btn-sm js-confirm-download" disabled
                  data-group-id="${escapeAttr(gid)}">
            다운로드
          </button>
        `;

      // ✅ 삭제버튼은 delete.js가 처리 (여기서는 UI만 렌더)
      const deleteGroupBtnHtml = canDeleteGroup
        ? `
          <button type="button"
                  class="btn btn-outline-danger btn-sm js-confirm-delete"
                  data-action="delete-group"
                  data-group-id="${escapeAttr(gid)}"
                  class="btn btn-outline-danger btn-sm eff-btn-nowrap">
            삭제
          </button>
        `
        : ``;

      const rowsHtml = rows.length
        ? `
          <div class="table-responsive">
            <table class="table table-sm mb-0 main-group-table">
              ${buildMainColGroup()}
              <thead class="table-light">
                <tr>
                  <th class="text-center">요청자</th>
                  <th class="text-center">구분</th>
                  <th class="text-center">금액</th>
                  <th class="text-center">세액</th>
                  <th class="text-center">공제자</th>
                  <th class="text-center">지급자</th>
                  <th class="text-center td-content">내용</th>
                  <th class="text-center">요청일</th>
                  <th class="text-center">처리일자</th>
                  <th class="text-center">삭제</th>
                </tr>
              </thead>
              <tbody>
                ${rows
                  .map((r) => {
                    const rowId = str(r.id);

                    const amountNum = Number(r.amount || 0);
                    const taxFromServer = Number(r.tax);
                    const taxNum = Number.isFinite(taxFromServer)
                      ? taxFromServer
                      : (Number.isFinite(amountNum) ? Math.round(amountNum * 0.033) : 0);

                    const ded = `${escapeHtml(str(r.ded_name))}${
                      r.ded_id ? `(${escapeHtml(str(r.ded_id))})` : ""
                    }`.trim();

                    const pay = `${escapeHtml(str(r.pay_name))}${
                      r.pay_id ? `(${escapeHtml(str(r.pay_id))})` : ""
                    }`.trim();

                    const rowDeleteDisabled = subAdmin ? "disabled" : "";
                    const processDateCell = renderProcessDateCell(r);

                    const contentText = str(r.content);
                    const contentTitle = escapeAttr(contentText);
                    const contentBody = escapeHtml(contentText);

                    return `
                      <tr>
                        <td class="text-center">${escapeHtml(formatRequesterDisplay(r))}</td>
                        <td class="text-center">${escapeHtml(str(r.category))}</td>

                        <td class="text-end">${fmtNumber(amountNum)}</td>
                        <td class="text-end">${fmtNumber(taxNum)}</td>

                        <td class="text-center">${ded || "-"}</td>
                        <td class="text-center">${pay || "-"}</td>

                        <td class="td-content" title="${contentTitle}">${contentBody || "-"}</td>

                        <td class="text-center">${escapeHtml(str(r.request_date))}</td>

                        <td class="text-center">${processDateCell}</td>

                        <td class="text-center">
                          <button type="button"
                                  class="btn btn-outline-danger btn-sm"
                                  data-action="delete-row"
                                  data-row-id="${escapeAttr(rowId)}"
                                  class="btn btn-outline-danger btn-sm eff-btn-nowrap"
                                  ${rowDeleteDisabled}>
                            삭제
                          </button>
                        </td>
                      </tr>
                    `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        `
        : `
          <div class="text-muted small py-3 px-3">
            이 그룹에 저장된 행이 없습니다.
          </div>
        `;

      // ✅ 헤더 구조 (좌 토글 / 우 확인서)
      return `
        <div class="accordion-item">
          <h2 class="accordion-header" id="${headingId}">
            <div class="eff-acc-head">

              <!-- 좌: 토글(제목) -->
              <button class="accordion-button collapsed eff-acc-toggle" type="button"
                      data-bs-toggle="collapse"
                      data-bs-target="#${collapseId}"
                      aria-expanded="false"
                      aria-controls="${collapseId}">

                <div class="eff-group-scroll">
                  <div class="eff-group-meta">
                    <span class="eff-group-title">${headerMain}</span>
                    <span class="eff-group-sub">${headerSub}</span>
                  </div>
                </div>

              </button>

              <!-- 우: 확인서 박스(토글과 분리) -->
              <div class="eff-acc-confirm">

                ${confirmFileHtml}

                ${downloadBtnHtml}
                ${deleteGroupBtnHtml}

              </div>

            </div>
          </h2>

          <div id="${collapseId}" class="accordion-collapse collapse"
               aria-labelledby="${headingId}"
               data-bs-parent="#confirmGroupsAccordion">
            <div class="accordion-body p-0">
              ${rowsHtml}
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  acc.innerHTML = html;

  // ✅ requester 컬럼 2칸(요청자+사번) → 1칸 통합이므로
  // 템플릿(root.dataset.mainColWidths)에서도 requester_id 제거/조정 권장

  // ✅ 렌더 후 컬럼비율 적용
  const root = getRoot();
  acc.querySelectorAll("table.main-group-table").forEach((tbl) => applyMainColWidths(root, tbl));
}

/* -------------------------
   Public: fetchData
-------------------------- */
export async function fetchData(ym, branch) {
  const url = getFetchUrl();
  if (!url) {
    alertBox("조회 URL이 없습니다. (data-fetch-url / data-data-fetch-url 확인)");
    return;
  }

  const month = str(ym);
  const br = str(branch);
  if (!month || !br) return;

  // ✅ 재조회 캐시(삭제 후 refresh에서도 사용)
  window.__lastEfficiencyYM = month;
  window.__lastEfficiencyBranch = br;

  showLoading("조회 중...");
  try {
    const fullUrl = `${url}?month=${encodeURIComponent(month)}&branch=${encodeURIComponent(br)}&grouped=1`;
    log("fetch ->", fullUrl);

    const res = await fetch(fullUrl, {
      method: "GET",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });

    const payload = await readJsonOrThrow(res, "조회 실패");
    if (!isSuccessJson(payload)) throw new Error(payload.message || "조회 실패");

    const groups = payload.groups || [];
    const rows = payload.rows || [];

    const rowsByGroup = buildRowsByGroup(rows);
    renderGroups(groups, rowsByGroup);

    // ✅ 이벤트 1회 바인딩(process_date)
    bindHandlersOnce();
  } catch (e) {
    console.error("❌ efficiency fetchData error:", e);
    alertBox(e?.message || "조회 중 오류가 발생했습니다.");
  } finally {
    hideLoading();
  }
}
