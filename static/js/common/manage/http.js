/**
 * django_ma/static/js/common/manage/http.js
 * ------------------------------------------------------------
 * - 관리 페이지 fetch JSON 응답 공통 처리
 * - 로그인 만료/403/500 HTML 응답 방어
 * - JSON endpoint에서만 사용
 * ------------------------------------------------------------
 */

export async function readJsonOrThrow(res, fallbackMessage = "요청 처리 중 오류가 발생했습니다.") {
  const status = Number(res?.status || 0);
  const contentType = String(res?.headers?.get?.("content-type") || "").toLowerCase();
  const text = await res.text();

  if (!contentType.includes("application/json")) {
    if (status === 401 || status === 403) {
      throw new Error("권한이 없거나 로그인이 만료되었습니다. 다시 로그인 후 시도해주세요.");
    }
    if (status >= 500) {
      throw new Error("서버 오류가 발생했습니다. 관리자에게 문의해주세요.");
    }
    throw new Error(`서버 응답이 JSON이 아닙니다. (status=${status || "unknown"})`);
  }

  let data = {};
  try {
    data = JSON.parse(text || "{}");
  } catch {
    throw new Error(`JSON 응답 파싱에 실패했습니다. (status=${status || "unknown"})`);
  }

  if (!res.ok) {
    throw new Error(data?.message || data?.error || fallbackMessage);
  }

  return data;
}

export function isSuccessJson(data) {
  return data?.status === "success" || data?.success === true;
}