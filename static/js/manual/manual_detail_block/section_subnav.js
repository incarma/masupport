// django_ma/static/js/manual/manual_detail_block/section_subnav.js
// -----------------------------------------------------------------------------
// Section actions + Subnav sync (Minimal split)
// - 소제목 수정
// - 섹션(카드) 삭제/추가
// - Subnav 링크 즉시 추가/삭제/재정렬 (DOM 기준 rebuild)
// -----------------------------------------------------------------------------

export function createSectionSubnavManager({
  S,
  api,
  sectionsEl,
  btnAddSection,
  sectionTitleUpdateUrl,
  sectionDeleteUrl,
}) {
  const { toStr, isDigits } = S;

  function getSubnavEl() {
    return document.querySelector("#manualSubnav .subnav-links");
  }

  function rebuildSubnavFromDOM() {
    const subnav = getSubnavEl();
    if (!subnav) return;

    const frag = document.createDocumentFragment();

    const sections = Array.from(sectionsEl.querySelectorAll(".manual-section"));
    sections.forEach((secEl) => {
      const sid = toStr(secEl.dataset.sectionId);
      if (!isDigits(sid)) return;

      const titleTextEl = secEl.querySelector('[data-role="secTitleText"]');
      const titleText = toStr(titleTextEl?.textContent || "").trim();

      const a = document.createElement("a");
      a.href = `#sec-${sid}`;
      a.className = "jsSubnavLink";
      a.dataset.target = `sec-${sid}`;
      a.textContent = titleText || "(소제목 없음)";

      frag.appendChild(a);
    });

    subnav.innerHTML = "";
    subnav.appendChild(frag);

    // 기존 manual_detail_subnav.js는 초기 로드시만 이벤트를 붙임.
    // 따라서 rebuild 이후에는 클릭/active 동작이 끊길 수 있음.
    // 해결: subnav.js쪽에 "재바인딩 가능한 전역 훅"을 하나 제공하거나,
    //       가장 간단하게는 이벤트를 위임으로 붙이는 방식으로 바꾸는 게 최선.
    //       (현재는 기존 파일을 유지해야 하므로, 여기서는 커스텀 이벤트를 발행)
    document.dispatchEvent(new CustomEvent("manual:subnavRebuilt"));
  }

  /* =========================================================================
   * Builders
   * ========================================================================= */
  function buildSectionElement(sectionId, titleText = "") {
    const sec = document.createElement("div");
    sec.className = "card p-4 mb-3 manual-section";
    sec.id = `sec-${sectionId}`;
    sec.dataset.sectionId = sectionId;

    const safeTitle = toStr(titleText);
    const titleHtml = safeTitle ? safeTitle : "(소제목 없음)";
    const titleClass = safeTitle ? "" : "empty";

    sec.innerHTML = `
      <div class="sec-card-actions">
        <button type="button"
                class="btn btn-sm btn-outline-secondary jsSectionDragHandle"
                title="드래그로 카드 순서 변경"
                aria-label="카드 순서 변경">↕ 이동</button>
        <button type="button" class="btn btn-sm btn-danger btnDeleteSection"
                data-section-id="${sectionId}">카드 삭제</button>
      </div>

      <div class="sec-title-row">
        <h5 class="sec-title ${titleClass}" data-role="secTitleText">${titleHtml}</h5>
        <div class="sec-title-actions">
          <button type="button" class="btn btn-sm btn-outline-secondary btnEditSectionTitle">소제목 수정</button>
        </div>
      </div>

      <div class="manualBlocks" id="manualBlocks-${sectionId}"></div>

      <div class="d-flex justify-content-end mt-2">
        <button type="button"
                class="btn btn-sm btn-primary btn-add-block"
                data-bs-toggle="modal"
                data-bs-target="#manualBlockModal"
                data-section-id="${sectionId}">+내용추가</button>
      </div>
    `;
    return sec;
  }

  /* =========================================================================
   * Title edit
   * ========================================================================= */
  function beginSectionTitleEdit(sectionEl) {
    const sid = sectionEl?.dataset?.sectionId;
    if (!isDigits(sid)) return;

    if (!sectionTitleUpdateUrl) {
      alert("섹션 소제목 업데이트 URL이 없습니다. (manualDetailBoot 확인)");
      return;
    }

    if (sectionEl.dataset.titleEditing === "1") return;
    sectionEl.dataset.titleEditing = "1";

    const titleTextEl = sectionEl.querySelector('[data-role="secTitleText"]');
    if (!titleTextEl) return;

    const editBtn = sectionEl.querySelector(".btnEditSectionTitle");
    const prevEditBtnDisplay = editBtn?.style?.display ?? "";
    if (editBtn) editBtn.style.display = "none";

    const currentTextRaw = toStr(titleTextEl.textContent);
    const currentValue = currentTextRaw === "(소제목 없음)" ? "" : currentTextRaw;

    const wrap = document.createElement("div");
    wrap.className = "sec-title-edit-wrap";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control form-control-sm sec-title-edit";
    input.maxLength = 120;
    input.placeholder = "소제목 입력 (최대 120자)";
    input.value = currentValue;

    const btns = document.createElement("div");
    btns.className = "sec-title-btns";

    const btnOk = document.createElement("button");
    btnOk.type = "button";
    btnOk.className = "btn btn-sm btn-primary";
    btnOk.textContent = "저장";

    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-sm btn-outline-secondary";
    btnCancel.textContent = "취소";

    btns.appendChild(btnOk);
    btns.appendChild(btnCancel);

    wrap.appendChild(input);
    wrap.appendChild(btns);

    titleTextEl.style.display = "none";
    titleTextEl.insertAdjacentElement("afterend", wrap);

    const cleanup = () => {
      wrap.remove();
      titleTextEl.style.display = "";
      sectionEl.dataset.titleEditing = "0";
      if (editBtn) editBtn.style.display = prevEditBtnDisplay;
    };

    const applyNewTitle = (newValue) => {
      const v = toStr(newValue);
      if (v) {
        titleTextEl.textContent = v;
        titleTextEl.classList.remove("empty");
      } else {
        titleTextEl.textContent = "(소제목 없음)";
        titleTextEl.classList.add("empty");
      }
      rebuildSubnavFromDOM(); // ✅ 소제목 변경 즉시 Subnav 반영
    };

    const save = async () => {
      const newValue = toStr(input.value);

      btnOk.disabled = true;
      btnCancel.disabled = true;
      input.disabled = true;

      try {
        const data = await api.json(sectionTitleUpdateUrl, {
          section_id: Number(sid),
          title: newValue,
        });
        applyNewTitle(data?.section?.title ?? newValue);
        cleanup();
      } catch (e) {
        console.error(e);
        alert(e?.message || "소제목 저장 중 오류가 발생했습니다.");
        btnOk.disabled = false;
        btnCancel.disabled = false;
        input.disabled = false;
        input.focus();
      }
    };

    btnOk.addEventListener("click", save);
    btnCancel.addEventListener("click", cleanup);

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); save(); }
      if (e.key === "Escape") { e.preventDefault(); cleanup(); }
    });

    setTimeout(() => { input.focus(); input.select(); }, 0);
  }

  /* =========================================================================
   * Delete section
   * ========================================================================= */
  async function deleteSectionById(sectionId, sectionEl) {
    if (!sectionDeleteUrl) return alert("섹션 삭제 URL이 없습니다. (manualDetailBoot 확인)");
    if (!isDigits(sectionId)) return alert("section_id가 올바르지 않습니다.");
    if (!confirm("이 카드를 삭제할까요?\n(카드 안의 내용도 함께 삭제됩니다.)")) return;

    try {
      const data = await api.json(sectionDeleteUrl, { section_id: Number(sectionId) });

      sectionEl?.remove();
      rebuildSubnavFromDOM(); // ✅ 삭제 즉시 Subnav 반영

      // 마지막 섹션 삭제 시 서버가 기본 섹션 생성해서 new_section 반환
      if (data?.new_section?.id && isDigits(data.new_section.id)) {
        const newSec = buildSectionElement(Number(data.new_section.id), data.new_section.title || "");
        sectionsEl.appendChild(newSec);
        rebuildSubnavFromDOM(); // ✅ 기본 섹션 생성 반영
        newSec.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    } catch (e) {
      console.error(e);
      alert(e?.message || "카드 삭제 중 오류가 발생했습니다.");
    }
  }

  /* =========================================================================
   * Add section button binding
   * ========================================================================= */
  function bindAddSectionButton({ buildSectionElement }) {
    btnAddSection?.addEventListener("click", async () => {
      const manualId = toStr(
        btnAddSection.dataset.manualId ||
        sectionsEl?.dataset?.manualId ||
        ""
      );
      const url = toStr(
        btnAddSection.dataset.sectionAddUrl ||
        sectionsEl?.dataset?.sectionAddUrl ||
        ""
      );

      if (!isDigits(manualId)) return alert("manual_id가 올바르지 않습니다.");
      if (!url) return alert("section_add_url이 없습니다. (data-section-add-url 확인)");

      btnAddSection.disabled = true;
      const oldText = btnAddSection.textContent;
      btnAddSection.textContent = "추가중...";

      try {
        const data = await api.json(url, { manual_id: Number(manualId) });
        const sid = data?.section?.id;
        if (!isDigits(sid)) throw new Error("section id가 응답에 없습니다.");

        const newSectionEl = buildSectionElement(Number(sid), "");
        sectionsEl.appendChild(newSectionEl);

        rebuildSubnavFromDOM(); // ✅ 추가 즉시 Subnav 반영
        newSectionEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (err) {
        console.error(err);
        alert(err?.message || "구역 추가 중 오류가 발생했습니다.");
      } finally {
        btnAddSection.disabled = false;
        btnAddSection.textContent = oldText;
      }
    });
  }

  return {
    buildSectionElement,
    beginSectionTitleEdit,
    deleteSectionById,
    bindAddSectionButton,
    rebuildSubnavFromDOM,
  };
}
