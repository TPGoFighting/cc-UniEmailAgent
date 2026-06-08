import asyncio
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.mailer import (
    HIGH_VOLUME_THRESHOLD,
    build_preview,
    create_send_job,
    detect_smtp_provider,
    is_valid_email,
)
from agent.universities import (
    UNIVERSITY_985,
    UNIVERSITY_211,
    build_university_response,
    parse_table_file,
)


class UniversityCatalogTests(unittest.TestCase):
    def test_catalog_filters_key_tiers(self):
        response = build_university_response(tier="985", q="南京大学")
        names = [u["name"] for group in response["groups"] for city in group["cities"] for u in city["universities"]]
        self.assertIn("南京大学", names)
        self.assertIn("南京大学", UNIVERSITY_985)
        self.assertIn("南京大学", UNIVERSITY_211)

    def test_plain_undergraduate_filter_excludes_priority_tags(self):
        response = build_university_response(tier="普通本科", q="南京工程学院")
        names = [u["name"] for group in response["groups"] for city in group["cities"] for u in city["universities"]]
        self.assertIn("南京工程学院", names)
        for group in response["groups"]:
            for city in group["cities"]:
                for university in city["universities"]:
                    self.assertFalse(university["is_985"])
                    self.assertFalse(university["is_211"])
                    self.assertFalse(university["is_double_first_class"])

    def test_parse_csv_table_counts_valid_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "南京大学_教师邮箱.csv"
            path.write_text("序号,姓名,邮箱,学院\n1,张三,zhang@nju.edu.cn,计算机学院\n2,李四,invalid,计算机学院\n", encoding="utf-8-sig")
            table = parse_table_file(path)
        self.assertEqual(table["columns"], ["序号", "姓名", "邮箱", "学院"])
        self.assertEqual(table["total"], 2)
        self.assertEqual(table["valid_email_count"], 1)


class MailerTests(unittest.TestCase):
    def test_smtp_provider_detection(self):
        detected = detect_smtp_provider("sender@163.com")
        self.assertTrue(detected["matched"])
        self.assertEqual(detected["config"]["host"], "smtp.163.com")

    def test_preview_renders_chinese_variables(self):
        rows = [{"学校": "南京大学", "姓名": "张三", "邮箱": "zhang@nju.edu.cn", "学院": "计算机学院", "职称": "教授"}]
        preview = build_preview(rows, "致{{姓名}}", "{{学校}}-{{学院}}", limit=1)
        self.assertEqual(preview["previews"][0]["subject"], "致张三")
        self.assertEqual(preview["previews"][0]["body"], "南京大学-计算机学院")
        self.assertEqual(preview["sendableCount"], 1)

    def test_send_requires_confirmation_and_high_volume_gate(self):
        rows = [{"姓名": f"教师{i}", "邮箱": f"t{i}@example.edu.cn"} for i in range(HIGH_VOLUME_THRESHOLD + 1)]
        with self.assertRaises(ValueError):
            create_send_job(rows=rows, subject_template="Hi", body_template="Body", smtp_session_id="missing", preview_confirmed=False, confirmed=True)
        with self.assertRaises(ValueError):
            create_send_job(rows=rows, subject_template="Hi", body_template="Body", smtp_session_id="missing", preview_confirmed=True, confirmed=True)

    def test_email_validation(self):
        self.assertTrue(is_valid_email("teacher@example.edu.cn"))
        self.assertFalse(is_valid_email("teacher at example.edu.cn"))


class AgentProcessTests(unittest.TestCase):
    def test_agent_process_registration_and_termination(self):
        from agent.claude_agent import ClaudeAgent
        agent = ClaudeAgent()

        class DummyProcess:
            def __init__(self):
                self.killed = False

            def kill(self):
                self.killed = True

        dummy = DummyProcess()
        task_id = "test-task-123"

        agent.active_procs[task_id] = dummy
        self.assertIn(task_id, agent.active_procs)

        ok = agent.stop_task(task_id)
        self.assertTrue(ok)
        self.assertTrue(dummy.killed)
        self.assertNotIn(task_id, agent.active_procs)

        ok_fail = agent.stop_task("non-existent")
        self.assertFalse(ok_fail)


class GlobalSkillsAndIsolationTests(unittest.TestCase):
    """验证任务上下文隔离 + 全局技能注入逻辑。"""

    def _call_build_context_prompt(self, task_data, latest_user_msg):
        """动态导入 main 模块中的辅助函数（避免 FastAPI 全局 app 副作用）。"""
        import importlib, sys as _sys
        # 确保 backend 目录在 path 中
        backend_dir = str(Path(__file__).resolve().parents[1])
        if backend_dir not in _sys.path:
            _sys.path.insert(0, backend_dir)
        import main as _main
        return _main._build_context_prompt(task_data, latest_user_msg)

    def _call_load_global_skills(self):
        import main as _main
        return _main._load_global_skills()

    # -------------------------------------------------------
    # 1. 任务上下文隔离：新任务只包含自己的消息
    # -------------------------------------------------------
    def test_new_task_prompt_does_not_contain_other_task_messages(self):
        """不同 task_data 对象之间不会互相污染，新任务仅含自身消息。"""
        task_a = {
            "messages": [
                {"role": "user", "content": "任务A的请求"},
            ]
        }
        task_b = {
            "messages": [
                {"role": "user", "content": "任务B的请求"},
            ]
        }
        prompt_a, _, _ = self._call_build_context_prompt(task_a, "任务A的请求")
        prompt_b, _, _ = self._call_build_context_prompt(task_b, "任务B的请求")

        # A 的 prompt 不应出现 B 的内容
        self.assertNotIn("任务B", prompt_a)
        # B 的 prompt 不应出现 A 的内容
        self.assertNotIn("任务A", prompt_b)

    # -------------------------------------------------------
    # 2. 追问场景只包含本任务的历史，不含其他任务消息
    # -------------------------------------------------------
    def test_followup_only_contains_own_history(self):
        """多轮追问时，上下文摘要只引用自身历史消息，而非全局或其他任务消息。"""
        task_data = {
            "messages": [
                {"role": "user", "content": "第一次问题"},
                {"role": "agent", "content": "第一次回答"},
                {"role": "user", "content": "第二次问题"},
            ]
        }
        prompt, first_msg, is_followup = self._call_build_context_prompt(task_data, "第二次问题")

        self.assertTrue(is_followup)
        self.assertIn("第一次问题", prompt)   # 包含本任务历史
        self.assertIn("第二次问题", prompt)   # 包含当前请求
        self.assertNotIn("其他任务", prompt)  # 不包含无关内容

    # -------------------------------------------------------
    # 3. 全局技能注入——无 skills 文件时不注入任何脏内容
    # -------------------------------------------------------
    def test_no_global_skills_file_returns_plain_message(self):
        """当 global_crawling_rules.md 不存在时，新任务 prompt 就是原始用户消息。"""
        import main as _main
        original = _main.GLOBAL_SKILLS_FILE

        # 临时指向一个不存在的路径
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            _main.GLOBAL_SKILLS_FILE = Path(tmp) / "nonexistent.md"
            task_data = {"messages": [{"role": "user", "content": "抓取清华大学邮箱"}]}
            prompt, _, is_followup = self._call_build_context_prompt(task_data, "抓取清华大学邮箱")
        _main.GLOBAL_SKILLS_FILE = original  # 恢复

        self.assertFalse(is_followup)
        self.assertEqual(prompt, "抓取清华大学邮箱")

    # -------------------------------------------------------
    # 4. _build_context_prompt 不注入全局技能（由 WS handler 统一注入）
    # -------------------------------------------------------
    def test_build_context_prompt_does_not_inject_global_skills(self):
        """即使 global_crawling_rules.md 存在，_build_context_prompt 也不注入技能。——技能由 WS handler 统一注入。"""
        import main as _main
        original = _main.GLOBAL_SKILLS_FILE

        with tempfile.TemporaryDirectory() as tmp:
            skills_file = Path(tmp) / "global_crawling_rules.md"
            skills_file.write_text("## 🏫 清华大学 爬取策略\n* https://www.tsinghua.edu.cn/cs/", encoding="utf-8")
            _main.GLOBAL_SKILLS_FILE = skills_file

            task_data = {"messages": [{"role": "user", "content": "抓取清华大学邮箱"}]}
            prompt, _, is_followup = self._call_build_context_prompt(task_data, "抓取清华大学邮箱")
        _main.GLOBAL_SKILLS_FILE = original  # 恢复

        self.assertFalse(is_followup)
        # _build_context_prompt 不应注入全局技能——那是 WS handler 的职责
        self.assertEqual(prompt, "抓取清华大学邮箱")
        self.assertNotIn("清华大学 爬取策略", prompt)

    # -------------------------------------------------------
    # 5. 追问时 _build_context_prompt 只提供上下文，不注入技能
    # -------------------------------------------------------
    def test_followup_context_does_not_include_global_skills(self):
        """追问场景下 _build_context_prompt 提供任务上下文（历史消息、文件等），但不注入全局技能。"""
        import main as _main
        original = _main.GLOBAL_SKILLS_FILE

        with tempfile.TemporaryDirectory() as tmp:
            skills_file = Path(tmp) / "global_crawling_rules.md"
            skills_file.write_text("## 🏫 南京大学 爬取策略\n* https://www.nju.edu.cn/teachers/", encoding="utf-8")
            _main.GLOBAL_SKILLS_FILE = skills_file

            task_data = {
                "messages": [
                    {"role": "user", "content": "抓取南京大学邮箱"},
                    {"role": "agent", "content": "已生成文件"},
                    {"role": "user", "content": "再加一个DOCX格式"},
                ]
            }
            prompt, _, is_followup = self._call_build_context_prompt(task_data, "再加一个DOCX格式")
        _main.GLOBAL_SKILLS_FILE = original  # 恢复

        self.assertTrue(is_followup)
        # _build_context_prompt 应包含本任务上下文
        self.assertIn("再加一个DOCX格式", prompt)
        self.assertIn("抓取南京大学邮箱", prompt)
        # 但不包含全局技能——那是 WS handler 的职责
        self.assertNotIn("南京大学 爬取策略", prompt)
        self.assertNotIn("全局共享", prompt)


if __name__ == "__main__":
    unittest.main()
