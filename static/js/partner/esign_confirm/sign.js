// static/js/partner/esign_confirm/sign.js
// 서명하기 모달 핸들러 + PDF 다운로드
// Playbook: 이벤트 위임으로 아코디언 동적 렌더 후 버튼에도 동작 보장

"use strict";

window.EsignSign = (function () {

  let _modalInstance = null;

  // ── Bootstrap Modal 인스턴스 (지연 생성) ─────────────────────
  function getModal() {
    if (_modalInstance) return _modalInstance;
    const el = window.EsignDom.signModal();
    if (!el) return null;
    _modalInstance = bootstrap.Modal.getOrCreateInstance(el);
    return _modalInstance;
  }

  // ── XSS 방어용 이스케이프 ────────────────────────────────────
  function _esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── 서명하기 버튼 클릭 (아코디언 이벤트 위임) ───────────────
  function handleSignBtnClick(e) {
    const btn = e.target.closest(".js-esign-sign-btn");
    if (!btn) return;

    const requestId = btn.dataset.requestId;
    if (!requestId) return;

    const groups = window.EsignFetch.getLastGroups();
    const group  = groups.find(g => String(g.sign_request_id) === String(requestId));
    if (!group) {
      alert("서명 정보를 찾을 수 없습니다. 페이지를 새로고침해 주세요.");
      return;
    }

    _openSignModal(group);
  }

  // ── 모달 열기 ────────────────────────────────────────────────
  function _openSignModal(group) {
    const dom = window.EsignDom;

    // 모달 제목/월도 주입
    const titleEl = dom.signModalTitle();
    const monthEl = dom.signModalMonth();
    if (titleEl) titleEl.textContent = group.title || `${group.branch} / ${group.month}`;
    if (monthEl) monthEl.textContent = group.month || "";

    // 내역 테이블 렌더
    const tbody = dom.signModalTbody();
    if (tbody) {
      if (!group.rows || !group.rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">데이터 없음</td></tr>';
      } else {
        tbody.innerHTML = group.rows.map((r, i) => `
          <tr>
            <td class="text-center">${i + 1}</td>
            <td class="text-center">${_esc(r.start_ym)}</td>
            <td class="text-center">${_esc(r.end_ym)}</td>
            <td class="text-end">${r.amount ? Number(r.amount).toLocaleString("ko-KR") + "원" : "—"}</td>
            <td>${_esc(r.ded_name)} <small class="text-muted">${_esc(r.ded_id)}</small></td>
            <td>${_esc(r.pay_name)} <small class="text-muted">${_esc(r.pay_id)}</small></td>
            <td title="${_esc(r.content)}">${_esc(r.content)}</td>
          </tr>`).join("");
      }
    }

    // 서명 현황 렌더
    const signersEl = dom.signModalSigners();
    if (signersEl) {
      const roleLabel = { deduct: "공제자", pay: "지급자", head_confirm: "확인자" };
      signersEl.innerHTML = (group.signers || []).map(s => `
        <span class="badge ${s.signed ? "bg-success" : "bg-secondary"} px-2 py-1" style="font-size:12px;">
          ${_esc(roleLabel[s.role] || s.role)}: ${_esc(s.signer_name)}
          ${s.signed ? "✅" : "⏳"}
        </span>`).join("");
    }

    // 동의 체크 + 버튼 초기화
    const check     = dom.signAgreementCheck();
    const doSignBtn = dom.btnDoSign();
    if (check)      check.checked   = false;
    if (doSignBtn)  doSignBtn.disabled = true;

    // 동의 체크 → 버튼 활성화 (리스너 교체)
    if (check && doSignBtn) {
      const listener = () => { doSignBtn.disabled = !check.checked; };
      check.removeEventListener("change", check._esignListener);
      check._esignListener = listener;
      check.addEventListener("change", listener);
    }

    // 서명 버튼에 requestId 주입
    if (doSignBtn) doSignBtn.dataset.requestId = group.sign_request_id;

    getModal()?.show();
  }

  // ── 서명 실행 ────────────────────────────────────────────────
  async function handleDoSign() {
    const dom       = window.EsignDom;
    const doSignBtn = dom.btnDoSign();
    const requestId = doSignBtn?.dataset.requestId;
    if (!requestId) return;

    const root    = dom.root();
    const signUrl = (root?.dataset.signUrlTemplate || "").replace("{id}", requestId);
    if (!signUrl) { alert("서명 URL이 설정되지 않았습니다."); return; }

    doSignBtn.disabled    = true;
    doSignBtn.textContent = "서명 처리 중...";

    try {
      const res = await fetch(signUrl, {
        method:      "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type":     "application/json",
          "X-CSRFToken":      window.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
      const data = await res.json();

      if (data.status !== "success") {
        alert(data.message || "서명 처리에 실패했습니다.");
        return;
      }

      getModal()?.hide();

      if (data.all_signed) {
        alert("서명이 완료되었습니다! 확인서 PDF가 생성됩니다.");
      } else {
        alert(`서명 완료 (${data.signed_at}). 나머지 서명자의 서명을 기다리고 있습니다.`);
      }

      // 아코디언 재조회
      await window.EsignFetch.fetchData();

    } catch (err) {
      console.error("[EsignSign] handleDoSign error:", err);
      alert("서명 처리 중 오류가 발생했습니다.");
    } finally {
      doSignBtn.disabled    = false;
      doSignBtn.textContent = "✍️ 서명하기";
    }
  }

  // ── PDF 다운로드 버튼 ────────────────────────────────────────
  function handlePdfBtnClick(e) {
    const btn = e.target.closest(".js-esign-pdf-btn");
    if (!btn) return;

    if (btn.disabled || btn.dataset.pdfReady === "false") {
      alert("서명이 완료되면 다운로드 가능합니다.");
      return;
    }

    const requestId = btn.dataset.requestId;
    const root      = window.EsignDom.root();
    const url       = (root?.dataset.pdfUrlTemplate || "").replace("{id}", requestId);
    if (!url) { alert("PDF URL이 설정되지 않았습니다."); return; }

    window.location.href = url;
  }

  // ── 삭제 버튼 ────────────────────────────────────────────────
  async function handleDeleteBtnClick(e) {
    const btn = e.target.closest(".js-esign-delete-btn");
    if (!btn) return;

    const requestId  = btn.dataset.requestId;
    const signStatus = btn.dataset.signStatus || "";
    const isCompleted = signStatus === "completed";
    const confirmMsg  = isCompleted
      ? "⚠️ 서명이 완료된 확인서입니다.\n삭제하면 PDF를 포함한 모든 서명 기록이 영구 삭제됩니다.\n\n정말 삭제하시겠습니까?"
      : "확인서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.";
    if (!confirm(confirmMsg)) return;

    const root      = window.EsignDom.root();
    const deleteUrl = root?.dataset.deleteGroupUrl;
    if (!deleteUrl) { alert("삭제 URL이 설정되지 않았습니다."); return; }

    btn.disabled = true;

    try {
      const res = await fetch(deleteUrl, {
        method:      "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type":     "application/json",
          "X-CSRFToken":      window.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ sign_request_id: requestId }),
      });
      if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
      const data = await res.json();
      if (data.status !== "success") {
        alert(data.message || "삭제에 실패했습니다.");
        return;
      }

      await window.EsignFetch.fetchData();

    } catch (err) {
      console.error("[EsignSign] handleDeleteBtnClick error:", err);
      alert("삭제 중 오류가 발생했습니다.");
    } finally {
      btn.disabled = false;
    }
  }

  // ── 이벤트 바인딩 ────────────────────────────────────────────
  function bindEvents() {
    const accordion = window.EsignDom.accordion();
    const doSignBtn = window.EsignDom.btnDoSign();

    // 아코디언 이벤트 위임 (동적 렌더 대응)
    accordion?.addEventListener("click", handleSignBtnClick);
    accordion?.addEventListener("click", handlePdfBtnClick);
    accordion?.addEventListener("click", handleDeleteBtnClick);

    // 서명하기 버튼 (모달 내부 — 정적 DOM)
    doSignBtn?.addEventListener("click", handleDoSign);
  }

  return { bindEvents };
})();