"""智能意图路由 — 三路分类（简单问答 / 全新爬取 / 增量爬取）+ 实体提取"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    SIMPLE_QUERY = "simple_query"       # 数据查询/统计 → 直接读文件回答
    NEW_CRAWL = "new_crawl"             # 全新爬取任务 → 启动完整 Pipeline
    INCREMENTAL_CRAWL = "incremental"   # 增量/修复爬取 → 加载历史上下文补充


@dataclass
class IntentResult:
    intent: IntentType
    university_name: str = ""           # 目标大学名称
    target_departments: list[str] = field(default_factory=list)  # 目标学院
    reason: str = ""                    # 分类理由（调试用）
    threshold_hint: str = ""            # 增量任务的质量阈值提示

    @property
    def is_crawl(self) -> bool:
        return self.intent in (IntentType.NEW_CRAWL, IntentType.INCREMENTAL_CRAWL)


# ── 本地关键词兜底规则（无 API Key 时使用） ──

_SIMPLE_QUERY_PATTERNS = [
    r"(多少|几个|几所|统计|占比|比例|率|平均|汇总|分析|查看|显示|列出|有哪些)",
    r"(每个学院|各学院|各个学院|分别)",
    r"(邮箱率|抓取率|覆盖率|有效率)",
    r"(数据.*怎么样|结果.*如何|有没有.*数据)",
]

_INCREMENTAL_PATTERNS = [
    r"(补充|补全|补爬|追加|重新爬|换策略|换个方式)",
    r"(部分.*少|不够|不足|缺|遗漏|漏掉|不全)",
    r"(少于|小于|不到|不够)\s*\d+",
    r"(增加|补充).*(学院|系|部门)",
    r"(修复|完善|改进).*(爬|抓|数据)",
]

_NEW_CRAWL_PATTERNS = [
    r"(爬取|抓取|爬|采集|获取).*(大学|学院|学校|教师|邮箱|信息)",
    r"(帮我|请|给我).*(找|搜索|查).*(教师|教授|老师|邮箱)",
    r"^(爬|抓|采集)\s*(.+大学|.+学院)",
]


def _match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _extract_university(text: str) -> str:
    """从用户消息中提取干净的大学名称。"""
    # 优先匹配 "XX大学" / "XX学院"（贪婪，但后处理清洗前缀）
    for m in re.finditer(r"([一-鿿\w]{2,8}(?:大学|学院))", text):
        raw = m.group(1)
        # 去除常见动词前缀
        cleaned = _clean_uni_name(raw)
        if cleaned:
            return cleaned
    # 尝试匹配英文缩写 + University
    m = re.search(r"([A-Z]{2,10})\s*(?:University|Univ)", text, re.I)
    if m:
        return m.group(1) + " University"
    return ""


def _clean_uni_name(raw: str) -> str:
    """清洗大学名称中的动词/介词前缀（循环移除多级前缀如「帮我爬取」）。"""
    noise_prefixes = [
        "爬取", "抓取", "帮我", "请", "给我", "去", "访问", "打开",
        "对于", "针对", "关于", "把", "从", "在",
    ]
    noise_sorted = sorted(noise_prefixes, key=len, reverse=True)
    changed = True
    while changed:
        changed = False
        for noise in noise_sorted:
            if raw.startswith(noise) and len(raw) > len(noise) + 2:
                raw = raw[len(noise):]
                changed = True
                break  # 重新从最长前缀开始匹配
    return raw if len(raw) >= 4 else ""


def _extract_departments(text: str) -> list[str]:
    """从用户消息中提取干净的学院名称。"""
    depts = []
    uni_name = _extract_university(text)

    for m in re.finditer(r"([一-鿿\w]{2,8}(?:学院|系|部|中心|研究院))", text):
        raw = m.group(1)
        # 去除常见连接词和无意义单字前缀
        raw = re.sub(r"^(?:和|与|及|以及|、)", "", raw)
        raw = re.sub(r"^[取爬抓给帮去找]", "", raw)
        raw = re.sub(r"^(?:关于|针对|对于)", "", raw)
        # 如果包含大学名称，去除大学部分
        if uni_name and uni_name in raw and raw != uni_name:
            raw = raw.replace(uni_name, "")
        # 过滤
        if raw.endswith("大学") or len(raw) < 3:
            continue
        if raw not in depts:
            depts.append(raw)
    return depts


async def classify_intent(
    message: str,
    *,
    has_existing_data: bool = False,
    existing_university: str = "",
) -> IntentResult:
    """使用 LLM 进行三路意图分类，无 API Key 时回退本地规则。

    参数:
        message: 用户当前输入
        has_existing_data: 当前任务是否已有输出文件
        existing_university: 当前任务关联的大学（如有）
    """

    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if api_key:
        try:
            result = await _llm_classify(message, api_key, has_existing_data, existing_university)
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"LLM 意图分类失败，回退本地规则: {e}")

    return _keyword_classify(message, has_existing_data, existing_university)


async def _llm_classify(
    message: str, api_key: str, has_existing_data: bool, existing_university: str
) -> IntentResult | None:
    """通过 DeepSeek/OpenAI API 进行精准三路分类。"""
    from openai import AsyncOpenAI

    if os.environ.get("DEEPSEEK_API_KEY"):
        base_url = "https://api.deepseek.com/v1"
        model = "deepseek-chat"
    else:
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        model = os.environ.get("OPENAI_API_MODEL") or "gpt-4o-mini"

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    context = ""
    if has_existing_data and existing_university:
        context = (
            f"当前任务已经对「{existing_university}」执行过爬取，有结果文件。"
        )
    elif has_existing_data:
        context = "当前任务已有输出文件。"

    system = (
        "你是一个精准的任务意图分类器。请根据用户输入判断意图类型，输出 JSON。\n\n"
        "## 意图类型\n"
        "- simple_query: 询问已有数据的统计信息、查看结果、数据分析，不涉及新的爬取\n"
        "- new_crawl: 要求爬取/抓取一个全新的目标大学\n"
        "- incremental: 基于已有爬取结果，要求补充缺失数据、修复不达标的学院、换策略重新爬取部分内容\n\n"
        "## 输出格式（严格 JSON）\n"
        '{"intent": "<类型>", "university": "<大学名或空>", "departments": ["<学院1>", ...], "reason": "<简短理由>"}\n\n'
        "## 分类原则\n"
        "1. 如果用户问的是「多少」「统计」「比例」「查看结果」「每个学院分别」等关键词且当前已有数据 → simple_query\n"
        "2. 如果用户提到「补充」「换策略」「部分学院不够」「修复」「增量」且当前已有数据 → incremental\n"
        "3. 如果用户要求爬取新大学且没有提到要基于已有数据 → new_crawl"
    )

    user_msg = f"【上下文】{context}\n【用户输入】{message}"

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=200,
        temperature=0.0,
    )

    raw = response.choices[0].message.content.strip()
    logger.info(f"[IntentRouter] LLM 分类结果: {raw}")

    # 解析 JSON
    import json as _json
    # 容错：提取 JSON 块
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0)

    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        logger.warning(f"[IntentRouter] LLM 返回非 JSON: {raw}")
        return None

    intent_str = data.get("intent", "").lower()
    intent_map = {
        "simple_query": IntentType.SIMPLE_QUERY,
        "new_crawl": IntentType.NEW_CRAWL,
        "incremental": IntentType.INCREMENTAL_CRAWL,
    }
    intent = intent_map.get(intent_str)
    if intent is None:
        return None

    return IntentResult(
        intent=intent,
        university_name=data.get("university", "") or _extract_university(message),
        target_departments=data.get("departments", []) or _extract_departments(message),
        reason=data.get("reason", ""),
    )


def _keyword_classify(
    message: str, has_existing_data: bool, existing_university: str
) -> IntentResult:
    """本地关键词规则分类（无 API Key 时的兜底方案）。"""
    uni = _extract_university(message) or existing_university
    depts = _extract_departments(message)

    # 先检测增量模式（优先级高于纯问答，因为可能包含补充+统计混合）
    if has_existing_data and _match_any(message, _INCREMENTAL_PATTERNS):
        # 提取阈值提示
        threshold_hint = ""
        m = re.search(r"(少于|小于|不到|不够)\s*(\d+)", message)
        if m:
            threshold_hint = f"部分学院数据量低于 {m.group(2)} 条需要补充"

        return IntentResult(
            intent=IntentType.INCREMENTAL_CRAWL,
            university_name=uni,
            target_departments=depts,
            reason="匹配增量/补充关键词",
            threshold_hint=threshold_hint,
        )

    # 检测简单问答
    if _match_any(message, _SIMPLE_QUERY_PATTERNS) and has_existing_data:
        return IntentResult(
            intent=IntentType.SIMPLE_QUERY,
            university_name=uni or existing_university,
            target_departments=depts,
            reason="匹配数据查询/统计关键词",
        )

    # 检测全新爬取
    if _match_any(message, _NEW_CRAWL_PATTERNS):
        return IntentResult(
            intent=IntentType.NEW_CRAWL,
            university_name=uni,
            target_departments=depts,
            reason="匹配爬取/抓取关键词",
        )

    # 如果当前任务已有数据但用户消息不含明确关键词 → 倾向简单问答
    if has_existing_data:
        return IntentResult(
            intent=IntentType.SIMPLE_QUERY,
            university_name=uni or existing_university,
            reason="有现有数据，且无明确爬取意图，按问答处理",
        )

    # 兜底：无明显意图
    return IntentResult(
        intent=IntentType.NEW_CRAWL if uni else IntentType.SIMPLE_QUERY,
        university_name=uni,
        reason="兜底分类",
    )
