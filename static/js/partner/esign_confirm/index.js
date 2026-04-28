// static/js/partner/esign_confirm/index.js
// Boot 진입점 — manage_boot.js 의존 없이 독립 동작
// Playbook: dataset 기반 Boot, BFCache 재진입 중복 방지, grade별 autoLoad

"use strict";

(function () {
  const GUARD_KEY = "__esignConfirmInited";

  // ── 연/월 셀렉트 직접 초기화 ────────────────────────────────
  function _initYearMonth() {
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
        monthSel.appendChild(new Option(`${String(mm).padStart(2, "0")}월`, String(mm)));
      }
      monthSel.value = String(m);
    }
  }

  // ── XSS 방어용 이스케이프 ────────────────────────────────────
  function _esc(s) {
    return String(s ?? "").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── 조회 버튼 바인딩 ────────────────────────────────────────
  function _bindSearchBtn(grade) {
    const btn = document.getElementById("btnSearch");
    if (!btn) return;

    // superuser 이외: 항상 활성화 (branch 고정)
    if (grade !== "superuser") {
      btn.disabled = false;
    }
    // superuser: part_branch_selector.js가 branch 선택 후 활성화 처리

    btn.addEventListener("click", () => {
      window.EsignFetch?.fetchData();
    });
  }

  // ── 메인 init ────────────────────────────────────────────────
  function init() {
    const root = document.getElementById("esign-confirm");
    if (!root) return;

    // BFCache 재진입 중복 방지
    if (root[GUARD_KEY]) return;
    root[GUARD_KEY] = true;

    const ds    = root.dataset;
    const grade = ds.userGrade || "basic";

    // ── 연/월 셀렉트 초기화 ──────────────────────────────────
    _initYearMonth();

    // ── 부서/지점 셀렉터 ─────────────────────────────────────
    if (grade === "superuser") {
      // part_branch_selector.js에 위임 (manage_boot 패턴과 동일)
      if (typeof window.loadPartsAndBranches === "function") {
        window.loadPartsAndBranches("esign-confirm").catch(console.error);
      } else {
        // part_branch_selector 아직 로드 안 됐을 경우 대기
        const MAX_RETRY = 10;
        let retry = 0;
        const timer = setInterval(() => {
          if (typeof window.loadPartsAndBranches === "function") {
            clearInterval(timer);
            window.loadPartsAndBranches("esign-confirm").catch(console.error);
          } else if (++retry >= MAX_RETRY) {
            clearInterval(timer);
            console.warn("[EsignConfirm] loadPartsAndBranches 로드 실패");
          }
        }, 200);
      }
    } else {
      // head / leader / basic: branch/part 고정
      const branchSel = document.getElementById("branchSelect");
      const partSel   = document.getElementById("partSelect");

      if (branchSel && ds.userBranch) {
        branchSel.innerHTML = `<option value="${_esc(ds.userBranch)}">${_esc(ds.userBranch)}</option>`;
        branchSel.disabled  = true;
      }
      if (partSel && ds.userPart) {
        partSel.innerHTML = `<option value="${_esc(ds.userPart)}">${_esc(ds.userPart)}</option>`;
        partSel.disabled  = true;
      }
    }

    // ── 조회 버튼 바인딩 ────────────────────────────────────
    _bindSearchBtn(grade);

    // ── save.js 바인딩 (내용입력 카드가 있을 때만) ───────────
    if (ds.canInput === "true") {
      window.EsignSave?.bindEvents();
    }

    // ── sign.js 바인딩 ───────────────────────────────────────
    window.EsignSign?.bindEvents();

    // ── fetch.js 아코디언 이벤트 위임 바인딩 ─────────────────
    window.EsignFetch?.bindAccordionEvents();

    // ── autoLoad: superuser 외 (branch 고정 → 즉시 조회) ────
    if (grade !== "superuser") {
      window.EsignFetch?.fetchData();
    }

    console.log("[EsignConfirm] init complete. grade=", grade);
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