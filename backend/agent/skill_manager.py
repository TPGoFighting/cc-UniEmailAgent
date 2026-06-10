"""技能库双向流转 — 前置读取 (注入 Prompt) + 后置反思 (经验沉淀)

v2: 按需加载（大学名匹配 Section）+ 智能写入去重（相似度校验）
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
GLOBAL_RULES_FILE = SKILLS_DIR / "global_crawling_rules.md"
CRAWL_KNOWLEDGE_FILE = SKILLS_DIR / "crawl_knowledge.md"

# ── 去重阈值 ──
SIMILARITY_THRESHOLD = 0.55  # 相似度超过此值视为重复，跳过写入

# ── 共享节标题关键词（总是保留的通用知识） ──
_SHARED_SECTION_KEYWORDS = [
    "核心数据规范", "输出格式", "数据清洗管道", "反爬邮箱恢复",
    "导航链接黑名单", "姓名验证规则", "标准爬取流程",
    "并行爬取脚本模板", "大学URL推断规则", "输出字段",
    "文件名规范", "FILES", "声明格式",
]

STANDARD_HEADERS = ["院校名称", "教师姓名", "所在学院", "职称", "邮箱", "官网主页链接"]


def _resolve_skills_dir() -> Path:
    SKILLS_DIR.mkdir(exist_ok=True)
    return SKILLS_DIR


# ═══════════════════════════════════════════════════════════════
# 前置读取：按需加载，只注入目标大学相关的技能知识
# ═══════════════════════════════════════════════════════════════

def load_skills_prompt(university_name: str = "") -> str:
    """前置读取技能库，按大学名精准提取相关 Section。

    优先级：
    1. crawl_knowledge.md 中与 university_name 匹配的 Section
    2. global_crawling_rules.md（全部，体积小）
    3. 大学专属 JSON 元数据摘要
    """
    parts: list[str] = []

    # 1. 按需读取 crawl_knowledge.md
    if CRAWL_KNOWLEDGE_FILE.exists():
        try:
            full_text = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()
            if university_name:
                extracted = _extract_relevant_sections(full_text, university_name)
            else:
                extracted = _strip_frontmatter(full_text)
            if extracted:
                parts.append(extracted)
        except OSError:
            pass

    # 2. 全局规则全文（体积可控，~2KB）
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


def _strip_frontmatter(text: str) -> str:
    """去除 YAML frontmatter。"""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    return text


def _extract_relevant_sections(full_text: str, university_name: str) -> str:
    """从完整知识库中提取与目标大学相关的 Section。

    策略：
    - 文档前言和共享节（数据规范/清洗管道等）→ 全部保留
    - 「已完成任务汇总」和「各高校详细爬取指南」→ 只提取匹配大学名的 ### 子节
    """
    text = _strip_frontmatter(full_text)

    # 按 ## 级别大节拆分
    sections = _split_top_sections(text)
    if len(sections) <= 1:
        return text  # 无法解析，返回全部

    result_parts: list[str] = []
    short_name = _uni_short_name(university_name)

    for section in sections:
        header = _section_header(section)

        if not header:
            # 前言 / 标题区 → 保留
            result_parts.append(section)
            continue

        if _is_university_index_section(header):
            # 大学索引节 → 只提取匹配的子节
            filtered = _filter_subsections(section, university_name, short_name)
            if filtered:
                result_parts.append(filtered)
        elif _is_reflection_section(header):
            # 🏫 反思节 → 只保留匹配目标大学的
            if _uni_matches_header(header, university_name, short_name):
                result_parts.append(section)
        elif _is_shared_section(header):
            result_parts.append(section)
        else:
            # 未知节 → 保守保留（避免丢失新知识）
            result_parts.append(section)

    return "\n".join(result_parts)


def _split_top_sections(text: str) -> list[str]:
    """按 ## 级别标题拆分文档。"""
    # 先找到第一个 ## 的位置，之前的是前言
    first_h2 = re.search(r"\n## ", text)
    if not first_h2:
        return [text]

    preamble = text[:first_h2.start()]
    rest = text[first_h2.start():]

    parts = [preamble] if preamble.strip() else []
    # 按 \n## 拆分，保留分隔符
    for sec in re.split(r"\n(?=## )", rest):
        parts.append(sec)
    return parts


def _section_header(section: str) -> str:
    """提取节的 ## 标题。"""
    m = re.match(r"## (.+?)(?:\n|$)", section)
    return m.group(1).strip() if m else ""


def _is_university_index_section(header: str) -> bool:
    """判断是否为大学索引节（需要按大学名过滤子节）。"""
    return any(kw in header for kw in ["已完成任务", "各高校详细爬取指南", "各高校"])


def _is_reflection_section(header: str) -> bool:
    """判断是否为 🏫 反思节（后置反思自动写入的大学专属节）。"""
    return "🏫" in header


def _is_shared_section(header: str) -> bool:
    """判断是否为共享节（对所有任务都有用）。"""
    return any(kw in header for kw in _SHARED_SECTION_KEYWORDS)


def _filter_subsections(section: str, university_name: str, short_name: str) -> str | None:
    """从大学索引节中只保留匹配大学名的 ### 子节。"""
    lines = section.split("\n")
    result_lines: list[str] = []
    in_matching_sub = False
    current_sub_lines: list[str] = []

    for line in lines:
        if line.startswith("### "):
            # 遇到新子节：先保存上一个
            if in_matching_sub and current_sub_lines:
                result_lines.extend(current_sub_lines)
            # 检查新子节是否匹配
            header_text = line[4:].strip()
            current_sub_lines = [line]
            in_matching_sub = _uni_matches_header(header_text, university_name, short_name)
        elif line.startswith("## "):
            # 遇到更高级别的标题，结束当前子节
            if in_matching_sub:
                result_lines.extend(current_sub_lines)
            current_sub_lines = [line]
            in_matching_sub = True  # 大节标题行保留
        else:
            current_sub_lines.append(line)

    # 最后一个子节
    if in_matching_sub and current_sub_lines:
        result_lines.extend(current_sub_lines)

    return "\n".join(result_lines) if result_lines else None


def _uni_short_name(full_name: str) -> str:
    """提取大学简称（如「南京大学」→「南大」）。"""
    # 取前两个字作为简称（中国大学命名惯例）
    m = re.match(r"([一-鿿]{2})", full_name)
    return m.group(1) if m else full_name


def _uni_matches_header(header: str, university_name: str, short_name: str) -> bool:
    """判断子节标题是否匹配目标大学。"""
    if not university_name:
        return False
    # 全名匹配
    if university_name in header:
        return True
    # 简称匹配（如「南大」在「南京大学 (nju.edu.cn)」中）
    if len(short_name) >= 2 and short_name in header:
        return True
    # 英文域名匹配
    domain_hint = _uni_domain_hint(university_name)
    if domain_hint and domain_hint in header.lower():
        return True
    return False


def _uni_domain_hint(university_name: str) -> str:
    """从大学名推断域名关键词。"""
    mapping = {
        "南京大学": "nju", "东南大学": "seu", "南京理工大学": "njust",
        "南京航空航天大学": "nuaa", "南京邮电大学": "njupt",
        "清华大学": "tsinghua", "北京大学": "pku", "浙江大学": "zju",
        "复旦大学": "fudan", "上海交通大学": "sjtu", "北京邮电大学": "bupt",
    }
    return mapping.get(university_name, "")


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
# 后置反思：分析日志 → 提取新策略 → 去重写入技能库
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
    """后置反思：用 LLM 分析任务日志，提取新经验 → 去重 → 持久化到技能库。

    返回写入的文件路径，若无需更新则返回 None。
    """
    log_text = _extract_relevant_logs(messages)
    if len(log_text) < 200:
        logger.info(f"[SkillManager] 任务 {task_id[:8]} 日志过短，跳过反思")
        return None

    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[SkillManager] 无 API Key，跳过反思总结")
        return None

    reflection = await _llm_reflection(api_key, university_name, log_text)
    if not reflection or "无新发现" in reflection:
        logger.info(f"[SkillManager] 任务 {task_id[:8]} 无新发现需要记录")
        return None

    # 去重检查：与已有知识比较相似度
    if _is_duplicate(reflection, university_name):
        logger.info(f"[SkillManager] 任务 {task_id[:8]} 反思与已有知识高度重复，跳过写入")
        return None

    return await atomic_write_reflection(task_id, university_name, reflection)


def _extract_relevant_logs(messages: list[dict]) -> str:
    """从任务消息中提取对反思有价值的内容。"""
    parts: list[str] = []

    for m in messages:
        content = m.get("content", "") or m.get("message", "")
        if not content:
            continue

        role = m.get("role", "")
        msg_type = m.get("type", "")

        if role in ("agent", "log") or msg_type in ("log", "agent", "text"):
            parts.append(content[:500])
        elif role == "error" or msg_type == "error":
            parts.append(f"[ERROR] {content[:300]}")

        if len(parts) > 80:
            break

    return "\n---\n".join(parts[-60:])


async def _llm_reflection(api_key: str, university_name: str, log_text: str) -> str | None:
    """调用 LLM 进行反思总结。"""
    try:
        from openai import AsyncOpenAI

        if os.environ.get("DEEPSEEK_API_KEY"):
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_API_BASE") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1",
            )
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


# ── 去重逻辑 ──

def _is_duplicate(new_content: str, university_name: str) -> bool:
    """检查新内容是否与已有知识高度重复。

    将新内容拆为句子，与已有知识中该校相关段落做相似度比较。
    """
    if not CRAWL_KNOWLEDGE_FILE.exists():
        return False

    try:
        existing = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8")
    except OSError:
        return False

    # 提取该校已有的知识点段落
    uni_sections = _extract_university_paragraphs(existing, university_name)
    if not uni_sections:
        return False

    # 将新内容拆分为独立的知识点行
    new_lines = [l.strip() for l in new_content.split("\n")
                 if l.strip().startswith("- ") and "**" in l]
    if not new_lines:
        return False

    # 逐条检查是否已有相似内容
    duplicate_count = 0
    for line in new_lines:
        for para in uni_sections:
            if SequenceMatcher(None, line, para).ratio() > SIMILARITY_THRESHOLD:
                duplicate_count += 1
                break

    # 超过半数知识点重复 → 视为整体重复
    return duplicate_count >= len(new_lines) * 0.5


def _extract_university_paragraphs(text: str, university_name: str) -> list[str]:
    """从知识库中提取与目标大学相关的段落。"""
    sections = _split_top_sections(_strip_frontmatter(text))
    short_name = _uni_short_name(university_name)
    relevant_sections: list[str] = []

    for sec in sections:
        header = _section_header(sec)
        if _is_university_index_section(header):
            filtered = _filter_subsections(sec, university_name, short_name)
            if filtered:
                relevant_sections.append(filtered)
        elif _is_reflection_section(header):
            if _uni_matches_header(header, university_name, short_name):
                relevant_sections.append(sec)

    if not relevant_sections:
        return []

    # 拆分成段落（按空行分隔）
    paragraphs: list[str] = []
    for sec in relevant_sections:
        for para in sec.split("\n\n"):
            para = para.strip()
            if len(para) > 30:  # 忽略过短段落
                paragraphs.append(para)

    return paragraphs


# ── 写入逻辑 ──

# 全局写入锁，防止并发写入技能文件造成数据损坏
_SKILL_WRITE_LOCK = asyncio.Lock()


def _safe_write(path: Path, content: str) -> None:
    """临时文件 + 原子重命名写入，防止写入中断导致文件损坏。"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)  # 原子替换


async def atomic_write_reflection(task_id: str, university_name: str, reflection: str) -> str | None:
    """带锁保护的反思写入入口。"""
    async with _SKILL_WRITE_LOCK:
        return _write_reflection(task_id, university_name, reflection)


def _write_reflection(task_id: str, university_name: str, reflection: str) -> str | None:
    """将反思结果写入技能文件。"""
    _resolve_skills_dir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    section = f"\n\n## 🏫 {university_name} — {ts}（任务 {task_id[:8]}）\n\n{reflection}\n"

    try:
        if CRAWL_KNOWLEDGE_FILE.exists():
            existing = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8")
            if f"## 🏫 {university_name}" in existing:
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

        _safe_write(CRAWL_KNOWLEDGE_FILE, updated)
        logger.info(f"[SkillManager] 反思已写入: {CRAWL_KNOWLEDGE_FILE.name}")
    except OSError as e:
        logger.error(f"[SkillManager] 写入失败: {e}")
        return None

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
    """返回任务隔离红线的 prompt 注入（与 CRAWL_STRATEGY_PROMPT 互补的快速提醒）。"""
    allowed_dirs = [f"outputs/{task_id}"]
    if inherited_task_id:
        safe = inherited_task_id.replace("/", "_").replace("\\", "_")
        allowed_dirs.append(f"outputs/{safe}")

    dirs_str = "、".join(f"`{d}`" for d in allowed_dirs)
    return (
        "## 🔒 工作目录确认\n\n"
        f"本任务专属目录：`outputs/{task_id}/`\n"
        f"可读写范围：{dirs_str}\n"
        "重申：不要用 Glob 遍历整个 outputs/，只在自己的目录下操作。\n"
    )


def get_post_task_prompt() -> str:
    """返回任务完成后的自我反思与技能更新指令。"""
    return (
        "## 🧠 任务完成后必须执行的收尾步骤\n\n"
        "收到 done 事件后，在关闭会话前必须完成：\n\n"
        "1. **回顾反思**：回顾本次爬取过程，提取新的发现和教训\n"
        "2. **读取技能库**：读取 `skills/crawl_knowledge.md`，了解现有知识\n"
        "3. **判断是否更新**：\n"
        "   - 有新的 URL 模式、选择器规则、反爬策略、邮箱格式 → 追加新章节\n"
        "   - 与已有知识重复 → 跳过（回复「无新发现」）\n"
        "4. **追加格式**（当有新发现时）：\n"
        "   ```\n"
        "   ## 🏫 {大学名} — {日期}\n\n"
        "   - **URL 模式**: <描述官网教师页面 URL 规律>\n"
        "   - **关键选择器**: <列出有效的 CSS 选择器>\n"
        "   - **踩坑记录**: <遇到的坑和解决方案>\n"
        "   - **邮箱特征**: <该校邮箱的域名规律>\n"
        "   ```\n"
        "5. **使用 Edit 工具将新章节追加到 skills/crawl_knowledge.md 末尾**\n\n"
        "**目的**：让后续任务能复用本次爬取经验，避免重复踩坑。\n"
    )
