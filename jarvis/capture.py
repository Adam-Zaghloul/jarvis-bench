"""Phase 5: photos (metadata stripped) and the quick-log API token.

Photos are saved to logs/photos/YYYY-MM-DD/HHMMSS-xxxx.(jpg|png). The browser already re-encodes through a
canvas (which drops EXIF); the server strips again so nothing with metadata is ever written:
  JPEG: drop APP1..APP15 (EXIF/GPS/XMP/IPTC/ICC) and COM segments; keep APP0 (JFIF) and image data.
  PNG:  drop tEXt, zTXt, iTXt, eXIf, tIME chunks.
"""
import base64
import json
import os
import re
import secrets
import struct

import store

SETTINGS = store.DATA_DIR / "settings.json"
PHOTO_DIR = store.LOG_DIR / "photos"
MAX_BYTES = 8 * 1024 * 1024
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_DROP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


# ---------------------------------------------------------------- settings / token

def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(d):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(SETTINGS))


def api_token():
    """Created once, kept in jarvis/settings.json. Used by POST /api/log from other apps (Shortcuts, curl)."""
    s = load_settings()
    if not s.get("api_token"):
        s["api_token"] = secrets.token_urlsafe(24)
        save_settings(s)
    return s["api_token"]


def token_ok(header_value):
    tok = (header_value or "").strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    return bool(tok) and secrets.compare_digest(tok, api_token())


# ---------------------------------------------------------------- metadata stripping

def strip_jpeg(b):
    if b[:2] != b"\xff\xd8":
        raise ValueError("Not a JPEG.")
    out = bytearray(b"\xff\xd8")
    i = 2
    while i < len(b):
        if b[i] != 0xFF:
            raise ValueError("Corrupt JPEG.")
        while i < len(b) and b[i] == 0xFF:  # fill bytes
            i += 1
        marker = b[i]
        i += 1
        if marker == 0xDA:  # start of scan: copy the rest verbatim
            out += b"\xff\xda" + b[i:]
            return bytes(out)
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            out += bytes([0xFF, marker])
            continue
        if marker == 0xD9:
            out += b"\xff\xd9"
            return bytes(out)
        if i + 2 > len(b):
            raise ValueError("Corrupt JPEG.")
        seg_len = struct.unpack(">H", b[i:i + 2])[0]
        seg = b[i:i + seg_len]
        i += seg_len
        if 0xE1 <= marker <= 0xEF or marker == 0xFE:
            continue  # APP1-15 (EXIF, GPS, XMP, ICC, IPTC) and comments: dropped
        out += bytes([0xFF, marker]) + seg
    raise ValueError("JPEG has no image data.")


def strip_png(b):
    if b[:8] != _PNG_SIG:
        raise ValueError("Not a PNG.")
    out = bytearray(_PNG_SIG)
    i = 8
    while i + 8 <= len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        ctype = b[i + 4:i + 8]
        chunk = b[i:i + 12 + n]
        i += 12 + n
        if ctype in _PNG_DROP:
            continue
        out += chunk
        if ctype == b"IEND":
            break
    return bytes(out)


def has_metadata(b):
    """For tests: does a JPEG/PNG still carry EXIF/GPS/text metadata?"""
    if b[:2] == b"\xff\xd8":
        return b"Exif\x00" in b.split(b"\xff\xda", 1)[0] or b"\xff\xfe" in b.split(b"\xff\xda", 1)[0]
    if b[:8] == _PNG_SIG:
        return any(t in b for t in (b"eXIf", b"tEXt", b"iTXt", b"zTXt"))
    return False


def save_photo(data_url):
    m = re.match(r"^data:image/(jpeg|jpg|png);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("Only JPEG or PNG images.")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > MAX_BYTES:
        raise ValueError("Image too large (8 MB max).")
    if raw[:2] == b"\xff\xd8":
        clean, ext = strip_jpeg(raw), "jpg"
    elif raw[:8] == _PNG_SIG:
        clean, ext = strip_png(raw), "png"
    else:
        raise ValueError("File is not a JPEG or PNG.")
    day = store._today()
    d = PHOTO_DIR / day
    d.mkdir(parents=True, exist_ok=True)
    name = "%s-%s.%s" % (store._now()[11:].replace(":", ""), secrets.token_hex(2), ext)
    (d / name).write_bytes(clean)
    return "jarvis/logs/photos/%s/%s" % (day, name), len(clean)
