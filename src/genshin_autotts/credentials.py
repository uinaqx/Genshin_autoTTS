from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


ENVIRONMENT_CREDENTIALS = {
    "volcengine": {
        "app_id": "GENSHIN_AUTOTTS_VOLCENGINE_APP_ID",
        "access_token": "GENSHIN_AUTOTTS_VOLCENGINE_ACCESS_TOKEN",
    },
    "aliyun": {
        "app_key": "GENSHIN_AUTOTTS_ALIYUN_APP_KEY",
        "access_token": "GENSHIN_AUTOTTS_ALIYUN_ACCESS_TOKEN",
    },
}


class CredentialStoreError(RuntimeError):
    """Raised when local credential protection is unavailable or fails."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("安全凭据存储仅支持 Windows；请改用环境变量")
    source, source_buffer = _blob(data)
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        ctypes.c_wchar_p("GenshinAutoTTS cloud credentials"),
        None,
        None,
        None,
        0x01,
        ctypes.byref(target),
    ):
        raise CredentialStoreError("Windows DPAPI 无法加密凭据")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        del source_buffer
        kernel32.LocalFree(target.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("安全凭据存储仅支持 Windows；请改用环境变量")
    source, source_buffer = _blob(data)
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(target),
    ):
        raise CredentialStoreError("Windows DPAPI 无法解密凭据")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        del source_buffer
        kernel32.LocalFree(target.pbData)


class CredentialStore:
    """Store cloud credentials encrypted for the current Windows user.

    Environment variables always take precedence. This makes CI and managed
    deployments possible without writing any secret to disk.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def get_provider(self, provider: str) -> dict[str, str]:
        expected = ENVIRONMENT_CREDENTIALS.get(provider)
        if expected is None:
            return {}
        stored = self._load().get(provider, {})
        result: dict[str, str] = {}
        for key, env_name in expected.items():
            value = os.environ.get(env_name) or stored.get(key)
            if value:
                result[key] = str(value)
        return result

    def has_provider(self, provider: str) -> bool:
        expected = ENVIRONMENT_CREDENTIALS.get(provider)
        if expected is None:
            return provider in {"recorded", "edge"}
        values = self.get_provider(provider)
        return all(values.get(key) for key in expected)

    def save_provider(self, provider: str, values: dict[str, str]) -> None:
        expected = ENVIRONMENT_CREDENTIALS.get(provider)
        if expected is None:
            raise ValueError(f"不支持保存 {provider} 凭据")
        cleaned = {key: str(values.get(key, "")).strip() for key in expected}
        if not all(cleaned.values()):
            raise ValueError("API 凭据字段不能为空")
        payload = self._load()
        payload[provider] = cleaned
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted = _protect(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(self.path)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            raw = _unprotect(self.path.read_bytes())
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeError, CredentialStoreError) as exc:
            raise CredentialStoreError(f"无法读取本地 API 凭据：{exc}") from exc
        if not isinstance(payload, dict):
            raise CredentialStoreError("本地 API 凭据格式无效")
        result: dict[str, dict[str, str]] = {}
        for provider, values in payload.items():
            if not isinstance(values, dict):
                continue
            result[str(provider)] = {
                str(key): str(value) for key, value in values.items() if value
            }
        return result
