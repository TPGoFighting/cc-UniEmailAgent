import { api } from "./api";
import type { IntentResult } from "@/lib/types";

/** 后端统一意图分类，网络失败时本地回退 */
export async function classifyIntent(message: string): Promise<IntentResult> {
  try {
    const res = await api.classifyTask(message);
    return {
      is_crawl: res.is_crawl ?? false,
      intent: (res.intent as IntentResult["intent"]) || "simple_query",
      university: res.university || "",
      departments: res.departments || [],
      reason: res.reason || "",
    };
  } catch {
    // 网络异常时本地回退
    return localClassify(message);
  }
}

/** @deprecated 使用 classifyIntent 代替 */
export async function isCrawlTask(message: string): Promise<boolean> {
  const result = await classifyIntent(message);
  return result.is_crawl;
}

function localClassify(message: string): IntentResult {
  const lower = message.toLowerCase();

  // 爬取关键词
  const crawlWords = ["爬取", "抓取", "提取", "采集", "帮我找", "搜索", "查一下"];
  const queryWords = ["多少", "几个", "分别", "统计", "结果", "情况", "分析", "查看"];
  const incrementalWords = ["补充", "补全", "追加", "不够", "缺少", "漏", "不全", "重新爬"];

  const hasCrawl = crawlWords.some(kw => lower.includes(kw));
  const hasQuery = queryWords.some(kw => lower.includes(kw));
  const hasIncremental = incrementalWords.some(kw => lower.includes(kw));

  if (hasCrawl && hasQuery) {
    return { is_crawl: false, intent: "simple_query", university: "", departments: [], reason: "本地回退: 含查询+爬取关键词" };
  }
  if (hasIncremental) {
    return { is_crawl: true, intent: "incremental", university: "", departments: [], reason: "本地回退: 含增量关键词" };
  }
  if (hasCrawl) {
    return { is_crawl: true, intent: "new_crawl", university: "", departments: [], reason: "本地回退: 含爬取关键词" };
  }
  return { is_crawl: false, intent: "simple_query", university: "", departments: [], reason: "本地回退: 无明确爬取意图" };
}
