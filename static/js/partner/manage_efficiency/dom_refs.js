// django_ma/static/js/partner/manage_efficiency/dom_refs.js
// =========================================================
// ✅ DOM references (Manage Efficiency)
// - get 접근자 패턴: BFCache 복원 후 stale DOM 참조 방지
// - 페이지별 element id 기반으로 안전 참조
// =========================================================

export const els = {
  // root
  get root()  { return document.getElementById("manage-efficiency"); },

  // top controls
  get year()  { return document.getElementById("yearSelect"); },
  get month() { return document.getElementById("monthSelect"); },
  get branch() { return document.getElementById("branchSelect"); }, // superuser only
  get btnSearch() { return document.getElementById("btnSearchPeriod"); },

  // sections
  get inputSection() { return document.getElementById("inputSection"); },
  get mainSheet()    { return document.getElementById("mainSheet"); },

  // input actions
  get btnAddRow()    { return document.getElementById("btnAddRow"); },
  get btnResetRows() { return document.getElementById("btnResetRows"); },
  get btnSaveRows()  { return document.getElementById("btnSaveRows"); },
  get inputTable()   { return document.getElementById("inputTable"); },

  // accordion container
  get accordion()   { return document.getElementById("confirmGroupsAccordion"); },
  get sheetNotice() { return document.getElementById("sheetNotice"); },

  // loading
  get loading() { return document.getElementById("loadingOverlay"); },

  // confirm upload (modal)
  get btnConfirmUploadDo() { return document.getElementById("btnConfirmUploadDo"); },
  get confirmFileInput()   { return document.getElementById("confirmFileInput"); },
  get confirmFileName()    { return document.getElementById("confirmFileName"); },

  // ✅ NEW: group id hidden
  get confirmGroupId() { return document.getElementById("confirmGroupId"); },

  // legacy
  get confirmAttachmentId() { return document.getElementById("confirmAttachmentId"); },
};
