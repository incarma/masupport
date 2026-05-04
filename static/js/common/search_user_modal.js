/**
 * django_ma/static/js/common/search_user_modal.js
 * =============================================================================
 * ✅ 공통 대상자 검색 모달 (FINAL REFACTOR - affiliation_display 지원)
 * =============================================================================
 */

(() => {
  const DEBUG = false; // 필요시 true로 바꿔서 콘솔 확인
  const log = (...a) => DEBUG && console.log("[search_user_modal]", ...a);

  /** @type {HTMLTableRowElement|null} */
  let activeRow = null;

  /* =======================================================
   * Utils
   * ======================================================= */
  const toStr = (v) => String(v ?? "").trim();

  function readDatasetAny(ds, keys = []) {
    if (!ds) return "";
    for (const k of keys) {
      const v = ds[k];
      if (v && String(v).trim()) return String(v).trim();
    }
    return "";
  }

  function escapeHtml(v) {
    const s = String(v ?? "");
    return s
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function tryHideModal(modalEl) {
    try {
      const inst = window.bootstrap?.Modal?.getInstance?.(modalEl);
      if (inst) inst.hide();
    } catch (_) {}
  }

  async function safeReadJson(res) {
    const text = await res.text().catch(() => "");
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { _raw: text.slice(0, 300) };
    }
  }

  function dispatchUserSelected(selected) {
    const ev = new CustomEvent("userSelected", { detail: selected });
    document.dispatchEvent(ev);
    window.dispatchEvent(ev);
  }

  /* =======================================================
   * Root / Scope
   * ======================================================= */
  function getActiveRoot() {
    return (
      document.getElementById("manage-structure") ||
      document.getElementById("manage-rate") ||
      document.getElementById("manage-efficiency") ||
      document.getElementById("manage-calculate") ||
      document.getElementById("manage-table") ||
      document.getElementById("collect-home") ||
      document.getElementById("collect-notice") ||
      document.getElementById("deposit-home") ||
      document.getElementById("support-form") ||
      null
    );
  }

  function getUserGrade(root) {
    return toStr(root?.dataset?.userGrade || window.currentUser?.grade || "");
  }

  function getPageScope(root) {
    const id = root?.id || "";
    if (
      id === "manage-structure" ||
      id === "manage-rate" ||
      id === "manage-efficiency" ||
      id === "manage-calculate" ||
      id === "support-form"
    ) {
      return "branch";
    }
    return "default";
  }

  function findBranchSelectEl(root) {
    const selectors = [
      "#branchSelect",
      "#branch",
      "#id_branch",
      "[data-branch-select]",
      'select[name="branch"]',
      'select[name="branchSelect"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }

    const inRoot = root?.querySelector?.('select[id*="branch"], select[name*="branch"]');
    if (inRoot) return inRoot;

    return null;
  }

  function getEffectiveBranchForSearch(root) {
    const grade = getUserGrade(root);
    const sel = findBranchSelectEl(root);

    const selectedBranch = toStr(sel?.value || "");
    const uBranch = toStr(window.currentUser?.branch || "");
    const dsBranch = toStr(root?.dataset?.defaultBranch || "");

    if (grade === "superuser") return selectedBranch || uBranch || dsBranch;
    return uBranch || dsBranch || selectedBranch;
  }

  /* =======================================================
   * Active row tracking
   * ======================================================= */
  function clearActiveMarks(root) {
    const scopeRoot = root || document;
    try {
      scopeRoot
        .querySelectorAll("tr.input-row.active, tr.input-row.active-input-row")
        .forEach((x) => {
          x.classList.remove("active");
          x.classList.remove("active-input-row");
        });
    } catch (_) {}
  }

  function markActiveRowFromBtn(btn) {
    const tr = btn?.closest?.("tr.input-row") || btn?.closest?.("tr");
    if (!tr) return;

    const root = getActiveRoot();
    clearActiveMarks(root);

    try {
      tr.classList.add("active-input-row");
      if (tr.classList.contains("input-row")) tr.classList.add("active");
    } catch (_) {}

    activeRow = tr;
    log("activeRow set", tr);
  }

  function getFallbackRow(root) {
    const inputTable = root?.querySelector?.("#inputTable");
    const rows = inputTable?.querySelectorAll?.("tr.input-row");
    if (rows && rows.length) return rows[rows.length - 1];
    return null;
  }

  function resolveTargetRow(root) {
    if (activeRow && document.contains(activeRow)) return activeRow;

    const r1 = root?.querySelector?.("tr.input-row.active");
    if (r1) return r1;

    const r2 = root?.querySelector?.("tr.input-row.active-input-row");
    if (r2) return r2;

    const a1 = document.querySelector("tr.input-row.active");
    if (a1) return a1;

    const a2 = document.querySelector("tr.input-row.active-input-row");
    if (a2) return a2;

    return getFallbackRow(root);
  }

  /* =======================================================
   * Field helpers
   * ======================================================= */
  function findField(row, key) {
    if (!row || !key) return null;

    let el =
      row.querySelector?.(`[name="${key}"]`) ||
      row.querySelector?.(`[name="${key}[]"]`) ||
      null;
    if (el) return el;

    el = row.querySelector?.(`[data-field="${key}"]`) || null;
    if (el) return el;

    el = row.querySelector?.(`.${key}`) || null;
    if (el) return el;

    el = row.querySelector?.(`[id^="${key}"]`) || null;
    if (el) return el;

    return null;
  }

  function setValueIfExists(row, key, value) {
    const el = findField(row, key);
    if (!el) return false;

    el.value = value ?? "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function syncDisplayIfExists(row, displaySelector, name, id) {
    const disp = row?.querySelector?.(displaySelector);
    if (!disp) return false;

    const n = toStr(name);
    const i = toStr(id);
    disp.value = n && i ? `${n}(${i})` : n || i || "";
    disp.dispatchEvent(new Event("input", { bubbles: true }));
    disp.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function buildTeamLabel(selected) {
    return [selected?.team_a, selected?.team_b, selected?.team_c]
      .map(toStr)
      .filter(Boolean)
      .join(" ");
  }

  function autofillSelectedUser(row, selected) {
    if (!row) return;

    const name = toStr(selected?.name || "");
    const id = toStr(selected?.id || "");
    const branch = toStr(selected?.branch || "");
    const rank = toStr(selected?.rank || "");
    const part = toStr(selected?.part || "");
    const affiliation = toStr(selected?.affiliation_display || selected?.affiliationDisplay || "");

    const teamLabel = buildTeamLabel(selected);
    const fallbackAff = [branch, teamLabel].filter(Boolean).join(" > ");
    const tgBranchValue = affiliation || fallbackAff || branch || teamLabel || "-";

    setValueIfExists(row, "tg_name", name) || setValueIfExists(row, "target_name", name);
    setValueIfExists(row, "tg_id", id) || setValueIfExists(row, "target_id", id);

    setValueIfExists(row, "tg_branch", tgBranchValue) || setValueIfExists(row, "target_branch", tgBranchValue);

    setValueIfExists(row, "tg_rank", rank) || setValueIfExists(row, "rank", rank);
    setValueIfExists(row, "tg_part", part) || setValueIfExists(row, "target_part", part);

    syncDisplayIfExists(row, ".tg_display", name, id) || syncDisplayIfExists(row, ".target_display", name, id);
  }

  /* =======================================================
   * Search
   * ======================================================= */
  function resolveSearchUrls(modalEl, root) {
    const modalUrl = toStr(modalEl?.dataset?.searchUrl || "");
    const rootUrl = toStr(root?.dataset?.searchUserUrl || "");
    const fallbacks = ["/board/search-user/", "/api/accounts/search-user/"];

    const urls = [modalUrl, rootUrl, ...fallbacks].map(toStr).filter(Boolean);
    return Array.from(new Set(urls));
  }

  async function fetchSearch(urls, params) {
    let lastErr = null;

    for (const base of urls) {
      try {
        const u = new URL(base, window.location.origin);

        if (params.q) {
          u.searchParams.set("q", params.q);
          u.searchParams.set("keyword", params.q);
        }
        if (params.scope) u.searchParams.set("scope", params.scope);
        if (params.branch) u.searchParams.set("branch", params.branch);

        const res = await fetch(u.toString(), {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });

        if (res.status === 404) {
          log("404 fallback next", u.toString());
          continue;
        }

        const data = await safeReadJson(res);
        if (!res.ok) throw new Error(data?.message || `HTTP ${res.status}`);

        // ✅ ok 플래그가 있는 API 대비 (ok:false면 200이어도 실패로 처리)
        if (data && data.ok === false) {
          throw new Error(data?.message || "검색 API 응답 ok=false");
        }

        return { ok: true, url: u.toString(), data };
      } catch (e) {
        lastErr = e;
        log("fetch failed", base, e);
      }
    }

    return { ok: false, error: lastErr || new Error("검색 API 호출 실패(모든 후보 URL 실패)") };
  }

  function normalizeUserList(data) {
    if (!data) return [];

    // 1) 가장 흔한 케이스
    if (Array.isArray(data.results)) return data.results;
    if (Array.isArray(data.items)) return data.items;
    if (Array.isArray(data.users)) return data.users;
    if (Array.isArray(data.data)) return data.data; // { data: [...] }

    // 2) 중첩 응답 케이스: { ok: true, data: { results:[...] } } 등
    const d = data.data || data.payload || data.result || null;
    if (d) {
      if (Array.isArray(d.results)) return d.results;
      if (Array.isArray(d.items)) return d.items;
      if (Array.isArray(d.users)) return d.users;
      if (Array.isArray(d.data)) return d.data;
      if (Array.isArray(d)) return d;
    }

    // 3) 마지막 방어: 단일 key 아래 배열이 들어있는 경우 자동 탐색
    try {
      for (const k of Object.keys(data)) {
        if (Array.isArray(data[k])) return data[k];
      }
    } catch (_) {}

    return [];
  }

  /* =======================================================
   * Render
   * ======================================================= */
  function renderLoading(resultsBox) {
    resultsBox.innerHTML = `<div class="text-center py-3 text-muted">검색 중...</div>`;
  }

  function renderEmpty(resultsBox) {
    resultsBox.innerHTML = `<div class="text-center py-3 text-danger">검색 결과가 없습니다.</div>`;
  }

  function renderError(resultsBox) {
    resultsBox.innerHTML = `<div class="text-center text-danger py-3">검색 실패</div>`;
  }

  function renderResults(resultsBox, list) {
    resultsBox.innerHTML = list
      .map((u0) => {
        const u = u0 || {};
        const name = escapeHtml(u.name || "");
        const id = escapeHtml(u.id || "");
        const regist = escapeHtml(u.regist || "");
        const enter = escapeHtml(u.enter || "-");
        const quit = escapeHtml(u.quit || "재직중");

        const affiliation = escapeHtml(u.affiliation_display || u.affiliationDisplay || "");
        const branchV = escapeHtml(u.branch || "");
        const rightLabel = affiliation || branchV || "-";

        return `
          <button type="button"
            class="list-group-item list-group-item-action search-result"
            data-id="${escapeHtml(u.id)}"
            data-name="${escapeHtml(u.name)}"
            data-branch="${escapeHtml(u.branch || "")}"
            data-affiliation-display="${escapeHtml(u.affiliation_display || u.affiliationDisplay || "")}"
            data-rank="${escapeHtml(u.rank || "")}"
            data-part="${escapeHtml(u.part || "")}"
            data-team-a="${escapeHtml(u.team_a || "")}"
            data-team-b="${escapeHtml(u.team_b || "")}"
            data-team-c="${escapeHtml(u.team_c || "")}"
            data-regist="${escapeHtml(u.regist || "")}"
            data-enter="${escapeHtml(u.enter || "")}"
            data-quit="${escapeHtml(u.quit || "재직중")}">
            <div class="d-flex justify-content-between">
              <span><strong>${name}</strong> (${id}) ${regist ? `(${regist})` : ""}</span>
              <small class="text-muted">${rightLabel}</small>
            </div>
            <small class="text-muted">입사일: ${enter} / 퇴사일: ${quit}</small>
          </button>
        `;
      })
      .join("");
  }

  /* =======================================================
   * Init
   * ======================================================= */
  function init() {
    const modalEl = document.getElementById("searchUserModal");
    if (!modalEl) return;

    if (modalEl.dataset.bound === "true") return;
    modalEl.dataset.bound = "true";

    const form = modalEl.querySelector("#searchUserForm");
    const input = modalEl.querySelector("#searchKeyword");
    const resultsBox = modalEl.querySelector("#searchResults");

    if (!form || !resultsBox) {
      console.warn("[search_user_modal] form/resultsBox not found");
      return;
    }

    document.addEventListener(
      "click",
      (e) => {
        const btn = e.target?.closest?.(".btnOpenSearch");
        if (!btn) return;
        markActiveRowFromBtn(btn);

        if (!btn.dataset.bsToggle && window.bootstrap?.Modal) {
          const modalEl = document.getElementById("searchUserModal");
          if (modalEl) window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      },
      true
    );

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const keyword = toStr(input?.value || "");
      if (!keyword) return window.alert("검색어를 입력하세요.");

      const root = getActiveRoot();
      const scope = getPageScope(root);
      const grade = getUserGrade(root);

      let branch = "";
      if (scope === "branch") {
        if (!root) return window.alert("페이지 루트를 찾을 수 없습니다.");
        branch = getEffectiveBranchForSearch(root);

        if (grade === "superuser" && !branch) {
          return window.alert("지점 정보가 없습니다. (부서/지점을 먼저 선택해주세요)");
        }
      }

      renderLoading(resultsBox);

      const urls = resolveSearchUrls(modalEl, root);
      const params = {
        q: keyword,
        scope: scope === "branch" ? "branch" : "",
        branch: scope === "branch" && grade === "superuser" ? branch : "",
      };

      try {
        const r = await fetchSearch(urls, params);
        if (!r.ok) throw r.error;

        const list = normalizeUserList(r.data);
        if (DEBUG) {
          console.log("[search_user_modal] response url:", r.url);
          console.log("[search_user_modal] raw json:", r.data);
          console.log("[search_user_modal] normalized list len:", list.length);
        }
        if (!list.length) return renderEmpty(resultsBox);

        renderResults(resultsBox, list);
      } catch (err) {
        console.error("❌ 검색 오류:", err);
        renderError(resultsBox);
      }
    });

    resultsBox.addEventListener("click", (e) => {
      const item = e.target?.closest?.(".search-result");
      if (!item) return;

      const ds = item.dataset || {};
      const selected = {
        id: readDatasetAny(ds, ["id"]),
        name: readDatasetAny(ds, ["name"]),
        branch: readDatasetAny(ds, ["branch"]),
        affiliation_display: readDatasetAny(ds, ["affiliationDisplay", "affiliation_display", "affiliation"]),
        rank: readDatasetAny(ds, ["rank"]),
        part: readDatasetAny(ds, ["part"]),
        team_a: readDatasetAny(ds, ["teamA", "team_a", "teama"]),
        team_b: readDatasetAny(ds, ["teamB", "team_b", "teamb"]),
        team_c: readDatasetAny(ds, ["teamC", "team_c", "teamc"]),
        regist: readDatasetAny(ds, ["regist"]),
        enter: readDatasetAny(ds, ["enter"]),
        quit: readDatasetAny(ds, ["quit"]),
      };

      const root = getActiveRoot();

      // ✅ collect-notice: row 자동입력 없음 → 이벤트만 전달
      if (root?.id === "collect-notice") {
        dispatchUserSelected(selected);
        tryHideModal(modalEl);

        if (input) input.value = "";
        resultsBox.innerHTML = "";
        return;
      }

      // ✅ [Step 12] collect-home: 검색 모달만 닫고 피드백 모달 유지
      // deposit-home의 location.href 방식과 다르다 — 절대 혼동 금지
      if (root?.id === "collect-home") {
        dispatchUserSelected(selected);  // collect_home.js의 userSelected 리스너가 처리
        tryHideModal(modalEl);           // 검색 모달만 닫기
        if (input) input.value = "";
        resultsBox.innerHTML = "";
        return;
      }

      // ✅ deposit-home: 이벤트 발행 금지(=fetch 중단으로 Failed to fetch 유발 방지), 바로 이동
      if (root?.id === "deposit-home") {
        tryHideModal(modalEl);
        if (input) input.value = "";
        resultsBox.innerHTML = "";

        const id = toStr(selected.id);
        if (id) {
          location.href = `/commission/deposit/?user=${encodeURIComponent(id)}`;
        }
        return;
      }

      // ✅ 일반 페이지: row autofill + 이벤트 발행
      const row = resolveTargetRow(root);
      if (!row) {
        console.warn("[search_user_modal] target row not found");
      } else {
        autofillSelectedUser(row, selected);
      }

      dispatchUserSelected(selected);
      tryHideModal(modalEl);

      if (input) input.value = "";
      resultsBox.innerHTML = "";
    });

    modalEl.addEventListener("hidden.bs.modal", () => {
      if (input) input.value = "";
      resultsBox.innerHTML = "";
    });

    log("bound ok");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
