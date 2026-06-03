#!/usr/bin/env python3
"""南京理工大学教师邮箱批量爬取脚本"""
import asyncio
import aiohttp
import json
import re
import csv
import os
from datetime import datetime

# 任务ID
TASK_ID = "3f22492c-4fa1-4744-869c-18bae396c477"
OUTPUT_DIR = os.path.join("outputs", TASK_ID)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 加载教师列表
with open("njust_all_teachers.json", "r", encoding="utf-8") as f:
    teachers = json.load(f)

print(f"总教师数: {len(teachers)}")

# 邮箱正则
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 反爬邮箱恢复
ANTI_SPAM = [
    (r'\[at\]', '@'), (r'\(at\)', '@'), (r'#@', '@'),
    (r'\[\s*@\s*\]', '@'), (r'\(\s*@\s*\)', '@'),
]

async def fetch_email(session, teacher, semaphore):
    """访问教师主页提取邮箱"""
    url = teacher.get("cnUrl", "")
    if not url:
        return None

    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()

                # 先恢复反爬格式
                for pattern, repl in ANTI_SPAM:
                    text = re.sub(pattern, repl, text)

                emails = EMAIL_REGEX.findall(text)

                # 过滤公共邮箱
                public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master',
                                   'root', 'postmaster', 'wxyxz', 'xwcb', 'bgs',
                                   'dangzheng', 'yuanban', 'office']
                personal_emails = []
                for e in emails:
                    prefix = e.split('@')[0].lower()
                    if not any(prefix.startswith(p) for p in public_prefixes):
                        personal_emails.append(e)

                return personal_emails[0] if personal_emails else "无邮箱"
        except Exception as e:
            return "无邮箱"

async def main():
    semaphore = asyncio.Semaphore(20)  # 20并发
    connector = aiohttp.TCPConnector(limit=50)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = []
        for teacher in teachers:
            tasks.append(fetch_email(session, teacher, semaphore))

        print(f"开始爬取 {len(tasks)} 个教师邮箱...")
        results = await asyncio.gather(*tasks)

        # 组装数据
        csv_data = []
        email_count = 0
        no_email_count = 0

        for teacher, email in zip(teachers, results):
            name = teacher.get("title", "")
            dept = teacher.get("department", "")
            career = teacher.get("career", "")
            url = teacher.get("cnUrl", "")

            if email and email != "无邮箱":
                email_count += 1
            else:
                no_email_count += 1

            csv_data.append({
                "姓名": name,
                "邮箱": email if email else "无邮箱",
                "学院": dept,
                "职称": career,
                "主页链接": url
            })

        print(f"\n结果统计:")
        print(f"  有邮箱: {email_count}")
        print(f"  无邮箱: {no_email_count}")

        # 按学院统计
        dept_stats = {}
        for d in csv_data:
            dept = d["学院"]
            if dept not in dept_stats:
                dept_stats[dept] = {"total": 0, "with_email": 0}
            dept_stats[dept]["total"] += 1
            if d["邮箱"] != "无邮箱":
                dept_stats[dept]["with_email"] += 1

        print("\n各学院统计:")
        for dept, stats in sorted(dept_stats.items(), key=lambda x: -x[1]["total"]):
            print(f"  {dept}: {stats['total']}人, {stats['with_email']}人有邮箱")

        # 导出CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(OUTPUT_DIR, f"南京理工大学_教师邮箱_{timestamp}.csv")

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
            writer.writeheader()
            writer.writerows(csv_data)

        print(f"\nCSV已保存: {csv_path}")

        # 同时导出到outputs根目录（兼容旧链接）
        root_csv = f"南京理工大学_教师邮箱_{timestamp}.csv"
        with open(root_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
            writer.writeheader()
            writer.writerows(csv_data)
        print(f"同步保存到根目录: {root_csv}")

if __name__ == "__main__":
    asyncio.run(main())
