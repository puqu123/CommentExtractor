"""Per-user model settings. The API key is protected by Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CommentExtractor" / "model.json"


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("模型密钥只能在 Windows 上保存和读取。")
    buffer = ctypes.create_string_buffer(data, len(data))
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise RuntimeError("无法使用当前 Windows 账户保护或读取模型密钥。")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load_settings(include_key=False):
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        data = {k: data[k] for k in ("endpoint", "model", "vision", "encrypted_key") if k in data}
        if include_key and data.get("encrypted_key"):
            data["key"] = _crypt(base64.b64decode(data["encrypted_key"], validate=True), True).decode("utf-8")
        return data
    except (OSError, ValueError, RuntimeError):
        return {}


def save_settings(endpoint, model, key, vision=True):
    from urllib.parse import urlsplit
    parsed = urlsplit(endpoint.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("请输入完整服务地址，例如 http://内网地址:端口/v1。")
    if not model.strip():
        raise ValueError("请输入服务实际使用的模型名称。")
    previous = load_settings()
    encrypted = base64.b64encode(_crypt(key.encode("utf-8"))).decode("ascii") if key else previous.get("encrypted_key", "")
    if not encrypted:
        raise ValueError("请输入 API Key。")
    data = {"endpoint": endpoint.strip().rstrip("/"), "model": model.strip(), "vision": bool(vision), "encrypted_key": encrypted}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def configured(settings):
    return bool(settings.get("endpoint") and settings.get("model") and settings.get("encrypted_key"))
