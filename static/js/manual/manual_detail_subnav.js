// django_ma/static/js/manual/manual_detail_subnav.js
// -----------------------------------------------------------------------------
// Manual Detail Subnav (FINAL - Rebuild-safe)
// - Subnav 링크는 "섹션 카드 DOM"을 기준으로 동기화(rebuild)
// - 구역 추가/삭제/제목 변경 시 즉시 반영을 위해 window.ManualDetailSubnav API 제공
// - 클릭: 이벤트 위임(delegation)으로 동적 링크에도 자동 대응
// - IntersectionObserver: rebuild 시 매번 안전하게 재구성 (미지원 시 graceful fallback)
// -----------------------------------------------------------------------------


(() => {
  const subnavEl = document.getElementById("manualSubnav");
  const sectionsRoot = document.getElementById("manualSections");
  if (!subnavEl || !sectionsRoot) return;
  if (subnavEl.dataset.inited === "1") return;
  subnavEl.dataset.inited = "1";

  const linksWrap = subnavEl.querySelector(".subnav-links");
  if (!linksWrap) return;

  // base.html navbar 높이(대략). 프로젝트에서 값이 달라지면 여기만 수정하면 됨.
  const MAIN_NAV_H = 70;

  // IntersectionObserver instance (rebuild 시 disconnect 후 재생성)
  let io = null;

  // rebuild debounce (연속 호출 방지)
  let rebuildRAF = 0;

  // CSS.escape fallback
  const esc = (v) => {
    const s = String(v || "");
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(s);
    // 최소한의 fallback: 쿼리셀렉터 깨지는 문자 제거
    return s.replace(/["\\#.;?+*~':!^$()[\]=>|/@]/g, "\\$&");
  };

  function getOffsetTop() {
    const subnavH = subnavEl.getBoundingClientRect().height || 0;
    return MAIN_NAV_H + subnavH + 10;
  }

  function normalizeTitleText(raw) {
    const t = (raw || "").trim();
    return t ? t : "(소제목 없음)";
  }

  function scrollToTargetId(id) {
    const target = document.getElementById(id);
    if (!target) return;

    const y = window.scrollY + target.getBoundingClientRect().top - getOffsetTop();
    window.scrollTo({ top: y, behavior: "smooth" });
  }

  /* =========================================================================
   * 1) Click: delegation (동적 링크 즉시 대응)
   * ========================================================================= */
  linksWrap.addEventListener("click", (e) => {
    const a = e.target?.closest?.("a.jsSubnavLink");
    if (!a) return;

    const id = a.dataset.target;
    if (!id) return;

    e.preventDefault();
    scrollToTargetId(id);
  });

  /* =========================================================================
   * 2) Active helpers
   * ========================================================================= */
  function clearActive() {
    linksWrap.querySelectorAll("a.jsSubnavLink.active").forEach((a) => a.classList.remove("active"));
  }

  function setActive(id) {
    if (!id) return;
    clearActive();
    const a = linksWrap.querySelector(`a.jsSubnavLink[data-target="${esc(id)}"]`);
    if (a) a.classList.add("active");
  }

  function rebuildObserver() {
    // IntersectionObserver 미지원이면 active 자동처리만 생략
    if (typeof window.IntersectionObserver === "undefined") return;

    // 기존 observer 정리
    if (io) {
      try { io.disconnect(); } catch (_) {}
      io = null;
    }

    const links = Array.from(linksWrap.querySelectorAll("a.jsSubnavLink"));
    const sections = links
      .map((a) => document.getElementById(a.dataset.target))
      .filter(Boolean);

    if (!sections.length) return;

    io = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((en) => en.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible.length) setActive(visible[0].target.id);
      },
      {
        root: null,
        rootMargin: `-${getOffsetTop()}px 0px -70% 0px`,
        threshold: [0.1, 0.2, 0.3],
      }
    );

    sections.forEach((sec) => io.observe(sec));
    setActive(sections[0]?.id);
  }

  /* =========================================================================
   * 3) Subnav link builders
   * ========================================================================= */
  function buildLink(sectionId, titleText) {
    const a = document.createElement("a");
    a.className = "jsSubnavLink";
    a.dataset.target = `sec-${sectionId}`;
    a.href = `#sec-${sectionId}`;
    a.textContent = normalizeTitleText(titleText);
    return a;
  }

  function getSectionCards() {
    return Array.from(sectionsRoot.querySelectorAll(".manual-section"));
  }

  function getSectionId(sectionEl) {
    return (sectionEl?.dataset?.sectionId || "").trim();
  }

  function getSectionTitleFromCard(sectionEl) {
    const t = sectionEl?.querySelector?.('[data-role="secTitleText"]')?.textContent || "";
    return normalizeTitleText(t);
  }

  /* =========================================================================
   * 4) Public API: rebuild / updateLinkText / removeLink
   * ========================================================================= */
  function rebuildNow() {
    const cards = getSectionCards();

    const frag = document.createDocumentFragment();

    cards.forEach((secEl) => {
      const sid = getSectionId(secEl);
      if (!sid) return;

      // 섹션 카드 id 보정(누락 방어)
      const targetId = `sec-${sid}`;
      if (!secEl.id) secEl.id = targetId;

      const titleText = getSectionTitleFromCard(secEl);
      frag.appendChild(buildLink(sid, titleText));
    });

    // ✅ 확실한 재정렬: 통째로 교체
    linksWrap.innerHTML = "";
    linksWrap.appendChild(frag);

    rebuildObserver();
  }

  function rebuild() {
    // 연속 호출 시 1프레임으로 묶기
    if (rebuildRAF) cancelAnimationFrame(rebuildRAF);
    rebuildRAF = requestAnimationFrame(() => {
      rebuildRAF = 0;
      rebuildNow();
    });
  }

  function updateLinkText(sectionId, newTitleText) {
    const id = `sec-${sectionId}`;
    const a = linksWrap.querySelector(`a.jsSubnavLink[data-target="${esc(id)}"]`);
    if (!a) return rebuild();
    a.textContent = normalizeTitleText(newTitleText);
  }

  function removeLink(sectionId) {
    const id = `sec-${sectionId}`;
    const a = linksWrap.querySelector(`a.jsSubnavLink[data-target="${esc(id)}"]`);
    if (a) a.remove();
    rebuildObserver();
  }

  // 외부(JS)에서 호출할 수 있게 노출
  window.ManualDetailSubnav = {
    rebuild,
    rebuildNow, // 디버그/테스트용(원하면 제거 가능)
    updateLinkText,
    removeLink,
  };

  /* =========================================================================
   * 5) External hooks
   * ========================================================================= */
  // section_subnav.js에서 dispatch하는 이벤트를 받아도 동작하게
  document.addEventListener("manual:subnavRebuilt", () => rebuild());

  /* =========================================================================
   * 6) Optional: Go top button
   * ========================================================================= */
  const btnTop = document.getElementById("btnManualGoTop");
  btnTop?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));

  // 최초 1회: 서버 렌더 기반을 DOM 기준으로 정규화
  rebuildNow();
})();
