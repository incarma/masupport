/**
 * django_ma/static/js/partner/join_form.js
 * ------------------------------------------------------------
 * 위촉서류 출력 페이지 JS
 *
 * 기능:
 * 1) 주소 찾기 버튼 → Daum Postcode API 실행
 * 2) PDF 출력 submit 시 진행률 UI가 존재하는 경우에만 표시
 *
 * CSP:
 * - inline script 제거
 * - 이벤트는 addEventListener로 바인딩
 */
document.addEventListener("DOMContentLoaded", function () {
  const addressBtn = document.getElementById("btnFindAddress");

  if (addressBtn) {
    addressBtn.addEventListener("click", function () {
      if (!window.daum?.Postcode) {
        window.alert("주소 검색 서비스를 불러오지 못했습니다.");
        return;
      }

      new window.daum.Postcode({
        oncomplete: function (data) {
          const postcode = document.getElementById("postcode");
          const address = document.getElementById("address");
          const detail = document.getElementById("address_detail");

          if (postcode) postcode.value = data.zonecode || "";
          if (address) address.value = data.roadAddress || "";
          if (detail) detail.focus();
        },
      }).open();
    });
  }

  const pdfButton = document.getElementById("pdfButton");
  const progressWrapper = document.getElementById("progressWrapper");
  const progressBar = document.getElementById("progressBar");

  if (!pdfButton || !progressWrapper || !progressBar) return;

  pdfButton.addEventListener("click", function () {
    progressWrapper.hidden = false;
    progressBar.style.width = "0%";
    progressBar.textContent = "0%";

    let progress = 0;
    const interval = window.setInterval(function () {
      progress += 5;

      if (progress >= 90) {
        window.clearInterval(interval);
        return;
      }

      progressBar.style.width = progress + "%";
      progressBar.textContent = progress + "%";
    }, 250);
  });
});