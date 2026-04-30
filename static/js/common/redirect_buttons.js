/**
 * button[data-redirect-url] 클릭 시 해당 URL로 이동.
 * inline onclick 제거용 공통 유틸.
 */
document.addEventListener("click", function (event) {
  const btn = event.target?.closest?.("[data-redirect-url]");
  if (!btn) return;

  const url = btn.dataset.redirectUrl || "";
  if (url) window.location.href = url;
});