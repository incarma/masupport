(function () {
  const root = document.getElementById("dash-sales");
  if (!root) return;

  const modalEl = document.getElementById("productNameModal");
  const modalText = document.getElementById("productNameModalText");

  if (!modalEl || !modalText) return;

  const modal = new bootstrap.Modal(modalEl);

  // 이벤트 위임 (성능 + 중복 바인딩 방지)
  root.addEventListener("click", function (e) {
    const btn = e.target.closest(".dash-product-name");
    if (!btn) return;

    const name = btn.dataset.productName || "";
    modalText.textContent = name;

    modal.show();
  });
})();