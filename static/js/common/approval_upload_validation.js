/**
 * django_ma/static/js/commission/approval_upload_validation.js
 * ------------------------------------------------------------
 * 목적:
 * - commission/_approval_upload_modal.html 내부 inline script 제거.
 * - Bootstrap validation 표시만 담당한다.
 *
 * 역할 분리:
 * - 이 파일: checkValidity 실패 시 submit 차단 + was-validated class 부여
 * - approval_excel_upload.js: 실제 업로드, 중복 제출 방지, 결과 표시 담당
 *
 * DOM 계약:
 * - form#approvalUploadForm
 */
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("approvalUploadForm");
  if (!form) return;

  form.addEventListener(
    "submit",
    function (event) {
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
      }

      form.classList.add("was-validated");
    },
    { passive: false }
  );
});