# AI Berkshire 开发快捷命令
# 用法: make lint / make format / make test / make check / make new-skill NAME=xxx [TYPE=shared-spec]

.PHONY: lint format test check doctor registry new-skill

## 代码检查（ruff lint）
lint:
	ruff check tools/*.py tests/

## 代码格式化（ruff format）
format:
	ruff format tools/*.py tests/

## 运行测试
test:
	python3 -m pytest tests/ -q

## 完整检查（lint + test）
check: lint test

## 环境自检
doctor:
	python3 tools/doctor.py

## 重新生成 skills/registry.json（从各 SKILL.md frontmatter 自动派生）
registry:
	python3 tools/skill_registry.py

## 创建新技能脚手架（用法: make new-skill NAME=my-skill [TYPE=shared-spec]）
new-skill:
	@if [ -z "$(NAME)" ]; then echo "用法: make new-skill NAME=my-skill [TYPE=shared-spec]"; exit 1; fi
	@mkdir -p skills/$(NAME)
	@echo '---' > skills/$(NAME)/SKILL.md
	@echo 'name: $(NAME)' >> skills/$(NAME)/SKILL.md
	@echo 'description: TODO—一句话描述技能用途与触发场景。' >> skills/$(NAME)/SKILL.md
	@echo 'type: $(or $(TYPE),executable)' >> skills/$(NAME)/SKILL.md
	@echo 'confirm_level: medium' >> skills/$(NAME)/SKILL.md
	@echo 'tools_required: []' >> skills/$(NAME)/SKILL.md
	@echo 'depends_on: [financial-data]' >> skills/$(NAME)/SKILL.md
	@echo '---' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '# $(NAME)：TODO 标题' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '对 $$ARGUMENTS 执行 TODO。' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '## 执行流程' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '### 第一步：TODO' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '## 输出契约' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '- 报告路径：`reports/{公司名}/{公司名}-$(NAME)-{YYYYMMDD}.md`' >> skills/$(NAME)/SKILL.md
	@echo '- 元信息头：按 `references/report-conventions.md`' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '## 准出流程' >> skills/$(NAME)/SKILL.md
	@echo '' >> skills/$(NAME)/SKILL.md
	@echo '按 [`references/audit-protocol.md`](../../references/audit-protocol.md) 执行。' >> skills/$(NAME)/SKILL.md
	@echo "✅ 已创建 skills/$(NAME)/SKILL.md 脚手架"
	@echo "⚠️  后续步骤：1) 编辑 SKILL.md  2) 在 tools/skill_registry.py CATEGORY_MAP 中补充分类  3) make registry  4) 在根 SKILL.md 路由表中注册"
