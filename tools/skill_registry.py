#!/usr/bin/env python3
"""技能注册表自动生成器 — 从 skills/*/SKILL.md frontmatter 生成 registry.json。

消除 registry.json 与 frontmatter 的手工双维护风险：
运行本脚本后，skills/registry.json 将由各 SKILL.md 的 frontmatter 自动派生。

用法：
    python3 tools/skill_registry.py          # 生成并写入 skills/registry.json
    python3 tools/skill_registry.py --check  # 仅校验一致性，不写入（CI 用）

退出码：0=成功/一致 / 1=不一致（--check 模式） / 2=参数或文件错误
"""

import argparse
import json
import os
import re
import sys

# 项目根目录（tools/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
REGISTRY_PATH = os.path.join(SKILLS_DIR, "registry.json")

# ---------------------------------------------------------------------------
# 技能分类映射（对应根 SKILL.md 路由表的投资生命周期分组）
# 新增 skill 时在此补充一行即可；make new-skill 脚手架会提示。
# ---------------------------------------------------------------------------

CATEGORY_MAP = {
    # ① 发现与筛选
    "bottleneck-hunter": "discovery",
    "industry-funnel": "discovery",
    "industry-research": "discovery",
    "quality-screen": "discovery",
    # ② 深度研究
    "investment-research": "deep-research",
    "investment-team": "deep-research",
    "management-deep-dive": "deep-research",
    "private-company-research": "deep-research",
    "red-team": "deep-research",
    # ③ 买卖决策
    "exit-review": "decision",
    "investment-checklist": "decision",
    # ④ 持有与监控
    "earnings-review": "monitoring",
    "masters-portfolio": "monitoring",
    "morning-brief": "monitoring",
    "news-pulse": "monitoring",
    "portfolio-review": "monitoring",
    "self-review": "monitoring",
    "thesis-drift": "monitoring",
    "thesis-tracker": "monitoring",
    "track-record": "monitoring",
    "watchlist-monitor": "monitoring",
    # ⑤ 内容创作
    "deep-company-series": "content",
    "earnings-team": "content",
    "wechat-article": "content",
    # ⑥ 视角问答
    "dyp-ask": "perspective",
    # 共享规范
    "financial-data": "shared-spec",
}


def parse_frontmatter(skill_md_path: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter（简易解析器，无外部依赖）。

    支持格式：
        ---
        key: value
        key: [item1, item2]
        ---
    """
    with open(skill_md_path, encoding="utf-8") as f:
        content = f.read()

    # 提取 --- 之间的 frontmatter 块
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}

    fm = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        raw_val = raw_val.strip()

        # 解析 YAML 列表 [a, b, c]
        if raw_val.startswith("[") and raw_val.endswith("]"):
            inner = raw_val[1:-1].strip()
            if inner:
                fm[key] = [item.strip().strip("'\"") for item in inner.split(",")]
            else:
                fm[key] = []
        else:
            fm[key] = raw_val.strip("'\"")

    return fm


def scan_skills() -> list:
    """扫描 skills/ 目录，返回按名称排序的技能注册信息列表。"""
    skills = []

    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_dir = os.path.join(SKILLS_DIR, entry)
        skill_md = os.path.join(skill_dir, "SKILL.md")

        if not os.path.isdir(skill_dir) or not os.path.isfile(skill_md):
            continue

        fm = parse_frontmatter(skill_md)
        if not fm.get("name"):
            continue

        name = fm["name"]
        category = CATEGORY_MAP.get(name)
        if category is None:
            # 未在映射表中的 skill：用 frontmatter type 或 fallback
            category = fm.get("type", "unknown")
            if category == "executable":
                category = "unknown"  # 提醒开发者补充映射
                print(f"⚠️  技能 '{name}' 未在 CATEGORY_MAP 中定义分类，使用 'unknown'", file=sys.stderr)

        skills.append({
            "name": name,
            "category": category,
            "confirm_level": fm.get("confirm_level", "medium"),
            "tools_required": fm.get("tools_required", []),
        })

    return skills


def build_registry(skills: list) -> dict:
    """构建完整的 registry.json 结构。"""
    # 读取当前 registry 获取版本号（保持版本同步）
    version = "1.2.0"
    if os.path.isfile(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, encoding="utf-8") as f:
                existing = json.load(f)
            version = existing.get("version", version)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "$schema": "技能注册表 — 机器可读的技能清单，供 doctor.py 完整性校验与未来自动化使用",
        "version": version,
        "skills": skills,
    }


def main():
    parser = argparse.ArgumentParser(description="AI Berkshire 技能注册表生成器")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅校验 registry.json 与 frontmatter 一致性，不写入文件",
    )
    args = parser.parse_args()

    skills = scan_skills()
    if not skills:
        print("❌ 未找到任何技能（skills/*/SKILL.md）", file=sys.stderr)
        sys.exit(2)

    registry = build_registry(skills)
    generated = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        # 校验模式：比对现有文件
        if not os.path.isfile(REGISTRY_PATH):
            print("❌ skills/registry.json 不存在，请先运行 make registry", file=sys.stderr)
            sys.exit(1)
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            existing_content = f.read()
        if existing_content.strip() == generated.strip():
            print(f"✅ registry.json 与 frontmatter 一致（{len(skills)} 个技能）")
            sys.exit(0)
        else:
            print("❌ registry.json 与 frontmatter 不一致，请运行 make registry 更新", file=sys.stderr)
            # 输出差异摘要
            try:
                existing = json.loads(existing_content)
                existing_names = {s["name"] for s in existing.get("skills", [])}
                generated_names = {s["name"] for s in skills}
                added = generated_names - existing_names
                removed = existing_names - generated_names
                if added:
                    print(f"   新增: {sorted(added)}", file=sys.stderr)
                if removed:
                    print(f"   移除: {sorted(removed)}", file=sys.stderr)
                if not added and not removed:
                    print("   字段差异（confirm_level/tools_required/category 变更）", file=sys.stderr)
            except json.JSONDecodeError:
                pass
            sys.exit(1)
    else:
        # 写入模式
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            f.write(generated)
        print(f"✅ 已生成 skills/registry.json（{len(skills)} 个技能）")
        sys.exit(0)


if __name__ == "__main__":
    main()
