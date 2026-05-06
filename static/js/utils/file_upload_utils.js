/**
 * django_ma/static/js/utils/file_upload_utils.js (FINAL REFACTOR)
 * -----------------------------------------------------------------------------
 * ✅ 전역 범용 파일 업로드 유틸리티
 * - 신규 첨부: 다중 추가/삭제, 용량 제한, 목록 UI
 * - 기존 첨부 삭제: delete_files hidden input 누적 + UI 제거 + empty message 처리
 * - FormData 전송: CSRF 헤더 + same-origin + XHR header
 * - ✅ submit 중복 전송 방지 (dataset.submitting)
 *
 * 사용법:
 *   initFileUpload({
 *     formSelector: "#postForm",
 *     fileInputSelector: "#fileInput",
 *     fileListSelector: "#fileNames",
 *     noFilesTextSelector: "#noFilesText",
 *     deleteContainerSelector: "#deleteContainer",
 *     existingFileSelector: ".remove-existing",
 *
 *     existingFilesSelector: "#existingFiles",
 *     existingFileListWrapSelector: "#existingFileList",
 *     existingEmptyHtml: '<p class="text-muted small m-0">첨부된 파일이 없습니다.</p>',
 *
 *     fileNameMaxWidthClass: "file-name-80",
 *     maxFileSize: 10 * 1024 * 1024,
 *
 *     // 선택 옵션
 *     attachmentsKey: "attachments", // or "attachments[]"
 *     onSubmitSuccess: (redirectUrl) => {},
 *     onSubmitError: (htmlText) => {},
 *   });
 */
(function () {
  "use strict";

  /* ===========================================================================
   * DOM helpers
   * =========================================================================== */
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function str(v) {
    return String(v == null ? "" : v).trim();
  }

  /* ===========================================================================
   * CSRF helpers
   * =========================================================================== */
  function buildHeaders(csrf) {
    var h = { "X-Requested-With": "XMLHttpRequest" };
    // FormData 사용 시 Content-Type을 직접 지정하지 않음
    if (csrf) h["X-CSRFToken"] = csrf;
    return h;
  }

  /* ===========================================================================
   * Format
   * =========================================================================== */
  function formatFileSize(bytes) {
    if (!bytes) return "0 B";
    var units = ["B", "KB", "MB", "GB"];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    var size = bytes / Math.pow(1024, i);
    return size.toFixed(1) + " " + units[i];
  }

  /* ===========================================================================
   * Main API
   * =========================================================================== */
  window.initFileUpload = function (options) {
    /* ---------------------------------------------
     * ⚙️ 옵션 병합
     * --------------------------------------------- */
    var config = Object.assign(
      {
        formSelector: "#postForm",
        fileInputSelector: "#fileInput",
        fileListSelector: "#fileNames",
        noFilesTextSelector: "#noFilesText",
        deleteContainerSelector: "#deleteContainer",

        existingFileSelector: ".remove-existing",

        existingFilesSelector: "#existingFiles",
        existingFileListWrapSelector: "#existingFileList",
        existingEmptyHtml: '<p class="text-muted small m-0">첨부된 파일이 없습니다.</p>',

        fileNameMaxWidthClass: "file-name-80",

        maxFileSize: 10 * 1024 * 1024, // 10MB
        attachmentsKey: "attachments", // 필요 시 "attachments[]"

        onSubmitSuccess: null,
        onSubmitError: null,
      },
      options || {}
    );

    /* ---------------------------------------------
     * 📋 주요 DOM 요소
     * --------------------------------------------- */
    var form = qs(config.formSelector);
    var fileInput = qs(config.fileInputSelector);
    var fileList = qs(config.fileListSelector);
    var noFilesText = qs(config.noFilesTextSelector);
    var deleteContainer = qs(config.deleteContainerSelector);

    if (!form || !fileInput) {
      console.warn("⚠️ initFileUpload: 필수 요소가 없습니다.", {
        form: !!form,
        fileInput: !!fileInput,
      });
      return;
    }
    if (!deleteContainer) deleteContainer = form; // 방어

    /* ---------------------------------------------
     * 상태: 신규 첨부 파일
     * --------------------------------------------- */
    var selectedFiles = [];

    /* ===========================================================================
     * 1) 기존 첨부 삭제 처리 (수정 페이지)
     * - delete_files hidden input 중복 생성 방지
     * =========================================================================== */
    (function bindExistingDeleteButtons() {
      var existingButtons = qsa(config.existingFileSelector);
      if (!existingButtons.length) return;

      existingButtons.forEach(function (btn) {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";

        btn.addEventListener("click", function () {
          var fileId = str(btn.dataset.id);
          if (!fileId) return;

          // ✅ 동일 fileId 중복 hidden input 방지
          var already = qs('input[name="delete_files"][value="' + fileId + '"]', deleteContainer);
          if (already) {
            // UI만 제거되어야 하는 케이스 방어
            var li0 = btn.closest ? btn.closest("li") : null;
            if (li0 && li0.remove) li0.remove();
            return;
          }

          // delete_files hidden input 추가
          var hidden = document.createElement("input");
          hidden.type = "hidden";
          hidden.name = "delete_files";
          hidden.value = fileId;
          deleteContainer.appendChild(hidden);

          // UI 제거
          var li = btn.closest ? btn.closest("li") : null;
          if (li && li.remove) li.remove();

          // 남은 기존 파일이 없으면 empty message 표시
          var existingList = qs(config.existingFilesSelector);
          var wrap = qs(config.existingFileListWrapSelector);
          if (existingList && wrap) {
            var remaining = qsa("li", existingList).length;
            if (remaining === 0) wrap.innerHTML = config.existingEmptyHtml;
          }
        });
      });
    })();

    /* ===========================================================================
     * 2) 신규 첨부 추가
     * =========================================================================== */
    (function bindFileInput() {
      if (fileInput.dataset.bound === "1") return;
      fileInput.dataset.bound = "1";

      fileInput.addEventListener("change", function (event) {
        var files = event && event.target ? event.target.files : null;
        var newFiles = files ? Array.prototype.slice.call(files) : [];

        newFiles.forEach(function (file) {
          if (!file) return;

          if (file.size > config.maxFileSize) {
            alert(
              "⚠️ " +
                file.name +
                "은(는) " +
                (config.maxFileSize / (1024 * 1024)).toFixed(0) +
                "MB를 초과합니다."
            );
            return;
          }
          selectedFiles.push(file);
        });

        renderSelectedFiles();
        fileInput.value = ""; // 동일 파일 재선택 가능
      });
    })();

    /* ===========================================================================
     * 3) 신규 첨부 목록 렌더
     * =========================================================================== */
    function renderSelectedFiles() {
      if (!fileList) return;

      fileList.innerHTML = "";

      if (!selectedFiles.length) {
        if (noFilesText) noFilesText.hidden = false;
        return;
      }
      if (noFilesText) noFilesText.hidden = true;

      selectedFiles.forEach(function (file, index) {
        var li = document.createElement("li");
        li.className = "d-flex justify-content-between align-items-center py-1 border-bottom";

        var nameSpan = document.createElement("span");
        nameSpan.textContent = file.name + " (" + formatFileSize(file.size) + ")";
        nameSpan.className = "small text-dark text-truncate " + str(config.fileNameMaxWidthClass);

        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "btn btn-sm btn-outline-danger";
        removeBtn.textContent = "✖";
        removeBtn.addEventListener("click", function () {
          selectedFiles.splice(index, 1);
          renderSelectedFiles();
        });

        li.appendChild(nameSpan);
        li.appendChild(removeBtn);
        fileList.appendChild(li);
      });
    }

    /* ===========================================================================
     * 4) Submit → FormData 전송 (CSRF + 중복 제출 방지)
     * =========================================================================== */
    (function bindSubmit() {
      if (form.dataset.boundUpload === "1") return;
      form.dataset.boundUpload = "1";

      form.addEventListener("submit", function (e) {
        e.preventDefault();

        // ✅ 중복 제출 방지
        if (form.dataset.submitting === "1") return;
        form.dataset.submitting = "1";

        var formData = new FormData(form);

        // 신규 첨부 append
        selectedFiles.forEach(function (file) {
          formData.append(config.attachmentsKey, file);
        });

        var headers = buildHeaders(window.csrfToken);

        fetch(form.action || window.location.href, {
          method: "POST",
          body: formData,
          headers: headers,
          credentials: "same-origin",
        })
          .then(function (response) {
            // Django: 성공 시 redirect 흔함
            if (response.redirected) {
              if (typeof config.onSubmitSuccess === "function") {
                config.onSubmitSuccess(response.url);
              } else {
                window.location.href = response.url;
              }
              return null;
            }

            // redirect가 아니면 HTML(폼 에러)일 가능성
            return response.text().then(function (html) {
              if (typeof config.onSubmitError === "function") {
                config.onSubmitError(html);
              } else {
                document.body.innerHTML = html;
              }
              return null;
            });
          })
          .catch(function (err) {
            alert("파일 업로드 중 오류가 발생했습니다.");
            console.error(err);
          })
          .finally(function () {
            form.dataset.submitting = "0";
          });
      });
    })();

    // 초기 상태 반영
    renderSelectedFiles();
  };
})();
