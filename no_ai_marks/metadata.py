"""Look inside binary files for metadata that marks them as AI-generated."""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from typing import Iterator

MAX_BYTES = 64 * 1024 * 1024
_MAX_FIELD = 1 << 20

_MAGIC = (
    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"RIFF", b"%PDF-",
    b"PK\x03\x04", b"II*\x00", b"MM\x00*",
)

# IPTC digital source type for AI output (also covers the composite variant).
_IPTC_AI = re.compile(rb"trainedalgorithmicmedia", re.I)
_C2PA = re.compile(rb"c2pa\.(?:claim|signature|assertions|actions|hash)|urn:c2pa:")
_XMP = re.compile(rb"<x:xmpmeta\b.*?</x:xmpmeta>", re.S)
_XMP_APP1 = b"http://ns.adobe.com/xap/1.0/\x00"

_PDF_FIELD = re.compile(rb"/(Producer|Creator|Author)\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", re.S)
_OFFICE_FIELD = re.compile(
    r"<((?:Application|dc:creator|cp:lastModifiedBy|meta:generator|meta:initial-creator))>([^<]*)</"
)
_OFFICE_PARTS = ("docProps/app.xml", "docProps/core.xml", "meta.xml")


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:8000] or data.startswith(_MAGIC) or data[4:8] == b"ftyp"


def scan_blob(data: bytes, registry) -> list[tuple[str, str]]:
    """Return (rule, message) pairs for one file's bytes. Tool names and
    PNG keys come from the registry."""
    data = data[:MAX_BYTES]
    found = []
    if _IPTC_AI.search(data):
        found.append(("ai-metadata", "IPTC digital source type marks it as AI-generated (trainedAlgorithmicMedia)"))
    if _C2PA.search(data):
        found.append(("c2pa-manifest", "embeds a C2PA content credentials manifest"))
    for where, key, text in _fields(data):
        tool = registry.metadata_keys.get(key.lower()) if key else None
        if tool:
            found.append(("ai-metadata", f"{where} has a '{key}' field ({tool})"))
        m = registry.metadata_names.search(text)
        if m:
            found.append(("ai-metadata", f"{where} names {m.group(0)}"))
    return list(dict.fromkeys(found))


def _fields(data: bytes) -> Iterator[tuple[str, str | None, str]]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        yield from _png(data)
    elif data.startswith(b"\xff\xd8\xff"):
        yield from _jpeg(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        yield from _webp(data)
    elif data.startswith(b"%PDF-"):
        yield from _pdf(data)
    elif data.startswith(b"PK\x03\x04"):
        yield from _office(data)
    for packet in _XMP.finditer(data):
        yield "XMP metadata", None, packet.group(0).decode("utf-8", "replace")


def _inflate(data: bytes) -> bytes:
    try:
        return zlib.decompressobj().decompress(data, _MAX_FIELD)
    except zlib.error:
        return b""


def _png(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"tEXt":
            key, _, value = body.partition(b"\0")
            yield "PNG tEXt chunk", key.decode("latin-1"), value.decode("latin-1")
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            yield "PNG zTXt chunk", key.decode("latin-1"), _inflate(rest[1:]).decode("latin-1")
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            if key == b"XML:com.adobe.xmp" or len(rest) < 2:
                continue  # XMP is scanned separately
            compressed, rest = rest[0], rest[2:]
            _lang, _, rest = rest.partition(b"\0")
            _translated, _, text = rest.partition(b"\0")
            if compressed:
                text = _inflate(text)
            yield "PNG iTXt chunk", key.decode("latin-1"), text.decode("utf-8", "replace")
        elif kind == b"eXIf":
            yield "EXIF", None, body.decode("latin-1")
        elif kind == b"IEND":
            break


def _jpeg(data: bytes):
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker in (0xDA, 0xD9):  # start of scan, end of image
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
        body = data[pos + 4:pos + 2 + length]
        pos += 2 + length
        if marker == 0xE1 and body.startswith(_XMP_APP1):
            continue
        if marker == 0xE1 and body.startswith(b"Exif\0"):
            yield "EXIF", None, body.decode("latin-1")
        elif 0xE0 <= marker <= 0xEF:
            yield f"JPEG APP{marker - 0xE0} segment", None, body.decode("latin-1")
        elif marker == 0xFE:
            yield "JPEG comment", None, body.decode("latin-1")


def _webp(data: bytes):
    pos = 12
    while pos + 8 <= len(data):
        kind, length = struct.unpack("<4sI", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 8 + length + (length & 1)
        if kind == b"EXIF":
            yield "EXIF", None, body.decode("latin-1")


def _pdf_string(raw: bytes) -> str:
    if raw.startswith(b"<"):
        try:
            raw = bytes.fromhex(raw[1:-1].decode("ascii"))
        except ValueError:
            return ""
    else:
        raw = re.sub(rb"\\(.)", rb"\1", raw[1:-1])
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    return raw.decode("latin-1")


def _pdf(data: bytes):
    for m in _PDF_FIELD.finditer(data):
        yield f"PDF {m.group(1).decode()}", None, _pdf_string(m.group(2))


def _office(data: bytes):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        for part in _OFFICE_PARTS:
            if part in names and archive.getinfo(part).file_size <= _MAX_FIELD:
                text = archive.read(part).decode("utf-8", "replace")
                for m in _OFFICE_FIELD.finditer(text):
                    yield f"{part} <{m.group(1)}>", None, m.group(2)
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
        return
