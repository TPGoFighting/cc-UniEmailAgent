"""爬取南大电子科学与工程学院教师邮箱"""
import re
import json
import time
import csv
import os
import sys
import subprocess

BASE_URL = "https://ese.nju.edu.cn"
REDIRECT_TPL = f"{BASE_URL}/_redirect?siteId=452&columnId=30446&articleId={{}}"
OUTPUT_DIR = "outputs/tmp"
OUTPUT_CSV = "outputs/电子科学_补全.csv"
HTML_DIR = os.path.join(OUTPUT_DIR, "profile_pages")

os.makedirs(HTML_DIR, exist_ok=True)

def extract_article_ids():
    """从目录页提取所有教师 articleId"""
    path = os.path.join(OUTPUT_DIR, "directory.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    links = re.findall(
        r"<a href='/_redirect\?siteId=452&columnId=30446&articleId=(\d+)'[^>]*title='([^']+)'",
        content,
    )
    seen = set()
    result = []
    for aid, name in links:
        if aid not in seen:
            seen.add(aid)
            result.append((name, aid))
    return result


def fetch_page(url, timeout=20):
    """使用 curl 获取页面内容（保存到临时文件避免编码问题）"""
    tmpfile = os.path.join(HTML_DIR, "_tmp_download.html")
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(timeout),
             "-w", "%{url_effective}", "-o", tmpfile, url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        final_url = result.stdout.strip()
        if os.path.exists(tmpfile):
            with open(tmpfile, "rb") as f:
                raw = f.read()
            html = raw.decode("utf-8", errors="replace")
            os.remove(tmpfile)
            return html, final_url if final_url else url
        return "", url
    except Exception as e:
        print(f"  fetch error: {e}", file=sys.stderr)
        return "", url


def parse_profile(html, name, profile_url):
    """从教师页面提取邮箱和职称"""
    if not html:
        return None, None, None

    # 提取邮箱
    emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html))

    # 去除常见的页面模板邮箱
    noise_emails = {
        "zhanghao@nju.edu.cn",  # 网站联系人
        "nju.edu.cn",  # 域名本身
    }

    teacher_emails = emails - noise_emails

    # 用"邮件："或"Email："来找教师个人邮箱
    email_match = re.search(r"(?:邮件|Email|email|邮箱)[：:]\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", html)
    personal_email = email_match.group(1) if email_match else None

    # 如果没有找到"邮件："标记，使用所有非噪声邮箱的第一个
    if not personal_email and teacher_emails:
        # 排除页面共用邮箱
        for e in teacher_emails:
            if "zhanghao" not in e:
                personal_email = e
                break

    # 提取文本以找职称
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 找职称
    title = None
    title_patterns = [
        rf"{name}[，,]\s*电子科学与工程学院\s*([^，,\s]+(?:教授|研究员|副教授|讲师|工程师|博导))",
        rf"{name}[，,][^。]*?([^，,\s]+(?:教授|研究员|副教授|讲师|工程师))",
        rf"{name}[^。]{0,50}?(教授|研究员|副教授|讲师|工程师)",
        r"职称[：:]\s*(\S+)",
    ]
    for pat in title_patterns:
        m = re.search(pat, text)
        if m:
            try:
                title = (m.group(1) or "").strip()
            except (AttributeError, IndexError):
                title = m.group(0).strip()
            if title:
                break

    # 找系别
    dept = None
    dept_match = re.search(r"(电子工程系|通信工程系|微电子与光电子学系|信息电子学系)", text)
    if dept_match:
        dept = dept_match.group(1)

    return personal_email, title, dept


def main():
    teachers = extract_article_ids()
    print(f"共找到 {len(teachers)} 位教师")

    results = []
    success = 0
    fail = 0

    for i, (name, article_id) in enumerate(teachers):
        print(f"[{i+1}/{len(teachers)}] {name} (articleId={article_id}) ...", end=" ", flush=True)

        redirect_url = REDIRECT_TPL.format(article_id)
        html, final_url = fetch_page(redirect_url)

        if not html or len(html) < 500:
            print("❌ 页面为空")
            fail += 1
            results.append({
                "name": name, "email": "", "college": "电子科学与工程学院",
                "title": "", "url": "", "status": "empty_page"
            })
            continue

        # 保存页面
        html_path = os.path.join(HTML_DIR, f"{article_id}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        email, title, dept = parse_profile(html, name, final_url)

        if email:
            print(f"✅ {email} | {title or '?'}")
            success += 1
        else:
            print(f"⚠ 无邮箱 | {title or '?'}")
            fail += 1

        results.append({
            "name": name, "email": email or "", "college": "电子科学与工程学院",
            "title": title or "", "url": final_url, "dept": dept or "",
            "article_id": article_id, "status": "ok" if email else "no_email"
        })

        # 礼貌延迟
        time.sleep(0.3)

    # 保存 CSV
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for idx, r in enumerate(results, 1):
            writer.writerow([
                idx, r["name"], r["email"], r["college"], r["title"], r["url"]
            ])

    # 保存 JSON 备份
    json_path = os.path.join(OUTPUT_DIR, "crawl_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n===== 完成 =====")
    print(f"成功: {success}, 无邮箱: {fail}, 总计: {len(teachers)}")
    print(f"CSV 已保存到: {OUTPUT_CSV}")
    print(f"JSON 已保存到: {json_path}")


if __name__ == "__main__":
    main()
