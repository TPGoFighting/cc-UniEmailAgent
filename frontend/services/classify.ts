import { api } from "./api";

/** 后端统一分类，网络失败时本地回退 */
export async function isCrawlTask(message: string): Promise<boolean> {
  try {
    const res = await api.classifyTask(message);
    return res.is_crawl;
  } catch {
    // 网络异常时本地回退
    return localIsCrawlTask(message);
  }
}

function localIsCrawlTask(message: string): boolean {
  const lower = message.toLowerCase();

  // 先检查反模式：过去时/问询已爬取结果的询问，即使含关键词也不分类为爬取
  const has_crawl_word = ["爬取", "抓取", "提取", "采集"].some(kw => lower.includes(kw));
  const has_query_word = ["到了", "多少", "几个", "分别", "统计", "结果", "情况"].some(kw => lower.includes(kw));
  if (has_crawl_word && has_query_word) {
    return false;
  }

  const keywords = [
    "抓取", "爬取", "爬虫", "邮箱", "教师",
    "crawl", "scrape", "email", "faculty", "teacher", "学院",
  ];
  const hits = keywords.filter(kw => lower.includes(kw)).length;
  const combos = ["教师邮箱", "crawl email", "scrape email"];
  if (combos.some(c => lower.includes(c))) {
    return true;
  }
  return hits >= 2;
}
