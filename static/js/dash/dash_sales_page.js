// static/js/dash/dash_sales_page.js
(function () {
  "use strict";

  // =========================================================
  // Constants
  // =========================================================
  function getForecastBaseUrl() {
   const root = getRoot();
   const u = (root?.dataset?.forecastUrl || "").trim();
   return u || "/dash/api/forecast/";
 }

  const FORECAST_TTL_MS = 60 * 1000; // 1분(페이지 내 재호출 방지용)

  // Chart instance keys
  const CHART_KEYS = {
    long: "__dailyCumsumChart",
    car: "__carDailyCumsumChart",
    nonlife: "__nonlifeDailyCumsumChart",
    life: "__lifeDailyCumsumChart",
  };

  // =========================================================
  // JSON helpers
  // =========================================================
  function safeJsonFromScriptTag(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent || "");
    } catch (e) {
      return fallback;
    }
  }

  // =========================================================
  // Root helpers
  // =========================================================
  function getRoot() {
    return document.getElementById("dash-sales");
  }

  function getStaticVer() {
    const root = getRoot();
    // data-static-version / data-static-ver 둘 다 지원
    return (root?.dataset?.staticVersion || root?.dataset?.staticVer || "dev").trim();
  }

  function debugOnce(payload) {
    if (window.__dashSalesDebugOnce) return;
    window.__dashSalesDebugOnce = true;
    try {
      console.log("[dash_sales_page] debug once", payload);
    } catch (e) {}
  }

  // =========================================================
  // Part -> Branch sync
  // =========================================================
  function initPartBranchSync(root) {
    const partEl = document.getElementById("partSelect");
    const branchEl = document.getElementById("branchSelect");
    if (!partEl || !branchEl) return;

    const partBranchMap = safeJsonFromScriptTag("part-branch-map", {});
    const branchAll = safeJsonFromScriptTag("branch-options-all", []);

    const initialPart = (root?.dataset?.initialPart || "").trim();
    const initialBranch = (root?.dataset?.initialBranch || "").trim();

    function rebuildBranchOptions(branches, selected) {
      branchEl.innerHTML = "";

      const optAll = document.createElement("option");
      optAll.value = "";
      optAll.textContent = "전체";
      optAll.selected = !selected;
      branchEl.appendChild(optAll);

      (branches || []).forEach((b) => {
        const v = (b || "").trim();
        if (!v) return;
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        opt.selected = selected === v;
        branchEl.appendChild(opt);
      });
    }

    function syncBranches(forceSelected) {
      const part = (partEl.value || "").trim();
      const selected = (forceSelected || branchEl.value || initialBranch || "").trim();

      if (!part) {
        rebuildBranchOptions(branchAll, branchAll.includes(selected) ? selected : "");
        return;
      }

      const branches = partBranchMap[part] || [];
      rebuildBranchOptions(branches, branches.includes(selected) ? selected : "");
    }

    // init
    if (initialPart) partEl.value = initialPart;
    syncBranches(initialBranch);

    partEl.addEventListener("change", function () {
      branchEl.value = ""; // 부서 바뀌면 지점은 전체로
      syncBranches("");
    });
  }

  // =========================================================
  // Life_nl -> Insurer sync (즉시 연동)
  // =========================================================
  function initLifeNlInsurerSync(root) {
    const lifeEl = document.getElementById("lifeNlSelect");
    const insurerEl = document.getElementById("insurerSelect");
    if (!lifeEl || !insurerEl) return;

    const map = safeJsonFromScriptTag("life-nl-insurer-map", {});
    const initialLifeNl = (root?.dataset?.initialLifeNl || "").trim();
    const initialInsurer = (root?.dataset?.initialInsurer || "").trim();

    function uniqClean(arr) {
      const out = [];
      const seen = new Set();
      (arr || []).forEach((x) => {
        const v = (x || "").trim();
        if (!v) return;
        if (seen.has(v)) return;
        seen.add(v);
        out.push(v);
      });
      return out;
    }

    function rebuildInsurerOptions(insurers, selected) {
      insurerEl.innerHTML = "";

      const optAll = document.createElement("option");
      optAll.value = "";
      optAll.textContent = "전체";
      optAll.selected = !selected;
      insurerEl.appendChild(optAll);

      (insurers || []).forEach((ins) => {
        const v = (ins || "").trim();
        if (!v) return;
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        opt.selected = selected === v;
        insurerEl.appendChild(opt);
      });
    }

    function getInsurersByLifeNl(lifeNl) {
      const ln = (lifeNl || "").trim();
      if (!ln) {
        const all = [].concat(map["손보"] || [], map["생보"] || [], map["자동차"] || []);
        return uniqClean(all);
      }
      return uniqClean(map[ln] || []);
    }

    function syncInsurers(forceSelected) {
      const ln = (lifeEl.value || "").trim();
      const insurers = getInsurersByLifeNl(ln);

      const selected = (forceSelected || insurerEl.value || initialInsurer || "").trim();
      const finalSelected = insurers.includes(selected) ? selected : "";
      rebuildInsurerOptions(insurers, finalSelected);
    }

    // init
    if (initialLifeNl && !lifeEl.value) lifeEl.value = initialLifeNl;
    syncInsurers(initialInsurer);

    lifeEl.addEventListener("change", function () {
      insurerEl.value = "";
      syncInsurers("");
    });
  }

    // =========================================================
  // Chart helpers
  // =========================================================
  function showWarnById(warnId, msg) {
    const warnEl = document.getElementById(warnId);
    if (!warnEl) return;
    warnEl.style.display = "block";
    warnEl.textContent = msg;
  }

  function hideWarnById(warnId) {
    const warnEl = document.getElementById(warnId);
    if (!warnEl) return;
    warnEl.style.display = "none";
    warnEl.textContent = "";
  }

  function destroyChart(chartKey) {
    const inst = window[chartKey];
    if (!inst) return;
    try {
      inst.destroy();
    } catch (e) {}
    window[chartKey] = null;
  }

  function toDayOfMonthLabels(dateLabels) {
    return (dateLabels || []).map((s) => {
      const m = String(s || "").match(/-(\d{2})$/);
      if (!m) return s;
      return String(parseInt(m[1], 10));
    });
  }

  // ✅ "마지막 영수일자"를 cumsum의 마지막 '증가' 지점으로 추정하고 이후 null
  function trimAfterLastIncreaseToNull(cumsum) {
    if (!Array.isArray(cumsum) || cumsum.length === 0) return cumsum;

    let lastIdx = -1;
    for (let i = 0; i < cumsum.length; i++) {
      const cur = Number(cumsum[i] ?? 0);
      const prev = i === 0 ? 0 : Number(cumsum[i - 1] ?? 0);
      if (cur - prev !== 0) lastIdx = i;
    }

    if (lastIdx < 0) return cumsum.map(() => null); // 월 전체 0이면 전부 null

    return cumsum.map((v, i) => (i <= lastIdx ? v : null));
  }

  function hasAnyIncrease(cumsum) {
    if (!Array.isArray(cumsum) || cumsum.length === 0) return false;
    for (let i = 0; i < cumsum.length; i++) {
      const cur = Number(cumsum[i] ?? 0);
      const prev = i === 0 ? 0 : Number(cumsum[i - 1] ?? 0);
      if (cur - prev !== 0) return true;
    }
    return false;
  }

  function lastIncreaseIndex(cumsum) {
    if (!Array.isArray(cumsum) || cumsum.length === 0) return -1;
    let lastIdx = -1;
    for (let i = 0; i < cumsum.length; i++) {
      const cur = Number(cumsum[i] ?? 0);
      const prev = i === 0 ? 0 : Number(cumsum[i - 1] ?? 0);
      if (cur - prev !== 0) lastIdx = i;
    }
    return lastIdx;
  }

  // =========================================================
  // Render helpers
  // =========================================================
  function normalizeSeriesToLen(arr, len) {
    if (!Array.isArray(arr) || arr.length === 0) return new Array(len).fill(null);
    if (arr.length === len) return arr;
    if (arr.length < len) return arr.concat(new Array(len - arr.length).fill(null));
    return arr.slice(0, len);
  }

  function pad2(n) {
    const x = String(n ?? "");
    return x.length === 1 ? "0" + x : x;
  }

  // =========================================================
  // Money display helpers
  // - 차트 표시 전용
  // - 원본 데이터/계산값은 유지하고, UI에서만 천원 단위 절사
  //   예) 10,000,000 -> 10,000
  // =========================================================
  function toThousandWonFloor(value) {
    if (value === null || typeof value === "undefined") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return Math.trunc(n / 1000);
  }

  function mapSeriesToThousandWon(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((v) => toThousandWonFloor(v));
  }

  function formatThousandWon(value) {
    const v = toThousandWonFloor(value);
    if (v === null) return "-";
    return v.toLocaleString();
  }

  function inferYmFromLabels(rawLabels) {
    // rawLabels: ["YYYY-MM-DD", ...]
    if (!Array.isArray(rawLabels) || rawLabels.length === 0) return "";
    const s = String(rawLabels[0] || "");
    const m = s.match(/^(\d{4}-\d{2})-\d{2}$/);
    return m ? m[1] : "";
  }

  function getFiltersFromDom(root) {
    const part = (document.getElementById("partSelect")?.value || "").trim();
    const branch = (document.getElementById("branchSelect")?.value || "").trim();
    const lifeNl = (document.getElementById("lifeNlSelect")?.value || "").trim();
    const insurer = (document.getElementById("insurerSelect")?.value || "").trim();

    // q는 서버 캐시 파편화 방지 차원에서 예측에는 보통 제외 권장.
    // 필요하면 root.dataset.initialQ 같은 걸 추가해서 포함시키면 됨.
    return { part, branch, life_nl: lifeNl, insurer };
  }

  // =========================================================
  // Forecast fetching (cached)
  // =========================================================
  const __forecastCache = {
    at: 0,
    key: "",
    payload: null,
  };

  function buildForecastUrl({ ym, asofDay, scope, part, branch }) {
    const base = getForecastBaseUrl();
    const url = new URL(base, window.location.origin);

    url.searchParams.set("ym", ym);
    url.searchParams.set("asof_day", String(asofDay || 1));

    // scope: branch/part/all 등 (너가 서버에서 정의)
    url.searchParams.set("scope", scope || "all");

    if (part) url.searchParams.set("part", part);
    if (branch) url.searchParams.set("branch", branch);

    return url.toString();
  }

  async function fetchForecastOnce({ ym, asofDay, scope, part, branch }) {
    const now = Date.now();
    const key = [ym, asofDay, scope || "all", part || "", branch || ""].join("|");

    if (__forecastCache.payload && __forecastCache.key === key && now - __forecastCache.at < FORECAST_TTL_MS) {
      return __forecastCache.payload;
    }

    const url = buildForecastUrl({ ym, asofDay, scope, part, branch });

    try {
      const res = await fetch(url, { method: "GET", headers: { "Accept": "application/json" } });
      const ct = String(res.headers.get("content-type") || "").toLowerCase();
      if (!ct.includes("application/json")) {
        // 로그인 리다이렉트/에러 페이지(HTML) 등
        const text = await res.text().catch(() => "");
        console.warn("[Forecast] non-json response", { status: res.status, ct, head: text.slice(0, 120) });
        __forecastCache.at = now;
        __forecastCache.key = key;
        __forecastCache.payload = null;
        return null;
      }
      const data = await res.json().catch(() => null);

      if (!res.ok || !data || data.ok !== true) {
        __forecastCache.at = now;
        __forecastCache.key = key;
        __forecastCache.payload = null;
        return null;
      }

      __forecastCache.at = now;
      __forecastCache.key = key;
      // ✅ 서버는 {ok:true, data:{...}} 형태
      __forecastCache.payload = data.data || null;
      return __forecastCache.payload;
    } catch (e) {
      __forecastCache.at = now;
      __forecastCache.key = key;
      __forecastCache.payload = null;
      return null;
    }
  }

  // =========================================================
  // Forecast -> datasets builder
  //   - 입력: mean/lo/hi (cumsum 기준) OR 일매출 기준이면 서버에서 cumsum으로 변환해서 내려주는 걸 권장
  // =========================================================
  function buildForecastDatasets(seriesObj, labelsLen, asofIdx) {
    // seriesObj: {mean:[..], lo:[..], hi:[..]}
    if (!seriesObj || typeof seriesObj !== "object") return null;

    const mean = normalizeSeriesToLen(seriesObj.mean, labelsLen);
    const lo = normalizeSeriesToLen(seriesObj.lo, labelsLen);
    const hi = normalizeSeriesToLen(seriesObj.hi, labelsLen);

    // ✅ asofIdx(0-based) 이전은 실제/과거 구간이므로 null로 날려서 “미래만” 보이게
    function maskBefore(arr) {
      return arr.map((v, i) => (i <= asofIdx ? null : v));
    }

    const fMean = maskBefore(mean);
    const fLo = maskBefore(lo);
    const fHi = maskBefore(hi);

    return { fMean, fLo, fHi };
  }

  // =========================================================
  // Render chart (datasets: 당월 + 전월 + 전년도 + 예측(선/밴드))
  // =========================================================
  function renderCompareLineChart(opts) {
    const {
      canvasId,
      warnId,
      chartKey,

      thisMonthScriptId,
      prevMonthScriptId,
      yearAgoScriptId,

      forecastSeriesKey,          // "long" | "car" | "nonlife" | "life"
      forecastPayload,            // fetchForecastOnce 결과
      asofDay,                    // 1~말일
      thisLabel,
      prevLabel,
      yearAgoLabel,
      forecastLabel,              // 예측 라인 label
      forecastBandLabel,          // 예측 밴드 label(표시 안함)
      useNlLifeUnifiedYAxis,
      trimAfterLast,
    } = opts;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const rawLabels = safeJsonFromScriptTag("chart-day-labels", []);
    const labels = toDayOfMonthLabels(rawLabels);
    const len = labels.length;

    const rawThis = safeJsonFromScriptTag(thisMonthScriptId, []);
    const rawPrev = safeJsonFromScriptTag(prevMonthScriptId, []);
    const rawYA = yearAgoScriptId ? safeJsonFromScriptTag(yearAgoScriptId, []) : [];

    if (!Array.isArray(labels) || len === 0) {
      showWarnById(warnId, "차트 라벨(월 1~말일)이 없습니다.");
      return;
    }

    // ✅ 당월은 반드시 len과 일치해야 함(당월이 깨지면 렌더 불가)
    if (!Array.isArray(rawThis) || rawThis.length !== len) {
      showWarnById(
        warnId,
        "당월 차트 데이터 길이가 라벨과 일치하지 않습니다. (labels=" +
          len +
          ", data=" +
          (Array.isArray(rawThis) ? rawThis.length : "N/A") +
          ")"
      );
      return;
    }

    // ✅ 전월/전년도는 길이 보정(없어도 렌더)
    const fixedPrev = normalizeSeriesToLen(rawPrev, len);
    const fixedYA = normalizeSeriesToLen(rawYA, len);

    if (typeof window.Chart === "undefined") {
      showWarnById(warnId, "Chart.js 로드에 실패했습니다. (정적 파일 경로/collectstatic 여부 확인)");
      return;
    }

    const dataThisRaw = trimAfterLast ? trimAfterLastIncreaseToNull(rawThis) : rawThis;
    const dataPrevRaw = trimAfterLast ? trimAfterLastIncreaseToNull(fixedPrev) : fixedPrev;
    const dataYARaw = trimAfterLast ? trimAfterLastIncreaseToNull(fixedYA) : fixedYA;

    // ✅ 표시 전용: 실제 렌더 데이터 자체를 천원 단위로 절사
    const dataThis = mapSeriesToThousandWon(dataThisRaw);
    const dataPrev = mapSeriesToThousandWon(dataPrevRaw);
    const dataYA = mapSeriesToThousandWon(dataYARaw);

    const anyThis = hasAnyIncrease(rawThis);
    const anyPrev = hasAnyIncrease(fixedPrev);

    if (!anyThis && !anyPrev) showWarnById(warnId, "당월/전월 모두 매출이 0입니다.");
    else if (!anyThis && anyPrev) showWarnById(warnId, "당월 매출이 0입니다. (전월은 데이터 있음)");
    else if (anyThis && !anyPrev) showWarnById(warnId, "전월 데이터가 없습니다. (당월은 정상 표시)");
    else hideWarnById(warnId);

    destroyChart(chartKey);

    // y축 통일(손보/생보만)
    const nlStep = safeJsonFromScriptTag("nl-l-y-step", null);
    const nlMax = safeJsonFromScriptTag("nl-l-y-max", null);

    const yScale = {
      ticks: {
        callback: (v) => Number(v ?? 0).toLocaleString()
      }
    };
    if (useNlLifeUnifiedYAxis && typeof nlStep === "number" && typeof nlMax === "number") {
      yScale.beginAtZero = true;
      yScale.suggestedMax = Math.trunc(nlMax / 1000);
      yScale.ticks = {
        stepSize: Math.max(1, Math.trunc(nlStep / 1000)),
        callback: (v) => Number(v ?? 0).toLocaleString()
      };
    }

    // =========================================================
    // Forecast overlay
    //   - asofDay: 1~말일  -> asofIdx: 0-based
    //   - “예측은 미래(>asofIdx)만 표시”
    // =========================================================
    const asofIdx = Math.max(0, Math.min(len - 1, Number(asofDay || 1) - 1));
    let forecastSets = null;

    // forecastPayload: 이제 payload.data가 넘어오므로 forecastPayload.series 존재
    if (forecastPayload?.series && forecastSeriesKey) {
      const KEYMAP = {
        long: "long",
        car: "car",
        nonlife: "long_nonlife",
        life: "long_life",
      };
      const serverKey = KEYMAP[forecastSeriesKey] || forecastSeriesKey;
      const catPayload = forecastPayload.series[serverKey];
      const pred = catPayload?.pred;
      if (pred) {
        // 서버는 p10/p50/p90 (누적) 형태
        const seriesObj = { mean: pred.p50, lo: pred.p10, hi: pred.p90 };
        forecastSets = buildForecastDatasets(seriesObj, len, asofIdx);
      } else if (catPayload && catPayload.pred === null) {
        // ✅ 예측 데이터가 없을 때 사용자에게 이유를 알려줌
        showWarnById(
          warnId,
          "AI 예측 데이터가 없습니다. (업로드 직후 예측 생성 작업이 아직 완료되지 않았거나, 해당 스코프의 예측이 생성되지 않았습니다.)"
        );
      } 
    }

    // 밴드(fill) 구현:
    // - (1) hi 라인을 투명으로 그리고
    // - (2) lo 라인도 투명으로 그린 다음
    // - (3) lo dataset에서 hi로 fill 하도록 (fill: {target: idx})
    // Chart.js fill target은 "dataset index" 기반이므로 순서가 중요.
    const datasets = [];

    // (A) 당월
    datasets.push({
      label: thisLabel || "당월",
      data: dataThis,
      tension: 0.25,
      pointRadius: 2,
      borderWidth: 2,
      borderColor: "rgb(54, 162, 235)",
      backgroundColor: "rgba(54, 162, 235, 0.15)",
      spanGaps: false,
    });

    // (B) 전월
    datasets.push({
      label: prevLabel || "전월",
      data: dataPrev,
      tension: 0.25,
      pointRadius: 2,
      borderWidth: 2,
      borderDash: [6, 4],
      borderColor: "rgb(75, 192, 192)",
      backgroundColor: "rgba(75, 192, 192, 0.15)",
      spanGaps: false,
    });

    // (C) 전년도
    datasets.push({
      label: yearAgoLabel || "전년도",
      data: dataYA,
      tension: 0.25,
      pointRadius: 2,
      borderWidth: 2,
      borderDash: [2, 4],
      borderColor: "rgb(153, 102, 255)",
      backgroundColor: "rgba(153, 102, 255, 0.12)",
      spanGaps: false,
    });

    // (D) 예측 밴드 + 예측선
    if (forecastSets) {
      const { fMean, fLo, fHi } = forecastSets;
      const fMeanK = mapSeriesToThousandWon(fMean);
      const fLoK = mapSeriesToThousandWon(fLo);
      const fHiK = mapSeriesToThousandWon(fHi);

      const hiIndex = datasets.length;
      datasets.push({
        label: (forecastBandLabel || "예측 상한"),
        data: fHiK,
        tension: 0.25,
        pointRadius: 0,
        borderWidth: 0,
        borderColor: "rgba(0,0,0,0)",     // 라인 숨김
        backgroundColor: "rgba(0,0,0,0)",
        spanGaps: false,
      });

      const loIndex = datasets.length;
      datasets.push({
        label: (forecastBandLabel || "예측 하한"),
        data: fLoK,
        tension: 0.25,
        pointRadius: 0,
        borderWidth: 0,
        borderColor: "rgba(0,0,0,0)",     // 라인 숨김
        backgroundColor: "rgba(255, 159, 64, 0.18)", // 밴드 색(주황 계열)
        fill: { target: hiIndex },        // lo -> hi 사이를 채움
        spanGaps: false,
      });

      datasets.push({
        label: forecastLabel || "예측",
        data: fMeanK,
        tension: 0.25,
        pointRadius: 1,
        borderWidth: 2,
        borderDash: [4, 4],
        borderColor: "rgb(255, 159, 64)", // 예측선(주황)
        backgroundColor: "rgba(0,0,0,0)",
        spanGaps: false,
      });
    }

    const ctx = canvas.getContext("2d");
    window[chartKey] = new window.Chart(ctx, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: true },
          tooltip: {
            callbacks: {
              label: function (c) {
                const v = c?.parsed?.y;
                const label = c?.dataset?.label || "";
                if (v === null || typeof v === "undefined") return label + ": -";
                return label + ": " + Number(v || 0).toLocaleString();
              },
            },
          },
        },
        scales: { y: yScale },
      },
    });
  }

  // =========================================================
  // Charts init
  // =========================================================
  async function initChartsWithForecast() {
    const root = getRoot();

    const rawLabels = safeJsonFromScriptTag("chart-day-labels", []);
    const ym = inferYmFromLabels(rawLabels);

    // 당월 series(4)
    const sLong = safeJsonFromScriptTag("chart-cumsum", []);
    const sCar = safeJsonFromScriptTag("car-chart-cumsum", []);
    const sNl = safeJsonFromScriptTag("nonlife-chart-cumsum", []);
    const sLife = safeJsonFromScriptTag("life-chart-cumsum", []);

    // 전월 series(4)
    const pLong = safeJsonFromScriptTag("prev-chart-cumsum", []);
    const pCar = safeJsonFromScriptTag("prev-car-chart-cumsum", []);
    const pNl = safeJsonFromScriptTag("prev-nonlife-chart-cumsum", []);
    const pLife = safeJsonFromScriptTag("prev-life-chart-cumsum", []);

    // 전년도 series(4)
    const pyLong = safeJsonFromScriptTag("py-chart-cumsum", []);
    const pyCar = safeJsonFromScriptTag("py-car-chart-cumsum", []);
    const pyNl = safeJsonFromScriptTag("py-nonlife-chart-cumsum", []);
    const pyLife = safeJsonFromScriptTag("py-life-chart-cumsum", []);

    const prevYm = safeJsonFromScriptTag("prev-ym", null);
    const prevYearYm = safeJsonFromScriptTag("prev-year-ym", null);

    // asof_day 결정:
    // - “실제 데이터가 마지막으로 증가한 일자”를 asof로 쓰는게 가장 자연스러움(= 실제가 있는 구간까지 학습)
    // - long(손생) 기준으로 잡고, 없으면 오늘 날짜로 fallback
    const lastIdx = lastIncreaseIndex(Array.isArray(sLong) ? sLong : []);
    const labelsLen = Array.isArray(rawLabels) ? rawLabels.length : 0;

    let asofDay = 1;
    if (lastIdx >= 0) asofDay = lastIdx + 1;
    else {
      const today = new Date();
      const d = today.getDate();
      asofDay = d > 0 ? d : 1;
    }

    // 범위 보정(1~말일)
    if (labelsLen > 0) asofDay = Math.max(1, Math.min(labelsLen, asofDay));

    // 예측 scope 결정(권장):
    // - head 권한이면 branch가 사실상 고정일 수 있음
    // - UI의 선택값을 기준으로 branch/part를 보내고
    // - 서버에서 권한 스코프를 재검증
    const { part, branch } = getFiltersFromDom(root);

    // scope 파라미터 정책(너가 서버에서 맞춰주면 됨)
    // - branch 선택되어 있으면 branch
    // - part만 있으면 part
    // - 둘 다 없으면 all
    let scope = "all";
    if (branch) scope = "branch";
    else if (part) scope = "part";

    // forecast fetch(ym이 없으면 skip)
    let forecastPayload = null;
    if (ym) {
      forecastPayload = await fetchForecastOnce({
        ym,
        asofDay,
        scope,
        part,
        branch,
      });
    }

    debugOnce({
      staticVer: getStaticVer(),
      chartJsLoaded: typeof window.Chart !== "undefined",
      ym,
      asofDay,
      scope,
      part,
      branch,
      prevYm: prevYm || null,
      prevYearYm: prevYearYm || null,
      labelsLen: labelsLen || "N/A",
      seriesLens: {
        long: Array.isArray(sLong) ? sLong.length : "N/A",
        car: Array.isArray(sCar) ? sCar.length : "N/A",
        nonlife: Array.isArray(sNl) ? sNl.length : "N/A",
        life: Array.isArray(sLife) ? sLife.length : "N/A",
      },
      forecastHasSeries: !!forecastPayload?.series
    });

    // ✅ 4개 차트 렌더
    renderCompareLineChart({
      canvasId: "dailyCumsumChart",
      warnId: "chartWarn",
      chartKey: CHART_KEYS.long,
      thisMonthScriptId: "chart-cumsum",
      prevMonthScriptId: "prev-chart-cumsum",
      yearAgoScriptId: "py-chart-cumsum",
      forecastSeriesKey: "long",
      forecastPayload,
      asofDay,
      thisLabel: "당월매출(손생)",
      prevLabel: "전월매출(손생)",
      yearAgoLabel: "전년도매출(손생)",
      forecastLabel: "예상매출(손생)",
      forecastBandLabel: "예측구간(손생)",
      useNlLifeUnifiedYAxis: false,
      trimAfterLast: true,
    });

    renderCompareLineChart({
      canvasId: "carDailyCumsumChart",
      warnId: "carChartWarn",
      chartKey: CHART_KEYS.car,
      thisMonthScriptId: "car-chart-cumsum",
      prevMonthScriptId: "prev-car-chart-cumsum",
      yearAgoScriptId: "py-car-chart-cumsum",
      forecastSeriesKey: "car",
      forecastPayload,
      asofDay,
      thisLabel: "당월매출(자동차)",
      prevLabel: "전월매출(자동차)",
      yearAgoLabel: "전년도매출(자동차)",
      forecastLabel: "예상매출(자동차)",
      forecastBandLabel: "예측구간(자동차)",
      useNlLifeUnifiedYAxis: false,
      trimAfterLast: true,
    });

    renderCompareLineChart({
      canvasId: "nonlifeDailyCumsumChart",
      warnId: "nonlifeChartWarn",
      chartKey: CHART_KEYS.nonlife,
      thisMonthScriptId: "nonlife-chart-cumsum",
      prevMonthScriptId: "prev-nonlife-chart-cumsum",
      yearAgoScriptId: "py-nonlife-chart-cumsum",
      forecastSeriesKey: "nonlife",
      forecastPayload,
      asofDay,
      thisLabel: "당월매출(손보)",
      prevLabel: "전월매출(손보)",
      yearAgoLabel: "전년도매출(손보)",
      forecastLabel: "예상매출(손보)",
      forecastBandLabel: "예측구간(손보)",
      useNlLifeUnifiedYAxis: true, // ✅ 손보/생보만 y축 통일
      trimAfterLast: true,
    });

    renderCompareLineChart({
      canvasId: "lifeDailyCumsumChart",
      warnId: "lifeChartWarn",
      chartKey: CHART_KEYS.life,
      thisMonthScriptId: "life-chart-cumsum",
      prevMonthScriptId: "prev-life-chart-cumsum",
      yearAgoScriptId: "py-life-chart-cumsum",
      forecastSeriesKey: "life",
      forecastPayload,
      asofDay,
      thisLabel: "당월매출(생보)",
      prevLabel: "전월매출(생보)",
      yearAgoLabel: "전년도매출(생보)",
      forecastLabel: "예상매출(생보)",
      forecastBandLabel: "예측구간(생보)",
      useNlLifeUnifiedYAxis: true,
      trimAfterLast: true,
    });
  }

  // =========================================================
  // Page size selector
  // =========================================================
  function initPageSize() {
    const sel = document.getElementById("pageSizeSelect");
    if (!sel) return;

    sel.addEventListener("change", function () {
      const v = (sel.value || "50").trim();
      const url = new URL(window.location.href);
      url.searchParams.set("page_size", v);
      url.searchParams.set("page", "1");
      window.location.href = url.toString();
    });
  }

  // =========================================================
  // Boot
  // =========================================================
  document.addEventListener("DOMContentLoaded", function () {
    const root = getRoot();
    const ver = getStaticVer();

    try {
      console.log("[dash_sales_page] loaded v=" + ver);
    } catch (e) {}

    initPartBranchSync(root);
    initLifeNlInsurerSync(root);

    // ✅ 예측 포함 차트 init(비동기)
    initChartsWithForecast();

    initPageSize();
  });
})();
