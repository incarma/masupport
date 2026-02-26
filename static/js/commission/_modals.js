// django_ma/static/js/commission/_modals.js
// Commission 공용 모달(TextViewer / SupportModal)
// - deposit_home.js는 "있으면 사용", 없으면 기존 내부 구현 fallback

(() => {
  "use strict";

  const root = (window.CommissionCommon = window.CommissionCommon || {});
  const F = root.format || {};
  const dom = root.dom || {};
  const toText = F.toText || ((v) => (v === null || v === undefined ? "" : String(v)));

  function hasBS() {
    return !!(window.bootstrap && window.bootstrap.Modal);
  }

  // ------------------------------
  // TextViewer
  // ------------------------------
  const TextViewer = (() => {
    function ensureModal() {
      let modal = document.getElementById("textViewerModal");
      if (modal) return modal;

      modal = document.createElement("div");
      modal.id = "textViewerModal";
      modal.className = "modal fade";
      modal.tabIndex = -1;
      modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg">
          <div class="modal-content rounded-4">
            <div class="modal-header">
              <h6 class="modal-title fw-bold"></h6>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <pre class="mb-0 small" style="white-space:pre-wrap;word-break:break-word;"></pre>
            </div>
          </div>
        </div>`;
      document.body.appendChild(modal);
      return modal;
    }

    function open(title, text) {
      const safeTitle = title || "전체 내용";
      const safeText = (text || "").toString();

      if (!hasBS()) {
        alert(`${safeTitle}\n\n${safeText || "-"}`);
        return;
      }

      const modal = ensureModal();
      modal.querySelector(".modal-title").textContent = safeTitle;
      modal.querySelector("pre").textContent = safeText || "-";
      new bootstrap.Modal(modal).show();
    }

    function bindEllipsisClickOnce(flagKey = "__commissionEllipsisBound") {
      if (window[flagKey]) return;
      window[flagKey] = true;

      document.addEventListener("click", (e) => {
        const cell = e.target.closest(".ellipsis-cell");
        if (!cell) return;

        const full = String(cell.dataset.fullText || "").trim();
        const fallback = String(cell.textContent || "").trim();
        open("전체 내용", full || fallback || "-");
      });
    }

    return { open, bindEllipsisClickOnce };
  })();

  // ------------------------------
  // SupportModal (지원신청서 텍스트)
  // ------------------------------
  const SupportModal = (() => {
    function ensureModal() {
      let modal = document.getElementById("supportPreviewModal");
      if (modal) return modal;

      modal = document.createElement("div");
      modal.id = "supportPreviewModal";
      modal.className = "modal fade";
      modal.tabIndex = -1;
      modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
          <div class="modal-content rounded-4">
            <div class="modal-header">
              <h6 class="modal-title fw-bold">지원신청서</h6>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="닫기"></button>
            </div>
            <div class="modal-body">
              <div class="small text-muted mb-2">아래 내용을 확인 후 필요하면 복사해서 사용하세요.</div>
              <pre id="supportPreviewBody"
                   class="mb-0 small p-3 rounded-3 border"
                   style="white-space:pre-wrap;word-break:break-word;"></pre>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
              <button type="button" class="btn btn-primary btn-sm" id="supportPreviewCopyBtn">복사</button>
            </div>
          </div>
        </div>`;
      document.body.appendChild(modal);

      // copy handler (1회만)
      if (!window.__commissionSupportCopyBound) {
        window.__commissionSupportCopyBound = true;

        document.addEventListener("click", async (e) => {
          const btn = e.target.closest("#supportPreviewCopyBtn");
          if (!btn) return;

          const body = document.getElementById("supportPreviewBody");
          const t = (body?.textContent || "").trim();
          if (!t) return;

          try {
            if (navigator.clipboard?.writeText) {
              await navigator.clipboard.writeText(t);
            } else {
              const ta = document.createElement("textarea");
              ta.value = t;
              ta.style.position = "fixed";
              ta.style.left = "-9999px";
              document.body.appendChild(ta);
              ta.select();
              document.execCommand("copy");
              ta.remove();
            }
            btn.textContent = "복사됨";
            setTimeout(() => (btn.textContent = "복사"), 900);
          } catch (err) {
            console.error(err);
            alert("복사에 실패했습니다. 내용을 선택해서 수동 복사해주세요.");
          }
        });
      }

      return modal;
    }

    // ✅ 하위호환 지원
    // - deposit_home.js: SupportModal.open({ textValue }) 형태 호출
    // - 다른 페이지: SupportModal.open({ buildTextFn, target, summary, ... }) 형태 호출 가능
    function open({ textValue, buildTextFn, target, summary, suretyItems, otherItems } = {}) {
      // 1) textValue가 직접 오면 최우선 사용 (deposit_home.js 호환)
      let finalText = (textValue || "").toString().trim();

      // 2) textValue가 없고 buildTextFn이 있으면 buildTextFn 결과 사용
      if (!finalText && typeof buildTextFn === "function") {
        try {
          finalText = String(
            buildTextFn({ target, summary, suretyItems, otherItems }) ?? ""
          ).trim();
        } catch (e) {
          console.error(e);
          finalText = "";
        }
      }

      // 3) 그래도 없으면 최소 fallback 포맷
      if (!finalText) {
        finalText = [
          `가. 대상 : ${(target?.branch || "-")} ${(target?.name || "-")} FA (${(target?.id || "-")})`,
          "",
          "나. 요청사항 : ",
          "",
          "다. 채권관리",
          `   1. 채권합계 : ${(summary?.debt_total ?? "-")}원`,
          `   2. 보증보험 : ${(summary?.surety_total ?? "-")}원`,
          `   3. 기타채권 : ${(summary?.other_total ?? "-")}원`,
          "",
          "  끝.",
        ].join("\n");
      }

      if (!hasBS()) {
        alert(finalText);
        return;
      }

      const modal = ensureModal();
      const body = modal.querySelector("#supportPreviewBody");
      if (body) body.textContent = finalText || "-";
      new bootstrap.Modal(modal).show();
    }

    return { open };
  })();

  root.modals = Object.freeze({
    TextViewer,
    SupportModal,
  });
})();