/**
 * django_ma/static/js/excel_upload.js (FINAL REFACTOR)
 * -----------------------------------------------------------------------------
 * ✅ 엑셀 업로드 폼 submit을 가로채서 fetch로 업로드
 * ✅ JSON 응답을 새 페이지로 띄우지 않고 결과 모달로 표시
 * ✅ CSRF / same-origin / 중복 방지
 * ✅ 성공 시: 토스트 + (옵션) 새로고침 버튼 제공
 *
 * 의존 요소(변경 금지):
 * - form#excelUploadForm, input#excelFile
 * - modal#excelUploadModal
 * - modal#excelUploadResultModal, #excelUploadResultBody, #excelUploadReloadBtn
 * - toast#uploadToast (있으면 사용)
 */
document.addEventListener("DOMContentLoaded", () => {
  const uploadForm = document.getElementById("excelUploadForm");
  const fileInput = document.getElementById("excelFile");

  if (!uploadForm || !fileInput) return;

  const safeText = (v) => (v === null || v === undefined ? "" : String(v));
  const escapeHtml = (v) =>
    safeText(v)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const safeSameOriginUrl = (v) => {
    try {
      const u = new URL(safeText(v), window.location.origin);
      if (u.origin !== window.location.origin) return "";
      return u.pathname + u.search + u.hash;
    } catch (_) {
      return "";
    }
  };

  const showToastIfExists = () => {
    const el = document.getElementById("uploadToast");
    if (!el || !window.bootstrap?.Toast) return;
    try {
      new bootstrap.Toast(el, { delay: 2500 }).show();
    } catch (_) {}
  };

  const showResultModal = ({ titleHtml, bodyHtml, showReload }) => {
    const body = document.getElementById("excelUploadResultBody");
    const reloadBtn = document.getElementById("excelUploadReloadBtn");
    if (!body || !window.bootstrap?.Modal) return;

    body.innerHTML = `
      ${titleHtml ? `<div class="fw-bold mb-2">${titleHtml}</div>` : ""}
      <div>${bodyHtml || ""}</div>
    `;

    if (reloadBtn) {
      if (showReload) {
        reloadBtn.classList.remove("d-none");
        reloadBtn.onclick = () => location.reload();
      } else {
        reloadBtn.classList.add("d-none");
        reloadBtn.onclick = null;
      }
    }

    new bootstrap.Modal(document.getElementById("excelUploadResultModal")).show();
  };

  const hideUploadModalIfOpen = () => {
    const modalEl = document.getElementById("excelUploadModal");
    if (!modalEl || !window.bootstrap?.Modal) return;
    const inst = bootstrap.Modal.getInstance(modalEl);
    if (inst) inst.hide();
  };

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!fileInput.files.length) {
      alert("엑셀 파일을 선택해주세요.");
      return;
    }

    const fileName = fileInput.files[0]?.name || "선택한 파일";
    if (!confirm(`"${fileName}" 파일을 업로드하시겠습니까?`)) return;

    if (uploadForm.dataset.submitting === "1") return;
    uploadForm.dataset.submitting = "1";

    try {
      const formData = new FormData(uploadForm);

      const res = await fetch(uploadForm.action, {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": window.csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
      });

      // 서버가 JSON을 준다는 전제(현재 응답이 JSON이므로)
      const data = await res.json();

      // 모달 표시용 메시지 구성
      if (data.ok) {
        const msg = escapeHtml(data.message) || "✅ 업로드가 완료되었습니다.";
        const uploaded = escapeHtml(data.uploaded);
        const missing = Number(data.missing_users || 0);
         const part = escapeHtml(data.part);
        const uploadType = escapeHtml(data.upload_type);
        const uploadedDate = escapeHtml(data.uploaded_date);

        let bodyHtml = `
          <div class="mb-2 text-success fw-bold">${msg}</div>
          <div class="small">
            <div>부서: <span class="fw-semibold">${part || "-"}</span></div>
            <div>업로드 구분: <span class="fw-semibold">${uploadType || "-"}</span></div>
            <div>업로드 건수: <span class="fw-semibold">${uploaded || "-"}</span></div>
            <div>업로드 일시: <span class="fw-semibold">${uploadedDate || "-"}</span></div>
          </div>
        `;

        if (missing > 0) {
          const sample = Array.isArray(data.missing_sample) ? data.missing_sample.slice(0, 10) : [];
          bodyHtml += `
            <hr class="my-3">
            <div class="text-warning fw-bold">⚠️ 미등록 사용자 ${missing}건</div>
            ${sample.length ? `<div class="small mt-1">예시: ${sample.map(escapeHtml).join(", ")}</div>` : ""}
          `;
        }

        const failUrl = safeSameOriginUrl(data.fail_download_url);
        if (failUrl) {
          bodyHtml += `
            <div class="mt-3">
              <a class="btn btn-sm btn-outline-danger" href="${failUrl}">
                실패 엑셀 다운로드
              </a>
            </div>
          `;
        }

        hideUploadModalIfOpen();
        showToastIfExists();
        showResultModal({
          titleHtml: "업로드 결과",
          bodyHtml,
          showReload: true, // 정책: 성공 시 새로고침 버튼 제공
        });
      } else {
        const errMsg = escapeHtml(data.message) || "업로드에 실패했습니다.";
        hideUploadModalIfOpen();
        showResultModal({
          titleHtml: "❌ 업로드 실패",
          bodyHtml: `<pre class="mb-0 small">${errMsg}</pre>`,
          showReload: false,
        });
      }
    } catch (err) {
      console.error(err);
      showResultModal({
        titleHtml: "❌ 업로드 오류",
        bodyHtml: `<div class="small">업로드 중 오류가 발생했습니다. 콘솔 로그를 확인해주세요.</div>`,
        showReload: false,
      });
    } finally {
      uploadForm.dataset.submitting = "0";
      fileInput.value = "";
    }
  });
});
