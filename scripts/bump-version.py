"""Bump the release version across all three manifests at once.

Usage:
    py -3 scripts/bump-version.py            # check-only: verify the three versions match
    py -3 scripts/bump-version.py 0.2.0      # set an explicit version
    py -3 scripts/bump-version.py patch       # bump patch (0.1.31 -> 0.1.32); minor/major too

The release flow then is:
    py -3 scripts/bump-version.py <ver>
    git commit -am "release: v<ver>" && git push
    git tag v<ver> && git push origin v<ver>   # <- triggers the Release workflow
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARGO = ROOT / "src-tauri" / "Cargo.toml"
CONF = ROOT / "src-tauri" / "tauri.conf.json"
PKG = ROOT / "package.json"

FILES = {
    "Cargo.toml": (CARGO, r'(?m)^version\s*=\s*"([^"]+)"'),
    "tauri.conf.json": (CONF, None),  # json
    "package.json": (PKG, None),
}


def read_versions():
    out = {}
    m = re.search(FILES["Cargo.toml"][1], CARGO.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Cargo.toml: no version line found")
    out["Cargo.toml"] = m.group(1)
    out["tauri.conf.json"] = json.loads(CONF.read_text(encoding="utf-8"))["version"]
    out["package.json"] = json.loads(PKG.read_text(encoding="utf-8"))["version"]
    return out


def write_versions(new: str):
    # Cargo.toml (first version = line only)
    text = CARGO.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^(version\s*=\s*)"[^"]+"', r'\g<1>"%s"' % new, text, count=1)
    CARGO.write_text(text, encoding="utf-8", newline="\n")
    # json files
    for path in (CONF, PKG):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = new
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


def bump(cur: str, part: str) -> str:
    major, minor, patch = (int(x) for x in cur.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"unknown bump part: {part}")


def main():
    vers = read_versions()
    unique = set(vers.values())
    args = sys.argv[1:]

    if not args:
        if len(unique) == 1:
            v = unique.pop()
            print(f"OK: all three manifests are at {v}")
            print(f"next release tag: v{v}")
            return
        print("MISMATCH:")
        for name, v in vers.items():
            print(f"  {name}: {v}")
        sys.exit(1)

    target = args[0]
    if target in ("patch", "minor", "major"):
        if len(unique) != 1:
            print("versions already mismatched, fix manually first:")
            for name, v in vers.items():
                print(f"  {name}: {v}")
            sys.exit(1)
        target = bump(unique.pop(), target)
    if not re.fullmatch(r"\d+\.\d+\.\d+", target):
        sys.exit(f"invalid version: {target}")

    print("before:")
    for name, v in vers.items():
        print(f"  {name}: {v}")
    write_versions(target)
    after = read_versions()
    print("after:")
    for name, v in after.items():
        print(f"  {name}: {v}")
    if set(after.values()) != {target}:
        sys.exit("write failed, still mismatched")
    print(f"\nrelease steps:")
    print(f'  git commit -am "release: v{target}" && git push')
    print(f"  git tag v{target} && git push origin v{target}   # triggers Release workflow")


if __name__ == "__main__":
    main()
