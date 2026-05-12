# django_ma/audit/constants.py

class ACTION:
    # Auth
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAIL = "auth.login.fail"
    AUTH_LOGIN_LOCKED = "auth.login.locked"
    AUTH_LOGIN_BLOCKED_LOCKED = "auth.login.blocked.locked"
    AUTH_LOGOUT = "auth.logout"

    # Board
    BOARD_POST_CREATE = "board.post.create"
    BOARD_POST_UPDATE = "board.post.update"
    BOARD_POST_DELETE = "board.post.delete"
    BOARD_TASK_CREATE = "board.task.create"
    BOARD_TASK_UPDATE = "board.task.update"
    BOARD_TASK_DELETE = "board.task.delete"

    BOARD_STATUS_UPDATE = "board.status.update"
    BOARD_HANDLER_UPDATE = "board.handler.update"
    BOARD_INLINE_UPDATE = "board.inline.update"

    BOARD_COMMENT_CREATE = "board.comment.create"
    BOARD_COMMENT_UPDATE = "board.comment.update"
    BOARD_COMMENT_DELETE = "board.comment.delete"

    BOARD_ATTACHMENT_UPLOAD = "board.attachment.upload"
    BOARD_ATTACHMENT_DELETE = "board.attachment.delete"
    BOARD_ATTACHMENT_DOWNLOAD = "board.attachment.download"
    TASK_ATTACHMENT_DOWNLOAD = "board.task_attachment.download"
    BOARD_SUPPORT_PDF_GENERATE = "board.support_pdf.generate"
    BOARD_STATES_PDF_GENERATE = "board.states_pdf.generate"
    BOARD_KR_HOLIDAY_SYNC = "board.kr_holiday.sync"

    # Manual
    MANUAL_CREATE = "manual.manual.create"
    MANUAL_UPDATE = "manual.manual.update"
    MANUAL_BULK_UPDATE = "manual.manual.bulk_update"
    MANUAL_REORDER = "manual.manual.reorder"
    MANUAL_DELETE = "manual.manual.delete"
    MANUAL_ATTACHMENT_UPLOAD = "manual.attachment.upload"
    MANUAL_ATTACHMENT_DELETE = "manual.attachment.delete"
    MANUAL_ATTACHMENT_DOWNLOAD = "manual.attachment.download"
    MANUAL_BLOCK_CREATE = "manual.block.create"
    MANUAL_BLOCK_UPDATE = "manual.block.update"
    MANUAL_BLOCK_DELETE = "manual.block.delete"
    
    # Manual / Section
    MANUAL_SECTION_CREATE = "manual.section.create"
    MANUAL_SECTION_UPDATE = "manual.section.update"
    MANUAL_SECTION_DELETE = "manual.section.delete"
    MANUAL_SECTION_REORDER = "manual.section.reorder"

    # Manual / Block order
    MANUAL_BLOCK_REORDER = "manual.block.reorder"
    MANUAL_BLOCK_MOVE = "manual.block.move"

    # Partner
    PARTNER_RATE_SAVE = "partner.rate.save"
    PARTNER_RATE_DELETE = "partner.rate.delete"
    PARTNER_STRUCTURE_SAVE = "partner.structure.save"
    PARTNER_STRUCTURE_DELETE = "partner.structure.delete"
    PARTNER_EFFICIENCY_SAVE = "partner.efficiency.save"
    PARTNER_EFFICIENCY_DELETE = "partner.efficiency.delete"
    PARTNER_PROCESS_DATE_UPDATE = "partner.process_date.update"
    PARTNER_PROCESS_DATE_DELETE = "partner.process_date.delete"
    PARTNER_TABLE_SAVE = "partner.table.save"
    PARTNER_RATE_UPLOAD = "partner.rate.upload"
    PARTNER_EFFICIENCY_CONFIRM_UPLOAD = "partner.efficiency.confirm.upload"
    PARTNER_EFFICIENCY_CONFIRM_DOWNLOAD = "partner.efficiency.confirm.download"
    PARTNER_LEADER_ADD = "partner.leader.add"
    PARTNER_LEADER_DELETE = "partner.leader.delete"
    PARTNER_GRADES_UPLOAD = "partner.grades.upload"

    # Commission
    COMMISSION_UPLOAD_DEPOSIT = "commission.upload.deposit"
    COMMISSION_UPLOAD_APPROVAL = "commission.upload.approval"
    COMMISSION_UPLOAD_EFFICIENCY = "commission.upload.efficiency"
    COMMISSION_FAIL_EXCEL_DOWNLOAD = "commission.fail_excel.download"
    COMMISSION_EXCEL_UPLOAD = "commission.excel.upload"

    # Accounts
    ACCOUNTS_EXCEL_UPLOAD = "accounts.excel.upload"
    ACCOUNTS_LEVEL_UPDATE = "accounts.user.level.update"
    ACCOUNTS_GRADE_UPDATE = "accounts.user.grade.update"
    ACCOUNTS_PASSWORD_RESET_UNLOCK = "accounts.user.password_reset_unlock"
    ACCOUNTS_PASSWORD_CHANGE_COMPLETED = "accounts.user.password_change.completed"
    ACCOUNTS_PASSWORD_CHANGE_CLEARED = "accounts.password_change_cleared"

    # Support
    SUPPORT_COLLECT_RUN = "support.collect.run"
    SUPPORT_COLLECT_FAIL = "support.collect.fail"
    SUPPORT_ARTICLE_HIDE = "support.article.hide"
    SUPPORT_ARTICLE_RESTORE = "support.article.restore"
    SUPPORT_USER_RATE = "support.user.rate"
    SUPPORT_USER_BOOKMARK = "support.user.bookmark"
    SUPPORT_USER_HIDE = "support.user.hide"
    SUPPORT_RECOMMEND_GENERATE = "support.recommend.generate"

    # ------------------------------------------------------------------
    # Collect (환수관리) — Step 1
    # 규약: domain.object.action 형식 준수
    # ------------------------------------------------------------------
    COLLECT_EXCEL_UPLOAD    = "collect.excel.upload"
    COLLECT_FEEDBACK_CREATE = "collect.feedback.create"
    COLLECT_FEEDBACK_UPDATE = "collect.feedback.update"
    COLLECT_FEEDBACK_DELETE = "collect.feedback.delete"

    RETENTION_EXCEL_UPLOAD = "retention.record.upload"

    # Partner / esign
    PARTNER_ESIGN_CREATE = "partner.esign.create"
    PARTNER_ESIGN_SIGN   = "partner.esign.sign"
    PARTNER_ESIGN_DELETE = "partner.esign.delete"
    PARTNER_ESIGN_PDF_DL = "partner.esign.pdf.download"
    PARTNER_ESIGN_PROCESS_DATE_UPDATE = "partner.esign.process_date.update"

    # Commission / RateExample (예시표)
    COMMISSION_RATE_EXAMPLE_UPLOAD          = "commission.rate_example.upload"
    COMMISSION_RATE_EXAMPLE_DOWNLOAD        = "commission.rate_example.download"
    COMMISSION_RATE_EXAMPLE_DELETE          = "commission.rate_example.delete"
    COMMISSION_RATE_EXAMPLE_NORMALIZE       = "commission.rate_example.normalize"
    COMMISSION_RATE_EXAMPLE_STRATEGY_UPDATE = "commission.rate_example.strategy_update"
    COMMISSION_RATE_EXAMPLE_CALCULATE       = "commission.rate_example.calculate"