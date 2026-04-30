/**
 * select[data-auto-submit="true"] 변경 시 소속 form submit.
 * inline onchange 제거용 공통 유틸.
 */
document.addEventListener("change", function (event) {
  const el = event.target;
  if (!el?.matches?.('select[data-auto-submit="true"]')) return;

  const form = el.form;
  if (form) form.submit();
});