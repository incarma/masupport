/**
 * django_ma/static/js/datatable_config.js (FINAL REFACTOR)
 * -----------------------------------------------------------------------------
 * ✅ .datatable 자동 DataTables 초기화
 * - dataset 옵션:
 *    data-column-filter="true"  : 컬럼별 필터
 *    data-export="true"         : 엑셀 다운로드 버튼
 * - ✅ jQuery/DataTables 존재 체크 가드
 */
document.addEventListener("DOMContentLoaded", function () {
  const tables = document.querySelectorAll(".datatable");
  if (!tables.length) return;

  // ✅ 의존성 가드
  if (!window.jQuery || !window.jQuery.fn?.DataTable) {
    console.warn("⚠️ DataTables(jQuery) not loaded. Skip datatable_config.js");
    return;
  }

  tables.forEach((table) => {
    const enableColumnFilter = table.dataset.columnFilter === "true";
    const enableExport = table.dataset.export === "true";

    const dt = window.jQuery(table).DataTable({
      language: { url: "/static/vendor/datatables/1.13.8/i18n/ko.json" },
      paging: true,
      searching: true,
      ordering: true,
      order: [],
      lengthMenu: [10, 25, 50, 100],
      pageLength: 25,
      responsive: true,
      autoWidth: false,
      dom: enableExport ? "Bfrtip" : "frtip",
      buttons: enableExport
        ? [
            {
              extend: "excelHtml5",
              text: "엑셀 다운로드",
              className: "btn btn-sm btn-primary",
            },
          ]
        : [],
    });

    // ✅ 컬럼별 검색 필터
    if (!enableColumnFilter) return;

    window.jQuery(table)
      .find("thead th")
      .each(function () {
        const title = window.jQuery(this).text();
        window.jQuery(this).html(
          title + '<br><input type="text" class="form-control form-control-sm" placeholder="검색" />'
        );
      });

    dt.columns().every(function () {
      const that = this;
      window.jQuery("input", this.header()).on("keyup change", function () {
        if (that.search() !== this.value) that.search(this.value).draw();
      });
    });
  });
});
