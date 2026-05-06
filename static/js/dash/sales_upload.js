// django_ma/static/js/dash/sales_upload.js
import { getCSRFToken } from "../common/manage/csrf.js";

(function () {
  const root = document.getElementById('dash-sales');
  if (!root) return;

  const uploadUrl = root.dataset.uploadUrl;
  const form = document.getElementById('salesUploadForm');
  const fileInput = document.getElementById('salesExcelFile');
  const resultBox = document.getElementById('salesUploadResult');
  const submitBtn = document.getElementById('salesUploadSubmitBtn');

  function renderResult(ok, payload) {
    if (!resultBox) return;
    if (!ok) {
      resultBox.innerHTML = `<div class="alert alert-danger mb-0">${payload?.message || '업로드 실패'}</div>`;
      return;

      
    }
    const s = payload.summary || {};
    resultBox.innerHTML = `
      <div class="alert alert-success mb-0">
        <div class="fw-bold">${payload.message || '업로드 완료'}</div>
        <hr class="my-2">
        <ul class="mb-0">
          <li>파일 행수(유효): ${s.rows_in_file ?? '-'}</li>
          <li>레코드 upsert: ${s.rows_upserted ?? '-'}</li>
          <li>스킵: ${s.rows_skipped ?? '-'}</li>
          <li>사용자 생성: ${s.users_created ?? '-'}</li>
          <li>사용자 업데이트: ${s.users_updated ?? '-'}</li>
        </ul>
      </div>
    `;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultBox.innerHTML = '';
    const file = fileInput.files?.[0];
    if (!file) {
      renderResult(false, { message: '엑셀 파일을 선택해주세요.' });
      return;
    }

    const fd = new FormData();
    fd.set('excel_file', file);

    submitBtn.disabled = true;
    submitBtn.textContent = '업로드 중...';

    try {
      const res = await fetch(uploadUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCSRFToken() },
        body: fd
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        renderResult(false, data);
      } else {
        renderResult(true, data);

        // ✅ 업로드 성공 후 테이블 갱신
        setTimeout(() => {
            window.location.reload();
        }, 800); // 결과 메시지 0.8초 보여준 뒤 새로고침
      }
    } catch (err) {
      renderResult(false, { message: `네트워크 오류: ${err}` });
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = '업로드 실행';
    }
  });
})();
