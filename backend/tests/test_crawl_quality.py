"""evaluator.py 单元测试 — 使用模拟 CSV 数据验证各评估维度。"""

import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.evaluator import (
    validate_crawl_output,
    save_quality_report,
    _is_valid_email,
    _is_dirty_name,
)


def _make_csv(content: str) -> str:
    """用 StringIO 无法直接传路径，故写入临时文件返回路径。"""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", encoding="utf-8-sig", delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestEmailValidation(unittest.TestCase):
    """邮箱格式校验（纯函数）。"""

    def test_valid_edu_email(self):
        self.assertTrue(_is_valid_email("zhangsan@nju.edu.cn"))

    def test_valid_gmail(self):
        self.assertTrue(_is_valid_email("professor@gmail.com"))

    def test_empty_email(self):
        self.assertFalse(_is_valid_email(""))

    def test_missing_at(self):
        self.assertFalse(_is_valid_email("zhangsan.nju.edu.cn"))

    def test_double_at(self):
        self.assertFalse(_is_valid_email("a@b@c.com"))


class TestDirtyNameDetection(unittest.TestCase):
    """脏数据姓名检测。"""

    def test_normal_chinese_name(self):
        self.assertFalse(_is_dirty_name("张三"))

    def test_three_char_name(self):
        self.assertFalse(_is_dirty_name("欧阳娜娜"))

    def test_nav_keyword_home(self):
        self.assertTrue(_is_dirty_name("首页"))

    def test_nav_keyword_faculty(self):
        self.assertTrue(_is_dirty_name("师资队伍"))

    def test_empty_name(self):
        self.assertTrue(_is_dirty_name(""))

    def test_numeric_name(self):
        self.assertTrue(_is_dirty_name("123"))

    def test_english_short(self):
        self.assertTrue(_is_dirty_name("Home"))


class TestPerfectData(unittest.TestCase):
    """完美数据 → quality_score >= 90, passed=True。"""

    def test_perfect_csv(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,li@nju.edu.cn,计算机学院,副教授\n"
            "王五,wang@nju.edu.cn,计算机学院,讲师\n"
            "赵六,zhao@nju.edu.cn,计算机学院,教授\n"
            "钱七,qian@nju.edu.cn,软件学院,教授\n"
            "孙八,sun@nju.edu.cn,软件学院,副教授\n"
            "周九,zhou@nju.edu.cn,软件学院,教授\n"
            "吴十,wu@nju.edu.cn,人工智能学院,研究员\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-perfect")
            self.assertGreaterEqual(report["quality_score"], 90)
            self.assertTrue(report["passed"])
            self.assertEqual(len(report["warnings"]), 0)
            self.assertEqual(report["details"]["total_rows"], 8)
            self.assertEqual(report["details"]["email_coverage"]["rows_with_email"], 8)
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestNoEmailData(unittest.TestCase):
    """无邮箱数据 → email_rate=0, passed=False, warnings 含 '邮箱覆盖率'。"""

    def test_no_email_csv(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,,计算机学院,教授\n"
            "李四,,计算机学院,副教授\n"
            "王五,,软件学院,讲师\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-noemail")
            self.assertEqual(report["details"]["email_coverage"]["rate"], 0.0)
            self.assertFalse(report["passed"])
            self.assertTrue(any("邮箱覆盖率" in w for w in report["warnings"]))
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestDirtyDataWarning(unittest.TestCase):
    """脏数据（姓名列为系统文字）→ details.dirty_data 有记录。"""

    def test_dirty_names_csv(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "首页,,,\n"
            "师资队伍,,,\n"
            "联系我们,,,\n"
            "李四,li@nju.edu.cn,计算机学院,副教授\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-dirty")
            self.assertEqual(report["details"]["dirty_data"]["dirty_count"], 3)
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestDuplicateEmailDetection(unittest.TestCase):
    """重复邮箱 → duplicate_email_count > 0。"""

    def test_duplicate_emails_csv(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "张三重复,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,li@nju.edu.cn,软件学院,副教授\n"
            "李四重复,li@nju.edu.cn,软件学院,副教授\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-dup")
            self.assertGreater(report["details"]["dedup"]["duplicate_emails"], 0)
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestCompletenessCheck(unittest.TestCase):
    """数据完整性 — 必填字段空值率高时产生 warning。"""

    def test_missing_department(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,,教授\n"
            "李四,li@nju.edu.cn,,副教授\n"
            "王五,wang@nju.edu.cn,,讲师\n"
            "赵六,zhao@nju.edu.cn,计算机学院,教授\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-complete")
            # 学院字段 3/4 为空，应触发完整性 warning
            completeness = report["details"]["completeness"]
            if "学院" in completeness:
                self.assertLess(completeness["学院"]["fill_rate"], 0.5)
                self.assertTrue(
                    any("学院" in w for w in report["warnings"])
                )
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestDepartmentCoverage(unittest.TestCase):
    """学院覆盖率 — 提供 university_config 时检测缺失学院。"""

    def test_missing_departments(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,li@nju.edu.cn,软件学院,副教授\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            config = {
                "departments": ["计算机学院", "软件学院", "人工智能学院", "网络空间安全学院"]
            }
            report = validate_crawl_output(csv_path, task_id="test-dept", university_config=config)
            dept_cov = report["details"]["department_coverage"]
            self.assertEqual(len(dept_cov["missing"]), 2)
            self.assertIn("人工智能学院", dept_cov["missing"])
            self.assertIn("网络空间安全学院", dept_cov["missing"])
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestTitleDistribution(unittest.TestCase):
    """职称分布统计。"""

    def test_title_counts(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,li@nju.edu.cn,计算机学院,教授\n"
            "王五,wang@nju.edu.cn,计算机学院,副教授\n"
            "赵六,zhao@nju.edu.cn,软件学院,讲师\n"
            "钱七,qian@nju.edu.cn,软件学院,讲师\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-title")
            dist = report["details"]["title_distribution"]
            self.assertEqual(dist.get("教授"), 2)
            self.assertEqual(dist.get("副教授"), 1)
            self.assertEqual(dist.get("讲师"), 2)
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestReportPersistence(unittest.TestCase):
    """评估报告读写。"""

    def test_save_report(self):
        report = {
            "task_id": "test-123",
            "quality_score": 85,
            "passed": True,
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = save_quality_report(report, tmp)
            self.assertTrue(Path(path).exists())

            # 手动读取验证写入内容
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["quality_score"], 85)
            self.assertTrue(loaded["passed"])


class TestEdgeCases(unittest.TestCase):
    """边界情况。"""

    def test_empty_csv(self):
        csv_content = "姓名,邮箱,学院,职称\n"
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-empty")
            self.assertTrue(any("空" in w for w in report["warnings"]))
        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_nonexistent_file(self):
        report = validate_crawl_output("/nonexistent/file.csv", task_id="test-missing")
        self.assertEqual(report["quality_score"], 0)
        self.assertFalse(report["passed"])

    def test_invalid_email_shows_in_warnings(self):
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,not-an-email,计算机学院,副教授\n"
            "王五,also@@bad,软件学院,讲师\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            report = validate_crawl_output(csv_path, task_id="test-invalid")
            self.assertEqual(report["details"]["email_validation"]["invalid"], 2)
            self.assertTrue(any("格式异常" in w for w in report["warnings"]))
        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_custom_email_rate_threshold(self):
        """通过 university_config 自定义邮箱覆盖率阈值。"""
        csv_content = (
            "姓名,邮箱,学院,职称\n"
            "张三,zhang@nju.edu.cn,计算机学院,教授\n"
            "李四,,计算机学院,副教授\n"
            "王五,wang@nju.edu.cn,软件学院,讲师\n"
            "赵六,,软件学院,教授\n"
        )
        csv_path = _make_csv(csv_content)
        try:
            # 默认阈值 70%，4行里只有2个邮箱 = 50%，应触发 warning
            report_default = validate_crawl_output(csv_path, task_id="test-def")
            self.assertTrue(any("邮箱覆盖率" in w for w in report_default["warnings"]))

            # 自定义阈值 40%，50% > 40%，不应触发 warning
            report_custom = validate_crawl_output(
                csv_path, task_id="test-custom", university_config={"min_email_rate": 0.4}
            )
            self.assertFalse(any("邮箱覆盖率" in w for w in report_custom["warnings"]))
        finally:
            Path(csv_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
