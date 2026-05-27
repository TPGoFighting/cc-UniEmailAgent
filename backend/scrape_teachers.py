"""
南京大学计算机学院教师邮箱抓取脚本（使用 curl，绕过 SSL 兼容性问题）
"""
import subprocess
import re
import time

# 教师列表: (姓名, URL路径)
professors = [
    ("吕建", "/58/2a/c2639a153642/page.htm"),
    ("谭铁牛", "/99/28/c2639a629032/page.htm"),
    ("周志华", "https://www.nju.edu.cn/info/1040/372961.htm"),
    ("李宣东", "/58/28/c2639a153640/page.htm"),
    ("宋方敏", "/58/24/c2639a153636/page.htm"),
    ("陈贵海", "/58/26/c2639a153638/page.htm"),
    ("陈家骏", "/58/22/c2639a153634/page.htm"),
    ("谢俊元", "/58/21/c2639a153633/page.htm"),
    ("孙正兴", "/58/20/c2639a153632/page.htm"),
    ("茅兵", "/58/1f/c2639a153631/page.htm"),
    ("陆桑璐", "/58/1e/c2639a153630/page.htm"),
    ("武港山", "/58/1b/c2639a153627/page.htm"),
    ("曾庆凯", "/58/1a/c2639a153626/page.htm"),
    ("窦万春", "/58/19/c2639a153625/page.htm"),
    ("赵建华", "/58/18/c2639a153624/page.htm"),
    ("徐宝文", "/58/17/c2639a153623/page.htm"),
    ("陈力军", "/58/16/c2639a153622/page.htm"),
    ("陶先平", "/58/15/c2639a153621/page.htm"),
    ("高阳", "/58/14/c2639a153620/page.htm"),
    ("顾庆", "/58/13/c2639a153619/page.htm"),
    ("马晓星", "/58/12/c2639a153618/page.htm"),
    ("徐锋", "/58/11/c2639a153617/page.htm"),
    ("郭延文", "/58/0f/c2639a153615/page.htm"),
    ("叶保留", "/58/0e/c2639a153614/page.htm"),
    ("黄宜华", "/58/0d/c2639a153613/page.htm"),
    ("袁春风", "/58/0c/c2639a153612/page.htm"),
    ("周毓明", "/58/0b/c2639a153611/page.htm"),
    ("瞿裕忠", "/58/0a/c2639a153610/page.htm"),
    ("聂长海", "/58/09/c2639a153609/page.htm"),
    ("仲盛", "/58/08/c2639a153608/page.htm"),
    ("王崇骏", "/58/06/c2639a153606/page.htm"),
    ("王林章", "/58/03/c2639a153603/page.htm"),
    ("杨育彬", "/58/02/c2639a153602/page.htm"),
    ("路通", "/58/01/c2639a153601/page.htm"),
    ("许畅", "/58/00/c2639a153600/page.htm"),
    ("尹一通", "/57/ff/c2639a153599/page.htm"),
    ("卜磊", "/c9/6f/c2639a51567/page.htm"),
    ("林冰凯", "/97/c0/c2639a432064/page.htm"),
    ("王利民", "/2f/cc/c2639a274380/page.htm"),
    ("冯新宇", "/a1/ca/c2639a238026/page.htm"),
    ("许封元", "/6f/7d/c2639a159613/page.htm"),
    ("李文中", "/c9/41/c2639a51521/page.htm"),
    ("黄宇", "/c9/3f/c2639a51519/page.htm"),
    ("曹春", "/c9/3b/c2639a51515/page.htm"),
    ("李武军", "/c9/54/c2639a51540/page.htm"),
    ("谢磊", "/c9/77/c2639a51575/page.htm"),
    ("钱柱中", "/c9/4b/c2639a51531/page.htm"),
    ("田臣", "/51/c1/c2639a86465/page.htm"),
    ("张天", "/c9/43/c2639a51523/page.htm"),
    ("刘奇志", "/c9/6b/c2639a51563/page.htm"),
    ("王炜", "/c9/52/c2639a51538/page.htm"),
    ("程龚", "/c9/37/c2639a51511/page.htm"),
    ("栗师", "/9f/b9/c2639a630713/page.htm"),
    ("胡伟", "/c9/4f/c2639a51535/page.htm"),
    ("华景煜", "/c9/cf/c2639a51663/page.htm"),
    ("黄书剑", "/c9/d2/c2639a51666/page.htm"),
    ("史颖欢", "/7c/5e/c2639a293982/page.htm"),
    ("姚鹏晖", "/2f/cd/c2639a274381/page.htm"),
    ("张渊", "/c9/cd/c2639a51661/page.htm"),
    ("戴海鹏", "/c9/d4/c2639a51668/page.htm"),
    ("李樾", "/74/a2/c2639a423074/page.htm"),
    ("梁红瑾", "/7f/97/c2639a229271/page.htm"),
    ("王晓亮", "/c9/5f/c2639a51551/page.htm"),
    ("王轲", "/a0/2b/c2639a761899/page.htm"),
    ("金莹", "/5a/a1/c2639a744097/page.htm"),
    ("张莉", "/5a/a2/c2639a744098/page.htm"),
]

associate_professors = [
    ("柏文阳", "/c9/4d/c2640a51533/page.htm"),
    ("唐杰", "/c9/59/c2640a51545/page.htm"),
    ("李宁", "/c9/69/c2640a51561/page.htm"),
    ("杨若瑜", "/c9/65/c2640a51557/page.htm"),
    ("苏丰", "/c9/55/c2640a51541/page.htm"),
    ("余萍", "/57/16/c2640a153366/page.htm"),
    ("吴楠", "/c9/35/c2640a51509/page.htm"),
    ("商琳", "/c9/47/c2640a51527/page.htm"),
    ("陈鑫", "/57/15/c2640a153365/page.htm"),
    ("张岩", "/c9/6d/c2640a51565/page.htm"),
    ("张胜", "/c9/e4/c2640a51684/page.htm"),
    ("许蕾", "/c9/67/c2640a51559/page.htm"),
    ("胡昊", "/c9/61/c2640a51553/page.htm"),
    ("马骏", "/_redirect?siteId=66&columnId=2640&articleId=51673"),
    ("刘佳", "/58/6a/c2640a153706/page.htm"),
    ("姚远", "/22/9c/c2640a139932/page.htm"),
    ("汪亮", "/c9/d5/c2640a51669/page.htm"),
    ("刘景铖", "/94/21/c2640a562209/page.htm"),
    ("张洁", "/5a/a3/c2640a744099/page.htm"),
    ("陶烨", "/5a/a5/c2640a744101/page.htm"),
]


def fetch_email(url_path):
    """抓取单个教师页面的邮箱（使用 curl 绕过 SSL 兼容性问题）"""
    if url_path.startswith("http"):
        full_url = url_path
    else:
        full_url = f"https://cs.nju.edu.cn{url_path}"

    try:
        result = subprocess.run(
            ["curl", "-sk", "--max-time", "30", full_url],
            capture_output=True, timeout=35
        )
        content = result.stdout.decode('utf-8', errors='replace')

        if not content:
            return "页面为空"

        # 先去除 HTML 标签，再处理反爬
        content = re.sub(r'<[^>]+>', '', content)
        # 反爬恢复
        content = content.replace("[at]", "@").replace("(at)", "@").replace("#@", "@").replace("[@]", "@")
        # 把 HTML 反爬中 # 替换为 @（如 gswu#nju.edu.cn）
        content = re.sub(r'([\w\.-]+)#([\w\.-]+\.\w+)', r'\1@\2', content)

        # 匹配邮箱
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content)
        # 清洗：移除 TLD 后紧跟的大写字母开头单词（如 haipengdai@nju.edu.cnHaipeng）
        emails = [re.sub(r'(\.[a-zA-Z]{2,3})[A-Z][a-z].*$', r'\1', e) for e in emails]
        # 过滤掉常见的非教师邮箱
        skip_patterns = ['example', '.png', '.jpg', '.gif', 'webmaster', 'noreply',
                         'admin@', 'support@', 'info@', 'contact@', 'postmaster',
                         'mailto@', 'abuse@', 'no-reply']
        valid_emails = [e for e in emails
                        if not any(p in e.lower() for p in skip_patterns)]

        if valid_emails:
            return valid_emails[0]
        return "未找到"
    except subprocess.TimeoutExpired:
        return "超时"
    except Exception as e:
        return f"错误: {e}"


if __name__ == "__main__":
    import csv
    from datetime import datetime

    all_teachers = [("教授", p[0], p[1]) for p in professors] + \
                   [("副教授", p[0], p[1]) for p in associate_professors]

    print(f"共 {len(all_teachers)} 位教师，开始抓取邮箱...\n")

    results = []
    for i, (title, name, url) in enumerate(all_teachers, 1):
        email = fetch_email(url)
        print(f"{i}|{name}|{title}|{email}", flush=True)
        results.append((name, title, email))
        time.sleep(0.3)

    # 保存 CSV + XLSX（使用 exporter 模块）
    from agent.exporter import export_all
    data = [{"name": r[0], "title": r[1], "email": r[2]} for r in results]
    files = export_all(data, "南京大学计算机学院")
    found = sum(1 for _, _, e in results if e not in ("未找到", "页面为空", "超时") and not e.startswith("错误"))
    print(f"\n完成！成功 {found}/{len(results)}，文件: CSV={files.get('csv','?')}, XLSX={files.get('xlsx','?')}")
