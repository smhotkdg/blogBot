#!/usr/bin/env python3
"""원고(post.md) + 그림 요청서(images.yaml) + 그림(images/)을 합쳐 복사용 완성본을 만든다.

사용법:
    python scripts/build.py                 # posts/ 아래 모든 글
    python scripts/build.py <slug> [...]    # 특정 글만

결과: dist/<slug>/index.html, post.txt, gpt_prompt.md
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import sys
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
DIST = ROOT / "dist"
IMAGE_GUIDE = ROOT / "docs" / "image-guide.md"

SLOT_RE = re.compile(r"\{\{img:([0-9A-Za-z_-]+)\}\}")
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# 붙여 넣기(네이버·티스토리 에디터)에서도 유지되도록 인라인 스타일을 쓴다.
ACCENT = "#F26B1D"
NAVY = "#1F2A44"
STYLE = {
    "h2": f"font-size:24px;font-weight:700;color:{NAVY};margin:36px 0 14px;"
          f"padding-left:12px;border-left:6px solid {ACCENT};line-height:1.5;",
    "h3": f"font-size:21px;font-weight:700;color:{NAVY};margin:28px 0 10px;line-height:1.5;",
    "p": "font-size:19px;line-height:1.9;margin:0 0 16px;color:#222;",
    "li": "font-size:19px;line-height:1.9;margin:0 0 10px;color:#222;",
    "ol": "margin:0 0 18px;padding-left:28px;",
    "ul": "margin:0 0 18px;padding-left:28px;",
    "strong": f"font-weight:700;color:{ACCENT};",
    "hr": "border:none;border-top:1px solid #ddd;margin:32px 0;",
    "tip": "background:#FFF4EC;border-radius:10px;padding:16px 18px;margin:20px 0;",
    "warn": "background:#F3F5FA;border-radius:10px;padding:16px 18px;margin:20px 0;",
    "slot": "font-size:17px;line-height:1.6;margin:22px 0;padding:14px;text-align:center;"
            "background:#EEE;border:2px dashed #999;border-radius:8px;color:#555;",
    "caption": "font-size:16px;line-height:1.6;margin:-8px 0 22px;text-align:center;color:#777;",
}


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


def find_image(post_dir: Path, item: dict) -> Path | None:
    img_dir = post_dir / "images"
    exact = img_dir / item["file"]
    if exact.exists():
        return exact
    stem = Path(item["file"]).stem
    for ext in IMG_EXTS:
        cand = img_dir / f"{stem}{ext}"
        if cand.exists():
            return cand
    return None


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def placeholder_uri(num: int, item: dict) -> str:
    w, h = (int(v) for v in str(item.get("size", "1600x1200")).split("x"))
    label = html.escape(f"그림 {num} — GPT 작업 대기 ({item['file']})")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="100%" height="100%" fill="#EEEEEE"/>'
        f'<rect x="12" y="12" width="{w-24}" height="{h-24}" fill="none" stroke="#999" '
        f'stroke-width="6" stroke-dasharray="24 16"/>'
        f'<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="sans-serif" font-size="{max(w // 22, 28)}" fill="#666">{label}</text></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def style_html(body_html: str) -> str:
    """markdown 결과에 인라인 스타일을 입힌다."""
    def bq(m: re.Match) -> str:
        inner = m.group(1)
        kind = "warn" if "⚠️" in inner else "tip"
        return f'<div style="{STYLE[kind]}">{inner}</div>'

    body_html = re.sub(r"<blockquote>\s*(.*?)\s*</blockquote>", bq, body_html, flags=re.S)
    for tag in ("h2", "h3", "p", "li", "ol", "ul", "strong"):
        body_html = re.sub(rf"<{tag}((?: [^>]*)?)>", rf'<{tag}\1 style="{STYLE[tag]}">', body_html)
    body_html = body_html.replace("<hr />", f'<hr style="{STYLE["hr"]}" />')
    # 상자 안 문단은 아래 여백 제거
    body_html = re.sub(
        r'(<div style="[^"]*">)\s*<p style="([^"]*)">',
        lambda m: f'{m.group(1)}<p style="{m.group(2)}margin:0;">',
        body_html,
    )
    return body_html


def to_plain(md_body: str, numbers: dict[str, int], items: dict[str, dict]) -> str:
    out = []
    for line in md_body.splitlines():
        m = SLOT_RE.fullmatch(line.strip())
        if m:
            sid = m.group(1)
            cap = items.get(sid, {}).get("caption") or ""
            out.append(f"[그림 {numbers.get(sid, '?')}]" + (f" {cap}" if cap else ""))
            continue
        line = re.sub(r"^#{2,3}\s*", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = line.replace("**", "")
        if line.strip() == "---":
            line = ""
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def gpt_prompt(meta: dict, spec: dict, post_md: str) -> str:
    guide = IMAGE_GUIDE.read_text(encoding="utf-8")
    lines = [
        f"# 그림 요청: {meta.get('title', '')}",
        "",
        "블로그 글에 들어갈 그림을 만들어 주세요. 아래 공통 스타일을 모든 그림에 적용하고,",
        "그림마다 하나씩 따로 만들어 주세요. 그림 안에는 '넣을 글자'에 적힌 글자만, 철자 그대로 넣어 주세요.",
        "파일 이름은 적힌 그대로 써 주세요.",
        "",
        "---",
        "",
        guide,
        "",
        "---",
        "",
        "## 그림 목록",
        "",
    ]
    for item in spec.get("images", []):
        lines += [
            f"### {item['file']} ({item['type']}, {item.get('size', '')})",
            "",
            "넣을 글자: " + " / ".join(f'"{t}"' for t in item.get("text", [])) if item.get("text") else "넣을 글자: 없음",
            "",
            str(item.get("prompt", "")).strip(),
            "",
        ]
    lines += ["---", "", "## 참고: 원고 전문", "", post_md.strip(), ""]
    return "\n".join(lines)


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc} — 복사용 완성본</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #F4F2EE; font-family: -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif; color: #222; }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 24px 16px 80px; }}
  .bar {{ position: sticky; top: 0; z-index: 10; background: #1F2A44; color: #fff; padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; }}
  .bar button {{ font-size: 15px; font-weight: 700; padding: 10px 14px; border: 0; border-radius: 8px; background: #F26B1D; color: #fff; cursor: pointer; }}
  .bar button.sub {{ background: #fff; color: #1F2A44; }}
  .toast {{ position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); background: #1F2A44; color: #fff; padding: 12px 20px; border-radius: 999px; font-size: 15px; opacity: 0; transition: opacity .2s; pointer-events: none; }}
  .toast.on {{ opacity: 1; }}
  .card {{ background: #fff; border-radius: 14px; padding: 22px; margin: 0 0 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .card h2.label {{ font-size: 14px; letter-spacing: .02em; color: #888; margin: 0 0 10px; font-weight: 700; }}
  .warnbox {{ background: #FFF4EC; border: 2px solid #F26B1D; }}
  .okbox {{ background: #EEF8F0; border: 2px solid #3A9B57; }}
  .title {{ font-size: 24px; font-weight: 800; line-height: 1.5; margin: 0; }}
  .tags {{ font-size: 16px; color: #555; margin: 0; word-break: keep-all; }}
  .figure {{ margin: 22px 0; text-align: center; }}
  .figure img {{ max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #eee; }}
  .figure .meta {{ font-size: 14px; color: #666; margin-top: 8px; line-height: 1.6; }}
  .figure a {{ display: inline-block; margin-top: 6px; font-size: 14px; font-weight: 700; color: #F26B1D; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }}
  .grid div {{ text-align: center; font-size: 13px; color: #555; }}
  .grid img {{ width: 100%; height: 120px; object-fit: contain; background: #fafafa; border-radius: 6px; border: 1px solid #eee; }}
  ul.check {{ margin: 6px 0 0; padding-left: 22px; line-height: 1.8; font-size: 15px; }}
  .hint {{ font-size: 14px; color: #666; line-height: 1.7; margin: 8px 0 0; }}
</style>
</head>
<body>
<div class="bar">
  <button onclick="copyText('title')">제목 복사</button>
  <button onclick="copyRich()">본문 서식 복사</button>
  <button class="sub" onclick="copyText('plain')">본문 텍스트만 복사</button>
  <button class="sub" onclick="copyText('tags')">태그 복사</button>
</div>
<div class="wrap">
  {status_card}
  <div class="card">
    <h2 class="label">제목</h2>
    <p class="title">{title_esc}</p>
  </div>
  <div class="card">
    <h2 class="label">태그</h2>
    <p class="tags">{tags_esc}</p>
  </div>
  <div class="card">
    <h2 class="label">그림 {img_total}장 — 번호 순서대로 저장해서 [그림 N] 자리에 넣으세요 ({img_ready}장 준비됨)</h2>
    <div class="grid">{grid}</div>
  </div>
  <div class="card">
    <h2 class="label">본문 미리보기 — 「본문 서식 복사」는 그림 자리를 [그림 N] 표시로 바꿔 복사합니다</h2>
    <div id="preview">{preview_html}</div>
  </div>
</div>
<div id="copy-src" style="position:absolute;left:-99999px;top:0;width:700px;" aria-hidden="true">{copy_html}</div>
<div class="toast" id="toast"></div>
<script>
const DATA = {data_json};
function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('on');
  clearTimeout(window.__t); window.__t = setTimeout(() => t.classList.remove('on'), 1800);
}}
function fallbackCopy(node) {{
  const sel = window.getSelection(); const range = document.createRange();
  range.selectNodeContents(node); sel.removeAllRanges(); sel.addRange(range);
  let ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
  sel.removeAllRanges(); return ok;
}}
async function copyText(key) {{
  const text = DATA[key];
  try {{ await navigator.clipboard.writeText(text); toast('복사했습니다'); return; }} catch (e) {{}}
  const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta);
  ta.select(); let ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
  ta.remove(); toast(ok ? '복사했습니다' : '복사에 실패했습니다. 직접 선택해 복사해 주세요');
}}
async function copyRich() {{
  const node = document.getElementById('copy-src');
  try {{
    await navigator.clipboard.write([new ClipboardItem({{
      'text/html': new Blob([node.innerHTML], {{type: 'text/html'}}),
      'text/plain': new Blob([DATA.plain], {{type: 'text/plain'}})
    }})]);
    toast('본문을 서식과 함께 복사했습니다'); return;
  }} catch (e) {{}}
  toast(fallbackCopy(node) ? '본문을 서식과 함께 복사했습니다' : '복사에 실패했습니다');
}}
</script>
</body>
</html>
"""


def build(post_dir: Path) -> dict:
    slug = post_dir.name
    meta, body = split_frontmatter((post_dir / "post.md").read_text(encoding="utf-8"))
    spec_path = post_dir / "images.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {"images": []}
    items = {str(i["id"]): i for i in spec.get("images", [])}

    # 원고에 나오는 순서대로 그림 번호를 매긴다
    order = [m.group(1) for m in SLOT_RE.finditer(body)]
    numbers = {sid: n for n, sid in enumerate(order, 1)}
    missing_spec = [sid for sid in order if sid not in items]

    rendered = markdown.markdown(body, extensions=["sane_lists"])
    styled = style_html(rendered)

    preview, copy = styled, styled
    grid, ready = [], 0
    for sid in order:
        n = numbers[sid]
        item = items.get(sid, {"file": f"{sid}.png", "caption": "", "alt": ""})
        path = find_image(post_dir, item)
        if path:
            ready += 1
            uri, fname = data_uri(path), f"{n:02d}_{path.name}"
        else:
            uri, fname = placeholder_uri(n, item), None
        cap = item.get("caption") or ""
        alt = item.get("alt") or ""
        dl = f'<a href="{uri}" download="{fname}">그림 {n} 내려받기</a>' if fname else ""
        fig = (
            f'<div class="figure"><img src="{uri}" alt="{html.escape(alt)}">'
            f'<div class="meta">[그림 {n}] {html.escape(cap)}<br>대체 텍스트: {html.escape(alt)}</div>{dl}</div>'
        )
        slot = f'<p style="{STYLE["slot"]}">[그림 {n}] 이 자리에 그림을 넣으세요</p>'
        if cap:
            slot += f'<p style="{STYLE["caption"]}">{html.escape(cap)}</p>'
        pattern = re.compile(rf'<p style="[^"]*">\s*\{{\{{img:{re.escape(sid)}\}}\}}\s*</p>')
        preview = pattern.sub(lambda _m, f=fig: f, preview, count=1)
        copy = pattern.sub(lambda _m, s=slot: s, copy, count=1)
        grid.append(
            f'<div><img src="{uri}" alt=""><br>그림 {n}<br>'
            + (f'<a href="{uri}" download="{fname}">내려받기</a>' if fname else "대기")
            + "</div>"
        )

    plain = to_plain(body, numbers, items)
    tags = meta.get("tags", [])
    tags_text = " ".join(f"#{t}" for t in tags)
    checked = bool(meta.get("checked"))
    verify = meta.get("verify", []) or []

    notes = []
    if not checked:
        li = "".join(f"<li>{html.escape(str(v))}</li>" for v in verify)
        notes.append(
            '<div class="card warnbox"><h2 class="label">발행 전 확인 필요</h2>'
            f'<p class="hint">기준: {html.escape(str(meta.get("basis", "")))}. 내 폰으로 아래 항목을 확인한 뒤 '
            "post.md의 <b>checked</b>를 true로 바꿔 주세요.</p>"
            f'<ul class="check">{li}</ul></div>'
        )
    if ready < len(order):
        notes.append(
            f'<div class="card warnbox"><h2 class="label">그림 {len(order) - ready}장 대기 중</h2>'
            f'<p class="hint">GPT에게 <b>dist/{slug}/gpt_prompt.md</b> 내용을 붙여 넣거나, '
            f"레포의 AGENTS.md를 따르게 하세요. 그림은 posts/{slug}/images/ 에 올리면 됩니다.</p></div>"
        )
    if missing_spec:
        notes.append(
            '<div class="card warnbox"><h2 class="label">요청서에 없는 그림 자리</h2>'
            f'<p class="hint">{", ".join(missing_spec)}</p></div>'
        )
    if checked and ready == len(order) and not missing_spec:
        notes.append('<div class="card okbox"><h2 class="label">발행 준비 완료</h2>'
                     '<p class="hint">확인과 그림이 모두 끝났습니다.</p></div>')

    out = DIST / slug
    out.mkdir(parents=True, exist_ok=True)
    title = str(meta.get("title", slug))
    page = PAGE.format(
        title_esc=html.escape(title),
        tags_esc=html.escape(tags_text),
        status_card="\n".join(notes),
        img_total=len(order),
        img_ready=ready,
        grid="".join(grid),
        preview_html=preview,
        copy_html=copy,
        data_json=json.dumps({"title": title, "tags": tags_text, "plain": plain}, ensure_ascii=False),
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "post.txt").write_text(f"{title}\n\n{plain}\n{tags_text}\n", encoding="utf-8")
    (out / "gpt_prompt.md").write_text(
        gpt_prompt(meta, spec, (post_dir / "post.md").read_text(encoding="utf-8")), encoding="utf-8"
    )
    return {"slug": slug, "images": f"{ready}/{len(order)}", "checked": checked, "missing_spec": missing_spec}


def main(argv: list[str]) -> int:
    targets = [POSTS / s for s in argv] if argv else sorted(p for p in POSTS.iterdir() if (p / "post.md").exists())
    for post_dir in targets:
        if not (post_dir / "post.md").exists():
            print(f"건너뜀: {post_dir.name} (post.md 없음)")
            continue
        r = build(post_dir)
        print(f"빌드: {r['slug']}  그림 {r['images']}  사람 확인 {'완료' if r['checked'] else '대기'}"
              + (f"  요청서 누락 {r['missing_spec']}" if r["missing_spec"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
