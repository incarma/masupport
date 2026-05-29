/* django_ma/static/js/dash/dash_retention_page.js
 * IIFE — BFCache 대응, data-inited 가드
 * ─────────────────────────────────────────────────────────────
 * Boot: #dash-retention[data-*] 로만 URL/권한 읽음
 * API: GET /dash/api/retention/ → renderAll()
 * Upload: POST /dash/api/retention/upload/ (superuser only)
 */
(function () {
  "use strict";

  /* ── BFCache / 재진입 방지 ───────────────────────────── */
  const root = document.getElementById("dash-retention");
  if (!root || root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  /* ── URL (boot div dataset SSOT) ─────────────────────── */
  const API_URL    = root.dataset.retentionApiUrl;
  const UPLOAD_URL = root.dataset.uploadUrl;
  const USER_GRADE = root.dataset.userGrade          || "";

  /* ── DOM refs ────────────────────────────────────────── */
  const $ = (id) => document.getElementById(id);
  const els = {
    yearSel:     $("drYearSel"),
    monthSel:    $("drMonthSel"),
    lifeNlSel:   $("drLifeNlSel"),
    scopeType:   $("drScopeTypeSel"),
    scopeKey:    $("drScopeKeyInp"),
    qInp:        $("drQInp"),
    searchBtn:   $("drSearchBtn"),
    resetBtn:    $("drResetBtn"),
    asOfBadge:   $("drAsOfBadge"),
    overlay:     $("drOverlay"),
    errBanner:   $("drErrBanner"),
    kpiGrid:     $("drKpiGrid"),
    trendCanvas: $("drTrendChart"),
    roundCanvas: $("drRoundChart"),
    companyThead: $("drCompanyThead"),
    companyTbody: $("drCompanyTbody"),
    plannerThead: $("drPlannerThead"),
    plannerTbody: $("drPlannerTbody"),
    uploadPanel: $("drUploadPanel"),
    /* 생보 업로드 */
    lifeYm:      $("drLifeYmInput"),
    lifeDrop:    $("drLifeDropZone"),
    lifeFile:    $("drLifeFileInput"),
    lifeBtn:     $("drLifeUploadBtn"),
    lifeMsg:     $("drLifeUploadMsg"),
    lifeBadge:   $("drLifeUploadBadge"),
    lifeDropLbl: $("drLifeDropLabel"),
    /* 손보 업로드 */
    nlYm:        $("drNonlifeYmInput"),
    nlDrop:      $("drNonlifeDropZone"),
    nlFile:      $("drNonlifeFileInput"),
    nlBtn:       $("drNonlifeUploadBtn"),
    nlMsg:       $("drNonlifeUploadMsg"),
    nlBadge:     $("drNonlifeUploadBadge"),
    nlDropLbl:   $("drNonlifeDropLabel"),
  };

  /* ── Chart instances ─────────────────────────────────── */
  let trendChart = null;
  let roundChart = null;

  /* ── 색상 팔레트 ──────────────────────────────────────── */
  const ROUND_COLORS = [
    "#1e4a7b", "#3d7cc9", "#6fa8dc",
    "#d97744", "#e8a87c", "#a0522d",
    "#2d9d5d", "#7bc8a0",
  ];

  /* ── 유틸 ────────────────────────────────────────────── */
  function pad2(n) { return String(n).padStart(2, "0"); }

  function nowParts() {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  }

  function toNum(v, fb = 0) {
    const n = Number(v);
    return Number.isFinite(n) ? n : fb;
  }

  function fmtPct(v) {
    if (v === null || v === undefined) return "-";
    return toNum(v).toFixed(1) + "%";
  }

  function fmtPctDelta(v) {
    if (v === null || v === undefined) return "";
    const n = toNum(v);
    const sign = n >= 0 ? "+" : "";
    return sign + n.toFixed(1) + "%p";
  }

  function fmtCount(v) {
    if (v === null || v === undefined) return "-";
    return toNum(v).toLocaleString("ko-KR");
  }

  function showErr(msg) {
    if (!els.errBanner) return;
    els.errBanner.textContent = msg;
    els.errBanner.hidden = false;
  }

  function clearErr() {
    if (els.errBanner) els.errBanner.hidden = true;
  }

  function showLoading() { if (els.overlay) els.overlay.hidden = false; }
  function hideLoading() { if (els.overlay) els.overlay.hidden = true;  }

  function destroyChart(c) {
    if (c && typeof c.destroy === "function") c.destroy();
  }

  /* ── 필터 초기화 ──────────────────────────────────────── */
  function fillYears() {
    if (!els.yearSel) return;
    const now = nowParts();
    const initY = toNum(root.dataset.initialYear, now.year);
    els.yearSel.innerHTML = "";
    for (let y = now.year; y >= now.year - 5; y--) {
      const o = document.createElement("option");
      o.value = String(y);
      o.textContent = y + "년";
      if (y === initY) o.selected = true;
      els.yearSel.appendChild(o);
    }
  }

  function fillMonths() {
    if (!els.monthSel) return;
    const now = nowParts();
    const initM = toNum(root.dataset.initialMonth, now.month);
    els.monthSel.innerHTML = "";
    for (let m = 1; m <= 12; m++) {
      const o = document.createElement("option");
      o.value = String(m);
      o.textContent = m + "월";
      if (m === initM) o.selected = true;
      els.monthSel.appendChild(o);
    }
  }

  function initScopeFromBoot() {
    if (els.scopeType) els.scopeType.value = root.dataset.initialScopeType || "all";
    if (els.scopeKey)  els.scopeKey.value  = root.dataset.initialScopeKey  || "";
    /* head 권한이면 scope 고정 */
    if (USER_GRADE === "head") {
      if (els.scopeType) { els.scopeType.value = "branch"; els.scopeType.disabled = true; }
      if (els.scopeKey)  { els.scopeKey.value = root.dataset.userBranch || ""; els.scopeKey.disabled = true; }
    }
  }

  function currentYm() {
    return `${els.yearSel.value}-${pad2(els.monthSel.value)}`;
  }

  function getFilters() {
    return {
      ym:         currentYm(),
      life_nl:    els.lifeNlSel  ? els.lifeNlSel.value  : "",
      scope_type: els.scopeType  ? els.scopeType.value  : "all",
      scope_key:  els.scopeKey   ? els.scopeKey.value.trim()  : "",
      q:          els.qInp       ? els.qInp.value.trim()      : "",
    };
  }

  /* ── KPI 렌더 ────────────────────────────────────────── */
  function renderKpis(rounds, summary, prevSummary) {
    if (!els.kpiGrid) return;
    els.kpiGrid.innerHTML = "";

    if (!rounds || rounds.length === 0) {
      els.kpiGrid.innerHTML = '<p class="text-muted text-center py-3">데이터가 없습니다.</p>';
      return;
    }

    rounds.forEach((rnd) => {
      const cur  = (summary      || {})[rnd];
      const prev = (prevSummary  || {})[rnd];
      const rate     = cur  ? toNum(cur.rate)  : null;
      const prevRate = prev ? toNum(prev.rate) : null;
      const delta = (rate !== null && prevRate !== null) ? rate - prevRate : null;

      const art = document.createElement("article");
      art.className = "card shadow-sm dr-kpi";
      art.innerHTML = `
        <div class="card-body">
          <div class="dr-kpi__label">${rnd}회차 유지율</div>
          <div class="dr-kpi__value ${rate !== null && rate < 80 ? "is-low" : ""}">${fmtPct(rate)}</div>
          <div class="dr-kpi__sub ${delta !== null ? (delta >= 0 ? "is-up" : "is-dn") : ""}">
            전월 대비 ${delta !== null ? fmtPctDelta(delta) : "-"}
          </div>
          <div class="dr-kpi__count">${fmtCount(cur ? cur.total_count : null)}건</div>
        </div>`;
      els.kpiGrid.appendChild(art);
    });
  }

  /* ── 추이 차트 ───────────────────────────────────────── */
  function renderTrendChart(trend) {
    if (!els.trendCanvas || typeof Chart === "undefined") return;
    destroyChart(trendChart);

    const labels = (trend && trend.labels) ? trend.labels : [];
    const byRound = (trend && trend.by_round) ? trend.by_round : {};
    const roundKeys = Object.keys(byRound).sort((a, b) => Number(a) - Number(b));

    const datasets = roundKeys.map((k, i) => ({
      label:           k + "회차",
      data:            byRound[k],
      borderColor:     ROUND_COLORS[i % ROUND_COLORS.length],
      backgroundColor: ROUND_COLORS[i % ROUND_COLORS.length] + "22",
      tension:         0.25,
      fill:            false,
    }));

    trendChart = new Chart(els.trendCanvas, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "top" } },
        scales: {
          y: {
            suggestedMin: 50, suggestedMax: 100,
            ticks: { callback: (v) => v + "%" },
          },
        },
      },
    });
  }

  /* ── 회차별 막대 차트 ────────────────────────────────── */
  function renderRoundChart(rounds, summary) {
    if (!els.roundCanvas || typeof Chart === "undefined") return;
    destroyChart(roundChart);

    const labels  = rounds.map((r) => r + "회차");
    const values  = rounds.map((r) => {
      const s = (summary || {})[r];
      return s ? toNum(s.rate) : null;
    });
    const colors  = rounds.map((_, i) => ROUND_COLORS[i % ROUND_COLORS.length]);

    roundChart = new Chart(els.roundCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "유지율",
          data:  values,
          backgroundColor: colors,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            suggestedMin: 50, suggestedMax: 100,
            ticks: { callback: (v) => v + "%" },
          },
        },
      },
    });
  }

  /* ── 테이블 헤더 동적 생성 ───────────────────────────── */
  function buildTableHeader(fixedCols, rounds) {
    const tr = document.createElement("tr");
    fixedCols.forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col;
      tr.appendChild(th);
    });
    rounds.forEach((rnd) => {
      const th = document.createElement("th");
      th.textContent = rnd + "회차";
      th.style.textAlign = "center";
      tr.appendChild(th);
    });
    return tr;
  }

  /* ── 보험사별 테이블 ──────────────────────────────────── */
  function renderCompanyTable(rounds, byInsurer) {
    if (!els.companyThead || !els.companyTbody) return;

    els.companyThead.innerHTML = "";
    els.companyTbody.innerHTML = "";

    const fixed = ["순위", "보험회사", "계약수"];
    els.companyThead.appendChild(buildTableHeader(fixed, rounds));

    if (!Array.isArray(byInsurer) || byInsurer.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="${fixed.length + rounds.length}" class="text-center text-muted py-4">데이터가 없습니다.</td>`;
      els.companyTbody.appendChild(tr);
      return;
    }

    byInsurer.forEach((row, idx) => {
      const tr = document.createElement("tr");
      const cells = [
        `<td class="text-center">${idx + 1}</td>`,
        `<td>${row.insurer || "-"}</td>`,
        `<td class="text-end">${fmtCount(row.total_count)}</td>`,
      ];
      rounds.forEach((rnd) => {
        const r = (row.rounds || {})[rnd];
        const cls = r !== null && r !== undefined && r < 80 ? " class=\"dr-val-low\"" : "";
        cells.push(`<td${cls} style="text-align:center">${fmtPct(r)}</td>`);
      });
      tr.innerHTML = cells.join("");
      els.companyTbody.appendChild(tr);
    });
  }

  /* ── 설계사별 테이블 ──────────────────────────────────── */
  function renderPlannerTable(rounds, byPlanner) {
    if (!els.plannerThead || !els.plannerTbody) return;

    els.plannerThead.innerHTML = "";
    els.plannerTbody.innerHTML = "";

    const fixed = ["순위", "설계사", "소속", "파트너", "계약수"];
    els.plannerThead.appendChild(buildTableHeader(fixed, rounds));

    if (!Array.isArray(byPlanner) || byPlanner.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="${fixed.length + rounds.length}" class="text-center text-muted py-4">데이터가 없습니다.</td>`;
      els.plannerTbody.appendChild(tr);
      return;
    }

    byPlanner.forEach((row, idx) => {
      const tr = document.createElement("tr");
      const cells = [
        `<td class="text-center">${idx + 1}</td>`,
        `<td>${row.name || row.emp_id || "-"}</td>`,
        `<td>${row.part || "-"}</td>`,
        `<td>${row.branch || "-"}</td>`,
        `<td class="text-end">${fmtCount(row.total_count)}</td>`,
      ];
      rounds.forEach((rnd) => {
        const r = (row.rounds || {})[rnd];
        const cls = r !== null && r !== undefined && r < 80 ? " class=\"dr-val-low\"" : "";
        cells.push(`<td${cls} style="text-align:center">${fmtPct(r)}</td>`);
      });
      tr.innerHTML = cells.join("");
      els.plannerTbody.appendChild(tr);
    });
  }

  /* ── renderAll ───────────────────────────────────────── */
  function renderAll(payload) {
    if (!payload) return;
    const d = payload;

    if (els.asOfBadge) els.asOfBadge.textContent = `기준월 ${d.ym || "-"}`;

    const rounds    = d.rounds    || [];
    const summary   = d.summary   || {};

    renderKpis(rounds, summary, null);
    renderTrendChart(d.trend || {});
    renderRoundChart(rounds, summary);
    renderCompanyTable(rounds, d.by_insurer || []);
    renderPlannerTable(rounds, d.by_planner || []);
  }

  /* ── API 조회 ─────────────────────────────────────────── */
  async function loadDashboard() {
    clearErr();
    showLoading();
    try {
      const f = getFilters();
      const params = new URLSearchParams({
        ym:         f.ym,
        life_nl:    f.life_nl,
        scope_type: f.scope_type,
        scope_key:  f.scope_key,
        q:          f.q,
      });
      const res  = await fetch(`${API_URL}?${params}`, {
        credentials:   "same-origin",
        headers:       { "X-Requested-With": "XMLHttpRequest" },
      });
      const json = await res.json();
      if (!json.ok) {
        showErr(json.message || "조회 실패");
        return;
      }
      renderAll(json.data);
    } catch (e) {
      console.error("[dr] loadDashboard error", e);
      showErr("유지율 데이터를 불러오지 못했습니다.");
    } finally {
      hideLoading();
    }
  }

  /* ── 필터 초기화 ──────────────────────────────────────── */
  function resetFilters() {
    const now = nowParts();
    if (els.yearSel)  els.yearSel.value  = String(now.year);
    if (els.monthSel) els.monthSel.value = String(now.month);
    if (els.lifeNlSel) els.lifeNlSel.value = "";
    if (USER_GRADE !== "head") {
      if (els.scopeType) els.scopeType.value = "all";
      if (els.scopeKey)  els.scopeKey.value  = "";
    }
    if (els.qInp) els.qInp.value = "";
    loadDashboard();
  }

  /* ════════════════════════════════════════════════════════
     업로드 모듈
  ════════════════════════════════════════════════════════ */
  function initUploadPanel() {
    if (USER_GRADE !== "superuser") return;
    if (els.uploadPanel) els.uploadPanel.hidden = false;

    function initSlot(cfg) {
      const { ymEl, dropEl, fileEl, btnEl, msgEl, badgeEl, dropLblEl, lifeNl } = cfg;
      if (!fileEl || !btnEl) return;

      /* 파일 선택 시 버튼 활성 */
      fileEl.addEventListener("change", () => {
        const f = fileEl.files[0];
        if (!f) return;
        if (dropLblEl) dropLblEl.textContent = "✅ " + f.name;
        btnEl.disabled = false;
      });

      /* 드래그&드롭 */
      if (dropEl) {
        dropEl.addEventListener("dragover", (e) => { e.preventDefault(); dropEl.classList.add("dragover"); });
        dropEl.addEventListener("dragleave", ()  => dropEl.classList.remove("dragover"));
        dropEl.addEventListener("drop", (e) => {
          e.preventDefault();
          dropEl.classList.remove("dragover");
          const f = e.dataTransfer.files[0];
          if (!f) return;
          fileEl.files = e.dataTransfer.files;  // 가능한 브라우저만
          if (dropLblEl) dropLblEl.textContent = "✅ " + f.name;
          btnEl.disabled = false;
        });
      }

      /* 업로드 */
      btnEl.addEventListener("click", async () => {
        if (btnEl.dataset.submitting === "1") return;
        const f = fileEl.files[0];
        if (!f) return;

        const ym = ymEl ? ymEl.value.trim() : "";
        const fd = new FormData();
        fd.append("excel_file", f);
        fd.append("life_nl", lifeNl);

        btnEl.dataset.submitting = "1";
        btnEl.disabled = true;
        if (msgEl) { msgEl.textContent = "업로드 중..."; msgEl.className = "dr-upload-msg"; }

        try {
          const res  = await fetch(UPLOAD_URL, {
            method:      "POST",
            credentials: "same-origin",
            headers:     { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": window.csrfToken },
            body:        fd,
          });
          const json = await res.json();

          if (json.ok) {
            const s = json.summary || {};
            const msg = `완료 — ${s.upserted || 0}건 저장 (스킵 ${s.skipped || 0}건)`;
            if (msgEl) { msgEl.textContent = msg; msgEl.className = "dr-upload-msg is-ok"; }
            if (badgeEl) badgeEl.textContent = s.yms ? s.yms.join(", ") : "-";
            /* 업로드 후 대시보드 자동 갱신 */
            loadDashboard();
          } else {
            if (msgEl) { msgEl.textContent = json.message || "업로드 실패"; msgEl.className = "dr-upload-msg is-err"; }
          }
        } catch (e) {
          if (msgEl) { msgEl.textContent = "네트워크 오류"; msgEl.className = "dr-upload-msg is-err"; }
          console.error("[dr] upload error", e);
        } finally {
          btnEl.dataset.submitting = "";
          btnEl.disabled = false;
        }
      });
    }

    initSlot({
      ymEl:      els.lifeYm,
      dropEl:    els.lifeDrop,
      fileEl:    els.lifeFile,
      btnEl:     els.lifeBtn,
      msgEl:     els.lifeMsg,
      badgeEl:   els.lifeBadge,
      dropLblEl: els.lifeDropLbl,
      lifeNl:    "생보",
    });

    initSlot({
      ymEl:      els.nlYm,
      dropEl:    els.nlDrop,
      fileEl:    els.nlFile,
      btnEl:     els.nlBtn,
      msgEl:     els.nlMsg,
      badgeEl:   els.nlBadge,
      dropLblEl: els.nlDropLbl,
      lifeNl:    "손보",
    });
  }

  /* ── 이벤트 바인딩 ───────────────────────────────────── */
  function bindEvents() {
    if (els.searchBtn) els.searchBtn.addEventListener("click", loadDashboard);
    if (els.resetBtn)  els.resetBtn.addEventListener("click",  resetFilters);

    [els.scopeKey, els.qInp].forEach((el) => {
      if (!el) return;
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); loadDashboard(); }
      });
    });

    /* BFCache 복원 시 재초기화 */
    window.addEventListener("pageshow", (e) => {
      if (e.persisted) { root.dataset.inited = ""; }
    });
  }

  /* ── init ────────────────────────────────────────────── */
  function init() {
    fillYears();
    fillMonths();
    initScopeFromBoot();
    bindEvents();
    initUploadPanel();
    loadDashboard();
  }

  init();
})();