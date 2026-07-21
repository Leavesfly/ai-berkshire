#!/usr/bin/env python3
"""投资决策日志 — 记录每次研究结论，支持事后复盘（track record）。

芒格式反馈闭环：把每次流程产出的结论（买入/观望/回避/卖出）连同当时价格
落盘到 data/decisions.jsonl，定期用 review 回看判断质量，让系统从
「每次都聪明」变成「越用越聪明」。

约定（见 CLAUDE.md「金融严谨性」）：所有产出明确结论的研报级流程
（investment-research / investment-team / exit-review / investment-checklist 等）
在报告交付后调用 add 追加一条记录。

用法（由 Skills 自动调用）：
    python3 tools/decision_log.py add --company 腾讯 --code hk00700 \\
        --skill investment-research --verdict 买入 --price 480 --currency HKD \\
        --reason "游戏基本盘稳固，视频号广告加速" --report reports/腾讯/腾讯-research-20260720.md
    python3 tools/decision_log.py list --company 腾讯
    python3 tools/decision_log.py review                # 全部决策 vs 当前价格复盘
    python3 tools/decision_log.py review --company 腾讯
    python3 tools/decision_log.py review --benchmark    # 额外对比同期指数（沪深300/恒指/标普500）

依赖：零外部依赖；review 需网络取现价（走 ashare_data 行情通道）。
退出码：0=成功 / 1=失败 / 2=参数错误。
"""

import argparse
import json
import os
import sys
from datetime import datetime

from utils import EXIT_BAD_ARGS, EXIT_OK

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_PATH = os.path.join(_ROOT, "data", "decisions.jsonl")

_VALID_VERDICTS = ("买入", "观望", "回避", "卖出", "持有", "减仓", "通过", "不通过")


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------


def _load_records() -> list:
    if not os.path.exists(_LOG_PATH):
        return []
    records = []
    with open(_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 跳过损坏行，不中断复盘
    return records


def cmd_add(args):
    if args.verdict not in _VALID_VERDICTS:
        print(f"❌ --verdict 仅支持: {' / '.join(_VALID_VERDICTS)}")
        sys.exit(EXIT_BAD_ARGS)
    record = {
        "date": args.date or datetime.now().strftime("%Y-%m-%d"),
        "company": args.company,
        "code": args.code or "",
        "skill": args.skill,
        "verdict": args.verdict,
        "price": args.price,
        "currency": args.currency or "",
        "reason": args.reason or "",
        "report": args.report or "",
    }
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
        f"  ✅ 决策已记录: {record['date']} {args.company} — {args.verdict}"
        + (f" @ {args.price}{record['currency']}" if args.price else "")
    )
    print(f"     日志: {os.path.relpath(_LOG_PATH, _ROOT)}（共 {len(_load_records())} 条）")


def cmd_list(company=None, limit=20):
    records = _load_records()
    if company:
        records = [r for r in records if r.get("company") == company]
    if not records:
        print("  （暂无决策记录）")
        return
    print("=" * 66)
    print(
        f"决策日志{'（' + company + '）' if company else ''} — 最近 {min(limit, len(records))} 条 / 共 {len(records)} 条"
    )
    print("=" * 66)
    for r in records[-limit:]:
        price = f" @ {r['price']}{r.get('currency', '')}" if r.get("price") else ""
        print(f"  {r['date']}  {r['company']:8s} {r['verdict']:4s}{price}  [{r.get('skill', '')}]")
        if r.get("reason"):
            print(f"             理由: {r['reason'][:60]}")


# ---------------------------------------------------------------------------
# review：决策 vs 现价复盘
# ---------------------------------------------------------------------------


def _get_current_price(code: str):
    """通过 ashare_data 行情通道取现价（导入复用，命中15分钟缓存时秒回）。"""
    try:
        import ashare_data

        d, _note = ashare_data._get_quote(code)
        if d and d.get("price"):
            return float(d["price"])
    except Exception:
        pass
    return None


def _judge(verdict: str, change_pct):
    """按结论方向给出初步验证信号（价格短期走势≠最终对错，仅作跟踪信号）。"""
    if change_pct is None:
        return "—"
    if verdict in ("买入", "持有", "通过"):
        return "✅ 方向一致" if change_pct > 0 else "⚠️ 暂时背离"
    if verdict in ("回避", "卖出", "减仓", "不通过"):
        return "✅ 方向一致" if change_pct < 0 else "⚠️ 暂时背离"
    return "— 观望中性"


# 各市场默认基准（与 ashare_data 日K通道兼容的指数代码）
_BENCH_BY_MARKET = {
    "A": ("sh000300", "沪深300"),
    "HK": ("hkHSI", "恒指"),
    "US": ("us.INX", "标普500"),
}


def _bench_for(code: str):
    cu = code.strip().upper()
    if cu.endswith(".HK") or (cu.startswith("HK") and cu[2:].isdigit()):
        return _BENCH_BY_MARKET["HK"]
    if cu.startswith("US") and len(cu) > 2 and not cu[2:].isdigit():
        return _BENCH_BY_MARKET["US"]
    return _BENCH_BY_MARKET["A"]


def _bench_change(bench_code: str, since_date: str, series_cache: dict):
    """基准指数自 since_date 以来的涨跌幅（%）；取不到返回 None。"""
    try:
        if bench_code not in series_cache:
            import ashare_data

            days = max(60, (datetime.now() - datetime.strptime(since_date, "%Y-%m-%d")).days + 30)
            series, _note = ashare_data.get_close_series(bench_code, min(days, 2000))
            series_cache[bench_code] = series or []
        series = series_cache[bench_code]
        base = next((s["close"] for s in series if s["date"] >= since_date), None)
        if base and series:
            return (series[-1]["close"] / base - 1) * 100
    except Exception:
        pass
    return None


def cmd_review(company=None, benchmark=False):
    records = _load_records()
    if company:
        records = [r for r in records if r.get("company") == company]
    records = [r for r in records if r.get("price") and r.get("code")]
    if not records:
        print("  （暂无可复盘的决策记录——需要记录时带 --price 与 --code）")
        return

    print("=" * 92 if benchmark else "=" * 78)
    print("决策复盘 (Track Record Review)" + ("，含同期基准对比" if benchmark else ""))
    print("=" * 92 if benchmark else "=" * 78)
    header = f"  {'日期':10s} {'公司':8s} {'结论':4s} {'当时价':>9s} {'现价':>9s} {'涨跌':>8s}"
    if benchmark:
        header += f" {'基准':>8s} {'超额':>8s}"
    print(header + "  信号")
    print("  " + "-" * (86 if benchmark else 72))

    aligned = misaligned = 0
    price_cache, bench_cache = {}, {}
    excess_sum, excess_n = 0.0, 0
    for r in records:
        code = r["code"]
        if code not in price_cache:
            price_cache[code] = _get_current_price(code)
        cur = price_cache[code]
        change = (cur / float(r["price"]) - 1) * 100 if cur else None
        signal = _judge(r["verdict"], change)
        if signal.startswith("✅"):
            aligned += 1
        elif signal.startswith("⚠️"):
            misaligned += 1
        cur_s = f"{cur:.2f}" if cur else "-"
        chg_s = f"{change:+.1f}%" if change is not None else "-"
        line = (
            f"  {r['date']:10s} {r['company']:8s} {r['verdict']:4s} "
            f"{float(r['price']):>9.2f} {cur_s:>9s} {chg_s:>8s}"
        )
        if benchmark:
            b_code, _b_name = _bench_for(code)
            b_chg = _bench_change(b_code, r["date"], bench_cache)
            b_s = f"{b_chg:+.1f}%" if b_chg is not None else "-"
            if change is not None and b_chg is not None:
                excess = change - b_chg
                # 回避/卖出类：跑输基准才是“避对了”，超额取反向
                if r["verdict"] in ("回避", "卖出", "减仓", "不通过"):
                    excess = -excess
                e_s = f"{excess:+.1f}%"
                excess_sum += excess
                excess_n += 1
            else:
                e_s = "-"
            line += f" {b_s:>8s} {e_s:>8s}"
        print(line + f"  {signal}")

    total = aligned + misaligned
    print()
    if total:
        print(
            f"  方向一致率: {aligned}/{total} = {aligned / total * 100:.0f}%（不含观望/取价失败）"
        )
    if benchmark and excess_n:
        print(
            f"  平均超额收益: {excess_sum / excess_n:+.1f}%（{excess_n} 条；基准按市场自动选 沪深300/恒指/标普500）"
        )
        print("  ⚠️ 胜率高但超额为负 = 只是赶上了牛市；超额才是判断力的证据")
    print("  ⚠️ 价值投资以年为单位验证，短期价格背离≠判断错误；")
    print("     背离标的应走 thesis-drift 复查论文，而不是直接改结论")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="投资决策日志 — 记录结论、复盘判断质量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="追加一条决策记录")
    p_add.add_argument("--company", required=True, help="公司名")
    p_add.add_argument("--code", default="", help="股票代码（600519 / hk00700 / usAAPL），复盘需要")
    p_add.add_argument("--skill", required=True, help="产出结论的子流程名")
    p_add.add_argument("--verdict", required=True, help=f"结论: {' / '.join(_VALID_VERDICTS)}")
    p_add.add_argument("--price", type=float, default=None, help="决策时股价，复盘需要")
    p_add.add_argument("--currency", default="", help="币种（CNY/HKD/USD）")
    p_add.add_argument("--reason", default="", help="一句话核心理由")
    p_add.add_argument("--report", default="", help="关联报告路径")
    p_add.add_argument("--date", default="", help="决策日期（默认今天）")

    p_list = sub.add_parser("list", help="查看决策记录")
    p_list.add_argument("--company", default=None)
    p_list.add_argument("--limit", type=int, default=20)

    p_rev = sub.add_parser("review", help="决策 vs 现价复盘")
    p_rev.add_argument("--company", default=None)
    p_rev.add_argument(
        "--benchmark",
        action="store_true",
        help="额外对比同期指数（按市场自动选沪深300/恒指/标普500）",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args.company, args.limit)
    else:
        cmd_review(args.company, args.benchmark)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
