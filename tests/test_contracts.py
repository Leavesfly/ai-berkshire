"""契约测试 — 验证技能注册表、frontmatter、路由表、工具文件的一致性。

这些测试保障项目结构化契约不被无意破坏：
- registry.json ↔ SKILL.md frontmatter 一致
- tools_required 中声明的工具文件存在
- depends_on 引用的技能目录存在
- 根 SKILL.md 路由表覆盖所有已注册技能

运行：python3 -m pytest tests/test_contracts.py -q
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
TOOLS_DIR = os.path.join(ROOT, "tools")
REGISTRY_PATH = os.path.join(SKILLS_DIR, "registry.json")
ROOT_SKILL_MD = os.path.join(ROOT, "SKILL.md")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry():
    """加载 skills/registry.json。"""
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def registry_skills(registry):
    """registry.json 中的技能列表。"""
    return registry["skills"]


@pytest.fixture(scope="module")
def all_skill_dirs():
    """skills/ 下所有含 SKILL.md 的目录名。"""
    dirs = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_md = os.path.join(SKILLS_DIR, entry, "SKILL.md")
        if os.path.isdir(os.path.join(SKILLS_DIR, entry)) and os.path.isfile(skill_md):
            dirs.append(entry)
    return dirs


def _parse_frontmatter(skill_name: str) -> dict:
    """解析指定技能的 SKILL.md frontmatter。"""
    skill_md = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    with open(skill_md, encoding="utf-8") as f:
        content = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        raw_val = raw_val.strip()
        if raw_val.startswith("[") and raw_val.endswith("]"):
            inner = raw_val[1:-1].strip()
            fm[key] = [i.strip().strip("'\"") for i in inner.split(",")] if inner else []
        else:
            fm[key] = raw_val.strip("'\"")
    return fm


# ---------------------------------------------------------------------------
# 1. registry.json ↔ frontmatter 一致性
# ---------------------------------------------------------------------------


class TestRegistryFrontmatterConsistency:
    def test_registry_covers_all_skill_dirs(self, registry_skills, all_skill_dirs):
        """registry.json 应包含 skills/ 下所有含 SKILL.md 的目录。"""
        registry_names = {s["name"] for s in registry_skills}
        dir_names = set(all_skill_dirs)
        missing = dir_names - registry_names
        extra = registry_names - dir_names
        assert not missing, f"registry.json 缺少技能: {sorted(missing)}"
        assert not extra, f"registry.json 含不存在的技能: {sorted(extra)}"

    def test_confirm_level_matches(self, registry_skills):
        """registry.json 的 confirm_level 应与 frontmatter 一致。"""
        for skill in registry_skills:
            fm = _parse_frontmatter(skill["name"])
            assert fm.get("confirm_level") == skill["confirm_level"], (
                f"{skill['name']}: registry confirm_level={skill['confirm_level']} "
                f"≠ frontmatter confirm_level={fm.get('confirm_level')}"
            )

    def test_tools_required_matches(self, registry_skills):
        """registry.json 的 tools_required 应与 frontmatter 一致。"""
        for skill in registry_skills:
            fm = _parse_frontmatter(skill["name"])
            fm_tools = fm.get("tools_required", [])
            assert fm_tools == skill["tools_required"], (
                f"{skill['name']}: registry tools_required={skill['tools_required']} "
                f"≠ frontmatter tools_required={fm_tools}"
            )

    def test_no_duplicate_names(self, registry_skills):
        """registry.json 中不应有重复的技能名。"""
        names = [s["name"] for s in registry_skills]
        dupes = [n for n in names if names.count(n) > 1]
        assert not dupes, f"重复技能名: {set(dupes)}"


# ---------------------------------------------------------------------------
# 2. tools_required 中工具文件存在性
# ---------------------------------------------------------------------------


class TestToolsExistence:
    def test_all_required_tools_exist(self, registry_skills):
        """每个技能声明的 tools_required 对应的文件必须存在于 tools/ 下。"""
        missing = []
        for skill in registry_skills:
            for tool in skill.get("tools_required", []):
                tool_path = os.path.join(TOOLS_DIR, tool)
                if not os.path.isfile(tool_path):
                    missing.append(f"{skill['name']} → {tool}")
        assert not missing, f"工具文件缺失: {missing}"


# ---------------------------------------------------------------------------
# 3. depends_on 引用的技能目录存在性
# ---------------------------------------------------------------------------


class TestDependsOnExistence:
    def test_all_depends_on_exist(self, all_skill_dirs):
        """每个技能 frontmatter 中 depends_on 引用的技能必须存在。"""
        missing = []
        for skill_name in all_skill_dirs:
            fm = _parse_frontmatter(skill_name)
            for dep in fm.get("depends_on", []):
                dep_dir = os.path.join(SKILLS_DIR, dep)
                if not os.path.isdir(dep_dir):
                    missing.append(f"{skill_name} → {dep}")
        assert not missing, f"depends_on 引用不存在的技能: {missing}"

    def test_no_circular_depends(self, all_skill_dirs):
        """depends_on 不应形成循环依赖。"""
        # 构建依赖图
        graph = {}
        for skill_name in all_skill_dirs:
            fm = _parse_frontmatter(skill_name)
            graph[skill_name] = fm.get("depends_on", [])

        # DFS 检测环
        visited = set()
        in_stack = set()
        cycles = []

        def dfs(node, path):
            if node in in_stack:
                cycles.append(path + [node])
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            for dep in graph.get(node, []):
                dfs(dep, path + [node])
            in_stack.discard(node)

        for skill in all_skill_dirs:
            dfs(skill, [])

        assert not cycles, f"循环依赖: {cycles}"


# ---------------------------------------------------------------------------
# 4. 根 SKILL.md 路由表覆盖所有技能
# ---------------------------------------------------------------------------


class TestRootSkillCoverage:
    def test_all_skills_in_root_routing(self, registry_skills):
        """根 SKILL.md 应提及所有已注册技能名（路由表或工具表中）。"""
        with open(ROOT_SKILL_MD, encoding="utf-8") as f:
            root_content = f.read()

        missing = []
        for skill in registry_skills:
            name = skill["name"]
            # 技能名应以 `name` 或反引号形式出现在根 SKILL.md 中
            if name not in root_content:
                missing.append(name)

        assert not missing, (
            f"根 SKILL.md 未提及以下技能（请在路由表或规范工具表中补充）: {missing}"
        )


# ---------------------------------------------------------------------------
# 5. registry.json 结构完整性
# ---------------------------------------------------------------------------


class TestRegistryStructure:
    def test_has_version(self, registry):
        """registry.json 应包含 version 字段。"""
        assert "version" in registry
        assert re.match(r"^\d+\.\d+\.\d+$", registry["version"])

    def test_skills_sorted_by_name(self, registry_skills):
        """技能列表应按名称字母序排列。"""
        names = [s["name"] for s in registry_skills]
        assert names == sorted(names), "registry.json 技能列表未按字母序排列"

    def test_required_fields(self, registry_skills):
        """每个技能条目必须包含 name/category/confirm_level/tools_required。"""
        required = {"name", "category", "confirm_level", "tools_required"}
        for skill in registry_skills:
            missing = required - set(skill.keys())
            assert not missing, f"{skill.get('name', '?')}: 缺少字段 {missing}"

    def test_valid_confirm_levels(self, registry_skills):
        """confirm_level 只允许 light/medium/heavy。"""
        valid = {"light", "medium", "heavy"}
        for skill in registry_skills:
            assert skill["confirm_level"] in valid, (
                f"{skill['name']}: 非法 confirm_level={skill['confirm_level']}"
            )

    def test_valid_categories(self, registry_skills):
        """category 只允许已知分类。"""
        valid = {"discovery", "deep-research", "decision", "monitoring", "content", "perspective", "shared-spec"}
        for skill in registry_skills:
            assert skill["category"] in valid, (
                f"{skill['name']}: 非法 category={skill['category']}（请在 CATEGORY_MAP 中补充）"
            )


# ---------------------------------------------------------------------------
# 6. skill_registry.py --check 通过（生成器与文件同步）
# ---------------------------------------------------------------------------


class TestRegistryGeneratorSync:
    def test_generator_check_passes(self):
        """skill_registry.py --check 应返回退出码 0（registry 与 frontmatter 同步）。"""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, os.path.join(TOOLS_DIR, "skill_registry.py"), "--check"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, (
            f"registry 不同步:\n{result.stdout}{result.stderr}"
        )
