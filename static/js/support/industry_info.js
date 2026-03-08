(function () {
  const root = document.getElementById("industryInfoRoot");
  if (!root || root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  const prefUrlTemplate = root.dataset.preferenceUrlTemplate || "";
  const clickUrlTemplate = root.dataset.clickUrlTemplate || "";
  const prefMap = window.supportPrefMap || {};

  /**
   * CSRF 토큰 조회
   * - 현재 프로젝트는 CSRF 쿠키 기반 fetch 패턴을 사용합니다.
   */
  function getCSRFToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  /**
   * 템플릿 URL에서 article_id 치환
   * 예: /support/api/articles/0/preference/ -> /support/api/articles/12/preference/
   */
  function buildUrl(template, articleId) {
    return template.replace("/0/", `/${articleId}/`);
  }

  /**
   * 공용 POST JSON helper
   */
  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    });

    return resp.json();
  }

  /**
   * 카드 busy 상태 토글
   * - 중복 클릭 방지
   * - 진행 중 UI 피드백
   */
  function setBusy(card, busy) {
    if (!card) return;

    card.classList.toggle("is-busy", !!busy);

    card.querySelectorAll("button").forEach((btn) => {
      btn.disabled = !!busy;
      btn.setAttribute("aria-busy", busy ? "true" : "false");
    });
  }

  /**
   * 선호도 저장 공통 처리
   * - rating
   * - bookmark
   * - hide
   */
  async function handlePreference(card, payload) {
    const articleId = card.dataset.articleId;
    setBusy(card, true);

    try {
      const json = await postJson(buildUrl(prefUrlTemplate, articleId), payload);

      if (!json.ok) {
        alert(json.message || "저장 중 오류가 발생했습니다.");
        return;
      }

      if (payload.rating) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].rating = payload.rating;
        alert(`평점 ${payload.rating}점이 저장되었습니다.`);
      } else if (payload.is_bookmarked !== undefined) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].is_bookmarked = payload.is_bookmarked;
        alert(payload.is_bookmarked ? "북마크했습니다." : "북마크를 해제했습니다.");
      } else if (payload.is_hidden !== undefined) {
        prefMap[articleId] = prefMap[articleId] || {};
        prefMap[articleId].is_hidden = payload.is_hidden;

        if (payload.is_hidden) {
          card.remove();
        }
        alert(payload.is_hidden ? "관심없음 처리되었습니다." : "숨김 해제되었습니다.");
      }
    } catch (err) {
      alert("저장 중 오류가 발생했습니다.");
    } finally {
      setBusy(card, false);
    }
  }

  /**
   * 이벤트 위임 처리
   * - 평점
   * - 북마크
   * - 관심없음
   * - 원문보기 클릭기록
   */
  root.addEventListener("click", async (e) => {
    const card = e.target.closest(".support-article-card");
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
        // 클릭 기록 실패는 사용자 이동을 막지 않습니다.
      }
    }
  });
})();