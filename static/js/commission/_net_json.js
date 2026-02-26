// django_ma/static/js/commission/_net_json.js
// Commission 공용 JSON fetch/unwrap 유틸 (content-type 방어 포함)

(() => {
  "use strict";

  const root = (window.CommissionCommon = window.CommissionCommon || {});

  async function fetchJSON(url, options = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        ...(options.headers || {}),
      },
      ...options,
    });

    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!ct.includes("application/json")) {
      const body = await res.text().catch(() => "");
      throw new Error(
        `JSON 아님: ${res.status} ${res.statusText}\nurl=${url}\ncontent-type=${ct}\nbody=${body.slice(0, 200)}`
      );
    }

    const data = await res.json();
    if (!res.ok) throw new Error(data?.message || `요청 실패 (${res.status})`);
    if (data && data.ok === false) throw new Error(data.message || "요청 실패");
    return data;
  }

  function firstObject(data) {
    if (!data || typeof data !== "object") return null;
    if (Array.isArray(data.rows) && data.rows.length) return data.rows[0];
    for (const k of ["user", "summary", "data", "result", "payload", "item"]) {
      const v = data?.[k];
      if (v && typeof v === "object" && !Array.isArray(v)) return v;
      if (Array.isArray(v) && v.length) return v[0];
    }
    return null;
  }

  function arrayRows(data) {
    if (!data || typeof data !== "object") return [];
    if (Array.isArray(data.rows)) return data.rows;
    for (const k of ["items", "results", "data", "list", "rows"]) {
      if (Array.isArray(data?.[k])) return data[k];
    }
    return [];
  }

  root.net = Object.freeze({
    fetchJSON,
    firstObject,
    arrayRows,
  });
})();