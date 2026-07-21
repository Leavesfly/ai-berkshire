#!/usr/bin/env python3
"""公司档案库 — 已验证事实的跨会话沉淀（data/companies/{代码}/facts.json）。

解决"每次研究都重新取数验证"的浪费：研究流程中经过双源验证的**稳定事实**
（股本结构、商业模式要点、历史关键数据、论文红线等）落盘归档，
下次任何流程研究同一家公司时先 get 复用，只刷新时效性数据（股价/市值/最新财报）。

分类约定（category）：
  profile    商业模式/主营构成等定性要点（很少变化）
  capital    股本/股权结构（股本变动、大股东、AB股）
  financial  历史财务关键值（"2025年营收6603亿"这类不可变事实）
  valuation  历史估值锚点（当时的判断，带日期看）
  redline    论文红线（来自 thesis-tracker）
  event      重大事件时间线（并购/回购/管理层变动）

用法（由 Skills 自动调用）：
    python3 tools/company_facts.py set hk00700 --name 腾讯 --category financial \\
        --key "2025年营收" --value "6603亿CNY" --source "2025年报+东财双源验证"
    python3 tools/company_facts.py get hk00700                    # 全部档案
    python3 tools/company_facts.py get hk00700 --category capital
    python3 tools/company_facts.py remove hk00700 --key "2025年营收"
    python3 tools/company_facts.py list                           # 已建档公司

纪律：只沉淀**经过双源验证的稳定事实**；时效性数据（现价/市值/PE）禁止入库；
复用时报告中标注"档案数据（{验证日期}验证）"。

依赖：零外部依赖。退出码：0=成功 / 1=未找到 / 2=参数错误。
"""

import argparse
import json
import os
import sys
from datetime import datetime

from utils import EXIT_BAD_ARGS, EXIT_FAIL, EXIT_OK

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASE = os.path.join(_ROOT, "data", "companies")

_CATEGORIES = ("profile", "capital", "financial", "valuation", "redline", "event")
# 时效性字段黑名单：这些值随时变化，入库只会制造过期数据
_VOLATILE_WORDS = ("现价", "股价", "市值", "最新价", "当前PE", "当前PB")


def _safe_key(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum() or ch in "._-")


def _path(code: str) -> str:
    return os.path.join(_BASE, _safe_key(code), "facts.json")


def _load(code: str) -> dict:
    try:
        with open(_path(code), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"code": code, "name": "", "facts": []}


def _save(code: str, doc: dict):
    p = _path(code)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    doc["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def cmd_set(args):
    if args.category not in _CATEGORIES:
        print(f"❌ --category 仅支持: {' / '.join(_CATEGORIES)}")
        sys.exit(EXIT_BAD_ARGS)
    if any(w in args.key for w in _VOLATILE_WORDS):
        print(f"❌ 「{args.key}」是时效性数据，禁止入档案库（每次研究实时取数）")
        sys.exit(EXIT_BAD_ARGS)
    doc = _load(args.code)
    if args.name:
        doc["name"] = args.name
    for fact in doc["facts"]:
        if fact["key"] == args.key and fact["category"] == args.category:
            fact.update(
                {
                    "value": args.value,
                    "source": args.source or fact.get("source", ""),
                    "verified": datetime.now().strftime("%Y-%m-%d"),
                }
            )
            _save(args.code, doc)
            print(f"  ✅ 已更新事实: [{args.category}] {args.key} = {args.value}")
            return
    doc["facts"].append(
        {
            "category": args.category,
            "key": args.key,
            "value": args.value,
            "source": args.source or "",
            "verified": datetime.now().strftime("%Y-%m-%d"),
        }
    )
    _save(args.code, doc)
    print(
        f"  ✅ 已归档事实: [{args.category}] {args.key} = {args.value}"
        f"（{doc.get('name') or args.code} 共 {len(doc['facts'])} 条）"
    )


def cmd_get(code: str, category=None):
    doc = _load(code)
    facts = doc["facts"]
    if category:
        facts = [f for f in facts if f["category"] == category]
    if not facts:
        print(f"  （{code} 暂无{'该分类' if category else ''}档案——研究后用 set 沉淀已验证事实）")
        sys.exit(EXIT_FAIL)
    print("=" * 70)
    print(f"公司档案: {doc.get('name') or code}（{code}）— 更新于 {doc.get('updated', '-')}")
    print("=" * 70)
    for cat in _CATEGORIES:
        group = [f for f in facts if f["category"] == cat]
        if not group:
            continue
        print(f"  [{cat}]")
        for f in group:
            src = (
                f"（{f['source']}，{f['verified']} 验证）"
                if f.get("source")
                else f"（{f['verified']} 验证）"
            )
            print(f"    {f['key']}: {f['value']} {src}")
    print()
    print("  提示: 引用时在报告中标注「档案数据（{验证日期}验证）」；发现事实已过期请用 set 更新")


def cmd_remove(code: str, key: str):
    doc = _load(code)
    remain = [f for f in doc["facts"] if f["key"] != key]
    if len(remain) == len(doc["facts"]):
        print(f"  ⚠️ 档案中没有键「{key}」")
        sys.exit(EXIT_FAIL)
    doc["facts"] = remain
    _save(code, doc)
    print(f"  ✅ 已移除「{key}」，剩余 {len(remain)} 条")


def cmd_list():
    if not os.path.isdir(_BASE):
        print("  （尚无公司档案）")
        return
    entries = []
    for sub in sorted(os.listdir(_BASE)):
        p = os.path.join(_BASE, sub, "facts.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    doc = json.load(f)
                entries.append(
                    (
                        doc.get("name") or sub,
                        doc.get("code", sub),
                        len(doc.get("facts", [])),
                        doc.get("updated", "-"),
                    )
                )
            except (OSError, json.JSONDecodeError):
                continue
    if not entries:
        print("  （尚无公司档案）")
        return
    print("=" * 60)
    print(f"公司档案库（{len(entries)} 家）— data/companies/")
    print("=" * 60)
    for name, code, n, updated in entries:
        print(f"  {name:12s} {code:10s} {n:>3d} 条事实  更新 {updated}")


def main():
    parser = argparse.ArgumentParser(
        description="公司档案库 — 已验证事实的跨会话沉淀",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_set = sub.add_parser("set", help="归档/更新一条已验证事实")
    p_set.add_argument("code", help="股票代码（600519 / hk00700 / usAAPL）")
    p_set.add_argument("--name", default=None, help="公司名（首次建档时填）")
    p_set.add_argument("--category", required=True, help=f"分类: {' / '.join(_CATEGORIES)}")
    p_set.add_argument("--key", required=True, help="事实名，如「2025年营收」「总股本」")
    p_set.add_argument("--value", required=True, help="事实值（含单位与币种）")
    p_set.add_argument("--source", default="", help="验证来源，如「2025年报+东财双源验证」")

    p_get = sub.add_parser("get", help="读取公司档案")
    p_get.add_argument("code")
    p_get.add_argument("--category", default=None, help=f"只看某分类: {' / '.join(_CATEGORIES)}")

    p_rm = sub.add_parser("remove", help="移除一条事实")
    p_rm.add_argument("code")
    p_rm.add_argument("--key", required=True)

    sub.add_parser("list", help="列出已建档公司")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    if args.command == "set":
        cmd_set(args)
    elif args.command == "get":
        cmd_get(args.code, args.category)
    elif args.command == "remove":
        cmd_remove(args.code, args.key)
    else:
        cmd_list()
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
