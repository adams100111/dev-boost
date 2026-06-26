from __future__ import annotations

import pytest

from devboost.core.errors import (
    DevbootError,
    DeviceError,
    DownloadError,
    UsbError,
    VentoyError,
)


def test_usb_errors_subclass_devboot_error() -> None:
    for cls in (UsbError, DeviceError, DownloadError, VentoyError):
        assert issubclass(cls, DevbootError)
    assert issubclass(DeviceError, UsbError)


def test_download_error_carries_url() -> None:
    err = DownloadError("https://x/iso", "checksum mismatch")
    assert "https://x/iso" in str(err)
    with pytest.raises(UsbError):
        raise err
