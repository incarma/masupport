// django_ma/static/js/manual/manual_detail_block/sort_blocks.js
// - 각 섹션의 .manualBlocks 에 Sortable 적용
// - 같은 섹션 내 reorder 저장 (manual_block_reorder_ajax)
// - (옵션) 섹션 간 이동 허용 시: manual_block_move_ajax 호출

export function initBlockSortable({ S, rootEl, bootEl, csrfToken }) {
  const { toStr, isDigits, postJson } = S;

  if (typeof window.Sortable === "undefined") {
    console.warn("[sort_blocks] SortableJS not loaded.");
    return;
  }

  const reorderUrl = toStr(bootEl?.dataset?.blockReorderUrl || "");
  const moveUrl = toStr(bootEl?.dataset?.blockMoveUrl || "");

  // reorderUrl은 필수
  if (!reorderUrl) return;

  // 중복 init 방지
  if (rootEl.dataset.blockSortBound === "true") return;
  rootEl.dataset.blockSortBound = "true";

  const getSectionIdFromBlocksEl = (blocksEl) => {
    const secEl = blocksEl?.closest?.(".manual-section");
    return toStr(secEl?.dataset?.sectionId || "");
  };

  const getBlockIds = (blocksEl) => {
    return Array.from(blocksEl.querySelectorAll(".manual-block"))
      .map((el) => toStr(el.dataset.blockId))
      .filter(isDigits)
      .map(Number);
  };

  const getBlockIdsAsStrings = (blocksEl) => {
    return Array.from(blocksEl.querySelectorAll(".manual-block"))
      .map((el) => toStr(el.dataset.blockId))
      .filter(isDigits);
  };

  function restoreBlockOrder(blocksEl, idsAsStrings) {
    const nodeById = new Map();
    blocksEl.querySelectorAll(".manual-block").forEach((el) => {
      const bid = toStr(el.dataset.blockId);
      if (isDigits(bid)) nodeById.set(String(bid), el);
    });

    idsAsStrings.forEach((id) => {
      const el = nodeById.get(String(id));
      if (el) blocksEl.appendChild(el);
    });
  }

  async function saveReorder(sectionId, blocksEl) {
    await postJson(reorderUrl, { section_id: Number(sectionId), block_ids: getBlockIds(blocksEl) }, csrfToken);
  }

  async function saveMove({ fromSectionId, toSectionId, fromEl, toEl }) {
    // moveUrl이 없으면 "카드 간 이동"은 막아야 안전
    if (!moveUrl) {
      // 원복을 위해 fromEl로 다시 되돌리기는 Sortable의 onMove/put 설정으로 막는 게 좋음
      throw new Error("블록 이동 URL이 없어 카드 간 이동을 저장할 수 없습니다.");
    }

    await postJson(
      moveUrl,
      {
        from_section_id: Number(fromSectionId),
        to_section_id: Number(toSectionId),
        from_block_ids: getBlockIds(fromEl),
        to_block_ids: getBlockIds(toEl),
      },
      csrfToken
    );
  }

  // 모든 섹션의 blocks 컨테이너에 Sortable 적용
  const blocksLists = Array.from(rootEl.querySelectorAll(".manualBlocks"));
  blocksLists.forEach((blocksEl) => {
    // 각 컨테이너별 중복 방지
    if (blocksEl.dataset.sortableBound === "1") return;
    blocksEl.dataset.sortableBound = "1";

    new window.Sortable(blocksEl, {
      animation: 150,
      draggable: ".manual-block",
      handle: ".jsBlockDragHandle",     // 위에서 추가한 버튼
      ghostClass: "manual-sort-ghost",
      chosenClass: "manual-sort-chosen",

      // ✅ 카드 간 이동까지 허용하려면 group을 열어둠
      // moveUrl이 없으면 같은 카드 내 reorder만 허용하도록 put/pull 막음
      group: moveUrl
        ? { name: "manualBlocks", pull: true, put: true }
        : { name: "manualBlocks", pull: false, put: false },

      onStart: (evt) => {
        const fromEl = evt.from;
        if (fromEl) {
          fromEl.dataset.prevOrder = JSON.stringify(getBlockIdsAsStrings(fromEl));
        }
      },

      onEnd: async (evt) => {
        const fromEl = evt.from;
        const toEl = evt.to;
        if (!fromEl || !toEl) return;

        const fromSectionId = getSectionIdFromBlocksEl(fromEl);
        const toSectionId = getSectionIdFromBlocksEl(toEl);
        if (!isDigits(fromSectionId) || !isDigits(toSectionId)) return;

        try {
          if (fromSectionId === toSectionId) {
            // 같은 카드 내 reorder
            await saveReorder(fromSectionId, toEl);
          } else {
            // 카드 간 이동
            await saveMove({ fromSectionId, toSectionId, fromEl, toEl });
          }

          // Subnav는 섹션 제목/순서에 영향 없으니 rebuild 불필요
          // (원하면 안전하게 호출 가능)
          // window.ManualDetailSubnav?.rebuild?.();

        } catch (e) {
          console.error(e);
          alert(e?.message || "블록 순서 저장 중 오류가 발생했습니다.");

          try {
            const prevOrder = JSON.parse(fromEl.dataset.prevOrder || "[]");
            if (fromSectionId === toSectionId && prevOrder.length) {
              restoreBlockOrder(fromEl, prevOrder);
              return;
            }
          } catch (_) {}

          // 섹션 간 이동 실패는 양쪽 컨테이너 원복이 복잡하므로 리로드가 가장 안전
          window.location.reload();
        }
      },
    });
  });
}
