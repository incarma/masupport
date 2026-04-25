// django_ma/static/js/partner/manage_efficiency/modal_search.js

import { els } from "./dom_refs.js";
import { readJsonOrThrow, isSuccessJson } from "../../common/manage/http.js";

function str(v) {
  return String(v ?? "").trim();
}

function escHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escAttr(v) {
  return escHtml(v);
}

export function setupModalSearch() {
  if (!els.searchForm) return;
  if (els.searchForm.dataset.bound === "1") return;
  els.searchForm.dataset.bound = "1";

  els.searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const keyword = str(els.searchKeyword?.value);
    if (!keyword) return alert("검색어를 입력하세요.");

    const url = els.root?.dataset?.searchUserUrl || "/board/search-user/";
    try {
      const res = await fetch(`${url}?q=${encodeURIComponent(keyword)}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      const data = await readJsonOrThrow(res, "검색 실패");
      if (!isSuccessJson(data) && !Array.isArray(data?.results)) {
        throw new Error(data?.message || "검색 실패");
      }

      if (!els.searchResults) return;
      if (!data.results?.length) {
        els.searchResults.innerHTML = `<div class="text-muted small mt-2">검색 결과가 없습니다.</div>`;
      } else {
        els.searchResults.innerHTML = data.results
          .map(
            (u) => `
            <div class="border rounded p-2 mb-1 d-flex justify-content-between align-items-center">
              <div>
                <strong>${escHtml(u.name)}</strong> (${escHtml(u.id)})
                ${u.regist ? ` <span class="text-muted">(${escHtml(u.regist)})</span>` : ""}<br>
                <small class="text-muted">${escHtml(u.part || "")}${u.branch ? " " + escHtml(u.branch) : ""}</small>
              </div>
              <button type="button" class="btn btn-sm btn-outline-primary selectUserBtn"
                data-id="${escAttr(u.id)}" data-name="${escAttr(u.name)}" data-branch="${escAttr(u.branch || "")}"
                data-part="${escAttr(u.part || "")}" data-rank="${escAttr(u.rank || "")}" data-regist="${escAttr(u.regist || "")}">
                선택
              </button>
            </div>`
          )
          .join("");
      }
    } catch (err) {
      console.error(err);
      alert("검색 중 오류가 발생했습니다.");
    }
  });

  if (document.documentElement.dataset.effModalSearchClickBound === "1") return;
  document.documentElement.dataset.effModalSearchClickBound = "1";

  document.addEventListener("click", (e) => {
    if (!e.target.classList.contains("selectUserBtn")) return;

    const btn = e.target;
    const userId = btn.dataset.id;
    const userName = btn.dataset.name;
    const userBranch = btn.dataset.branch || "";
    const userPart = btn.dataset.part || "";
    const userRank = btn.dataset.rank || "";
    const userRegist = btn.dataset.regist || "";

    const targetRow = els.inputTable?.querySelector("tbody tr:last-child");
    if (!targetRow) return alert("입력 행이 존재하지 않습니다.");

    targetRow.querySelector("input[name='tg_id']") && (targetRow.querySelector("input[name='tg_id']").value = userId);
    targetRow.querySelector("input[name='tg_name']") && (targetRow.querySelector("input[name='tg_name']").value = userName);
    targetRow.querySelector("input[name='tg_branch']") && (targetRow.querySelector("input[name='tg_branch']").value = `${userPart} ${userBranch}`.trim());
    targetRow.querySelector("input[name='tg_rank']") && (targetRow.querySelector("input[name='tg_rank']").value = userRank);
    const regEl = targetRow.querySelector("input[name='tg_regist']");
    if (regEl) regEl.value = userRegist;

    // 요청자 자동 입력
    targetRow.querySelector("input[name='rq_name']") && (targetRow.querySelector("input[name='rq_name']").value = window.currentUser?.name || "");
    targetRow.querySelector("input[name='rq_id']") && (targetRow.querySelector("input[name='rq_id']").value = window.currentUser?.id || "");
    targetRow.querySelector("input[name='rq_branch']") && (targetRow.querySelector("input[name='rq_branch']").value = window.currentUser?.branch || "");

    // 모달 닫기 & 폼 초기화
    const modalEl = document.getElementById("searchUserModal");
    const modal = window.bootstrap?.Modal?.getInstance?.(modalEl);
    if (modal) modal.hide();
    if (els.searchResults) els.searchResults.innerHTML = "";
    if (els.searchKeyword) els.searchKeyword.value = "";
  });
}
