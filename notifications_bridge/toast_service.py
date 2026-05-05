from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ToastService:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id
        self._toaster = None
        try:
            from windows_toasts import Toast, WindowsToaster

            self._Toast = Toast
            self._toaster = WindowsToaster(app_id)
        except Exception:
            logger.exception("Windows-Toasts unavailable; toasts disabled")

    def show(self, title: str, body: str) -> None:
        if not self._toaster:
            logger.info("Toast (disabled): %s | %s", title, body)
            return
        try:
            toast = self._Toast()
            toast.text_fields = [title, body]
            self._toaster.show_toast(toast)
        except Exception:
            logger.exception("Failed to show toast")
