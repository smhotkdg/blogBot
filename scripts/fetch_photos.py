#!/usr/bin/env python3
"""images.yaml 의 type: photo 항목에 적힌 후보 사진을 내려받는다.

저장 위치: posts/<글>/photos/<id>-<후보번호>.jpg  (이미 있으면 건너뜀)

사용법:
    python scripts/fetch_photos.py            # 모든 글
    python scripts/fetch_photos.py <slug>     # 특정 글
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
UA = "Mozilla/5.0 (blogBot photo fetcher; +https://github.com/smhotkdg/blogBot)"


def candidate_url(c: dict) -> str:
    if c.get("url"):
        return c["url"]
    if c.get("source") == "pexels":
        pid = c["id"]
        return f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=1600"
    if c.get("source") == "unsplash":
        return f"https://unsplash.com/photos/{c['id']}/download?force=true&w=1600"
    raise ValueError(f"내려받을 주소를 알 수 없음: {c}")


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 5000:
        raise ValueError(f"파일이 너무 작음 ({len(data)} bytes)")
    dest.write_bytes(data)


def main(argv: list[str]) -> int:
    dirs = [POSTS / s for s in argv] if argv else sorted(p for p in POSTS.iterdir() if p.is_dir())
    failed = 0
    for post_dir in dirs:
        spec_path = post_dir / "images.yaml"
        if not spec_path.exists():
            continue
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        for item in spec.get("images", []):
            if item.get("type") != "photo":
                continue
            out_dir = post_dir / "photos"
            out_dir.mkdir(exist_ok=True)
            for n, c in enumerate(item.get("candidates", []), 1):
                dest = out_dir / f"{item['id']}-{n}.jpg"
                if dest.exists():
                    continue
                try:
                    fetch(candidate_url(c), dest)
                    print(f"받음: {post_dir.name}/{dest.name}")
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    print(f"실패: {post_dir.name}/{dest.name} — {e}")
    if failed:
        print(f"{failed}개 실패 (나머지는 계속 진행)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
