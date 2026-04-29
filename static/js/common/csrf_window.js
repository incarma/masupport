/**
 * django_ma/static/js/common/csrf_window.js
 * ------------------------------------------------------------
 * 목적:
 * - 기존 레거시 JS가 window.csrfToken을 참조하는 구조를 유지한다.
 * - inline script로 window.csrfToken을 주입하던 방식을 제거한다.
 *
 * 우선순위:
 * 1) form/input의 csrfmiddlewaretoken
 * 2) csrftoken cookie
 *
 * 신규 코드 권장:
 * - static/js/common/manage/csrf.js 의 getCSRFToken() 사용
 */
(function () {
  const inputToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const cookieToken = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
  const token = inputToken || cookieToken;

  if (!token) return;

  try {
    window.csrfToken = decodeURIComponent(token);
  } catch (_) {
    window.csrfToken = token;
  }
})();