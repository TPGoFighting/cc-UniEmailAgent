import type { Message } from "@/lib/types";

// 欢迎消息（新建任务时显示）
export const welcomeMessage: Message = {
  id: "welcome",
  role: "agent",
  content: `你好，我是 **UniEmail Agent**。

我可以帮你自动抓取高校教师的邮箱信息。只需告诉我目标院校和学院，我会自动浏览官网、识别教师列表、提取邮箱地址，并导出为 CSV / XLSX 文件。

请输入你的任务，比如：**"帮我抓取南京大学计算机学院教师邮箱"**`,
};
