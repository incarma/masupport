// django_ma/static/js/common/manage/text.js
// ======================================================
// ✅ Common Text Utilities
// - partner/manage_* 중복 문자열/escape/표시 포맷 SSOT
// - 기능 변화 0: 기존 각 파일의 로컬 함수와 동일한 결과를 반환
// ======================================================

/** null/undefined 안전 문자열 변환 */
export function toStr(value) {
  return String(value ?? "").trim();
}

/** HTML body escape */
export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/** HTML attribute escape — 현재 정책은 escapeHtml과 동일 */
export function escapeAttr(value) {
  return escapeHtml(value);
}

/** 성명/사번 표시: 홍길동(1234567) */
export function formatNameId(name, id) {
  const n = toStr(name);
  const i = toStr(id);

  if (n && i) return `${n}(${i})`;
  if (!n && i) return `(${i})`;
  return n || i || "";
}

/** 숫자만 추출 */
export function digitsOnly(value) {
  return toStr(value).replace(/[^\d]/g, "");
}

/** 한국식 천단위 콤마 */
export function formatCommaNumber(value, fallback = "0") {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return fallback;
  return n.toLocaleString("ko-KR");
}

/** -, 빈값 제외 후 공백 조합 */
export function joinNonEmpty(values, sep = " ") {
  const arr = (values || [])
    .map(toStr)
    .filter((v) => v && v !== "-");

  return arr.length ? arr.join(sep) : "";
}