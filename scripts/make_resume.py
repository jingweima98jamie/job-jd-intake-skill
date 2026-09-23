#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规格驱动的简历生成器：spec.json -> HTML -> Chrome 无头导出单页 PDF

用法：
    python make_resume.py spec.json                    # 输出到 spec 里的 folder
    python make_resume.py spec.json --root ./output     # 相对 folder 解析到这个根目录
    python make_resume.py spec.json --no-pdf            # 只出 HTML

依赖：pypdf（页数校验）、Chrome 或 Chromium（转 PDF）

环境变量（都可选）：
    CHROME_PATH       浏览器可执行文件路径（自动探测失败时用）
    PYLIBS            已安装 pypdf 的目录（不想装进当前环境时用）
    RESUME_TEMPLATE   简历母版 HTML 路径（spec 里没写 template 时用）

设计要点：
  1. 排版、教育背景、照片全部从**你自己的母版 HTML**里提取——母版是唯一的排版事实源，
     换母版，所有生成的简历跟着变。本脚本不硬编码任何人的路径。
  2. 导出后校验页数，超过 1 页自动收紧 CSS 重导（最多 2 轮），仍超页直接报错，
     不会静默交付一份 2 页简历。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_TITLES = {
    "summary": "个人总结",
    "work": "工作经历",
    "projects": "项目经历",
    "skills": "专业技能",
    "education": "教育背景",
}

# 超页时的两轮收紧参数（只动 CSS，不改内容）
SHRINK_ROUNDS = [
    [
        (r"padding: 22px 32px;", "padding: 12px 28px;"),
        (r"font-size: 15px;(\s*)line-height: 1\.42;", r"font-size: 14px;\1line-height: 1.36;"),
        (r"margin-bottom: 14px;", "margin-bottom: 10px;"),
        (r"\.section \{ margin-bottom: 12px; \}", ".section { margin-bottom: 10px; }"),
        (r"\.entry \{ margin-bottom: 8px; \}", ".entry { margin-bottom: 7px; }"),
    ],
    [
        (r"padding: 12px 28px;", "padding: 10px 24px;"),
        (r"font-size: 14px;(\s*)line-height: 1\.36;", r"font-size: 13.5px;\1line-height: 1.3;"),
        (r"\.section \{ margin-bottom: 10px; \}", ".section { margin-bottom: 8px; }"),
        (r"\.entry \{ margin-bottom: 7px; \}", ".entry { margin-bottom: 6px; }"),
        (r"width: 92px;(\s*)height: 92px;", r"width: 84px;\1height: 84px;"),
        (r"\.entry-content li \{(\s*)margin-bottom: 2px;", r".entry-content li {\1margin-bottom: 1px;"),
    ],
]


def die(msg: str):
    sys.exit("[错误] " + msg)


def find_chrome() -> str:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "chrome.exe"):
        p = shutil.which(name)
        if p:
            return p
    die("找不到 Chrome/Chromium，请设置环境变量 CHROME_PATH 指向浏览器可执行文件")


def load_pypdf():
    try:
        import pypdf  # noqa
        return pypdf
    except ImportError:
        libs = os.environ.get("PYLIBS")
        if libs and Path(libs).is_dir():
            sys.path.insert(0, libs)
            try:
                import pypdf  # noqa
                return pypdf
            except ImportError:
                pass
    die("缺少 pypdf，请先安装：pip install pypdf（或用 PYLIBS 环境变量指向已安装目录）")


def extract_section(html: str, title: str):
    """按小节标题抽出一整段 <section>，不允许跨 section 边界匹配"""
    pat = re.compile(
        r'<section class="section">(?:(?!</section>).)*?'
        r'<h2 class="section-title">' + re.escape(title) + r"</h2>.*?</section>",
        re.S,
    )
    m = pat.search(html)
    return m.group(0) if m else None


def load_template(path: Path, edu_title: str):
    if not path.exists():
        die(f"母版 HTML 不存在：{path}\n请把 profile.md 里的「简历母版」路径写对，"
            f"或从 assets/resume-template.example.html 复制一份改成自己的")
    html = path.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", html, re.S)
    contact = re.findall(r"<p>(.*?)</p>", html, re.S)
    edu = extract_section(html, edu_title)
    if not css:
        die(f"母版里找不到 <style> 块：{path}")
    if not edu:
        die(f"母版里找不到「{edu_title}」小节：{path}")
    return {
        "css": css.group(1),
        "contact": contact[0].strip() if contact else "",
        "edu": edu,
        "raw": html,
    }


def resolve_photo(spec: dict, tpl: dict, spec_dir: Path):
    pf = spec.get("photo_file")
    if pf:
        p = Path(pf)
        if not p.is_absolute():
            p = spec_dir / p
        if not p.exists():
            die(f"photo_file 不存在：{p}")
        ext = p.suffix.lstrip(".").lower().replace("jpg", "jpeg") or "png"
        return f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()
    m = re.search(r'src="(data:image/[^"]+)"', tpl["raw"])
    if m:
        return m.group(1)
    if "{{PHOTO}}" in tpl["raw"]:
        print("[警告] 母版用的是 {{PHOTO}} 占位符且 spec 未提供 photo_file，照片位置会留空")
        return "{{PHOTO}}"
    print("[警告] 母版里没找到照片（data:image 或 {{PHOTO}}），简历将无照片")
    return ""


def build_html(tpl: dict, css: str, spec: dict, photo: str) -> str:
    T = {**DEFAULT_TITLES, **(spec.get("section_titles") or {})}

    def bullets(items):
        if not items:
            return ""
        return '<div class="entry-content"><ul>' + "".join(f"<li>{b}</li>" for b in items) + "</ul></div>"

    projects = ""
    for p in spec.get("projects", []):
        gh = ""
        if p.get("link"):
            gh = f'<p class="entry-subtitle">{p.get("link_text", "链接")}：<a href="{p["link"]}">{p["link"]}</a></p>'
        projects += f'''
                <div class="entry">
                    <div class="entry-header"><h3 class="entry-title">{p["title"]}</h3><div class="entry-meta">{p.get("meta", "")}</div></div>
                    {gh}
                    {bullets(p.get("bullets", []))}
                </div>'''

    work = spec["work"]
    work_html = f'''
                <div class="entry">
                    <div class="entry-header"><h3 class="entry-title">{work.get("company", "")} ｜ {work["title"]}</h3><div class="entry-meta">{work.get("meta", "")}</div></div>
                    {f'<p class="entry-subtitle">{work["sub"]}</p>' if work.get("sub") else ""}
                    {bullets(work.get("bullets", []))}
                </div>'''

    skills = "".join(f"<p>{s}</p>" for s in spec.get("skills", []))
    tagline = spec.get("tagline", "")
    header_extra = f"<p>{tagline}</p>" if tagline else ""
    photo_html = f'<div class="photo-wrapper"><img class="photo" src="{photo}" alt="photo"></div>' if photo else ""

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{spec.get("name", "")} · {spec["intent"]}</title>
    <style>{css}</style>
</head>
<body>

    <header class="resume-header">
        <div class="header-info">
            <h1>{spec.get("name", "")}<span>求职意向：{spec["intent"]}</span></h1>
            <p>{spec.get("contact") or tpl["contact"]}</p>
            {header_extra}
        </div>
        {photo_html}
    </header>

    <main class="resume-body">

        {tpl["edu"]}

        <section class="section">
            <div class="section-title-wrapper"><div class="title-bar"></div><h2 class="section-title">{T["summary"]}</h2></div>
            <div class="section-content other-info"><p>{spec["summary"]}</p></div>
        </section>

        <section class="section">
            <div class="section-title-wrapper"><div class="title-bar"></div><h2 class="section-title">{T["work"]}</h2></div>
            <div class="section-content">{work_html}</div>
        </section>

        <section class="section">
            <div class="section-title-wrapper"><div class="title-bar"></div><h2 class="section-title">{T["projects"]}</h2></div>
            <div class="section-content">{projects}</div>
        </section>

        <section class="section">
            <div class="section-title-wrapper"><div class="title-bar"></div><h2 class="section-title">{T["skills"]}</h2></div>
            <div class="section-content other-info">{skills}</div>
        </section>

    </main>

</body>
</html>'''


def shrink(css: str, level: int) -> str:
    for pat, repl in SHRINK_ROUNDS[level]:
        css = re.sub(pat, repl, css)
    return css


def to_pdf(chrome: str, html_path: Path, pdf_path: Path, pypdf) -> int:
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         "--print-to-pdf=" + str(pdf_path.resolve()), str(html_path.resolve())],
        capture_output=True, timeout=180,
    )
    if not pdf_path.exists() or pdf_path.stat().st_size < 8000:
        die(f"PDF 导出失败（文件缺失或过小）：{pdf_path}\n常见原因：Chrome 路径不对、母版引用了外部资源")
    return pypdf.PdfReader(str(pdf_path)).get_num_pages()


def main():
    ap = argparse.ArgumentParser(description="规格驱动的简历生成器")
    ap.add_argument("spec", help="spec.json 路径")
    ap.add_argument("--root", help="输出根目录（spec.folder 为相对路径时按其解析）")
    ap.add_argument("--no-pdf", action="store_true", help="只生成 HTML")
    args = ap.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec_dir = spec_path.parent

    for field in ("filename", "intent", "summary", "work"):
        if field not in spec:
            die(f"spec 缺少必填字段：{field}")

    template = spec.get("template") or os.environ.get("RESUME_TEMPLATE")
    if not template:
        die("没有指定简历母版：请在 spec 里写 template，或设 RESUME_TEMPLATE 环境变量，"
            "或直接复制 assets/resume-template.example.html 改成自己的")
    tpl_path = Path(template)
    if not tpl_path.is_absolute():
        tpl_path = spec_dir / tpl_path
    edu_title = (spec.get("section_titles") or {}).get("education", DEFAULT_TITLES["education"])
    tpl = load_template(tpl_path, edu_title)
    photo = resolve_photo(spec, tpl, spec_dir)

    folder = Path(spec["folder"])
    if not folder.is_absolute():
        base = Path(args.root).resolve() if args.root else Path.cwd()
        folder = base / folder
    folder.mkdir(parents=True, exist_ok=True)

    html_path = folder / (spec["filename"] + ".html")
    pdf_path = folder / (spec["filename"] + ".pdf")

    pypdf = None if args.no_pdf else load_pypdf()
    chrome = None if args.no_pdf else find_chrome()

    steps = []
    for level in range(len(SHRINK_ROUNDS) + 1):
        css = tpl["css"]
        for i in range(level):
            css = shrink(css, i)
        html_path.write_text(build_html(tpl, css, spec, photo), encoding="utf-8")
        if args.no_pdf:
            steps.append({"level": level, "html": str(html_path), "pages": None})
            break
        pages = to_pdf(chrome, html_path, pdf_path, pypdf)
        steps.append({"level": level, "html": str(html_path), "pdf": str(pdf_path), "pages": pages})
        if pages == 1:
            break
    else:
        die(f"压到单页失败（已收紧 2 轮 CSS），需要删减内容：{html_path}")

    print(json.dumps({"ok": True, "filename": spec["filename"], "steps": steps}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
