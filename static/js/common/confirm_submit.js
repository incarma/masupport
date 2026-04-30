/**
 * form[data-confirm-submit] submit 시 confirm 처리.
 * inline onsubmit 제거용 공통 유틸.
 */
document.addEventListener("submit", function (event) {
  const form = event.target;
  if (!form?.matches?.("form[data-confirm-submit]")) return;

  const message = form.dataset.confirmSubmit || "정말 진행하시겠습니까?";
  if (!window.confirm(message)) {
    event.preventDefault();
  }
});