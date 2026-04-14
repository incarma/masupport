// django_ma/static/js/board/industry_info.js
// =========================================================
// Board Industry Info Page JS
// - support 업계정보 UI를 board에서 동일 동작으로 제공
// - dataset 기반 URL 템플릿 사용
// - CSRF cookie 기반 fetch
// - 이벤트 위임 기반 rating / bookmark / hide / click 처리
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
  // - 운영 환경에서 csrftoken이 여러 개 보이는 경우를 고려해 마지막 값을 우선 사용
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

  // =========================================================
  // URL Builder
  // - 템플릿 URL의 /0/ 부분을 실제 article id로 치환
  // =========================================================
  function buildUrl(template, articleId) {
    return template.replace("/0/", `/${articleId}/`);
  }

  // =========================================================
  // 공용 POST JSON helper
  // =========================================================
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
  // Busy 상태 토글
  // - 카드 전체 중복 클릭 방지
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
  // 선호도 저장 공통 처리
  // - rating / bookmark / hide
  // =========================================================
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
        // 클릭 기록 실패는 사용자 이동을 막지 않습니다.
      }
    }
  });
})();