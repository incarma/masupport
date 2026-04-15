# board/views/__init__.py
# =============================================================
# Public View API — re-export surface
#
# urls.py 는 항상 `from board import views` 패턴으로 접근합니다.
# 이 파일은 모든 서브모듈의 view 함수를 단일 네임스페이스로 노출합니다.
#
# ┌─ 모듈 구조 ─────────────────────────────────────────────┐
# │  posts.py        Post(업무요청) 뷰                       │
# │  tasks.py        Task(직원업무) 뷰 — superuser only      │
# │  forms.py        서식/PDF 뷰                             │
# │  attachments.py  첨부 다운로드 뷰 (보안 SSOT)           │
# │  collateral.py   담보평가 계산기 뷰 (신규)               │
# └──────────────────────────────────────────────────────────┘
#
# 규칙:
#   - 각 서브모듈에서 __all__ 을 정의하거나 명시적으로 import 한다.
#   - 외부에서 이 파일을 수정 없이 views.* 로 참조 가능해야 한다.
# =============================================================

from .posts import *          # post_list, post_create, post_detail, post_edit
from .tasks import *          # task_list, task_create, task_detail, task_edit
from .forms import *          # support_form, states_form, generate_*, search_user
from .attachments import *    # post_attachment_download, task_attachment_download

# 인라인 업데이트 뷰 (posts / tasks 에서 분리되어 있을 경우 대비 명시적 노출)
from .posts import (          # noqa: F811 — 중복 import 방지 (서브모듈이 __all__ 미정의 시 안전 보호)
    ajax_update_post_field,
    ajax_update_post_field_detail,
)
from .tasks import (          # noqa: F811
    ajax_update_task_field,
    ajax_update_task_field_detail,
)

# 담보평가 (신규 — Step 2 이후 추가)
from .collateral import (     # noqa: F401
    collateral_page,
    collateral_calc,
    collateral_delete,
)

# 업계정보 (support → board 1단계 브리지)
from .industry_info import (  # noqa: F401
    industry_info,
    industry_bookmarks,
    industry_save_preference,
    industry_mark_click,
)