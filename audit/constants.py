# django_ma/audit/constants.py

class ACTION:
    # Auth
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAIL = "auth.login.fail"
    AUTH_LOGOUT = "auth.logout"

    # Board
    BOARD_POST_CREATE = "board.post.create"
    BOARD_POST_UPDATE = "board.post.update"
    BOARD_POST_DELETE = "board.post.delete"
    BOARD_ATTACHMENT_DOWNLOAD = "board.attachment.download"
    TASK_ATTACHMENT_DOWNLOAD = "board.task_attachment.download"

    # Manual
    MANUAL_CREATE = "manual.manual.create"
    MANUAL_UPDATE = "manual.manual.update"
    MANUAL_DELETE = "manual.manual.delete"
    MANUAL_ATTACHMENT_DOWNLOAD = "manual.attachment.download"
    MANUAL_BLOCK_CREATE = "manual.block.create"
    MANUAL_BLOCK_UPDATE = "manual.block.update"
    MANUAL_BLOCK_DELETE = "manual.block.delete"

    # Partner
    PARTNER_RATE_SAVE = "partner.rate.save"
    PARTNER_RATE_DELETE = "partner.rate.delete"
    PARTNER_STRUCTURE_SAVE = "partner.structure.save"
    PARTNER_STRUCTURE_DELETE = "partner.structure.delete"
    PARTNER_EFFICIENCY_SAVE = "partner.efficiency.save"
    PARTNER_EFFICIENCY_DELETE = "partner.efficiency.delete"
    PARTNER_PROCESS_DATE_UPDATE = "partner.process_date.update"
    PARTNER_PROCESS_DATE_DELETE = "partner.process_date.delete"

    # Commission
    COMMISSION_UPLOAD_DEPOSIT = "commission.upload.deposit"
    COMMISSION_UPLOAD_APPROVAL = "commission.upload.approval"
    COMMISSION_UPLOAD_EFFICIENCY = "commission.upload.efficiency"
    COMMISSION_FAIL_EXCEL_DOWNLOAD = "commission.fail_excel.download"

    # Accounts
    ACCOUNTS_EXCEL_UPLOAD = "accounts.excel.upload"
    ACCOUNTS_LEVEL_UPDATE = "accounts.user.level.update"
    ACCOUNTS_GRADE_UPDATE = "accounts.user.grade.update"