(function () {
  "use strict";

  const root = document.getElementById("rate-example-root");
  if (!root) return;
  if (root.dataset.inited === "1") return;
  root.dataset.inited = "1";

  // ── URL / CSRF ─────────────────────────────────────────────────────────────
  const UPLOAD_URL = root.dataset.uploadUrl;

  // ── 보험사 목록 (json_script 태그에서 읽기) ───────────────────────────────
  const LIFE_INSURERS = JSON.parse(
    document.getElementById("life-insurers-data").textContent
  );
  const NONLIFE_INSURERS = JSON.parse(
    document.getElementById("nonlife-insurers-data").textContent
  );

  // ── DataTables 초기화 ──────────────────────────────────────────────────────
  // typeof $ 는 $ 미선언 시에도 throw 없이 "undefined" 반환 (ECMAScript 보장).
  // typeof $.fn 은 $ 평가 후 .fn 접근이라 $ 미선언 시 ReferenceError → 사용 금지.
  const tableEl = document.getElementById("re-table");
  let table = null;
  if (tableEl && typeof $ !== "undefined" && $ && $.fn && $.fn.DataTable) {
    table = $(tableEl).DataTable({
      searching: false,
      pageLength: 20,
      language: {
        lengthMenu: "_MENU_ 건씩 보기",
        info: "_START_ - _END_ / 전체 _TOTAL_ 건",
        infoEmpty: "데이터 없음",
        paginate: { previous: "이전", next: "다음" },
        emptyTable: "등록된 예시표가 없습니다.",
        zeroRecords: "검색 결과 없음",
      },
      columnDefs: [
        { orderable: false, targets: [7] },  // 다운로드
        { orderable: false, targets: [8] },  // 삭제 (superuser 없으면 존재하지 않음)
      ],
    });
  }

  // ── 커스텀 필터 헬퍼 ──────────────────────────────────────────────────────
  function buildInsurerOptions(type) {
    const sel = document.getElementById("re-filter-insurer");
    sel.innerHTML = '<option value="">전체</option>';
    const list = type === "생명보험" ? LIFE_INSURERS
                : type === "손해보험" ? NONLIFE_INSURERS
                : [];
    list.forEach(function (name) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }

  // ── 필터 이벤트 ───────────────────────────────────────────────────────────
  const filterType = document.getElementById("re-filter-type");
  const filterCat = document.getElementById("re-filter-cat");
  const filterInsurer = document.getElementById("re-filter-insurer");

  if (filterType) {
    filterType.addEventListener("change", function () {
      buildInsurerOptions(this.value);
      filterInsurer.value = "";
      if (table) {
        table.column(1).search(this.value).column(2).search("").draw();
      }
    });
  }

  if (filterCat) {
    filterCat.addEventListener("change", function () {
      if (table) table.column(2).search(this.value).draw();
    });
  }

  if (filterInsurer) {
    filterInsurer.addEventListener("change", function () {
      if (table) table.column(3).search(this.value).draw();
    });
  }

  // ── 모달: 손생 변경 → 보험사 드랍다운 교체 ────────────────────────────────
  const modalType = document.getElementById("re-modal-type");
  const modalInsurer = document.getElementById("re-modal-insurer");

  if (modalType && modalInsurer) {
    modalType.addEventListener("change", function () {
      const val = this.value;
      modalInsurer.innerHTML = '<option value="">선택</option>';
      const list = val === "life" ? LIFE_INSURERS
                  : val === "nonlife" ? NONLIFE_INSURERS
                  : [];
      if (list.length === 0) {
        modalInsurer.disabled = true;
        modalInsurer.innerHTML = '<option value="">손생구분을 먼저 선택하세요</option>';
        return;
      }
      modalInsurer.disabled = false;
      list.forEach(function (name) {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        modalInsurer.appendChild(opt);
      });
    });
  }

  // ── 저장 버튼 ──────────────────────────────────────────────────────────────
  const btnSave = document.getElementById("re-btn-save");
  const errBox = document.getElementById("re-upload-error");

  function showError(msg) {
    if (!errBox) return;
    errBox.textContent = msg;
    errBox.classList.remove("d-none");
  }
  function clearError() {
    if (!errBox) return;
    errBox.textContent = "";
    errBox.classList.add("d-none");
  }

  if (btnSave) {
    btnSave.addEventListener("click", async function () {
      clearError();
      const insurerType = document.getElementById("re-modal-type")?.value || "";
      const category = document.getElementById("re-modal-cat")?.value || "";
      const insurer = modalInsurer?.value || "";
      const fileInput = document.getElementById("re-modal-file");
      const file = fileInput?.files[0];

      if (!insurerType) { showError("손생구분을 선택해 주세요."); return; }
      if (!category) { showError("구분을 선택해 주세요."); return; }
      if (!insurer) { showError("보험사를 선택해 주세요."); return; }
      if (!file) { showError("파일을 선택해 주세요."); return; }

      const fd = new FormData();
      fd.append("insurer_type", insurerType);
      fd.append("category", category);
      fd.append("insurer", insurer);
      fd.append("file", file);

      btnSave.disabled = true;
      try {
        const res = await fetch(UPLOAD_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": window.csrfToken || "" },
          body: fd,
        });
        const json = await res.json();
        if (json.ok) {
          const modal = bootstrap.Modal.getInstance(
            document.getElementById("rateExampleUploadModal")
          );
          if (modal) modal.hide();
          location.reload();
        } else {
          showError(json.message || "업로드에 실패했습니다.");
        }
      } catch (e) {
        showError("네트워크 오류가 발생했습니다.");
      } finally {
        btnSave.disabled = false;
      }
    });
  }

  // ── 삭제 버튼 (이벤트 위임) ────────────────────────────────────────────────
  root.addEventListener("click", async function (e) {
    const btn = e.target.closest(".re-btn-delete");
    if (!btn) return;

    if (!confirm("정말 삭제하시겠습니까?")) return;

    const deleteUrl = btn.dataset.deleteUrl;
    if (!deleteUrl) return;

    btn.disabled = true;
    try {
      const res = await fetch(deleteUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": window.csrfToken || "" },
      });
      const json = await res.json();
      if (json.ok) {
        if (table) {
          const row = btn.closest("tr");
          table.row(row).remove().draw();
        } else {
          location.reload();
        }
      } else {
        alert(json.message || "삭제에 실패했습니다.");
        btn.disabled = false;
      }
    } catch (e) {
      alert("네트워크 오류가 발생했습니다.");
      btn.disabled = false;
    }
  });

  // ── 모달 초기화 (열릴 때 입력 리셋) ───────────────────────────────────────
  const uploadModal = document.getElementById("rateExampleUploadModal");
  if (uploadModal) {
    uploadModal.addEventListener("show.bs.modal", function () {
      clearError();
      const form = ["re-modal-type", "re-modal-cat", "re-modal-insurer", "re-modal-file"];
      form.forEach(function (id) {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.tagName === "SELECT") el.selectedIndex = 0;
        if (el.tagName === "INPUT") el.value = "";
      });
      if (modalInsurer) {
        modalInsurer.disabled = true;
        modalInsurer.innerHTML = '<option value="">손생구분을 먼저 선택하세요</option>';
      }
    });
  }
})();
