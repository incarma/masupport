(function () {
  "use strict";

  const root = document.getElementById("rate-example-root");
  if (!root) return;
  if (root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  // ── URL / CSRF ─────────────────────────────────────────────────────────────
  const UPLOAD_URL = root.dataset.uploadUrl;
  const OPTIONS_URL = root.dataset.optionsUrl;
  const CALCULATE_URL = root.dataset.calculateUrl;
  const CONVERSION_LIST_URL = root.dataset.conversionListUrl;
  const CONVERSION_STRATEGY_UPDATE_URL = root.dataset.conversionStrategyUpdateUrl;
  const CONVERSION_BULK_EDIT_URL = root.dataset.conversionBulkEditUrl;
  // 환산율 정규화 초기화 URL (보험사 단위)
  const CONVERSION_RESET_URL         = root.dataset.conversionResetUrl;
  // 지급률 확인 모달 조회 URL — data-pay-list-url dataset에서 주입
  const PAY_LIST_URL = root.dataset.payListUrl;
  // 지급률 정규화 전체 초기화 URL
  const PAY_RESET_URL                = root.dataset.payResetUrl;

  // ── 보험사 목록 (json_script 태그에서 읽기) ───────────────────────────────
  const LIFE_INSURERS = JSON.parse(
    document.getElementById("life-insurers-data").textContent
  );

  const NONLIFE_INSURERS = JSON.parse(
    document.getElementById("nonlife-insurers-data").textContent
  );

  // ── 현재 보험 구분 페이지 상태 ────────────────────────────────────────
  // 기본값은 기존 화면과 동일한 생명보험(life)이다.
  const ACTIVE_INSURER_TYPE = ["life", "nonlife"].includes(root.dataset.activeInsurerType)
    ? root.dataset.activeInsurerType
    : "life";

  // ─────────────────────────────────────────────────────────
  // 손해보험 전용 보험사 목록
  // 요구사항:
  // AIG, DB, KB, 농협, 롯데, 메리츠, 삼성, 하나, 한화, 현대, 흥국
  // ─────────────────────────────────────────────────────────
  const NONLIFE_MODAL_INSURERS = [
    "AIG",
    "DB",
    "KB",
    "농협",
    "롯데",
    "메리츠",
    "삼성",
    "하나",
    "한화",
    "현대",
    "흥국",
  ];

  function getModalInsurers() {
    if (ACTIVE_INSURER_TYPE === "nonlife") {
      return NONLIFE_MODAL_INSURERS;
    }
    return LIFE_INSURERS;
  }

  // ─────────────────────────────────────────────────────────
  // 손해보험 페이지 진입 시 모달 제목 변경
  // ─────────────────────────────────────────────────────────
  const uploadModalTitle = document.getElementById("rateExampleUploadModalTitle");
  const convModalTitle = document.getElementById("rateExampleConvModalTitle");

  if (ACTIVE_INSURER_TYPE === "nonlife") {
    if (uploadModalTitle) {
      uploadModalTitle.textContent = "수정률 업데이트";
    }

    if (convModalTitle) {
      convModalTitle.textContent = "수정률 확인";
    }
  }

  function isNonlifePage() {
    return ACTIVE_INSURER_TYPE === "nonlife";
  }

  function getRateLabel() {
    return isNonlifePage() ? "수정률" : "환산율";
  }

  function getActiveInsurers() {
    return ACTIVE_INSURER_TYPE === "nonlife" ? NONLIFE_INSURERS : LIFE_INSURERS;
  }

  // =========================================================================
  // 메인 계산 입력 UI
  // =========================================================================
  // - 기존 파일 목록 DataTables/필터 기능 제거
  // - 보험사/상품명/구분/납기 연동만 담당
  // - 실제 계산은 추후 calculator API에서 개발

  const commissionRateInput = document.getElementById("re-commission-rate");
  const premiumInput = document.getElementById("re-premium");
  const calcSearchBtn = document.getElementById("re-btn-calc-search");
  const calcTbody = document.getElementById("re-calc-tbody");
  const btnAddRow = document.getElementById("re-btn-add-row");
  const btnDeleteRow = document.getElementById("re-btn-delete-row");
  const btnResetRows = document.getElementById("re-btn-reset-rows");
  const MAX_CALC_ROWS = 10;
  const IBK_INSURER = "IBK";
  const CONV_COVERAGE_CHOICES = [
    "종신,CI",
    "연금",
    "변액연금",
    "저축",
    "VUL",
    "연금저축",
    "기타(보장성)",
    "CEO정기",
  ];

  let activeComboInput = null;
  let activeComboMenu = null;

  function onlyDigits(value) {
    return String(value || "").replace(/[^\d]/g, "");
  }

  function formatComma(value) {
    const digits = onlyDigits(value);
    return digits ? Number(digits).toLocaleString("ko-KR") : "";
  }

  function normalizePremiumValue() {
    if (!premiumInput) return;
    premiumInput.value = formatComma(premiumInput.value);
  }

  function clampCommissionRate() {
    if (!commissionRateInput) return;
    const raw = onlyDigits(commissionRateInput.value);
    if (!raw) {
      commissionRateInput.value = "";
      return;
    }
    const n = Math.max(1, Math.min(100, Number(raw)));
    commissionRateInput.value = String(n);
  }

  function positionComboMenu(input, menu) {
    if (!input || !menu) return;
    /*
     * CSP strict(style-src 'self') 환경에서는 JS의 element.style.* 적용이
     * inline style로 차단될 수 있다.
     * 위치는 CSS 고정 규칙으로 처리하고, JS는 메뉴 렌더/표시만 담당한다.
     */
  }

  function renderComboMenu(input, menu, values, keyword) {
    if (!input || !menu) return;
    const kw = String(keyword || "").trim().toLowerCase();
    const items = (values || []).filter(function (name) {
      return !kw || String(name).toLowerCase().includes(kw);
    });

    menu.innerHTML = items.map(function (name) {
      return (
        '<button type="button" class="re-combo-item" data-value="' +
        escapeHtml(name) +
        '">' +
        escapeHtml(name) +
        "</button>"
      );
    }).join("");

    positionComboMenu(input, menu);
    menu.hidden = items.length === 0;
  }

  function hideActiveComboMenu() {
    if (activeComboMenu) activeComboMenu.hidden = true;
    activeComboInput = null;
    activeComboMenu = null;
  }

  function selectComboItem(btn) {
    if (!btn) return;

    const combo = btn.closest(".re-combo");
    const selectedInput = combo?.querySelector(".re-calc-insurer, .re-calc-product");
    if (!selectedInput) return;

    const row = getRow(selectedInput);
    selectedInput.value = btn.dataset.value || "";

    selectedInput.dispatchEvent(new Event("input", { bubbles: true }));
    selectedInput.dispatchEvent(new Event("change", { bubbles: true }));

    hideActiveComboMenu();

    if (selectedInput.classList.contains("re-calc-insurer")) {
      refreshProductsByInsurer(row);
    } else if (selectedInput.classList.contains("re-calc-product")) {
      refreshPlansByProduct(row);
    }
  }

  function getRow(el) {
    return el ? el.closest(".re-calc-row") : null;
  }

  function rowEls(row) {
    return {
      insurer: row?.querySelector(".re-calc-insurer"),
      product: row?.querySelector(".re-calc-product"),
      plan: row?.querySelector(".re-calc-plan"),
      period: row?.querySelector(".re-calc-period"),
      insurerMenu: row?.querySelector(".re-insurer-menu"),
      productMenu: row?.querySelector(".re-product-menu"),
    };
  }

  function isIbkRow(row) {
    const els = rowEls(row);
    return (els.insurer?.value || "").trim() === IBK_INSURER;
  }

  function setIbkRowMode(row) {
    const els = rowEls(row);
    const enabled = isIbkRow(row);

    if (els.plan) {
      fillSelect(els.plan, [], "사용안함");
      els.plan.disabled = enabled;
      if (enabled) els.plan.value = "";
    }
    if (els.period) {
      fillSelect(els.period, [], "사용안함");
      els.period.disabled = enabled;
      if (enabled) els.period.value = "";
    }
    if (els.product) {
      els.product.placeholder = enabled ? "IBK 상품군" : "상품명";
    }
  }

  function fillSelect(el, values, placeholder) {
    if (!el) return;
    el.innerHTML = `<option value="">${placeholder || "선택"}</option>`;
    (values || []).forEach(function (value) {
      if (!value) return;
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      el.appendChild(opt);
    });
  }

  async function loadOptionList(kind, params) {
    if (!OPTIONS_URL) return [];
    const url = new URL(OPTIONS_URL, window.location.origin);
    url.searchParams.set("kind", kind);
    Object.entries(params || {}).forEach(function ([key, value]) {
      if (value) url.searchParams.set(key, value);
    });
    // 생명보험/손해보험 탭 상태를 옵션 API에 전달한다.
    url.searchParams.set("insurer_type", ACTIVE_INSURER_TYPE);
    const res = await fetch(url.toString(), {
      method: "GET",
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const json = await readJsonOrThrow(res);
    return json.data?.items || json.message?.items || [];
  }

  async function refreshProductsByInsurer(row) {
    const els = rowEls(row);
    const insurer = (els.insurer?.value || "").trim();
    if (els.product) els.product.value = "";
    fillSelect(els.plan, [], "선택");
    fillSelect(els.period, [], "선택");
    setIbkRowMode(row);
    if (els.productMenu) els.productMenu.innerHTML = "";
    row.dataset.products = "[]";

    if (!insurer) return;

    const products = await loadOptionList("products", { insurer });
    row.dataset.products = JSON.stringify(products || []);

    /*
     * 보험사 선택 직후 상품명 입력창에 포커스가 있거나,
     * 사용자가 바로 상품명을 선택하려는 경우를 위해
     * 상품명 메뉴 데이터를 즉시 준비한다.
     */
    if (els.product && document.activeElement === els.product) {
      renderComboMenu(els.product, els.productMenu, products, els.product.value);
    }
  }

  async function refreshPlansByProduct(row) {
    const els = rowEls(row);
    const insurer = (els.insurer?.value || "").trim();
    const productName = (els.product?.value || "").trim();
    row.dataset.selectedPlanType = "";
    fillSelect(els.plan, [], "선택");
    fillSelect(els.period, [], "선택");
    setIbkRowMode(row);
    if (insurer === IBK_INSURER) return;
    if (!insurer || !productName) return;

    const plans = await loadOptionList("plan_types", {
      insurer,
      product_name: productName,
    });

    /*
     * 한화 연금보험처럼 정규화 row의 plan_type이 공란인 상품은
     * 구분 select를 "사용안함"으로 고정하고,
     * plan_type="" 조건으로 납기 목록을 즉시 조회한다.
     *
     * 계산 API는 plan_type 공란을 허용하므로,
     * 사용자는 보험사/상품명/납기만 선택하면 된다.
     */
    if (!plans || plans.length === 0) {
      fillSelect(els.plan, [], "사용안함");
      if (els.plan) els.plan.disabled = true;
      row.dataset.selectedPlanType = "";

      const periods = await loadOptionList("pay_periods", {
        insurer,
        product_name: productName,
        plan_type: "",
      });
      fillSelect(els.period, periods, "선택");
      if (els.period) els.period.disabled = false;
      return;
    }

    if (els.plan) els.plan.disabled = false;
    fillSelect(els.plan, plans, "선택");
  }

  async function refreshPeriodsByPlan(row) {
    const els = rowEls(row);
    const insurer = (els.insurer?.value || "").trim();
    const productName = (els.product?.value || "").trim();
    const planType = (els.plan?.value || "").trim();
    row.dataset.selectedPlanType = planType;
    fillSelect(els.period, [], "선택");
    setIbkRowMode(row);
    if (insurer === IBK_INSURER) return;
    if (!insurer || !productName) return;
    const periods = await loadOptionList("pay_periods", {
      insurer,
      product_name: productName,
      plan_type: planType,
    });
    fillSelect(els.period, periods, "선택");
  }

  if (premiumInput) {
    premiumInput.addEventListener("input", normalizePremiumValue);
  }
  if (commissionRateInput) {
    commissionRateInput.addEventListener("input", clampCommissionRate);
  }
  function cloneCalcRow() {
    const first = calcTbody?.querySelector(".re-calc-row");
    if (!first) return null;
    const row = first.cloneNode(true);
    row.dataset.products = "[]";

    row.querySelectorAll("input").forEach(function (input) {
      if (input.type === "checkbox") {
        input.checked = false;
      } else {
        input.value = "";
      }
    });
    row.querySelectorAll("select").forEach(function (sel) {
      fillSelect(sel, [], "선택");
      sel.disabled = false;
    });
    row.querySelectorAll(".re-combo-menu").forEach(function (menu) {
      menu.innerHTML = "";
      menu.hidden = true;
    });
    row.querySelectorAll(
      ".re-calc-placeholder, .re-calc-amount, .re-calc-na, .re-calc-total, .re-calc-subtotal"
    ).forEach(function (td) {
      td.textContent = "-";
      td.classList.remove(
        "re-calc-amount",
        "re-calc-na",
        "re-calc-total",
        "re-calc-subtotal"
      );
      td.classList.add("re-calc-placeholder");
    });
    return row;
  }

  function resetCalcRows() {
    if (!calcTbody) return;
    const first = calcTbody.querySelector(".re-calc-row");
    if (!first) return;
    const clean = cloneCalcRow();
    calcTbody.innerHTML = "";
    calcTbody.appendChild(clean || first);
    hideActiveComboMenu();
  }

  if (btnAddRow) {
    btnAddRow.addEventListener("click", function () {
      const currentRows = calcTbody
        ? calcTbody.querySelectorAll(".re-calc-row").length
        : 0;

      if (currentRows >= MAX_CALC_ROWS) {
        alert("행은 최대 10개까지만 추가할 수 있습니다.");
        return;
      }

      const row = cloneCalcRow();
      if (row && calcTbody) calcTbody.appendChild(row);
    });
  }

  if (btnDeleteRow) {
    btnDeleteRow.addEventListener("click", function () {
      if (!calcTbody) return;
      const rows = Array.from(calcTbody.querySelectorAll(".re-calc-row"));
      const checked = rows.filter(function (row) {
        return row.querySelector(".re-row-check")?.checked;
      });
      if (checked.length === 0) {
        alert("삭제할 행을 선택해 주세요.");
        return;
      }
      checked.forEach(function (row) { row.remove(); });
      if (!calcTbody.querySelector(".re-calc-row")) {
        const row = cloneCalcRow();
        if (row) calcTbody.appendChild(row);
      }
      hideActiveComboMenu();
    });
  }

  if (btnResetRows) {
    btnResetRows.addEventListener("click", function () {
      if (!confirm("입력 행을 모두 초기화하시겠습니까?")) return;
      resetCalcRows();
    });
  }

  if (calcTbody) {
    calcTbody.addEventListener("focusin", function (e) {
      const insurerInput = e.target.closest(".re-calc-insurer");
      const productInput = e.target.closest(".re-calc-product");

      if (insurerInput) {
        const row = getRow(insurerInput);
        const menu = row?.querySelector(".re-insurer-menu");
        activeComboInput = insurerInput;
        activeComboMenu = menu;
        renderComboMenu(insurerInput, menu, getActiveInsurers(), insurerInput.value);
        return;
      }

      if (productInput) {
        const row = getRow(productInput);
        let products = JSON.parse(row?.dataset.products || "[]");
        const menu = rowEls(row).productMenu;
        activeComboInput = productInput;
        activeComboMenu = menu;

        if (products.length === 0) {
          refreshProductsByInsurer(row).then(function () {
            products = JSON.parse(row?.dataset.products || "[]");
            renderComboMenu(productInput, menu, products, productInput.value);
          });
          return;
        }

        renderComboMenu(productInput, menu, products, productInput.value);
      }
    });

    calcTbody.addEventListener("input", function (e) {
      const insurerInput = e.target.closest(".re-calc-insurer");
      const productInput = e.target.closest(".re-calc-product");

      if (insurerInput) {
        const row = getRow(insurerInput);
        const menu = rowEls(row).insurerMenu;
        activeComboInput = insurerInput;
        activeComboMenu = menu;
        renderComboMenu(insurerInput, menu, getActiveInsurers(), insurerInput.value);
        return;
      }

      if (productInput) {
        const row = getRow(productInput);
        let products = JSON.parse(row?.dataset.products || "[]");
        const menu = rowEls(row).productMenu;
        activeComboInput = productInput;
        activeComboMenu = menu;

        if (products.length === 0) {
          refreshProductsByInsurer(row).then(function () {
            products = JSON.parse(row?.dataset.products || "[]");
            renderComboMenu(productInput, menu, products, productInput.value);
          });
          return;
        }

        renderComboMenu(productInput, menu, products, productInput.value);
      }
    });

    calcTbody.addEventListener("change", function (e) {
      const row = getRow(e.target);
      if (!row) return;
      if (e.target.closest(".re-calc-insurer")) refreshProductsByInsurer(row);
      if (e.target.closest(".re-calc-product")) refreshPlansByProduct(row);
      if (e.target.closest(".re-calc-plan")) refreshPeriodsByPlan(row);
    });

    /*
     * focusout에서 무조건 메뉴를 닫으면
     * 보험사 input → 상품명 input 이동 시 이전 타이머가 상품명 메뉴까지 닫아버린다.
     * 메뉴 닫기는 document mousedown에서 combo 외부 클릭일 때만 처리한다.
     */

    calcTbody.addEventListener("focusout", function (e) {
      const fromCombo = e.target.closest(".re-combo");
      if (!fromCombo) return;

      window.setTimeout(function () {
        const activeEl = document.activeElement;

        /*
         * Tab 이동 후 포커스가 같은 combo 내부에 남아 있으면 유지하고,
         * 다른 input/select/페이지 영역으로 이동했으면 열린 메뉴를 닫는다.
         */
        if (!fromCombo.contains(activeEl)) {
          hideActiveComboMenu();
        }
      }, 0);
    });

    calcTbody.addEventListener("pointerdown", function (e) {
      const btn = e.target.closest(".re-combo-item");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      selectComboItem(btn);
    });
  }

  document.addEventListener("mousedown", function (e) {
    if (!activeComboMenu) return;
    if (e.target.closest(".re-combo")) return;
    if (e.target.closest(".re-combo-menu")) return;
    hideActiveComboMenu();
  });

  // ── 수수료 예시표 계산 API 연동 ─────────────────────────────────────
  function parseMoneyInput(value) {
    return String(value || "").replace(/[^\d]/g, "");
  }

  function formatMoneyValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    return Number(value).toLocaleString("ko-KR");
  }

  function formatRatioValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    return String(value) + "%";
  }

  function getResultCells(row) {
    /*
     * 계산 결과 셀은 조회 후 class가 아래 상태값 중 하나로 바뀐다.
     * re-calc-subtotal을 누락하면 재조회 시 익월 소계/계속 소계 셀이
     * 수집 대상에서 빠져 결과값이 한 칸씩 밀리는 문제가 발생한다.
     */
    return Array.from(row.querySelectorAll(
      ".re-calc-placeholder, .re-calc-amount, .re-calc-na, .re-calc-total, .re-calc-subtotal"
    ));
  }

  function resetResultCells(row) {
    getResultCells(row).forEach(function (td) {
      td.textContent = "-";
      td.classList.remove("re-calc-amount", "re-calc-na", "re-calc-total", "re-calc-subtotal");
      td.classList.add("re-calc-placeholder");
    });
  }

  function renderCalcResult(row, data) {
    const cells = getResultCells(row);
    const values = [
      formatMoneyValue(data.next_month_first),
      formatMoneyValue(data.next_month_subtotal),
      formatMoneyValue(data.month_13),
      formatMoneyValue(data.year2),
      formatMoneyValue(data.year3),
      formatMoneyValue(data.month_36),
      formatMoneyValue(data.month_37),
      formatMoneyValue(data.year4),
      formatMoneyValue(data.renewal_subtotal),
      formatMoneyValue(data.total_amount),
      formatRatioValue(data.total_ratio),
    ];

    cells.forEach(function (td, idx) {
      td.textContent = values[idx] || "-";
      td.classList.remove("re-calc-placeholder", "re-calc-amount", "re-calc-na", "re-calc-total", "re-calc-subtotal");

      if (idx === 1 || idx === 8) {
        td.classList.add("re-calc-subtotal");
      } else if (idx >= 9) {
        // 총합 금액 / 비율: 하늘색 바탕 + 남색 굵은 폰트 유지
        td.classList.add("re-calc-total");
      } else if ([2, 3, 4, 5, 6, 7].includes(idx)) {
        // 13회 / 2차년 / 3차년 / 36회 / 37회	/ 4차년
        // 익월과 동일하게 흰색 바탕 + 굵은 글씨
        td.classList.add("re-calc-amount");
      } else if (values[idx] === "-") {
        td.classList.add("re-calc-na");
      } else {
        td.classList.add("re-calc-amount");
      }
    });
  }

  function collectCalcPayload(row) {
    const els = rowEls(row);
    const insurer = (els.insurer?.value || "").trim();
    const isIbk = insurer === IBK_INSURER;
    const selectedPlanType = (els.plan?.value || row.dataset.selectedPlanType || "").trim();
    return {
      insurer: insurer,
      product_name: (els.product?.value || "").trim(),
      plan_type: isIbk ? "" : selectedPlanType,
      pay_period: isIbk ? "" : (els.period?.value || "").trim(),
      premium: parseMoneyInput(premiumInput?.value || ""),
      commission_rate: String(commissionRateInput?.value || "").trim(),
      insurer_type: ACTIVE_INSURER_TYPE,
    };
  }

  async function calculateOneRow(row) {
    resetResultCells(row);
    const payload = collectCalcPayload(row);

    if (!payload.insurer && !payload.product_name && !payload.plan_type && !payload.pay_period) {
      return;
    }
    if (payload.insurer === IBK_INSURER) {
      if (!payload.product_name) {
        throw new Error("IBK 상품군을 선택해 주세요.");
      }
    } else if (!payload.insurer || !payload.product_name || !payload.pay_period) {
      throw new Error("보험사, 상품명, 납기를 모두 선택해 주세요.");
    }
    if (!payload.premium || Number(payload.premium) <= 0) {
      throw new Error("보험료를 입력해 주세요.");
    }
    if (!payload.commission_rate || Number(payload.commission_rate) <= 0) {
      throw new Error("수수료율을 입력해 주세요.");
    }

    const res = await fetch(CALCULATE_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.csrfToken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });
    const json = await readJsonOrThrow(res);
    renderCalcResult(row, json.data || {});
  }

  if (calcSearchBtn) {
    calcSearchBtn.addEventListener("click", async function () {
      if (!CALCULATE_URL) {
        alert("계산 URL이 설정되지 않았습니다.");
        return;
      }
      const rows = Array.from(calcTbody?.querySelectorAll(".re-calc-row") || []);
      calcSearchBtn.disabled = true;
      try {
        for (const row of rows) {
          await calculateOneRow(row);
        }
      } catch (err) {
        alert(err.message || "계산 중 오류가 발생했습니다.");
      } finally {
        calcSearchBtn.disabled = false;
      }
    });
  }

  // ── 환산율/수정률 정규화 테이블 렌더링 ───────────────────────────────
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function showConvError(msg) {
    if (!convErrBox) return;
    convErrBox.textContent = msg;
    convErrBox.classList.remove("d-none");
  }

  function clearConvError() {
    if (!convErrBox) return;
    convErrBox.textContent = "";
    convErrBox.classList.add("d-none");
  }

  function renderConvRows(rows) {
    if (!convTbody) return;

    if (!rows || rows.length === 0) {
      convTbody.innerHTML = `
        <tr>
          <td colspan="10" class="text-center text-muted py-3">
            조회된 정규화 데이터가 없습니다.
          </td>
        </tr>`;
      return;
    }

    convTbody.innerHTML = rows.map(function (row) {
      if (convEditMode) {
        return `
          <tr class="re-conv-edit-row" data-row-id="${escapeHtml(row.id || "")}">
            <td class="text-center">
              <input type="checkbox" class="form-check-input re-conv-row-check" aria-label="행 선택">
            </td>
            <td>${convCoverageInput(row)}</td>
            <td>${convStrategyInput(row)}</td>
            <td>${convInputCell(row, "product_name")}</td>
            <td>${convInputCell(row, "plan_type")}</td>
            <td>${convInputCell(row, "pay_period")}</td>
            <td>${convInputCell(row, "year1", "text-end")}</td>
            <td>${convInputCell(row, "year2", "text-end")}</td>
            <td>${convInputCell(row, "year3", "text-end")}</td>
            <td>${convInputCell(row, "year4", "text-end")}</td>
          </tr>`;
      }

      return `
        <tr>
          <td class="text-center re-conv-edit-only d-none"></td>
          <td class="text-center">${ellipsisCell(row.coverage_type, "보종")}</td>
          <td class="text-center">${strategySelect(row.id, row.strategy_flag)}</td>
          <td>${ellipsisCell(row.product_name, "상품명", "re-product-name")}</td>
          <td class="text-center">${ellipsisCell(row.plan_type, "구분")}</td>
          <td class="text-center">${ellipsisCell(row.pay_period, "납기")}</td>
          <td class="text-end re-rate-num">${escapeHtml(row.year1)}</td>
          <td class="text-end re-rate-num">${escapeHtml(row.year2)}</td>
          <td class="text-end re-rate-num">${escapeHtml(row.year3)}</td>
          <td class="text-end re-rate-num">${escapeHtml(row.year4)}</td>
        </tr>`;
    }).join("");
  }

  async function readJsonOrThrow(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("JSON 응답이 아닙니다. 로그인 만료 또는 권한 오류를 확인해 주세요.");
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.message || "요청 처리 중 오류가 발생했습니다.");
    }
    return data;
  }

  // 기존 메인 목록 필터는 제거됨.
  // 환산율/지급률 확인 모달 내부 필터는 아래 기존 로직을 그대로 유지한다.

  // ── 업로드 모달: 환산율/수정률 보험사 선택 ─────────────────────────────
  const modalInsurer = document.getElementById("re-modal-insurer");
  const modalProductKindWrap = document.getElementById("re-modal-product-kind-wrap");
  const modalProductKind = document.getElementById("re-modal-product-kind");
  const modalProductKindHelp = document.getElementById("re-modal-product-kind-help");

  const PRODUCT_KIND_OPTIONS = {
    KB: [
      ["general", "일반상품"],
      ["health", "건강보험"],
    ],
    "한화": [
      ["hanhwa_whole", "종신보험"],
      ["hanhwa_annuity", "연금보험"],
      ["hanhwa_general", "일반보장"],
    ],
  };

  // ── 보험사별 환산율/수정률 상품 구분 활성화 ─────────────────────
  function updateProductKindVisibility() {
    if (!modalProductKindWrap || !modalProductKind) return;

    if (isNonlifePage()) {
      modalProductKind.innerHTML = '<option value="">선택</option>';
      modalProductKind.value = "";
      modalProductKind.disabled = true;
      modalProductKindWrap.classList.add("d-none");
      return;
    }

    const insurer = modalInsurer?.value || "";
    const options = PRODUCT_KIND_OPTIONS[insurer] || [];
    const shouldShow = options.length > 0;

    modalProductKind.innerHTML = '<option value="">선택</option>';
    options.forEach(function ([value, label]) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      modalProductKind.appendChild(opt);
    });

    modalProductKindWrap.classList.toggle("d-none", !shouldShow);
    modalProductKind.disabled = !shouldShow;

    if (!shouldShow) {
      modalProductKind.value = "";
    }

    if (modalProductKindHelp) {
      modalProductKindHelp.textContent = insurer === "한화"
        ? "한화 환산율 파일 업로드 시 종신보험/연금보험/일반보장 중 하나를 선택합니다."
        : "KB 환산율 파일 업로드 시 일반상품/건강보험 중 하나를 선택합니다.";
    }
  }

  if (modalInsurer) {
    modalInsurer.addEventListener("change", updateProductKindVisibility);
  }

  function populateModalInsurerSelect(sel, placeholder, options) {
    if (!sel) return;
    const opts = options || {};
    sel.disabled = false;
    sel.innerHTML = `<option value="">${placeholder || "선택"}</option>`;
    getModalInsurers().filter(function (name) {
      // 환산율 업데이트/확인 모달에서는 IBK 제외.
      // IBK는 지급률(pay) 기반 계산 특수 보험사이므로 메인 계산 입력에서는 유지한다.
      return !(opts.excludeIbk === true && name === IBK_INSURER);
    }).forEach(function (name) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }

  // ── 환산율 확인 모달: 생보 전용 보험사 선택 ──────────────────
  const convInsurer = document.getElementById("re-conv-insurer");
  const convTbody   = document.getElementById("re-conv-tbody");
  const convErrBox  = document.getElementById("re-conv-error");
  const convUpdatedAt = document.getElementById("re-conv-updated-at");
  const convFilterEls = Array.from(document.querySelectorAll(".re-conv-filter"));
  const convKeyword = document.getElementById("re-conv-keyword");
  const convSortBtns = Array.from(document.querySelectorAll(".re-sort-btn"));
  const convEditOnlyEls = Array.from(document.querySelectorAll(".re-conv-edit-only"));
  const convBtnEdit = document.getElementById("re-conv-btn-edit");
  const convBtnSaveEdit = document.getElementById("re-conv-btn-save-edit");
  const convBtnCancelEdit = document.getElementById("re-conv-btn-cancel-edit");
  const convBtnAddRow = document.getElementById("re-conv-btn-add-row");
  const convBtnDeleteRow = document.getElementById("re-conv-btn-delete-row");
  const convBtnClose = document.getElementById("re-conv-btn-close");
  const fullTextModalEl = document.getElementById("reCellFullTextModal");
  const fullTextTitleEl = document.getElementById("re-cell-fulltext-title");
  const fullTextBodyEl = document.getElementById("re-cell-fulltext-body");

  let convRowsOriginal = [];
  let convEditSnapshot = [];
  let convEditMode = false;
  let convDeletedIds = [];
  let convSortKey = "";
  let convSortDir = "asc";

  function stripPercent(value) {
    return String(value ?? "").replace(/,/g, "").replace(/%/g, "").trim();
  }

  function convInputCell(row, key, alignClass) {
    const value = stripPercent(row[key]);
    return `
      <input type="text"
             class="form-control form-control-sm re-conv-edit-input ${alignClass || ""}"
             data-field="${escapeHtml(key)}"
             value="${escapeHtml(value)}">`;
  }

  function convCoverageInput(row) {
    const selected = String(row.coverage_type || "");
    return `
      <select class="form-select form-select-sm re-conv-edit-input"
              data-field="coverage_type">
        <option value="">선택</option>
        ${CONV_COVERAGE_CHOICES.map(function (choice) {
          const isSelected = choice === selected ? " selected" : "";
          return `<option value="${escapeHtml(choice)}"${isSelected}>${escapeHtml(choice)}</option>`;
        }).join("")}
      </select>`;
  }

  function convStrategyInput(row) {
    const selected = String(row.strategy_flag || "");
    const choices = ["", "전략상품1", "전략상품2", "전략상품3", "전략상품4"];
    return `
      <select class="form-select form-select-sm re-conv-edit-input"
              data-field="strategy_flag">
        ${choices.map(function (choice) {
          const label = choice || "선택";
          const isSelected = choice === selected ? " selected" : "";
          return `<option value="${escapeHtml(choice)}"${isSelected}>${escapeHtml(label)}</option>`;
        }).join("")}
      </select>`;
  }

  function setConvEditMode(enabled) {
    convEditMode = enabled;

    convEditOnlyEls.forEach(function (el) {
      el.classList.toggle("d-none", !enabled);
    });
    [convBtnSaveEdit, convBtnCancelEdit, convBtnAddRow, convBtnDeleteRow].forEach(function (btn) {
      if (btn) btn.classList.toggle("d-none", !enabled);
    });
    if (convBtnEdit) convBtnEdit.classList.toggle("d-none", enabled);
    if (convBtnReset) convBtnReset.disabled = enabled;
    if (convBtnApply) convBtnApply.disabled = enabled;
    if (convInsurer) convInsurer.disabled = enabled;
    if (convBtnClose) convBtnClose.disabled = enabled;

    convFilterEls.forEach(function (sel) { sel.disabled = enabled; });
    if (convKeyword) convKeyword.disabled = enabled;
    convSortBtns.forEach(function (btn) { btn.disabled = enabled; });
  }

  function setConvUpdatedInfo(data) {
    if (!convUpdatedAt) return;
    const updatedAt = data?.last_updated_at || "";
    const updatedBy = data?.last_updated_by || "";
    const sourceName = data?.source_file_name || "";

    if (!updatedAt) {
      convUpdatedAt.textContent = "마지막 업데이트 정보 없음";
      return;
    }

    convUpdatedAt.textContent = [
      `마지막 업데이트: ${updatedAt}`,
      updatedBy ? `업로더: ${updatedBy}` : "",
      sourceName ? `원본: ${sourceName}` : "",
    ].filter(Boolean).join(" / ");
  }

  function uniqueValues(rows, key) {
    return Array.from(new Set(
      rows.map(function (row) { return row[key] || ""; }).filter(Boolean)
    )).sort(function (a, b) {
      return String(a).localeCompare(String(b), "ko");
    });
  }

  function populateConvFilters(rows) {
    convFilterEls.forEach(function (sel) {
      const key = sel.dataset.filterKey;
      const current = sel.value;
      sel.innerHTML = '<option value="">전체</option>';

      uniqueValues(rows, key).forEach(function (value) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = value;
        sel.appendChild(opt);
      });

      if (current && uniqueValues(rows, key).includes(current)) {
        sel.value = current;
      }
    });
  }

  function resetConvFilters() {
    convFilterEls.forEach(function (sel) {
      sel.innerHTML = '<option value="">전체</option>';
      sel.value = "";
    });
  }

  function filteredConvRows() {
    const keyword = String(convKeyword?.value || "").trim().toLowerCase();

    return convRowsOriginal.filter(function (row) {
      const matchedFilters = convFilterEls.every(function (sel) {
        const key = sel.dataset.filterKey;
        const val = sel.value || "";
        return !val || String(row[key] || "") === val;
      });

      if (!matchedFilters) return false;
      if (!keyword) return true;

      return [
        row.coverage_type,
        row.strategy_flag,
        row.product_name,
        row.plan_type,
        row.pay_period,
        row.year1,
        row.year2,
        row.year3,
        row.year4,
      ].some(function (value) {
        return String(value || "").toLowerCase().includes(keyword);
      });
    });
  }

  function sortedConvRows(rows) {
    if (!convSortKey) return rows;
    const dir = convSortDir === "desc" ? -1 : 1;
    return rows.slice().sort(function (a, b) {
      const av = String(a[convSortKey] || "");
      const bv = String(b[convSortKey] || "");
      return av.localeCompare(bv, "ko", { numeric: true }) * dir;
    });
  }

  function updateSortButtons() {
    convSortBtns.forEach(function (btn) {
      btn.classList.remove("is-asc", "is-desc");
      if (btn.dataset.sortKey === convSortKey) {
        btn.classList.add(convSortDir === "desc" ? "is-desc" : "is-asc");
      }
    });
  }

  function applyConvView() {
    if (convEditMode) {
      renderConvRows(convRowsOriginal);
    } else {
      renderConvRows(sortedConvRows(filteredConvRows()));
    }
    updateSortButtons();
  }

  function ellipsisCell(value, title, extraClass) {
    const safeValue = escapeHtml(value || "");
    const safeTitle = escapeHtml(title || "전체 텍스트");
    const cls = extraClass ? ` ${extraClass}` : "";
    return `
      <span class="re-ellipsis-cell${cls}"
            data-title="${safeTitle}"
            data-fulltext="${safeValue}"
            title="${safeValue}">
        ${safeValue}
      </span>`;
  }

  function strategySelect(rowId, value) {
    const selected = String(value || "");
    const choices = ["", "전략상품1", "전략상품2", "전략상품3", "전략상품4"];
    return `
      <select class="form-select form-select-sm re-strategy-select"
              data-row-id="${escapeHtml(rowId)}"
              data-prev-value="${escapeHtml(selected)}"
              aria-label="전략유무 선택">
        ${choices.map(function (choice) {
          const label = choice || "선택";
          const isSelected = choice === selected ? " selected" : "";
          return `<option value="${escapeHtml(choice)}"${isSelected}>${escapeHtml(label)}</option>`;
        }).join("")}
      </select>`;
  }

  // ── 저장 버튼 ──────────────────────────────────────────────────────────────
  const btnSave = document.getElementById("re-btn-save");
  const errBox = document.getElementById("re-upload-error");

  function showError(msg) {
    if (!errBox) return;
    errBox.textContent = msg;
    errBox.classList.remove("d-none");
  }
  function clearError() {
    if (!errBox) return;
    errBox.textContent = "";
    errBox.classList.add("d-none");
  }

  if (btnSave) {
    btnSave.addEventListener("click", async function () {
      clearError();
      const insurerType = ACTIVE_INSURER_TYPE;
      const category = "conv";
      const insurer = modalInsurer?.value || "";
      const productKind = modalProductKind?.value || "";
      const normalizeMode = document.querySelector(
        'input[name="normalize_mode"]:checked'
      )?.value || "replace";
      const fileInput = document.getElementById("re-modal-file");
      const file = fileInput?.files[0];

      if (!insurer) { showError("보험사를 선택해 주세요."); return; }
      if (!isNonlifePage() && ["KB", "한화"].includes(insurer) && !productKind) {
        showError(`${insurer} 상품 구분을 선택해 주세요.`);
        return;
      }
      if (!file) { showError("파일을 선택해 주세요."); return; }

      if (!["replace", "append"].includes(normalizeMode)) {
        showError("기존 데이터 초기화 여부 값이 올바르지 않습니다.");
        return;
      }

      const fd = new FormData();
      fd.append("insurer_type", insurerType);
      fd.append("category", category);
      fd.append("insurer", insurer);
      fd.append("product_kind", productKind);
      fd.append("normalize_mode", normalizeMode);
      fd.append("file", file);

      btnSave.disabled = true;
      try {
        const res = await fetch(UPLOAD_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": window.csrfToken || "" },
          body: fd,
        });
        const json = await res.json();
        if (json.ok) {
          const modal = bootstrap.Modal.getInstance(
            document.getElementById("rateExampleUploadModal")
          );
          if (modal) modal.hide();
          location.reload();
        } else {
          showError(json.message || "업로드에 실패했습니다.");
        }
      } catch (e) {
        showError("네트워크 오류가 발생했습니다.");
      } finally {
        btnSave.disabled = false;
      }
    });
  }

  // ── 환산율/수정률 확인 버튼 → 정규화 데이터 조회 ─────────────────────────
  const convBtnApply = document.getElementById("re-conv-btn-apply");

  if (convBtnApply) {
    convBtnApply.addEventListener("click", async function () {
      const typeVal    = ACTIVE_INSURER_TYPE;
      const insurerVal = convInsurer ? convInsurer.value : "";

      clearConvError();

      if (!CONVERSION_LIST_URL) {
        showConvError("조회 URL이 설정되지 않았습니다.");
        return;
      }
      if (!insurerVal) {
        showConvError("보험사를 선택해 주세요.");
        return;
      }

      const url = new URL(CONVERSION_LIST_URL, window.location.origin);
      url.searchParams.set("insurer_type", typeVal);
      url.searchParams.set("insurer", insurerVal);

      convBtnApply.disabled = true;
      if (convTbody) {
        convTbody.innerHTML = `
          <tr>
            <td colspan="9" class="text-center text-muted py-3">
              조회 중입니다...
            </td>
          </tr>`;
      }

      try {
        const res = await fetch(url.toString(), {
          method: "GET",
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const json = await readJsonOrThrow(res);
        convRowsOriginal = json.data?.rows || [];
        convSortKey = "";
        convSortDir = "asc";
        setConvUpdatedInfo(json.data || {});
        populateConvFilters(convRowsOriginal);
        applyConvView();
      } catch (err) {
        showConvError(err.message || "조회 중 오류가 발생했습니다.");
        convRowsOriginal = [];
        setConvUpdatedInfo(null);
        resetConvFilters();
        renderConvRows([]);
      } finally {
        convBtnApply.disabled = false;
      }
    });
  }

  // ── 환산율/수정률 필터 변경 ─────────────────────────────────────
  convFilterEls.forEach(function (sel) {
    sel.addEventListener("change", applyConvView);
  });

  if (convKeyword) {
    convKeyword.addEventListener("input", applyConvView);
  }

  // ── 전략유무 드랍다운 변경 → DB 즉시 저장 ─────────────────────
  if (convTbody) {
    convTbody.addEventListener("change", async function (e) {
      const sel = e.target.closest(".re-strategy-select");
      if (!sel) return;
      if (convEditMode) return;

      const rowId = sel.dataset.rowId || "";
      const value = sel.value || "";
      const prev = sel.dataset.prevValue || "";

      if (!CONVERSION_STRATEGY_UPDATE_URL) {
        showConvError("전략유무 저장 URL이 설정되지 않았습니다.");
        sel.value = prev;
        return;
      }

      const fd = new FormData();
      fd.append("id", rowId);
      fd.append("strategy_flag", value);

      sel.disabled = true;
      try {
        const res = await fetch(CONVERSION_STRATEGY_UPDATE_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": window.csrfToken || "",
            "X-Requested-With": "XMLHttpRequest",
          },
          body: fd,
        });
        const json = await readJsonOrThrow(res);
        const savedValue = json.data?.strategy_flag || "";

        convRowsOriginal = convRowsOriginal.map(function (row) {
          if (String(row.id) !== String(rowId)) return row;
          return Object.assign({}, row, { strategy_flag: savedValue });
        });

        populateConvFilters(convRowsOriginal);
        applyConvView();
      } catch (err) {
        showConvError(err.message || "전략유무 저장 중 오류가 발생했습니다.");
        sel.value = prev;
      } finally {
        sel.disabled = false;
      }
    });
  }

  function enterConvEditMode() {
    if (!convInsurer?.value) {
      showConvError("보험사를 선택 후 조회해 주세요.");
      return;
    }
    if (!convRowsOriginal.length) {
      showConvError("수정할 환산율 데이터가 없습니다.");
      return;
    }
    clearConvError();
    convEditSnapshot = JSON.parse(JSON.stringify(convRowsOriginal));
    convDeletedIds = [];
    convFilterEls.forEach(function (sel) { sel.value = ""; });
    if (convKeyword) convKeyword.value = "";
    convSortKey = "";
    convSortDir = "asc";
    setConvEditMode(true);
    applyConvView();
  }

  function exitConvEditMode(restore) {
    if (restore) {
      convRowsOriginal = JSON.parse(JSON.stringify(convEditSnapshot));
    }
    convEditSnapshot = [];
    convDeletedIds = [];
    setConvEditMode(false);
    populateConvFilters(convRowsOriginal);
    applyConvView();
  }

  function collectConvEditRows() {
    return Array.from(convTbody?.querySelectorAll(".re-conv-edit-row") || []).map(function (tr) {
      const row = { id: tr.dataset.rowId || "" };
      tr.querySelectorAll(".re-conv-edit-input").forEach(function (input) {
        const field = input.dataset.field || "";
        if (field) row[field] = input.value || "";
      });
      return row;
    });
  }

  async function reloadConvRowsAfterEdit() {
    if (!convBtnApply) return;
    convBtnApply.disabled = false;
    convBtnApply.click();
  }

  if (convBtnEdit) {
    convBtnEdit.addEventListener("click", enterConvEditMode);
  }

  if (convBtnCancelEdit) {
    convBtnCancelEdit.addEventListener("click", function () {
      if (!confirm("수정 중인 내용을 취소하시겠습니까?")) return;
      exitConvEditMode(true);
    });
  }

  if (convBtnAddRow) {
    convBtnAddRow.addEventListener("click", function () {
      if (!convEditMode) return;
      convRowsOriginal.push({
        id: "",
        coverage_type: "",
        strategy_flag: "",
        product_name: "",
        plan_type: "",
        pay_period: "",
        year1: "",
        year2: "",
        year3: "",
        year4: "",
      });
      applyConvView();
    });
  }

  if (convBtnDeleteRow) {
    convBtnDeleteRow.addEventListener("click", function () {
      if (!convEditMode) return;
      const checkedRows = Array.from(convTbody?.querySelectorAll(".re-conv-edit-row") || [])
        .filter(function (tr) {
          return tr.querySelector(".re-conv-row-check")?.checked;
        });
      if (!checkedRows.length) {
        showConvError("삭제할 행을 선택해 주세요.");
        return;
      }
      checkedRows.forEach(function (tr) {
        const rowId = tr.dataset.rowId || "";
        if (rowId) convDeletedIds.push(rowId);
        tr.remove();
      });
      clearConvError();
    });
  }

  if (convBtnSaveEdit) {
    convBtnSaveEdit.addEventListener("click", async function () {
      if (!CONVERSION_BULK_EDIT_URL) {
        showConvError("저장 URL이 설정되지 않았습니다.");
        return;
      }
      const insurerVal = convInsurer?.value || "";
      if (!insurerVal) {
        showConvError("보험사를 선택해 주세요.");
        return;
      }
      const payload = {
        insurer_type: ACTIVE_INSURER_TYPE,
        insurer: insurerVal,
        rows: collectConvEditRows(),
        deleted_ids: convDeletedIds,
      };

      convBtnSaveEdit.disabled = true;
      clearConvError();
      try {
        const res = await fetch(CONVERSION_BULK_EDIT_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": window.csrfToken || "",
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify(payload),
        });
        await readJsonOrThrow(res);
        setConvEditMode(false);
        convEditSnapshot = [];
        convDeletedIds = [];
        await reloadConvRowsAfterEdit();
      } catch (err) {
        showConvError(err.message || "저장 중 오류가 발생했습니다.");
      } finally {
        convBtnSaveEdit.disabled = false;
      }
    });
  }

  // ── 환산율 데이터 초기화 버튼 ────────────────────────────────────────────
  const convBtnReset = document.getElementById("re-conv-btn-reset");
  if (convBtnReset) {
    convBtnReset.addEventListener("click", async function () {
      const insurerVal = convInsurer ? convInsurer.value : "";
      if (!insurerVal) {
        showConvError("초기화할 보험사를 먼저 선택 후 조회해 주세요.");
        return;
      }
      if (!confirm(`[${insurerVal}] ${getRateLabel()} 데이터를 전체 삭제하겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) {
        return;
      }
      if (!CONVERSION_RESET_URL) {
        showConvError("초기화 URL이 설정되지 않았습니다.");
        return;
      }
      convBtnReset.disabled = true;
      clearConvError();
      try {
        const fd = new FormData();
        fd.append("insurer_type", ACTIVE_INSURER_TYPE);
        fd.append("insurer", insurerVal);
        const res = await fetch(CONVERSION_RESET_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": window.csrfToken || "" },
          body: fd,
        });
        const json = await readJsonOrThrow(res);
        // 테이블 초기화 후 안내 메시지
        convRowsOriginal = [];
        convSortKey = "";
        convSortDir = "asc";
        setConvUpdatedInfo(null);
        resetConvFilters();
        if (convKeyword) convKeyword.value = "";
        updateSortButtons();
        if (convTbody) {
          convTbody.innerHTML = `
            <tr>
              <td colspan="9" class="text-center text-muted py-3">
                ${json.message || "데이터가 삭제되었습니다."}
              </td>
            </tr>`;
        }
      } catch (err) {
        showConvError(err.message || "초기화 중 오류가 발생했습니다.");
      } finally {
        convBtnReset.disabled = false;
      }
    });
  }

  // ── 환산율/수정률 컬럼 정렬 ─────────────────────────────────────
  convSortBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const key = btn.dataset.sortKey || "";
      if (!key) return;

      if (convSortKey === key) {
        convSortDir = convSortDir === "asc" ? "desc" : "asc";
      } else {
        convSortKey = key;
        convSortDir = "asc";
      }
      applyConvView();
    });
  });

  // ── 말줄임 셀 클릭 → 전체 텍스트 모달 ───────────────────────────
  if (convTbody) {
    convTbody.addEventListener("click", function (e) {
      const cell = e.target.closest(".re-ellipsis-cell");
      if (!cell) return;

      const fulltext = cell.dataset.fulltext || cell.textContent || "";
      if (!fulltext.trim()) return;

      if (fullTextTitleEl) fullTextTitleEl.textContent = cell.dataset.title || "전체 텍스트";
      if (fullTextBodyEl) fullTextBodyEl.textContent = fulltext;

      if (fullTextModalEl && window.bootstrap?.Modal) {
        bootstrap.Modal.getOrCreateInstance(fullTextModalEl).show();
      } else {
        alert(fulltext);
      }
    });
  }

  // ── 삭제 버튼 (이벤트 위임) ────────────────────────────────────────────────
  // 기존 파일 목록 삭제 버튼은 메인 목록 제거에 따라 비활성화.
  // 파일 삭제/관리 화면이 다시 필요하면 별도 관리 모달로 분리한다.

  // ── 모달 초기화 (열릴 때 입력 리셋) ───────────────────────────────────────
  const uploadModal = document.getElementById("rateExampleUploadModal");
  if (uploadModal) {
    uploadModal.addEventListener("show.bs.modal", function () {
      clearError();
      const form = [
        "re-modal-insurer",
        "re-modal-product-kind",
        "re-modal-file",
      ];
      form.forEach(function (id) {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.tagName === "SELECT") el.selectedIndex = 0;
        if (el.tagName === "INPUT") el.value = "";
      });
      if (modalInsurer) {
        populateModalInsurerSelect(modalInsurer, "선택", { excludeIbk: true });
      }

      const replaceMode = document.getElementById("re-modal-normalize-mode-replace");
      if (replaceMode) {
        replaceMode.checked = true;
      }

      updateProductKindVisibility();
    });
  }
  // ── 환산율/수정률 모달 초기화 (열릴 때 선택값 리셋) ──────────────────────
  const convModal = document.getElementById("rateExampleConvModal");
  if (convModal) {
    convModal.addEventListener("show.bs.modal", function () {
      if (convInsurer) {
        populateModalInsurerSelect(convInsurer, "선택", { excludeIbk: true });
      }
      setConvEditMode(false);
      convEditSnapshot = [];
      convDeletedIds = [];
      convRowsOriginal = [];
      convSortKey = "";
      convSortDir = "asc";
      setConvUpdatedInfo(null);
      resetConvFilters();
      if (convKeyword) convKeyword.value = "";
      updateSortButtons();
      if (convTbody) {
        convTbody.innerHTML = `
          <tr>
            <td colspan="9" class="text-center text-muted py-3">
              보험사를 선택 후 조회해 주세요.
            </td>
          </tr>`;
      }
    });
  }

  // =========================================================================
  // 지급률 기능
  // =========================================================================

  // ── DOM 참조 ────────────────────────────────────────────────────────────────
  const payModalEl       = document.getElementById("rateExamplePayModal");
  const payUploadModalEl = document.getElementById("rateExamplePayUploadModal");
  const payTbody         = document.getElementById("re-pay-tbody");
  const payErrBox        = document.getElementById("re-pay-error");
  const payUpdatedInfo   = document.getElementById("re-pay-updated-at");
  const payCountLabel    = document.getElementById("re-pay-count-label");
  const payFilterInsurer = document.getElementById("re-pay-filter-insurer");
  const payFilterCov     = document.getElementById("re-pay-filter-cov");
  const payKeyword       = document.getElementById("re-pay-keyword");
  const payBtnLoad       = document.getElementById("re-pay-btn-load");
  const btnPaySave       = document.getElementById("re-pay-btn-save");

  let payRowsOriginal = [];

  // ── 에러 헬퍼 ───────────────────────────────────────────────────────────────
  function showPayError(msg) {
    if (!payErrBox) return;
    payErrBox.textContent = msg;
    payErrBox.classList.remove("d-none");
  }
  function clearPayError() {
    if (!payErrBox) return;
    payErrBox.textContent = "";
    payErrBox.classList.add("d-none");
  }

  // ── 마지막 업데이트 정보 표시 ───────────────────────────────────────────────
  function setPayUpdatedInfo(data) {
    if (!payUpdatedInfo) return;
    const updatedAt  = data?.last_updated_at  || "";
    const updatedBy  = data?.last_updated_by  || "";
    const sourceName = data?.source_file_name || "";
    if (!updatedAt) {
      payUpdatedInfo.textContent = "업데이트 정보 없음";
      return;
    }
    payUpdatedInfo.textContent = [
      `마지막 업데이트: ${updatedAt}`,
      updatedBy  ? `업로더: ${updatedBy}`  : "",
      sourceName ? `원본: ${sourceName}` : "",
    ].filter(Boolean).join(" / ");
  }

  // ── 필터 select 채우기 ──────────────────────────────────────────────────────
  function populatePayFilterSelect(sel, rows, key) {
    if (!sel) return;
    const current = sel.value;
    const values  = Array.from(
      new Set(rows.map(function (r) { return r[key] || ""; }).filter(Boolean))
    ).sort(function (a, b) { return String(a).localeCompare(String(b), "ko"); });
    sel.innerHTML = '<option value="">전체</option>';
    values.forEach(function (v) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
    if (current && values.includes(current)) sel.value = current;
  }

  function populatePayFilters(rows) {
    populatePayFilterSelect(payFilterInsurer, rows, "insurer");
    populatePayFilterSelect(payFilterCov,     rows, "coverage_type");
  }

  function resetPayFilters() {
    [payFilterInsurer, payFilterCov].forEach(function (sel) {
      if (sel) sel.innerHTML = '<option value="">전체</option>';
    });
    if (payKeyword) payKeyword.value = "";
  }

  // ── 필터 적용 ────────────────────────────────────────────────────────────────
  function filteredPayRows() {
    const ins = (payFilterInsurer?.value || "").trim();
    const cov = (payFilterCov?.value     || "").trim();
    const kw  = (payKeyword?.value       || "").trim().toLowerCase();
    return payRowsOriginal.filter(function (row) {
      if (ins && row.insurer       !== ins) return false;
      if (cov && row.coverage_type !== cov) return false;
      if (kw) {
        const haystack = [
          row.insurer, row.coverage_type,
          row.col_a, row.col_b, row.col_c,
          row.col_d, row.col_e, row.col_f,
        ].map(function (v) { return String(v ?? ""); }).join(" ").toLowerCase();
        if (!haystack.includes(kw)) return false;
      }
      return true;
    });
  }

  // ── 테이블 렌더링 ────────────────────────────────────────────────────────────
  function renderPayRows(rows) {
    if (!payTbody) return;
    if (!rows || rows.length === 0) {
      payTbody.innerHTML =
        '<tr><td colspan="8" class="text-center text-muted py-3">조회된 데이터가 없습니다.</td></tr>';
      if (payCountLabel) payCountLabel.textContent = "";
      return;
    }
    payTbody.innerHTML = rows.map(function (row) {
      function cell(v) {
        return '<td class="text-end re-pay-num">' + escapeHtml(v || "0") + "</td>";
      }
      // col_m36 / col_m37 / col_yr4: 해당 보험사에 없으면 "" → "-" 표시
      function optCell(v) {
        return '<td class="text-end re-pay-num re-pay-opt">'
          + (v !== "" ? escapeHtml(v) : "-")
          + "</td>";
      }
      return (
        "<tr>" +
        "<td>" + escapeHtml(row.insurer || "") + "</td>" +
        "<td>" + escapeHtml(row.coverage_type || "") + "</td>" +
        cell(row.col_first) +
        cell(row.col_yr1) +
        cell(row.col_m13) +
        cell(row.col_yr2) +
        cell(row.col_yr3) +
        optCell(row.col_m36) +
        optCell(row.col_m37) +
        optCell(row.col_yr4) +
        "</tr>"
      );
    }).join("");
    if (payCountLabel) payCountLabel.textContent = "총 " + rows.length + "건";
  }

  function applyPayView() {
    renderPayRows(filteredPayRows());
  }

  // ── 조회 버튼 ────────────────────────────────────────────────────────────────
  if (payBtnLoad) {
    payBtnLoad.addEventListener("click", async function () {
      clearPayError();
      if (!PAY_LIST_URL) {
        showPayError("조회 URL이 설정되지 않았습니다.");
        return;
      }
      payBtnLoad.disabled = true;
      if (payTbody) {
        payTbody.innerHTML =
          '<tr><td colspan="8" class="text-center text-muted py-3">조회 중입니다...</td></tr>';
      }
      try {
        const res = await fetch(PAY_LIST_URL, {
          method: "GET",
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const json = await readJsonOrThrow(res);
        payRowsOriginal = json.data?.rows || [];
        setPayUpdatedInfo(json.data || {});
        populatePayFilters(payRowsOriginal);
        applyPayView();
      } catch (err) {
        showPayError(err.message || "조회 중 오류가 발생했습니다.");
        payRowsOriginal = [];
        setPayUpdatedInfo(null);
        resetPayFilters();
        renderPayRows([]);
      } finally {
        payBtnLoad.disabled = false;
      }
    });
  }

  // ── 지급률 데이터 초기화 버튼 ────────────────────────────────────────────
  const payBtnReset = document.getElementById("re-pay-btn-reset");
  if (payBtnReset) {
    payBtnReset.addEventListener("click", async function () {
      if (!confirm("전체 지급률 데이터를 삭제하겠습니까?\n이 작업은 되돌릴 수 없습니다.")) {
        return;
      }
      if (!PAY_RESET_URL) {
        showPayError("초기화 URL이 설정되지 않았습니다.");
        return;
      }
      payBtnReset.disabled = true;
      clearPayError();
      try {
        const res = await fetch(PAY_RESET_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": window.csrfToken || "" },
        });
        const json = await readJsonOrThrow(res);
        // 테이블 초기화 후 안내 메시지
        payRowsOriginal = [];
        setPayUpdatedInfo(null);
        resetPayFilters();
        if (payTbody) {
          payTbody.innerHTML =
            `<tr><td colspan="10" class="text-center text-muted py-3">${json.message || "데이터가 삭제되었습니다."}</td></tr>`;
        }
        if (payCountLabel) payCountLabel.textContent = "";
      } catch (err) {
        showPayError(err.message || "초기화 중 오류가 발생했습니다.");
      } finally {
        payBtnReset.disabled = false;
      }
    });
  }

  // ── 필터 이벤트 ──────────────────────────────────────────────────────────────
  if (payFilterInsurer) payFilterInsurer.addEventListener("change", applyPayView);
  if (payFilterCov)     payFilterCov.addEventListener("change", applyPayView);
  if (payKeyword)       payKeyword.addEventListener("input",  applyPayView);

  // ── 지급률 업로드 저장 버튼 ─────────────────────────────────────────────────
  if (btnPaySave) {
    btnPaySave.addEventListener("click", async function () {
      clearPayError();
      const fileInput = document.getElementById("re-pay-modal-file");
      const file      = fileInput?.files[0];

      if (!file) { showPayError("파일을 선택해 주세요."); return; }

      const fd = new FormData();
      fd.append("insurer_type",   "life");
      fd.append("category",       "pay");
      fd.append("normalize_mode", "replace");
      fd.append("file",           file);

      btnPaySave.disabled = true;
      try {
        const res = await fetch(UPLOAD_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": window.csrfToken || "" },
          body: fd,
        });
        const json = await res.json();
        if (json.ok) {
          bootstrap.Modal.getInstance(
            document.getElementById("rateExamplePayUploadModal")
          )?.hide();
          location.reload();
        } else {
          showPayError(json.message || "업로드에 실패했습니다.");
        }
      } catch (e) {
        showPayError("네트워크 오류가 발생했습니다.");
      } finally {
        btnPaySave.disabled = false;
      }
    });
  }

  // ── 지급률 업로드 모달 초기화 ────────────────────────────────────────────────
  if (payUploadModalEl) {
    payUploadModalEl.addEventListener("show.bs.modal", function () {
      clearPayError();
      const payFileInput = document.getElementById("re-pay-modal-file");
      if (payFileInput) payFileInput.value = "";
    });
  }

  // ── 지급률 확인 모달 초기화 ──────────────────────────────────────────────────
  // 열릴 때 에러만 초기화 — 조회 결과는 명시적 조회 버튼 클릭 시에만 갱신
  if (payModalEl) {
    payModalEl.addEventListener("show.bs.modal", function () {
      clearPayError();
    });
  }
})();
