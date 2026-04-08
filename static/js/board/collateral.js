/**
 * board/static/js/board/collateral.js
 * ============================================================
 * 담보평가(근저당조회) 계산기 — IIFE
 * 네임스페이스: window.CollateralApp
 *
 * ── 규약 준수 ─────────────────────────────────────────────
 *  Boot   : #collateralBoot dataset 만 읽음
 *  CSRF   : window.csrfToken → [name=csrfmiddlewaretoken] → cookie
 *  fetch  : credentials:"same-origin" + X-Requested-With
 *  중복제출: dataset.submitting="1"
 *  DOM가드 : if (!el) return
 *  BFCache: dataset.inited="1"
 *
 * ── search_user_modal.js 연동 ─────────────────────────────
 *  선택 완료 시 search_user_modal.js 가 발행하는
 *  CustomEvent("userSelected", { detail: selected }) 를 수신.
 *  직접 콜백 주입 없이 이벤트 리스닝만 사용.
 * ============================================================
 */
(function () {
  "use strict";

  /* ── 내부 상태 ─────────────────────────────────────────── */
  var _calcUrl      = "";
  var _deleteBase   = "";
  var _canDelete    = false;
  var _targetUserId = "";
  var _dt           = null;   /* DataTables 인스턴스 */

  /* ── DOM 헬퍼 ─────────────────────────────────────────── */
  function qs(sel, ctx) {
    return (ctx || document).querySelector(sel);
  }

  /* ── CSRF 토큰 탐색 (SSOT 우선순위) ─────────────────── */
  function getCSRF() {
    if (window.csrfToken) return window.csrfToken;
    var h = qs("[name=csrfmiddlewaretoken]");
    if (h) return h.value;
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  /* ── 금액 포맷 유틸 ──────────────────────────────────── */
  /** 정수 → "1,234,567" */
  function fmt(val) {
    var n = parseInt(val, 10);
    return isNaN(n) ? "0" : n.toLocaleString("ko-KR");
  }

  /** "1,234,567원" → 1234567 */
  function parse(str) {
    var n = parseInt(String(str || "0").replace(/[^0-9]/g, ""), 10);
    return isNaN(n) ? 0 : n;
  }

  /* ── 입력 필드 콤마 포맷 자동 바인딩 ────────────────── */
  function bindMoneyFmt(el) {
    if (!el) return;
    el.addEventListener("input", function () {
      var raw  = parse(this.value);
      var pos  = this.selectionStart;
      var prev = this.value.length;
      this.value = raw === 0 ? "" : fmt(raw);
      var diff = this.value.length - prev;
      try { this.setSelectionRange(pos + diff, pos + diff); } catch (_) {}
    });
    el.addEventListener("blur", function () {
      this.value = fmt(parse(this.value));
    });
  }

  /* ══════════════════════════════════════════════════════
   * 결과 카드 렌더링
   * ════════════════════════════════════════════════════ */
  function renderResult(data) {
    var card   = qs("#calcResultCard");
    var header = qs("#resultCardHeader");
    var body   = qs("#calcResultBody");
    var errBox = qs("#calcErrorBox");
    if (!card || !body) return;

    if (errBox) errBox.classList.add("d-none");

    var isZero = (data.max_collateral === 0);
    header.className  = "card-header fw-semibold text-white " +
                        (isZero ? "bg-secondary" : "bg-success");
    header.textContent = "계산 결과";

    body.innerHTML =
      '<div class="row g-3">' +
        '<div class="col-sm-4">' +
          '<div class="text-muted small mb-1">적용 비율</div>' +
          '<div class="fw-bold fs-5">' + (data.apply_rate || "—") + '%</div>' +
        '</div>' +
        '<div class="col-sm-4">' +
          '<div class="text-muted small mb-1">담보기준금액</div>' +
          '<div class="fw-bold">' + fmt(data.base_amount) + ' 원</div>' +
        '</div>' +
        '<div class="col-sm-4">' +
          '<div class="text-muted small mb-1">★ 설정가능금액</div>' +
          '<div class="fw-bold fs-4 ' +
            (isZero ? "text-secondary" : "text-success") + '">' +
            fmt(data.max_collateral) + ' 원' +
          '</div>' +
          (isZero
            ? '<small class="text-danger">채권최고액이 담보기준금액을 초과합니다.</small>'
            : '') +
        '</div>' +
      '</div>';

    card.classList.remove("d-none");
  }

  /* ── 오류 메시지 표시 ────────────────────────────────── */
  function renderError(msg) {
    var errBox = qs("#calcErrorBox");
    var card   = qs("#calcResultCard");
    if (errBox) {
      errBox.textContent = msg || "오류가 발생했습니다.";
      errBox.classList.remove("d-none");
    }
    if (card) card.classList.add("d-none");
  }

  /* ══════════════════════════════════════════════════════
   * DataTables
   * ════════════════════════════════════════════════════ */
  function initDT() {
    if (typeof $ === "undefined" || typeof $.fn.DataTable === "undefined") return;
    var table = $("#evalHistoryTable");
    if (!table.length) return;
    /* 이미 초기화된 경우 재초기화 방지 */
    if ($.fn.DataTable.isDataTable(table)) return;
    _dt = table.DataTable({
      order:        [],          /* 초기 정렬 없음 — 서버 최신순 유지 */
      pageLength:   10,
      lengthMenu:   [10, 25, 50, 100],
      lengthChange: true,
      searching:    true,
      language: {
        search:      "검색:",
        lengthMenu:  "_MENU_ 건씩 보기",
        info:        "_START_–_END_ / 전체 _TOTAL_건",
        infoEmpty:   "조회 이력 없음",
        zeroRecords: "검색 결과 없음",
        paginate:    { previous: "이전", next: "다음" },
      },
    });
  }

  /* ── 계산 후 이력 행 삽입 ────────────────────────────── */
  function prependHistoryRow(payload, data) {
    var tbody = qs("#evalHistoryTbody");
    if (!tbody) return;

    /* 빈 행 제거 */
    var emptyRow = qs("#emptyRow");
    if (emptyRow) emptyRow.remove();

    /* 물건유형 텍스트 */
    var typeLabel = "";
    var sel = qs("#propertyType");
    if (sel && sel.options[sel.selectedIndex]) {
      typeLabel = sel.options[sel.selectedIndex].text;
    }

    /* 현재 시각 */
    var now = new Date();
    var ymd = now.getFullYear() + "-" +
      String(now.getMonth() + 1).padStart(2, "0") + "-" +
      String(now.getDate()).padStart(2, "0") + " " +
      String(now.getHours()).padStart(2, "0") + ":" +
      String(now.getMinutes()).padStart(2, "0");

    var maxVal    = data.max_collateral != null ? data.max_collateral : 0;
    var colorCls  = maxVal === 0 ? "text-danger" : "text-success";

    /* 대상자 표시 */
    var targetName   = String(data.target_name   || "").trim();
    var targetBranch = String(data.target_branch || "").trim();
    var targetId     = String(payload.target_user_id || "").trim();
    var targetDisplay = targetName
      ? (targetName + "(" + targetId + ")")
      : "—";
    var targetBranchDisplay = targetBranch || "—";

    /* 삭제 버튼 셀 (권한 있을 때만) */
    var deleteTd = _canDelete
      ? '<td class="text-center">' +
          '<button type="button"' +
          ' class="btn btn-outline-danger btn-sm btn-delete-eval"' +
          ' data-eval-id="' + data.eval_id + '">삭제</button>' +
        '</td>'
      : "";

    /* DataTables 살아있으면 파괴 후 행 삽입 → 재초기화 */
    if (_dt) { _dt.destroy(); _dt = null; }

    var tr = document.createElement("tr");
    tr.setAttribute("data-eval-id", String(data.eval_id));
    tr.innerHTML =
      '<td class="ps-3 text-nowrap text-muted" style="font-size:.85rem;">' + ymd + '</td>' +
      /* 요청자 소속/성명: JS 에서는 서버 정보가 없으므로 페이지 새로고침 전까지 — 표시 */
      '<td class="text-nowrap">—</td>' +
      '<td class="text-nowrap">—</td>' +
      /* 대상자 소속/성명 */
      '<td class="text-nowrap">' + targetBranchDisplay + '</td>' +
      '<td class="text-nowrap">' + targetDisplay + '</td>' +
      /* 물건유형 */
      '<td class="text-nowrap">' + typeLabel + '</td>' +
      /* 주소 */
      '<td class="board-ellipsis" style="max-width:160px;"' +
          ' title="' + String(payload.address || "") + '">' +
        (payload.address || "—") +
      '</td>' +
      /* 금액 */
      '<td class="text-end text-nowrap money-cell">' + fmt(payload.kb_price)   + '</td>' +
      '<td class="text-end text-nowrap money-cell">' + fmt(payload.prior_debt) + '</td>' +
      '<td class="text-end text-nowrap fw-semibold money-cell ' + colorCls + '">' +
        fmt(maxVal) +
      '</td>' +
      deleteTd;

    tbody.prepend(tr);
    initDT();
  }

  /* ══════════════════════════════════════════════════════
   * 계산 제출
   * ════════════════════════════════════════════════════ */
  function onCalcSubmit() {
    var btn = qs("#calcBtn");
    if (!btn || btn.dataset.submitting === "1") return;

    var propertyTypeEl = qs("#propertyType");
    var kbPriceEl      = qs("#kbPrice");
    var priorDebtEl    = qs("#priorDebt");
    if (!propertyTypeEl || !kbPriceEl || !priorDebtEl) return;

    var propertyType = propertyTypeEl.value;
    var kbPrice      = parse(kbPriceEl.value);
    var priorDebt    = parse(priorDebtEl.value);
    var address      = (qs("#address") ? qs("#address").value : "").trim();
    var memo         = (qs("#memo")    ? qs("#memo").value    : "").trim();

    /* 클라이언트 유효성 검사 */
    if (!propertyType) {
      renderError("물건 유형을 선택해 주세요.");
      return;
    }
    if (propertyType === "etc") {
      renderError("해당 물건 유형은 담보 설정이 불가합니다.");
      return;
    }
    if (kbPrice <= 0) {
      renderError("KB시세를 올바르게 입력해 주세요.");
      return;
    }

    /* 중복 제출 잠금 */
    btn.dataset.submitting = "1";
    btn.disabled = true;

    var payload = {
      property_type:  propertyType,
      kb_price:       kbPrice,
      prior_debt:     priorDebt,
      address:        address,
      memo:           memo,
      target_user_id: _targetUserId || null,
    };

    fetch(_calcUrl, {
      method:      "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type":     "application/json",
        "X-CSRFToken":      getCSRF(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
    .then(function (res) {
      if (!res.ok) throw new Error("서버 오류 (" + res.status + ")");
      return res.json();
    })
    .then(function (json) {
      if (json.ok) {
        renderResult(json.data);
        prependHistoryRow(payload, json.data);
      } else {
        renderError(json.message || "계산에 실패했습니다.");
      }
    })
    .catch(function (err) {
      renderError("요청 오류: " + err.message);
    })
    .finally(function () {
      delete btn.dataset.submitting;
      btn.disabled = false;
    });
  }

  /* ══════════════════════════════════════════════════════
   * 삭제 처리
   * ════════════════════════════════════════════════════ */
  function onDeleteEval(evalId) {
    if (!evalId) return;
    if (!confirm("이 이력을 삭제하시겠습니까?")) return;

    var url = _deleteBase + evalId + "/delete/";

    fetch(url, {
      method:      "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type":     "application/json",
        "X-CSRFToken":      getCSRF(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({}),
    })
    .then(function (res) { return res.json(); })
    .then(function (json) {
      if (json.ok) {
        var row = qs('tr[data-eval-id="' + evalId + '"]');
        if (row && _dt) {
          _dt.row(row).remove().draw();
        } else if (row) {
          row.remove();
        }
      } else {
        alert(json.message || "삭제에 실패했습니다.");
      }
    })
    .catch(function (err) {
      alert("요청 오류: " + err.message);
    });
  }

  /* ══════════════════════════════════════════════════════
   * 대상자 검색 — search_user_modal.js 연동
   *
   * search_user_modal.js 는 결과 항목 클릭 시
   *   document.dispatchEvent(new CustomEvent("userSelected", { detail: selected }))
   * 를 발행한다. 여기서 이 이벤트를 수신하여 대상자 필드를 채운다.
   *
   * ✅ collateral 페이지에서만 처리하도록 모달 표시 상태를 flag 로 관리.
   * ════════════════════════════════════════════════════ */
  function setupTargetSearch() {
    var btnSearch = qs("#btnSearchTarget");
    var btnClear  = qs("#btnClearTarget");
    var displayEl = qs("#targetUserDisplay");
    var branchEl  = qs("#targetBranchDisplay");
    var hiddenId  = qs("#targetUserId");

    if (!btnSearch) return;

    /* 모달이 이 페이지에서 열렸는지 추적하는 flag */
    var _modalOpenedHere = false;

    /* 검색 버튼 → 모달 오픈 */
    btnSearch.addEventListener("click", function () {
      var modalEl = document.getElementById("searchUserModal");
      if (!modalEl) return;
      _modalOpenedHere = true;
      var bsModal = window.bootstrap &&
                    bootstrap.Modal.getOrCreateInstance(modalEl);
      if (bsModal) bsModal.show();
    });

    /* 모달 닫힐 때 flag 초기화 */
    var modalEl = document.getElementById("searchUserModal");
    if (modalEl) {
      modalEl.addEventListener("hidden.bs.modal", function () {
        _modalOpenedHere = false;
      });
    }

    /* search_user_modal.js 선택 완료 이벤트 수신 */
    document.addEventListener("userSelected", function (e) {
      /* 이 페이지에서 열린 모달의 선택이 아니면 무시 */
      if (!_modalOpenedHere) return;
      _modalOpenedHere = false;   /* 한 번만 처리 */

      var user = e.detail || {};
      _targetUserId = String(user.id || user.pk || "").trim();
      if (!_targetUserId) return;

      var name   = String(user.name || "").trim();
      var branch = String(
        user.branch || user.affiliation_display || ""
      ).trim();

      if (displayEl) displayEl.value      = name + "(" + _targetUserId + ")";
      if (branchEl)  branchEl.textContent = branch;
      if (hiddenId)  hiddenId.value       = _targetUserId;
      if (btnClear)  btnClear.classList.remove("d-none");
    });

    /* 초기화 버튼 */
    if (btnClear) {
      btnClear.addEventListener("click", function () {
        _targetUserId = "";
        if (displayEl) displayEl.value      = "";
        if (branchEl)  branchEl.textContent = "";
        if (hiddenId)  hiddenId.value       = "";
        btnClear.classList.add("d-none");
      });
    }
  }

  /* ── 삭제 버튼 이벤트 위임 ──────────────────────────── */
  function bindDeleteButtons() {
    var tbody = qs("#evalHistoryTbody");
    if (!tbody) return;
    tbody.addEventListener("click", function (e) {
      var btn = e.target.closest(".btn-delete-eval");
      if (!btn) return;
      onDeleteEval(btn.dataset.evalId);
    });
  }

  /* ══════════════════════════════════════════════════════
   * 초기화
   * ════════════════════════════════════════════════════ */
  function init() {
    var root = qs("#collateralBoot");
    if (!root) return;
    if (root.dataset.inited === "1") return;
    root.dataset.inited = "1";

    /* Boot dataset 에서 URL / 권한 플래그 읽기 */
    _calcUrl    = root.dataset.calcUrl      || "";
    _deleteBase = root.dataset.deleteBaseUrl || "/board/collateral/";
    _canDelete  = root.dataset.canDelete    === "true";

    if (!_calcUrl) {
      console.error("[CollateralApp] calcUrl 없음. #collateralBoot dataset 확인.");
      return;
    }

    /* 금액 입력 자동 콤마 */
    bindMoneyFmt(qs("#kbPrice"));
    bindMoneyFmt(qs("#priorDebt"));

    /* 물건 유형 변경 시 결과/오류 초기화 */
    var typeSelect = qs("#propertyType");
    if (typeSelect) {
      typeSelect.addEventListener("change", function () {
        var c = qs("#calcResultCard");
        var e = qs("#calcErrorBox");
        if (c) c.classList.add("d-none");
        if (e) e.classList.add("d-none");
      });
    }

    /* 계산 버튼 */
    var calcBtn = qs("#calcBtn");
    if (calcBtn) calcBtn.addEventListener("click", onCalcSubmit);

    /* Enter 키 제출 (입력 필드 공통) */
    ["#kbPrice", "#priorDebt", "#address", "#memo"].forEach(function (s) {
      var el = qs(s);
      if (el) {
        el.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") onCalcSubmit();
        });
      }
    });

    setupTargetSearch();
    bindDeleteButtons();
    initDT();
  }

  /* DOMContentLoaded 이후 실행 */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* 전역 네임스페이스 (디버깅 및 외부 확장용) */
  window.CollateralApp = { init: init, fmt: fmt, parse: parse };
})();