/* django_ma/static/js/commission/deposit_home.js
 * Deposit Home (채권현황) - FINAL (Refactor)
 *
 * ✅ 핵심 동작 (기존 유지)
 * - 대상자 선택(userSelected 이벤트) → pushState로 URL만 변경 + 즉시 fetch&render (새로고침 없음)
 * - 뒤로가기(popstate) → URL의 user 파라미터로 재렌더
 * - data-bind 기반 자동 바인딩(템플릿 legacy 키 ↔ API 키 mismatch는 alias로 흡수)
 * - surety/other 테이블 렌더 + 말줄임(.ellipsis-cell) 클릭 시 전체보기 모달
 * - 지원신청서 버튼: user 선택 시 활성화 → support-pdf URL로 이동
 *
 * ✅ 리팩토링 목표(기능 변화 없음)
 * - 공통 유틸(텍스트/포맷/escape/fetch/unwrap) 모듈화(로컬)
 * - 기능 단위로 섹션 재정렬 + 주석 보강
 * - 전역 플래그/이벤트 중복 바인딩 방지 유지
 */
(() => {
  "use strict";

  /* ==========================================================
   * 0) Boot / Guard
   * ========================================================== */
  const root = document.getElementById("deposit-home");
  if (!root) return;
  // ✅ FIX:
  // - 일부 data-bind 섹션이 #deposit-home 바깥에 있을 수 있어
  //   바인딩 탐색 범위를 document로 확장한다.
  // - 이 스크립트는 #deposit-home 존재 시에만 실행되므로 안전.

  console.log("[DepositHome] loaded", { href: location.href });
  
  const bindRoot = document;

  const DEBUG = false;
  const log = (...args) => DEBUG && console.log("[DepositHome]", ...args);

  const ds = root.dataset || {};

  /* ==========================================================
   * 1) URL config (dataset 우선, 없으면 기본값) - 기존 유지
   * ========================================================== */
  const URLS = {
    page: ds.resetUrl || "/commission/deposit/",
    userDetail: ds.userDetailUrl || "/commission/api/user-detail/",
    summary: ds.depositSummaryUrl || "/commission/api/deposit-summary/",
    surety: ds.depositSuretyUrl || "/commission/api/deposit-surety/",
    other: ds.depositOtherUrl || "/commission/api/deposit-other/",
    supportPdf: ds.supportPdfUrl || "/commission/api/support-pdf/",
  };

  /* ==========================================================
   * 2) DOM refs
   * ========================================================== */
  const els = {
    supportPdfBtn: document.getElementById("supportPdfBtn"),
    resetBtn: document.getElementById("resetUserBtn"),
    empIdSpan: document.getElementById("target_emp_id"), // fallback only

    suretyTbody: document.getElementById("suretyTableBody"),
    otherTbody: document.getElementById("otherTableBody"),
  };

  /* ==========================================================
   * 3) Common Utils (local-module style)
   * ========================================================== */
  const U = (() => {
    const toText = (v) => (v === null || v === undefined ? "" : String(v));

    const safeSetText = (node, text) => {
      if (!node) return;
      node.textContent =
        text === null || text === undefined || text === "" ? "-" : String(text);
    };

    const readTextOrValue = (el) => {
      if (!el) return "";
      if ("value" in el) {
        const v = String(el.value || "").trim();
        if (v) return v;
      }
      return String(el.textContent || "").trim();
    };

    const qsUser = () => new URL(window.location.href).searchParams.get("user") || "";

    /* money/percent 안전 포맷 (문자열은 그대로 통과) */
    const comma = (v) => {
      const s = toText(v).trim();
      if (!s || s === "-" || s.toLowerCase() === "nan") return "-";

      const cleaned = s.replace(/,/g, "");
      const num = Number(cleaned);
      if (!Number.isFinite(num)) return s; // "정상/분급" 같은 문자열 방어
      return Math.trunc(num).toLocaleString("ko-KR");
    };

    const percent = (v) => {
      const s = toText(v).trim();
      if (!s || s === "-" || s.toLowerCase() === "nan") return "-";

      const cleaned = s.replace(/,/g, "");
      const num = Number(cleaned);
      if (!Number.isFinite(num)) return s;
      return `${num.toFixed(2)}%`;
    };

    /* HTML escape */
    const escapeHtml = (str) =>
      String(str ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    return {
      toText,
      safeSetText,
      readTextOrValue,
      qsUser,
      comma,
      percent,
      escapeHtml,
    };
  })();

  /* ==========================================================
   * 4) Modal: ellipsis-cell 전체보기 (기존 UX 유지)
   * ========================================================== */
  const TextViewer = (() => {
    const hasBootstrapModal = () => !!(window.bootstrap && window.bootstrap.Modal);

    function ensureModal() {
      let modal = document.getElementById("textViewerModal");
      if (modal) return modal;

      modal = document.createElement("div");
      modal.id = "textViewerModal";
      modal.className = "modal fade";
      modal.tabIndex = -1;
      modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg">
          <div class="modal-content rounded-4">
            <div class="modal-header">
              <h6 class="modal-title fw-bold"></h6>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <pre class="mb-0 small" style="white-space:pre-wrap;word-break:break-word;"></pre>
            </div>
          </div>
        </div>`;
      document.body.appendChild(modal);
      return modal;
    }

    function open(title, text) {
      const safeTitle = title || "전체 내용";
      const safeText = (text || "").toString();

      // Bootstrap 모달 없으면 alert fallback - 기존 유지
      if (!hasBootstrapModal()) {
        alert(`${safeTitle}\n\n${safeText || "-"}`);
        return;
      }

      const modal = ensureModal();
      modal.querySelector(".modal-title").textContent = safeTitle;
      modal.querySelector("pre").textContent = safeText || "-";
      new bootstrap.Modal(modal).show();
    }

    function bindEllipsisClickOnce() {
      // 기존: 전역 플래그로 중복 바인딩 방지
      if (window.__depositEllipsisBound) return;
      window.__depositEllipsisBound = true;

      document.addEventListener("click", (e) => {
        const cell = e.target.closest(".ellipsis-cell");
        if (!cell) return;

        const full = String(cell.dataset.fullText || "").trim();
        const fallback = String(cell.textContent || "").trim();
        open("전체 내용", full || fallback || "-");
      });
    }

    return { open, bindEllipsisClickOnce };
  })();

  /* ==========================================================
   * 5) Fetch / unwrap helpers (응답 구조 변화 흡수) - 기존 로직 유지
   * ========================================================== */
  const Net = (() => {
    async function fetchJSON(url) {
      const res = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      const ct = (res.headers.get("content-type") || "").toLowerCase();
      const isJson = ct.includes("application/json");

      // JSON이 아니면(HTML/redirect/404페이지 등) 바로 텍스트로 읽어서 에러로 처리
      if (!isJson) {
        const text = await res.text().catch(() => "");
        throw new Error(
          `JSON 아님: ${res.status} ${res.statusText}\n` +
          `url=${url}\ncontent-type=${ct}\n` +
          `body=${text.slice(0, 200)}`
        );
      }

      const data = await res.json();

      if (!res.ok) {
        const msg = data?.message || `요청 실패 (${res.status})`;
        throw new Error(msg);
      }
      if (data && data.ok === false) {
        throw new Error(data.message || "요청 실패");
      }
      return data;
    }

    function unwrapFirstObject(data, candidates = []) {
      if (!data || typeof data !== "object") return null;

      // ✅ rows: [] 형태 지원 (첫 번째 row를 객체로 취급)
      if (Array.isArray(data.rows) && data.rows.length) return data.rows[0];
      if (Array.isArray(data.items) && data.items.length) return data.items[0];

      for (const k of candidates) {
        const v = data?.[k];
        if (v && typeof v === "object" && !Array.isArray(v)) return v;
        if (Array.isArray(v) && v.length) return v[0];
      }

      for (const k of ["user", "summary", "data", "result", "payload", "item"]) {
        const v = data?.[k];
        if (v && typeof v === "object" && !Array.isArray(v)) return v;
        if (Array.isArray(v) && v.length) return v[0];
      }
      return null;
    }

    function unwrapFirstArray(data, candidates = []) {
      if (!data || typeof data !== "object") return [];
      for (const k of candidates) {
        const v = data?.[k];
        if (Array.isArray(v)) return v;
      }
      // ✅ rows 배열 기본 지원
      if (Array.isArray(data.rows)) return data.rows;
      if (Array.isArray(data.items)) return data.items;

      for (const k of ["items", "results", "data", "list", "rows"]) {
        const v = data?.[k];
        if (Array.isArray(v)) return v;
      }
      return [];
    }

    return { fetchJSON, unwrapFirstObject, unwrapFirstArray };
  })();

  const api = {
    async userDetail(userId) {
      const url = `${URLS.userDetail}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.unwrapFirstObject(data, ["user", "data", "result", "item"]);
    },
    async summary(userId) {
      const url = `${URLS.summary}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);

      // ✅ backend가 {"ok":true,"rows":[{...}]}로 주는 케이스 흡수
      if (Array.isArray(data?.rows)) return data.rows[0] || null;

      return Net.unwrapFirstObject(data, ["summary", "data", "result", "item"]);
    },
    async surety(userId) {
      const url = `${URLS.surety}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.unwrapFirstArray(data, ["rows", "items", "results", "data", "list"]);
    },
    async other(userId) {
      const url = `${URLS.other}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.unwrapFirstArray(data, ["rows", "items", "results", "data", "list"]);
    },
  };

  /* ==========================================================
   * 6) data-bind 렌더 (legacy alias 흡수) - 기존 유지
   * ========================================================== */
  const Binder = (() => {
    const BIND_ALIAS = {
      // target.*
      "target.emp_id": "target.id",
      "target.join_date": "target.join_date_display",
      "target.leave_date": "target.retire_date_display",

      // summary.* legacy
      "summary.final_pay": "summary.final_payment",
      "summary.long_term": "summary.sales_total",
      "summary.loss_asset": "summary.maint_total",
      "summary.deposit_total": "summary.debt_total",
      "summary.etc_total": "summary.other_total",
      "summary.need_deposit": "summary.required_debt",
      "summary.final_extra_pay": "summary.final_excess_amount",
      "summary.month1": "summary.div_1m",
      "summary.month2": "summary.div_2m",
      "summary.month3": "summary.div_3m",

      // ✅ FIX: prefix 없이 쓰인 data-bind도 summary 기준으로 매핑
      // (deposit_home.html에서 final_payment 같은 키를 그대로 쓰는 케이스 대응)
      "final_payment": "summary.final_payment",
      "sales_total": "summary.sales_total",
      "refund_expected": "summary.refund_expected",
      "pay_expected": "summary.pay_expected",
      "maint_total": "summary.maint_total",
      "debt_total": "summary.debt_total",
      "surety_total": "summary.surety_total",
      "other_total": "summary.other_total",
      "required_debt": "summary.required_debt",
      "final_excess_amount": "summary.final_excess_amount",
      // 유지합계/유지채권합계(백엔드 패치 반영 시)
      "surety_keep_total": "summary.surety_keep_total",
      "other_keep_total": "summary.other_keep_total",
      "debt_keep_total": "summary.debt_keep_total",
    };

    function resolveBindKey(key) {
      const k = String(key || "").trim();
      if (!k) return k;
      if (BIND_ALIAS[k]) return BIND_ALIAS[k];

      // ✅ FIX: prefix 없는 키는 summary → target 순으로 자동 탐색하도록 변환
      // ex) "final_payment" -> "summary.final_payment"
      if (!k.includes(".")) {
        return `summary.${k}`;
      }
      return k;
    }

    const getByPath = (obj, path) => {
      const parts = String(path || "").split(".");
      let cur = obj;
      for (const p of parts) {
        if (!cur) return undefined;
        cur = cur[p];
      }
      return cur;
    };

    function setSupportEnabled(userId) {
      if (!els.supportPdfBtn) return;
      els.supportPdfBtn.disabled = !String(userId || "").trim();
    }

    function renderBinds({ target, summary }) {
      const ctx = { target: target || {}, summary: summary || {} };

      bindRoot.querySelectorAll("[data-bind]").forEach((node) => {
        const rawKey = node.getAttribute("data-bind");
        const key = resolveBindKey(rawKey);
        const type = (node.getAttribute("data-type") || "").trim(); // money/percent/plain
        const v = getByPath(ctx, key);

        if (type === "percent") U.safeSetText(node, U.percent(v));
        else if (type === "money") U.safeSetText(node, U.comma(v));
        else U.safeSetText(node, U.toText(v).trim() || "-");
      });

      const uid = String(target?.id || "").trim();
      setSupportEnabled(uid);
    }

    return { renderBinds, setSupportEnabled };
  })();

  /* ==========================================================
   * 7) Table renderers (surety / other) - 기존 유지
   * ========================================================== */
  const Tables = (() => {
    function renderSurety(items) {
      if (!els.suretyTbody) return;

      if (!items || items.length === 0) {
        els.suretyTbody.innerHTML = `
          <tr><td class="text-nowrap text-center" colspan="6">표시할 보증보험 내역이 없습니다.</td></tr>
        `;
        return;
      }

      els.suretyTbody.innerHTML = items
        .map((x) => {
          const policy = U.toText(x.policy_no || "").trim();
          const policyCell = policy
            ? `<span class="ellipsis-cell" data-full-text="${U.escapeHtml(policy)}">${U.escapeHtml(policy)}</span>`
            : "-";

          return `
            <tr>
              <td class="text-nowrap">${U.escapeHtml(x.product_name || "")}</td>
              <td class="text-nowrap">${policyCell}</td>
              <td class="text-nowrap text-end">${U.comma(x.amount)}</td>
              <td class="text-nowrap">${U.escapeHtml(x.status || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.start_date || "-")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.end_date || "-")}</td>
            </tr>
          `;
        })
        .join("");
    }

    function renderOther(items) {
      if (!els.otherTbody) return;

      if (!items || items.length === 0) {
        els.otherTbody.innerHTML = `
          <tr><td class="text-nowrap text-center" colspan="7">표시할 기타채권 내역이 없습니다.</td></tr>
        `;
        return;
      }

      els.otherTbody.innerHTML = items
        .map((x) => {
          const memo = U.toText(x.memo || "").trim();
          const memoCell = memo
            ? `<span class="ellipsis-cell" data-full-text="${U.escapeHtml(memo)}">${U.escapeHtml(memo)}</span>`
            : "-";

          return `
            <tr>
              <td class="text-nowrap">${U.escapeHtml(x.product_name || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.product_type || "")}</td>
              <td class="text-nowrap text-end">${U.comma(x.amount)}</td>
              <td class="text-nowrap">${U.escapeHtml(x.status || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.bond_no || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.start_date || "-")}</td>
              <td class="text-nowrap">${memoCell}</td>
            </tr>
          `;
        })
        .join("");
    }

    function clearUI() {
      bindRoot.querySelectorAll("[data-bind]").forEach((n) => (n.textContent = "-"));

      if (els.suretyTbody) {
        els.suretyTbody.innerHTML = `
          <tr><td class="text-nowrap text-center" colspan="6">대상자를 선택하면 보증보험 내역이 표시됩니다.</td></tr>
        `;
      }
      if (els.otherTbody) {
        els.otherTbody.innerHTML = `
          <tr><td class="text-nowrap text-center" colspan="7">대상자를 선택하면 기타채권 내역이 표시됩니다.</td></tr>
        `;
      }

      Binder.setSupportEnabled("");
    }

    return { renderSurety, renderOther, clearUI };
  })();

  /* ==========================================================
   * 8) Main flow: load → render (기존 동작 유지)
   * ========================================================== */
  let currentUserId = "";

  async function loadAndRender(userId) {
    const uid = String(userId || "").trim();
    if (!uid) {
      currentUserId = "";
      Tables.clearUI();
      return;
    }

    currentUserId = uid;
    Binder.setSupportEnabled(uid);

    try {
      const [user, summary, surety, other] = await Promise.all([
        api.userDetail(uid),
        api.summary(uid),
        api.surety(uid),
        api.other(uid),
      ]);

      // ✅ 1회 강제 확인(운영에서 거슬리면 확인 후 제거)
      if (!window.__depositSummaryOnce) {
        window.__depositSummaryOnce = true;
        console.log("[DepositHome] summary keys:", Object.keys(summary || {}));
        console.log("[DepositHome] summary sample:", summary);
      }

      // DEBUG helper: 템플릿이 요구하는 summary.* 키가 응답에 없는 경우 경고
      if (DEBUG) {
        const keys = new Set(Object.keys(summary || {}));
        const missing = [];
        bindRoot.querySelectorAll("[data-bind^='summary.']").forEach((el) => {
          const k = (el.getAttribute("data-bind") || "").trim().slice("summary.".length);
          if (k && !keys.has(k)) missing.push(k);
        });
        if (missing.length) {
          console.warn("[DepositHome] summary missing keys:", Array.from(new Set(missing)));
        }
      }

      Binder.renderBinds({ target: user, summary });
      Tables.renderSurety(surety);
      Tables.renderOther(other);

      log("render ok", { uid, suretyCount: surety.length, otherCount: other.length });
    } catch (err) {
      console.error(err);
      alert(err?.message || "데이터 조회 중 오류가 발생했습니다.");
      // 기존 UX 유지: 일부라도 표시된 상태를 깨지 않기 위해 clearUI()는 호출하지 않음
    }
  }

  function pushUserToUrl(userId) {
    const uid = String(userId || "").trim();
    const url = new URL(window.location.href);
    if (uid) url.searchParams.set("user", uid);
    else url.searchParams.delete("user");
    window.history.pushState({}, "", url.toString());
  }

  /* ==========================================================
   * 9) Events (기존 동작 유지)
   * ========================================================== */
  function getSelectedUserIdFromEvent(e) {
    const d = e?.detail || {};

    // 1) 가장 흔한 케이스: detail에 id가 직접 들어오는 경우
    const direct =
      d.id ||
      d.user_id ||
      d.userId ||
      d.empId ||
      d.emp_id ||
      d.employee_id;

    if (direct) return String(direct).trim();

    // 2) ✅ 버그 원인: detail.user / detail.target / detail.payload 등이 "객체"로 오는 경우
    //    (search_user_modal이 user 객체를 그대로 detail에 실어 보내는 패턴)
    const obj =
      d.user ||
      d.target ||
      d.payload ||
      d.data ||
      d.result ||
      null;

    if (obj && typeof obj === "object") {
      const oid =
        obj.id ||
        obj.user_id ||
        obj.userId ||
        obj.empId ||
        obj.emp_id ||
        obj.employee_id;

      if (oid) return String(oid).trim();
    }

    // 3) detail.user가 문자열로 오는 케이스 방어
    if (typeof d.user === "string") return d.user.trim();

    return "";
  }

  function bindUserSelected() {
    const handler = (e) => {
      const userId = getSelectedUserIdFromEvent(e);
      if (userId === "[object Object]" || userId.includes("object Object")) return;
      if (!userId) return;

      pushUserToUrl(userId);
      loadAndRender(userId);
    };

    // 기존 유지: window + document 둘 다 수신
    window.addEventListener("userSelected", handler);
    document.addEventListener("userSelected", handler);
  }

  function bindReset() {
    if (!els.resetBtn) return;
    els.resetBtn.addEventListener("click", () => {
      pushUserToUrl("");
      loadAndRender("");
    });
  }

  function bindSupportPdf() {
    if (!els.supportPdfBtn) return;

    els.supportPdfBtn.addEventListener("click", () => {
      const uid =
        String(currentUserId || "").trim() || U.qsUser() || U.readTextOrValue(els.empIdSpan);

      if (!uid || uid === "-") {
        alert("대상자를 먼저 선택해주세요.");
        return;
      }

      window.location.href = `${URLS.supportPdf}?user=${encodeURIComponent(uid)}`;
    });
  }

  // 뒤로가기 지원 - 기존 유지
  window.addEventListener("popstate", () => {
    loadAndRender(U.qsUser());
  });

  /* ==========================================================
   * 10) Init
   * ========================================================== */
  function init() {
    TextViewer.bindEllipsisClickOnce();
    bindUserSelected();
    bindReset();
    bindSupportPdf();

    const initial = U.qsUser();
    if (initial) loadAndRender(initial);
    else Tables.clearUI();

    log("init", { URLS, initial });
  }

  init();
})();
