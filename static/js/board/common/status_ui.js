// django_ma/static/js/board/common/status_ui.js
// =========================================================
// Board Common Status UI (FINAL REFACTOR)
// - post_list / post_detail / task_* 공용
//
// ✅ 목표
// 1) 상태값에 따라 select / badge에 표준 status-* 클래스를 적용
// 2) 필터용 select(name="status" 등)는 색칠 대상에서 제외
// 3) 인라인 업데이트(AJAX) 후에도 applyAll() 재호출로 재적용 가능
//
// ✅ 적용 대상 규칙(중요)
// - select:  class="status-select" AND data-status-ui="1" 인 경우만 적용
// - badge:   .status-badge, .status-pill (data-status 또는 textContent)
//
// ✅ 사용법(템플릿 권장)
// - 실제 상태 변경 select에만 data-status-ui="1" 추가
//   ex) <select class="status-select" data-status="{{...}}" data-status-ui="1">
//
// - init:
//   const status = window.Board?.Common?.initStatusUI?.({ preset: "post" });
//   status?.applyAll?.();
// =========================================================

(function () {
  "use strict";

  const Board = (window.Board = window.Board || {});
  Board.Common = Board.Common || {};

  const INIT_FLAG = "__boardStatusUIBound";
  const PAGE_SHOW_FLAG = "__boardStatusUIPageShowBound";
  const CTX_KEY = "__boardStatusUIContexts";

  // 프로젝트 표준 클래스 (CSS는 apps/board.css 또는 base.css에 존재)
  const STANDARD_CLASSES = ["status-start", "status-progress", "status-fix", "status-done", "status-reject"];

  // preset 별 상태값 -> 표준 클래스
  const PRESETS = {
    post: {
      "확인중": "status-start",
      "접수": "status-start",
      "진행중": "status-progress",
      "보완요청": "status-reject",
      "보완필요": "status-reject",
      "완료": "status-done",
      "처리완료": "status-done",
      "반려": "status-fix",
      "보류": "status-reject",
      "취소": "status-reject",
    },
    task: {
      "시작전": "status-start",
      "진행중": "status-progress",
      "보완필요": "status-reject",
      "보완요청": "status-reject",
      "완료": "status-done",
      "반려": "status-fix",
    },
  };

  /* =========================================================
   * utils
   * ========================================================= */
  function normalize(v) {
    return String(v ?? "").trim();
  }

  function clearStandardClasses(el) {
    if (!el) return;
    el.classList.remove(...STANDARD_CLASSES);
  }

  function resolveClassByPreset(presetName, rawStatus) {
    const p = PRESETS[presetName] || {};
    return p[normalize(rawStatus)] || "";
  }

  function applyStandardClass(el, cls) {
    if (!el) return;
    clearStandardClasses(el);
    if (cls) el.classList.add(cls);
  }

  function getStatusFromSelect(sel) {
    if (!(sel instanceof HTMLSelectElement)) return "";
    const opt = sel.options?.[sel.selectedIndex];
    return normalize(opt?.value || sel.value || sel.dataset.status || "");
  }

  function getStatusFromBadge(el) {
    return normalize(el?.dataset?.status || el?.textContent || "");
  }

  function getContexts() {
    if (!Array.isArray(Board.Common[CTX_KEY])) {
      Board.Common[CTX_KEY] = [];
    }
    return Board.Common[CTX_KEY];
  }

  function sameRoot(a, b) {
    return (a || document) === (b || document);
  }

  function registerContext(ctx) {
    const contexts = getContexts();
    const exists = contexts.some(
      (item) =>
        item.preset === ctx.preset &&
        sameRoot(item.root, ctx.root) &&
        JSON.stringify(item.badgeSelectors || []) === JSON.stringify(ctx.badgeSelectors || [])
    );
    if (!exists) contexts.push(ctx);
  }

  function bindPageShowReapply() {
    if (document.body.dataset[PAGE_SHOW_FLAG] === "1") return;
    document.body.dataset[PAGE_SHOW_FLAG] = "1";

    window.addEventListener("pageshow", () => {
      getContexts().forEach((ctx) => {
        applyAll({ preset: ctx.preset, root: ctx.root, badgeSelectors: ctx.badgeSelectors });
      });
    });
  }

  /* =========================================================
   * apply
   * ========================================================= */
  function isEligibleStatusSelect(sel) {
    // ✅ 필터 select(상태 전체 등)는 적용 제외
    // 실제 상태 변경 select에만 data-status-ui="1"을 붙여서 대상 지정
    return (
      sel instanceof HTMLSelectElement &&
      sel.classList.contains("status-select") &&
      String(sel.dataset.statusUi || "") === "1"
    );
  }

  function applyToSelect(sel, presetName) {
    const status = getStatusFromSelect(sel);
    const cls = resolveClassByPreset(presetName, status);

    // dataset 동기화(중요: CSS 또는 다른 로직에서 참조 가능)
    sel.dataset.status = status;
    sel.setAttribute("data-status", status);

    applyStandardClass(sel, cls);
  }

  function applyToBadge(badge, presetName) {
    const status = getStatusFromBadge(badge);
    const cls = resolveClassByPreset(presetName, status);

    badge.dataset.status = status;
    badge.setAttribute("data-status", status);

    applyStandardClass(badge, cls);
  }

  function applyAll({ preset = "post", root = document, badgeSelectors } = {}) {
    const scope = root || document;
    const badgeSel =
      Array.isArray(badgeSelectors) && badgeSelectors.length ? badgeSelectors : [".status-badge", ".status-pill"];

    // ✅ select: data-status-ui="1" 대상만
    scope.querySelectorAll("select.status-select").forEach((sel) => {
      if (!isEligibleStatusSelect(sel)) return;
      applyToSelect(sel, preset);
    });

    // badge
    badgeSel.forEach((selector) => {
      scope.querySelectorAll(selector).forEach((el) => applyToBadge(el, preset));
    });
  }

  /* =========================================================
   * public init
   * ========================================================= */
  Board.Common.initStatusUI = function initStatusUI(opts) {
    const preset = opts?.preset || "post";
    const badgeSelectors = opts?.badgeSelectors;
    const root = opts?.root || document;

    const bind = () => {
      registerContext({ preset, root, badgeSelectors });

      // 최초 1회 적용
      applyAll({ preset, root, badgeSelectors });
      bindPageShowReapply();

      // ✅ change 이벤트 위임: 전역 1회만
      if (document.body.dataset[INIT_FLAG] === "1") return;
      document.body.dataset[INIT_FLAG] = "1";

      document.addEventListener(
        "change",
        (e) => {
          const sel = e.target;
          if (!(sel instanceof HTMLSelectElement)) return;
          if (!isEligibleStatusSelect(sel)) return;

          getContexts().forEach((ctx) => {
            const currentRoot = ctx.root || document;
            if (currentRoot !== document && currentRoot && !currentRoot.contains(sel)) return;
            applyToSelect(sel, ctx.preset || "post");
          });
        },
        { passive: true }
      );
    };

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bind, { once: true });
    } else {
      bind();
    }

    return {
      applyAll: () => applyAll({ preset, root, badgeSelectors }),
    };
  };

  // (optional) debug export
  Board.Common.__StatusUI = { STANDARD_CLASSES, PRESETS, applyAll };
})();
