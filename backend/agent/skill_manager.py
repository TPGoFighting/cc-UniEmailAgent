"""技能库双向流转 — 前置读取 (注入 Prompt) + 后置反思 (经验沉淀)"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
GLOBAL_RULES_FILE = SKILLS_DIR / "global_crawling_rules.md"
CRAWL_KNOWLEDGE_FILE = SKILLS_DIR / "crawl_knowledge.md"

# ── 数据结构 ──

STANDARD_HEADERS = ["院校名称", "教师姓名", "所在学院", "职称", "邮箱", "官网主页链接"]


def _resolve_skills_dir() -> Path:
    """返回技能目录，确保存在。"""
    SKILLS_DIR.mkdir(exist_ok=True)
    return SKILLS_DIR


# ═══════════════════════════════════════════════════════════════
# 前置读取：加载技能注入 System Prompt
# ═══════════════════════════════════════════════════════════════

def load_skills_prompt(university_name: str = "") -> str:
    """前置读取技能库，返回要注入 Agent System Prompt 的经验知识文本。

    按优先级合并：
    1. crawl_knowledge.md（标准 Markdown 格式，含各校策略）
    2. global_crawling_rules.md（踩坑记录，含正确流程）
    3. 如果提供了大学名称，额外提取该校相关的 JSON 元数据摘要
    """
    parts: list[str] = []

    # 1. 读取标准技能汇总
    if CRAWL_KNOWLEDGE_FILE.exists():
        try:
            text = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()
            # 去除 YAML frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            if text:
                parts.append(text)
        except OSError:
            pass

    # 2. 读取全局规则（含踩坑记录）
    if GLOBAL_RULES_FILE.exists():
        try:
            text = GLOBAL_RULES_FILE.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        except OSError:
            pass

    # 3. 大学专属 JSON 摘要
    if university_name:
        uni_summary = _load_university_json_summary(university_name)
        if uni_summary:
            parts.append(uni_summary)

    if not parts:
        return ""

    header = (
        "## 📚 全局共享爬取经验库（技能知识注入）\n\n"
        "以下是系统从过往所有任务中自动提炼的高校爬取经验与避坑指南。"
        "**请在执行本次爬取任务前仔细阅读并严格遵守**，避免重蹈历史覆辙：\n\n"
    )

    return header + "\n\n---\n\n".join(parts) + "\n\n"


def _load_university_json_summary(university_name: str) -> str:
    """从大学专属 JSON 文件中提取摘要信息。"""
    lines: list[str] = []
    for jf in sorted(SKILLS_DIR.glob("*.json")):
        if university_name not in jf.name:
            continue
        try:
            import json
            data = json.loads(jf.read_text(encoding="utf-8"))
            lines.append(f"### {data.get('university', jf.stem)} 历史记录")
            lines.append(f"- 任务: {data.get('user_query', '')[:120]}")
            files = data.get("files", [])
            if files:
                lines.append(f"- 历史产出: {', '.join(files[:5])}")
            lines.append(f"- 消息量: {data.get('message_count', 0)} | 状态: {data.get('status', '?')}")
            lines.append("")
        except Exception:
            pass
    return "\n".join(lines) if lines else ""


# ═══════════════════════════════════════════════════════════════
# 后置反思：分析日志 → 提取新策略 → 写入技能库
# ═══════════════════════════════════════════════════════════════

_REFLECTION_SYSTEM_PROMPT = """你是一个爬虫经验分析师。请根据以下任务日志，总结出这次爬取中遇到的**新难点和解决策略**。

要求：
1. 只提取之前可能不知道的新发现（如特殊的动态渲染方式、新的反爬策略、特定网站的 DOM 结构特点、邮箱编码规则等）
2. 如果本次任务没有值得记录的新发现，回复「无新发现」
3. 每条发现格式：`- **难点**: <描述> → **解决**: <方法>`
4. 如果有特定 URL/选择器/CSS 类名值得记录，也请列出
5. 用中文回复，控制在 300 字以内

请直接输出 Markdown 格式的发现列表，不要有多余的开场白。"""


async def reflect_and_save(
    task_id: str,
    university_name: str,
    messages: list[dict],
) -> str | None:
    """后置反思：用 LLM 分析任务日志，提取新经验并持久化到技能库。

    返回写入的文件路径，若无需更新则返回 None。
    """
    # 提取日志和关键内容
    log_text = _extract_relevant_logs(messages)
    if len(log_text) < 200:
        logger.info(f"[SkillManager] 任务 {task_id[:8]} 日志过短，跳过反思")
        return None

    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[SkillManager] 无 API Key，跳过反思总结")
        return None

    # 调用 LLM 反思
    reflection = await _llm_reflection(api_key, university_name, log_text)
    if not reflection or "无新发现" in reflection:
        logger.info(f"[SkillManager] 任务 {task_id[:8]} 无新发现需要记录")
        return None

    # 写入技能文件
    return _write_reflection(task_id, university_name, reflection)


def _extract_relevant_logs(messages: list[dict]) -> str:
    """从任务消息中提取对反思有价值的内容。"""
    parts: list[str] = []

    for m in messages:
        content = m.get("content", "") or m.get("message", "")
        if not content:
            continue

        role = m.get("role", "")
        msg_type = m.get("type", "")

        # Agent 思考/工具调用日志
        if role in ("agent", "log") or msg_type in ("log", "agent", "text"):
            parts.append(content[:500])
        # 错误信息
        elif role == "error" or msg_type == "error":
            parts.append(f"[ERROR] {content[:300]}")

        # 只保留最近的日志（避免过长）
        if len(parts) > 80:
            break

    return "\n---\n".join(parts[-60:])  # 只保留最近 60 条


async def _llm_reflection(api_key: str, university_name: str, log_text: str) -> str | None:
    """调用 LLM 进行反思总结。"""
    try:
        from openai import AsyncOpenAI

        if os.environ.get("DEEPSEEK_API_KEY"):
            client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
            model = "deepseek-chat"
        else:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=os.environ.get("OPENAI_BASE_URL") or None,
            )
            model = os.environ.get("OPENAI_API_MODEL") or "gpt-4o-mini"

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"【目标大学】{university_name}\n\n【任务日志】\n{log_text[:4000]}"},
            ],
            max_tokens=500,
            temperature=0.3,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"[SkillManager] LLM 反思结果 ({len(result)} 字): {result[:120]}...")
        return result

    except Exception as e:
        logger.warning(f"[SkillManager] LLM 反思失败: {e}")
        return None


def _write_reflection(task_id: str, university_name: str, reflection: str) -> str | None:
    """将反思结果写入技能文件。

    优先写入各校专属文件，再追加到通用技能汇总。
    """
    _resolve_skills_dir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    section = f"\n\n## 🏫 {university_name} — {ts}（任务 {task_id[:8]}）\n\n{reflection}\n"

    # 1. 写入/追加到 crawl_knowledge.md
    try:
        if CRAWL_KNOWLEDGE_FILE.exists():
            existing = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8")
            # 检查是否已有该校记录，有则追加到该节下，无则新开一节
            if f"## 🏫 {university_name}" in existing:
                # 在该校最后一个 section 后追加
                pattern = rf"(## 🏫 {re.escape(university_name)}.*?)(?=\n## 🏫 |\Z)"
                updated = re.sub(pattern, rf"\1{section}", existing, count=1, flags=re.DOTALL)
            else:
                updated = existing.rstrip() + section
        else:
            updated = (
                "# 🧠 高校爬虫技能知识库\n\n"
                "本文件由系统自动维护，记录各高校爬取过程中的实战经验和避坑指南。\n\n"
                "---\n"
                + section
            )

        CRAWL_KNOWLEDGE_FILE.write_text(updated, encoding="utf-8")
        logger.info(f"[SkillManager] 反思已写入: {CRAWL_KNOWLEDGE_FILE.name}")
    except OSError as e:
        logger.error(f"[SkillManager] 写入失败: {e}")
        return None

    # 2. 同时更新任务专属 JSON（保留元数据追溯）
    _update_skill_json(task_id, university_name, reflection)

    return str(CRAWL_KNOWLEDGE_FILE)


def _update_skill_json(task_id: str, university_name: str, reflection: str) -> None:
    """更新任务专属 JSON 元数据文件。"""
    import json as _json
    skill_file = SKILLS_DIR / f"{university_name}_{task_id[:8]}.json"
    try:
        data = {}
        if skill_file.exists():
            data = _json.loads(skill_file.read_text(encoding="utf-8"))
        data["reflection"] = reflection[:500]
        data["reflected_at"] = datetime.now().isoformat()
        skill_file.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════
# 数据规范注入
# ═══════════════════════════════════════════════════════════════

def get_data_schema_prompt() -> str:
    """返回数据规范要求的 prompt 注入。"""
    return (
        "## 📋 爬虫数据规范（强制要求）\n\n"
        "采集结果必须包含以下结构化字段，不可缺失：\n\n"
        f"| {' | '.join(STANDARD_HEADERS)} |\n"
        f"|{' | '.join(['---'] * len(STANDARD_HEADERS))} |\n\n"
        "- 院校名称：大学全称\n"
        "- 教师姓名：完整中文或英文姓名\n"
        "- 所在学院：所属院系全称\n"
        "- 职称：教授/副教授/讲师/研究员等\n"
        "- 邮箱：有效的个人邮箱地址\n"
        "- 官网主页链接：教师个人主页 URL\n"
    )


def get_task_isolation_prompt(task_id: str, inherited_task_id: str = "") -> str:
    """返回任务隔离红线的 prompt 注入。

    inherited_task_id: 增量任务允许读取的历史任务 ID。
    """
    allowed_dirs = [f"outputs/{task_id}"]
    if inherited_task_id:
        safe = inherited_task_id.replace("/", "_").replace("\\", "_")
        allowed_dirs.append(f"outputs/{safe}")

    dirs_str = "、".join(f"`{d}`" for d in allowed_dirs)
    return (
        "## 🚫 任务隔离红线（必须严格遵守）\n\n"
        f"本任务的专属输出目录为 `outputs/{task_id}/`。\n\n"
        f"**文件读写权限**：你只能读取和写入以下目录中的文件：{dirs_str}\n\n"
        "**严禁**：\n"
        "- 扫描 `outputs/` 根目录\n"
        "- 读取其他学校的 CSV/XLSX/JSON 数据文件\n"
        "- 使用 `glob` / `rglob` 或 `ls` 遍历 `outputs/` 的全部子目录\n"
        "- 读取 `skills/` 中的其他学校专属 JSON 文件中的数据内容\n\n"
        "**正确做法**：直接指定 `outputs/{task_id}/文件名.csv` 进行读写。\n"
    )
