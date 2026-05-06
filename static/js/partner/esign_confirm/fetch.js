// static/js/partner/esign_confirm/fetch.js
// 데이터 조회 + 아코디언 렌더링

"use strict";

window.EsignFetch = (function () {
  let _lastGroups = [];

  // ─── 유틸 ────────────────────────────────────────────────────
  function fmtAmount(v) {
    if (!v && v !== 0) return "";
    return Number(v).toLocaleString("ko-KR") + "원";
  }
  function fmtDate(s) {
    return s ? s.replace("T", " ").substring(0, 16) : "—";
  }
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ─── 상태 배지 ───────────────────────────────────────────────
  function badgeHtml(signStatus, mySignStatus) {
    if (signStatus === "completed") {
      return '<span class="badge esign-badge esign-badge--completed">서명 완료</span>';
    }
    if (mySignStatus === "unsigned") {
      return '<span class="badge esign-badge esign-badge--pending">서명 필요</span>';
    }
    if (signStatus === "partial") {
      return '<span class="badge esign-badge esign-badge--partial">서명 진행중</span>';
    }
    return '<span class="badge esign-badge esign-badge--pending">서명 대기</span>';
  }

  // ─── 서명하기 버튼 ───────────────────────────────────────────
  function signBtnHtml(group) {
    if (group.my_sign_status !== "unsigned") return "";
    return `
      <button type="button"
              class="btn btn-warning btn-sm js-esign-sign-btn"
              data-request-id="${group.sign_request_id}"
              data-sign-id="${group.my_sign_id}"
              title="서명하기">
        ✍️ 서명하기
      </button>`;
  }

  // ─── 확인서 보기 버튼 ─────────────────────────────────────────
  // 서명 미완료 시: 버튼은 항상 표시하되 disabled + 안내 메시지
  function pdfBtnHtml(group) {
    const ready    = group.pdf_ready;
    const disabled = ready ? "" : "disabled";
    const tooltip  = ready
      ? ""
      : 'title="모든 대상자의 서명이 완료되어야 확인서 생성이 가능합니다"';
    return `
      <button type="button"
              class="btn btn-outline-success btn-sm js-esign-pdf-btn"
              data-request-id="${group.sign_request_id}"
              data-pdf-ready="${ready}"
              ${disabled} ${tooltip}>
        확인서 보기
      </button>`;
  }

  // ─── 삭제 버튼 (superuser/head: 모든 상태 삭제 가능) ─────────
  function deleteBtnHtml(group, canDelete) {
    if (!canDelete) return "";
    const isCompleted = group.sign_status === "completed";
    const btnClass    = isCompleted
      ? "btn btn-danger btn-sm js-esign-delete-btn"
      : "btn btn-outline-danger btn-sm js-esign-delete-btn";
    const tooltip     = isCompleted
      ? 'title="⚠️ 서명 완료된 확인서입니다. 삭제 시 복구 불가"'
      : 'title="삭제"';
    return `
      <button type="button"
              class="${btnClass}"
              data-request-id="${group.sign_request_id}"
              data-group-id="${esc(group.confirm_group_id)}"
              data-sign-status="${group.sign_status}"
              ${tooltip}>
        삭제
      </button>`;
  }

  // ─── 세부 테이블 (아코디언 body) — 처리일시 컬럼 포함 ────────
  function detailTableHtml(group, canProcessDate) {
    const rows = group.rows || [];
    if (!rows.length) return '<p class="text-muted px-3 py-2">데이터가 없습니다.</p>';

    const trs = rows.map((r, i) => {
      // 처리일시 셀: superuser/head는 date input, 나머지는 텍스트
      let processDateCell;
      if (canProcessDate) {
        processDateCell = `
          <td class="text-center">
            <input type="date"
                   class="form-control form-control-sm js-process-date-input"
                   data-row-id="${r.id}"
                   value="${esc(r.process_date || '')}"
                   style="min-width:120px; font-size:11px;">
          </td>`;
      } else {
        processDateCell = `<td class="text-center">${r.process_date ? esc(r.process_date) : "—"}</td>`;
      }

      return `
        <tr>
          <td class="text-center">${i + 1}</td>
          <td>${esc(r.requester_name)} <small class="text-muted">${esc(r.requester_id)}</small></td>
          <td class="text-center">${esc(r.start_ym)}</td>
          <td class="text-center">${esc(r.end_ym)}</td>
          <td class="text-center">${esc(r.category)}</td>
          <td class="text-end">${fmtAmount(r.amount)}</td>
          <td>${esc(r.ded_name)} <small class="text-muted">${esc(r.ded_id)}</small></td>
          <td>${esc(r.pay_name)} <small class="text-muted">${esc(r.pay_id)}</small></td>
          <td title="${esc(r.content)}">${esc(r.content)}</td>
          <td class="text-center">${r.signed_at ? fmtDate(r.signed_at) : "—"}</td>
          ${processDateCell}
        </tr>`;
    }).join("");

    // 처리일시 저장 버튼 (superuser/head만)
    const saveDateBtnHtml = canProcessDate ? `
      <div class="mt-2 px-1">
        <button type="button"
                class="btn btn-outline-primary btn-sm js-save-process-dates-btn"
                data-request-id="${group.sign_request_id}">
          처리일시 저장
        </button>
      </div>` : "";

    return `
      <table class="table table-sm table-bordered main-group-table mb-0">
        <colgroup>
          <col style="width:40px">
          <col style="width:130px">
          <col style="width:80px">
          <col style="width:80px">
          <col style="width:80px">
          <col style="width:110px">
          <col style="width:130px">
          <col style="width:130px">
          <col>
          <col style="width:120px">
          <col style="width:130px">
        </colgroup>
        <thead class="table-light">
          <tr>
            <th class="text-center">번호</th>
            <th>요청자</th>
            <th class="text-center">시작월</th>
            <th class="text-center">종료월</th>
            <th class="text-center">구분</th>
            <th class="text-end">금액</th>
            <th>공제자</th>
            <th>지급자</th>
            <th>내용</th>
            <th class="text-center">서명일시</th>
            <th class="text-center">처리일시</th>
          </tr>
        </thead>
        <tbody>${trs}</tbody>
      </table>
      ${saveDateBtnHtml}`;
  }

  // ─── 서명자 현황 테이블 ──────────────────────────────────────
  function signerTableHtml(signers) {
    if (!signers || !signers.length) return "";
    const roleLabel = { deduct: "공제자", pay: "지급자", head_confirm: "확인자" };
    const rows = signers.map(s => `
      <tr>
        <td>${esc(roleLabel[s.role] || s.role)}</td>
        <td>${esc(s.signer_name)} <small class="text-muted">${esc(s.signer_id)}</small></td>
        <td class="text-center">
          ${s.signed
            ? `<span class="badge bg-success">✅ ${fmtDate(s.signed_at)}</span>`
            : '<span class="badge bg-secondary">미서명</span>'}
        </td>
      </tr>`).join("");
    return `
      <table class="table table-sm signer-list mb-0">
        <thead class="table-light">
          <tr><th>역할</th><th>서명자</th><th class="text-center">서명 여부</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ─── 아코디언 아이템 렌더 ────────────────────────────────────
  function renderAccordionItem(group, idx, canDelete, canProcessDate) {
    const collapseId = `esignCollapse${group.sign_request_id}`;
    const headerId   = `esignHeader${group.sign_request_id}`;
    const totalAmt   = (group.rows || []).reduce((s, r) => s + (r.amount || 0), 0);

    return `
      <div class="accordion-item mb-2"
           data-request-id="${group.sign_request_id}"
           data-sign-status="${esc(group.sign_status)}">
        <h2 class="accordion-header" id="${headerId}">
          <div class="eff-acc-head">
            <button class="accordion-button collapsed eff-acc-toggle"
                    type="button"
                    data-bs-toggle="collapse"
                    data-bs-target="#${collapseId}"
                    aria-expanded="false"
                    aria-controls="${collapseId}">
              <div class="eff-group-scroll">
                <span class="eff-group-title">${esc(group.title || group.branch)}</span>
                <span class="eff-group-sub">${group.row_count}건 / ${fmtAmount(totalAmt)}</span>
              </div>
            </button>
            <div class="esign-status-area">
              ${badgeHtml(group.sign_status, group.my_sign_status)}
              ${signBtnHtml(group)}
              ${pdfBtnHtml(group)}
              ${deleteBtnHtml(group, canDelete)}
            </div>
          </div>
        </h2>
        <div id="${collapseId}"
             class="accordion-collapse collapse"
             aria-labelledby="${headerId}">
          <div class="accordion-body">
            ${detailTableHtml(group, canProcessDate)}
            <div class="mt-2 px-1">
              ${signerTableHtml(group.signers)}
            </div>
          </div>
        </div>
      </div>`;
  }

  // ─── 처리일시 저장 (이벤트 위임) ─────────────────────────────
  async function handleSaveProcessDates(e) {
    const btn = e.target.closest(".js-save-process-dates-btn");
    if (!btn) return;

    const root       = window.EsignDom.root();
    const saveUrl    = root?.dataset?.processDateUrl;
    if (!saveUrl) { alert("처리일시 저장 URL이 설정되지 않았습니다."); return; }

    const accordionItem = btn.closest(".accordion-item");
    const inputs = accordionItem?.querySelectorAll(".js-process-date-input") || [];

    const updates = [];
    inputs.forEach(input => {
      const rowId = input.dataset.rowId;
      const val   = (input.value || "").trim();
      if (rowId) updates.push({ row_id: rowId, process_date: val || null });
    });

    if (!updates.length) { alert("저장할 행이 없습니다."); return; }

    btn.disabled    = true;
    btn.textContent = "저장 중...";

    try {
      const res = await fetch(saveUrl, {
        method:      "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type":     "application/json",
          "X-CSRFToken":      window.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ updates }),
      });
      const data = await res.json();
      if (data.status !== "success") {
        alert(data.message || "처리일시 저장에 실패했습니다.");
        return;
      }
      alert(`처리일시가 저장되었습니다. (${data.updated_count}건)`);
    } catch (err) {
      console.error("[EsignFetch] handleSaveProcessDates error:", err);
      alert("처리일시 저장 중 오류가 발생했습니다.");
    } finally {
      btn.disabled    = false;
      btn.textContent = "처리일시 저장";
    }
  }

  // ─── 확인서 보기 disabled 버튼 클릭 안내 ─────────────────────
  function handlePdfDisabledClick(e) {
    const btn = e.target.closest(".js-esign-pdf-btn");
    if (!btn) return;
    if (!btn.disabled && btn.dataset.pdfReady !== "false") return;
    // disabled 상태에서 클릭한 경우
    e.preventDefault();
    e.stopImmediatePropagation();
    alert("모든 대상자의 서명이 완료되어야 확인서 생성이 가능합니다.");
  }

  // ─── 메인 fetchData ──────────────────────────────────────────
  async function fetchData() {
    const dom  = window.EsignDom;
    const root = dom.root();
    if (!root) return;

    const ds           = root.dataset;
    const grade        = ds.userGrade || "";
    const canDel       = ds.canDelete === "true";
    const canProcDate  = ds.canProcessDate === "true";

    const year    = dom.yearSelect()?.value    || "";
    const month   = dom.monthSelect()?.value   || "";
    const channel = dom.channelSelect()?.value || "";
    const ym      = year && month ? `${year}-${month.padStart(2, "0")}` : "";
    const branch  = (grade === "superuser")
      ? (dom.branchSelect()?.value || "")
      : (ds.userBranch || "");

    const url = new URL(ds.fetchUrl, location.origin);
    if (ym)      url.searchParams.set("month",   ym);
    if (branch)  url.searchParams.set("branch",  branch);
    if (channel) url.searchParams.set("channel", channel);

    const accordion  = dom.accordion();
    const loadingMsg = dom.loadingMsg();
    const emptyMsg   = dom.emptyMsg();

    accordion.innerHTML = "";
    emptyMsg.hidden     = true;
    loadingMsg.hidden   = false;

    try {
      const res = await fetch(url.toString(), {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const groups = data.groups || [];
      _lastGroups  = groups;

      loadingMsg.hidden = true;

      if (!groups.length) {
        emptyMsg.hidden = false;
        return;
      }

      accordion.innerHTML = groups
        .map((g, i) => renderAccordionItem(g, i, canDel, canProcDate))
        .join("");

    } catch (err) {
      loadingMsg.hidden = true;
      accordion.innerHTML = `
        <div class="alert alert-danger">
          데이터를 불러오지 못했습니다: ${esc(err.message)}
        </div>`;
      console.error("[EsignFetch] fetchData error:", err);
    }
  }

  // ─── 이벤트 바인딩 (accordion 이벤트 위임) ───────────────────
  function bindAccordionEvents() {
    const accordion = window.EsignDom.accordion();
    if (!accordion) return;
    // 처리일시 저장 버튼
    accordion.addEventListener("click", handleSaveProcessDates);
    // 확인서 보기 disabled 안내 (capture 필요 — disabled 버튼은 click 버블링 안 됨)
    accordion.addEventListener("click", handlePdfDisabledClick, true);
  }

  return { fetchData, getLastGroups: () => _lastGroups, bindAccordionEvents };
})();