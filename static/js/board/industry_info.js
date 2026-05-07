  // django_ma/static/js/board/industry_info.js

  (function () {
    "use strict";

    const root = document.getElementById("industryInfoRoot");
    if (!root || root.dataset.inited === "1") return;
    root.dataset.inited = "1";

    const prefUrlTemplate = root.dataset.preferenceUrlTemplate || "";
    const clickUrlTemplate = root.dataset.clickUrlTemplate || "";
    const prefMap = window.industryPrefMap || {};

    function buildUrl(template, articleId) {
      return template.replace("/0/", `/${articleId}/`);
    }

    function isSafeExternalHref(href) {
      try {
        const url = new URL(href, window.location.origin);
        return url.protocol === "http:" || url.protocol === "https:";
      } catch (_) {
        return false;
      }
    }

    async function postJson(url, payload) {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": window.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload || {}),
      });
      const json = await resp.json().catch(() => ({
        ok: false,
        message: "서버 응답을 읽지 못했습니다.",
      }));
      if (!resp.ok && !json.message) {
        json.message = `요청 처리 실패 (${resp.status})`;
      }
      return json;
    }

    function getAllCardsByArticleId(articleId) {
      return Array.from(
        root.querySelectorAll(`.industry-article-card[data-article-id="${articleId}"]`)
      );
    }

    function setBusy(card, busy) {
      if (!card) return;
      card.classList.toggle("is-busy", !!busy);
      card.querySelectorAll("button").forEach((btn) => {
        btn.disabled = !!busy;
        btn.setAttribute("aria-busy", busy ? "true" : "false");
      });
    }

    function syncRatingUI(articleId, rating) {
      getAllCardsByArticleId(articleId).forEach((card) => {
        card.querySelectorAll(".js-rate-btn").forEach((btn) => {
          btn.classList.toggle("active", Number(btn.dataset.rating) === rating);
        });
      });
    }

    function syncBookmarkUI(articleId, isBookmarked) {
      getAllCardsByArticleId(articleId).forEach((card) => {
        const btn = card.querySelector(".js-bookmark-btn");
        if (btn) btn.classList.toggle("active", isBookmarked);
      });
    }

    function removeAllCardsByArticleId(articleId) {
      getAllCardsByArticleId(articleId).forEach((card) => card.remove());

      if (root.dataset.bookmarkedOnly === "1") {
        const remaining = root.querySelectorAll(".industry-article-card");
        if (!remaining.length) {
          const emptyEl = document.getElementById("industryEmptyState");
          if (emptyEl) emptyEl.style.display = "";
        }
      }
    }

    async function handlePreference(card, payload) {
      const articleId = card.dataset.articleId;
      const allCards = getAllCardsByArticleId(articleId);
      allCards.forEach((c) => setBusy(c, true));

      try {
        const json = await postJson(buildUrl(prefUrlTemplate, articleId), payload);

        if (!json.ok) {
          alert(json.message || "저장 중 오류가 발생했습니다.");
          return;
        }

        if (payload.rating !== undefined) {
          prefMap[articleId] = prefMap[articleId] || {};
          prefMap[articleId].rating = payload.rating;
          syncRatingUI(articleId, payload.rating);
          alert(`평점 ${payload.rating}점이 저장되었습니다.`);

        } else if (payload.is_bookmarked !== undefined) {
          prefMap[articleId] = prefMap[articleId] || {};
          prefMap[articleId].is_bookmarked = payload.is_bookmarked;
          syncBookmarkUI(articleId, payload.is_bookmarked);

          if (!payload.is_bookmarked && root.dataset.bookmarkedOnly === "1") {
            removeAllCardsByArticleId(articleId);
          }
          alert(payload.is_bookmarked ? "북마크했습니다." : "북마크를 해제했습니다.");

        } else if (payload.is_hidden !== undefined) {
          prefMap[articleId] = prefMap[articleId] || {};
          prefMap[articleId].is_hidden = payload.is_hidden;

          if (payload.is_hidden) {
            removeAllCardsByArticleId(articleId);
          }
          alert(payload.is_hidden ? "관심없음 처리되었습니다." : "숨김 해제되었습니다.");
        }

      } catch (err) {
        alert("저장 중 오류가 발생했습니다.");
      } finally {
        getAllCardsByArticleId(articleId).forEach((c) => setBusy(c, false));
      }
    }

    // =========================================================
    // per_page 드랍다운 → URL 이동
    // =========================================================
    root.addEventListener("change", (e) => {
      const select = e.target.closest(".industry-perpage-select");
      if (!select) return;

      const url = new URL(window.location.href);
      url.searchParams.set("per_page", select.value);
      url.searchParams.delete("page"); // per_page 변경 시 1페이지로 초기화
      window.location.href = url.toString();
    });

    // =========================================================
    // 이벤트 위임 (click)
    // =========================================================
    root.addEventListener("click", async (e) => {
      const card = e.target.closest(".industry-article-card");
      if (!card) return;

      const rateBtn = e.target.closest(".js-rate-btn");
      if (rateBtn) {
        return handlePreference(card, { rating: Number(rateBtn.dataset.rating) });
      }

      const bookmarkBtn = e.target.closest(".js-bookmark-btn");
      if (bookmarkBtn) {
        const articleId = card.dataset.articleId;
        const current = !!(prefMap[articleId] && prefMap[articleId].is_bookmarked);
        return handlePreference(card, { is_bookmarked: !current });
      }

      const hideBtn = e.target.closest(".js-hide-btn");
      if (hideBtn) {
        return handlePreference(card, { is_hidden: true });
      }

      const originLink = e.target.closest(".js-origin-link");
      if (originLink) {
        if (!isSafeExternalHref(originLink.getAttribute("href") || "")) {
          e.preventDefault();
          alert("안전하지 않은 외부 링크입니다.");
          return;
        }
        try {
          await postJson(buildUrl(clickUrlTemplate, card.dataset.articleId), {});
        } catch (err) {
          // 클릭 기록 실패는 사용자 이동을 막지 않음
        }
      }
    });
  })();