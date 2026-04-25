// django_ma/static/js/partner/manage_rate/table_dropdown.js
// ======================================================
// 📘 Manage Rate - Table Dropdown
// - Fetches TableSetting rows per branch (cached)
// - Replaces after_ftable/after_ltable inputs with selects
// - Syncs after_frate/after_lrate automatically
// ======================================================

import { els } from "./dom_refs.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

const cache = new Map();

/* ======================================================
   Cache controls
====================================================== */
export function clearTableCache(branch = "") {
  const b = String(branch || "").trim();
  if (b) cache.delete(b);
  else cache.clear();
}

/* ======================================================
   Fetch branch tables (cached)
   returns: [{ table, rate }, ...]
====================================================== */
export async function fetchBranchTables(branch) {
  const b = String(branch || "").trim();
  if (!b) return [];

  if (cache.has(b)) return cache.get(b);

  const base = String(els.root?.dataset?.tableFetchUrl || "").trim(); // data-table-fetch-url
  if (!base) {
    console.warn("[rate/table_dropdown] data-table-fetch-url missing");
    cache.set(b, []);
    return [];
  }

  const url = new URL(base, window.location.origin);
  url.searchParams.set("branch", b);

  const res = await fetch(url.toString(), {
    headers: { "X-Requested-With": "XMLHttpRequest" },
    credentials: "same-origin",
  });

  let data;
  try {
    data = await readJsonOrThrow(res, "테이블 정보 조회 실패");
  } catch (err) {
    console.warn("[rate/table_dropdown] fetch failed:", err?.message || err);
    cache.set(b, []);
    return [];
  }

  if (!isSuccessJson(data)) {
    console.warn("[rate/table_dropdown] fetch failed:", data);
    cache.set(b, []);
    return [];
  }

  const rows = Array.isArray(data.rows) ? data.rows : [];
  const tables = rows
    .map((r) => ({
      table: String(r.table || r.table_name || "").trim(),
      rate: String(r.rate ?? "").trim(),
    }))
    .filter((x) => x.table);

  cache.set(b, tables);
  return tables;
}

/* ======================================================
   Apply dropdown to a row
====================================================== */
export function applyTableDropdownToRow(rowEl, tables = []) {
  if (!rowEl) return;

  /* ---------------------------
     Ensure selects exist (replace inputs if needed)
  --------------------------- */
  const ensureSelect = (name) => {
    const existing = rowEl.querySelector(`select[name="${name}"]`);
    if (existing) return existing;

    const input = rowEl.querySelector(`input[name="${name}"]`);
    const keepValue = input?.value || "";

    const sel = document.createElement("select");
    sel.name = name;
    sel.className = "form-select form-select-sm";

    if (input && input.parentNode) input.parentNode.replaceChild(sel, input);
    else rowEl.appendChild(sel);

    if (keepValue) sel.value = keepValue;
    return sel;
  };

  const afterFSelect = ensureSelect("after_ftable");
  const afterLSelect = ensureSelect("after_ltable");

  /* ---------------------------
     Fill options (table name only)
  --------------------------- */
  const fillOptions = (sel) => {
    const current = sel.value || "";
    sel.innerHTML = `<option value="">선택</option>`;

    for (const t of tables) {
      const opt = document.createElement("option");
      opt.value = t.table;
      opt.textContent = t.table;
      sel.appendChild(opt);
    }

    if (current) sel.value = current;
  };

  fillOptions(afterFSelect);
  fillOptions(afterLSelect);

  /* ---------------------------
     Sync rates
  --------------------------- */
  const rateMap = new Map(tables.map((t) => [t.table, t.rate]));
  const afterFRateInput = rowEl.querySelector(`[name="after_frate"]`);
  const afterLRateInput = rowEl.querySelector(`[name="after_lrate"]`);

  const syncRates = () => {
    if (afterFRateInput) afterFRateInput.value = rateMap.get(afterFSelect.value) || "";
    if (afterLRateInput) afterLRateInput.value = rateMap.get(afterLSelect.value) || "";
  };

  // overwrite onchange (prevents multiple bindings)
  afterFSelect.onchange = syncRates;
  afterLSelect.onchange = syncRates;

  syncRates();
}
