#!/usr/bin/env python3
"""观察清单监控 — 维护标的清单与买卖关注区间，一条命令批量扫描触发信号。

把"用户问才动"变成"主动盯盘"：为每个标的设定理想买入价上限 / 卖出关注价，
scan 时批量取行情并输出触发信号（进入买入区 / 触发卖出关注 / 接近52周低点 / 单日异动）。

清单文件：data/watchlist.json（人读机读两用，可手工编辑）。

用法（由 Skills 自动调用）：
    python3 tools/watchlist.py add --code hk00700 --name 腾讯 --buy-below 400 --sell-above 700 \\
        --note "论文红线：游戏流水连续两季下滑"
    python3 tools/watchlist.py remove --code hk00700
    python3 tools/watchlist.py list
    python3 tools/watchlist.py scan                 # 批量扫描（15分钟行情缓存）
    python3 tools/watchlist.py scan --no-cache      # 强制实时
    python3 tools/watchlist.py scan --notify        # 有触发信号时推送 webhook（钉钉/飞书/通用）
    python3 tools/watchlist.py schedule --every 60  # 生成定时扫描配置（launchd/cron，不自动安装）

推送配置：环境变量 WATCHLIST_WEBHOOK 设为钉钉/飞书机器人 webhook 地址
（按 URL 自动识别格式；其他地址按通用 {"text": ...} JSON POST）。

依赖：零外部依赖；scan 走 ashare_data 行情通道（腾讯行情），推送走 curl。
退出码：0=成功（scan 时含"有触发信号"）/ 1=失败 / 2=参数错误。
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

from utils import _CURL_PATH, EXIT_BAD_ARGS, cli_entry

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WL_PATH = os.path.join(_ROOT, "data", "watchlist.json")

# ---------------------------------------------------------------------------
# 信号阈值常量（避免 magic number）
# ---------------------------------------------------------------------------

SIGNAL_CHANGE_PCT_THRESHOLD = 5.0  # 单日异动阈值 (%)
SIGNAL_52W_LOW_PROXIMITY = 0.05  # 距 52 周低点触发距离 (5%)


def _load() -> list:
    """加载观察清单条目列表，文件不存在或损坏时返回空列表。"""
    try:
        with open(_WL_PATH, encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except (OSError, json.JSONDecodeError):
        return []


def _save(items: list) -> None:
    """持久化观察清单到 data/watchlist.json。"""
    os.makedirs(os.path.dirname(_WL_PATH), exist_ok=True)
    with open(_WL_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": items},
            f,
            ensure_ascii=False,
            indent=2,
        )


def cmd_add(args: argparse.Namespace) -> None:
    """添加或更新观察标的（同 code 已存在则更新区间/备注）。"""
    items = _load()
    for it in items:
        if it["code"] == args.code:
            # 已存在则更新（区间/备注可随论文演进调整）
            it.update(
                {
                    k: v
                    for k, v in {
                        "name": args.name,
                        "buy_below": args.buy_below,
                        "sell_above": args.sell_above,
                        "note": args.note,
                    }.items()
                    if v is not None
                }
            )
            _save(items)
            print(f"  ✅ 已更新观察标的: {it['name']} ({args.code})")
            return
    items.append(
        {
            "code": args.code,
            "name": args.name or args.code,
            "buy_below": args.buy_below,
            "sell_above": args.sell_above,
            "note": args.note or "",
            "added": datetime.now().strftime("%Y-%m-%d"),
        }
    )
    _save(items)
    print(f"  ✅ 已加入观察清单: {args.name or args.code} ({args.code})，共 {len(items)} 个标的")


def cmd_remove(code: str) -> None:
    """从观察清单移除指定标的，不存在时退出码 2。"""
    items = _load()
    remain = [it for it in items if it["code"] != code]
    if len(remain) == len(items):
        print(f"  ⚠️ 清单中没有 {code}")
        sys.exit(EXIT_BAD_ARGS)
    _save(remain)
    print(f"  ✅ 已移除 {code}，剩余 {len(remain)} 个标的")


def cmd_list() -> None:
    """打印观察清单全部标的及其买卖区间。"""
    items = _load()
    if not items:
        print("  （观察清单为空——add 添加，或让研究流程结论自动入列）")
        return
    print("=" * 70)
    print(f"观察清单（{len(items)} 个标的）— data/watchlist.json")
    print("=" * 70)
    for it in items:
        buy = f"买入区 ≤{it['buy_below']}" if it.get("buy_below") else "买入区未设"
        sell = f"卖出关注 ≥{it['sell_above']}" if it.get("sell_above") else "卖出线未设"
        print(
            f"  {it['name']:10s} {it['code']:10s} {buy:16s} {sell:16s} (加入 {it.get('added', '-')})"
        )
        if it.get("note"):
            print(f"    备注: {it['note']}")


def _notify(text: str) -> bool:
    """通过 WATCHLIST_WEBHOOK 推送文本（钉钉/飞书按 URL 自动适配，其余通用格式）。"""
    url = os.environ.get("WATCHLIST_WEBHOOK", "").strip()
    if not url:
        print("  ⚠️ 未配置 WATCHLIST_WEBHOOK 环境变量，跳过推送")
        print(
            "     配置方法: export WATCHLIST_WEBHOOK='https://oapi.dingtalk.com/robot/send?access_token=...'"
        )
        return False
    if "dingtalk" in url:
        payload = {"msgtype": "text", "text": {"content": text}}
    elif "feishu" in url or "larksuite" in url:
        payload = {"msg_type": "text", "content": {"text": text}}
    else:
        payload = {"text": text}
    try:
        r = subprocess.run(
            [
                _CURL_PATH,
                "-s",
                "-m",
                "10",
                "-X",
                "POST",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(payload, ensure_ascii=False),
                url,
            ],
            capture_output=True,
            timeout=15,
        )
        ok = r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    print("  📨 推送" + ("成功" if ok else "失败（检查 webhook 地址与网络）"))
    return ok


def cmd_scan(no_cache: bool = False, notify: bool = False) -> None:
    """批量扫描观察清单，输出触发信号（进入买入区/卖出关注/52周低点/单日异动）。"""
    items = _load()
    if not items:
        print("  （观察清单为空，无可扫描标的）")
        return

    import ashare_data

    print("=" * 78)
    print(f"观察清单扫描 — {datetime.now().strftime('%Y-%m-%d %H:%M')}（{len(items)} 个标的）")
    print("=" * 78)

    triggers = []
    for it in items:
        try:
            d, note = ashare_data._get_quote(it["code"], no_cache=no_cache)
        except Exception:
            d = None
        if not d or not d.get("price"):
            print(f"  ❌ {it['name']:10s} 取数失败（{it['code']}）")
            continue

        price = float(d["price"])
        signals = []
        if it.get("buy_below") and price <= float(it["buy_below"]):
            signals.append(f"🟢 进入买入区（≤{it['buy_below']}）")
        if it.get("sell_above") and price >= float(it["sell_above"]):
            signals.append(f"🔴 触发卖出关注（≥{it['sell_above']}）")
        try:
            low52 = float(d.get("low_52w", 0))
            # 合理性防护：现价应 ≥ 52周低点（字段错位/脏数据时跳过，避免误报）
            if low52 > 0 and low52 * (1 - SIGNAL_52W_LOW_PROXIMITY * 0.4) <= price <= low52 * (1 + SIGNAL_52W_LOW_PROXIMITY):
                signals.append(f"📉 距52周低点({low52:.2f})不足5%")
        except (ValueError, TypeError):
            pass
        try:
            chg = float(d.get("change_pct", 0))
            if abs(chg) >= SIGNAL_CHANGE_PCT_THRESHOLD:
                signals.append(f"⚡ 单日异动 {chg:+.1f}%")
        except (ValueError, TypeError):
            chg = 0

        cache_tag = " [缓存]" if note else ""
        sig_txt = "；".join(signals) if signals else "— 无信号"
        print(
            f"  {it['name']:10s} 现价 {price:>9.2f} ({float(d.get('change_pct') or 0):+.2f}%){cache_tag}  {sig_txt}"
        )
        if signals:
            triggers.append((it, signals))

    print()
    if triggers:
        print(f"  📌 {len(triggers)} 个标的有触发信号：")
        for it, signals in triggers:
            print(f"     {it['name']}: {'；'.join(signals)}")
            if it.get("note"):
                print(f"       └ 论文备注: {it['note']}")
        print(
            "  下一步: 买入区标的走 investment-checklist 核对；卖出关注/异动标的走 exit-review / news-pulse"
        )
        if notify:
            lines = [
                f"【AI Berkshire 观察清单】{datetime.now().strftime('%m-%d %H:%M')} "
                f"{len(triggers)} 个标的触发信号"
            ]
            for it, signals in triggers:
                lines.append(f"· {it['name']}({it['code']}): {'；'.join(signals)}")
                if it.get("note"):
                    lines.append(f"  论文备注: {it['note']}")
            _notify("\n".join(lines))
    else:
        print("  ✅ 全部标的无触发信号")


def cmd_schedule(every: int) -> None:
    """生成定时扫描配置（只生成文件与说明，不自动安装——安装由用户执行）。"""
    if every < 5:
        print("❌ --every 最小 5 分钟（行情缓存 15 分钟，过密无意义）")
        sys.exit(EXIT_BAD_ARGS)
    py = sys.executable or "python3"
    script = os.path.join(_ROOT, "tools", "watchlist.py")
    log = os.path.join(_ROOT, "data", "watchlist-scan.log")

    plist_path = os.path.join(_ROOT, "data", "com.ai-berkshire.watchlist.plist")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ai-berkshire.watchlist</string>
  <key>ProgramArguments</key>
  <array><string>{py}</string><string>{script}</string><string>scan</string><string>--notify</string></array>
  <key>StartInterval</key><integer>{every * 60}</integer>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>EnvironmentVariables</key>
  <dict><key>WATCHLIST_WEBHOOK</key><string>{os.environ.get("WATCHLIST_WEBHOOK", "在此填入webhook地址")}</string></dict>
</dict></plist>
"""
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist)

    print("=" * 70)
    print(f"定时扫描配置已生成（每 {every} 分钟，仅生成不安装）")
    print("=" * 70)
    print("  macOS (launchd)：")
    print(f"    cp {plist_path} ~/Library/LaunchAgents/")
    print("    launchctl load ~/Library/LaunchAgents/com.ai-berkshire.watchlist.plist")
    print("    卸载: launchctl unload ~/Library/LaunchAgents/com.ai-berkshire.watchlist.plist")
    print()
    print("  Linux (crontab -e 添加一行)：")
    print(
        f"    */{every if every < 60 else 60} * * * * WATCHLIST_WEBHOOK='<webhook>' {py} {script} scan --notify >> {log} 2>&1"
    )
    print()
    print(f"  扫描日志: {log}")
    print(
        "  提示: 触发信号只在盘中有意义，可按需限定运行时段；webhook 未配置时扫描仍执行，仅不推送"
    )


@cli_entry
def main() -> None:
    """CLI 入口：解析子命令并分发执行。"""
    parser = argparse.ArgumentParser(
        description="观察清单监控 — 买卖区间维护与批量信号扫描",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="添加/更新观察标的")
    p_add.add_argument("--code", required=True, help="股票代码（600519 / hk00700 / usAAPL）")
    p_add.add_argument("--name", default=None, help="公司名")
    p_add.add_argument("--buy-below", type=float, default=None, help="理想买入价上限")
    p_add.add_argument("--sell-above", type=float, default=None, help="卖出关注价")
    p_add.add_argument("--note", default=None, help="论文红线/关注要点备注")

    p_rm = sub.add_parser("remove", help="移除观察标的")
    p_rm.add_argument("--code", required=True)

    sub.add_parser("list", help="查看观察清单")

    p_scan = sub.add_parser("scan", help="批量扫描触发信号")
    p_scan.add_argument("--no-cache", action="store_true", help="跳过行情缓存强制实时")
    p_scan.add_argument(
        "--notify", action="store_true", help="有触发信号时推送 WATCHLIST_WEBHOOK（钉钉/飞书/通用）"
    )

    p_sch = sub.add_parser("schedule", help="生成定时扫描配置（launchd/cron）")
    p_sch.add_argument("--every", type=int, default=60, help="扫描间隔分钟（默认60）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    if args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args.code)
    elif args.command == "list":
        cmd_list()
    elif args.command == "schedule":
        cmd_schedule(args.every)
    else:
        cmd_scan(no_cache=args.no_cache, notify=args.notify)


if __name__ == "__main__":
    main()
