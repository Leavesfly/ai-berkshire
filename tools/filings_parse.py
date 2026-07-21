#!/usr/bin/env python3
"""财报原文语义管道 — 章节抽取 + 跨年对比（filings_fetch.py 的下游）。

把"下载了原文"变成"消化了原文"：从 10-K/年报中切出关键章节
（风险因素 / MD&A / 业务描述等），并支持两份年报同章节的跨年 diff
（新增/删除句子、篇幅与措辞变化）——这正是 thesis-drift 措辞漂移检测、
earnings-review 精读、management-deep-dive 管理层言行对照最需要的输入。

支持格式：
  - 美股 SEC EDGAR：HTML/HTM（含 inline XBRL）与 TXT，零依赖直接解析
  - A股巨潮 / 港股披露易：PDF，需可选依赖 pypdf（pip install pypdf）；
    缺失时退出码 1，降级提示用 pdf 解析能力先转文本再用 text 模式

用法（由 Skills 自动调用）：
    python3 tools/filings_parse.py text data/filings/usaapl/20251101-10-K.htm       # 全文转纯文本
    python3 tools/filings_parse.py sections data/filings/usaapl/20251101-10-K.htm   # 列出可抽取章节
    python3 tools/filings_parse.py extract data/filings/usaapl/20251101-10-K.htm --section risk
    python3 tools/filings_parse.py extract data/filings/600519/20260325-annual.pdf --section mda
    python3 tools/filings_parse.py diff <去年文件> <今年文件> --section risk         # 跨年对比

--section 取值（模糊匹配）：
  risk / item1a / 风险    → 风险因素（10-K Item 1A / A股"风险"相关章节）
  mda / item7 / 讨论      → 管理层讨论与分析（Item 7 / 经营情况讨论与分析）
  business / item1 / 业务 → 业务描述（Item 1 / 公司业务概要）
  legal / item3 / 诉讼    → 法律诉讼（Item 3 / 重要事项-诉讼）

依赖：零外部依赖（PDF 需可选 pypdf）。
退出码：0=成功 / 1=解析失败或缺可选依赖 / 2=参数错误。
"""

import argparse
import difflib
import html as html_mod
import os
import re
import sys

from utils import EXIT_BAD_ARGS, EXIT_FAIL, EXIT_OK

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 文件 → 纯文本
# ---------------------------------------------------------------------------


def _html_to_text(raw: str) -> str:
    """HTML/inline-XBRL → 纯文本：去脚本样式、去标签、解实体、归一空白。"""
    raw = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw)
    # 块级标签换行，保住段落边界，便于后续切句
    raw = re.sub(r"(?i)</?(p|div|tr|br|h[1-6]|li|table)[^>]*>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html_mod.unescape(raw)
    raw = raw.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _pdf_to_text(path: str) -> str:
    """PDF → 纯文本（可选依赖 pypdf；缺失时抛 ImportError 由上层降级）。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # 老环境兼容
        except ImportError:
            raise ImportError(
                "PDF 解析需要 pypdf: pip install pypdf（或 pip install .[filings]）\n"
                "   降级路径：用 pdf 解析能力将 PDF 转为 .txt 后，对 .txt 使用本工具"
            )
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def load_text(path: str) -> str:
    """任意披露文件 → 纯文本（按扩展名分派）。"""
    if not os.path.exists(path):
        raise ValueError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _pdf_to_text(path)
    with open(path, "rb") as f:
        raw_bytes = f.read()
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = raw_bytes.decode("gbk", errors="replace")
    if ext in (".htm", ".html") or raw.lstrip()[:200].lower().find("<") >= 0 and "</" in raw[:5000]:
        return _html_to_text(raw)
    return raw


# ---------------------------------------------------------------------------
# 章节切分
# ---------------------------------------------------------------------------

# 规范章节名 → (10-K Item 编号, 中文年报标题关键词, 别名)
_SECTION_MAP = {
    "risk": ("1A", ("风险", "可能面对的风险"), ("item1a", "风险", "risk")),
    "mda": (
        "7",
        ("经营情况讨论与分析", "管理层讨论与分析", "董事会报告", "管理层讨论"),
        ("item7", "讨论", "mda", "md&a"),
    ),
    "business": (
        "1",
        ("公司业务概要", "公司简介和主要财务指标", "业务概要", "主席报告"),
        ("item1", "业务", "business"),
    ),
    "legal": ("3", ("重要事项", "重大诉讼"), ("item3", "诉讼", "legal")),
}


def _canon_section(name: str) -> str:
    n = name.strip().lower().replace(" ", "")
    for canon, (_item, _cn, aliases) in _SECTION_MAP.items():
        if n == canon or n in aliases:
            return canon
    raise ValueError(f"--section 仅支持: {', '.join(_SECTION_MAP)}（或其别名，见 --help）")


def _find_us_items(text: str) -> list:
    """10-K 文本中定位各 Item 起始位置：返回 [(pos, item编号)]，已去目录页。"""
    hits = []
    for m in re.finditer(r"(?im)^\s*item\s+(\d{1,2}[A-C]?)\s*[.:—–-]", text):
        hits.append((m.start(), m.group(1).upper()))
    if not hits:
        return []
    # 目录页会把所有 Item 密集列一遍——若某编号出现≥2次，丢弃第一次（目录）
    from collections import Counter

    counts = Counter(item for _p, item in hits)
    seen, result = set(), []
    for pos, item in hits:
        if counts[item] >= 2 and item not in seen:
            seen.add(item)  # 第一次出现视为目录条目，跳过
            continue
        result.append((pos, item))
    return result


def _find_cn_sections(text: str) -> list:
    """中文年报定位"第X节 标题"：返回 [(pos, 标题)]。"""
    hits = []
    for m in re.finditer(r"第\s*[一二三四五六七八九十]{1,3}\s*[节章]\s*([^\n]{2,30})", text):
        title = m.group(1).strip()
        hits.append((m.start(), title))
    # 同标题多次出现（目录+正文）时保留最后一次（正文）
    dedup = {}
    for pos, title in hits:
        dedup[title] = pos
    return sorted((pos, title) for title, pos in dedup.items())


def split_sections(text: str) -> list:
    """返回 [(标识, 标题行, 正文)]；自动识别美式 Item / 中文"第X节"。"""
    us = _find_us_items(text)
    if len(us) >= 3:
        out = []
        for i, (pos, item) in enumerate(us):
            end = us[i + 1][0] if i + 1 < len(us) else len(text)
            body = text[pos:end].strip()
            title = body.splitlines()[0][:80] if body else f"Item {item}"
            out.append((f"item{item.lower()}", title, body))
        return out
    cn = _find_cn_sections(text)
    if len(cn) >= 3:
        out = []
        for i, (pos, title) in enumerate(cn):
            end = cn[i + 1][0] if i + 1 < len(cn) else len(text)
            out.append((title, title, text[pos:end].strip()))
        return out
    return []


def pick_section(text: str, section: str):
    """按规范章节名从全文取出目标章节正文；找不到返回 None。"""
    canon = _canon_section(section)
    item_no, cn_keys, _aliases = _SECTION_MAP[canon]
    sections = split_sections(text)
    # 美式：item 编号精确匹配
    for ident, _title, body in sections:
        if ident == f"item{item_no.lower()}":
            return body
    # 中文：标题关键词匹配（按 _SECTION_MAP 中优先级）
    for key in cn_keys:
        for ident, _title, body in sections:
            if key in ident:
                return body
    return None


# ---------------------------------------------------------------------------
# 跨年 diff
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list:
    """粗粒度切句（中英文通用），过滤短碎片与纯数字表格行。"""
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[。；;.!?！？])\s*", text)
    out = []
    for p in parts:
        p = p.strip()
        if len(p) < 12:
            continue
        if len(re.sub(r"[\d\s,.%()\-—]", "", p)) < 6:  # 基本全是数字的表格碎片
            continue
        out.append(p)
    return out


def diff_sections(old_text: str, new_text: str, top_n: int = 12):
    """两版同章节对比：返回 (篇幅变化%, 新增句子, 删除句子, 相似度)。"""
    old_s, new_s = _sentences(old_text), _sentences(new_text)
    sm = difflib.SequenceMatcher(a=old_s, b=new_s, autojunk=False)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(new_s[j1:j2])
        if tag in ("delete", "replace"):
            removed.extend(old_s[i1:i2])
    len_change = (len(new_text) / len(old_text) - 1) * 100 if old_text else 0.0
    return len_change, added[:top_n], removed[:top_n], sm.ratio()


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------


def cmd_text(path: str, output=None):
    text = load_text(path)
    if len(text) < 200:
        print(f"❌ 提取文本过短（{len(text)} 字符），文件可能是扫描件或加密 PDF")
        print("   降级路径：用 pdf 解析能力（OCR）提取正文后再用本工具")
        sys.exit(EXIT_FAIL)
    if output:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  ✅ 纯文本已保存: {output}（{len(text):,} 字符）")
    else:
        print(text)


def cmd_sections(path: str):
    text = load_text(path)
    sections = split_sections(text)
    print("=" * 66)
    print(f"章节结构: {os.path.basename(path)}（全文 {len(text):,} 字符）")
    print("=" * 66)
    if not sections:
        print("  ⚠️ 未识别出章节结构（非标准 10-K/年报排版）")
        print("   可用 text 模式导出全文后人工定位")
        sys.exit(EXIT_FAIL)
    for ident, title, body in sections:
        print(f"  [{ident:12s}] {title[:56]}  ({len(body):,} 字符)")
    print()
    print("  抽取: python3 tools/filings_parse.py extract <文件> --section risk|mda|business|legal")


def cmd_extract(path: str, section: str, output=None):
    text = load_text(path)
    body = pick_section(text, section)
    if not body:
        print(f"❌ 未在文件中定位到章节 [{section}]（用 sections 命令查看实际结构）")
        sys.exit(EXIT_FAIL)
    if output is None:
        stem = os.path.splitext(path)[0]
        output = f"{stem}-{_canon_section(section)}.txt"
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"  ✅ 章节 [{_canon_section(section)}] 已保存: {output}（{len(body):,} 字符）")
    print(f"     开头预览: {body[:120]}...")


def cmd_diff(old_path: str, new_path: str, section: str, top_n: int):
    old_body = pick_section(load_text(old_path), section)
    new_body = pick_section(load_text(new_path), section)
    missing = [p for p, b in ((old_path, old_body), (new_path, new_body)) if not b]
    if missing:
        print(f"❌ 未定位到章节 [{section}]: {', '.join(os.path.basename(m) for m in missing)}")
        sys.exit(EXIT_FAIL)

    len_change, added, removed, ratio = diff_sections(old_body, new_body, top_n)
    canon = _canon_section(section)
    print("=" * 70)
    print(f"跨年章节对比 [{canon}]: {os.path.basename(old_path)} → {os.path.basename(new_path)}")
    print("=" * 70)
    print(f"  篇幅变化: {len(old_body):,} → {len(new_body):,} 字符（{len_change:+.1f}%）")
    print(f"  文本相似度: {ratio * 100:.0f}%（越低说明措辞/内容改动越大）")
    if canon == "risk" and len_change > 15:
        print("  ⚠️ 风险因素篇幅显著增加（>15%）——通常意味着新增实质性风险，逐条核对新增内容")
    print()
    if added:
        print(f"  🆕 新增/改写内容（前 {len(added)} 条）：")
        for s in added:
            print(f"     + {s[:110]}")
    else:
        print("  🆕 无新增内容")
    print()
    if removed:
        print(f"  🗑️ 删除/被改写内容（前 {len(removed)} 条）：")
        for s in removed:
            print(f"     - {s[:110]}")
    else:
        print("  🗑️ 无删除内容")
    print()
    print("  解读提示：新增风险≠公司变差（可能是律师式披露），但「删掉曾强调的优势」")
    print("  或「悄悄改口径」是 thesis-drift 的强信号，应回到论文红线逐条核对")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="财报原文语义管道 — 章节抽取 + 跨年对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s text data/filings/usaapl/20251101-10-K.htm --output /tmp/aapl.txt
  %(prog)s sections data/filings/usaapl/20251101-10-K.htm
  %(prog)s extract data/filings/usaapl/20251101-10-K.htm --section risk
  %(prog)s diff data/filings/usaapl/2024-10-K.htm data/filings/usaapl/2025-10-K.htm --section risk
        """,
    )
    sub = parser.add_subparsers(dest="command")

    p_text = sub.add_parser("text", help="披露文件转纯文本")
    p_text.add_argument("file")
    p_text.add_argument("--output", default=None, help="保存路径（缺省打印到 stdout）")

    p_sec = sub.add_parser("sections", help="列出可抽取章节")
    p_sec.add_argument("file")

    p_ext = sub.add_parser("extract", help="抽取单个章节到 .txt")
    p_ext.add_argument("file")
    p_ext.add_argument("--section", required=True, help="risk / mda / business / legal（或别名）")
    p_ext.add_argument("--output", default=None, help="保存路径（默认同目录 <文件名>-<章节>.txt）")

    p_diff = sub.add_parser("diff", help="两份年报同章节跨年对比")
    p_diff.add_argument("old_file", help="上一期文件")
    p_diff.add_argument("new_file", help="本期文件")
    p_diff.add_argument("--section", required=True, help="risk / mda / business / legal")
    p_diff.add_argument("--top", type=int, default=12, help="新增/删除各展示条数（默认12）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    try:
        if args.command == "text":
            cmd_text(args.file, args.output)
        elif args.command == "sections":
            cmd_sections(args.file)
        elif args.command == "extract":
            cmd_extract(args.file, args.section, args.output)
        else:
            cmd_diff(args.old_file, args.new_file, args.section, args.top)
        sys.exit(EXIT_OK)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_BAD_ARGS)
    except ImportError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
