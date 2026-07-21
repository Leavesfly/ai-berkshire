#!/usr/bin/env python3
"""AI Berkshire 报告图表生成工具 — matplotlib 输出出版级 PNG。

可视化三级方案的首选级（见 references/report-visuals.md）：
    1) 本工具可用 → 生成 PNG，Markdown 以 ![](charts/xxx.png) 引用；
    2) matplotlib 缺失/损坏 → 本工具退出码 1，调用方降级为 Mermaid 代码块；
    3) 渲染环境不支持 Mermaid → 再降级为符号/表格方案。

子命令与报告图表类型对应：
    trend      类型1 趋势类（营收/利润 3-5 年走势，单/多系列 bar 或 line）
    structure  类型2 结构类（收入结构/持仓占比，饼图）
    compare    类型5 对比类（公司 vs 同业关键指标，分组柱状）
    quadrant   类型7 象限类（持仓质量×估值定位，散点+四象限）

用法示例（路径以技能根目录为基准）：
    python3 tools/chart_gen.py trend --title "营业收入趋势（亿元）" \
      --x '[2021,2022,2023,2024,2025]' --series '{"营收":[5601,5546,6090,6603,7200]}' \
      --ylabel 亿元 --output reports/腾讯/charts/revenue-trend.png
    python3 tools/chart_gen.py structure --title "收入结构（2025）" \
      --values '{"增值服务":48,"网络广告":19,"金融科技与企业服务":31,"其他":2}' \
      --output reports/腾讯/charts/revenue-structure.png
    python3 tools/chart_gen.py compare --title "毛利率对比（%）" \
      --x '[2023,2024,2025]' --series '{"公司A":[42.1,43.5,45.0],"公司B":[35.2,34.8,33.9]}' \
      --ylabel "%" --output reports/公司A/charts/margin-compare.png
    python3 tools/chart_gen.py quadrant --title "持仓质量×估值定位" \
      --points '{"腾讯":[0.45,0.9],"茅台":[0.55,0.85]}' \
      --xlabel "估值便宜 → 昂贵" --ylabel "质量低 → 高" \
      --output reports/portfolio-charts/quadrant.png

退出码：0=生成成功 / 1=matplotlib 不可用（降级 Mermaid/表格，不算失败）/ 2=参数错误。
依赖：matplotlib（可选依赖，缺失时整个体系自动降级，pip install matplotlib 即可启用）。
"""

import argparse
import contextlib
import io
import os
import sys

from utils import EXIT_BAD_ARGS, EXIT_OK, EXIT_UNAVAILABLE
from utils import cli_entry as _cli_entry
from utils import load_json_arg as _load_json_arg

# 与投研报告风格匹配的克制配色（依次取用）
_PALETTE = ["#2F5C8F", "#C0504D", "#4F8F6B", "#8064A2", "#E0A030", "#6B7B8C"]
_CJK_FONTS = [
    "PingFang SC",
    "Hiragino Sans GB",
    "Heiti TC",
    "STHeiti",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
]


def _load_mpl():
    """加载 matplotlib；缺失或损坏（如 NumPy ABI 不兼容）都视为不可用。"""
    try:
        # 静默导入期间第三方库的告警/回溯噪音，失败时只给出精简降级指引
        with contextlib.redirect_stderr(io.StringIO()):
            import matplotlib

            matplotlib.use("Agg")  # 无显示环境也可渲染
            import matplotlib.pyplot as plt
            from matplotlib import font_manager
    except Exception as e:  # ImportError 及编译不兼容等一切异常
        print(f"⚠️ matplotlib 不可用: {type(e).__name__}: {e}", file=sys.stderr)
        print(
            "   降级路径：按 references/report-visuals.md 用 Mermaid 代码块作图，", file=sys.stderr
        )
        print("   仍不支持时用符号/表格方案；启用本工具：pip install matplotlib", file=sys.stderr)
        sys.exit(EXIT_UNAVAILABLE)

    # 中文字体：按候选列表选第一个可用的，避免中文标题变方块
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_FONTS:
        if name in available:
            matplotlib.rcParams["font.sans-serif"] = [name] + matplotlib.rcParams["font.sans-serif"]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    return plt


def _validate_series(x, series):
    """校验 x 轴与各系列等长且均为数值。"""
    if not isinstance(x, list) or not x:
        print("❌ --x 必须是非空 JSON 数组，如 [2021,2022,2023]")
        sys.exit(EXIT_BAD_ARGS)
    if not isinstance(series, dict) or not series:
        print("❌ --series 必须是 {系列名: [数值...]} 形式的 JSON 对象")
        sys.exit(EXIT_BAD_ARGS)
    for name, vals in series.items():
        if not isinstance(vals, list) or len(vals) != len(x):
            print(
                f"❌ 系列「{name}」长度 {len(vals) if isinstance(vals, list) else '非数组'} 与 x 轴长度 {len(x)} 不一致"
            )
            sys.exit(EXIT_BAD_ARGS)
        if not all(isinstance(v, (int, float)) for v in vals):
            print(f"❌ 系列「{name}」存在非数值元素（不要带单位/逗号/百分号）")
            sys.exit(EXIT_BAD_ARGS)


def _style_axes(ax):
    """统一坐标轴风格：去上右边框，浅色横向网格。"""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _save(plt, fig, output):
    """落盘 PNG（自动建目录），输出成功信息与 Markdown 引用片段。"""
    out_dir = os.path.dirname(output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"✅ 图表已生成: {output}")
    print(
        f"   Markdown 引用（与报告同目录时）: ![图表]({os.path.relpath(output, os.path.dirname(out_dir) or '.')})"
    )


def cmd_trend(args, plt):
    """类型1 趋势类：单/多系列柱状或折线。"""
    x = _load_json_arg(args.x, "--x", "[2021,2022,2023,2024,2025]")
    series = _load_json_arg(args.series, "--series", '{"营收":[5601,5546,6090,6603,7200]}')
    _validate_series(x, series)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [str(v) for v in x]
    n = len(series)
    if args.kind == "line":
        for i, (name, vals) in enumerate(series.items()):
            ax.plot(
                labels,
                vals,
                marker="o",
                linewidth=2,
                color=_PALETTE[i % len(_PALETTE)],
                label=name,
                zorder=3,
            )
    else:
        width = 0.8 / n
        for i, (name, vals) in enumerate(series.items()):
            pos = [j + i * width - 0.4 + width / 2 for j in range(len(labels))]
            bars = ax.bar(
                pos,
                vals,
                width=width * 0.92,
                color=_PALETTE[i % len(_PALETTE)],
                label=name,
                zorder=3,
            )
            if n == 1:  # 单系列时标注数值
                ax.bar_label(bars, fmt="%g", padding=2, fontsize=9, color="#444444")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
    _style_axes(ax)
    if args.ylabel:
        ax.set_ylabel(args.ylabel)
    ax.set_title(args.title, fontsize=13, pad=12)
    if n > 1:
        ax.legend(frameon=False, fontsize=9)
    _save(plt, fig, args.output)


def cmd_structure(args, plt):
    """类型2 结构类：占比饼图（大分部→小分部顺时针）。"""
    values = _load_json_arg(args.values, "--values", '{"增值服务":48,"网络广告":19}')
    if not isinstance(values, dict) or not values:
        print("❌ --values 必须是 {分部名: 数值} 形式的非空 JSON 对象")
        sys.exit(EXIT_BAD_ARGS)
    if not all(isinstance(v, (int, float)) and v >= 0 for v in values.values()):
        print("❌ --values 各占比必须是非负数值")
        sys.exit(EXIT_BAD_ARGS)
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    vals = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(6.5, 5))
    wedges, _, autotexts = ax.pie(
        vals,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
        colors=[_PALETTE[i % len(_PALETTE)] for i in range(len(vals))],
        wedgeprops={"linewidth": 1.2, "edgecolor": "white"},
        textprops={"fontsize": 10},
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(9)
    ax.set_title(args.title, fontsize=13, pad=12)
    _save(plt, fig, args.output)


def cmd_compare(args, plt):
    """类型5 对比类：多系列分组柱状（公司 vs 同业）。"""
    args.kind = "bar"
    cmd_trend(args, plt)


def cmd_quadrant(args, plt):
    """类型7 象限类：0-1 坐标散点 + 四象限分区。"""
    points = _load_json_arg(args.points, "--points", '{"腾讯":[0.45,0.9],"茅台":[0.55,0.85]}')
    if not isinstance(points, dict) or not points:
        print("❌ --points 必须是 {名称: [x,y]} 形式的非空 JSON 对象（坐标取值 0-1）")
        sys.exit(EXIT_BAD_ARGS)
    for name, xy in points.items():
        if (
            not isinstance(xy, list)
            or len(xy) != 2
            or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in xy)
        ):
            print(f"❌ 点「{name}」坐标必须是 [x,y] 且取值 0-1: {xy}")
            sys.exit(EXIT_BAD_ARGS)
    quad_labels = (
        _load_json_arg(
            args.labels, "--labels", '["好公司贵价格","好公司好价格","价值陷阱警惕","退出"]'
        )
        if args.labels
        else [
            "好公司贵价格（持有不加）",
            "好公司好价格（重点配置）",
            "差公司低估值（价值陷阱警惕）",
            "差公司高估值（退出）",
        ]
    )
    if not isinstance(quad_labels, list) or len(quad_labels) != 4:
        print(
            "❌ --labels 必须是 4 元素 JSON 数组，顺序为 [右上, 左上, 左下, 右下]（同 Mermaid quadrant-1..4）"
        )
        sys.exit(EXIT_BAD_ARGS)

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    # 象限底色与分割线
    ax.axhline(0.5, color="#BBBBBB", linewidth=1, linestyle="--", zorder=1)
    ax.axvline(0.5, color="#BBBBBB", linewidth=1, linestyle="--", zorder=1)
    corners = [(0.75, 0.95), (0.25, 0.95), (0.25, 0.05), (0.75, 0.05)]  # 右上/左上/左下/右下
    for (cx, cy), text in zip(corners, quad_labels):
        ax.text(cx, cy, text, ha="center", va="center", fontsize=9, color="#999999", zorder=2)
    for i, (name, (px, py)) in enumerate(points.items()):
        ax.scatter(
            px,
            py,
            s=90,
            color=_PALETTE[i % len(_PALETTE)],
            zorder=3,
            edgecolors="white",
            linewidths=1.2,
        )
        ax.annotate(
            name, (px, py), textcoords="offset points", xytext=(8, 6), fontsize=10, zorder=4
        )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if args.xlabel:
        ax.set_xlabel(args.xlabel)
    if args.ylabel:
        ax.set_ylabel(args.ylabel)
    ax.set_title(args.title, fontsize=13, pad=12)
    _save(plt, fig, args.output)


@_cli_entry
def main():
    parser = argparse.ArgumentParser(
        description="报告图表生成 — matplotlib 输出 PNG（不可用时退出码 1，降级 Mermaid）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--title", required=True, help="图表标题")
    common.add_argument("--output", required=True, help="输出 PNG 路径（自动创建目录）")

    tr = sub.add_parser("trend", help="类型1 趋势类（柱状/折线）", parents=[common])
    tr.add_argument("--x", required=True, help="x 轴 JSON 数组，如 [2021,2022,2023]")
    tr.add_argument("--series", required=True, help="JSON: {系列名: [数值...]}")
    tr.add_argument("--ylabel", default="", help="y 轴单位标签")
    tr.add_argument("--kind", choices=["bar", "line"], default="bar")

    st = sub.add_parser("structure", help="类型2 结构类（饼图）", parents=[common])
    st.add_argument("--values", required=True, help="JSON: {分部名: 占比数值}")

    cp = sub.add_parser("compare", help="类型5 对比类（分组柱状）", parents=[common])
    cp.add_argument("--x", required=True, help="x 轴 JSON 数组")
    cp.add_argument("--series", required=True, help="JSON: {公司名: [数值...]}，至少 2 个系列")
    cp.add_argument("--ylabel", default="", help="y 轴单位标签")

    qd = sub.add_parser("quadrant", help="类型7 象限类（质量×估值散点）", parents=[common])
    qd.add_argument("--points", required=True, help="JSON: {名称: [x,y]}，坐标 0-1")
    qd.add_argument("--xlabel", default="估值便宜 → 昂贵")
    qd.add_argument("--ylabel", default="质量低 → 高")
    qd.add_argument("--labels", default=None, help="可选，4 元素 JSON 数组 [右上,左上,左下,右下]")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(EXIT_BAD_ARGS)

    plt = _load_mpl()  # 不可用时在此退出码 1
    {
        "trend": cmd_trend,
        "structure": cmd_structure,
        "compare": cmd_compare,
        "quadrant": cmd_quadrant,
    }[args.command](args, plt)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
