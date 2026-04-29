/**
 * django_ma/static/js/common/json_boot_bridge.js
 * ------------------------------------------------------------
 * 목적:
 * - Django json_script로 안전하게 렌더링한 JSON 데이터를
 *   기존 레거시 JS가 기대하는 window 전역 변수로 연결한다.
 *
 * 사용 예:
 * <script
 *   src="{% static 'js/common/json_boot_bridge.js' %}"
 *   data-json-id="boot-efficiency"
 *   data-window-name="ManageefficiencyBoot">
 * </script>
 *
 * 설계 원칙:
 * - inline <script> 제거(CSP script-src 'self' 대응)
 * - 기존 window.Manage*Boot / window.currentUser 의존성 유지
 * - JSON parse 실패가 페이지 전체를 깨지 않도록 방어
 */
(function () {
  const script = document.currentScript;
  if (!script) return;

  const jsonId = (script.dataset.jsonId || "").trim();
  const windowName = (script.dataset.windowName || "").trim();

  if (!jsonId || !windowName) return;

  const jsonEl = document.getElementById(jsonId);
  if (!jsonEl) return;

  try {
    window[windowName] = JSON.parse(jsonEl.textContent || "null");
  } catch (err) {
    console.error("[json_boot_bridge] JSON parse failed:", jsonId, err);
  }
})();