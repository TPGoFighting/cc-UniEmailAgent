"""清华大学计算机系教师邮箱爬取脚本 — 使用 meta description 标签快速提取"""

import re
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.cs.tsinghua.edu.cn"

# 39 位教师名录（从教职工名录页提取）
TEACHER_LINKS = {
    "冯建华": "/info/1111/3490.htm",
    "冯铃": "/info/1111/3489.htm",
    "李国良": "/info/1111/3488.htm",
    "李涓子": "/info/1111/3487.htm",
    "唐杰": "/info/1111/3486.htm",
    "王建勇": "/info/1111/3485.htm",
    "许斌": "/info/1111/5271.htm",
    "喻文健": "/info/1111/4776.htm",
    "周强": "/info/1111/2004.htm",
    "陈渝": "/info/1112/3500.htm",
    "东昱晓": "/info/1112/5837.htm",
    "侯磊": "/info/1112/7030.htm",
    "王健楠": "/info/1112/6905.htm",
    "戴桂兰": "/info/1113/5098.htm",
    "潘捷": "/info/1113/6640.htm",
    "孙佶": "/info/1113/7061.htm",
    "韩旭": "/info/1114/6422.htm",
    "金煜阳": "/info/1114/6843.htm",
    "赵文来": "/info/1114/3943.htm",
    "艾海舟": "/info/1116/3537.htm",
    "胡事民": "/info/1116/3536.htm",
    "贾珈": "/info/1116/4777.htm",
    "刘永进": "/info/1116/3535.htm",
    "史元春": "/info/1116/3534.htm",
    "孙立峰": "/info/1116/3533.htm",
    "兴军亮": "/info/1116/5088.htm",
    "张松海": "/info/1116/7039.htm",
    "周悦芝": "/info/1116/3530.htm",
    "朱文武": "/info/1116/3529.htm",
    "崔鹏": "/info/1117/3545.htm",
    "穆太江": "/info/1117/6628.htm",
    "任炬": "/info/1117/4596.htm",
    "陶品": "/info/1117/3542.htm",
    "王鑫": "/info/1117/5849.htm",
    "王运涛": "/info/1117/5273.htm",
    "徐昆": "/info/1117/3540.htm",
    "喻纯": "/info/1117/3539.htm",
    "孟媛": "/info/1118/5694.htm",
    "徐群策": "/info/1118/6617.htm",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

ADMIN_EMAIL_PATTERNS = [
    r"^webmaster@", r"^admin@", r"^office@", r"^info@",
    r"^master@", r"^root@", r"^postmaster@", r"^service@",
    r"^support@", r"^help@", r"^contact@",
]


def is_admin_email(email: str) -> bool:
    return any(re.search(p, email, re.IGNORECASE) for p in ADMIN_EMAIL_PATTERNS)


def _extract_email_from_text(text: str) -> str | None:
    """从文本中提取邮箱，确保不截取多余字符。"""
    match = re.search(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:[a-zA-Z]{2,})(?![a-zA-Z])',
        text
    )
    if not match:
        return None
    email = match.group(0)
    # 后处理：去掉末尾可能的多余字符
    email = re.sub(r'(URL|http|ＵＲＬ).*$', '', email, flags=re.IGNORECASE).strip()
    email = email.rstrip('.')
    return email if '@' in email and '.' in email.split('@')[1] else None


def extract_teacher_info(name: str, rel_path: str) -> dict:
    url = BASE_URL + rel_path
    result = {
        "姓名": name,
        "邮箱": "无邮箱",
        "职称": "",
        "学院": "清华大学计算机科学与技术系",
        "主页链接": url,
    }

    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                logger.warning(f"[{name}] HTTP {resp.status_code}")
                time.sleep(1)
                continue

            html = resp.text

            # 方法1：从 meta description 标签提取（最可靠）
            meta_match = re.search(
                r'<meta[^>]+name\s*=\s*["\']description["\'][^>]+content\s*=\s*["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if not meta_match:
                meta_match = re.search(
                    r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+name\s*=\s*["\']description["\']',
                    html, re.IGNORECASE
                )

            has_email = False
            if meta_match:
                desc = meta_match.group(1)
                # 提取职称：匹配"职称："后直到下一个字段名之间的文本
                # 优先用字段分隔符法（能处理含"研究"的职称）
                title_match = re.search(
                    r'职称[：:](.+?)(?:电话[：：]|邮箱[：：]|邮件[：：]|教育背景|工作履历|社会兼职|研究领域|讲授课程|获奖荣誉)',
                    desc
                )
                if title_match:
                    result["职称"] = title_match.group(1).strip()
                else:
                    # 备用方法：排除法
                    title_match2 = re.search(
                        r'职称[：:]\s*([^电邮手微姓名电话教育背景工作履历社会兼职\s]{2,20})',
                        desc
                    )
                    if title_match2:
                        result["职称"] = title_match2.group(1).strip()

                # 提取邮箱
                email = _extract_email_from_text(desc)
                if email and not is_admin_email(email):
                    result["邮箱"] = email
                    has_email = True

            # 如果 meta 中没有邮箱，执行全页搜索（后备）
            if not has_email:
                email = _extract_email_from_text(html)
                if email and not is_admin_email(email):
                    result["邮箱"] = email
                    has_email = True

            # 如果 meta 中没找到职称，全页搜索
            if not result["职称"]:
                soup = BeautifulSoup(html, "html.parser")
                body_text = soup.get_text()
                for t in ["教授", "副教授", "讲师", "研究员", "副研究员",
                          "助理研究员", "高级工程师", "工程师", "助理教授",
                          "博士后", "院士"]:
                    if t in body_text[:2000]:
                        result["职称"] = t
                        break

            logger.info(f"[{name}] √ 职称={result['职称']}, 邮箱={result['邮箱']}")
            break

        except requests.RequestException as e:
            logger.warning(f"[{name}] 请求失败: {e}")
            time.sleep(2)

    return result


def main():
    output_dir = Path(__file__).parent.parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"清华大学_计算机系教师邮箱_{timestamp}.xlsx"

    teachers_data = []
    for idx, (name, rel_path) in enumerate(TEACHER_LINKS.items(), 1):
        logger.info(f"[{idx}/{len(TEACHER_LINKS)}] 正在爬取: {name}")
        info = extract_teacher_info(name, rel_path)
        teachers_data.append(info)
        time.sleep(1)

    # 导出 XLSX
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "清华计算机系教师邮箱"

    headers = ["姓名", "邮箱", "学院", "职称", "主页链接"]
    ws.append(headers)
    for row in teachers_data:
        ws.append([row[h] for h in headers])

    # 列宽
    widths = [12, 35, 30, 15, 55]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w

    wb.save(str(output_file))
    logger.info(f"✅ 已保存: {output_file}")
    logger.info(f"📊 共 {len(teachers_data)} 位教师")

    with_email = sum(1 for t in teachers_data if t["邮箱"] != "无邮箱")
    logger.info(f"📧 有邮箱: {with_email}/{len(teachers_data)}")
    if with_email < len(teachers_data):
        no_email = [t["姓名"] for t in teachers_data if t["邮箱"] == "无邮箱"]
        logger.info(f"❌ 无邮箱: {', '.join(no_email)}")

    return output_file


if __name__ == "__main__":
    main()
