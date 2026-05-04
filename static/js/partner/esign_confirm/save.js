// static/js/partner/esign_confirm/save.js
// 내용 입력 테이블 행 관리 + 저장 API 호출
//
// search_user_modal.js 연동 방식:
//   - 버튼: class="btnOpenSearch" + data-bs-toggle/target → 모달 오픈 + activeRow 추적
//   - 선택 후 "userSelected" 커스텀 이벤트 발행 (document / window)
//   - save.js가 이벤트를 수신하여 _lastClickedRole("deduct"|"pay") 기준으로
//     올바른 셀(data-role)의 name/id 필드에 직접 기입
//   - autofillSelectedUser()의 tg_name/tg_id 자동채움은 의도적으로 무시
//     (같은 tr 내에 tg_name이 2개라 항상 첫 번째 셀에 적용되는 문제 회피)

"use strict";

window.EsignSave = (function () {
  const MAX_ROWS = 10;

  // ── 상태: 마지막으로 클릭된 검색 버튼의 역할 ─────────────────
  // "deduct" | "pay" | null
  let _lastClickedRole = null;
  let _lastClickedRow  = null;

  // ── CSRF 헬퍼 ────────────────────────────────────────────────
  // TODO RULE-Q-01: csrf_window.js 로드 확인 후 window.csrfToken 으로 전환 필요
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
      opts.push(`<option value="${yy}-${mm}">${yy}-${mm}</option>`);
    }
    return opts.join("");
  }
  const YM_OPTIONS = buildYmOptions();

  // ── 카테고리 옵션 ────────────────────────────────────────────
  const CAT_OPTIONS = `
    <option value="">구분 선택</option>
    <option value="지점관리">지점관리</option>
    <option value="지점시상">지점시상</option>
    <option value="상위차감">상위차감</option>`;

  // ── XSS 방어 ─────────────────────────────────────────────────
  function _esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── 행 HTML 생성 ─────────────────────────────────────────────
  // ⚠️ 공제자/지급자 셀 모두 name="tg_name"/name="tg_id" 사용
  //    (search_user_modal.js activeRow 추적용 — 실제 값은 userSelected 이벤트로 채움)
  // ⚠️ 실제 저장값: data-ded-name / data-ded-id / data-pay-name / data-pay-id (tr에 저장)
  function buildRowHtml(branch) {
    return `
      <tr class="input-row"
          data-ded-name="" data-ded-id=""
          data-pay-name="" data-pay-id="">
        <td>
          <input type="text" class="form-control form-control-sm"
                 name="branch_display" value="${_esc(branch)}" readonly tabindex="-1">
        </td>
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
          <input type="text" class="form-control form-control-sm text-end"
                 name="amount" placeholder="0" inputmode="numeric">
        </td>

        <!-- 공제자 셀 -->
        <td data-role="deduct">
          <div class="input-group input-group-sm">
            <input type="text" class="form-control esign-display-name"
                   placeholder="성명" readonly tabindex="-1">
            <input type="hidden" class="esign-hidden-id">
            <button type="button"
                    class="btn btn-outline-secondary btn-sm btnOpenSearch"
                    data-role="deduct"
                    data-bs-toggle="modal"
                    data-bs-target="#searchUserModal">검색</button>
          </div>
        </td>

        <!-- 지급자 셀 -->
        <td data-role="pay">
          <div class="input-group input-group-sm">
            <input type="text" class="form-control esign-display-name"
                   placeholder="성명" readonly tabindex="-1">
            <input type="hidden" class="esign-hidden-id">
            <button type="button"
                    class="btn btn-outline-secondary btn-sm btnOpenSearch"
                    data-role="pay"
                    data-bs-toggle="modal"
                    data-bs-target="#searchUserModal">검색</button>
          </div>
        </td>

        <td>
          <input type="text" class="form-control form-control-sm"
                 name="content" placeholder="최대 80자" maxlength="80">
        </td>
        <td class="text-center">
          <button type="button" class="btn btn-outline-danger btn-sm js-del-row">✕</button>
        </td>
      </tr>`;
  }

  // ── 검색 버튼 클릭 추적 (capture) ────────────────────────────
  // btnOpenSearch 클릭 시 어느 셀(공제/지급)의 버튼인지 기억
  function handleSearchBtnCapture(e) {
    const btn = e.target.closest(".btnOpenSearch");
    if (!btn) return;

    const tbody = window.EsignDom?.inputTbody?.();
    if (!tbody || !tbody.contains(btn)) return; // inputTable 내부 버튼만 처리

    _lastClickedRole = btn.dataset.role || null; // "deduct" | "pay"
    _lastClickedRow  = btn.closest("tr.input-row") || null;
  }

  // ── userSelected 이벤트 수신 → 올바른 셀에 적용 ─────────────
  function handleUserSelected(e) {
    const selected = e.detail;
    if (!selected || !_lastClickedRow || !_lastClickedRole) return;

    // document에 아직 존재하는 행인지 확인
    if (!document.contains(_lastClickedRow)) {
      _lastClickedRow = null;
      _lastClickedRole = null;
      return;
    }

    const name = (selected.name || "").trim();
    const id   = (selected.id   || "").trim();

    // data-role="deduct|pay" 셀 내부 필드에 직접 기입
    const cell = _lastClickedRow.querySelector(`[data-role="${_lastClickedRole}"]`);
    if (cell) {
      const nameInput = cell.querySelector(".esign-display-name");
      const idInput   = cell.querySelector(".esign-hidden-id");
      if (nameInput) nameInput.value = name;
      if (idInput)   idInput.value   = id;
    }

    // tr에도 캐싱 (collectRows에서 읽음)
    if (_lastClickedRole === "deduct") {
      _lastClickedRow.dataset.dedName = name;
      _lastClickedRow.dataset.dedId   = id;
    } else {
      _lastClickedRow.dataset.payName = name;
      _lastClickedRow.dataset.payId   = id;
    }

    // 사용 후 초기화
    _lastClickedRole = null;
    _lastClickedRow  = null;
  }

  // ── 행 수 표시 갱신 ──────────────────────────────────────────
  function updateRowCount() {
    const tbody = window.EsignDom.inputTbody();
    const count = tbody ? tbody.querySelectorAll("tr.input-row").length : 0;
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
    if (tbody.querySelectorAll("tr.input-row").length >= MAX_ROWS) {
      alert(`최대 ${MAX_ROWS}건까지 입력할 수 있습니다.`);
      return;
    }
    const branch = window.EsignDom.root()?.dataset?.userBranch || "";
    const tmp    = document.createElement("tbody");
    tmp.innerHTML = buildRowHtml(branch);
    tbody.appendChild(tmp.firstElementChild);
    updateRowCount();
  }

  // ── 행 전체 초기화 ────────────────────────────────────────────
  function clearRows() {
    const tbody = window.EsignDom.inputTbody();
    if (!tbody) return;
    if (tbody.querySelectorAll("tr.input-row").length > 0) {
      if (!confirm("입력된 내용을 모두 초기화하시겠습니까?")) return;
    }
    tbody.innerHTML = "";
    updateRowCount();
  }

  // ── 행 삭제 (이벤트 위임) ────────────────────────────────────
  function handleDeleteRow(e) {
    const btn = e.target.closest(".js-del-row");
    if (!btn) return;
    btn.closest("tr.input-row")?.remove();
    updateRowCount();
  }

  // ── 금액 포맷 (입력 blur) ────────────────────────────────────
  function handleAmountBlur(e) {
    const input = e.target;
    if (input.name !== "amount") return;
    const raw = input.value.replace(/,/g, "");
    const num = parseInt(raw, 10);
    input.value = (!isNaN(num) && num > 0) ? num.toLocaleString("ko-KR") : "";
  }

  // ── rows 수집 및 검증 ─────────────────────────────────────────
  // 공제자/지급자 값: tr의 data-ded-*/data-pay-* (userSelected 이벤트가 채움)
  function collectRows() {
    const tbody = window.EsignDom.inputTbody();
    if (!tbody) throw new Error("입력 테이블을 찾을 수 없습니다.");

    const trs = tbody.querySelectorAll("tr.input-row");
    if (!trs.length) throw new Error("저장할 행이 없습니다.");
    if (trs.length > MAX_ROWS) throw new Error(`최대 ${MAX_ROWS}건까지 저장할 수 있습니다.`);

    const rows = [];
    trs.forEach((tr, i) => {
      const get = (name) =>
        (tr.querySelector(`[name="${name}"]`)?.value || "").trim();

      const startYm   = get("start_ym");
      const endYm     = get("end_ym");
      const amountRaw = get("amount").replace(/,/g, "");

      // 공제자/지급자: data-* 에서 읽음
      const dedName = (tr.dataset.dedName || "").trim();
      const dedId   = (tr.dataset.dedId   || "").trim();
      const payName = (tr.dataset.payName || "").trim();
      const payId   = (tr.dataset.payId   || "").trim();

      if (!startYm || !endYm)
        throw new Error(`${i + 1}번 행: 시작월도와 종료월도는 필수입니다.`);
      if (startYm > endYm)
        throw new Error(`${i + 1}번 행: 종료월도는 시작월도 이후여야 합니다.`);
      if (!dedId)
        throw new Error(`${i + 1}번 행: 공제자를 검색하여 선택해 주세요.`);
      if (!payId)
        throw new Error(`${i + 1}번 행: 지급자를 검색하여 선택해 주세요.`);

      const amount = amountRaw ? parseInt(amountRaw, 10) : null;
      if (amountRaw && isNaN(amount))
        throw new Error(`${i + 1}번 행: 금액이 올바르지 않습니다.`);

      rows.push({
        start_ym: startYm,
        end_ym:   endYm,
        category: get("category"),
        amount:   amount,
        ded_name: dedName,
        ded_id:   dedId,
        pay_name: payName,
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

    tbody?.addEventListener("click",  handleDeleteRow);
    tbody?.addEventListener("blur",   handleAmountBlur, true);

    // ── 검색 버튼 클릭 감지 (capture — btnOpenSearch 클릭 전 role 기억)
    document.addEventListener("click", handleSearchBtnCapture, true);

    // ── userSelected 이벤트 수신 (search_user_modal.js가 발행)
    document.addEventListener("userSelected", handleUserSelected);

    updateRowCount();
  }

  return { bindEvents, addRow, clearRows, save, updateRowCount };
})();