/**
 * django_ma/static/js/partner/pdf_processing.js
 * ------------------------------------------------------------
 * 목적:
 * - partner/pdf_processing.html의 inline polling script 제거.
 * - PDF 생성 상태를 주기적으로 확인하고 완료 시 다운로드 URL로 이동한다.
 *
 * DOM 계약:
 * - #pdfProcessingRoot
 *   - data-task-id
 *   - data-status-url-template="/manual/status/{taskId}/"
 *   - data-download-url-template="/manual/download/{taskId}/"
 *
 * 보안/안정성:
 * - same-origin credentials 사용
 * - JSON 응답 content-type 확인
 * - 일시적 오류 발생 시 3초 후 재시도
 * - FAILURE는 사용자 alert 후 polling 중단
 */
document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("pdfProcessingRoot");
  if (!root) return;

  const taskId = (root.dataset.taskId || "").trim();
  const statusUrlTemplate = root.dataset.statusUrlTemplate || "/manual/status/{taskId}/";
  const downloadUrlTemplate = root.dataset.downloadUrlTemplate || "/manual/download/{taskId}/";

  if (!taskId) return;

  const buildUrl = function (template) {
    return template.replace("{taskId}", encodeURIComponent(taskId));
  };

  async function checkStatus() {
    try {
      const response = await fetch(buildUrl(statusUrlTemplate), {
        credentials: "same-origin",
        cache: "no-store",
      });

      const contentType = String(response.headers.get("content-type") || "").toLowerCase();
      if (!response.ok || !contentType.includes("application/json")) {
        throw new Error("Invalid status response");
      }

      const data = await response.json();

      if (data.status === "SUCCESS" && data.pdf_ready) {
        window.location.href = buildUrl(downloadUrlTemplate);
        return;
      }

      if (data.status === "FAILURE") {
        window.alert("PDF 생성에 실패했습니다.");
        return;
      }

      window.setTimeout(checkStatus, 2000);
    } catch (err) {
      window.setTimeout(checkStatus, 3000);
    }
  }

  checkStatus();
});