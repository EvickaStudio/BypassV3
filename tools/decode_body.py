"""
Decode captured reCAPTCHA protobuf request/response bodies.

Usage:
    python decode_body.py path/to/body.bin
    python decode_body.py --raw '<JS-escaped string from devtools>'
    python decode_body.py --file body.txt   # file containing JS-escaped string

The devtools "Copy as fetch" body uses JS string escapes like \\u0012 and \\u00f9.
Those are unicode code points <= 0xFF, so they round-trip cleanly through latin-1.
"""

import json
import sys
from contextlib import suppress
from pathlib import Path

import blackboxprotobuf


def _jsonable(obj):
    if isinstance(obj, bytes):
        with suppress(UnicodeDecodeError):
            t = obj.decode("utf-8")
            if all(31 < ord(c) < 127 or c in "\n\r\t" for c in t) and t:
                return {"_str": t}
        return {"_bytes_hex": obj.hex(), "_len": len(obj)}
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def decode_bytes(data: bytes, label: str = "", out_path: str | None = None) -> dict:
    print(f"=== {label} ({len(data)} bytes) ===")
    try:
        message, typedef = blackboxprotobuf.decode_message(data)
    except Exception as e:
        print(f"  decode failed: {e}")
        print(f"  raw (first 200): {data[:200]!r}")
        return {}
    _print_message(message, typedef, indent=1)
    payload = {
        "label": label,
        "length": len(data),
        "message": _jsonable(message),
        "typedef": _jsonable(typedef),
    }
    if out_path:
        Path(out_path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  -> wrote {out_path}")
    return payload


def js_escaped_to_bytes(text: str) -> bytes:
    """Convert a JS-escaped string (as shown in devtools) to raw bytes."""
    # Strip surrounding quotes if present
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1]
    # Decode JS unicode escapes and hex escapes to bytes via latin-1.
    # \u00XX -> byte XX, \xNN -> byte NN, \n -> 0x0A, etc.
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "u" and i + 5 < len(text) + 1:
                cp = int(text[i + 2 : i + 6], 16)
                out.append(cp & 0xFF)
                i += 6
                continue
            if nxt == "x" and i + 3 < len(text) + 1:
                cp = int(text[i + 2 : i + 4], 16)
                out.append(cp & 0xFF)
                i += 4
                continue
            simple = {
                "n": 0x0A, "r": 0x0D, "t": 0x09, "b": 0x08, "f": 0x0C,
                "0": 0x00, "\\": 0x5C, "/": 0x2F, '"': 0x22, "'": 0x27,
            }
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            out.append(ord(ch))
            i += 1
            continue
        # Non-escaped char: encode as latin-1 (works for the high-unicode
        # chars that devtools renders directly, e.g. ù, «, etc.)
        cp = ord(ch)
        out.append(cp & 0xFF)
        i += 1
    return bytes(out)


def _print_message(message: dict, typedef: dict, indent: int) -> None:
    pad = "  " * indent
    for field_num, typedef_entry in sorted(typedef.items(), key=lambda x: int(x[0])):
        field_name = typedef_entry.get("field_name", f"field_{field_num}")
        ftype = typedef_entry.get("type", "?")
        alt = typedef_entry.get("alt_typedef")
        value = message.get(field_name)
        if isinstance(value, list):
            print(f"{pad}{field_name} ({ftype}): [list of {len(value)}]")
            for item in value:
                if alt and isinstance(item, dict):
                    _print_message(item, alt, indent + 1)
                else:
                    _print_value(item, ftype, f"{pad}  ")
        elif alt and isinstance(value, dict):
            print(f"{pad}{field_name} ({ftype}):")
            _print_message(value, alt, indent + 1)
        else:
            _print_value(value, ftype, pad, field_name)


def _print_value(value, ftype, pad, field_name=""):
    label = f"{field_name} ({ftype})" if field_name else f"({ftype})"
    if isinstance(value, bytes):
        with suppress(UnicodeDecodeError):
            text = value.decode("utf-8")
            if all(31 < ord(c) < 127 or c in "\n\r\t" for c in text) and len(text) > 0:
                print(f"{pad}{label}: {text!r} (utf-8)")
                return
        preview = value[:80].hex()
        print(f"{pad}{label}: <bytes len={len(value)}> {preview}{'...' if len(value) > 80 else ''}")
    else:
        shown = repr(value)
        if len(shown) > 200:
            shown = f"{shown[:200]}..."
        print(f"{pad}{label}: {shown}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] in ("--raw", "-r"):
        body = js_escaped_to_bytes(args[1])
        out = args[2] if len(args) > 2 else None
        decode_bytes(body, "raw arg", out)
        return

    if args[0] in ("--file", "-f"):
        text = Path(args[1]).read_text(encoding="utf-8")
        body = js_escaped_to_bytes(text)
        out = args[2] if len(args) > 2 else None
        decode_bytes(body, f"file: {args[1]}", out)
        return

    path = Path(args[0])
    data = path.read_bytes()
    out = args[1] if len(args) > 1 else None
    decode_bytes(data, f"file: {path}", out)


if __name__ == "__main__":
    main()
