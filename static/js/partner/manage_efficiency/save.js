// django_ma/static/js/partner/manage_efficiency/save.js
//
// ✅ confirm_group_id 기반 저장
// - confirmGroupId 없으면 저장 차단
// - 저장 후 confirmGroupId/파일명 초기화(“1회 업로드 = 1회 저장”)
// - 저장 후 fetchData 재조회
//
// ✅ FIX: "tax is not defined" 방지
// - 각 입력행에서 tax 값을 안전하게 읽어서 저장
// - tax 입력값이 비어 있으면 amount 기반으로 계산 fallback

import { els } from "./dom_refs.js";
import { showLoading, hideLoading, alertBox, getCSRFToken, selectedYM } from "./utils.js";
import { fetchData } from "./fetch.js";
import { resetInputSection } from "./input_rows.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

function str(v) {
  return String(v ?? "").trim();
}
function digitsOnly(v) {
  return str(v).replace(/[^\d]/g, "");
}
function normalizeAmount(raw) {
  const digits = digitsOnly(raw);
  const n = parseInt(digits || "0", 10);
  return Number.isFinite(n) ? n : 0;
}

const TAX_RATE = 0.033;
function calcTaxInt(amountInt) {
  const a = Number(amountInt || 0);
  if (!Number.isFinite(a) || a <= 0) return 0;
  // input_rows.js와 동일하게 floor 사용
  return Math.floor(a * TAX_RATE);
}

/* =========================================================
   Confirm group helpers
========================================================= */
function getConfirmGroupId() {
  return str(els.confirmGroupId?.value || document.getElementById("confirmGroupId")?.value || "");
}
function mustHaveGroupOrAlert() {
  const gid = getConfirmGroupId();
  if (!gid) {
    alertBox("※ 반드시 확인서를 업로드해야 저장이 가능합니다.");
    return null;
  }
  return gid;
}

/* =========================================================
   Branch/Part helpers
========================================================= */
function getUser() {
  return window.currentUser || {};
}

function getBranchForSave() {
  const user = getUser();
  const grade = str(user.grade);

  if (grade === "superuser") {
    return str(els.branch?.value || document.getElementById("branchSelect")?.value || "");
  }
  return str(user.branch) || str(els.root?.dataset?.branch) || "";
}

function getPartForSave() {
  const user = getUser();
  const grade = str(user.grade);

  // ✅ superuser는 선택값 우선
  if (grade === "superuser") {
    return str(els.part?.value || document.getElementById("partSelect")?.value || "");
  }
  return str(user.part) || str(els.root?.dataset?.part) || "";
}

/* =========================================================
   Collect rows
========================================================= */
function getTaxFromRow(row, amountInt) {
  // 템플릿 기준: name="tax" (readonly)
  // 혹시 이름이 바뀌는 케이스도 대비
  const candidates = ["tax", "tax_amount", "vat", "se_tax"];
  let raw = "";
  for (const n of candidates) {
    const el = row.querySelector(`[name="${n}"]`);
    if (el) {
      raw = el.value ?? "";
      break;
    }
  }

  const taxInt = normalizeAmount(raw);
  if (taxInt > 0) return taxInt;

  // 값이 비어있으면 amount 기반으로 계산
  return calcTaxInt(amountInt);
}

function collectRowsFromInputTable() {
  const table = els.inputTable || document.getElementById("inputTable");
  if (!table) return [];

  const rows = Array.from(table.querySelectorAll("tbody tr.input-row"));
  const payloadRows = [];

  for (const row of rows) {
    const category = str(row.querySelector("[name='category']")?.value || "");
    const amountRaw = row.querySelector("[name='amount']")?.value ?? "";
    const amount = normalizeAmount(amountRaw);
    const content = str(row.querySelector("[name='content']")?.value || "");

    const ded_name = str(row.querySelector("[name='ded_name']")?.value || "");
    const ded_id = str(row.querySelector("[name='ded_id']")?.value || "");
    const pay_name = str(row.querySelector("[name='pay_name']")?.value || "");
    const pay_id = str(row.querySelector("[name='pay_id']")?.value || "");

    if (!category || amount <= 0 || !content) {
      throw new Error("구분/금액/내용은 필수입니다. 입력값을 확인해주세요.");
    }

    // ✅ 핵심 FIX: tax를 row에서 읽거나 계산해서 저장
    const tax = getTaxFromRow(row, amount);

    payloadRows.push({
      category,
      amount,
      tax,
      ded_name,
      ded_id,
      pay_name,
      pay_id,
      content,
    });
  }

  return payloadRows;
}

export async function saveRows() {
  const url = els.root?.dataset?.dataSaveUrl;
  if (!url) {
    alertBox("저장 URL이 없습니다. (data-data-save-url 확인)");
    return;
  }

  const confirmGroupId = mustHaveGroupOrAlert();
  if (!confirmGroupId) return;

  let payloadRows = [];
  try {
    payloadRows = collectRowsFromInputTable();
  } catch (e) {
    alertBox(e?.message || "입력값을 확인해주세요.");
    return;
  }

  if (!payloadRows.length) {
    alertBox("저장할 데이터가 없습니다.");
    return;
  }

  const ym = selectedYM(els.year, els.month);
  const branch = getBranchForSave();
  const part = getPartForSave();
  const user = getUser();

  if (!ym) return alertBox("연도/월도를 확인해주세요.");
  if (!branch && str(user.grade) === "superuser") return alertBox("지점을 먼저 선택하세요.");

  showLoading("저장 중...");

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        rows: payloadRows,
        month: ym,
        part,
        branch,
        confirm_group_id: confirmGroupId, // ✅ NEW
      }),
    });

    const result = await readJsonOrThrow(res, "저장 실패");
    if (!isSuccessJson(result)) {
      throw new Error(result.message || "저장 중 오류");
    }

    const count = result.saved_count ?? payloadRows.length;
    alertBox(`✅ ${count}건 저장 완료\n그룹ID: ${result.confirm_group_id || confirmGroupId}`);

    // 입력 초기화
    resetInputSection();

    // ✅ 확인서 상태 초기화(“1회 업로드 = 1회 저장”)
    if (els.confirmGroupId) els.confirmGroupId.value = "";
    if (els.confirmFileName) els.confirmFileName.value = "";
    if (els.confirmFileInput) els.confirmFileInput.value = "";
    if (els.confirmAttachmentId) els.confirmAttachmentId.value = "";

    // 재조회
    try {
      await fetchData(ym, branch);
    } catch (reErr) {
      console.warn("⚠️ 저장 후 재조회 오류:", reErr);
      alertBox("저장은 완료되었지만, 새로고침 중 오류가 발생했습니다.");
    }
  } catch (err) {
    console.error("❌ efficiency saveRows error:", err);
    alertBox(err?.message || "저장 중 오류가 발생했습니다.");
  } finally {
    hideLoading();
  }
}
