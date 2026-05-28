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


if __name__ == "__main__":
    unittest.main()
