"""汇总北京邮电大学计算机学院教师数据并导出 CSV"""

import csv
import re
from datetime import datetime
from pathlib import Path

# 所有已确认有邮箱的教师数据（按研究中心分组）
teachers = [
    # ═══ 物联网技术中心 ═══
    {"name": "马华东", "email": "mhd@bupt.edu.cn", "department": "物联网技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/mahuadong"},
    {"name": "罗红", "email": "luoh@bupt.edu.cn", "department": "物联网技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/luohong1"},
    {"name": "孙岩", "email": "sunyan@bupt.edu.cn", "department": "物联网技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/sunyan"},

    # ═══ 数据科学与服务中心 ═══
    {"name": "吴斌", "email": "wubin@bupt.edu.cn", "department": "数据科学与服务中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/wubin"},
    {"name": "王柏", "email": "wangbai@bupt.edu.cn", "department": "数据科学与服务中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/wangbai"},
    {"name": "石川", "email": "shichuan@bupt.edu.cn", "department": "数据科学与服务中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/shichuan"},
    {"name": "于艳华", "email": "yuyanhua@bupt.edu.cn", "department": "数据科学与服务中心", "title": "副教授/博导", "url": "https://teacher.bupt.edu.cn/yuyanhua"},
    {"name": "王啸", "email": "xiaowang@bupt.edu.cn", "department": "数据科学与服务中心", "title": "副教授", "url": "https://teacher.bupt.edu.cn/wangxiao"},
    {"name": "胡琳梅", "email": "hulinmei@bupt.edu.cn", "department": "数据科学与服务中心", "title": "副教授", "url": "https://teacher.bupt.edu.cn/hulinmei"},
    {"name": "杨成", "email": "", "department": "数据科学与服务中心", "title": "副教授", "url": "https://teacher.bupt.edu.cn/yangcheng"},
    {"name": "白婷", "email": "", "department": "数据科学与服务中心", "title": "讲师", "url": ""},
    {"name": "李劼", "email": "", "department": "数据科学与服务中心", "title": "讲师", "url": "https://teacher.bupt.edu.cn/lijie1"},

    # ═══ 计算机软件与理论中心 ═══
    {"name": "牛少彰", "email": "szniu@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/niushaozhang"},
    {"name": "左兴权", "email": "zuoxq@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/zuoxingquan"},
    {"name": "杨娟", "email": "", "department": "计算机软件与理论中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/yangjuan"},
    {"name": "方维", "email": "Fang_wei@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/fangwei"},
    {"name": "陈洪", "email": "chenhong76@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "副教授/硕导", "url": ""},
    {"name": "谷勇浩", "email": "", "department": "计算机软件与理论中心", "title": "讲师/硕导", "url": ""},
    {"name": "黄海", "email": "", "department": "计算机软件与理论中心", "title": "讲师/硕导", "url": ""},
    {"name": "王鹏飞", "email": "wangpengfei@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "副教授/博导", "url": "https://teacher.bupt.edu.cn/wangpengfei"},
    {"name": "杨亚", "email": "yangya@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/yangya"},
    {"name": "张继威", "email": "jwzhang666@bupt.edu.cn", "department": "计算机软件与理论中心", "title": "讲师/硕导", "url": ""},

    # ═══ 物联网与智能系统团队(软件工程01组/大数据与云服务中心) ═══
    {"name": "邝坚", "email": "jkuang@bupt.edu.cn", "department": "大数据与云服务中心", "title": "教授/硕导", "url": "https://teacher.bupt.edu.cn/jkuang"},
    {"name": "郭迎", "email": "guoying@bupt.edu.cn", "department": "大数据与云服务中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/guoying1"},
    {"name": "雷友珣", "email": "yxlei@bupt.edu.cn", "department": "大数据与云服务中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/yxlei"},
    {"name": "崔毅东", "email": "cyd@bupt.edu.cn", "department": "大数据与云服务中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/cyd"},
    {"name": "杨谈", "email": "tyang@bupt.edu.cn", "department": "大数据与云服务中心", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/tyang"},
    {"name": "侯鲁洋", "email": "luyang.hou@bupt.edu.cn", "department": "大数据与云服务中心", "title": "副研究员/博导", "url": ""},
    {"name": "熊健", "email": "", "department": "大数据与云服务中心", "title": "研究员(兼职硕导)", "url": ""},

    # ═══ 网络智能研究中心 ═══
    {"name": "廖建新", "email": "", "department": "网络智能研究中心", "title": "讲席教授/博导", "url": "https://teacher.bupt.edu.cn/liaojianxin"},
    {"name": "王敬宇", "email": "wangjingyu@bupt.edu.cn", "department": "网络智能研究中心", "title": "长聘教授/博导", "url": "https://teacher.bupt.edu.cn/wangjingyu"},
    {"name": "戚琦", "email": "", "department": "网络智能研究中心", "title": "教授/博导", "url": ""},
    {"name": "王晶", "email": "wangjing@bupt.edu.cn", "department": "网络智能研究中心", "title": "副教授/硕导", "url": ""},
    {"name": "王纯", "email": "", "department": "网络智能研究中心", "title": "副教授/硕导", "url": ""},
    {"name": "李炜", "email": "", "department": "网络智能研究中心", "title": "副教授/硕导", "url": ""},
    {"name": "朱晓民", "email": "", "department": "网络智能研究中心", "title": "副教授/硕导", "url": ""},
    {"name": "王玉龙", "email": "", "department": "网络智能研究中心", "title": "副教授/硕导", "url": ""},
    {"name": "庄子睿", "email": "", "department": "网络智能研究中心", "title": "副教授/博导", "url": ""},
    {"name": "付霄元", "email": "", "department": "网络智能研究中心", "title": "助理教授/博导", "url": ""},
    {"name": "沈奇威", "email": "", "department": "网络智能研究中心", "title": "讲师/硕导", "url": ""},
    {"name": "孙海峰", "email": "", "department": "网络智能研究中心", "title": "讲师/硕导", "url": ""},
    {"name": "何波", "email": "", "department": "网络智能研究中心", "title": "助理教授/硕导", "url": ""},
    {"name": "任鹏飞", "email": "", "department": "网络智能研究中心", "title": "助理教授/硕导", "url": ""},

    # ═══ 交换与智能控制研究中心 ═══
    {"name": "苏森", "email": "susen@bupt.edu.cn", "department": "交换与智能控制研究中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/susen"},
    {"name": "王尚广", "email": "sgwang@bupt.edu.cn", "department": "交换与智能控制研究中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/sgwang"},
    {"name": "李静林", "email": "jlli@bupt.edu.cn", "department": "交换与智能控制研究中心", "title": "副教授", "url": ""},

    # ═══ 网络体系结构研究中心 ═══
    {"name": "许长桥", "email": "cqxu@bupt.edu.cn", "department": "网络体系结构研究中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/cqxu"},
    {"name": "关建峰", "email": "jfguan@bupt.edu.cn", "department": "网络体系结构研究中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/gjf"},

    # ═══ 网络技术中心 ═══
    {"name": "周安福", "email": "", "department": "网络技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/zhouanfu"},

    # ═══ 信息网络中心 ═══
    {"name": "黄小红", "email": "huangxh@bupt.edu.cn", "department": "信息网络中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/huangxiaohong"},

    # ═══ 计算机体系结构中心 ═══
    {"name": "卞佳丽", "email": "jlbian@bupt.edu.cn", "department": "计算机体系结构中心", "title": "教授/硕导", "url": "https://teacher.bupt.edu.cn/bianjiali"},
    {"name": "戴志涛", "email": "", "department": "计算机体系结构中心", "title": "教授/硕导", "url": "https://teacher.bupt.edu.cn/daizhitao"},
    {"name": "欧中洪", "email": "zhonghong.ou@bupt.edu.cn", "department": "计算机体系结构中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/ouzhonghong"},
    {"name": "张冬梅", "email": "zhangdm@bupt.edu.cn", "department": "计算机体系结构中心", "title": "副教授", "url": "https://teacher.bupt.edu.cn/zhangdongmei"},

    # ═══ 软件系统与工程中心 / 其他 ═══
    {"name": "胡博", "email": "hubo@bupt.edu.cn", "department": "计算机学院", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/hubo"},
    {"name": "高志鹏", "email": "gaozhipeng@bupt.edu.cn", "department": "计算机学院", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/gaozhipeng"},
    {"name": "赵东", "email": "dzhao@bupt.edu.cn", "department": "计算机学院", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/zhaodong"},
    {"name": "张笑燕", "email": "xiaoyan@bupt.edu.cn", "department": "计算机学院", "title": "教授", "url": "https://teacher.bupt.edu.cn/zhangxiaoyan"},
    {"name": "陆天波", "email": "luth@bupt.edu.cn", "department": "计算机学院", "title": "教授", "url": "https://teacher.bupt.edu.cn/lutianbo"},
    {"name": "王祎", "email": "yiwang@bupt.edu.cn", "department": "计算机学院", "title": "教授", "url": "https://teacher.bupt.edu.cn/wangyi2"},
    {"name": "郭文明", "email": "guowenming@bupt.edu.cn", "department": "计算机学院", "title": "副教授", "url": ""},
    {"name": "傅湘玲", "email": "fuxiangling@bupt.edu.cn", "department": "计算机学院", "title": "副教授", "url": ""},
    {"name": "陈晋鹏", "email": "jpchen@bupt.edu.cn", "department": "计算机学院", "title": "副教授", "url": ""},
    {"name": "张树壮", "email": "zhangshuzhuang@bupt.edu.cn", "department": "计算机学院", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/zhangshuzhuang"},
    {"name": "蒋砚军", "email": "jiangyanjun0718@bupt.edu.cn", "department": "计算机学院", "title": "副教授/硕导", "url": "https://teacher.bupt.edu.cn/jiangyanjun"},
    {"name": "王雪莹", "email": "wangxueying@bupt.edu.cn", "department": "计算机学院", "title": "助理教授/硕导", "url": "https://teacher.bupt.edu.cn/wangxueying1"},
    {"name": "程渤", "email": "chengbo@bupt.edu.cn", "department": "计算机学院", "title": "教授", "url": "https://teacher.bupt.edu.cn/chengbo"},
    {"name": "程莉", "email": "chengli@bupt.edu.cn", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/chengli"},
    {"name": "尚雁雷", "email": "shangyl@bupt.edu.cn", "department": "计算机学院", "title": "高级工程师", "url": "https://teacher.bupt.edu.cn/shangyanlei"},
    {"name": "邵颖霞", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/shaoyingxia"},
    {"name": "修佳鹏", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/xiujiapeng"},
    {"name": "王智立", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/wangzhili"},
    {"name": "孙其博", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/SunQibo"},
    {"name": "梁美玉", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/liangmeiyu"},
    {"name": "马骁", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/maxiao1"},
    {"name": "张海滨", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/zhanghaibin"},
    {"name": "梁洪亮", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/lianghongliang"},
    {"name": "田野", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/tianye"},
    {"name": "徐鹏", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/xupeng"},
    {"name": "孟祥武", "email": "", "department": "计算机应用技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/mengxiangwu"},
    {"name": "杜军平", "email": "", "department": "计算机应用技术中心", "title": "教授/博导", "url": "https://teacher.bupt.edu.cn/dujunping"},
    {"name": "王莹", "email": "", "department": "计算机学院", "title": "教师", "url": "https://teacher.bupt.edu.cn/wangying3"},
]

# 去重（按 name 去重，保留后者）
seen_names = {}
for t in teachers:
    seen_names[t["name"]] = t
teachers = list(seen_names.values())

# 按学院排序
teachers.sort(key=lambda t: (t["department"], t["name"]))

# 统计
with_email = sum(1 for t in teachers if t["email"])
without_email = sum(1 for t in teachers if not t["email"])
print(f"总计: {len(teachers)} 位教师")
print(f"有邮箱: {with_email}")
print(f"缺邮箱: {without_email}")

# 保存 CSV
output_dir = Path(__file__).parent / "outputs"
output_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = output_dir / f"北京邮电大学_计算机学院_教师邮箱_{ts}.csv"

fieldnames = ["姓名", "邮箱", "学院", "职称", "主页链接"]
col_map = {"姓名": "name", "邮箱": "email", "学院": "department", "职称": "title", "主页链接": "url"}

with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(fieldnames)
    for t in teachers:
        writer.writerow([t[col_map[fn]] for fn in fieldnames])

print(f"\nCSV 已保存: {csv_path}")
print(f"\n=== 有邮箱的教师 ===")
for t in teachers:
    if t["email"]:
        print(f"  {t['name']} <{t['email']}> [{t['department']}] {t['title']}")

print(f"\n=== 缺邮箱的教师 ===")
for t in teachers:
    if not t["email"]:
        print(f"  {t['name']} [{t['department']}] {t['title']}")
