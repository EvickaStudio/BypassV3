"""
Extract raw request bodies and responses from captured HAR files
into tests/fixtures/ so the other tools can decode them.

Usage:
    uv run python tools/extract_har.py                    # scans tests/har/
    uv run python tools/extract_har.py capture.har        # specific file
    uv run python tools/extract_har.py a.har b.har        # multiple files

Output goes to tests/fixtures/ (or the path given via --out).
"""
import argparse
import base64
import json
from contextlib import suppress
from pathlib import Path


def slug(url: str) -> str:
    tail = url.split("/")[-1].split("?")[0]
    return tail or "root"


def write(out_dir: Path, name: str, data: bytes | str) -> None:
    p = out_dir / name
    if isinstance(data, bytes):
        p.write_bytes(data)
        unit = "bytes"
    else:
        p.write_text(data, encoding="utf-8")
        unit = "chars"
    print(f"  wrote {p} ({len(data)} {unit})")


def process_har(har_path: Path, out_dir: Path, seen: set) -> None:
    print(f"=== {har_path}")
    d = json.loads(har_path.read_text(encoding="utf-8"))
    for e in d["log"]["entries"]:
        req = e["request"]
        resp = e["response"]
        url = req["url"]
        method = req["method"]
        slug_name = slug(url)
        key = (method, slug_name)
        if key in seen:
            idx = sum(k[1] == slug_name for k in seen)
            slug_name = f"{slug_name}_{idx}"
        seen.add(key)

        print(f"  {method} {url[:80]}")

        pd = req.get("postData", {})
        if pd.get("text"):
            text = pd["text"]
            if pd.get("encoding") == "base64":
                write(out_dir, f"{slug_name}_req.bin", base64.b64decode(text))
            else:
                write(out_dir, f"{slug_name}_req.txt", text)
                try:
                    write(out_dir, f"{slug_name}_req.bin", text.encode("latin-1"))
                except UnicodeEncodeError as ex:
                    print(f"    (latin-1 encode failed: {ex})")

        content = resp.get("content", {})
        if content.get("text"):
            text = content["text"]
            if content.get("encoding") == "base64":
                write(out_dir, f"{slug_name}_resp.bin", base64.b64decode(text))
            else:
                write(out_dir, f"{slug_name}_resp.txt", text)
                with suppress(UnicodeEncodeError):
                    write(out_dir, f"{slug_name}_resp.bin", text.encode("latin-1"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("har_files", nargs="*", help="HAR files to process (default: tests/har/*.har)")
    p.add_argument("--out", default="tests/fixtures", help="output directory (default: tests/fixtures)")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.har_files:
        har_paths = [Path(f) for f in args.har_files]
    else:
        har_dir = Path("tests/har")
        har_paths = sorted(har_dir.glob("*.har"))

    if not har_paths:
        print("No HAR files found. Place .har files in tests/har/ or pass paths as arguments.")
        return

    seen: set = set()
    for hp in har_paths:
        if not hp.exists():
            print(f"  skipping (not found): {hp}")
            continue
        process_har(hp, out_dir, seen)


if __name__ == "__main__":
    main()
