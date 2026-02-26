// django_ma/static/js/manual/manual_list_edit.js
// ============================================================================
// Manual List Edit Mode (FINAL)
// - superuser 전용 편집모드
//   · 드래그 정렬 (SortableJS)
//   · 삭제
//   · 제목 / 공개범위 일괄 수정
// - 편집모드가 아닐 때는 링크 이동 100% 보장
// - 이벤트 위임 + 중복 바인딩 방지
// ============================================================================

(() => {
  const S = window.ManualShared;
  if (!S) {
    console.error("[manual_list_edit] ManualShared not loaded.");
    return;
  }

  const {
    toStr,
    isDigits,
    getCSRFTokenFromForm,
    setBtnLoading,
    postJson,
  } = S;

  /* ------------------------------------------------------------------------
   * DOM / Boot
   * --------------------------------------------------------------------- */
  const listEl = document.getElementById("manualListGroup");
  const btnEdit = document.getElementById("btnManualEditMode");
  const btnSave = document.getElementById("btnManualSaveOrder");
  const btnDone = document.getElementById("btnManualDone");
  const csrfForm = document.getElementById("manualEditCsrfForm");

  if (!listEl || !btnEdit || !btnSave || !btnDone || !csrfForm) return;

  // 중복 바인딩 방지
  if (listEl.dataset.bound === "true") return;
  listEl.dataset.bound = "true";

  // SortableJS 필수
  if (typeof window.Sortable === "undefined") {
    console.error("[manual_list_edit] SortableJS not loaded.");
    return;
  }

  const csrfToken = getCSRFTokenFromForm(csrfForm);

  // Boot: prefer DOM dataset, fallback to window.ManualListBoot (legacy)
  const bootEl =
    document.getElementById("manualListBoot") ||
    document.getElementById("manual-list-boot");

  // dataset은 kebab-case(data-reorder-url) → camelCase(dataset.reorderUrl)
  const bootFromDom = bootEl?.dataset || {};
  const bootFromWin = window.ManualListBoot || {};

  const reorderUrl = toStr(bootFromDom.reorderUrl || bootFromWin.reorderUrl);
  const deleteUrl = toStr(bootFromDom.deleteUrl || bootFromWin.deleteUrl);
  const bulkUpdateUrl = toStr(
    bootFromDom.bulkUpdateUrl || bootFromWin.bulkUpdateUrl
  );

  // superuser인데 boot url이 비면 템플릿 주입 누락/라우팅 name 오류
  if (!reorderUrl || !deleteUrl || !bulkUpdateUrl) {
    console.error("[manual_list_edit] boot urls missing", { reorderUrl, deleteUrl, bulkUpdateUrl, bootFromDom, bootFromWin });
  }

  const api = {
    json: (url, body) => postJson(url, body, csrfToken),
  };

  /* ------------------------------------------------------------------------
   * State
   * --------------------------------------------------------------------- */
  let isEditMode = false;
  let sortable = null;

  /* ------------------------------------------------------------------------
   * Helpers
   * --------------------------------------------------------------------- */
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const getItems = () => qsa("a.manual-item", listEl);

  function alertBox(msg) {
    window.alert(toStr(msg) || "오류가 발생했습니다.");
  }

  /* ------------------------------------------------------------------------
   * Link handling
   * - 편집모드에서는 링크 이동 완전 차단
   * --------------------------------------------------------------------- */
  function blockOrRestoreLinks(block) {
    getItems().forEach((a) => {
      const href = toStr(a.dataset.href || a.getAttribute("href") || "#");
      if (block) {
        a.dataset.href = href;
        a.setAttribute("href", "javascript:void(0)");
      } else {
        a.setAttribute("href", href);
      }
    });
  }

  /* ------------------------------------------------------------------------
   * Title / Access Editors
   * --------------------------------------------------------------------- */
  function toggleEditors(edit) {
    getItems().forEach((a) => {
      const text = a.querySelector(".manual-title-text");
      const input = a.querySelector(".manual-title-input");
      const access = a.querySelector(".manual-access-select");

      if (text && input) {
        input.value = toStr(text.textContent);
        text.classList.toggle("d-none", edit);
        input.classList.toggle("d-none", !edit);
      }

      if (access) {
        access.value = toStr(a.dataset.access || "normal");
        access.classList.toggle("d-none", !edit);
      }

      // 배지는 편집모드에서 숨김
      qsa(".manual-badge-admin, .manual-badge-staff", a)
        .forEach((b) => b.classList.toggle("d-none", edit));
    });
  }

  /* ------------------------------------------------------------------------
   * Sortable
   * --------------------------------------------------------------------- */
  function enableSortable() {
    if (sortable) return;
    sortable = new Sortable(listEl, {
      animation: 150,
      handle: ".manual-drag-handle",
      draggable: "a.manual-item",
      ghostClass: "sortable-ghost",
    });
  }

  function disableSortable() {
    sortable?.destroy();
    sortable = null;
  }

  /* ------------------------------------------------------------------------
   * UI State Toggle
   * --------------------------------------------------------------------- */
  function setEditUI(next) {
    isEditMode = !!next;

    qsa(".manual-drag-handle", listEl)
      .forEach((el) => el.classList.toggle("d-none", !isEditMode));
    qsa(".btn-manual-delete", listEl)
      .forEach((el) => el.classList.toggle("d-none", !isEditMode));

    blockOrRestoreLinks(isEditMode);
    toggleEditors(isEditMode);

    btnEdit.classList.toggle("d-none", isEditMode);
    btnSave.classList.toggle("d-none", !isEditMode);
    btnDone.classList.toggle("d-none", !isEditMode);
  }

  /* ------------------------------------------------------------------------
   * Collect & Apply Changes
   * --------------------------------------------------------------------- */
  function collectMetaChanges() {
    const items = [];

    getItems().forEach((a) => {
      const id = a.dataset.id;
      if (!isDigits(id)) return;

      const oldTitle = toStr(a.querySelector(".manual-title-text")?.textContent);
      const newTitle = toStr(a.querySelector(".manual-title-input")?.value);
      const oldAccess = toStr(a.dataset.access || "normal");
      const newAccess = toStr(a.querySelector(".manual-access-select")?.value);

      if (!newTitle) throw new Error("제목은 비워둘 수 없습니다.");
      if (newTitle.length > 80) throw new Error("제목은 80자 이하여야 합니다.");

      if (newTitle !== oldTitle || newAccess !== oldAccess) {
        items.push({ id: Number(id), title: newTitle, access: newAccess });
      }
    });

    return items;
  }

  function applyServerUpdated(data) {
    (data?.updated || []).forEach((u) => {
      const a = listEl.querySelector(`a.manual-item[data-id="${u.id}"]`);
      if (!a) return;

      a.querySelector(".manual-title-text").textContent = u.title;
      a.querySelector(".manual-title-input").value = u.title;
      a.dataset.access = u.admin_only ? "admin" : (u.is_published ? "normal" : "staff");
    });
  }

  /* ------------------------------------------------------------------------
   * Save
   * --------------------------------------------------------------------- */
  async function saveAll() {
    try {
      setBtnLoading(btnSave, true, "저장중...");

      const metaItems = collectMetaChanges();
      if (metaItems.length) {
        const data = await api.json(bulkUpdateUrl, { items: metaItems });
        applyServerUpdated(data);
      }

      const ordered_ids = getItems().map((a) => a.dataset.id);
      await api.json(reorderUrl, { ordered_ids });

      alertBox("저장되었습니다.");
    } catch (e) {
      console.error(e);
      alertBox(e.message);
    } finally {
      setBtnLoading(btnSave, false);
    }
  }

  /* ------------------------------------------------------------------------
   * Events
   * --------------------------------------------------------------------- */
  btnEdit.addEventListener("click", () => {
    setEditUI(true);
    enableSortable();
  });

  btnDone.addEventListener("click", () => {
    disableSortable();
    setEditUI(false);
  });

  btnSave.addEventListener("click", saveAll);

  // 삭제 (위임)
  listEl.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-manual-delete");
    if (!btn || !isEditMode) return;

    e.preventDefault();
    e.stopPropagation();

    const item = btn.closest("a.manual-item");
    const id = item?.dataset?.id;
    if (!isDigits(id)) return;

    if (!confirm("정말 삭제하시겠습니까?")) return;

    try {
      btn.disabled = true;
      await api.json(deleteUrl, { id: Number(id) });
      item.remove();
    } catch (err) {
      btn.disabled = false;
      alertBox(err.message);
    }
  });

  /* ------------------------------------------------------------------------
   * Init
   * --------------------------------------------------------------------- */
  setEditUI(false);
})();
