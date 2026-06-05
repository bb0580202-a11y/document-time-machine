"""Phase 1 全局常量。可被环境变量覆盖的留到 Phase 2。"""
DEBOUNCE_SECONDS = 5
FALLBACK_INTERVAL = 600
LARGE_FILE_MB = 50

# 黑名单：只放铁定是垃圾的，越短越安全（INV-2）。匹配 basename 的通配。
IGNORE_PATTERNS = [
    "~$*", "*.tmp", ".tmp", ".DS_Store", "Thumbs.db",
    "*.log", "*.aux", "desktop.ini",
]
# 白名单：重点保护、出问题重点告警（小写后缀）。
PROTECTED_EXTS = {
    ".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt",
    ".tex", ".md", ".txt", ".csv",
}
# zip 系 Office：完整性校验用 zip 可打开。
ZIP_OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}

IDENTITY_FILE = "dtm_identity.json"     # 位于 .git/ 内
NOTES_REF = "refs/notes/dtm"            # git notes 命名空间
TOOL_MARKER = "doc-time-machine"
