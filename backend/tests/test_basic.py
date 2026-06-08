"""Tests for UniEmailAgent backend."""
import json
import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Add backend to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.cleaner import (
    is_valid_person_name,
    is_valid_email_format,
    is_admin_email,
    is_nav_list_url,
    is_academic_domain,
    clean_title,
)
from constants import EMAIL_RE, UNIVERSITY_NAME_RE

# Import functions from main
from main import (
    _user_facing_message,
    _safe_resolve,
    _translate_error,
    _parse_structured_log,
    _is_technical_message,
    _extract_stats_from_logs,
)


class TestUserFacingMessage(unittest.TestCase):
    """Test the Phase 1 user-facing message filter."""

    def test_hides_empty(self):
        self.assertIsNone(_user_facing_message(""))

    def test_hides_tool_call(self):
        self.assertIsNone(_user_facing_message("🔧 调用工具: Bash"))

    def test_hides_tool_result(self):
        self.assertIsNone(_user_facing_message("📋 结果: (stdout)"))

    def test_hides_hermes_orchestrator(self):
        self.assertIsNone(
            _user_facing_message("🧠 Hermes Orchestrator: thinking..."),
        )

    def test_hides_claude_code(self):
        self.assertIsNone(_user_facing_message("Claude Code is executing"))

    def test_passes_friendly_messages(self):
        """✅ 学院提取消息现在返回结构化 dict 而非原文本."""
        result = _user_facing_message("✅ 计算机学院：提取到 50 位教师邮箱")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["type"], "stats")
        self.assertEqual(result["teachers_found"], 50)

    def test_hides_step_limit(self):
        self.assertIsNone(_user_facing_message("达到最大步数限制，停止"))

    def test_hides_termination(self):
        self.assertEqual(_user_facing_message("⏹️ 任务终止"), "任务已手动停止")

    def test_hides_timeout_block(self):
        self.assertIsNone(_user_facing_message("timeout waiting for block"))

    def test_hides_tool_use_error(self):
        self.assertIsNone(_user_facing_message("tool_use_error: Bash failed"))

    def test_hides_input_validation_error(self):
        self.assertIsNone(_user_facing_message("InputValidationError: invalid"))

    def test_hides_retrieval_status(self):
        self.assertIsNone(_user_facing_message("<retrieval_status> done"))

    def test_hides_command_running(self):
        self.assertIsNone(_user_facing_message("Command running: python"))

    def test_hides_block_eq(self):
        self.assertIsNone(_user_facing_message("block=10"))

    def test_hides_command_eq(self):
        self.assertIsNone(_user_facing_message("command=echo hello"))

    def test_hides_json_with_output(self):
        self.assertIsNone(_user_facing_message("JSON 格式输出: {...}"))

    def test_hides_exit_code(self):
        self.assertIsNone(_user_facing_message("Exit code 1"))

    def test_hides_syntax_error(self):
        self.assertIsNone(_user_facing_message("SyntaxError: invalid syntax"))

    def test_hides_traceback(self):
        self.assertIsNone(_user_facing_message("Traceback (most recent call last)"))

    def test_hides_file_created(self):
        self.assertIsNone(_user_facing_message("File created successfully at: /tmp/foo.py"))

    def test_hides_playwright_agent(self):
        self.assertIsNone(_user_facing_message("playwright_agent.py line 42"))

    def test_hides_hermes_agent(self):
        self.assertIsNone(_user_facing_message("hermes_agent.py error"))

    def test_translates_error(self):
        self.assertIn("自动跳过", _translate_error("HTTP 403 Forbidden"))
        self.assertIn("不存在", _translate_error("HTTP 404 Not Found"))
        self.assertIn("超时", _translate_error("timeout occurred"))
        self.assertIn("自动恢复", _translate_error("Traceback: ZeroDivisionError"))


class TestParseStructuredLog(unittest.TestCase):
    """Test structured log parsing."""

    def test_parse_stage(self):
        result = _parse_structured_log("📌 第1阶段: 探索学院页面")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "stage")
        self.assertEqual(result["stage"], "explore")

    def test_parse_stats(self):
        result = _parse_structured_log("✅ 计算机学院：提取到 50 位教师邮箱")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "stats")
        self.assertEqual(result["teachers_found"], 50)


class TestTechnicalMessage(unittest.TestCase):
    """Test technical message detection."""

    def test_technical_patterns(self):
        self.assertTrue(_is_technical_message("🧠 Hermes Orchestrator:"))
        self.assertTrue(_is_technical_message("📋 结果: data"))
        self.assertTrue(_is_technical_message("Claude Code 执行"))
        self.assertTrue(_is_technical_message("Exit code 1"))
        self.assertTrue(_is_technical_message("SyntaxError: invalid"))
        self.assertFalse(_is_technical_message("你好，我是助手"))
        self.assertFalse(_is_technical_message("✅ 任务完成"))


class TestExtractStats(unittest.TestCase):
    """Test stats extraction from logs."""

    def test_extract_basic(self):
        logs = [
            "✅ 计算机学院：提取到 30 位教师邮箱",
            "✅ 数学学院：提取到 20 位教师邮箱",
            "共 50 个邮箱",
        ]
        stats = _extract_stats_from_logs(logs)
        self.assertEqual(stats["teachers_found"], 50)
        self.assertEqual(stats["departments_done"], 2)
        self.assertEqual(stats["emails_extracted"], 50)

    def test_empty_logs(self):
        stats = _extract_stats_from_logs([])
        self.assertEqual(stats["teachers_found"], 0)
        self.assertEqual(stats["departments_done"], 0)


class TestSafeResolve(unittest.TestCase):
    """Test _safe_resolve path traversal protection."""

    def test_normal_path_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = _safe_resolve(base, "test.txt")
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "test.txt")

    def test_rejects_dotdot(self):
        base = Path("/tmp")
        result = _safe_resolve(base, "..", "etc")
        self.assertIsNone(result)


class TestIsValidPersonName(unittest.TestCase):
    """Test person name validation."""

    def test_valid_names(self):
        self.assertTrue(is_valid_person_name("张伟"))
        self.assertTrue(is_valid_person_name("李小明"))
        self.assertTrue(is_valid_person_name("欧阳修"))

    def test_invalid_names(self):
        self.assertFalse(is_valid_person_name("首页"))
        self.assertFalse(is_valid_person_name("师资队伍"))
        self.assertFalse(is_valid_person_name("教授"))
        self.assertFalse(is_valid_person_name("副教授"))
        self.assertFalse(is_valid_person_name("讲师"))
        self.assertFalse(is_valid_person_name("兼职教授"))
        self.assertFalse(is_valid_person_name("实验师"))
        self.assertFalse(is_valid_person_name("高级实验师"))


class TestIsValidEmailFormat(unittest.TestCase):
    """Test email format validation."""

    def test_valid_emails(self):
        self.assertTrue(EMAIL_RE.match("test@njfu.edu.cn"))
        self.assertTrue(EMAIL_RE.match("zhang.san@njau.edu.cn"))
        self.assertTrue(EMAIL_RE.match("test@njfu.edu.cn"))

    def test_invalid_emails(self):
        self.assertFalse(EMAIL_RE.match("not-a-email"))


class TestIsAdminEmail(unittest.TestCase):
    """Test admin email detection."""

    def test_admin_emails(self):
        self.assertTrue(is_admin_email("admin@njfu.edu.cn"))
        self.assertTrue(is_admin_email("webmaster@njfu.edu.cn"))

    def test_personal_emails(self):
        self.assertFalse(is_admin_email("zhangsan@njfu.edu.cn"))
        self.assertFalse(is_admin_email("lisi@njfu.edu.cn"))


class TestCleanTitle(unittest.TestCase):
    """Test title cleaning."""

    def test_clean_titles(self):
        self.assertEqual(clean_title("教授"), "教授")
        self.assertEqual(clean_title(" 副教授 "), "副教授")
        self.assertEqual(clean_title(""), "")

    def test_polluted_titles(self):
        self.assertEqual(clean_title("国家自然科学基金项目"), "")


class TestIsAcademicDomain(unittest.TestCase):
    """Test academic domain detection."""

    def test_academic_domains(self):
        self.assertTrue(is_academic_domain("test@njfu.edu.cn"))
        self.assertTrue(is_academic_domain("test@mit.edu"))

    def test_non_academic(self):
        self.assertFalse(is_academic_domain("test@gmail.com"))
        self.assertFalse(is_academic_domain("test@qq.com"))
