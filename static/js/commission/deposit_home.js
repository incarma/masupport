/* django_ma/static/js/commission/deposit_home.js
 * Deposit Home (채권현황) - FINAL (Refactor)
 *
 * ✅ 주요 기능
 * - 대상자 선택(userSelected) → pushState로 URL만 변경 + 즉시 fetch&render (새로고침 없음)
 * - 뒤로가기(popstate) → URL의 user 파라미터로 재렌더
 * - data-bind 자동 바인딩(legacy key alias 흡수)
 * - surety/other 테이블 렌더 + 말줄임(.ellipsis-cell) 클릭 시 전체보기 모달
 * - ✅ 지원신청서 버튼: PDF 생성 제거 → "텍스트 지원신청서" 부트스트랩 모달 출력
 *
 * ✅ 리팩토링 목표
 * - 중복 제거(fetch/unwrap, summary rows 처리 등)
 * - 기능별 모듈화 + 주석 보강
 * - 전역 중복 바인딩 가드 유지
 */
(() => {
  "use strict";

  /* ==========================================================
   * 0) Boot / Guard
   * ========================================================== */
  const root = document.getElementById("deposit-home");
  if (!root) return;

  // 일부 data-bind가 root 밖에 있을 수 있으므로 탐색 범위를 document로 확장
  const bindRoot = document;

  const ds = root.dataset || {};

  /* ==========================================================
   * 1) URL config (dataset 우선, 없으면 기본값)
   * ========================================================== */
  const URLS = {
    userDetail: ds.userDetailUrl || "/commission/api/user-detail/",
    summary: ds.depositSummaryUrl || "/commission/api/deposit-summary/",
    surety: ds.depositSuretyUrl || "/commission/api/deposit-surety/",
    other: ds.depositOtherUrl || "/commission/api/deposit-other/",
    // supportPdfUrl은 더 이상 사용하지 않음 (PDF 생성 기능 제거)
  };

  /* ==========================================================
   * 2) DOM refs
   * ========================================================== */
  const els = {
    supportBtn: document.getElementById("supportPdfBtn"), // id는 그대로 유지(템플릿 영향 최소화)
    resetBtn: document.getElementById("resetUserBtn"),
    empIdSpan: document.getElementById("target_emp_id"), // fallback

    suretyTbody: document.getElementById("suretyTableBody"),
    otherTbody: document.getElementById("otherTableBody"),
  };

    /* ==========================================================
   * 3) Utils
   * ========================================================== */
  const U = (() => {
    const toText = (v) => (v === null || v === undefined ? "" : String(v));

    // 채권번호(bond_no)처럼 "식별자" 값은 천단위 콤마가 있으면 불편 → 제거 표시
    const stripCommas = (v) => toText(v).replace(/,/g, "").trim();

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

    const qsUser = () =>
      new URL(window.location.href).searchParams.get("user") || "";

    // money/percent 안전 포맷 (문자열은 그대로 통과)
    const comma = (v) => {
      const s = toText(v).trim();
      if (!s || s === "-" || s.toLowerCase() === "nan") return "-";

      const cleaned = s.replace(/,/g, "");
      const num = Number(cleaned);
      if (!Number.isFinite(num)) return s;
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

    // HTML escape
    const escapeHtml = (str) =>
      String(str ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    return {
      toText,
      stripCommas,
      safeSetText,
      readTextOrValue,
      qsUser,
      comma,
      percent,
      escapeHtml,
    };
  })();

  /* ==========================================================
   * 4) Modal: ellipsis-cell 전체보기 (공용)
   * ========================================================== */
  const TextViewer = (() => {
    const hasBS = () => !!(window.bootstrap && window.bootstrap.Modal);

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

      if (!hasBS()) {
        alert(`${safeTitle}\n\n${safeText || "-"}`);
        return;
      }

      const modal = ensureModal();
      modal.querySelector(".modal-title").textContent = safeTitle;
      modal.querySelector("pre").textContent = safeText || "-";
      new bootstrap.Modal(modal).show();
    }

    function bindEllipsisClickOnce() {
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
   * 5) Support Preview Modal (지원신청서 텍스트)
   * - ✅ PDF 생성 기능 삭제 → 이 모달이 대체
   * ========================================================== */
  const SupportModal = (() => {
    const hasBS = () => !!(window.bootstrap && window.bootstrap.Modal);

    function ensureModal() {
      let modal = document.getElementById("supportPreviewModal");
      if (modal) return modal;

      modal = document.createElement("div");
      modal.id = "supportPreviewModal";
      modal.className = "modal fade";
      modal.tabIndex = -1;
      modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
          <div class="modal-content rounded-4">
            <div class="modal-header">
              <h6 class="modal-title fw-bold">지원신청서</h6>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="닫기"></button>
            </div>
            <div class="modal-body">
              <div class="small text-muted mb-2">아래 내용을 확인 후 필요하면 복사해서 사용하세요.</div>
              <pre id="supportPreviewBody"
                   class="mb-0 small p-3 rounded-3 border"
                   style="white-space:pre-wrap;word-break:break-word;"></pre>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
              <button type="button" class="btn btn-primary btn-sm" id="supportPreviewCopyBtn">복사</button>
            </div>
          </div>
        </div>`;
      document.body.appendChild(modal);

      // copy handler (1회만 바인딩)
      if (!window.__depositSupportCopyBound) {
        window.__depositSupportCopyBound = true;
        document.addEventListener("click", async (e) => {
          const btn = e.target.closest("#supportPreviewCopyBtn");
          if (!btn) return;

          const body = document.getElementById("supportPreviewBody");
          const text = (body?.textContent || "").trim();
          if (!text) return;

          try {
            if (navigator.clipboard?.writeText) {
              await navigator.clipboard.writeText(text);
            } else {
              const ta = document.createElement("textarea");
              ta.value = text;
              ta.style.position = "fixed";
              ta.style.left = "-9999px";
              document.body.appendChild(ta);
              ta.select();
              document.execCommand("copy");
              ta.remove();
            }
            btn.textContent = "복사됨";
            setTimeout(() => (btn.textContent = "복사"), 900);
          } catch (err) {
            console.error(err);
            alert("복사에 실패했습니다. 내용을 선택해서 수동 복사해주세요.");
          }
        });
      }

      return modal;
    }

    function buildText({ target, summary, suretyItems, otherItems }) {
      const name = (target?.name || "").trim() || "-";
      const empId = (target?.id || "").trim() || "-";
      const part = (target?.part || "").trim() || "-";
      const branch = (target?.branch || "").trim() || "-";
      const joinDate = (target?.join_date_display || "").trim() || "-";

      // 화면 표기 기준(summary.*)
      const suretyTotal = U.comma(summary?.surety_total);
      const otherTotal = U.comma(summary?.other_total);
      const debtTotal = U.comma(summary?.debt_total);

      // ------------------------------------------------------------
      // helpers: number/status normalize
      // ------------------------------------------------------------
      const toNum = (v) => {
        const s = U.toText(v).trim().replace(/,/g, "");
        const n = Number(s);
        return Number.isFinite(n) ? n : 0;
      };
      const normStatus = (v) => U.toText(v).replace(/\s+/g, "").trim(); // "유지 인" 같은 케이스 방어
      const isKeep = (st) => ["유지", "유지인"].includes(normStatus(st));

      // ✅ 요구 포맷: "가. 대상 : {소속} {성명} FA ({사번}, {입사일} 입사)"
      const targetLine = `가. 대상 : ${branch} ${name} FA (${empId}, ${joinDate} 입사)`;

      // ------------------------------------------------------------
      // 다. 채권관리 - 데이터 리스트 기반(화면에서 이미 fetch한 surety/other 재사용)
      // ------------------------------------------------------------
      const S = Array.isArray(suretyItems) ? suretyItems : [];
      const O = Array.isArray(otherItems) ? otherItems : [];

      // 1) 보증보험: GA개인 + 유지 + 금액>0
      const suretyFiltered = S.filter((x) => {
        const pn = U.toText(x?.product_name).trim();
        const st = x?.status;
        const amt = toNum(x?.amount);
        return pn.includes("GA개인") && isKeep(st) && amt > 0;
      });

      // ✅ 보증보험 표기 금액: (요구사항) "대상금액"이 0이면 기간 생략 가능
      // - summary.surety_total 이 0이더라도 리스트에 남아있을 수 있고(또는 반대),
      //   표기 기준을 확실히 하려면 필터된 리스트 합계를 쓰는 게 가장 일관적임.
      const suretyFilteredSum = suretyFiltered.reduce((acc, x) => acc + toNum(x?.amount), 0);
      const suretyDisplay = U.comma(suretyFilteredSum);

      // 기간: start_date(min) ~ end_date(max)
      const dateKey = (s) => {
        // payload가 "YYYY-MM-DD" 또는 "-" 형태임
        const t = U.toText(s).trim();
        if (!t || t === "-") return "";
        // YYYY-MM-DD 정렬 가능 키
        return t;
      };
      const starts = suretyFiltered.map((x) => dateKey(x?.start_date)).filter(Boolean).sort();
      const ends = suretyFiltered.map((x) => dateKey(x?.end_date)).filter(Boolean).sort();
      const suretyRangeRaw =
        starts.length || ends.length
          ? `(${starts[0] || "-"} - ${ends[ends.length - 1] || "-"})`
          : "";
      // ✅ 보증보험 대상금액이 0이면 기간 표기 생략
      const suretyRange = suretyFilteredSum > 0 ? suretyRangeRaw : "";

      // 2) 기타채권 리스트: 보증내용=수수료 + 금액>0 + 상태=유지인 (전부 출력)
      const otherFiltered = O.filter((x) => {
        const pt = U.toText(x?.product_type).trim();
        const st = x?.status;
        const amt = toNum(x?.amount);
        // ✅ '유지'/'유지인' 모두 포함 (실데이터 변형 방어)
        return pt.includes("수수료") && isKeep(st) && amt > 0;
      });

      const otherLines =
        otherFiltered.length > 0
          ? otherFiltered.map((x) => {
              // ✅ 요청 포맷: 상품명(채권번호) : 가입금액원 (가입일 : YYYY-MM-DD)
              // ※ 메모는 표시하지 않음
              const pname = U.toText(x?.product_name).trim() || "-";
              const bondNo = U.stripCommas(x?.bond_no || "");
              const bondLabel = bondNo ? `(${bondNo})` : "";

              const amtNum = toNum(x?.amount);
              const amt = `${U.comma(amtNum)}원`;

              const start = U.toText(x?.start_date).trim() || "-";

              return `      ${pname}${bondLabel} : ${amt} (가입일 : ${start})`;
            })
          : ["      - (해당 없음)"];

      return [
        targetLine,
        "",
        "나. 요청사항 : ",
        "",
        "다. 채권관리",
        `   1. 채권합계 : ${debtTotal}원`,
        `   2. 보증보험 : ${suretyDisplay}원${suretyRange ? " " + suretyRange : ""}`,
        `   3. 기타채권 : ${otherTotal}원`,
        ...otherLines,
        "",
        "라. 리스크관리",
        `   1. 최종지급액 : ${U.comma(summary?.payment)}원`,
        `   2. 환수예상수수료 및 지급예상수수료`,
        `      - 환수예상수수료 : ${U.comma(summary?.refund_expected)}원`,
        `      - 지급예상수수료 : ${U.comma(summary?.pay_expected)}원`,
        `   3. 직전 3개월 장기총수수료 : ${U.comma(summary?.comm_3m)}원`,
        `   4. 응당수금률 (2-13회차 합산)`,
        `      - 생보 : ${U.percent(summary?.ls_2_13_due)}`,
        `      - 손보 : ${U.percent(summary?.ns_2_13_due)}`,
        `   5. 통산유지율 (25회차 통산)`,
        `      - 생보 : ${U.percent(summary?.ls_25_total)}`,
        `      - 손보 : ${U.percent(summary?.ns_25_total)}`,
        "",
        "※ 별첨",
        `   - ${branch} 업무요청서 1부.`,
        `   - ${name} FA 지표현황 1부.`,
        `   - ${name} FA 기타채권 캡처본 1부.`,
        `   - ${name} FA 환수리스트 캡처본 1부.`,
        "",
        "",
        "  끝.",
      ].join("\n");
    }

    function open({ target, summary, suretyItems, otherItems }) {
      const text = buildText({ target, summary, suretyItems, otherItems });

      if (!hasBS()) {
        alert(text);
        return;
      }

      const modal = ensureModal();
      const body = modal.querySelector("#supportPreviewBody");
      if (body) body.textContent = text || "-";

      new bootstrap.Modal(modal).show();
    }

    return { open };
  })();

  /* ==========================================================
   * 6) Network helpers
   * ========================================================== */
  const Net = (() => {
    async function fetchJSON(url) {
      const res = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (!ct.includes("application/json")) {
        const text = await res.text().catch(() => "");
        throw new Error(
          `JSON 아님: ${res.status} ${res.statusText}\nurl=${url}\ncontent-type=${ct}\nbody=${text.slice(0, 200)}`
        );
      }

      const data = await res.json();

      if (!res.ok) throw new Error(data?.message || `요청 실패 (${res.status})`);
      if (data && data.ok === false) throw new Error(data.message || "요청 실패");

      return data;
    }

    const firstObject = (data) => {
      if (!data || typeof data !== "object") return null;
      if (Array.isArray(data.rows) && data.rows.length) return data.rows[0];
      for (const k of ["user", "summary", "data", "result", "payload", "item"]) {
        const v = data?.[k];
        if (v && typeof v === "object" && !Array.isArray(v)) return v;
        if (Array.isArray(v) && v.length) return v[0];
      }
      return null;
    };

    const arrayRows = (data) => {
      if (!data || typeof data !== "object") return [];
      if (Array.isArray(data.rows)) return data.rows;
      for (const k of ["items", "results", "data", "list", "rows"]) {
        if (Array.isArray(data?.[k])) return data[k];
      }
      return [];
    };

    return { fetchJSON, firstObject, arrayRows };
  })();

  const api = {
    async userDetail(userId) {
      const url = `${URLS.userDetail}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.firstObject(data);
    },
    async summary(userId) {
      const url = `${URLS.summary}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.firstObject(data);
    },
    async surety(userId) {
      const url = `${URLS.surety}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.arrayRows(data);
    },
    async other(userId) {
      const url = `${URLS.other}?user=${encodeURIComponent(userId)}`;
      const data = await Net.fetchJSON(url);
      return Net.arrayRows(data);
    },
  };

    /* ==========================================================
   * 7) Binder: data-bind 렌더 (legacy alias 흡수)
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

      // prefix 없이 쓰인 키를 summary.*로 매핑
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
      // 유지합계
      "surety_keep_total": "summary.surety_keep_total",
      "other_keep_total": "summary.other_keep_total",
      "debt_keep_total": "summary.debt_keep_total",
    };

    const resolveKey = (raw) => {
      const k = String(raw || "").trim();
      if (!k) return k;
      if (BIND_ALIAS[k]) return BIND_ALIAS[k];
      if (!k.includes(".")) return `summary.${k}`;
      return k;
    };

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
      if (!els.supportBtn) return;
      els.supportBtn.disabled = !String(userId || "").trim();
    }

    function render({ target, summary }) {
      const ctx = { target: target || {}, summary: summary || {} };

      bindRoot.querySelectorAll("[data-bind]").forEach((node) => {
        const rawKey = node.getAttribute("data-bind");
        const key = resolveKey(rawKey);
        const type = (node.getAttribute("data-type") || "").trim(); // money/percent/plain
        const v = getByPath(ctx, key);

        if (type === "percent") U.safeSetText(node, U.percent(v));
        else if (type === "money") U.safeSetText(node, U.comma(v));
        else U.safeSetText(node, U.toText(v).trim() || "-");
      });

      setSupportEnabled(String(target?.id || "").trim());
    }

    return { render, setSupportEnabled };
  })();

  /* ==========================================================
   * 8) Tables: surety / other 렌더
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

          // ✅ 채권번호 콤마 제거 표시
          const bondNo = U.stripCommas(x.bond_no || "");

          return `
            <tr>
              <td class="text-nowrap">${U.escapeHtml(x.product_name || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(x.product_type || "")}</td>
              <td class="text-nowrap text-end">${U.comma(x.amount)}</td>
              <td class="text-nowrap">${U.escapeHtml(x.status || "")}</td>
              <td class="text-nowrap">${U.escapeHtml(bondNo)}</td>
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
   * 9) Main flow: load → render
   * ========================================================== */
  let currentUserId = "";
  let lastTarget = null;
  let lastSummary = null;
  let lastSurety = [];
  let lastOther = [];

  async function loadAndRender(userId) {
    const uid = String(userId || "").trim();
    if (!uid) {
      currentUserId = "";
      lastTarget = null;
      lastSummary = null;
      Tables.clearUI();
      return;
    }

    currentUserId = uid;
    Binder.setSupportEnabled(uid);

    try {
      const [target, summary, surety, other] = await Promise.all([
        api.userDetail(uid),
        api.summary(uid),
        api.surety(uid),
        api.other(uid),
      ]);

      lastTarget = target || { id: uid };
      lastSummary = summary || {};
      lastSurety = Array.isArray(surety) ? surety : [];
      lastOther = Array.isArray(other) ? other : [];

      Binder.render({ target: lastTarget, summary: lastSummary });
      Tables.renderSurety(surety);
      Tables.renderOther(other);
    } catch (err) {
      console.error(err);
      alert(err?.message || "데이터 조회 중 오류가 발생했습니다.");
      // UX: 일부라도 표시된 상태를 깨지 않기 위해 clearUI()는 호출하지 않음
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
   * 10) Events
   * ========================================================== */
  function getSelectedUserIdFromEvent(e) {
    const d = e?.detail || {};

    // detail에 id가 직접 들어오는 케이스
    const direct =
      d.id || d.user_id || d.userId || d.empId || d.emp_id || d.employee_id;
    if (direct) return String(direct).trim();

    // detail에 user/target 객체가 들어오는 케이스 방어
    const obj = d.user || d.target || d.payload || d.data || d.result || null;
    if (obj && typeof obj === "object") {
      const oid =
        obj.id || obj.user_id || obj.userId || obj.empId || obj.emp_id || obj.employee_id;
      if (oid) return String(oid).trim();
    }

    if (typeof d.user === "string") return d.user.trim();
    return "";
  }

  function bindUserSelected() {
    const handler = (e) => {
      const userId = getSelectedUserIdFromEvent(e);
      if (!userId || userId.includes("object Object")) return;

      pushUserToUrl(userId);
      loadAndRender(userId);
    };

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

  function bindSupportModal() {
    if (!els.supportBtn) return;

    els.supportBtn.addEventListener("click", () => {
      const uid =
        String(currentUserId || "").trim() ||
        U.qsUser() ||
        U.readTextOrValue(els.empIdSpan);

      if (!uid || uid === "-") {
        alert("대상자를 먼저 선택해주세요.");
        return;
      }

      // ✅ PDF 생성 제거 → 모달 텍스트 출력
      SupportModal.open({
        target: lastTarget || { id: uid },
        summary: lastSummary || {},
        suretyItems: lastSurety || [],
        otherItems: lastOther || [],
      });
    });
  }

  // 뒤로가기 지원
  window.addEventListener("popstate", () => {
    loadAndRender(U.qsUser());
  });

  /* ==========================================================
   * 11) Init
   * ========================================================== */
  function init() {
    TextViewer.bindEllipsisClickOnce();
    bindUserSelected();
    bindReset();
    bindSupportModal();

    const initial = U.qsUser();
    if (initial) loadAndRender(initial);
    else Tables.clearUI();
  }

  init();
})();