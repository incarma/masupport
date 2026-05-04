/**
 * django_ma/static/js/board/support_form.js
 * ------------------------------------------------------------
 * ✅ 업무요청서 페이지 전용 스크립트 (Board)
 * 기능:
 * - 요청대상 행 / 계약사항 행 추가/초기화/제거
 * - 공통 검색 모달(userSelected 이벤트) 결과를 현재 row에 주입
 * - 보험료 입력: 숫자만 + 콤마 / submit 시 콤마 제거
 * - PDF 생성: POST(FormData) → Blob 다운로드
 *
 * 요구 요소(id):
 * - requestForm
 * - loadingOverlay
 * - generatePdfBtn (data-pdf-url 필요)
 * - addUserBtn/resetUserBtn + addContractBtn/resetContractBtn
 *
 * 요구 행 구조:
 * - .user-row / .contract-row 들이 DOM에 미리 존재 (숨김: style.display="none")
 * - 제거 버튼은 class "btn-remove" + data-index 또는 rowSelector 기반으로 탐색 가능
 * - 검색 버튼은 .btn-open-search + data-row="1..n" 형태(현재 코드 호환)
 * ------------------------------------------------------------
 */

import { qs, qsa } from "../common/forms/dom.js";
import { initRowController } from "../common/forms/rows.js";
import { bindPremiumInputs } from "../common/forms/premium.js";
import { getCSRFToken } from "../common/manage/csrf.js";

const INIT_FLAG = "boardSupportInited";
const BUSY_FLAG = "boardSupportBusy";
const USER_BIND_FLAG = "boardSupportUserBind";
const PAGE_SHOW_FLAG = "boardSupportPageShowBind";

function isJsonResponse(res) {
  return (res.headers.get("content-type") || "").toLowerCase().includes("application/json");
}

async function readErrorMessage(res, fallback) {
  if (!isJsonResponse(res)) return fallback;
  try {
    const data = await res.json();
    return data?.message || data?.error || fallback;
  } catch (_) {
    return fallback;
  }
}

function setBusyState({ overlay, button, busy }) {
  if (overlay) overlay.style.display = busy ? "block" : "none";
  if (button) {
    button.disabled = !!busy;
    button.dataset[BUSY_FLAG] = busy ? "1" : "";
    button.setAttribute("aria-busy", busy ? "true" : "false");
  }
}

function bindPageShowReset({ overlay, button }) {
  if (window[PAGE_SHOW_FLAG]) return;
  window[PAGE_SHOW_FLAG] = true;
  window.addEventListener("pageshow", () => {
    setBusyState({ overlay, button, busy: false });
  });
}

async function downloadPdf({ url, formEl, filename }) {
  const formData = new FormData(formEl);
  const csrf = getCSRFToken();

  const res = await fetch(url, {
    method: "POST",
    body: formData,
    headers: {
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
      "X-Requested-With": "XMLHttpRequest",
    },
    credentials: "same-origin",
  });

  if (!res.ok) {
    const fallback = `PDF 생성 실패 (HTTP ${res.status})`;
    throw new Error(await readErrorMessage(res, fallback));
  }

  if (isJsonResponse(res)) {
    throw new Error(await readErrorMessage(res, "PDF 생성 실패"));
  }

  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (!ct.includes("application/pdf")) {
    let hint = "";
    try {
      hint = (await res.text()).slice(0, 200);
    } catch (_) {
      hint = "";
    }
    throw new Error(
      "PDF 응답이 아닙니다. (서버가 리다이렉트/에러 페이지를 반환했을 수 있습니다.)"
      + (hint ? `\n\n${hint}` : "")
    );
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename || "download.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(objectUrl);
}

function getPdfUrlFallback() {
  const btn = document.querySelector("#generatePdfBtn");
  const fromBtn = btn?.dataset?.pdfUrl;
  if (fromBtn) return fromBtn;
  const root = document.querySelector("#support-form");
  return root?.dataset?.pdfUrl || "";
}

/**
 * ✅ support_form 전용: userSelected 결과를 currentRow에 넣기
 * - 기존 템플릿 input name 규칙을 그대로 따른다.
 */
function bindUserSelectedAutofill() {
  if (window[USER_BIND_FLAG]) return;
  window[USER_BIND_FLAG] = true;

  let currentRow = "";

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-open-search");
    if (!btn) return;
    currentRow = String(btn.dataset.row || "").trim();
  });

  document.addEventListener("userSelected", (e) => {
    const u = e.detail || {};
    if (!currentRow) return;

    const set = (name, val) => {
      const el = document.querySelector(
        `input[name="${name}_${currentRow}"], input[name="${name}${currentRow}"], input[name="${name}-${currentRow}"]`
      );
      if (el) el.value = val ?? "";
    };

    set("target_name", u.name);
    set("target_code", u.id);
    set("target_join", u.enter);
    set("target_leave", u.quit);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = qs("#requestForm");
  const overlay = qs("#loadingOverlay");
  const generateBtn = qs("#generatePdfBtn");

  if (!form || !generateBtn) return;
  if (form.dataset[INIT_FLAG] === "1") return;
  form.dataset[INIT_FLAG] = "1";

  generateBtn.setAttribute("type", "button");
  setBusyState({ overlay, button: generateBtn, busy: false });
  bindPageShowReset({ overlay, button: generateBtn });

  // 1) 요청대상 행 제어
  initRowController({
    rowSelector: ".user-row",
    addBtnId: "addUserBtn",
    resetBtnId: "resetUserBtn",
    removeBtnClass: "btn-remove",
    maxCount: 5,
    alertMsg:
      "요청대상은 최대 5개까지만 입력 가능합니다.\n추가 입력이 필요한 경우 상세내용 칸에 기재해주세요.",
    removeMode: "delegation",
    // support_form은 row가 data-index를 쓰는 경우가 많아서, 가능하면 이를 우선 사용
    resolveRowForRemove: (btn) => {
      const idx = String(btn?.dataset?.index || "").trim();
      if (idx) {
        const row = document.querySelector(`.user-row[data-index="${idx}"], .contract-row[data-index="${idx}"]`);
        if (row) return row;
      }
      return btn?.closest?.(".user-row") || btn?.closest?.(".contract-row");
    },
  });

  // 2) 계약사항 행 제어
  initRowController({
    rowSelector: ".contract-row",
    addBtnId: "addContractBtn",
    resetBtnId: "resetContractBtn",
    removeBtnClass: "btn-remove",
    maxCount: 5,
    alertMsg:
      "계약사항은 최대 5개까지만 입력 가능합니다.\n추가 입력이 필요한 경우 상세내용 칸에 기재해주세요.",
    removeMode: "delegation",
    resolveRowForRemove: (btn) => {
      const idx = String(btn?.dataset?.index || "").trim();
      if (idx) {
        const row = document.querySelector(`.contract-row[data-index="${idx}"]`);
        if (row) return row;
      }
      return btn?.closest?.(".contract-row");
    },
  });

  // 3) 검색 모달 결과 바인딩
  bindUserSelectedAutofill();

  // 4) 보험료 입력 처리
  bindPremiumInputs({ formEl: form, inputSelector: 'input[name^="premium_"]' });

  // 5) PDF 생성
  generateBtn.addEventListener("click", async () => {
    if (generateBtn.dataset[BUSY_FLAG] === "1") return;

    const pdfUrl = generateBtn.dataset.pdfUrl || getPdfUrlFallback();
    if (!pdfUrl) return window.alert("PDF URL(data-pdf-url)이 없습니다.");

    setBusyState({ overlay, button: generateBtn, busy: true });

    try {
      await downloadPdf({
        url: pdfUrl,
        formEl: form,
        filename: "업무요청서.pdf",
      });
    } catch (err) {
      console.error(err);
      window.alert(err?.message || "PDF 생성 중 오류가 발생했습니다.");
    } finally {
      setBusyState({ overlay, button: generateBtn, busy: false });
    }
  });
});
