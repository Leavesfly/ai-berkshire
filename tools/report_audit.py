#!/usr/bin/env python3
"""Report Audit Tool for AI Berkshire.

数据抽检工具：从研究报告中抽取15%的财务数据点，与可靠信源比对，
通过则准出，不通过则打回并说明原因。

Zero external dependencies — uses only Python stdlib.
Requires Python >= 3.9.

工作流程（三步）：
  Step 1 — 提取数据点，随机抽样15%：
    python3 tools/report_audit.py extract --report reports/xxx.md

  Step 2 — Claude 对抽检清单中的每个数据点，从可靠信源（macrotrends/
            stockanalysis/aastocks/eastmoney）取数，填入 fetched_value

  Step 3 — 输入核验结果，输出准出/打回判决：
    python3 tools/report_audit.py verdict --results '[...]'

  一步完成（仅提取+打印抽检清单，不做网络验证）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run
"""

import argparse
import json
import math
import os
import re
import sys
from random import Random

# 终端 ANSI 颜色（用于判决结果高亮显示）；非 TTY（管道/重定向）时自动禁用，避免转义码污染日志
_USE_COLOR = sys.stdout.isatty()
BOLD = "\033[1m" if _USE_COLOR else ""
RED = "\033[91m" if _USE_COLOR else ""
GREEN = "\033[92m" if _USE_COLOR else ""
YELLOW = "\033[93m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""

# ---------------------------------------------------------------------------
# 数据点提取：从 Markdown 报告中识别财务数字
# ---------------------------------------------------------------------------


def _clean_num(s: str) -> float:
    """把带逗号、中文逗号的数字字符串转为 float。"""
    s = s.replace(",", "").replace("，", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _is_valid_label(label: str) -> bool:
    """判断标签是否是有意义的财务字段名，过滤噪声。"""
    label = label.strip()
    # 太短
    if len(label) < 2:
        return False
    # 纯数字或纯年份
    if re.fullmatch(r"[\d\s年季度Q]+", label):
        return False
    # 以符号/markdown标记开头
    if re.match(r"^[+\-\*#\|~\$>_`]", label):
        return False
    # 含有 markdown 粗体/代码标记
    if "**" in label or "`" in label or "__" in label:
        return False
    # 标签含有纯增速符号（如 +56%、-13% 单独作标签）
    if re.fullmatch(r"[+\-]?\d+(\.\d+)?%", label):
        return False
    # 常见无意义标签
    _SKIP = {
        "来源",
        "sources",
        "source",
        "说明",
        "注意",
        "备注",
        "数据来源",
        "n/a",
        "—",
        "-",
        "/",
        "合计",
        "total",
        "单位",
        "趋势",
    }
    if label.lower() in _SKIP:
        return False
    # 非财务类标签（评分/星级/排名/章节/清单序号等），不作为抽检对象，避免假阳性
    if re.search(
        r"(评分|评级|星级|排名|权重|字数|页码|序号|数量|条数|篇数|个数|信心度|健康度)", label
    ):
        return False
    if re.search(r"第.{0,4}(章|节|关|步|篇|页|层)", label):
        return False
    return True


# 带标签的 KV 行：标签：数值 单位
_KV_LABEL_RE = re.compile(
    r"(?P<label>[\u4e00-\u9fa5A-Za-z][^\|\n：:*]{1,30})[：:]\s*[~约]?\$?"
    r"(?P<num>[\d,，\.]+)\s*(?P<unit>亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?"
)


def _parse_md_tables(lines: list) -> list:
    """解析 Markdown 中所有表格，返回 (row_label, col_header, value, unit, lineno, raw) 列表。"""
    results = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 检测表头行（含 | 且不是分隔行）
        if "|" in line and not re.match(r"^\|[\-\s\|:]+\|$", line):
            headers_raw = [h.strip().strip("*_").strip() for h in line.split("|")]
            headers_raw = [h for h in headers_raw if h]
            # 下一行应是分隔行
            if i + 1 < len(lines) and re.match(r"^\|[\-\s\|:]+\|$", lines[i + 1].strip()):
                i += 2  # 跳过分隔行
                # 读数据行
                while i < len(lines):
                    dline = lines[i].strip()
                    if not dline or not dline.startswith("|"):
                        break
                    cells = [c.strip().strip("*_~").strip() for c in dline.split("|")]
                    cells = [c for c in cells if c != ""]
                    if len(cells) < 2:
                        i += 1
                        continue
                    row_label = cells[0]
                    for col_idx, cell in enumerate(cells[1:], start=1):
                        col_header = (
                            headers_raw[col_idx] if col_idx < len(headers_raw) else f"列{col_idx}"
                        )
                        # 提取 cell 中的数字+单位
                        m = re.search(
                            r"[~约]?\$?([\d,，\.]+)\s*(亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?", cell
                        )
                        if m:
                            val = _clean_num(m.group(1))
                            unit = (m.group(2) or "").strip()
                            if val and val != 0 and val < 1e15:
                                results.append((row_label, col_header, val, unit, i + 1, dline))
                    i += 1
                continue
        i += 1
    return results


def extract_data_points(md_text: str) -> list:
    """从 Markdown 报告中提取所有可识别的财务数据点。

    覆盖三类结构：
      1. 多列 Markdown 表格（最主要的来源）：(行标签 + 列标题) → 数值
      2. 带冒号的 KV 行：标签：数值 单位
      3. 加粗数字行：**数值** 单位

    返回 list of dict：
      {id, label, reported_value, unit, raw_text, line_number}
    """
    points = []
    seen = set()

    def _add(label, val, unit, lineno, raw):
        label = re.sub(r"[\*_`]+", "", label).strip()
        if not _is_valid_label(label):
            return
        if val is None or val == 0 or val > 1e15:
            return
        # 过滤纯年份/季度
        if re.fullmatch(r"(20\d{2}|Q[1-4]|\d{4}\s*Q[1-4])", label.strip()):
            return
        key = f"{label}|{round(val, 4)}|{unit}"
        if key in seen:
            return
        seen.add(key)
        points.append(
            {
                "id": len(points) + 1,
                "label": label,
                "reported_value": val,
                "unit": unit,
                "raw_text": raw[:120],
                "line_number": lineno,
            }
        )

    lines = md_text.split("\n")
    in_code = False

    # --- 1. 多列表格 ---
    for row_label, col_header, val, unit, lineno, raw in _parse_md_tables(lines):
        # 跳过无意义行标签
        if not _is_valid_label(row_label):
            continue
        # 跳过无意义列标题（YoY增速列单独标注，不作为待核验数据）
        if col_header.upper() in ("YOY", "YOY增速", "增速", "同比", "变化", "趋势", "说明", "备注"):
            continue
        # label = "行标签 · 列标题"（若列标题是行标签的补充）
        if col_header and col_header != row_label:
            label = f"{row_label} · {col_header}"
        else:
            label = row_label
        _add(label, val, unit, lineno, raw)

    # --- 2. KV 冒号行 ---
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or stripped.startswith("> ") or re.match(r"^#{1,6}\s", stripped):
            continue
        if "|" in stripped:
            continue  # 表格已在上面处理

        for m in _KV_LABEL_RE.finditer(stripped):
            label = m.group("label")
            val = _clean_num(m.group("num"))
            unit = (m.group("unit") or "").strip()
            _add(label, val, unit, lineno, stripped)

    return points


def sample_points(points: list, ratio: float = 0.15, seed: int = None) -> list:
    """随机抽取 ratio 比例的数据点，最少 3 个，最多 30 个。

    优先抽取带财务单位（亿/万亿/%/x倍/B/M/T）的数据点；
    无单位的裸数字噪声概率高，仅在带单位数据点不足时补充。
    """
    n = max(3, min(30, math.ceil(len(points) * ratio)))
    n = min(n, len(points))
    rng = Random(seed)
    with_unit = [p for p in points if p.get("unit")]
    without_unit = [p for p in points if not p.get("unit")]
    if len(with_unit) >= n:
        sampled = rng.sample(with_unit, n)
    else:
        sampled = list(with_unit)
        remaining = n - len(sampled)
        if without_unit and remaining > 0:
            sampled += rng.sample(without_unit, min(remaining, len(without_unit)))
    # 按行号排序，方便人工比对
    return sorted(sampled, key=lambda p: p["line_number"])


# ---------------------------------------------------------------------------
# 准出/打回判决
# ---------------------------------------------------------------------------

_TOLERANCE = 0.01  # 1% 容差


def _pct_diff(reported: float, fetched: float) -> float:
    """相对偏差 (absolute)。"""
    if reported == 0:
        return 0.0 if fetched == 0 else float("inf")
    return abs(reported - fetched) / abs(reported)


def render_verdict(results: list, report_name: str = "") -> dict:
    """
    根据核验结果输出准出/打回判决。

    results: list of dict，每项包含：
      - id, label, reported_value, unit, fetched_value, fetched_source
      - (可选) fetched_value2, fetched_source2   ← 第二来源

    返回：
      {
        'verdict': 'PASS' | 'FAIL',
        'pass_count': int,
        'fail_count': int,
        'total': int,
        'fail_items': [...],
        'summary': str,
      }
    """
    print("=" * 70)
    print(f"{BOLD}报告数据抽检 — 准出/打回判决{RESET}")
    if report_name:
        print(f"报告：{report_name}")
    print("=" * 70)
    print()

    fail_items = []
    warn_items = []
    skipped_bad = []

    for idx, item in enumerate(results, start=1):
        # 字段完整性防护：缺失必需字段的项友好跳过，不崩溃
        if (
            not isinstance(item, dict)
            or item.get("id") is None
            or not item.get("label")
            or item.get("reported_value") is None
        ):
            skipped_bad.append(idx)
            print(
                f"  ⛔ 第 {idx} 项缺少必需字段（id/label/reported_value），已跳过: {str(item)[:60]}"
            )
            continue
        label = item.get("label", "?")
        reported = float(item.get("reported_value", 0))
        unit = item.get("unit", "")
        fetched = item.get("fetched_value")
        source = item.get("fetched_source", "?")
        fetched2 = item.get("fetched_value2")
        source2 = item.get("fetched_source2", "")

        # --- 主来源比对 ---
        if fetched is None:
            # 没有提供核验值 → 跳过（不计入通过/失败）
            print(
                f"  ⬜ [{item['id']:>2}] {label[:35]:35s} {reported:>12.2f} {unit}  →  [未提供核验值，跳过]"
            )
            continue

        fetched = float(fetched)
        diff1 = _pct_diff(reported, fetched)

        # --- 第二来源比对（如有）---
        diff2 = None
        if fetched2 is not None:
            fetched2 = float(fetched2)
            diff2 = _pct_diff(reported, fetched2)

        # 判断
        pass1 = diff1 <= _TOLERANCE

        if diff2 is None:
            # 单源核验：主来源直接定生死（playbook：任意抽检点偏差 >1% 即打回）
            pass2 = pass1
        else:
            pass2 = diff2 <= _TOLERANCE

        if pass1 and pass2:
            status = f"{GREEN}✅ 通过{RESET}"
            detail = f"{source}: {fetched:.2f} (偏差 {diff1 * 100:.2f}%)"
            if diff2 is not None:
                detail += f"  |  {source2}: {fetched2:.2f} (偏差 {diff2 * 100:.2f}%)"
        elif not pass1 and not pass2:
            status = f"{RED}❌ 不通过{RESET}"
            detail = f"{source}: {fetched:.2f} (偏差 {diff1 * 100:.2f}%)"
            if diff2 is not None:
                detail += f"  |  {source2}: {fetched2:.2f} (偏差 {diff2 * 100:.2f}%)"
            fail_items.append(
                {
                    "id": item["id"],
                    "label": label,
                    "reported": reported,
                    "unit": unit,
                    "fetched": fetched,
                    "source": source,
                    "fetched2": fetched2,
                    "source2": source2,
                    "diff1_pct": round(diff1 * 100, 2),
                    "diff2_pct": round(diff2 * 100, 2) if diff2 is not None else None,
                    "raw_text": item.get("raw_text", ""),
                    "line_number": item.get("line_number", 0),
                }
            )
        else:
            # 一个来源通过，一个不通过 → 警告，不计入失败
            status = f"{YELLOW}⚠️  警告{RESET}"
            detail = f"{source}: {fetched:.2f} (偏差 {diff1 * 100:.2f}%)"
            if diff2 is not None:
                detail += f"  |  {source2}: {fetched2:.2f} (偏差 {diff2 * 100:.2f}%)"
            warn_items.append(
                {
                    "id": item["id"],
                    "label": label,
                    "reported": reported,
                    "unit": unit,
                    "diff1_pct": round(diff1 * 100, 2),
                    "diff2_pct": round(diff2 * 100, 2) if diff2 is not None else None,
                }
            )

        print(f"  {status} [{item['id']:>2}] {label[:35]:35s}  报告: {reported:>12.2f} {unit}")
        print(f"              {' ' * 38}{detail}")

    print()
    print("-" * 70)

    total = len(
        [
            r
            for r in results
            if isinstance(r, dict)
            and r.get("fetched_value") is not None
            and r.get("id") is not None
            and r.get("label")
            and r.get("reported_value") is not None
        ]
    )
    fail_count = len(fail_items)
    warn_count = len(warn_items)
    pass_count = total - fail_count - warn_count

    if skipped_bad:
        print(
            f"  ⛔ {len(skipped_bad)} 项字段不完整已跳过（序号: {skipped_bad}），请补齐 id/label/reported_value 后重跑"
        )

    print(
        f"  抽检总数: {total}  |  通过: {GREEN}{pass_count}{RESET}  |  警告: {YELLOW}{warn_count}{RESET}  |  不通过: {RED}{fail_count}{RESET}"
    )
    print()

    if fail_count == 0:
        print(f"{BOLD}{GREEN}【准出】所有抽检数据通过，报告可发布。{RESET}")
        verdict = "PASS"
    else:
        print(f"{BOLD}{RED}【打回】{fail_count} 个数据点核验不通过，报告需修正后重审。{RESET}")
        print()
        print(f"{BOLD}打回原因：{RESET}")
        for fi in fail_items:
            print(f"  ❌ 第 {fi['line_number']} 行 | {fi['label']}")
            print(f"     报告值：{fi['reported']} {fi['unit']}")
            print(f"     {fi['source']}：{fi['fetched']}  （偏差 {fi['diff1_pct']}%）")
            if fi.get("fetched2") is not None:
                print(f"     {fi['source2']}：{fi['fetched2']}  （偏差 {fi['diff2_pct']}%）")
            print(f"     原文：{fi['raw_text'][:80]}")
            print()
        verdict = "FAIL"

    if warn_count > 0:
        print(
            f"{YELLOW}注意：{warn_count} 个数据点两来源结果不一致（超过1%），可能是口径差异（GAAP/Non-GAAP或汇率），请人工复核。{RESET}"
        )
        for wi in warn_items:
            print(
                f"  ⚠️  {wi['label']}  报告:{wi['reported']} {wi['unit']}  偏差: {wi['diff1_pct']}% / {wi['diff2_pct']}%"
            )

    print("=" * 70)

    return {
        "verdict": verdict,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "total": total,
        "fail_items": fail_items,
        "warn_items": warn_items,
    }


# ---------------------------------------------------------------------------
# 逻辑链审计：Claim-Evidence 图谱检查
# ---------------------------------------------------------------------------

# 结论性语句识别：含判断/结论/建议/评估等关键词的行
_CLAIM_RE = re.compile(
    r"(结论|判断|建议|评估|认为|表明|说明|证明|意味着|风险|机会|"
    r"护城河|安全边际|买入|观望|回避|卖出|通过|不通过|"
    r"值得|不值得|核心|关键|主要|最|强|弱|高|低)"
)

# 证据标注：[E1] [E2] 等
_EVIDENCE_RE = re.compile(r"\[E(\d+)\]")


def extract_logic_chain(md_text: str) -> dict:
    """从报告中提取结论-证据图谱，检查逻辑链完整性。

    返回：
      {
        'claims': [{'line', 'text', 'evidence_ids'}],
        'evidence_definitions': [{'id', 'line', 'text'}],
        'naked_claims': [...],       # 无证据支撑的结论
        'orphan_evidence': [...],    # 未被引用的证据
        'summary': {...}
      }
    """
    lines = md_text.split("\n")
    claims = []
    evidence_defs = []
    all_evidence_ids = set()
    cited_evidence_ids = set()

    in_code = False
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        # 识别证据定义行：含 [E1] 且是定义性质（如 "[E1] 来源：..." 或表格行）
        e_matches = _EVIDENCE_RE.findall(stripped)
        for eid in e_matches:
            all_evidence_ids.add(int(eid))

        # 识别结论性语句
        if _CLAIM_RE.search(stripped) and len(stripped) > 10:
            # 排除纯标题行、表格分隔行、元信息头
            if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith(">"):
                # 表格行和引用行也可能是结论，但标题行不是
                if stripped.startswith("#"):
                    continue
            e_cited = [int(x) for x in e_matches]
            for eid in e_cited:
                cited_evidence_ids.add(eid)
            claims.append({
                "line": lineno,
                "text": stripped[:100],
                "evidence_ids": e_cited,
            })

    # 证据定义：第一次出现 [EX] 的行视为定义
    seen_eids = set()
    for lineno, line in enumerate(lines, start=1):
        for m in _EVIDENCE_RE.finditer(line):
            eid = int(m.group(1))
            if eid not in seen_eids:
                seen_eids.add(eid)
                evidence_defs.append({
                    "id": eid,
                    "line": lineno,
                    "text": line.strip()[:100],
                })

    naked = [c for c in claims if not c["evidence_ids"]]
    orphan = sorted(all_evidence_ids - cited_evidence_ids)

    return {
        "claims": claims,
        "evidence_definitions": evidence_defs,
        "naked_claims": naked,
        "orphan_evidence": orphan,
        "summary": {
            "total_claims": len(claims),
            "supported_claims": len(claims) - len(naked),
            "naked_claims": len(naked),
            "total_evidence": len(all_evidence_ids),
            "orphan_evidence": len(orphan),
            "coverage": round((len(claims) - len(naked)) / max(len(claims), 1) * 100, 1),
        },
    }


def render_logic_chain(result: dict, report_name: str = ""):
    """输出逻辑链审计结果。"""
    s = result["summary"]
    print("=" * 70)
    print(f"{BOLD}逻辑链审计 — Claim-Evidence 图谱检查{RESET}")
    if report_name:
        print(f"报告：{report_name}")
    print("=" * 70)
    print()
    print(f"  结论性语句: {s['total_claims']} 条")
    print(f"  有证据支撑: {GREEN}{s['supported_claims']}{RESET} 条")
    print(f"  裸奔结论:   {RED if s['naked_claims'] > 0 else GREEN}{s['naked_claims']}{RESET} 条（无 [EX] 标注）")
    print(f"  证据定义:   {s['total_evidence']} 条")
    print(f"  孤立证据:   {YELLOW if s['orphan_evidence'] > 0 else GREEN}{s['orphan_evidence']}{RESET} 条（未被任何结论引用）")
    print(f"  证据覆盖率: {s['coverage']}%")
    print()

    if result["naked_claims"]:
        print(f"{BOLD}{RED}裸奔结论（无证据支撑）：{RESET}")
        for c in result["naked_claims"][:10]:  # 最多显示 10 条
            print(f"  ❌ 第 {c['line']} 行: {c['text']}")
        if len(result["naked_claims"]) > 10:
            print(f"  ... 及另外 {len(result['naked_claims']) - 10} 条")
        print()

    if result["orphan_evidence"]:
        print(f"{YELLOW}孤立证据（定义了但未被引用）：{RESET}")
        print(f"  ⚠️  证据 ID: {result['orphan_evidence']}")
        print()

    # 判决
    if s["naked_claims"] == 0:
        print(f"{BOLD}{GREEN}【通过】所有结论均有证据支撑。{RESET}")
    elif s["coverage"] >= 70:
        print(f"{BOLD}{YELLOW}【警告】{s['naked_claims']} 条结论缺少证据标注，建议补充。{RESET}")
    else:
        print(f"{BOLD}{RED}【不通过】证据覆盖率仅 {s['coverage']}%，大量结论裸奔，需补充证据链。{RESET}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Report Audit Tool — 研究报告数据抽检工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流程：

  Step 1 — 提取数据点并随机抽样 15%，输出抽检清单（推荐写入文件）：
    python3 tools/report_audit.py extract --report reports/腾讯/腾讯-research-20260408.md \
      --output reports/腾讯/audit-checklist.json

  Step 2 — Claude 对清单中每个数据点，从可靠信源取数，
            填入 fetched_value / fetched_source / fetched_value2 / fetched_source2

  Step 3 — 输入核验结果，输出准出/打回判决（推荐从文件读入，避免 shell 引号问题）：
    python3 tools/report_audit.py verdict --results-file reports/腾讯/audit-checklist.json
    # 或内联 JSON（向后兼容）：
    python3 tools/report_audit.py verdict --results '[
      {"id":1,"label":"营业收入","reported_value":7518,"unit":"亿","fetched_value":7518,"fetched_source":"macrotrends","fetched_value2":7500,"fetched_source2":"stockanalysis"},
      ...
    ]'

  一步预览（只打印抽检清单，不核验）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run

  指定抽样比例（默认0.15）：
    python3 tools/report_audit.py extract --report reports/xxx.md --ratio 0.20

  固定随机种子（复现同一批样本）：
    python3 tools/report_audit.py extract --report reports/xxx.md --seed 42

  退出码：0=准出(PASS) / 1=打回(FAIL) / 2=参数错误
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # extract
    ext = sub.add_parser("extract", help="从报告提取数据点并随机抽样")
    ext.add_argument("--report", required=True, help="报告文件路径（Markdown）")
    ext.add_argument("--ratio", type=float, default=0.15, help="抽样比例，默认 0.15")
    ext.add_argument("--seed", type=int, default=None, help="随机种子（可选，用于复现）")
    ext.add_argument("--dry-run", action="store_true", help="只打印，不输出 JSON")
    ext.add_argument(
        "--output",
        default=None,
        help="将抽检清单 JSON 模板写入文件（建议 reports/{公司}/audit-checklist.json，填好后传给 verdict --results-file）",
    )

    # verdict
    vrd = sub.add_parser("verdict", help="根据核验结果输出准出/打回判决")
    vrd.add_argument(
        "--results",
        default=None,
        help="JSON 数组，含 fetched_value 等字段（与 --results-file 二选一）",
    )
    vrd.add_argument(
        "--results-file", default=None, help="从 JSON 文件读入核验结果（推荐，避免 shell 引号问题）"
    )
    vrd.add_argument("--report", default="", help="报告名称（可选，用于显示）")
    vrd.add_argument("--output-json", action="store_true", help="将判决结果以 JSON 输出到 stdout")

    # logic-chain
    lc = sub.add_parser("logic-chain", help="逻辑链审计：检查结论是否有证据支撑")
    lc.add_argument("--report", required=True, help="报告文件路径（Markdown）")
    lc.add_argument("--output-json", action="store_true", help="将审计结果以 JSON 输出到 stdout")

    args = parser.parse_args()

    if args.command == "extract":
        if not os.path.exists(args.report):
            print(f"❌ 文件不存在: {args.report}", file=sys.stderr)
            sys.exit(1)

        with open(args.report, encoding="utf-8") as f:
            text = f.read()

        all_points = extract_data_points(text)
        sampled = sample_points(all_points, ratio=args.ratio, seed=args.seed)

        print("=" * 70)
        print("报告数据抽检清单")
        print(f"文件：{args.report}")
        print(
            f"总提取数据点：{len(all_points)}  |  抽样比例：{args.ratio:.0%}  |  抽检数量：{len(sampled)}"
        )
        if args.seed is not None:
            print(f"随机种子：{args.seed}（可用于复现同一批样本）")
        print("=" * 70)
        print()
        print(f"{'ID':>3}  {'行号':>5}  {'数据标签':<35}  {'报告值':>12}  {'单位'}")
        print(f"{'─' * 3}  {'─' * 5}  {'─' * 35}  {'─' * 12}  {'─' * 6}")
        for p in sampled:
            print(
                f"{p['id']:>3}  {p['line_number']:>5}  {p['label'][:35]:<35}  {p['reported_value']:>12.2f}  {p['unit']}"
            )
        print()
        print("↑ 请对上述每个数据点，从以下信源取数，填入 fetched_value：")
        print("  美股：macrotrends.net（主）+ stockanalysis.com（副）")
        print("  港股：aastocks.com（主）+ macrotrends ADR（副）")
        print("  A股： eastmoney.com（主）+ cninfo.com.cn（副）")
        print()

        if not args.dry_run:
            # 输出可填写的 JSON 模板
            template = []
            for p in sampled:
                template.append(
                    {
                        "id": p["id"],
                        "label": p["label"],
                        "reported_value": p["reported_value"],
                        "unit": p["unit"],
                        "line_number": p["line_number"],
                        "raw_text": p["raw_text"],
                        "fetched_value": None,  # ← 填入主来源核验值
                        "fetched_source": "",  # ← 填入主来源名称
                        "fetched_value2": None,  # ← 填入副来源核验值（可选）
                        "fetched_source2": "",  # ← 填入副来源名称（可选）
                    }
                )
            if args.output:
                out_dir = os.path.dirname(args.output)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(template, f, ensure_ascii=False, indent=2)
                print(f"抽检清单已写入：{args.output}")
                print("填入 fetched_value 后执行：")
                print(f"  python3 tools/report_audit.py verdict --results-file {args.output}")
            else:
                print("抽检清单 JSON（填入 fetched_value 后，传给 verdict 命令）：")
                print()
                print(json.dumps(template, ensure_ascii=False, indent=2))

    elif args.command == "verdict":
        # --results-file 优先（推荐），--results 内联方式向后兼容
        if not args.results and not args.results_file:
            print(
                "❌ 需提供 --results-file <路径>（推荐）或 --results <JSON字符串>", file=sys.stderr
            )
            sys.exit(2)
        if args.results_file:
            if not os.path.exists(args.results_file):
                print(f"❌ 核验结果文件不存在: {args.results_file}", file=sys.stderr)
                sys.exit(2)
            with open(args.results_file, encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = args.results
        try:
            results = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
            print(
                "   提示：优先用 --results-file 从文件读入，避免 shell 引号转义问题",
                file=sys.stderr,
            )
            sys.exit(2)
        if not isinstance(results, list):
            print("❌ 核验结果必须是 JSON 数组（extract 输出的模板格式）", file=sys.stderr)
            sys.exit(2)

        report_name = args.report or ""
        outcome = render_verdict(results, report_name=report_name)

        if args.output_json:
            print(json.dumps(outcome, ensure_ascii=False, indent=2))

        # 非零退出码表示打回，方便 CI/脚本判断
        sys.exit(0 if outcome["verdict"] == "PASS" else 1)

    elif args.command == "logic-chain":
        if not os.path.exists(args.report):
            print(f"❌ 文件不存在: {args.report}", file=sys.stderr)
            sys.exit(1)
        with open(args.report, encoding="utf-8") as f:
            text = f.read()
        result = extract_logic_chain(text)
        render_logic_chain(result, report_name=args.report)
        if args.output_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        # 覆盖率 < 70% 视为不通过
        sys.exit(0 if result["summary"]["coverage"] >= 70 else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
