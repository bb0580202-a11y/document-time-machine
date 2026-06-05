"""所有面向用户的错误都带'人话原因'（INV-5），且不含 git 术语（INV-6）。"""


class DtmError(Exception):
    """基类：message 必须是人能看懂的具体原因。"""


class GitUnavailableError(DtmError):
    pass


class NotADtmFolderError(DtmError):
    pass


class FolderMovedError(DtmError):
    """记录路径不存在，提示用户 relocate。"""


class IntegrityError(DtmError):
    pass


class LockBusyError(DtmError):
    """另一个进程正持有该仓库的备份锁（且未超时）。"""
