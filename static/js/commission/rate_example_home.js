(function () {
  "use strict";

  const root = document.getElementById("rate-example-root");
  if (!root) return;
  if (root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  // ── URL / CSRF ─────────────────────────────────────────────────────────────
  const UPLOAD_URL = root.dataset.uploadUrl;
  const CONVERSION_LIST_URL = root.dataset.conversionListUrl;
  const CONVERSION_STRATEGY_UPDATE_URL = root.dataset.conversionStrategyUpdateUrl;
  // 지급률 확인 모달 조회 URL — data-pay-list-url dataset에서 주입
  const PAY_LIST_URL = root.dataset.payListUrl;

  // ── 보험사 목록 (json_script 태그에서 읽기) ───────────────────────────────
  const LIFE_INSURERS = JSON.parse(
    document.getElementById("life-insurers-data").textContent
  );
  const NONLIFE_INSURERS = JSON.parse(
    document.getElementById("nonlife-insurers-data").textContent
  );

  // ── DataTables 초기화 ──────────────────────────────────────────────────────
  // typeof $ 는 $ 미선언 시에도 throw 없이 "undefined" 반환 (ECMAScript 보장).
  // typeof $.fn 은 $ 평가 후 .fn 접근이라 $ 미선언 시 ReferenceError → 사용 금지.
  const tableEl = document.getElementById("re-table");
  let table = null;
  if (tableEl && typeof $ !== "undefined" && $ && $.fn && $.fn.DataTable) {
    table = $(tableEl).DataTable({
      searching: false,
      pageLength: 20,
      language: {
        lengthMenu: "_MENU_ 건씩 보기",
        info: "_START_ - _END_ / 전체 _TOTAL_ 건",
        infoEmpty: "데이터 없음",
        paginate: { previous: "이전", next: "다음" },
        emptyTable: "등록된 예시표가 없습니다.",
        zeroRecords: "검색 결과 없음",
      },
      columnDefs: [
        { orderable: false, targets: [7] },  // 다운로드
        { orderable: false, targets: [8] },  // 삭제 (superuser 없으면 존재하지 않음)
      ],
    });
  }

  // ── 커스텀 필터 헬퍼 ──────────────────────────────────────────────────────
  function buildInsurerOptions(type) {
    const sel = document.getElementById("re-filter-insurer");
    sel.innerHTML = '<option value="">전체</option>';
    const list = type === "생명보험" ? LIFE_INSURERS
                : type === "손해보험" ? NONLIFE_INSURERS
                : [];
    list.forEach(function (name) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
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
          <td colspan="9" class="text-center text-muted py-3">
            조회된 정규화 데이터가 없습니다.
          </td>
        </tr>`;
      return;
    }

    convTbody.innerHTML = rows.map(function (row) {
      return `
        <tr>
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

  // ── 필터 이벤트 ───────────────────────────────────────────────────────────
  const filterType = document.getElementById("re-filter-type");
  const filterCat = document.getElementById("re-filter-cat");
  const filterInsurer = document.getElementById("re-filter-insurer");

  if (filterType) {
    filterType.addEventListener("change", function () {
      buildInsurerOptions(this.value);
      filterInsurer.value = "";
      if (table) {
        table.column(1).search(this.value).column(2).search("").draw();
      }
    });
  }

  if (filterCat) {
    filterCat.addEventListener("change", function () {
      if (table) table.column(2).search(this.value).draw();
    });
  }

  if (filterInsurer) {
    filterInsurer.addEventListener("change", function () {
      if (table) table.column(3).search(this.value).draw();
    });
  }

  // ── 업로드 모달: 생보 전용 보험사 선택 ────────────────────────────────
  const modalInsurer = document.getElementById("re-modal-insurer");
  const modalProductKindWrap = document.getElementById("re-modal-product-kind-wrap");
  const modalProductKind = document.getElementById("re-modal-product-kind");

  // ── KB 생명보험 환산율/수정률 상품 구분 활성화 ─────────────────────────
  function updateKbProductKindVisibility() {
    if (!modalProductKindWrap || !modalProductKind) return;

    const insurer = modalInsurer?.value || "";

    const shouldShow = (
      insurer === "KB"
    );

    modalProductKindWrap.classList.toggle("d-none", !shouldShow);
    modalProductKind.disabled = !shouldShow;

    if (!shouldShow) {
      modalProductKind.value = "";
    }
  }

  if (modalInsurer) {
    modalInsurer.addEventListener("change", updateKbProductKindVisibility);
  }

  function populateLifeInsurerSelect(sel, placeholder) {
    if (!sel) return;
    sel.disabled = false;
    sel.innerHTML = `<option value="">${placeholder || "선택"}</option>`;
    LIFE_INSURERS.forEach(function (name) {
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
  const fullTextModalEl = document.getElementById("reCellFullTextModal");
  const fullTextTitleEl = document.getElementById("re-cell-fulltext-title");
  const fullTextBodyEl = document.getElementById("re-cell-fulltext-body");

  let convRowsOriginal = [];
  let convSortKey = "";
  let convSortDir = "asc";

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
    renderConvRows(sortedConvRows(filteredConvRows()));
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
      const insurerType = "life";
      const category = "conv";
      const insurer = modalInsurer?.value || "";
      const productKind = modalProductKind?.value || "";
      const normalizeMode = document.querySelector(
        'input[name="normalize_mode"]:checked'
      )?.value || "replace";
      const fileInput = document.getElementById("re-modal-file");
      const file = fileInput?.files[0];

      if (!insurer) { showError("보험사를 선택해 주세요."); return; }
      if (
        insurer === "KB" &&
        !productKind
      ) {
        showError("KB 상품 구분을 선택해 주세요.");
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
      const typeVal    = "life";
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
  root.addEventListener("click", async function (e) {
    const btn = e.target.closest(".re-btn-delete");
    if (!btn) return;

    if (!confirm("정말 삭제하시겠습니까?")) return;

    const deleteUrl = btn.dataset.deleteUrl;
    if (!deleteUrl) return;

    btn.disabled = true;
    try {
      const res = await fetch(deleteUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": window.csrfToken || "" },
      });
      const json = await res.json();
      if (json.ok) {
        if (table) {
          const row = btn.closest("tr");
          table.row(row).remove().draw();
        } else {
          location.reload();
        }
      } else {
        alert(json.message || "삭제에 실패했습니다.");
        btn.disabled = false;
      }
    } catch (e) {
      alert("네트워크 오류가 발생했습니다.");
      btn.disabled = false;
    }
  });

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
        populateLifeInsurerSelect(modalInsurer, "선택");
      }

      const replaceMode = document.getElementById("re-modal-normalize-mode-replace");
      if (replaceMode) {
        replaceMode.checked = true;
      }

      updateKbProductKindVisibility();
    });
  }
  // ── 환산율/수정률 모달 초기화 (열릴 때 선택값 리셋) ──────────────────────
  const convModal = document.getElementById("rateExampleConvModal");
  if (convModal) {
    convModal.addEventListener("show.bs.modal", function () {
      if (convInsurer) {
        populateLifeInsurerSelect(convInsurer, "선택");
      }
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
      return (
        "<tr>" +
        "<td>" + escapeHtml(row.insurer || "") + "</td>" +
        "<td>" + escapeHtml(row.coverage_type || "") + "</td>" +
        cell(row.col_a) + cell(row.col_b) + cell(row.col_c) +
        cell(row.col_d) + cell(row.col_e) + cell(row.col_f) +
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
