// static/js/partner/esign_confirm/index.js
// Boot 진입점 — manage_efficiency/index.js 패턴 준수
// Playbook: dataset 기반 Boot, BFCache 재진입 중복 방지, grade별 autoLoad

"use strict";

(function () {
  // ── 중복 실행 방지 (BFCache / pageshow 재진입) ───────────────
  const GUARD_KEY = "__esignConfirmInited";

  function init() {
    const root = document.getElementById("esign-confirm");
    if (!root) return;

    if (root[GUARD_KEY]) return;
    root[GUARD_KEY] = true;

    const ds    = root.dataset;
    const grade = ds.userGrade || "basic";

    // ── year/month 셀렉트 초기화 (manage_boot 패턴) ──────────
    if (typeof window.ManageBoot !== "undefined") {
      // manage_boot.js가 있으면 위임
      window.ManageBoot.init("esign-confirm");
    } else {
      _initYearMonth(root);
    }

    // ── superuser: part/branch 셀렉터 로드 ───────────────────
    if (grade === "superuser" && typeof window.loadPartsAndBranches === "function") {
      window.loadPartsAndBranches("esign-confirm").catch(console.error);
    } else {
      // head/leader/basic: branch 고정 (dataset에서 읽음)
      const branchSel = document.getElementById("branchSelect");
      const partSel   = document.getElementById("partSelect");
      const userBranch = ds.userBranch || "";
      const userPart   = ds.userPart   || "";

      if (branchSel && userBranch) {
        branchSel.innerHTML = `<option value="${_esc(userBranch)}">${_esc(userBranch)}</option>`;
        branchSel.disabled  = true;
      }
      if (partSel && userPart) {
        partSel.innerHTML = `<option value="${_esc(userPart)}">${_esc(userPart)}</option>`;
        partSel.disabled  = true;
      }
    }

    // ── 이벤트 바인딩 ────────────────────────────────────────
    _bindSearchBtn();

    // save.js 바인딩 (내용입력 카드가 있을 때만)
    if (ds.canInput === "true") {
      window.EsignSave?.bindEvents();
    }

    // sign.js 바인딩
    window.EsignSign?.bindEvents();

    // ── autoLoad: head/leader/basic (branch 고정이므로 즉시 조회) ─
    if (grade !== "superuser") {
      window.EsignFetch?.fetchData();
    }

    // ── inputSection 표시 ────────────────────────────────────
    if (ds.canInput === "true") {
      document.getElementById("inputSection")?.removeAttribute("hidden");
    }
    document.getElementById("mainSheet")?.removeAttribute("hidden");

    console.log("[EsignConfirm] init complete. grade=", grade);
  }

  // ── year/month 셀렉트 수동 초기화 (manage_boot 없을 때 폴백) ─
  function _initYearMonth(root) {
    const now = new Date();
    const y   = now.getFullYear();
    const m   = now.getMonth() + 1;

    const yearSel  = document.getElementById("yearSelect");
    const monthSel = document.getElementById("monthSelect");

    if (yearSel && !yearSel.options.length) {
      for (let yy = y - 2; yy <= y + 1; yy++) {
        yearSel.appendChild(new Option(`${yy}년`, String(yy)));
      }
      yearSel.value = String(y);
    }
    if (monthSel && !monthSel.options.length) {
      for (let mm = 1; mm <= 12; mm++) {
        monthSel.appendChild(new Option(`${mm}월`, String(mm)));
      }
      monthSel.value = String(m);
    }
  }

  // ── 조회 버튼 바인딩 ────────────────────────────────────────
  function _bindSearchBtn() {
    const btn    = document.getElementById("btnSearch");
    const root   = document.getElementById("esign-confirm");
    const grade  = root?.dataset.userGrade || "basic";

    if (!btn) return;

    // superuser: branch 선택 후 활성화 (part_branch_selector.js가 처리)
    // 나머지: 항상 활성
    if (grade !== "superuser") {
      btn.disabled = false;
    }

    btn.addEventListener("click", () => {
      window.EsignFetch?.fetchData();
    });
  }

  function _esc(s) {
    return String(s ?? "").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── 진입점 ──────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // BFCache 재진입 대응
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
      const root = document.getElementById("esign-confirm");
      if (root) root[GUARD_KEY] = false;
      init();
    }
  });
})();