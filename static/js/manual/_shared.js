// django_ma/static/js/manual/_shared.js
// -----------------------------------------------------------------------------
// Manual JS Shared Utilities (FINAL)
// - 공통 파서/CSRF/Fetch/버튼 로딩/JSON 안전 파싱을 한 곳에서 제공
// - "기존 기능에 영향 없이" 단순 추출/정리만 수행
// -----------------------------------------------------------------------------

(() => {
  // 이미 로드되어 있으면 중복 정의 방지
  if (window.ManualShared) return;

  const DEBUG = false;
  const log = (...a) => DEBUG && console.log("[ManualShared]", ...a);

  const toStr = (v) => String(v ?? "").trim();
  const isDigits = (v) => /^\d+$/.test(String(v ?? ""));

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  function getCSRFTokenFromForm(formEl) {
    /*
     * ✅ CSRF 조회 SSOT 보강
     * 기능 변화 0:
     * - 기존 window.csrfToken 우선 정책 유지
     * - 호출부에서 넘기는 csrf form hidden input fallback 추가
     * - 마지막으로 document 전체 hidden input fallback
     */
    const fromWindow = toStr(window.csrfToken);
    if (fromWindow) return fromWindow;

    const fromForm = toStr(formEl?.querySelector?.("[name=csrfmiddlewaretoken]")?.value);
    return fromForm || toStr(document.querySelector("[name=csrfmiddlewaretoken]")?.value);
  }

  function setBtnLoading(btn, isLoading, loadingText, defaultText) {
    if (!btn) return;

    if (isLoading) {
      if (btn.dataset.oldText == null) btn.dataset.oldText = btn.textContent || (defaultText || "");
      btn.disabled = true;
      if (loadingText) btn.textContent = loadingText;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.oldText || (defaultText || btn.textContent || "");
      delete btn.dataset.oldText;
    }
  }

  function showErrorBox(errBox, msg, fallbackAlert = true) {
    const m = toStr(msg) || "오류가 발생했습니다.";
    if (!errBox) {
      if (fallbackAlert) window.alert(m);
      return;
    }
    errBox.textContent = m;
    errBox.classList.remove("d-none");
  }

  function clearErrorBox(errBox) {
    if (!errBox) return;
    errBox.textContent = "";
    errBox.classList.add("d-none");
  }

  async function safeReadJson(res) {
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!ct.includes("application/json")) {
      const text = await res.text().catch(() => "");
      return { __non_json__: true, __text__: text };
    }
    return await res.json().catch(() => ({}));
  }

  // JSON 전송
  async function postJson(url, bodyObj, csrfToken) {
    const u = toStr(url);
    const csrf = toStr(csrfToken);

    if (!u) throw new Error("요청 URL이 비어있습니다.");
    if (!csrf) throw new Error("CSRF 토큰이 없습니다.");

    const res = await fetch(u, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(bodyObj || {}),
    });

    const data = await safeReadJson(res);
    if (data?.__non_json__) throw new Error(`요청 실패 (HTTP ${res.status})`);
    if (!res.ok || !data?.ok) throw new Error(data?.message || `요청 실패 (HTTP ${res.status})`);
    return data;
  }

  // FormData 전송 (파일/이미지 포함)
  async function postForm(url, formData, csrfToken) {
    const u = toStr(url);
    const csrf = toStr(csrfToken);

    if (!u) throw new Error("요청 URL이 비어있습니다.");
    if (!csrf) throw new Error("CSRF 토큰이 없습니다.");

    const res = await fetch(u, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: formData,
    });

    const data = await safeReadJson(res);
    if (data?.__non_json__) throw new Error(`요청 실패 (HTTP ${res.status})`);
    if (!res.ok || !data?.ok) throw new Error(data?.message || `요청 실패 (HTTP ${res.status})`);
    return data;
  }

  function formatBytes(bytes) {
    const n = Number(bytes || 0);
    if (!n) return "";
    const units = ["B", "KB", "MB", "GB"];
    let x = n;
    let idx = 0;
    while (x >= 1024 && idx < units.length - 1) {
      x /= 1024;
      idx += 1;
    }
    const v = idx === 0 ? String(Math.round(x)) : String(Math.round(x * 10) / 10);
    return `${v}${units[idx]}`;
  }

  window.ManualShared = {
    log,
    ready,
    toStr,
    isDigits,
    getCSRFTokenFromForm,
    setBtnLoading,
    showErrorBox,
    clearErrorBox,
    safeReadJson,
    postJson,
    postForm,
    formatBytes,
  };
})();
