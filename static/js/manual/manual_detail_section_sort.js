// django_ma/static/js/manual/manual_detail_section_sort.js
// -----------------------------------------------------------------------------
// Manual Detail - Section Sort (FINAL - Refactor)
// - superuser만 활성화 (dataset에 reorder URL이 있을 때만)
// - SortableJS로 #manualSections 안의 .manual-section 드래그 정렬
// - 정렬 완료 시 manual_section_reorder_ajax 로 section_ids 저장
// - 성공/실패 모두 Subnav(목차) 링크를 DOM 기준으로 재정렬
// -----------------------------------------------------------------------------


(() => {
  const S = window.ManualShared;
  if (!S) {
    console.error("[manual_detail_section_sort] ManualShared not loaded.");
    return;
  }

  const { toStr, isDigits, getCSRFTokenFromForm, postJson } = S;

  /* =========================================================================
   * 0) DOM / Dataset
   * ========================================================================= */
  const sectionsEl = document.getElementById("manualSections");
  if (!sectionsEl) return;

  const reorderUrl = toStr(sectionsEl.dataset.sectionReorderUrl);
  const manualId = toStr(sectionsEl.dataset.manualId);

  // superuser만 reorderUrl이 들어오므로, 없으면 그냥 종료
  if (!reorderUrl) return;
  if (!isDigits(manualId)) return;

  if (typeof window.Sortable === "undefined") {
    console.warn("[manual_detail_section_sort] SortableJS not loaded. (superuser assets 확인)");
    return;
  }

  // 중복 바인딩 방지
  const htmlEl = document.documentElement;
  if (htmlEl.dataset.manualSectionSortBound === "true") return;
  htmlEl.dataset.manualSectionSortBound = "true";

  /* =========================================================================
   * 1) CSRF
   * ========================================================================= */
  // manual_detail_block.js에서 사용하는 CSRF form을 재사용 (없으면 빈 값)
  const csrfForm = document.getElementById("manualBlockCsrfForm");
  const csrfToken = csrfForm ? getCSRFTokenFromForm(csrfForm) : "";

  /* =========================================================================
   * 2) Order utils (snapshot/restore)
   * ========================================================================= */
  function getSectionIdListAsStrings() {
    return Array.from(sectionsEl.querySelectorAll(".manual-section"))
      .map((el) => toStr(el.dataset.sectionId))
      .filter(isDigits);
  }

  function getSectionIdListAsNumbers() {
    return getSectionIdListAsStrings().map(Number);
  }

  function restoreOrder(orderIdsAsStrings) {
    const nodeById = new Map();
    sectionsEl.querySelectorAll(".manual-section").forEach((el) => {
      const sid = toStr(el.dataset.sectionId);
      if (isDigits(sid)) nodeById.set(String(sid), el);
    });

    orderIdsAsStrings.forEach((id) => {
      const el = nodeById.get(String(id));
      if (el) sectionsEl.appendChild(el);
    });
  }

  /* =========================================================================
   * 3) Save
   * ========================================================================= */
  async function saveOrder(sectionIds, prevOrderAsStrings) {
    try {
      await postJson(
        reorderUrl,
        { manual_id: Number(manualId), section_ids: sectionIds },
        csrfToken
      );
      
      // ✅ Subnav 재정렬은 manual_detail_subnav.js의 DOM 기준 rebuild API로 단일화
      window.ManualDetailSubnav?.rebuild?.();
    } catch (e) {
      console.error(e);
      alert(e?.message || "카드 순서 저장 중 오류가 발생했습니다.");

      restoreOrder(prevOrderAsStrings);
      window.ManualDetailSubnav?.rebuild?.();
    }
  }

  /* =========================================================================
   * 4) Sortable init
   * ========================================================================= */
  let prevOrderAsStrings = getSectionIdListAsStrings();

  new window.Sortable(sectionsEl, {
    animation: 150,
    draggable: ".manual-section",
    handle: ".jsSectionDragHandle",
    ghostClass: "manual-sort-ghost",
    chosenClass: "manual-sort-chosen",

    onStart: () => {
      prevOrderAsStrings = getSectionIdListAsStrings();
    },

    onEnd: async () => {
      const currentIds = getSectionIdListAsNumbers();
      if (!currentIds.length) return;

      const nowAsStrings = currentIds.map(String);
      if (JSON.stringify(nowAsStrings) === JSON.stringify(prevOrderAsStrings)) return;

      await saveOrder(currentIds, prevOrderAsStrings);
    },
  });
})();
