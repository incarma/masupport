// django_ma/static/js/manual/manual_detail_block/index.js
// -----------------------------------------------------------------------------
// Manual Detail Blocks (FINAL)
// - 이벤트 위임 + 상태 관리 + API 오케스트레이션
// - Quill/첨부: ./quill.js
// - 섹션 CRUD + Subnav 반영: ./section_subnav.js
// - 블록 정렬/이동(Sortable): ./sort_block.js
//
// 전제
// - window.ManualShared 가 선로딩되어 있어야 함 (manual/_shared.js)
// - superuser 에서만 실행됨(템플릿에서 type="module" 로드 자체를 제한)
// -----------------------------------------------------------------------------

import { createQuillManager } from "./quill.js";
import { createSectionSubnavManager } from "./section_subnav.js";
import { initBlockSortable } from "./sort_blocks.js";

(() => {
  const S = window.ManualShared;
  if (!S) {
    console.error("[manual_detail_block/index] ManualShared not loaded.");
    return;
  }

  const {
    toStr,
    isDigits,
    getCSRFTokenFromForm,
    showErrorBox,
    clearErrorBox,
    postJson,
    postForm,
    formatBytes,
  } = S;

  /* =========================================================================
   * 0) DOM refs
   * ========================================================================= */
  const rootEl = document.getElementById("manual-detail");
  const sectionsEl = document.getElementById("manualSections");
  const bootEl = document.getElementById("manualDetailBoot");

  const modalEl = document.getElementById("manualBlockModal");
  const btnSave = document.getElementById("btnManualBlockSave");
  const titleEl = document.getElementById("manualBlockModalTitle");
  const errBox = document.getElementById("manualBlockError");
  const csrfForm = document.getElementById("manualBlockCsrfForm");

  const btnAddSection = document.getElementById("btnAddManualSection");

  const imgInput = document.getElementById("manualBlockImageInput");
  const imgPreviewWrap = document.getElementById("manualBlockImagePreviewWrap");
  const imgPreview = document.getElementById("manualBlockImagePreview");
  const removeWrap = document.getElementById("manualBlockRemoveImageWrap");
  const removeChk = document.getElementById("manualBlockRemoveImage");

  const viewerModalEl = document.getElementById("manualImageViewer");
  const viewerImg = document.getElementById("manualViewerImg");

  const attachInput = document.getElementById("manualQuillAttachInput");

  // 필수 요소 체크 (깨지면 조용히 종료)
  if (!rootEl || !sectionsEl || !bootEl || !modalEl || !btnSave || !titleEl || !errBox || !csrfForm) {
    console.warn("[manual_detail_block/index] Required elements missing.");
    return;
  }

  /* =========================================================================
   * 0.1) Bind guard (BFCache / 중복 로드 방지) — rootEl = #manual-detail
   * ========================================================================= */
  if (rootEl.dataset.inited === "1") return;
  rootEl.dataset.inited = "1";

  /* =========================================================================
   * 0.2) URLs from Boot
   * ========================================================================= */
  const urls = {
    // Section
    sectionTitleUpdate: toStr(bootEl.dataset.sectionTitleUpdateUrl || ""),
    sectionDelete: toStr(bootEl.dataset.sectionDeleteUrl || ""),

    // Block
    blockDelete: toStr(bootEl.dataset.blockDeleteUrl || ""),
    blockReorder: toStr(bootEl.dataset.blockReorderUrl || ""),
    blockMove: toStr(bootEl.dataset.blockMoveUrl || ""),
  };

  /* =========================================================================
   * 0.3) API helpers
   * ========================================================================= */
  const csrfToken = getCSRFTokenFromForm(csrfForm);

  const api = {
    json: (url, body) => postJson(url, body, csrfToken),
    form: (url, fd) => postForm(url, fd, csrfToken),
  };

  const ui = {
    err: (msg) => showErrorBox(errBox, msg, false),
    clearErr: () => clearErrorBox(errBox),
  };

  /* =========================================================================
   * 1) State
   * ========================================================================= */
  const state = {
    mode: "add",            // "add" | "edit"
    editingBlockId: null,   // number|null
    currentSectionId: null, // number|null
    // 이미지 미리보기 blob url 해제용
    _previewBlobUrl: null,
  };

  /* =========================================================================
   * 2) Small utils
   * ========================================================================= */
  function isEmptyQuillHtml(html) {
    const s = toStr(html).trim();
    if (!s) return true;

    // 공백 제거 기준으로 Quill의 빈 문단 패턴 방어
    const normalized = s.replace(/\s+/g, "").toLowerCase();
    return normalized === "<p><br></p>" || normalized === "<p></p>";
  }

  function safeBootstrapModalShow(modalDom) {
    try {
      if (!modalDom || typeof bootstrap === "undefined") return false;
      const m = new bootstrap.Modal(modalDom);
      m.show();
      return true;
    } catch (e) {
      console.warn("[manual_detail_block/index] bootstrap modal show failed:", e);
      return false;
    }
  }

  function safeBootstrapModalHide(modalDom) {
    try {
      if (!modalDom || typeof bootstrap === "undefined") return false;
      bootstrap.Modal.getInstance(modalDom)?.hide();
      return true;
    } catch (e) {
      console.warn("[manual_detail_block/index] bootstrap modal hide failed:", e);
      return false;
    }
  }

  /* =========================================================================
   * 3) Image UI
   * ========================================================================= */
  function resetImageUI() {
    // blob url revoke
    if (state._previewBlobUrl) {
      try { URL.revokeObjectURL(state._previewBlobUrl); } catch (_) {}
      state._previewBlobUrl = null;
    }

    if (imgInput) imgInput.value = "";
    if (imgPreviewWrap) imgPreviewWrap.classList.add("d-none");
    if (imgPreview) imgPreview.src = "";
    if (removeWrap) removeWrap.classList.add("d-none");
    if (removeChk) removeChk.checked = false;
  }

  function showPreviewFromUrl(url) {
    if (!imgPreviewWrap || !imgPreview) return;

    const u = toStr(url);
    if (!u) {
      imgPreviewWrap.classList.add("d-none");
      imgPreview.src = "";
      return;
    }

    imgPreview.src = u;
    imgPreviewWrap.classList.remove("d-none");
  }

  imgInput?.addEventListener("change", () => {
    const file = imgInput?.files?.[0];
    if (!file) return;

    // 기존 blob url 정리 후 새로 생성
    if (state._previewBlobUrl) {
      try { URL.revokeObjectURL(state._previewBlobUrl); } catch (_) {}
      state._previewBlobUrl = null;
    }

    const blobUrl = URL.createObjectURL(file);
    state._previewBlobUrl = blobUrl;
    showPreviewFromUrl(blobUrl);
  });

  function openViewer(url) {
    if (!viewerModalEl || !viewerImg) return;
    const u = toStr(url);
    if (!u) return;

    viewerImg.src = u;
    // bootstrap이 없으면 새 탭으로라도 열기
    if (!safeBootstrapModalShow(viewerModalEl)) window.open(u, "_blank");
  }

  /* =========================================================================
   * 4) Quill manager (attach 포함)
   * ========================================================================= */
  const quillMgr = createQuillManager({
    S,
    modalEl,
    errBox,
    attachInput,
    api,
    state,
    formatBytes,
  });

  modalEl.addEventListener("shown.bs.modal", () => quillMgr.onModalShown());

  /* =========================================================================
   * 5) Section + Subnav manager
   * ========================================================================= */
  const secMgr = createSectionSubnavManager({
    S,
    api,
    sectionsEl,
    btnAddSection,
    sectionTitleUpdateUrl: urls.sectionTitleUpdate,
    sectionDeleteUrl: urls.sectionDelete,
  });

  /* =========================================================================
   * 6) Builders
   * ========================================================================= */
  function buildBlockElement(b) {
    const wrapper = document.createElement("div");
    wrapper.className = "border rounded-3 p-3 mb-3 manual-block";
    wrapper.dataset.blockId = b.id;
    wrapper.dataset.imageUrl = b.image_url || "";

    const leftHtml = b.image_url
      ? `<img src="${b.image_url}" class="manual-block-thumb jsManualImg" alt="manual image">`
      : `<div class="text-muted small py-4">이미지 없음</div>`;

    wrapper.innerHTML = `
      <div class="manual-block-grid">
        <div class="manual-block-media">${leftHtml}</div>
        <div class="manual-block-text manual-block-content">${b.content || ""}</div>
      </div>

      <div class="manual-block-actions">
        <button type="button"
                class="btn btn-sm btn-outline-secondary jsBlockDragHandle"
                title="드래그로 순서 변경"
                aria-label="블록 순서 변경">↕ 이동</button>

        <button type="button"
                class="btn btn-sm btn-outline-secondary btn-edit-block"
                data-bs-toggle="modal"
                data-bs-target="#manualBlockModal">수정</button>

        <button type="button"
                class="btn btn-sm btn-outline-danger btn-delete-block"
                data-block-id="${b.id}">삭제</button>
      </div>
    `;
    return wrapper;
  }

  /* =========================================================================
   * 7) Modal open helpers
   * ========================================================================= */
  function openForAdd(sectionId) {
    state.mode = "add";
    state.editingBlockId = null;
    state.currentSectionId = sectionId || null;

    titleEl.textContent = "내용 추가";
    ui.clearErr();
    resetImageUI();

    // Quill 초기화 타이밍 이슈 방지
    setTimeout(() => quillMgr.setHtml(""), 0);
  }

  function openForEdit(blockEl) {
    const bid = blockEl?.dataset?.blockId;
    if (!isDigits(bid)) return;

    state.mode = "edit";
    state.editingBlockId = Number(bid);
    state.currentSectionId = null;

    titleEl.textContent = "내용 수정";
    ui.clearErr();
    resetImageUI();

    const imgUrl = toStr(blockEl.dataset.imageUrl);
    if (imgUrl) {
      showPreviewFromUrl(imgUrl);
      removeWrap?.classList.remove("d-none");
    }

    const html = blockEl.querySelector(".manual-block-content")?.innerHTML || "";
    setTimeout(() => quillMgr.setHtml(html), 0);
  }

  /* =========================================================================
   * 8) Delete helpers
   * ========================================================================= */
  async function deleteBlockById(blockId, blockEl) {
    if (!urls.blockDelete) return alert("블록 삭제 URL이 없습니다. (manualDetailBoot 확인)");
    if (!isDigits(blockId)) return alert("block_id가 올바르지 않습니다.");
    if (!confirm("이 블록을 삭제할까요?")) return;

    try {
      await api.json(urls.blockDelete, { block_id: Number(blockId) });
      blockEl?.remove();
    } catch (e) {
      console.error(e);
      alert(e?.message || "블록 삭제 중 오류가 발생했습니다.");
    }
  }

  /* =========================================================================
   * 9) Events (delegation)
   * ========================================================================= */
  sectionsEl.addEventListener("click", (e) => {
    const t = e.target;

    // 9-1) 이미지 클릭 -> viewer
    const imgEl = t?.closest?.(".jsManualImg");
    if (imgEl) {
      const blockEl = imgEl.closest(".manual-block");
      const url = toStr(blockEl?.dataset?.imageUrl) || toStr(imgEl.getAttribute("src"));
      if (url) openViewer(url);
      return;
    }

    // 9-2) 섹션 소제목 수정
    const editTitleBtn = t?.closest?.(".btnEditSectionTitle");
    if (editTitleBtn) {
      const sectionEl = editTitleBtn.closest(".manual-section");
      if (sectionEl) secMgr.beginSectionTitleEdit(sectionEl);
      return;
    }

    // 9-3) 섹션 삭제
    const delSectionBtn = t?.closest?.(".btnDeleteSection");
    if (delSectionBtn) {
      const sectionId =
        delSectionBtn.getAttribute("data-section-id") ||
        delSectionBtn.closest(".manual-section")?.dataset?.sectionId;
      const sectionEl = delSectionBtn.closest(".manual-section");
      secMgr.deleteSectionById(sectionId, sectionEl);
      return;
    }

    // 9-4) 블록 추가 모달 open
    const addBtn = t?.closest?.(".btn-add-block");
    if (addBtn) {
      const sid = addBtn.getAttribute("data-section-id");
      if (isDigits(sid)) openForAdd(Number(sid));
      return;
    }

    // 9-5) 블록 수정 모달 open
    const editBtn = t?.closest?.(".btn-edit-block");
    if (editBtn) {
      const blockEl = editBtn.closest(".manual-block");
      if (blockEl) openForEdit(blockEl);
      return;
    }

    // 9-6) 블록 삭제
    const delBlockBtn = t?.closest?.(".btn-delete-block");
    if (delBlockBtn) {
      const blockId =
        delBlockBtn.getAttribute("data-block-id") ||
        delBlockBtn.closest(".manual-block")?.dataset?.blockId;
      const blockEl = delBlockBtn.closest(".manual-block");
      deleteBlockById(blockId, blockEl);
      return;
    }
  });

  /* =========================================================================
   * 10) Save (add/edit) - FormData
   * ========================================================================= */
  btnSave.addEventListener("click", async () => {
    ui.clearErr();

    const addUrl = toStr(modalEl.dataset.addUrl);
    const updateUrl = toStr(modalEl.dataset.updateUrl);
    const manualId = toStr(modalEl.dataset.manualId);

    let html = "";
    try {
      html = toStr(quillMgr.getHtml());
    } catch (e) {
      return ui.err(e?.message || "편집기 초기화에 실패했습니다.");
    }

    if (isEmptyQuillHtml(html)) return ui.err("텍스트 내용을 입력해주세요.");

    btnSave.disabled = true;
    const oldText = btnSave.textContent;
    btnSave.textContent = "저장중...";

    try {
      const fd = new FormData();

      if (state.mode === "add") {
        if (!isDigits(manualId)) throw new Error("manual_id가 올바르지 않습니다.");
        if (!isDigits(state.currentSectionId)) throw new Error("추가할 구역(section)이 지정되지 않았습니다.");

        fd.append("manual_id", String(manualId));
        fd.append("section_id", String(state.currentSectionId));
        fd.append("content", html);

        if (imgInput?.files?.[0]) fd.append("image", imgInput.files[0]);

        const data = await api.form(addUrl, fd);
        const b = data?.block;
        const sid = toStr(b?.section_id);

        const container = document.getElementById(`manualBlocks-${sid}`);
        if (!container) throw new Error(`manualBlocks-${sid} 컨테이너를 찾을 수 없습니다.`);

        const newEl = buildBlockElement(b);
        container.appendChild(newEl);
        newEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else {
        if (!state.editingBlockId) throw new Error("수정 대상이 없습니다.");

        fd.append("block_id", String(state.editingBlockId));
        fd.append("content", html);

        if (removeChk?.checked) fd.append("remove_image", "1");
        if (imgInput?.files?.[0]) fd.append("image", imgInput.files[0]);

        const data = await api.form(updateUrl, fd);
        const b = data?.block;

        const target = sectionsEl.querySelector(`.manual-block[data-block-id="${b.id}"]`);
        if (target) {
          target.dataset.imageUrl = b.image_url || "";

          const contentEl = target.querySelector(".manual-block-content");
          if (contentEl) contentEl.innerHTML = b.content || "";

          const media = target.querySelector(".manual-block-media");
          if (media) {
            media.innerHTML = b.image_url
              ? `<img src="${b.image_url}" class="manual-block-thumb jsManualImg" alt="manual image">`
              : `<div class="text-muted small py-4">이미지 없음</div>`;
          }
        }
      }

      // 저장 성공 후 모달 닫기
      safeBootstrapModalHide(modalEl);
    } catch (errObj) {
      console.error(errObj);
      ui.err(errObj?.message || "저장 중 오류가 발생했습니다.");
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = oldText;
    }
  });

  /* =========================================================================
   * 11) modal reset
   * ========================================================================= */
  modalEl.addEventListener("hidden.bs.modal", () => {
    state.mode = "add";
    state.editingBlockId = null;
    state.currentSectionId = null;

    ui.clearErr();
    resetImageUI();
    quillMgr.reset();
    if (attachInput) attachInput.value = "";
  });

  /* =========================================================================
   * 12) Section add (버튼은 secMgr가 책임)
   * ========================================================================= */
  secMgr.bindAddSectionButton({
    // ✅ 기능 변화 0: 기존 buildSectionElement 위임 wrapper 제거
    buildSectionElement: secMgr.buildSectionElement,
  });

  /* =========================================================================
   * 13) Block Sortable (reorder / move)
   * - SortableJS가 로드되어 있고, reorder URL이 있을 때만 동작
   * ========================================================================= */
  initBlockSortable({
    S,
    rootEl: sectionsEl, // .manualBlocks 들을 sectionsEl 아래에서 찾음
    bootEl,             // data-block-reorder-url / data-block-move-url 읽음
    csrfToken,
  });
})();
