"""诊断脚本：查看南理工计算机学院页面结构"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "outputs" / "njust_cs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # 访问首页
        url = "https://cs.njust.edu.cn"
        print(f"访问: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # 截图
        await page.screenshot(path=str(OUTPUT_DIR / "homepage.png"), full_page=False)
        print(f"截图保存: {OUTPUT_DIR / 'homepage.png'}")

        # 获取页面标题
        title = await page.title()
        print(f"页面标题: {title}")

        # 获取所有链接
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                text: (a.textContent || '').trim().slice(0, 50),
                href: a.href || '',
                visible: a.offsetParent !== null
            }));
        }""")

        print(f"\n页面中共 {len(links)} 个链接:")
        for l in links:
            if l['visible']:
                print(f"  [可见] {l['text'][:40]:40s} → {l['href'][:100]}")

        # 检查 iframe
        iframes = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map(f => ({
                src: f.src,
                id: f.id,
                name: f.name
            }));
        }""")
        print(f"\niframe 数量: {len(iframes)}")
        for f in iframes:
            print(f"  iframe: id={f['id']}, name={f['name']}, src={f['src']}")

        # 获取页面 body 文本（前3000字）
        body_text = await page.evaluate("() => document.body.innerText.slice(0, 3000)")
        print(f"\n页面 body 文本(前3000字):\n{body_text}")

        # 尝试进入 iframe 查看
        if iframes:
            for i, f_info in enumerate(iframes):
                if f_info['src']:
                    try:
                        frame = page.frame(name=f_info.get('name')) or page.frame(url=f_info['src'])
                        if frame:
                            frame_links = await frame.evaluate("""() => {
                                return Array.from(document.querySelectorAll('a')).map(a => ({
                                    text: (a.textContent || '').trim().slice(0, 50),
                                    href: a.href || ''
                                }));
                            }""")
                            print(f"\niframe[{i}] 内链接 ({len(frame_links)}个):")
                            for fl in frame_links[:30]:
                                print(f"  {fl['text'][:40]:40s} → {fl['href'][:120]}")
                    except Exception as e:
                        print(f"  iframe[{i}] 读取失败: {e}")

        # 也尝试几个常见的子页面
        test_urls = [
            "https://cs.njust.edu.cn/szdw.htm",
            "https://cs.njust.edu.cn/szdw1/js.htm",
            "https://cs.njust.edu.cn/11559/list.htm",
            "https://cs.njust.edu.cn/szdw/js.htm",
            "https://cs.njust.edu.cn/szdw1.htm",
        ]

        for test_url in test_urls:
            try:
                resp = await page.goto(test_url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(2)
                status = resp.status if resp else "N/A"
                print(f"\n--- 尝试: {test_url} (status={status}) ---")

                sub_links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a => ({
                        text: (a.textContent || '').trim().slice(0, 50),
                        href: a.href || ''
                    })).filter(l => l.text.length >= 2 && l.text.length <= 15 && !l.href.includes('javascript:'));
                }""")

                print(f"  短文本链接 ({len(sub_links)}个):")
                for sl in sub_links[:20]:
                    print(f"    {sl['text'][:30]:30s} → {sl['href'][:100]}")

            except Exception as e:
                print(f"  ❌ 加载失败: {e}")

        await context.close()
        await browser.close()


asyncio.run(diagnose())
