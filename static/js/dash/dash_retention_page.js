/* django_ma/static/js/dash/dash_retention_page.js */
(function () {
  const root = document.getElementById("dash-retention");
  if (!root || root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  const els = {
    year: document.getElementById("retentionYearSelect"),
    month: document.getElementById("retentionMonthSelect"),
    scopeType: document.getElementById("retentionScopeTypeSelect"),
    scopeKey: document.getElementById("retentionScopeKeyInput"),
    keyword: document.getElementById("retentionKeywordInput"),
    searchBtn: document.getElementById("retentionSearchBtn"),
    resetBtn: document.getElementById("retentionResetBtn"),
    asOfText: document.getElementById("retentionAsOfText"),
    overlay: document.getElementById("retentionLoadingOverlay"),
    kpi13m: document.getElementById("kpi13m"),
    kpi13mSub: document.getElementById("kpi13mSub"),
    kpi25m: document.getElementById("kpi25m"),
    kpi25mSub: document.getElementById("kpi25mSub"),
    kpiAvg: document.getElementById("kpiAvg"),
    kpiAvgSub: document.getElementById("kpiAvgSub"),
    kpiCount: document.getElementById("kpiCount"),
    kpiCountSub: document.getElementById("kpiCountSub"),
    trendCanvas: document.getElementById("retentionTrendChart"),
    bucketCanvas: document.getElementById("retentionBucketChart"),
    companyBody: document.querySelector("#retentionCompanyTable tbody"),
    productBody: document.querySelector("#retentionProductTable tbody"),
    plannerBody: document.querySelector("#retentionPlannerTable tbody"),
  };

  let trendChart = null;
  let bucketChart = null;

  function showLoading() {
    if (els.overlay) els.overlay.hidden = false;
  }

  function hideLoading() {
    if (els.overlay) els.overlay.hidden = true;
  }

  function destroyChart(instance) {
    if (instance && typeof instance.destroy === "function") {
      instance.destroy();
    }
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function getNowParts() {
    const now = new Date();
    return {
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    };
  }

  function toNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatPercent(value) {
    if (value === null || value === undefined || value === "") return "-";
    return `${toNumber(value).toFixed(1)}%`;
  }

  function formatSignedPercent(value) {
    if (value === null || value === undefined || value === "") return "-";
    const n = toNumber(value);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(1)}%`;
  }

  function formatCount(value) {
    if (value === null || value === undefined || value === "") return "-";
    return toNumber(value).toLocaleString("ko-KR");
  }

  function currentYm() {
    return `${els.year.value}-${pad2(els.month.value)}`;
  }

  function setAsOfText(ym) {
    if (els.asOfText) {
      els.asOfText.textContent = `기준월 ${ym}`;
    }
  }

  function fillYearOptions() {
    if (!els.year) return;

    const now = getNowParts();
    const currentYear = now.year;
    const initialYear = toNumber(root.dataset.initialYear || currentYear, currentYear);

    els.year.innerHTML = "";
    for (let y = currentYear; y >= currentYear - 5; y -= 1) {
      const option = document.createElement("option");
      option.value = String(y);
      option.textContent = `${y}년`;
      if (y === initialYear) {
        option.selected = true;
      }
      els.year.appendChild(option);
    }
  }

  function fillMonthOptions() {
    if (!els.month) return;

    const now = getNowParts();
    const currentMonth = now.month;
    const initialMonth = toNumber(root.dataset.initialMonth || currentMonth, currentMonth);

    els.month.innerHTML = "";
    for (let m = 1; m <= 12; m += 1) {
      const option = document.createElement("option");
      option.value = String(m);
      option.textContent = `${m}월`;
      if (m === initialMonth) {
        option.selected = true;
      }
      els.month.appendChild(option);
    }
  }

  function initScope() {
    if (els.scopeType) {
      els.scopeType.value = root.dataset.initialScopeType || "all";
    }
    if (els.scopeKey) {
      els.scopeKey.value = root.dataset.initialScopeKey || "";
    }
  }

  function getFilters() {
    return {
      ym: currentYm(),
      scopeType: els.scopeType ? els.scopeType.value : "all",
      scopeKey: els.scopeKey ? els.scopeKey.value.trim() : "",
      keyword: els.keyword ? els.keyword.value.trim() : "",
    };
  }

  function setKpis(summary) {
    const data = summary || {};

    if (els.kpi13m) {
      els.kpi13m.textContent = formatPercent(data.m13);
    }
    if (els.kpi13mSub) {
      els.kpi13mSub.textContent = `전월 대비 ${formatSignedPercent(data.m13Delta)}`;
    }

    if (els.kpi25m) {
      els.kpi25m.textContent = formatPercent(data.m25);
    }
    if (els.kpi25mSub) {
      els.kpi25mSub.textContent = `전월 대비 ${formatSignedPercent(data.m25Delta)}`;
    }

    if (els.kpiAvg) {
      els.kpiAvg.textContent = formatPercent(data.avg);
    }
    if (els.kpiAvgSub) {
      els.kpiAvgSub.textContent = `전체 평균 ${formatPercent(data.overallAvg)}`;
    }

    if (els.kpiCount) {
      els.kpiCount.textContent = formatCount(data.contractCount);
    }
    if (els.kpiCountSub) {
      els.kpiCountSub.textContent = "조회 범위 기준";
    }
  }

  function renderTableRows(tbody, rows, columns) {
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!Array.isArray(rows) || rows.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="${columns.length}" class="is-empty">데이터가 없습니다.</td>`;
      tbody.appendChild(tr);
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = columns
        .map((key) => `<td>${row[key] ?? "-"}</td>`)
        .join("");
      tbody.appendChild(tr);
    });
  }

  function renderTrendChart(trend) {
    if (!els.trendCanvas || typeof Chart === "undefined") return;

    destroyChart(trendChart);

    trendChart = new Chart(els.trendCanvas, {
      type: "line",
      data: {
        labels: Array.isArray(trend.labels) ? trend.labels : [],
        datasets: [
          {
            label: "13회차",
            data: Array.isArray(trend.m13) ? trend.m13 : [],
            tension: 0.25,
          },
          {
            label: "25회차",
            data: Array.isArray(trend.m25) ? trend.m25 : [],
            tension: 0.25,
          },
          {
            label: "평균",
            data: Array.isArray(trend.avg) ? trend.avg : [],
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            position: "top",
          },
        },
        scales: {
          y: {
            suggestedMin: 0,
            suggestedMax: 100,
          },
        },
      },
    });
  }

  function renderBucketChart(bucket) {
    if (!els.bucketCanvas || typeof Chart === "undefined") return;

    destroyChart(bucketChart);

    bucketChart = new Chart(els.bucketCanvas, {
      type: "bar",
      data: {
        labels: Array.isArray(bucket.labels) ? bucket.labels : [],
        datasets: [
          {
            label: "유지율",
            data: Array.isArray(bucket.values) ? bucket.values : [],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
        },
        scales: {
          y: {
            suggestedMin: 0,
            suggestedMax: 100,
          },
        },
      },
    });
  }

  function buildDemoPayload(filters) {
    return {
      ym: filters.ym,
      summary: {
        m13: 87.2,
        m13Delta: 1.4,
        m25: 81.6,
        m25Delta: -0.6,
        avg: 84.4,
        overallAvg: 82.9,
        contractCount: 1284,
      },
      trend: {
        labels: ["1월", "2월", "3월", "4월", "5월", "6월"],
        m13: [84.1, 84.9, 85.5, 86.2, 86.8, 87.2],
        m25: [79.4, 80.1, 80.3, 80.9, 82.0, 81.6],
        avg: [81.8, 82.5, 82.9, 83.6, 84.4, 84.4],
      },
      bucket: {
        labels: ["13회", "25회", "37회"],
        values: [87.2, 81.6, 78.4],
      },
      companies: [
        { rank: 1, company: "삼성생명", m13: "88.4%", m25: "83.0%", avg: "85.7%", count: "312" },
        { rank: 2, company: "DB손해보험", m13: "87.5%", m25: "82.3%", avg: "84.9%", count: "276" },
        { rank: 3, company: "한화생명", m13: "85.2%", m25: "80.4%", avg: "82.8%", count: "194" },
      ],
      products: [
        { rank: 1, company: "삼성생명", product: "The좋은종신", m13: "89.2%", m25: "84.4%", count: "82" },
        { rank: 2, company: "DB손해보험", product: "참좋은건강", m13: "88.7%", m25: "81.9%", count: "76" },
        { rank: 3, company: "한화생명", product: "스마트케어", m13: "84.9%", m25: "80.1%", count: "55" },
      ],
      planners: [
        { rank: 1, planner: "홍길동", affiliation: "MA사업4부 / 강남지점", m13: "91.1%", m25: "86.3%", count: "48" },
        { rank: 2, planner: "김영희", affiliation: "MA사업4부 / 서초지점", m13: "89.8%", m25: "84.9%", count: "43" },
        { rank: 3, planner: "이철수", affiliation: "MA사업5부 / 분당지점", m13: "87.3%", m25: "82.0%", count: "39" },
      ],
    };
  }

  function renderAll(payload) {
    const safePayload = payload || {};

    setAsOfText(safePayload.ym || currentYm());
    setKpis(safePayload.summary || {});
    renderTrendChart(safePayload.trend || {});
    renderBucketChart(safePayload.bucket || {});

    renderTableRows(
      els.companyBody,
      safePayload.companies || [],
      ["rank", "company", "m13", "m25", "avg", "count"]
    );

    renderTableRows(
      els.productBody,
      safePayload.products || [],
      ["rank", "company", "product", "m13", "m25", "count"]
    );

    renderTableRows(
      els.plannerBody,
      safePayload.planners || [],
      ["rank", "planner", "affiliation", "m13", "m25", "count"]
    );
  }

  async function loadDashboard() {
    showLoading();

    try {
      const filters = getFilters();

      /*
        TODO:
        실제 API 연결 시 아래 demo payload 대신 fetch 결과로 대체
        예시:
        const url = `/dash/api/retention/?ym=${encodeURIComponent(filters.ym)}&scope_type=${encodeURIComponent(filters.scopeType)}&scope_key=${encodeURIComponent(filters.scopeKey)}&q=${encodeURIComponent(filters.keyword)}`;
        const response = await fetch(url, { credentials: "same-origin" });
        const payload = await response.json();
      */
      const payload = buildDemoPayload(filters);
      renderAll(payload);
    } catch (error) {
      console.error("[dash_retention] load failed", error);
      alert("유지율 데이터를 불러오지 못했습니다.");
    } finally {
      hideLoading();
    }
  }

  function resetFilters() {
    const now = getNowParts();

    if (els.year) {
      els.year.value = String(now.year);
    }
    if (els.month) {
      els.month.value = String(now.month);
    }
    if (els.scopeType) {
      els.scopeType.value = "all";
    }
    if (els.scopeKey) {
      els.scopeKey.value = "";
    }
    if (els.keyword) {
      els.keyword.value = "";
    }

    loadDashboard();
  }

  function bindEnterSearch(element) {
    if (!element) return;

    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        loadDashboard();
      }
    });
  }

  function bindEvents() {
    if (els.searchBtn) {
      els.searchBtn.addEventListener("click", loadDashboard);
    }

    if (els.resetBtn) {
      els.resetBtn.addEventListener("click", resetFilters);
    }

    bindEnterSearch(els.scopeKey);
    bindEnterSearch(els.keyword);
  }

  function init() {
    fillYearOptions();
    fillMonthOptions();
    initScope();
    bindEvents();
    loadDashboard();
  }

  init();
})();