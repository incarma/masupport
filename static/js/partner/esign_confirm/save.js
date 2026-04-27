// static/js/partner/esign_confirm/save.js
// 내용 입력 테이블 행 관리 + 저장 API 호출
// Playbook: search_user_modal SSOT 경유, 10행 제한 서버/클라이언트 동시 검증

"use strict";

window.EsignSave = (function () {
  const MAX_ROWS = 10;

  // ── CSRF 헬퍼 (ES Module 미사용 — 쿠키 직접 읽기) ───────────
  function getCsrf() {
    return (
      document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
      document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
      ""
    );
  }

  // ── 시작월도/종료월도 옵션 생성 (현재 기준 ±13개월) ──────────
  function buildYmOptions() {
    const now  = new Date();
    const opts = ['<option value="">선택</option>'];
    for (let i = -13; i <= 13; i++) {
      const d  = new Date(now.getFullYear(), now.getMonth() + i, 1);
      const yy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const val = `${yy}-${mm}`;
      opts.push(`<option value="${val}">${val}</option>`);
    }
    return opts.join("");
  }
  const YM_OPTIONS = buildYmOptions();

  // ── 카테고리 옵션 ────────────────────────────────────────────
  const CAT_OPTIONS = `
    <option value="">구분 선택</option>
    <option value="지급">지급</option>
    <option value="공제">공제</option>
    <option value="기타">기타</option>`;

  // ── 행 HTML 생성 ─────────────────────────────────────────────
  function buildRowHtml(branch) {
    return `
      <tr>
        <td><input type="text" class="form-control form-control-sm" name="branch_display"
                   value="${branch}" readonly tabindex="-1"></td>
        <td>
          <select name="start_ym" class="form-select form-select-sm">${YM_OPTIONS}</select>
        </td>
        <td>
          <select name="end_ym" class="form-select form-select-sm">${YM_OPTIONS}</select>
        </td>
        <td>
          <select name="category" class="form-select form-select-sm">${CAT_OPTIONS}</select>
        </td>
        <td>
          <input type="text" class="form-control form-control-sm text-end" name="amount"
                 placeholder="0" inputmode="numeric">
        </td>
        <td>
          <div class="input-group input-group-sm">
            <input type="text" class="form-control" name="ded_name" placeholder="성명" readonly>
            <input type="hidden" name="ded_id">
            <button type="button" class="btn btn-outline-secondary btn-sm js-search-user-btn"
                    data-role="deduct" tabindex="-1">검색</button>
          </div>
        </td>
        <td>
          <div class="input-group input-group-sm">
            <input type="text" class="form-control" name="pay_name" placeholder="성명" readonly>
            <input type="hidden" name="pay_id">
            <button type="button" class="btn btn-outline-secondary btn-sm js-search-user-btn"
                    data-role="pay" tabindex="-1">검색</button>
          </div>
        </td>
        <td>
          <input type="text" class="form-control form-control-sm" name="content"
                 placeholder="최대 80자" maxlength="80">
        </td>
        <td class="text-center">
          <button type="button" class="btn btn-outline-danger btn-sm js-del-row">✕</button>
        </td>
      </tr>`;
  }

  // ── 행 수 표시 갱신 ──────────────────────────────────────────
  function updateRowCount() {
    const tbody = window.EsignDom.inputTbody();
    const count = tbody ? tbody.querySelectorAll("tr").length : 0;
    const msg   = window.EsignDom.rowCountMsg();
    if (msg) {
      msg.textContent = `${count} / ${MAX_ROWS}행`;
      msg.className   = count >= MAX_ROWS ? "text-danger small" : "text-muted small";
    }
    return count;
  }

  // ── 행 추가 ──────────────────────────────────────────────────
  function addRow() {
    const tbody = window.EsignDom.inputTbody();
    if (!tbody) return;

    const count = tbody.querySelectorAll("tr").length;
    if (count >= MAX_ROWS) {
      alert(`최대 ${MAX_ROWS}건까지 입력할 수 있습니다.`);
      return;
    }

    const root   = window.EsignDom.root();
    const branch = root?.dataset?.userBranch || "";
    const tmp    = document.createElement("tbody");
    tmp.innerHTML = buildRowHtml(branch);
    tbody.appendChild(tmp.firstElementChild);
    updateRowCount();
  }

  // ── 행 전체 초기화 ────────────────────────────────────────────
  function clearRows() {
    const tbody = window.EsignDom.inputTbody();
    if (!tbody) return;
    if (tbody.querySelectorAll("tr").length > 0) {
      if (!confirm("입력된 내용을 모두 초기화하시겠습니까?")) return;
    }
    tbody.innerHTML = "";
    updateRowCount();
  }

  // ── 행 삭제 (이벤트 위임) ────────────────────────────────────
  function handleDeleteRow(e) {
    const btn = e.target.closest(".js-del-row");
    if (!btn) return;
    btn.closest("tr")?.remove();
    updateRowCount();
  }

  // ── 금액 포맷 (입력 blur) ────────────────────────────────────
  function handleAmountBlur(e) {
    const input = e.target;
    if (input.name !== "amount") return;
    const raw = input.value.replace(/,/g, "");
    const num = parseInt(raw, 10);
    if (!isNaN(num) && num > 0) {
      input.value = num.toLocaleString("ko-KR");
    } else {
      input.value = "";
    }
  }

  // ── rows 수집 및 검증 ─────────────────────────────────────────
  function collectRows() {
    const tbody = window.EsignDom.inputTbody();
    if (!tbody) throw new Error("입력 테이블을 찾을 수 없습니다.");

    const trs = tbody.querySelectorAll("tr");
    if (!trs.length) throw new Error("저장할 행이 없습니다.");
    if (trs.length > MAX_ROWS) throw new Error(`최대 ${MAX_ROWS}건까지 저장할 수 있습니다.`);

    const rows = [];
    trs.forEach((tr, i) => {
      const get = (name) => (tr.querySelector(`[name="${name}"]`)?.value || "").trim();

      const startYm   = get("start_ym");
      const endYm     = get("end_ym");
      const dedId     = get("ded_id");
      const payId     = get("pay_id");
      const amountRaw = get("amount").replace(/,/g, "");

      if (!startYm || !endYm) throw new Error(`${i + 1}번 행: 시작월도와 종료월도는 필수입니다.`);
      if (startYm > endYm)    throw new Error(`${i + 1}번 행: 종료월도는 시작월도 이후여야 합니다.`);
      if (!dedId)  throw new Error(`${i + 1}번 행: 공제자를 검색하여 선택해 주세요.`);
      if (!payId)  throw new Error(`${i + 1}번 행: 지급자를 검색하여 선택해 주세요.`);

      const amount = amountRaw ? parseInt(amountRaw, 10) : null;
      if (amountRaw && isNaN(amount)) throw new Error(`${i + 1}번 행: 금액이 올바르지 않습니다.`);

      rows.push({
        start_ym: startYm,
        end_ym:   endYm,
        category: get("category"),
        amount:   amount,
        ded_name: get("ded_name"),
        ded_id:   dedId,
        pay_name: get("pay_name"),
        pay_id:   payId,
        content:  get("content"),
      });
    });

    return rows;
  }

  // ── 저장 실행 ────────────────────────────────────────────────
  async function save() {
    const dom     = window.EsignDom;
    const root    = dom.root();
    const ds      = root?.dataset || {};
    const saveUrl = ds.saveUrl;
    if (!saveUrl) { alert("저장 URL이 설정되지 않았습니다."); return; }

    const year   = dom.yearSelect()?.value   || "";
    const month  = dom.monthSelect()?.value  || "";
    const branch = dom.branchSelect()?.value || ds.userBranch || "";
    const part   = dom.partSelect()?.value   || ds.userPart   || "";

    const ym = year && month ? `${year}-${month.padStart(2, "0")}` : "";
    if (!ym)     { alert("연도와 월을 선택해 주세요."); return; }
    if (!branch) { alert("지점을 선택해 주세요."); return; }

    let rows;
    try {
      rows = collectRows();
    } catch (e) {
      alert(e.message);
      return;
    }

    const btnSave = dom.btnSave();
    if (btnSave) { btnSave.disabled = true; btnSave.textContent = "저장 중..."; }

    try {
      const res = await fetch(saveUrl, {
        method:      "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type":     "application/json",
          "X-CSRFToken":      getCsrf(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ month: ym, part, branch, rows }),
      });

      const data = await res.json();
      if (data.status !== "success") {
        alert(data.message || "저장에 실패했습니다.");
        return;
      }

      alert(`저장 완료! (${data.saved_count}건, 서명자 ${data.signer_count}명 등록)`);

      // 초기화 + 재조회
      if (dom.inputTbody()) dom.inputTbody().innerHTML = "";
      updateRowCount();
      await window.EsignFetch.fetchData();

    } catch (e) {
      console.error("[EsignSave] save error:", e);
      alert("저장 중 오류가 발생했습니다.");
    } finally {
      if (btnSave) { btnSave.disabled = false; btnSave.textContent = "저장"; }
    }
  }

  // ── 검색 모달 연동 (이벤트 위임) ────────────────────────────
  function handleSearchBtn(e) {
    const btn = e.target.closest(".js-search-user-btn");
    if (!btn) return;

    const tr   = btn.closest("tr");
    const role = btn.dataset.role; // "deduct" | "pay"

    // search_user_modal.js SSOT 경유
    if (typeof window.openSearchUserModal === "function") {
      window.openSearchUserModal({
        onSelect: (user) => {
          const nameKey = role === "deduct" ? "ded_name" : "pay_name";
          const idKey   = role === "deduct" ? "ded_id"   : "pay_id";
          const nameField = tr.querySelector(`[name="${nameKey}"]`);
          const idField   = tr.querySelector(`[name="${idKey}"]`);
          if (nameField) nameField.value = user.name || "";
          if (idField)   idField.value   = user.id   || "";
        },
      });
    } else {
      alert("사용자 검색 모달을 불러올 수 없습니다.");
    }
  }

  // ── 이벤트 바인딩 ────────────────────────────────────────────
  function bindEvents() {
    const dom    = window.EsignDom;
    const tbody  = dom.inputTbody();
    const addBtn = dom.btnAddRow();
    const clrBtn = dom.btnClearRows();
    const savBtn = dom.btnSave();

    addBtn?.addEventListener("click", addRow);
    clrBtn?.addEventListener("click", clearRows);
    savBtn?.addEventListener("click", save);

    // 이벤트 위임 (tbody — 동적 행 대응)
    tbody?.addEventListener("click", handleDeleteRow);
    tbody?.addEventListener("click", handleSearchBtn);
    tbody?.addEventListener("blur",  handleAmountBlur, true); // capture

    updateRowCount();
  }

  return { bindEvents, addRow, clearRows, save, updateRowCount };
})();