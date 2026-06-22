"""
Decode reCAPTCHA protobuf request/response bodies without a schema.
Pure wire-format decoder: handles varints, length-delimited, fixed32/64.

Usage:
    uv run python proto_decode.py tests/fixtures/reload_req.bin
    uv run python proto_decode.py tests/fixtures/reload_req.bin out.json
"""
import json
import sys
from contextlib import suppress
from pathlib import Path


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def decode(buf: bytes, depth: int = 0) -> list[tuple[int, int, object]]:
    """Return list of (field_number, wire_type, value)."""
    out = []
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = read_varint(buf, pos)
        field = tag >> 3
        wire = tag & 7
        if wire == 0:  # varint
            val, pos = read_varint(buf, pos)
            out.append((field, wire, val))
        elif wire == 1:  # fixed64
            val = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
            out.append((field, wire, val))
        elif wire == 2:  # length-delimited
            ln, pos = read_varint(buf, pos)
            data = buf[pos:pos + ln]
            pos += ln
            out.append((field, wire, data))
        elif wire == 5:  # fixed32
            val = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
            out.append((field, wire, val))
        else:
            break  # unknown wire type
    return out


def parse_field(data: bytes) -> object:
    """Try to interpret a length-delimited field as a nested message,
    else as a utf-8 string, else raw bytes."""
    # Heuristic: try nested message first.
    with suppress(Exception):
        decoded = decode(data)
        total_consumed = sum(_len_of_entry(d) for d in decoded)
        if total_consumed == len(data) and decoded:
            nested = [parse_entry(d) for d in decoded]
            return {"_msg": nested}
    # Try utf-8 string if mostly printable
    with suppress(UnicodeDecodeError):
        s = data.decode("utf-8")
        if s and all(31 < ord(c) < 0x110000 for c in s) and sum(
            32 <= ord(c) < 127 for c in s
        ) / max(len(s), 1) > 0.85:
            return s
    return {"_hex": data.hex(), "_len": len(data)}


def _len_of_entry(entry) -> int:
    field, wire, val = entry
    if wire == 0:
        # we don't track exact bytes here; conservative
        return 1
    elif wire == 1:
        return 8
    elif wire == 2:
        # 1-byte len + data (ignore multi-byte len case)
        return 1 + len(val) if isinstance(val, (bytes, bytearray)) else 1
    elif wire == 5:
        return 4
    return 1


def parse_entry(entry) -> dict:
    field, wire, val = entry
    parsed = parse_field(val) if wire == 2 and isinstance(val, (bytes, bytearray)) else val
    return {"field": field, "wire": wire, "value": parsed}


def _jsonable(o):
    if isinstance(o, bytes):
        return {"_hex": o.hex(), "_len": len(o)}
    if isinstance(o, list):
        return [_jsonable(x) for x in o]
    return {k: _jsonable(v) for k, v in o.items()} if isinstance(o, dict) else o


def main() -> None:
    path = Path(sys.argv[1])
    data = path.read_bytes()
    decoded = decode(data)
    parsed = [parse_entry(e) for e in decoded]

    # Group repeated fields
    grouped: dict[int, list] = {}
    for p in parsed:
        grouped.setdefault(p["field"], []).append(p["value"])

    print(f"=== {path} ({len(data)} bytes) ===")
    for field in sorted(grouped):
        values = grouped[field]
        print(f"  field {field}: {len(values)} value(s)")
        for v in values[:5]:
            _print(v, "    ")
        if len(values) > 5:
            print(f"    ... +{len(values) - 5} more")

    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
        out.write_text(
            json.dumps(_jsonable(grouped), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  -> wrote {out}")


def _print(obj, pad: str) -> None:
    if isinstance(obj, dict) and "_msg" in obj:
        print(f"{pad}<nested message>")
        for sub in obj["_msg"]:
            print(f"{pad}  field {sub['field']} (wire {sub['wire']}):")
            _print(sub["value"], f"{pad}    ")
    elif isinstance(obj, dict) and "_hex" in obj:
        h = obj["_hex"][:100]
        print(f"{pad}<bytes len={obj['_len']}> {h}{'...' if obj['_len'] > 50 else ''}")
    elif isinstance(obj, str):
        s = obj if len(obj) <= 200 else f"{obj[:200]}..."
        print(f"{pad}{s!r}")
    else:
        print(f"{pad}{obj!r}")


if __name__ == "__main__":
    main()
