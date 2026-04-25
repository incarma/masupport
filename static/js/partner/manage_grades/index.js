// django_ma/static/js/partner/manage_grades/index.js
/* =========================================================
   Partner / Manage Grades - Final Refactor (v3)
   ---------------------------------------------------------
   [Goals]
   - Readability & Maintainability
   - Stable on BFCache (pageshow persisted)
   - Robust CSRF / fetch / error handling
   - Safe DataTables lifecycle (destroy/re-init)
   - Feature parity with existing implementation

   [Features]
   - Superuser: Channel → Part → Branch cascading selector
   - DataTables: SubAdmin table + AllUser serverSide table
   - Excel: Download (XLSX) + Upload trigger
   - SubAdmin: level change + delete
   - Add SubAdmin modal: search + promote
========================================================= */

(function () {
  "use strict";

  /* =========================================================
   * 0) Small Utilities
   * ========================================================= */
  const U = {
    str(v) { return String(v ?? "").trim(); },
    qs(sel, root = document) { return root.querySelector(sel); },
    escHtml(v) {
      const s = String(v ?? "");
      return s
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    },
    getCookie(name) {
      const value = `; ${document.cookie || ""}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) return parts.pop().split(";").shift();
      return "";
    },
    buildUrl(base, params) {
      const url = new URL(base, window.location.origin);
      Object.entries(params || {}).forEach(([k, v]) => {
        const val = String(v ?? "").trim();
        if (!val) return;
        url.searchParams.set(k, val);
      });
      return url.toString();
    },
    // Data payload resolver (channels/parts/branches/data or array)
    pickListPayload(d) {
      if (!d) return [];
      if (Array.isArray(d)) return d;
      if (Array.isArray(d.channels)) return d.channels;
      if (Array.isArray(d.parts)) return d.parts;
      if (Array.isArray(d.branches)) return d.branches;
      if (Array.isArray(d.data)) return d.data;
      return [];
    },
  };

  /* =========================================================
   * 1) DOM + Context
   * ========================================================= */
  function getRoot() {
    return document.getElementById("manage-grades");
  }

  function getContext() {
    const root = getRoot();
    const d = root?.dataset || {};
    return {
      root,

      // auth/grade context
      userGrade: U.str(d.userGrade),
      userBranch: U.str(d.userBranch),

      // current selected (server-rendered)
      selectedChannel: U.str(d.selectedChannel),
      selectedPart: U.str(d.selectedPart),
      selectedBranch: U.str(d.selectedBranch),

      // urls
      updateLevelUrl: U.str(d.updateLevelUrl),
      deleteSubadminUrl: U.str(d.deleteSubadminUrl),
      addSubadminUrl: U.str(d.addSubadminUrl),
      searchUrl: U.str(d.searchUrl || "/api/accounts/search-user/"),

      // cascade endpoints (superuser)
      fetchChannelsUrl: U.str(d.fetchChannelsUrl || "/partner/ajax/fetch-channels/"),
      fetchPartsUrl: U.str(d.fetchPartsUrl || "/partner/ajax/fetch-parts/"),
      fetchBranchesUrl: U.str(d.fetchBranchesUrl || "/partner/ajax/fetch-branches/"),
    };
  }

  function isAllowedGrade(grade) {
    return grade === "superuser" || grade === "head";
  }

  function canInitDataTables(ctx) {
    if (!isAllowedGrade(ctx.userGrade)) return false;
    return !!(ctx.selectedPart && ctx.selectedBranch);
  }

  /* =========================================================
   * 2) UI Helpers (Toast / Select options)
   * ========================================================= */
  function showToast(message, isSuccess) {
    const toastElement = document.getElementById("statusToast");
    const toastTitle = document.getElementById("toastTitle");
    const toastBody = document.getElementById("toastBody");

    if (!toastElement || !toastTitle || !toastBody) {
      alert(message);
      return;
    }

    toastTitle.textContent = isSuccess ? "✅ 처리 성공" : "❌ 처리 실패";
    toastElement.classList.toggle("text-bg-success", !!isSuccess);
    toastElement.classList.toggle("text-bg-danger", !isSuccess);
    toastBody.textContent = message;

    if (window.bootstrap?.Toast) new bootstrap.Toast(toastElement, { delay: 3000 }).show();
    else alert(message);
  }

  function setSelectOptions(selectEl, options, placeholderText = "선택") {
    if (!selectEl) return;
    const opts = Array.isArray(options) ? options : [];
    selectEl.innerHTML =
      `<option value="">${U.escHtml(placeholderText)}</option>` +
      opts.map(v => {
        const val = U.str(v);
        return `<option value="${U.escHtml(val)}">${U.escHtml(val)}</option>`;
      }).join("");
  }

  function updateSearchButtonState(partSelect, branchSelect, btnSearch) {
    if (!btnSearch) return;
    const ok = !!U.str(partSelect?.value) && !!U.str(branchSelect?.value);
    btnSearch.disabled = !ok;
  }

  /* =========================================================
   * 3) Network / CSRF / fetch wrappers
   * ========================================================= */
  function getCSRFToken() {
    const input =
      U.qs('#csrfForm input[name="csrfmiddlewaretoken"]') ||
      U.qs('input[name="csrfmiddlewaretoken"]');
    const fromInput = U.str(input?.value);
    return fromInput || U.str(U.getCookie("csrftoken"));
  }

  async function readJson(res) {
    const status = Number(res?.status || 0);
    const contentType = String(res?.headers?.get?.("content-type") || "").toLowerCase();
    const text = await res.text();
    if (!contentType.includes("application/json")) {
      return {
        ok: false,
        status,
        data: null,
        text,
        message:
          status === 401 || status === 403
            ? "권한이 없거나 로그인이 만료되었습니다. 다시 로그인 후 시도해주세요."
            : status >= 500
              ? "서버 오류가 발생했습니다. 관리자에게 문의해주세요."
              : `서버 응답이 JSON이 아닙니다. (${status || "unknown"})`,
      };
    }
    if (!text) return { ok: res.ok, status, data: null, text: "" };
    try {
      return { ok: res.ok, status, data: JSON.parse(text), text };
    } catch {
      return { ok: false, status, data: null, text, message: "JSON 응답 파싱에 실패했습니다." };
    }
  }

  async function getList(url) {
    const res = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });

    const parsed = await readJson(res);
    if (!res.ok || !parsed.data) {
      const msg = parsed.message || parsed.data?.message || parsed.data?.error || `HTTP ${parsed.status}`;
      throw new Error(msg);
    }
    return U.pickListPayload(parsed.data);
  }

  function buildPostHeaders() {
    const csrf = getCSRFToken();
    const headers = {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
    };
    if (csrf) headers["X-CSRFToken"] = csrf;
    return headers;
  }

  async function postForm(url, params) {
    if (!url) throw new Error("요청 URL이 비어 있습니다.");

    const res = await fetch(url, {
      method: "POST",
      headers: buildPostHeaders(),
      credentials: "same-origin",
      body: new URLSearchParams(params || {}),
    });

    const parsed = await readJson(res);

    // 로그인 redirect/HTML 등 JSON이 아닌 케이스 방어
    if (!parsed.data) {
      console.error("Non-JSON response:", { status: parsed.status, text: parsed.text });
      throw new Error(parsed.message || `서버 응답이 JSON이 아닙니다. (${parsed.status})`);
    }

    if (!res.ok) {
      throw new Error(parsed.data?.error || parsed.data?.message || `요청 실패 (${parsed.status})`);
    }

    if (parsed.data.ok === false || parsed.data.success === false) {
      throw new Error(parsed.data?.error || parsed.data?.message || "처리 실패");
    }

    return parsed.data;
  }

  /* =========================================================
   * 4) Superuser Filters: Channel → Part → Branch
   * ========================================================= */
  function getFilterEls() {
    return {
      channelSelect: document.getElementById("channelSelect"),
      partSelect: document.getElementById("partSelect"),
      branchSelect: document.getElementById("branchSelect"),
      btnSearch: document.getElementById("btnSearch"),

      // hidden initial values
      selectedChannelInit: document.getElementById("selectedChannelInit"),
      selectedPartInit: document.getElementById("selectedPartInit"),
      selectedBranchInit: document.getElementById("selectedBranchInit"),
    };
  }

  async function loadChannels(ctx, channelSelect) {
    channelSelect.disabled = true;
    setSelectOptions(channelSelect, [], "불러오는 중...");
    const list = await getList(ctx.fetchChannelsUrl);
    const cleaned = list.map(U.str).filter(Boolean);
    setSelectOptions(channelSelect, cleaned, "부문 선택");
    channelSelect.disabled = false;
    return cleaned;
  }

  async function loadParts(ctx, channel, partSelect) {
    partSelect.disabled = true;
    setSelectOptions(partSelect, [], channel ? "불러오는 중..." : "부문을 먼저 선택하세요");
    if (!channel) return [];

    const url = U.buildUrl(ctx.fetchPartsUrl, { channel });
    const list = await getList(url);
    const cleaned = list.map(U.str).filter(Boolean);
    setSelectOptions(partSelect, cleaned, "부서 선택");
    partSelect.disabled = false;
    return cleaned;
  }

  async function loadBranches(ctx, part, branchSelect, channel) {
    branchSelect.disabled = true;
    setSelectOptions(branchSelect, [], part ? "불러오는 중..." : "부서를 먼저 선택하세요");
    if (!part) return [];

    const url = U.buildUrl(ctx.fetchBranchesUrl, { part, channel }); // channel optional
    const list = await getList(url);
    const cleaned = list.map(U.str).filter(Boolean);
    setSelectOptions(branchSelect, cleaned, "지점 선택");
    branchSelect.disabled = false;
    return cleaned;
  }

  async function initChannelPartBranchSelectors() {
    const ctx = getContext();
    if (ctx.userGrade !== "superuser") return;

    const els = getFilterEls();
    const { channelSelect, partSelect, branchSelect, btnSearch } = els;
    if (!channelSelect || !partSelect || !branchSelect) return;

    // BFCache/재진입 중복 바인딩 방지
    if (channelSelect.dataset.bound === "1") {
      updateSearchButtonState(partSelect, branchSelect, btnSearch);
      return;
    }
    channelSelect.dataset.bound = "1";

    // initial values from hidden
    const initChannel = U.str(els.selectedChannelInit?.value);
    const initPart = U.str(els.selectedPartInit?.value);
    const initBranch = U.str(els.selectedBranchInit?.value);

    if (btnSearch) btnSearch.disabled = true;

    // 1) load channel list
    try {
      await loadChannels(ctx, channelSelect);
    } catch (e) {
      console.error("channel load failed:", e);
      setSelectOptions(channelSelect, [], "부문 로드 실패");
      channelSelect.disabled = false;
      return;
    }

    // 2) on channel change -> load parts, reset branch
    channelSelect.addEventListener("change", async () => {
      const channel = U.str(channelSelect.value);

      setSelectOptions(partSelect, [], channel ? "불러오는 중..." : "부문을 먼저 선택하세요");
      partSelect.disabled = true;

      setSelectOptions(branchSelect, [], "부서를 먼저 선택하세요");
      branchSelect.disabled = true;

      updateSearchButtonState(partSelect, branchSelect, btnSearch);

      try {
        await loadParts(ctx, channel, partSelect);
      } catch (e) {
        console.error("part load failed:", e);
        setSelectOptions(partSelect, [], "부서 로드 실패");
        partSelect.disabled = false;
      }
    });

    // 3) on part change -> load branches
    partSelect.addEventListener("change", async () => {
      const part = U.str(partSelect.value);
      const channel = U.str(channelSelect.value); // ✅ always read current channel

      setSelectOptions(branchSelect, [], part ? "불러오는 중..." : "부서를 먼저 선택하세요");
      branchSelect.disabled = true;

      updateSearchButtonState(partSelect, branchSelect, btnSearch);

      try {
        await loadBranches(ctx, part, branchSelect, channel);
      } catch (e) {
        console.error("branch load failed:", e);
        setSelectOptions(branchSelect, [], "지점 로드 실패");
        branchSelect.disabled = false;
      }
    });

    // 4) branch change -> enable search
    branchSelect.addEventListener("change", () => {
      updateSearchButtonState(partSelect, branchSelect, btnSearch);
    });

    // 5) apply initial values: channel -> part -> branch
    if (initChannel) {
      channelSelect.value = initChannel;
      try {
        await loadParts(ctx, initChannel, partSelect);
        if (initPart) {
          partSelect.value = initPart;
          try {
            await loadBranches(ctx, initPart, branchSelect, initChannel);
            if (initBranch) branchSelect.value = initBranch;
          } catch (e) {
            console.warn("init branch load failed:", e);
          }
        }
      } catch (e) {
        console.warn("init part load failed:", e);
      }
    } else {
      setSelectOptions(partSelect, [], "부문을 먼저 선택하세요");
      partSelect.disabled = true;
      setSelectOptions(branchSelect, [], "부서를 먼저 선택하세요");
      branchSelect.disabled = true;
    }

    updateSearchButtonState(partSelect, branchSelect, btnSearch);
  }

  /* =========================================================
   * 5) DataTables
   * ========================================================= */
  function hasDataTables() {
    return !!(window.$ && $.fn && $.fn.DataTable);
  }

  function safeDestroyDataTable($table) {
    if (!$table || !$table.length) return;
    if (hasDataTables() && $.fn.DataTable.isDataTable($table)) {
      try {
        $table.DataTable().clear().destroy(true);
      } catch (e) {
        console.warn("DataTable destroy failed:", e);
      }
    }
  }

  function initTables() {
    const ctx = getContext();
    if (!canInitDataTables(ctx)) {
      console.log("DataTables init skipped: 조건 불충족");
      return;
    }
    if (!hasDataTables()) {
      console.warn("jQuery/DataTables missing: 테이블 초기화 생략");
      return;
    }

    const $subTable = $("#subAdminTable");
    const $allTable = $("#allUserTable");

    const ajaxBase = U.str($allTable.data("ajax-base"));
    if (!ajaxBase) {
      console.warn("ajax-base missing: allUserTable init aborted");
      return;
    }

    const ajaxUrl = U.buildUrl(ajaxBase, { part: ctx.selectedPart, branch: ctx.selectedBranch });

    safeDestroyDataTable($subTable);
    safeDestroyDataTable($allTable);

    // (A) SubAdmin table
    $subTable.DataTable({
      paging: true,
      searching: true,
      info: true,
      pageLength: 10,
      autoWidth: false,
      lengthMenu: [[10, 25, 50, 100], ["10명", "25명", "50명", "100명"]],
      language: {
        url: "//cdn.datatables.net/plug-ins/1.13.6/i18n/ko.json",
        lengthMenu: "페이지당 인원 _MENU_",
        search: "검색:",
        zeroRecords: "표시할 데이터가 없습니다.",
        emptyTable: "해당 부서/지점의 중간관리자가 없습니다.",
        info: "총 _TOTAL_명 중 _START_–_END_ 표시",
        infoEmpty: "데이터 없음",
      },
      dom: `
        <'d-flex justify-content-between align-items-center mb-2'
          <'d-flex align-items-center gap-2'l>
          f
        >rtip
      `,
    });

    // (B) AllUser table (serverSide)
    $allTable.DataTable({
      serverSide: true,
      processing: true,
      ajax: { url: ajaxUrl, type: "GET" },
      columns: [
        { data: "part" },
        { data: "branch" },
        { data: "name" },
        { data: "user_id" },
        { data: "position" },
        { data: "team_a" },
        { data: "team_b" },
        { data: "team_c" },
      ],
      pageLength: 10,
      autoWidth: false,
      lengthMenu: [[10, 25, 50, 100], ["10명", "25명", "50명", "100명"]],
      language: {
        url: "//cdn.datatables.net/plug-ins/1.13.6/i18n/ko.json",
        lengthMenu: "페이지당 인원 _MENU_",
        search: "검색:",
        processing: "로딩 중...",
        zeroRecords: "표시할 데이터가 없습니다.",
        emptyTable: "표시할 데이터가 없습니다.",
      },
      dom: `
        <'d-flex justify-content-between align-items-center mb-2'
          <'d-flex align-items-center gap-2'lB>
          f
        >rtip
      `,
      buttons: buildTableButtons(ajaxUrl),
    });

    bindExcelUploadOnce();
  }

  function buildTableButtons(ajaxUrl) {
    return [
      {
        text: "<i class='bi bi-download'></i> 엑셀 다운로드",
        className: "btn btn-primary btn-sm",
        action: () => downloadAllUsersExcel(ajaxUrl),
      },
      {
        text: "<i class='bi bi-upload'></i> 엑셀 업로드",
        className: "btn btn-primary btn-sm",
        action: () => document.getElementById("excelFile")?.click(),
      },
    ];
  }

  async function downloadAllUsersExcel(ajaxUrl) {
    if (!window.XLSX?.utils) {
      alert("엑셀 라이브러리(XLSX)가 로드되지 않았습니다.");
      return;
    }

    const url = U.buildUrl(ajaxUrl, { length: 999999 });

    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`서버 응답 오류 (${res.status})`);

      const parsed = await readJson(res);
      if (!res.ok || !parsed.data) {
        throw new Error(parsed.message || parsed.data?.message || `서버 응답 오류 (${parsed.status})`);
      }
      const data = parsed.data;
      const list = Array.isArray(data?.data) ? data.data : [];

      if (!list.length) {
        alert("다운로드할 데이터가 없습니다.");
        return;
      }

      const rows = list.map((u) => ({
        성명: u.name || "",
        사번: u.user_id || "",
        직급: u.position || "",
        팀A: u.team_a || "",
        팀B: u.team_b || "",
        팀C: u.team_c || "",
      }));

      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.json_to_sheet(rows);
      XLSX.utils.book_append_sheet(wb, ws, "전체설계사명단");
      XLSX.writeFile(wb, "전체설계사명단.xlsx");
    } catch (err) {
      alert("엑셀 생성 중 오류가 발생했습니다.");
      console.error("Excel download error:", err);
    }
  }

  function bindExcelUploadOnce() {
    const excelFile = document.getElementById("excelFile");
    const excelForm = document.getElementById("excelUploadForm");
    if (!excelFile || !excelForm) return;
    if (excelFile.dataset.bound === "1") return;

    excelFile.dataset.bound = "1";
    excelFile.addEventListener("change", function () {
      if (!this.files.length) return;
      const fileName = this.files[0].name;
      if (confirm(`"${fileName}" 파일을 업로드하시겠습니까?`)) {
        excelForm.submit();
      } else {
        this.value = "";
      }
    });
  }

  /* =========================================================
   * 6) SubAdmin actions (delegated)
   * ========================================================= */
  async function handleLevelChange(selectEl) {
    const ctx = getContext();
    const tr = selectEl.closest("tr");
    const userId = U.str(tr?.dataset?.userId || tr?.getAttribute("data-user-id"));
    const newLevel = U.str(selectEl.value);

    if (!userId) return showToast("user_id를 찾을 수 없습니다.", false);

    try {
      await postForm(ctx.updateLevelUrl, { user_id: userId, level: newLevel });
      showToast(`레벨이 ${newLevel}로 변경되었습니다.`, true);
    } catch (err) {
      console.error("level update error:", err);
      showToast(err?.message || "서버 요청 중 오류가 발생했습니다.", false);
    }
  }

  async function handleSubadminDelete(btnEl) {
    const ctx = getContext();
    const tr = btnEl.closest("tr");

    const userId =
      U.str(btnEl.dataset.userId) ||
      U.str(tr?.dataset?.userId || tr?.getAttribute("data-user-id"));

    const userName =
      U.str(btnEl.dataset.userName) ||
      U.str(tr?.dataset?.userName) ||
      "";

    if (!userId) return showToast("user_id를 찾을 수 없습니다.", false);

    const label = userName ? `[${userName}]` : `[${userId}]`;
    if (!confirm(`${label} 중간관리자를 삭제할까요?\n(계정은 유지되고 grade가 basic으로 변경됩니다.)`)) return;

    btnEl.disabled = true;

    try {
      await postForm(ctx.deleteSubadminUrl, { user_id: userId });

      // row remove (DataTable if exists, else DOM)
      if (hasDataTables()) {
        const $sub = $("#subAdminTable");
        if ($sub.length && $.fn.DataTable.isDataTable($sub)) {
          $sub.DataTable().row($(tr)).remove().draw(false);
        } else {
          tr?.remove();
        }
      } else {
        tr?.remove();
      }

      showToast("중간관리자가 삭제되었습니다. (grade=basic)", true);
    } catch (err) {
      console.error("delete error:", err);
      showToast(err?.message || "삭제 처리 중 오류가 발생했습니다.", false);
      btnEl.disabled = false;
    }
  }

  function bindSubAdminDelegation() {
    const table = document.getElementById("subAdminTable");
    if (!table || table.dataset.bound === "1") return;

    table.dataset.bound = "1";

    table.addEventListener("change", (e) => {
      const sel = e.target?.closest?.(".level-select");
      if (!sel) return;
      handleLevelChange(sel);
    });

    table.addEventListener("click", (e) => {
      const btn = e.target?.closest?.(".js-delete-subadmin");
      if (!btn) return;
      handleSubadminDelete(btn);
    });
  }

  /* =========================================================
   * 7) Add SubAdmin Modal
   * ========================================================= */
  function openAddModal() {
    const modalEl = document.getElementById("addSubAdminModal");
    const keywordEl = document.getElementById("addSubAdminKeyword");
    const resultsEl = document.getElementById("addSubAdminResults");
    if (!modalEl) return;

    const ctx = getContext();

    if (ctx.userGrade === "superuser" && (!ctx.selectedPart || !ctx.selectedBranch)) {
      return alert("부서/지점을 선택 후 검색하세요.");
    }
    if (ctx.userGrade === "head" && !ctx.userBranch) {
      return alert("본인 지점 정보가 없습니다. 관리자에게 문의해주세요.");
    }

    if (keywordEl) keywordEl.value = "";
    if (resultsEl) {
      resultsEl.innerHTML = `<div class="text-center py-3 text-muted">검색어를 입력 후 검색하세요.</div>`;
    }

    if (window.bootstrap?.Modal) new bootstrap.Modal(modalEl).show();
    else modalEl.classList.add("show");
  }

  async function runAddSearch(keyword) {
    const ctx = getContext();
    const resultsEl = document.getElementById("addSubAdminResults");
    if (!resultsEl) return;

    resultsEl.innerHTML = `<div class="text-center py-3 text-muted">검색 중...</div>`;

    try {
      const url = new URL(ctx.searchUrl, window.location.origin);
      url.searchParams.set("q", keyword);

      // head: branch scoped search
      if (ctx.userGrade === "head") url.searchParams.set("scope", "branch");

      const res = await fetch(url.toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      const parsed = await readJson(res);
      if (!res.ok || !parsed.data) {
        throw new Error(parsed.message || parsed.data?.message || `HTTP ${parsed.status}`);
      }
      const data = parsed.data;
      const list = Array.isArray(data?.results) ? data.results : [];

      if (!list.length) {
        resultsEl.innerHTML = `<div class="text-center py-3 text-danger">검색 결과가 없습니다.</div>`;
        return;
      }

      resultsEl.innerHTML = list.map(renderAddSearchItem).join("");
    } catch (err) {
      console.error("add search error:", err);
      resultsEl.innerHTML = `<div class="text-center text-danger py-3">검색 실패</div>`;
    }
  }

  function renderAddSearchItem(u0) {
    const u = u0 || {};
    const name = U.escHtml(u.name || "");
    const id = U.escHtml(u.id || "");
    const branch = U.escHtml(u.branch || "");
    const part = U.escHtml(u.part || "");
    const regist = U.escHtml(u.regist || "");
    const enter = U.escHtml(u.enter || "-");
    const quit = U.escHtml(u.quit || "재직중");

    return `
      <button type="button"
              class="list-group-item list-group-item-action addsub-result"
              data-user-id="${U.escHtml(u.id)}"
              data-user-name="${U.escHtml(u.name)}">
        <div class="d-flex justify-content-between">
          <span><strong>${name}</strong> (${id}) ${regist ? `(${regist})` : ""}</span>
          <small class="text-muted">${branch}</small>
        </div>
        <small class="text-muted">부서: ${part || "-"} / 입사일: ${enter} / 퇴사일: ${quit}</small>
      </button>
    `;
  }

  async function promoteToSubAdmin(userId) {
    const ctx = getContext();
    if (!ctx.addSubadminUrl) throw new Error("승격 URL이 설정되지 않았습니다.");
    return postForm(ctx.addSubadminUrl, { user_id: userId });
  }

  function bindAddSubAdminModal() {
    const ctx = getContext();
    if (!isAllowedGrade(ctx.userGrade)) return;

    const btn = document.getElementById("btnOpenAddSubAdmin");
    const form = document.getElementById("addSubAdminSearchForm");
    const keywordEl = document.getElementById("addSubAdminKeyword");
    const resultsEl = document.getElementById("addSubAdminResults");
    const modalEl = document.getElementById("addSubAdminModal");

    if (btn && btn.dataset.bound !== "1") {
      btn.dataset.bound = "1";
      btn.addEventListener("click", openAddModal);
    }

    if (form && form.dataset.bound !== "1") {
      form.dataset.bound = "1";
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const kw = U.str(keywordEl?.value);
        if (!kw) return alert("검색어를 입력하세요.");
        await runAddSearch(kw);
      });
    }

    if (resultsEl && resultsEl.dataset.bound !== "1") {
      resultsEl.dataset.bound = "1";
      resultsEl.addEventListener("click", async (e) => {
        const item = e.target?.closest?.(".addsub-result");
        if (!item) return;

        const userId = U.str(item.dataset.userId);
        const userName = U.str(item.dataset.userName);
        if (!userId) return;

        if (!confirm(`[${userName || userId}] 사용자를 중간관리자(leader)로 추가할까요?`)) return;

        try {
          await promoteToSubAdmin(userId);
          showToast("중간관리자로 추가되었습니다. (grade=leader)", true);

          // close modal
          try {
            const inst = window.bootstrap?.Modal?.getInstance?.(modalEl);
            if (inst) inst.hide();
          } catch (_) {}

          window.location.reload();
        } catch (err) {
          console.error("promote error:", err);
          showToast(err?.message || "승격 처리 중 오류가 발생했습니다.", false);
        }
      });
    }

    // reset modal UI on hide (bootstrap only)
    if (modalEl && modalEl.dataset.bound !== "1") {
      modalEl.dataset.bound = "1";
      modalEl.addEventListener("hidden.bs.modal", () => {
        if (keywordEl) keywordEl.value = "";
        if (resultsEl) resultsEl.innerHTML = `<div class="text-center py-3 text-muted">검색어를 입력 후 검색하세요.</div>`;
      });
    }
  }

  /* =========================================================
   * 8) Init (DOM ready + BFCache pageshow)
   * ========================================================= */
  function initAll() {
    const ctx = getContext();
    if (!isAllowedGrade(ctx.userGrade)) return;

    // (1) superuser selector cascade
    initChannelPartBranchSelectors();

    // (2) tables
    initTables();

    // (3) subadmin delegated events
    bindSubAdminDelegation();

    // (4) add modal
    bindAddSubAdminModal();
  }

  document.addEventListener("DOMContentLoaded", initAll);
  window.addEventListener("pageshow", (e) => { if (e.persisted) initAll(); });

})();
