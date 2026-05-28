"""清理 NJU CS 爬虫结果 — 移除错误条目并重新导出。"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

TASK_ID = "a468ea4c-1347-4a08-adc8-696eb43df27c"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
TASK_DIR = OUTPUT_DIR / TASK_ID

# 读取原始XLSX
import openpyxl

xlsx_files = sorted(TASK_DIR.glob("南京大学_计算机学院_教师邮箱_*.xlsx"))
if not xlsx_files:
    logger.error("未找到 XLSX 文件！")
    exit(1)

latest = xlsx_files[-1]
logger.info(f"读取: {latest}")

wb = openpyxl.load_workbook(latest)
ws = wb.active

# 读取所有数据
data = []
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[1]:  # 有姓名
        data.append({
            "name": str(row[1]).strip(),
            "email": str(row[2]).strip() if row[2] else "",
            "department": str(row[3]).strip() if row[3] else "",
            "title": str(row[4]).strip() if row[4] else "",
            "url": str(row[5]).strip() if row[5] else "",
        })

logger.info(f"原始: {len(data)} 条")

# 需要排除的假数据
BAD_NAMES = {
    "南大概况", "南京大学", "计算机系", "计算机学院",
    "师资队伍", "教授", "副教授", "讲师",
    "联系人", "联系方式", "地址", "邮编", "电话",
    "版权所有", "首页", "学院概况",
}

# 过滤
clean = []
removed = []
for r in data:
    name = r["name"]
    if name in BAD_NAMES:
        removed.append(r)
        continue
    if len(name) < 2:
        removed.append(r)
        continue
    # 排除全角/半角混用且不像是人名的
    import re
    if not re.match(r"^[一-鿿]{2,4}$", name):
        removed.append(r)
        continue
    # 把 None 邮箱转为空字符串
    if r["email"] in ("None", "无", "-"):
        r["email"] = ""
    if r["title"] in ("None",):
        r["title"] = ""
    clean.append(r)

logger.info(f"移除: {len(removed)} 条")
for r in removed:
    logger.info(f"  ✗ {r['name']}")

logger.info(f"清洗后: {len(clean)} 条")

# 重新导出
from agent.exporter import export_xlsx
xlsx_path = export_xlsx(clean, "南京大学_计算机学院_教师邮箱", TASK_ID)

has_email = sum(1 for r in clean if r["email"])
logger.info(f"\n===== 最终结果 =====")
logger.info(f"总教师: {len(clean)}")
logger.info(f"有邮箱: {has_email}")
logger.info(f"文件: {xlsx_path}")

# 展示无邮箱的
no_email = [r for r in clean if not r["email"]]
if no_email:
    logger.info(f"\n无邮箱 ({len(no_email)} 人):")
    for r in no_email:
        logger.info(f"  {r['name']:6s} | {r['url'][:60]}")

print("\n[FILES]")
print(f"{xlsx_path.name} | 南京大学计算机学院教师邮箱 (共{len(clean)}条，{has_email}个邮箱)")
print("[/FILES]")
