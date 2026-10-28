"""Contraseñas y tokens guardados en disco (correo, Telegram).

En Windows se cifran con DPAPI (ligadas a la cuenta de Windows del equipo: otra PC o usuario no las puede
leer). En otros sistemas (desarrollo) solo se ocultan con base64. Nunca se guardan en texto plano.
"""
from __future__ import annotations

import base64
import sys


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(inp), None, None, None, None, 0x01, ctypes.byref(out))  # CRYPTPROTECT_UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class SecretError(OSError):
    """No se pudo cifrar: el secreto no se guarda (nunca se deja legible en disco)."""


def protect(text: str) -> str:
    if not text:
        return ""
    raw = text.encode("utf-8")
    if sys.platform == "win32":
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode("ascii")
        except Exception as exc:  # en Windows nunca se cae a base64: se avisa y no se guarda
            raise SecretError(f"no se pudo cifrar con DPAPI ({exc})") from exc
    return "b64:" + base64.b64encode(raw).decode("ascii")  # solo fuera de Windows (desarrollo)


def unprotect(stored: str) -> str:
    if not stored:
        return ""
    try:
        kind, _, data = stored.partition(":")
        raw = base64.b64decode(data)
        if kind == "dpapi":
            return _dpapi(raw, False).decode("utf-8")
        if kind == "b64":
            return raw.decode("utf-8")
    except Exception:
        return ""
    return ""
