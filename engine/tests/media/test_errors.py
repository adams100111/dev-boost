from __future__ import annotations

import pytest

from devboost.core.errors import (
    DevbootError,
    DeviceError,
    DownloadError,
    MediaError,
    VentoyError,
)


def test_usb_errors_subclass_devboot_error() -> None:
    for cls in (MediaError, DeviceError, DownloadError, VentoyError):
        assert issubclass(cls, DevbootError)
    assert issubclass(DeviceError, MediaError)


def test_download_error_carries_url() -> None:
    err = DownloadError("https://x/iso", "checksum mismatch")
    assert "https://x/iso" in str(err)
    with pytest.raises(MediaError):
        raise err
