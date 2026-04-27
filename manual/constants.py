# django_ma/manual/constants.py

# 제목/섹션/블록 타이틀 길이
MANUAL_TITLE_MAX_LEN = 80
SECTION_TITLE_MAX_LEN = 120
BLOCK_TITLE_MAX_LEN = 120

# 첨부파일 제한
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20MB

# manual 업로드 보안 정책
MANUAL_ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".hwp", ".hwpx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
}

MANUAL_ALLOWED_ATTACHMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/haansofthwp",
    "application/x-hwp",
    "application/vnd.hancom.hwp",
    "application/vnd.hancom.hwpx",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

MANUAL_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MANUAL_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}