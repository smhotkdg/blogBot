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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_photos import candidate_filename  # noqa: E402

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


SOURCE_NAMES = {"pexels": "Pexels", "unsplash": "Unsplash", "pixabay": "Pixabay"}


def photo_choice(post_dir: Path, item: dict) -> tuple[Path | None, dict | None, bool]:
    """사진 칸: (파일, 고른 후보, 직접 골랐는지). images/ 에 같은 이름 파일이 있으면 그것을 우선한다."""
    manual = find_image(post_dir, item)
    if manual:
        return manual, None, True
    cands = item.get("candidates", []) or []
    pick = item.get("pick")
    order = [int(pick)] if pick else list(range(1, len(cands) + 1))
    for n in order:
        if not 1 <= n <= len(cands):
            continue
        f = post_dir / "photos" / candidate_filename(item, cands[n - 1])
        if f.exists():
            return f, cands[n - 1], bool(pick)
    return None, None, False


def credit_text(c: dict | None) -> str:
    if not c:
        return ""
    src = SOURCE_NAMES.get(c.get("source", ""), c.get("source", ""))
    author = str(c.get("author") or "").strip()
    return f"사진: {author} / {src}" if author else f"사진: {src}"


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def placeholder_uri(num: int, item: dict) -> str:
    w, h = (int(v) for v in str(item.get("size", "1600x1200")).split("x"))
    who = {"photo": "사진 내려받기 대기", "capture": "직접 캡처 대기"}.get(item.get("type"), "GPT 작업 대기")
    label = html.escape(f"그림 {num} — {who} ({item['file']})")
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


def to_plain(md_body: str, numbers: dict[str, int], caps: dict[str, str]) -> str:
    out = []
    for line in md_body.splitlines():
        m = SLOT_RE.fullmatch(line.strip())
        if m:
            sid = m.group(1)
            cap = caps.get(sid, "")
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


REPO_RAW = "https://raw.githubusercontent.com/smhotkdg/blogBot/main"
RATIO = {"1080x1080": "정사각형 1:1", "1600x1200": "가로 4:3", "1600x1067": "가로 3:2", "1080x1920": "세로 9:16"}
KIND = {"thumbnail": "대표 이미지", "illustration": "설명 그림", "infographic": "정리 도표",
        "screen-guide": "화면 안내 그림", "photo-ai": "실사풍 사진"}


def gpt_request(slug: str, meta: dict, spec: dict, done: set[str]) -> str:
    """ChatGPT에 그대로 붙여 넣을 요청 문구. 이미 있는 그림은 목록에서 뺀다."""
    todo = [i for i in spec.get("images", [])
            if i.get("type") not in ("photo", "capture") and i["file"] not in done]
    if not todo:
        return "이 글의 GPT 그림은 모두 준비되었습니다."
    lines = [
        f"블로그 글 「{meta.get('title', '')}」에 들어갈 그림을 만들어 줘.",
        "",
        f"요청서(공통 스타일 + 그림별 설명): {REPO_RAW}/dist/{slug}/gpt_prompt.md",
        "",
        "규칙",
        "- 요청서의 '공통' 스타일을 모든 그림에 적용해.",
        "- 한 번에 한 장씩, 아래 순서대로 만들어. 한 장을 만들면 파일 이름을 알려 주고, 내가 \"다음\"이라고 하면 다음 그림을 만들어.",
        "- 그림 안 글자는 요청서의 '넣을 글자'만, 철자 그대로 넣어. 다른 글자는 넣지 마.",
        "- 비율은 아래 적힌 대로 맞춰.",
        "- 실사풍 사진은 진짜 사진처럼 보이게, 얼굴은 보이지 않게, 휴대폰에 로고 없이.",
        "- 실제 회사·기관 로고, 실존 인물, 실제 앱 화면은 그리지 마.",
        "- 링크가 열리지 않으면 바로 말해 줘. 요청서 내용을 붙여 넣을게.",
        "",
        f"만들 그림 ({len(todo)}장)",
    ]
    for n, i in enumerate(todo, 1):
        ratio = RATIO.get(str(i.get("size", "")), str(i.get("size", "")))
        txt = " / ".join(f'"{t}"' for t in i.get("text", []) or [])
        lines.append(f"{n}. {i['file']} — {KIND.get(i['type'], i['type'])}, {ratio}"
                     + (f", 넣을 글자: {txt}" if txt else ", 글자 없음"))
        lines.append(f"   {str(i.get('alt', '')).strip()}")
    lines += ["", "첫 번째 그림부터 시작해 줘."]
    return "\n".join(lines)


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
        if item.get("type") in ("photo", "capture"):
            continue  # 실사 사진·실제 화면 캡처는 GPT 담당이 아님
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
  <button class="sub" onclick="copyText('gpt')">GPT 요청 문구 복사</button>
</div>
<div class="wrap">
  {status_card}
  <div class="card">
    <h2 class="label">GPT 요청 문구 — 「GPT 요청 문구 복사」를 눌러 ChatGPT에 붙여 넣으세요</h2>
    <pre style="white-space:pre-wrap;font-size:14px;line-height:1.7;background:#F7F7F7;border-radius:8px;padding:14px;margin:0;">{gpt_esc}</pre>
  </div>
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
    photo_cards = []
    caps: dict[str, str] = {}
    capture_items = []
    gpt_waiting = 0
    for sid in order:
        n = numbers[sid]
        item = items.get(sid, {"file": f"{sid}.png", "caption": "", "alt": ""})
        credit = ""
        if item.get("type") == "photo":
            path, cand, picked = photo_choice(post_dir, item)
            credit = credit_text(cand)
            if not picked:
                thumbs = []
                for k, c in enumerate(item.get("candidates", []) or [], 1):
                    f = post_dir / "photos" / candidate_filename(item, c)
                    src = data_uri(f) if f.exists() else placeholder_uri(n, item)
                    thumbs.append(f'<div><img src="{src}" alt=""><br>후보 {k} · '
                                  f'<a href="{html.escape(c.get("page", ""))}">{html.escape(str(c.get("author", "")))}</a></div>')
                photo_cards.append(f'<p class="hint">그림 {n} ({sid}) — 마음에 드는 후보 번호를 images.yaml의 '
                                   f'<b>pick</b>에 적어 주세요. 지금은 {"1번이 임시로" if path else "아무것도 안"} 들어가 있습니다.</p>'
                                   f'<div class="grid">{"".join(thumbs)}</div>')
        else:
            path = find_image(post_dir, item)
            if item.get("type") == "photo-ai":
                credit = "AI 생성 이미지"
        if path:
            ready += 1
            uri, fname = data_uri(path), f"{n:02d}_{path.name}"
        else:
            uri, fname = placeholder_uri(n, item), None
        cap = item.get("caption") or ""
        alt = item.get("alt") or ""
        cap_full = f"{cap} ({credit})" if cap and credit else (cap or credit)
        caps[sid] = cap_full
        if not path and item.get("type") == "capture":
            mask = ", ".join(item.get("mask") or []) or "없음"
            capture_items.append(
                f"<li><b>그림 {n} · {html.escape(item['file'])}</b> — {html.escape(str(item.get('guide', '')).strip())}"
                f"<br><span style=\"color:#C0392B\">가릴 것: {html.escape(mask)}</span></li>")
        if not path and item.get("type") not in ("photo", "capture"):
            gpt_waiting += 1
        dl = f'<a href="{uri}" download="{fname}">그림 {n} 내려받기</a>' if fname else ""
        fig = (
            f'<div class="figure"><img src="{uri}" alt="{html.escape(alt)}">'
            f'<div class="meta">[그림 {n}] {html.escape(cap_full)}<br>대체 텍스트: {html.escape(alt)}</div>{dl}</div>'
        )
        slot = f'<p style="{STYLE["slot"]}">[그림 {n}] 이 자리에 그림을 넣으세요</p>'
        if cap_full:
            slot += f'<p style="{STYLE["caption"]}">{html.escape(cap_full)}</p>'
        pattern = re.compile(rf'<p style="[^"]*">\s*\{{\{{img:{re.escape(sid)}\}}\}}\s*</p>')
        preview = pattern.sub(lambda _m, f=fig: f, preview, count=1)
        copy = pattern.sub(lambda _m, s=slot: s, copy, count=1)
        grid.append(
            f'<div><img src="{uri}" alt=""><br>그림 {n}<br>'
            + (f'<a href="{uri}" download="{fname}">내려받기</a>' if fname else "대기")
            + "</div>"
        )

    plain = to_plain(body, numbers, caps)
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
    if capture_items:
        notes.append(
            f'<div class="card warnbox"><h2 class="label">직접 캡처할 화면 {len(capture_items)}장</h2>'
            f'<p class="hint">본인 휴대폰으로 캡처해서 개인정보를 가린 뒤 posts/{slug}/images/ 에 아래 파일 이름으로 올려 주세요.</p>'
            f'<ul class="check">{"".join(capture_items)}</ul></div>')
    if photo_cards:
        notes.append('<div class="card warnbox"><h2 class="label">실사 사진 고르기</h2>'
                     + "".join(photo_cards) + "</div>")
    if gpt_waiting:
        notes.append(
            f'<div class="card warnbox"><h2 class="label">GPT 그림 {gpt_waiting}장 대기 중</h2>'
            f'<p class="hint">GPT에게 <b>dist/{slug}/gpt_prompt.md</b> 내용을 붙여 넣거나, '
            f"레포의 AGENTS.md를 따르게 하세요. 그림은 posts/{slug}/images/ 에 올리면 됩니다.</p></div>"
        )
    if missing_spec:
        notes.append(
            '<div class="card warnbox"><h2 class="label">요청서에 없는 그림 자리</h2>'
            f'<p class="hint">{", ".join(missing_spec)}</p></div>'
        )
    if checked and ready == len(order) and not missing_spec and not photo_cards and not capture_items:
        notes.append('<div class="card okbox"><h2 class="label">발행 준비 완료</h2>'
                     '<p class="hint">확인과 그림이 모두 끝났습니다.</p></div>')

    out = DIST / slug
    out.mkdir(parents=True, exist_ok=True)
    title = str(meta.get("title", slug))
    done_files = {i["file"] for i in spec.get("images", []) if find_image(post_dir, i)}
    gpt_req = gpt_request(slug, meta, spec, done_files)
    page = PAGE.format(
        title_esc=html.escape(title),
        tags_esc=html.escape(tags_text),
        status_card="\n".join(notes),
        img_total=len(order),
        img_ready=ready,
        grid="".join(grid),
        preview_html=preview,
        copy_html=copy,
        gpt_esc=html.escape(gpt_req),
        data_json=json.dumps({"title": title, "tags": tags_text, "plain": plain, "gpt": gpt_req}, ensure_ascii=False),
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "post.txt").write_text(f"{title}\n\n{plain}\n{tags_text}\n", encoding="utf-8")
    (out / "gpt_request.txt").write_text(gpt_req + "\n", encoding="utf-8")
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
