// static/js/partner/esign_confirm/dom_refs.js
// DOM 참조 중앙화 — index.js / fetch.js / save.js / sign.js 모두 이 파일을 통해 DOM 접근
// Playbook: id/class 변경 시 이 파일 1곳만 수정하면 됨

"use strict";

window.EsignDom = (function () {
  const $ = (id) => document.getElementById(id);

  return {
    // ── Root ──────────────────────────────────────────
    root:        ()  => $("esign-confirm"),

    // ── Controls ──────────────────────────────────────
    yearSelect:  ()  => $("yearSelect"),
    monthSelect: ()  => $("monthSelect"),
    partSelect:  ()  => $("partSelect"),
    branchSelect:()  => $("branchSelect"),
    btnSearch:   ()  => $("btnSearch"),

    // ── InputSection ──────────────────────────────────
    inputSection:()  => $("inputSection"),
    inputTbody:  ()  => $("inputTbody"),
    btnAddRow:   ()  => $("btnAddRow"),
    btnClearRows:()  => $("btnClearRows"),
    btnSave:     ()  => $("btnSave"),
    rowCountMsg: ()  => $("rowCountMsg"),

    // ── MainSheet / Accordion ─────────────────────────
    mainSheet:   ()  => $("mainSheet"),
    accordion:   ()  => $("confirmGroupsAccordion"),
    loadingMsg:  ()  => $("esignLoadingMsg"),
    emptyMsg:    ()  => $("esignEmptyMsg"),

    // ── Sign Modal ────────────────────────────────────
    signModal:        () => $("esignSignModal"),
    signModalTitle:   () => $("signModalTitle"),
    signModalMonth:   () => $("signModalMonth"),
    signModalTbody:   () => $("signModalTbody"),
    signModalSigners: () => $("signModalSigners"),
    signAgreementCheck: () => $("signAgreementCheck"),
    btnDoSign:        () => $("btnDoSign"),
  };
})();