# django_ma/partner/views/__init__.py

"""partner.views package

This package splits the formerly-large partner/views.py into feature-focused modules.

Import surface:
    from partner.views import *   # urls.py can keep using partner.views.<view>

The __init__.py re-exports view callables to preserve existing import paths.
"""

from .pages import (
    redirect_to_join,
    manage_calculate,   
    manage_rate,
    manage_tables,
    manage_charts,
    join_form,

)

from .process_date import (
    structure_update_process_date,
    rate_update_process_date,
    efficiency_update_process_date,
)

from .structure import (
    ajax_save,
    ajax_delete,
    ajax_fetch,
    structure_fetch,
    structure_save,
    structure_delete,
)

from .efficiency import (
    efficiency_confirm_template_download,
    efficiency_confirm_attachment_download,
    efficiency_fetch,
    efficiency_save,
    efficiency_delete_row,
    efficiency_delete_group,
    efficiency_confirm_upload,
    efficiency_confirm_groups,
)

from .rate import (
    rate_fetch,
    rate_save,
    rate_delete,
)

from .grades import (
    manage_grades,
    upload_grades_excel,
    ajax_users_data,
    ajax_update_level,
)

from .parts import (
    ajax_fetch_channels,
    ajax_fetch_parts,
    ajax_fetch_branches,
)

from .tablesettings import (
    ajax_table_fetch,
    ajax_table_save,
)

from .ratetable import (
    ajax_rate_userlist,
    ajax_rate_userlist_excel,
    ajax_rate_userlist_upload,
    ajax_rate_user_detail,
    ajax_rate_userlist_template_excel,
)

from .subadmin import (
    ajax_add_sub_admin,
    ajax_delete_subadmin,
)

from partner.views.esign import (
    esign_confirm_page,
    esign_fetch,
    esign_save,
    esign_sign,
    esign_pdf_download,
    esign_delete_group,
)