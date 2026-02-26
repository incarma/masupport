// django_ma/static/js/commission/approval_excel_upload.js
//
// ✅ 목적
// - "기존 기능에 전혀 영향을 주지 않는 범위" 내에서 가독성/유지보수성 개선
// - 공통 유틸 분리(로컬 모듈화), 기능별 재정렬, 방어 로직 유지, 주석 보강
//
// ✅ 기존 동작 유지 포인트
// - 템플릿 id/name 변경 대비: year/month/part/kind/file selector 다중 지원
// - FormData 강제 set + excel_file 키 통일
// - toast + 모달 닫기 + querystring 유지 새로고침
// - 중복 제출 방지 (dataset.submitting)
//
(() => {
  "use strict";

  /* ==========================================================
   * 0) Guard
   * ========================================================== */
  // ✅ 템플릿 SSOT: _approval_upload_modal.html
  const form = document.getElementById("approvalUploadForm");
  if (!form) return;

  const resultEl = document.getElementById("approvalUploadResult");
  const toastEl = document.getElementById("approvalUploadToast");
  const modalEl = document.getElementById("approvalExcelUploadModal");
  const failWrap = document.getElementById("approvalFailDownloadWrap");
  const failLink = document.getElementById("approvalFailDownloadLink");

  /* ==========================================================
   * 1) Tiny DOM utils
   * ========================================================== */
  const $ = (sel, root = document) => root.querySelector(sel);

  /* ==========================================================
   * 2) Bootstrap helpers (존재하지 않아도 fallback 동작 유지)
   * ========================================================== */
  const hasBootstrap = () => !!(window.bootstrap && window.bootstrap.Modal);

  const showToast = () => {
    if (!toastEl || !window.bootstrap) return;
    new bootstrap.Toast(toastEl, { delay: 1800 }).show();
  };

  const closeModal = () => {
    if (!modalEl || !hasBootstrap()) return;
    const inst = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
    inst.hide();
  };

  /* ==========================================================
   * 3) Form helpers
   * ========================================================== */
  const getCSRFToken = () => {
    const inp = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return inp ? inp.value : "";
  };

  const isSubmitting = () => form.dataset.submitting === "1";

  const setSubmitting = (on) => {
    form.dataset.submitting = on ? "1" : "0";
    const btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = !!on;
  };

  const showResult = (msg, type = "muted") => {
    if (!resultEl) return;
    resultEl.textContent = msg;
    resultEl.className = `mt-3 small text-center text-${type}`;
  };

  const setFailDownload = (url) => {
    if (!failWrap || !failLink) return;
    const u = (url || "").toString().trim();
    if (!u) {
      failWrap.classList.add("d-none");
      failLink.setAttribute("href", "#");
      return;
    }
    failLink.setAttribute("href", u);
    failWrap.classList.remove("d-none");
  };

  /* ==========================================================
   * 4) Robust input readers (템플릿 변경 대응)
   * ========================================================== */
  const readSelectValue = (selectorList) => {
    for (const sel of selectorList) {
      const el = $(sel, form) || $(sel);
      if (!el) continue;
      const v = (el.value ?? "").toString().trim();
      if (v) return v;
    }
    return "";
  };

  const readFileInput = (selectorList) => {
    for (const sel of selectorList) {
      const el = $(sel, form) || $(sel);
      if (!el) continue;
      if (el.files && el.files.length > 0) return el;
    }
    return null;
  };

  /* ==========================================================
   * 5) Validation
   * ========================================================== */
  const validate = ({ ym, kind, fileEl }) => {
    // ✅ 템플릿 SSOT: ym(YYYY-MM) 입력을 사용 (서버도 ym 지원)
    if (!ym) return { ok: false, msg: "월도를 입력해주세요. (예: 2026-02)" };
    if (!/^\d{4}-\d{2}$/.test(ym)) {
      return { ok: false, msg: "월도 형식이 올바르지 않습니다. (예: 2026-02)" };
    }
    if (!kind) return { ok: false, msg: "구분을 선택해주세요." };
    if (!fileEl) return { ok: false, msg: "엑셀 파일을 선택해주세요." };

    const file = fileEl.files[0];
    const name = (file?.name || "").toLowerCase();
    const okExt = name.endsWith(".xlsx") || name.endsWith(".xls");

    if (!okExt) {
      return { ok: false, msg: "엑셀 파일(.xlsx / .xls)만 업로드할 수 있습니다." };
    }
    return { ok: true, msg: "" };
  };

  /* ==========================================================
   * 6) Payload builders
   * ========================================================== */
  const buildSuccessMessage = (data) => {
    const ym = data?.ym ? String(data.ym) : "-";
    const kind = data?.kind ? String(data.kind) : "-";
    const rowCount = typeof data?.row_count === "number" ? data.row_count : null;
    const inserted = typeof data?.inserted === "number" ? data.inserted : null;

    const parts = [`✅ 완료 (${ym} / ${kind})`];
    if (rowCount !== null) parts.push(`rows: ${rowCount}`);
    if (inserted !== null) parts.push(`반영: ${inserted}`);
    return parts.join(" · ");
  };

  const buildFormData = ({ ym, part, kind, fileEl }) => {
    // ✅ SSOT: form에 있는 ym/part/kind/excel_file 기반 + 값 강제 set
    const fd = new FormData(form);
    fd.set("ym", ym);
    fd.set("part", part);
    fd.set("kind", kind);

    // 파일 name이 다른 경우도 대비해서 excel_file 키로 통일(서버가 excel_file 기대 시)
    if (!fd.get("excel_file") && fileEl?.files?.[0]) {
      fd.set("excel_file", fileEl.files[0]);
    }
    return fd;
  };

  /* ==========================================================
   * 7) Network
   * ========================================================== */
  const postFormData = async (fd) => {
    const res = await fetch(form.action, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: fd,
    });

    const data = await res.json().catch(() => null);
    return { res, data };
  };

  /* ==========================================================
   * 8) Main submit handler
   * ========================================================== */
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (isSubmitting()) return;

    // 모달 재사용 시 이전 상태 초기화
    setFailDownload("");

    // ✅ 템플릿 SSOT 값 읽기
    const ym = readSelectValue(['input[name="ym"]', "#ym", "#approvalYm"]);
    const part = readSelectValue(['select[name="part"]', "#part", "#approvalPart"]);
    const kind = readSelectValue(['select[name="kind"]', "#kind", "#approvalKind"]);

    const fileEl = readFileInput([
      'input[type="file"][name="excel_file"]',
      'input[type="file"][name="file"]',
      'input[type="file"]#excel_file',
      'input[type="file"]#approvalExcelFile',
      'input[type="file"]',
    ]);

    const v = validate({ ym, kind, fileEl });
    if (!v.ok) {
      showResult(v.msg, "danger");
      return;
    }

    setSubmitting(true);
    showResult("업로드 중...", "muted");

    const fd = buildFormData({ ym, part, kind, fileEl });

    try {
      const { res, data } = await postFormData(fd);

      if (!res.ok || !data || data.ok !== true) {
        const msg = data?.message ? data.message : `업로드 실패 (HTTP ${res.status})`;
        showResult(msg, "danger");
        return;
      }

      showResult(buildSuccessMessage(data), "success");
      // ✅ missing_sample이 있으면 서버가 fail_download_url 내려줌
      setFailDownload(data?.fail_download_url || "");
      showToast();

      // ✅ 모달 닫고, 쿼리스트링 유지한 채 새로고침 - 기존 유지
      setTimeout(() => {
        closeModal();
        window.location.reload();
      }, 600);
    } catch (err) {
      showResult("⚠️ 네트워크 오류로 업로드에 실패했습니다.", "danger");
    } finally {
      setSubmitting(false);
    }
  });
})();
