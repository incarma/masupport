// django_ma/static/js/board/industry_info.js
// =========================================================
// Board Industry Info Page JS
// - dataset 기반 URL 템플릿 사용
// - CSRF cookie 기반 fetch
// - 이벤트 위임 기반 rating / bookmark / hide / click 처리
// ✅ 동일 article_id 카드 전체 동기화
//    - 관심없음: 같은 article_id 카드 모두 제거
//    - 별점/북마크: 같은 article_id 카드 모두 UI 갱신
// =========================================================

(function () {
  "use strict";

  const root = document.getElementById("industryInfoRoot");
  if (!root || root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  const prefUrlTemplate = root.dataset.preferenceUrlTemplate || "";
  const clickUrlTemplate = root.dataset.clickUrlTemplate || "";
  const prefMap = window.industryPrefMap || {};

  // =========================================================
  // CSRF
  // =========================================================
  function getCSRFToken() {
    const raw = document.cookie || "";
    if (!raw) return "";
    const parts = raw.split(";").map((v) => v.trim()).filter(Boolean);
    const values = [];
    for (const part of parts) {
      if (!part.startsWith("csrftoken=")) continue;
      values.push(part.slice("csrftoken=".length));
    }
    if (!values.length) return "";
    return decodeURIComponent(values[values.length - 1]);
  }

  function buildUrl(template, articleId) {
    return template.replace("/0/", `/${articleId}/`);
  }

  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    });
    return resp.json();
  }

  // =========================================================
  // ✅ 동일 article_id 카드 전체 조회
  // - 추천/최신 양쪽 섹션에 같은 기사가 있을 수 있으므로
  //   querySelectorAll로 전체를 배열로 반환
  // =========================================================
  function getAllCardsByArticleId(articleId) {
    return Array.from(
      root.querySelectorAll(`.industry-article-card[data-article-id="${articleId}"]`)
    );
  }

  // =========================================================
  // Busy 상태 토글 (단일 카드)
  // =========================================================
  function setBusy(card, busy) {
    if (!card) return;
    card.classList.toggle("is-busy", !!busy);
    card.querySelectorAll("button").forEach((btn) => {
      btn.disabled = !!busy;
      btn.setAttribute("aria-busy", busy ? "true" : "false");
    });
  }

  // =========================================================
  // ✅ 별점 UI 갱신 — 동일 article_id 카드 전체 적용
  // - .js-rate-btn 의 active 클래스를 서버 응답 기준으로 동기화
  // =========================================================
  function syncRatingUI(articleId, rating) {
    getAllCardsByArticleId(articleId).forEach((card) => {
      card.querySelectorAll(".js-rate-btn").forEach((btn) => {
        const btnRating = Number(btn.dataset.rating);
        btn.classList.toggle("active", btnRating === rating);
      });
    });
  }

  // =========================================================
  // ✅ 북마크 UI 갱신 — 동일 article_id 카드 전체 적용
  // - .js-bookmark-btn 의 active 클래스 동기화
  // =========================================================
  function syncBookmarkUI(articleId, isBookmarked) {
    getAllCardsByArticleId(articleId).forEach((card) => {
      const btn = card.querySelector(".js-bookmark-btn");
      if (btn) btn.classList.toggle("active", isBookmarked);
    });
  }

  // =========================================================
  // ✅ 관심없음 — 동일 article_id 카드 전체 제거
  // 북마크 페이지에서 북마크 해제 시에도 전체 제거
  // =========================================================
  function removeAllCardsByArticleId(articleId) {
    getAllCardsByArticleId(articleId).forEach((card) => card.remove());

    // 북마크 페이지: 남은 카드 없으면 빈 상태 UI 노출
    if (root.dataset.bookmarkedOnly === "1") {
      const remaining = root.querySelectorAll(".industry-article-card");
      if (!remaining.length) {
        const emptyEl = document.getElementById("industryEmptyState");
        if (emptyEl) emptyEl.style.display = "";
      }
    }
  }

  // =========================================================
  // 선호도 저장 공통 처리
  // =========================================================
  async function handlePreference(card, payload) {
    const articleId = card.dataset.articleId;

    // ✅ 요청 중 동일 article_id 카드 전체 busy 처리
    const allCards = getAllCardsByArticleId(articleId);
    allCards.forEach((c) => setBusy(c, true));

    try {
      const json = await postJson(buildUrl(prefUrlTemplate, articleId), payload);

      if (!json.ok) {
        alert(json.message || "저장 중 오류가 발생했습니다.");
        return;
      }

      // ── 별점 ──────────────────────────────────────────────
      if (payload.rating !== undefined) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].rating = payload.rating;
        syncRatingUI(articleId, payload.rating);
        alert(`평점 ${payload.rating}점이 저장되었습니다.`);

      // ── 북마크 ────────────────────────────────────────────
      } else if (payload.is_bookmarked !== undefined) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].is_bookmarked = payload.is_bookmarked;
        syncBookmarkUI(articleId, payload.is_bookmarked);

        // 북마크 페이지에서 해제 → 전체 카드 제거
        if (!payload.is_bookmarked && root.dataset.bookmarkedOnly === "1") {
          removeAllCardsByArticleId(articleId);
        }
        alert(payload.is_bookmarked ? "북마크했습니다." : "북마크를 해제했습니다.");

      // ── 관심없음 ──────────────────────────────────────────
      } else if (payload.is_hidden !== undefined) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].is_hidden = payload.is_hidden;

        if (payload.is_hidden) {
          // ✅ 추천/최신 양쪽 동일 article_id 카드 모두 제거
          removeAllCardsByArticleId(articleId);
        }
        alert(payload.is_hidden ? "관심없음 처리되었습니다." : "숨김 해제되었습니다.");
      }

    } catch (err) {
      alert("저장 중 오류가 발생했습니다.");
    } finally {
      // ✅ busy 해제: 카드가 이미 제거된 경우 querySelectorAll이 빈 배열 반환하므로 안전
      getAllCardsByArticleId(articleId).forEach((c) => setBusy(c, false));
    }
  }

  // =========================================================
  // 이벤트 위임
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
      try {
        await postJson(buildUrl(clickUrlTemplate, card.dataset.articleId), {});
      } catch (err) {
        // 클릭 기록 실패는 사용자 이동을 막지 않음
      }
    }
  });
})();