/**
 * django_ma/static/js/common/manage/dataset.js
 * ------------------------------------------------------------
 * - dataset key 접근 헬퍼
 * - 여러 key 후보 중 첫 번째 유효값 반환
 * - 공통 ds() 제공
 * - camelCase dataset + data-kebab-case fallback 지원
 * ------------------------------------------------------------
 */

export function ds(rootEl, key, fallback = "") {
  try {
    return (rootEl?.dataset?.[key] ?? fallback).toString().trim();
  } catch {
    return (fallback ?? "").toString().trim();
  }
}

// ✅ camelCase → kebab-case 변환
// 예: dataFetchUrl → data-fetch-url
export function toDashed(camel) {
  return String(camel || "").replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
}

// ✅ 여러 dataset key 후보 중 첫 번째 유효값 반환
// - 기존 ds(rootEl, key)와 getDatasetUrl(rootEl, keys) 호출부 호환 유지
// - rootEl.dataset[k] 우선
// - 없으면 rootEl.getAttribute("data-...") fallback
export function getDatasetValue(rootEl, keys = [], fallback = "") {
  if (!rootEl) return String(fallback ?? "").trim();

  const dsObj = rootEl?.dataset;
  if (dsObj) {
    for (const k of keys) {
      const v = dsObj[k];
      if (v && String(v).trim()) return String(v).trim();
    }
  }

  // ✅ legacy/혼재 dataset 키 방어
  // 예: keys=["dataFetchUrl"]이면 data-data-fetch-url도 확인 가능
  for (const k of keys) {
    const attr = `data-${toDashed(k)}`;
    const v = rootEl.getAttribute?.(attr);
    if (v && String(v).trim()) return String(v).trim();
  }
  
  return String(fallback ?? "").trim();
}

export function getDatasetUrl(rootEl, keys = []) {
  return getDatasetValue(rootEl, keys, "");
}
