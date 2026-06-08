# 南京大学爬取升级方案 V3.0

## 当前状态

- V2.0.1: 1139 记录, 697 邮箱 (61.2%), 35 学院
- 期望目标: 2000+ 教师, 1800+ 邮箱 (90%+)
- 缺口: ~860+ 教师, ~1100+ 邮箱

---

## 问题一：数据完整性（848→1800+）

### 根因分析

#### 1. iframe 内嵌邮箱（最严重）

当前 `_crawl_single_profile` 只用 `document.body.innerText`，完全跳过了 iframe。

**受影响学院（预估）：**
- 文学院 — chin.nju.edu.cn 可能用 iframe 嵌入 nju.edu.cn 邮箱
- 化学学院 — 70人2邮箱，很多邮箱可能在 iframe 中
- 外国语学院 — 108人13邮箱，页面可能是 iframe 嵌套
- 地球科学与工程学院 — 70人3邮箱
- 生命科学学院 — 43人2邮箱

**修复方案：**
```python
# 在 _crawl_single_profile / _scrape_teacher_list 中添加 iframe 检测
async def _extract_from_iframes(self, page) -> list[str]:
    """穿透所有 iframe 提取邮箱"""
    iframe_emails = await page.evaluate("""() => {
        const results = new Set();
        const p = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
        document.querySelectorAll('iframe').forEach(iframe => {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                if (doc) {
                    const text = doc.body.innerText;
                    for (const match of text.matchAll(p)) results.add(match[0]);
                }
            } catch(e) { /* cross-origin iframe */ }
        });
        return Array.from(results);
    }""")
    return iframe_emails
```

**工作量：** 小（~2h），集成到 `_extract_emails_multi` 中
**预期效果：** +100~200 邮箱

---

#### 2. 邮箱编码/JS 变量中（中度严重）

有些学院将邮箱编码成 HTML entity 或存在 JS 变量中，`body.innerText` 提取不到。

**常见编码方式：**
- Base64 编码：`btoa('xxx@nju.edu.cn')` → 需 decode
- HTML entity：`&#120;&#120;&#120;&#64;nju&#46;edu&#46;cn`
- CSS `display:none` 中的邮箱字符拼接
- JS 变量：`var email = 'xxx' + '@' + 'nju.edu.cn'`
- URI 编码：`%78%78%78%40nju.edu.cn`

**修复方案：**
```python
async def _extract_emails_from_js(self, page) -> list[str]:
    """从 JS 变量和 DOM 属性中提取编码邮箱"""
    return await page.evaluate("""() => {
        const results = new Set();
        const p = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

        // 1. 从内联 script 中提取（包含拼接模式 xxx+@+domain）
        document.querySelectorAll('script:not([src])').forEach(s => {
            const text = s.textContent || '';
            // 替换拼接模式
            const cleaned = text.replace(/['"]\s*\+\s*['"]/g, '')
                                .replace(/['"]/g, '');
            for (const match of cleaned.matchAll(p)) results.add(match[0]);
        });

        // 2. 从 data-* 属性提取
        document.querySelectorAll('[data-email], [data-mail]').forEach(el => {
            const val = el.dataset.email || el.dataset.mail || '';
            for (const match of val.matchAll(p)) results.add(match[0]);
        });

        // 3. Base64 解码尝试
        document.querySelectorAll('[data-email-b64]').forEach(el => {
            try {
                const decoded = atob(el.dataset.emailB64);
                for (const match of decoded.matchAll(p)) results.add(match[0]);
            } catch(e) {}
        });

        return Array.from(results);
    }""")
```

**工作量：** 中（~4h），需覆盖各种编码变体
**预期效果：** +50~100 邮箱

---

#### 3. 分页未处理

许多学院列表页有分页（list.htm?page=2），当前只抓第1页。

**受影响学院：**
- 物理学院 199人 — 可能是多页列表汇总
- 天文学院 135人 — 同上
- 计算机学院 — 6个子页但只引用了部分
- 任何超过30人的学院都可能有多页

**修复方案：**
```python
async def _find_pagination(self, page, base_url: str) -> list[str]:
    """检测并收集所有分页 URL"""
    urls = await page.evaluate("""() => {
        const results = new Set();
        document.querySelectorAll('.pagination a, .page a, .pager a, ' +
                                  '[class*="page"] a, [class*="Page"] a').forEach(a => {
            const href = a.href;
            if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                results.add(href);
            }
        });
        return Array.from(results);
    }""")
    return urls
```

**工作量：** 中（~4h），需集成到 _scrape_teacher_list 流程中
**预期效果：** +200~400 教师

---

#### 4. 列表页链接提取策略太死板

当前 _scrape_teacher_list 的 JS evaluate 中：
- 策略1：只找 `<table>` 中的 `<a>` 
- 策略2：只找 `<ul>` / `div.list` / `div.teacher-list` / `div.faculty-list` 
- 策略3：遍历所有 `<a>` 标签，但要求 `href` 包含 `list.htm` 或 `page.htm`

**问题：** 许多学院的结构不匹配这些假设，导致漏掉大量教师。

**受影响学院：**
- 外国语学院 — 页面结构可能完全不是 table/ul
- 政府管理学院 — 数据在一页上但分块（需按 section 解析）
- 机器人与自动化学院 — 可能用 div.card / div.teacher-card
- 现代生物研究院 — 可能用完全自定义布局

**修复方案：**
为每个低邮箱率学院写**自定义提取器**，注册到映射表中。

```python
# 策略注册表
DEPT_SCRAPER_REGISTRY = {
    "外国语学院": ForeignLanguageScraper,
    "政府管理学院": GovSchoolScraper,
    "化学学院": ChemistryScraper,
    # ... 默认回退通用爬虫
}
```

**工作量：** 大（每个学院 2-4h，10个学院 = 20-40h）
**预期效果：** +300~500 邮箱

---

#### 5. 学院子域名缺失 / 入口 URL 不对

当前 hardcoded 的学院 URL 列表可能不是真正的师资页面入口。有些学院换了网站结构。

**需验证的学院：**
- 商学院 (nubs.nju.edu.cn) — 完全没出现在 V2.0.1 统计中，但补充爬取有
- 外国语学院 (sfs.nju.edu.cn) — 当前只有1个邮箱
- 现代生物研究院 (imb.nju.edu.cn) — 首页可能不是师资页面
- 生物医学工程学院 (bme.nju.edu.cn) — 0邮箱
- 国际关系学院 (sis.nju.edu.cn) — 0邮箱

**修复方案：**
手动验证每个学院的师资页面 URL，更新 DEPT_CONFIG。

**工作量：** 小（~2h，逐页验证）
**预期效果：** +50~100 邮箱

---

#### 6. 详情页 timeout 太多

当前 `_crawl_single_profile` 的 PROFILE_TIMEOUT = 15000ms。慢页面频繁超时，导致大量教师的详情页没被爬取。

**受影响学院的详情页结构：**
- 有些详情页含大图（如物理学院教师照片）
- 有些详情页是 AJAX 懒加载（需滚动触发）

**修复方案：**
```python
async def _crawl_single_profile(self, ctx, entry, dept_name):
    async with self._profile_sem:
        profile_page = await ctx.new_page()
        try:
            await profile_page.goto(profile_url, wait_until="load", timeout=30000)  # 延长+等load
            # 滚动到底部触发懒加载
            await profile_page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)
            # ... 提取
```

**工作量：** 小（~1h）
**预期效果：** +30~50 邮箱（原有超时的页面能加载到）

---

## 问题二：数据纯净度（过滤导航垃圾）

### 当前污染严重

从 V2.0.1 CSV 尾部可以看到大量导航条目混入记录：

```
学术交流,,能源与资源学院,教授,https://sser.nju.edu.cn/xsjl.htm
诚聘英才,,能源与资源学院,教授,https://sser.nju.edu.cn/cpyc.htm
党团建设,,能源与资源学院,,https://sser.nju.edu.cn/dtjs.htm
下页,guangxinlv@nju.edu.cn,能源与资源学院,教授,...
尾页,xiaobochen@nju.edu.cn,能源与资源学院,教授,...
科研系统,,机器人与自动化学院,,http://ky.nju.edu.cn/
学院概况,,机器人与自动化学院,,https://ra.nju.edu.cn/xygk/index.html
师资队伍,,机器人与自动化学院,,https://ra.nju.edu.cn/szll/index.html
```

### 根本原因

1. `_scrape_teacher_list` 中的 isNavLink 函数过滤不够严格 — 匹配到"教授"就放行
2. URL 过滤太松 — 只要看起来像详情页就放行
3. 没有区分"纯导航URL"（/index.htm）和"详情页URL"（/page.htm?id=xxx）

### 修复方案

#### 方案 A：URL 模式白名单（推荐，最有效）

```python
def is_teacher_detail_url(url: str) -> bool:
    """确定 URL 是教师详情页而非导航页"""
    lower = url.lower()
    
    # 导航页特征（列表页、索引页）
    NAV_URL_PATTERNS = [
        r'/list\.htm$', r'/index\.html?$', r'/main\.htm',
        r'/main\.psp', r'javascript:', r'#\d*$', r'mailto:',
    ]
    for pat in NAV_URL_PATTERNS:
        if re.search(pat, lower):
            return False
    
    # 详情页特征
    DETAIL_URL_PATTERNS = [
        r'/page\.htm',           # 常见详情页
        r'/\d+/\d+/c\d+',       # NJU 特有格式: /58/2a/c2639a153642/page.htm
        r'/list\.htm\?',         # 带参数的详情页
        r'/\d{5,}/list\.htm',   # 部分学院用数字ID作为详情页
    ]
    for pat in DETAIL_URL_PATTERNS:
        if re.search(pat, lower):
            return True
    
    # 子路径详情页（含多位数字ID的路径，如 /zsl/list.htm 可能是教师URL）
    if re.search(r'/[a-z]{2,6}/list\.htm$', lower) and len(lower) < 80:
        return True
    
    return False
```

**工作量：** 中（~3h），需测试各学院的URL模式
**预期效果：** 过滤掉 80%+ 的导航垃圾

#### 方案 B：增强 cleaner.py 的黑名单

当前 cleaner.py 的 NAME_BLACKLIST 只有 21 条，需扩展到 200+ 条：

```python
NAME_BLACKLIST = {
    # 导航/结构关键词
    "学院概况", "学院简介", "学院领导", "组织机构", "历史沿革",
    "师资队伍", "师资概况", "教师名录", "教职员工", "全体教师",
    "专职教师", "兼职教师", "客座教授", "讲座教授", "博导名单",
    "硕士导师", "研究生导师", "导师风采", "杰出人才", "人才队伍",
    # 网页UI文字
    "下页", "上一页", "下一页", "尾页", "首页", "返回", "更多",
    "第1页", "第2页", "共1页", "共2页",
    # 学院子页（导航条目）
    "人才培养", "科学研究", "学术交流", "国际合作", "学生工作",
    "党团建设", "党建工作", "工会工作", "校友工作", "校友天地",
    "通知公告", "新闻动态", "学术活动", "学术报告", "科研动态",
    "规章制度", "办事指南", "下载中心", "联系我们", "网站地图",
    "诚聘英才", "人才招聘", "招聘信息",
    # 职称占位符
    "教授", "副教授", "讲师", "研究员", "副研究员",
    "两院院士", "长江学者", "杰出青年",
    # URL相关
    "南大主页", "学校主页", "校园地图", "教师登录",
}
```

**工作量：** 小（~1h）
**预期效果：** 补齐 ~20% 的过滤能力

#### 方案 C：准入规则收紧（最大改动）

修改 `_scrape_teacher_list` 的核心逻辑，采用**准入制**而非**黑名单制**：

> 当前：~~不像是导航的，就当作教师~~  
> 改为：**只有同时满足多个教师特征，才认为是教师**

```python
def is_likely_teacher(entry: dict) -> bool:
    """多维度判断是否为教师条目"""
    name = entry.get("name", "")
    url = entry.get("url", "")
    title = entry.get("title", "")
    
    # 必须项：2-4个汉字姓名
    if not re.match(r'^[\u4e00-\u9fff]{2,4}$', name):
        return False
    
    # 加分项（达到2分才通过）
    score = 0
    
    # 1. URL是详情页（不是列表页）
    if is_teacher_detail_url(url):
        score += 2
    elif re.search(r'/[a-z]{2,5}/list\.htm$', url.lower()):
        score += 1  # 可能是教师的子页面
    else:
        score -= 1  # 不认识的URL模式
    
    # 2. 标题含教师职称
    if any(t in title for t in ["教授", "研究员", "讲师", "博导"]):
        score += 1
    
    # 3. URL不含导航关键词
    nav_url_kw = ["about", "intro", "news", "contact", "map", "login",
                  "概况", "简介", "新闻", "通知", "公告", "联系"]
    if not any(kw in url.lower() for kw in nav_url_kw):
        score += 1
    
    return score >= 2
```

**工作量：** 中（~4h），对 35 个学院的 URL 模式做 validation
**预期效果：** 过滤掉 95%+ 的导航垃圾

---

## 推荐实施优先级

| 优先级 | 任务 | 工作量 | 预期邮箱增量 | 累计 |
|--------|------|--------|-------------|------|
| P0 | 分页处理 | 4h | 200-400 | 900-1100 |
| P0 | iframe 穿透提取 | 2h | 100-200 | 1000-1300 |
| P0 | 验证学院URL入口 | 2h | 50-100 | 1050-1400 |
| P1 | 自定义低邮箱学院爬虫 | 20-40h | 300-500 | 1350-1800 |
| P1 | 准入制过滤导航 | 4h | (数据纯净) | — |
| P2 | JS变量提取 + Base64 | 4h | 50-100 | 1400-1900 |
| P2 | 超时放宽 | 1h | 30-50 | 1430-1950 |

## 各学院专项分析

### 1. 外国语学院（108人13邮箱 = 12%）
- URL: https://sfs.nju.edu.cn/szdw/index.html
- 可能问题：页面结构不是标准 table，是用 js 渲染的卡片
- 建议：检查页面 HTML，可能每个教师是独立 div.card 结构
- 修复：写专用提取器

### 2. 化学学院（70人2邮箱 = 3%）
- URL: https://chem.nju.edu.cn/szll/list.htm
- 可能问题：详情页可能用 iframe 或 JS 动态加载邮箱
- 建议：检查详情页 HTML 结构
- 修复：iframe 穿透 + JS 变量提取

### 3. 政府管理学院（37人4邮箱 = 11%）
- URL: https://public.nju.edu.cn/szdw/qzjs/index.html
- 可能问题：数据都在一页上，按系分块，需按块解析
- 补充爬虫已有修复，需整合

### 4. 地球科学与工程学院（70人3邮箱 = 4%）
- URL: https://es.nju.edu.cn/25235/list.htm
- 可能问题：有多页子页面（35665/list.htm=教授, 35666/list.htm=副教授）
- 建议：正确配置所有子页 URL

### 5. 生命科学学院（43人2邮箱 = 5%）
- URL: https://life.nju.edu.cn/szdw/list.htm
- 建议：检查详情页结构

### 6. 生物医学工程学院（50人0邮箱）
- URL: https://bme.nju.edu.cn/szll/zzjs/index.html
- 建议：可能是完全不同的页面结构

---

## 数据纯净度快速修复

### 立即执行（5分钟内见效）

修改 `cleaner.py` 中的 `is_valid_person_name`，增加更严格的过滤：

```python
# 在任何学院中都不可能是教师名字的词汇
FULL_BLACKLIST = NAME_BLACKLIST | {
    "下页", "上一页", "尾页", "首页", "返回", "更多",
    "教授", "副教授", "讲师", "研究员", "副研究员",
    "学院概况", "学院简介", "师资队伍", "联系我们",
    "诚聘英才", "通知公告", "新闻动态", "学术交流",
    "党团建设", "党建工作", "学生工作", "人才培养",
    "科研系统", "学院领导", "组织机构", "历史沿革",
}
```

并在 `clean_records` 中添加 URL 模式过滤：

```python
def _is_list_page_url(url: str) -> bool:
    """检测URL是否为列表/导航页而非详情页"""
    lower = url.lower()
    list_patterns = ['/list.htm', '/index.htm', '/index.html', 
                     '/main.htm', '/main.psp', '#']
    for pat in list_patterns:
        if pat in lower:
            return True
    return False

# 在使用中：
if _is_list_page_url(r.get('url', '')) and not r.get('email'):
    stats['bad_url'] += 1
    continue  # 跳过
```

---

## 总结

**目标：** 697 → 1800+ 邮箱

**速效方案（P0，6-8h 内）：**
1. 分页处理 → 预期 +200-400
2. iframe 穿透 → 预期 +100-200
3. 验证学院 URL → 预期 +50-100
4. 快速过滤（full blacklist + URL 白名单）→ 数据纯净
→ 合计预期: 1050-1400 邮箱

**深度方案（P1，20-40h）：**
5. 低邮箱率学院自定义爬虫
→ 预期: 1400-1800 邮箱

**锦上添花（P2，5h）：**
6. JS变量/Base64提取 + 超时放宽
→ 预期: 1450-1950 邮箱
