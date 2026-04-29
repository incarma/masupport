/**
 * django_ma/static/js/common/prevent_form_submit.js
 * ------------------------------------------------------------
 * 목적:
 * - form의 inline onsubmit="return false;" 제거.
 * - data-prevent-submit="true"가 붙은 form만 submit 기본 동작을 차단한다.
 *
 * 사용 예:
 * <form id="controlsForm" data-prevent-submit="true">
 *
 * 적용 대상:
 * - 버튼 클릭/AJAX 기반 컨트롤 폼
 * - Enter 키로 의도치 않은 reload가 발생하면 안 되는 폼
 */
document.addEventListener("submit", function (event) {
  const form = event.target;

  if (!form?.matches?.('form[data-prevent-submit="true"]')) return;

  event.preventDefault();
});