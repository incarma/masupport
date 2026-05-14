/**
 * login_recaptcha.js
 * /login/ 페이지 전용 reCAPTCHA v3 토큰 주입
 *
 * 규약:
 * - BFCache 가드: document.body.dataset.recaptchaInited
 * - 사이트 키: .login-card-wrap[data-recaptcha-site-key] (템플릿 주입)
 * - fail-open: grecaptcha 미로드 또는 execute 실패 시 그냥 제출
 * - CSRF: 기존 django CSRF 폼 처리에 영향 없음
 */
(function () {
  "use strict";

  if (document.body.dataset.recaptchaInited === "1") return;
  document.body.dataset.recaptchaInited = "1";

  const container = document.querySelector(".login-card-wrap");
  const siteKey = ((container && container.dataset.recaptchaSiteKey) || "").trim();
  if (!siteKey) return;

  const form = document.getElementById("loginForm");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    if (typeof grecaptcha === "undefined") {
      form.submit();
      return;
    }

    grecaptcha.ready(function () {
      grecaptcha
        .execute(siteKey, { action: "login" })
        .then(function (token) {
          var input = form.querySelector('input[name="g-recaptcha-response"]');
          if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = "g-recaptcha-response";
            form.appendChild(input);
          }
          input.value = token;
          form.submit();
        })
        .catch(function () {
          form.submit();
        });
    });
  });
})();
