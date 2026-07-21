#!/usr/bin/env python3
"""报告导出 — Markdown 研报 → 自包含 HTML（图表 base64 内嵌，单文件可分享）。

reports/ 下的研报是 Markdown + PNG 图表，直接发给别人会丢图/丢格式。
本工具把报告转成**单文件 HTML**：本地图片内嵌 base64、保留表格与代码块、
中文排版样式，微信/邮件/浏览器直接打开。

用法（由 Skills 自动调用）：
    python3 tools/report_export.py reports/腾讯/腾讯-investment-research-20260720.md
    python3 tools/report_export.py <报告.md> --output /tmp/report.html

依赖：零外部依赖（Python >= 3.9 标准库）。
退出码：0=成功 / 1=失败 / 2=参数错误。

说明：支持研报常用的 Markdown 子集（标题/表格/列表/引用/代码块/粗斜体/图片/链接/分隔线）。
需要 PDF 时：浏览器打开 HTML → 打印 → 存为 PDF（保真度最高的零依赖路径）。
"""

import argparse
import base64
import html as html_mod
import mimetypes
import os
import re
import sys

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BAD_ARGS = 2

_CSS = """
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
       max-width: 860px; margin: 0 auto; padding: 32px 20px; color: #24292f;
       line-height: 1.75; font-size: 15px; }
h1, h2, h3, h4 { line-height: 1.35; margin: 1.4em 0 0.6em; }
h1 { font-size: 26px; border-bottom: 2px solid #d0d7de; padding-bottom: 8px; }
h2 { font-size: 21px; border-bottom: 1px solid #d8dee4; padding-bottom: 6px; }
h3 { font-size: 17px; }
table { border-collapse: collapse; margin: 14px 0; width: 100%; font-size: 14px; }
th, td { border: 1px solid #d0d7de; padding: 6px 12px; text-align: left; }
th { background: #f6f8fa; }
tr:nth-child(even) td { background: #fafbfc; }
blockquote { margin: 12px 0; padding: 4px 16px; color: #57606a;
             border-left: 4px solid #d0d7de; background: #f6f8fa; }
code { background: #f6f8fa; padding: 2px 5px; border-radius: 4px;
       font-family: "SF Mono", Menlo, monospace; font-size: 13px; }
pre { background: #f6f8fa; padding: 14px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
img { max-width: 100%; border-radius: 6px; margin: 8px 0; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 24px 0; }
a { color: #0969da; text-decoration: none; }
.footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid #d0d7de;
          color: #8b949e; font-size: 12px; }
@media print { body { max-width: none; } }
"""


def _embed_image(src: str, base_dir: str) -> str:
    """本地图片 → base64 data URI；外链/不存在时原样返回。"""
    if src.startswith(("http://", "https://", "data:")):
        return src
    path = src if os.path.isabs(src) else os.path.join(base_dir, src)
    if not os.path.exists(path):
        return src
    mime = mimetypes.guess_type(path)[0] or "image/png"
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except OSError:
        return src


def _inline(text: str, base_dir: str) -> str:
    """行内 Markdown：先转义 HTML，再处理图片/链接/粗斜体/行内代码。"""
    text = html_mod.escape(text, quote=False)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img alt="{m.group(1)}" src="{_embed_image(m.group(2), base_dir)}">',
        text,
    )
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<em>\1</em>", text)
    return text


def _table_row(line: str, base_dir: str, tag: str) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return "<tr>" + "".join(f"<{tag}>{_inline(c, base_dir)}</{tag}>" for c in cells) + "</tr>"


def md_to_html(md: str, base_dir: str) -> str:
    """研报 Markdown 子集 → HTML 片段（逐行状态机）。"""
    lines = md.splitlines()
    out, i = [], 0
    in_list = None  # None / "ul" / "ol"

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            close_list()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre><code>" + html_mod.escape("\n".join(block)) + "</code></pre>")
            i += 1
            continue
        # 表格（当前行含 | 且下一行是分隔行）
        if (
            "|" in stripped
            and i + 1 < len(lines)
            and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1])
        ):
            close_list()
            out.append("<table>")
            out.append("<thead>" + _table_row(stripped, base_dir, "th") + "</thead><tbody>")
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                out.append(_table_row(lines[i], base_dir, "td"))
                i += 1
            out.append("</tbody></table>")
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            close_list()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2), base_dir)}</h{n}>")
            i += 1
            continue
        # 分隔线
        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            close_list()
            out.append("<hr>")
            i += 1
            continue
        # 引用
        if stripped.startswith(">"):
            close_list()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(
                "<blockquote>"
                + "<br>".join(_inline(q, base_dir) for q in quote if q)
                + "</blockquote>"
            )
            continue
        # 列表
        m = re.match(r"^\s*[-*+]\s+(.*)", line)
        mo = re.match(r"^\s*\d+[.)]\s+(.*)", line)
        if m or mo:
            tag = "ul" if m else "ol"
            if in_list != tag:
                close_list()
                out.append(f"<{tag}>")
                in_list = tag
            out.append(f"<li>{_inline((m or mo).group(1), base_dir)}</li>")
            i += 1
            continue
        # 空行
        if not stripped:
            close_list()
            i += 1
            continue
        # 普通段落
        close_list()
        out.append(f"<p>{_inline(stripped, base_dir)}</p>")
        i += 1

    close_list()
    return "\n".join(out)


def export(md_path: str, output=None) -> str:
    if not os.path.exists(md_path):
        print(f"❌ 报告不存在: {md_path}")
        sys.exit(EXIT_BAD_ARGS)
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    base_dir = os.path.dirname(os.path.abspath(md_path))
    body = md_to_html(md, base_dir)

    title = os.path.splitext(os.path.basename(md_path))[0]
    m = re.search(r"^#\s+(.+)$", md, re.M)
    if m:
        title = m.group(1).strip()

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
<div class="footer">由 AI Berkshire 生成 · 方法论推演，不构成投资建议 · 源文件: {html_mod.escape(os.path.basename(md_path))}</div>
</body>
</html>
"""
    if output is None:
        output = os.path.splitext(md_path)[0] + ".html"
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html_doc)
    size_kb = os.path.getsize(output) / 1024
    print(f"  ✅ 已导出: {output}（{size_kb:.0f} KB，图片已内嵌，单文件可直接分享）")
    print("  需要 PDF: 浏览器打开 → ⌘P 打印 → 存为 PDF")
    return output


def main():
    parser = argparse.ArgumentParser(description="报告导出 — Markdown 研报转自包含 HTML")
    parser.add_argument("report", help="报告 Markdown 路径")
    parser.add_argument("--output", default=None, help="输出路径（默认同目录同名 .html）")
    args = parser.parse_args()
    export(args.report, args.output)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
