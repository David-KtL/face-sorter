"""Turn exceptions into short Spanish messages for the user."""

from __future__ import annotations

import errno

from face_sorter.gui import strings as S


def friendly_message(exc: BaseException) -> str:
    """A message the user can act on; falls back to the exception text."""
    if isinstance(exc, MemoryError):
        return S.ERR_MEMORY
    if isinstance(exc, PermissionError):
        return S.ERR_PERMISSION.format(path=exc.filename or exc)
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return S.ERR_DISK_FULL
    return str(exc) or type(exc).__name__
