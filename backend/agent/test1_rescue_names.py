"""更好地修复未知姓名 — 深度提取页面中的教师姓名"""
import asyncio
import csv
import re
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright 未安装")
    exit(1)

CSV_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_clean.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_final.csv"

# 从原始clean文件重新开始
with open(CSV_PATH, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

unknown = [(i, r) for i, r in enumerate(rows) if r["姓名"] == "未知" and r["邮箱"] != "无邮箱"]
print(f"需要修复的条目: {len(unknown)}")

BAD_NAMES = {"导航", "党委", "行政", "组织机构", "组织架构", "机构设置", "师资队伍",
             "教师", "教授", "副教授", "首页", "学院介绍", "学工园地", "捐赠",
             "诚聘英才", "报名方式", "双学位", "硕士生导师", "党群工作", "按专业",
             "英语系", "我所开发出250", "群众团体", "院行政",
             "师德师风监督举报邮箱", "平台基地", "研究生", "国家级青年人才",
             "最新更新", "医学伦理分委会", "院长信箱"}

def is_valid_name(name):
    if not name or name in BAD_NAMES:
        return False
    return bool(re.match(r"^[一-鿿]{2,4}$", name.strip()))

async def fix_names():
    fixed = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for idx, (i, r) in enumerate(unknown):
            url = r["主页链接"]
            email = r["邮箱"]
            if not url:
                continue

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(0.5)

                # 深度提取姓名：从多个位置查找
                name = await page.evaluate("""() => {
                    const bod = document.body?.innerText || '';
                    const lines = bod.split('\\n').filter(l => l.trim());

                    // 方法1：在页面文本中搜索与邮箱前缀匹配的附近文字
                    // 先尝试提取 h1-h3 中的人名
                    for (const sel of ['h1','h2','h3']) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const t = el.textContent.trim();
                            if (t.length <= 30) {
                                const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                                if (m) {
                                    const name = m[0];
                                    // 排除导航文字
                                    const bad = ["导航","党委","行政","组织","机构","师资","教师","教授",
                                                 "学院","首页","介绍","学工","捐赠","诚聘","报名","学位",
                                                 "导师","党群","专业","英语","平台","研究","最新","伦理",
                                                 "院长","群众","师德"];
                                    if (!bad.some(b => name.includes(b))) return name;
                                }
                            }
                        }
                    }

                    // 方法2：找包含"教授"/"讲师"等职称前面的人名
                    for (const line of lines) {
                        if (line.length <= 50 && /(教授|副教授|讲师|研究员|工程师|实验师)/.test(line)) {
                            const m = line.match(/^[\\u4e00-\\u9fff]{2,4}/);
                            if (m) return m[1];
                        }
                    }

                    // 方法3：找页面中的独立中文字符串（可能是姓名）
                    for (const line of lines) {
                        const t = line.trim();
                        if (/^[\\u4e00-\\u9fff]{2,3}$/.test(t)) {
                            const bad = ["导航","党委","行政","组织","机构","师资","教师","教授",
                                         "学院","首页","介绍","学工","捐赠","诚聘","报名","学位",
                                         "导师","党群","专业","英语","平台","研究","最新","伦理",
                                         "院长","群众","师德","电话","传真","邮箱","地址","邮编",
                                         "联系","方式","办公","通讯","个人","简介","研究","方向",
                                         "开设","课程","代表","成果","学术","论文","著作","获奖"];
                            if (!bad.some(b => t.includes(b))) return t;
                        }
                    }

                    return '';
                }""")

                if is_valid_name(name):
                    rows[i]["姓名"] = name
                    fixed += 1
                    print(f"  ✅ [{idx+1}/{len(unknown)}] → {name} | {email}")
                else:
                    # 尝试从email推断
                    print(f"  ❌ [{idx+1}/{len(unknown)}] 未找到姓名 (got: '{name}') | {email} | {url[:80]}")

            except Exception as e:
                print(f"  ⚠️ [{idx+1}/{len(unknown)}] 错误: {e}")

        await context.close()
        await browser.close()

    print(f"\n修复: {fixed}/{len(unknown)}")

    # 最终清洗
    final = []
    BAD_NAMES_FINAL = BAD_NAMES | {"未知"}
    for r in rows:
        name = r["姓名"].strip()
        email = r["邮箱"].strip()
        if name in BAD_NAMES_FINAL and not email:
            continue
        if name in BAD_NAMES_FINAL and email:
            r["姓名"] = "未知"
        if not email:
            r["邮箱"] = "无邮箱"
        final.append(r)

    total = len(final)
    has_email = sum(1 for r in final if r["邮箱"] != "无邮箱")
    print(f"最终: {total}条, 有邮箱: {has_email}条, 未知姓名: {sum(1 for r in final if r['姓名']=='未知')}条")

    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        writer.writerows(final)

    print(f"💾 已保存: {OUT_PATH}")

asyncio.run(fix_names())
