"""合并所有数据源：已有数据 + 网络搜索新数据 + v2清洗数据 → 最终CSV/XLSX"""
import csv
from collections import Counter
from datetime import datetime

# 1. 加载已有数据
with open('outputs/南京大学_教师邮箱_合并版_20260526_163254.csv', 'r', encoding='utf-8') as f:
    existing_rows = list(csv.DictReader(f))
print(f'已有数据: {len(existing_rows)} 条')

existing_keys = set()
for r in existing_rows:
    key = (r['姓名'].strip(), r['学院'].strip())
    existing_keys.add(key)

# 2. 网络搜索 + v2清洗 发现的新数据
new_teachers = [
    # ===== 商学院 (5人) =====
    {'姓名':'蔡杨','邮箱':'caiyang6@nju.edu.cn','学院':'商学院','职称':'特任副研究员','主页链接':'https://nubs.nju.edu.cn/'},
    {'姓名':'夏江','邮箱':'xiajiang@nju.edu.cn','学院':'商学院','职称':'副教授','主页链接':'https://nubs.nju.edu.cn/'},
    {'姓名':'周耿','邮箱':'zhougeng@nju.edu.cn','学院':'商学院','职称':'副教授','主页链接':'https://nubs.nju.edu.cn/'},
    {'姓名':'徐宁','邮箱':'xuning@nju.edu.cn','学院':'商学院','职称':'讲师','主页链接':'https://nubs.nju.edu.cn/'},
    {'姓名':'李小琳','邮箱':'lixl@nju.edu.cn','学院':'商学院','职称':'教授','主页链接':'https://nubs.nju.edu.cn/'},

    # ===== 电子科学与工程学院 (8人) =====
    {'姓名':'徐骏','邮箱':'junxu@nju.edu.cn','学院':'电子科学与工程学院','职称':'教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'王军转','邮箱':'wangjz@nju.edu.cn','学院':'电子科学与工程学院','职称':'教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'王学锋','邮箱':'xfwang@nju.edu.cn','学院':'电子科学与工程学院','职称':'教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'涂学凑','邮箱':'tuxuecou@nju.edu.cn','学院':'电子科学与工程学院','职称':'教授级高工','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'邱浩','邮箱':'haoqiu@nju.edu.cn','学院':'电子科学与工程学院','职称':'副教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'王欣然','邮箱':'xrwang@nju.edu.cn','学院':'电子科学与工程学院','职称':'教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'王宇宣','邮箱':'wangyuxuan@nju.edu.cn','学院':'电子科学与工程学院','职称':'副教授','主页链接':'https://ese.nju.edu.cn/'},
    {'姓名':'彭成磊','邮箱':'pcl@nju.edu.cn','学院':'电子科学与工程学院','职称':'副教授','主页链接':'https://ese.nju.edu.cn/'},

    # ===== 工程管理学院 (2人) =====
    {'姓名':'宁延','邮箱':'ny@nju.edu.cn','学院':'工程管理学院','职称':'教授','主页链接':'https://sme.nju.edu.cn/'},
    {'姓名':'占杨','邮箱':'zhanyang@nju.edu.cn','学院':'工程管理学院','职称':'助理研究员','主页链接':'https://sme.nju.edu.cn/'},

    # ===== 匡亚明学院 (4人) =====
    {'姓名':'董昊','邮箱':'donghao@nju.edu.cn','学院':'匡亚明学院','职称':'教授','主页链接':'https://dii.nju.edu.cn/'},
    {'姓名':'王骏','邮箱':'wangj@nju.edu.cn','学院':'匡亚明学院','职称':'教授','主页链接':'https://dii.nju.edu.cn/'},
    {'姓名':'胡茜茜','邮箱':'xxhu@nju.edu.cn','学院':'匡亚明学院','职称':'副教授','主页链接':'https://dii.nju.edu.cn/'},
    {'姓名':'陈爽','邮箱':'chenshuang@nju.edu.cn','学院':'匡亚明学院','职称':'副教授','主页链接':'https://dii.nju.edu.cn/'},

    # ===== 艺术学院 (9人) =====
    {'姓名':'何成洲','邮箱':'chengzhou@nju.edu.cn','学院':'艺术学院','职称':'教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'黄厚明','邮箱':'huanghouming@nju.edu.cn','学院':'艺术学院','职称':'教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'童强','邮箱':'tongqiang@nju.edu.cn','学院':'艺术学院','职称':'教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'李牧','邮箱':'muli@nju.edu.cn','学院':'艺术学院','职称':'教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'李健','邮箱':'lijian@nju.edu.cn','学院':'艺术学院','职称':'教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'刘毅','邮箱':'liuyi@nju.edu.cn','学院':'艺术学院','职称':'副教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'季峰','邮箱':'jifeng@nju.edu.cn','学院':'艺术学院','职称':'副教授','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'袁梦倩','邮箱':'yuanmengqian@nju.edu.cn','学院':'艺术学院','职称':'特聘研究员','主页链接':'https://art.nju.edu.cn/'},
    {'姓名':'黎万峡','邮箱':'liwanxia@nju.edu.cn','学院':'艺术学院','职称':'特任副研究员','主页链接':'https://art.nju.edu.cn/'},

    # ===== 能源与资源学院 (15人) =====
    {'姓名':'朱嘉','邮箱':'jiazhu@nju.edu.cn','学院':'能源与资源学院','职称':'教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'卞斌','邮箱':'bin.bian@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'蔡亮','邮箱':'liangcai@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'贾腾','邮箱':'teng.jia@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'金彪','邮箱':'biao.jin@nju.edu.cn','学院':'能源与资源学院','职称':'教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'金艳','邮箱':'yanjin@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'吕光鑫','邮箱':'guangxinlv@nju.edu.cn','学院':'能源与资源学院','职称':'助理教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'马朝阳','邮箱':'zhaoyang.ma@nju.edu.cn','学院':'能源与资源学院','职称':'助理教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'宋琰','邮箱':'yansong@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'王景阳','邮箱':'jy_wang@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'王晓君','邮箱':'xiaojunwang@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'颜亦超','邮箱':'ychyan@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'杨成升','邮箱':'csyang@nju.edu.cn','学院':'能源与资源学院','职称':'助理教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'朱鹏臣','邮箱':'pczhu@nju.edu.cn','学院':'能源与资源学院','职称':'助理教授','主页链接':'https://sser.nju.edu.cn/'},
    {'姓名':'朱棣','邮箱':'zhudi@nju.edu.cn','学院':'能源与资源学院','职称':'副教授','主页链接':'https://sser.nju.edu.cn/'},

    # ===== 文学院 - v2清洗新增 (3人) =====
    {'姓名':'李章斌','邮箱':'lizhangbin728@163.com','学院':'文学院','职称':'教授','主页链接':'https://chin.nju.edu.cn/'},
    {'姓名':'孙书磊','邮箱':'sunshulei@nju.edu.cn','学院':'文学院','职称':'教授','主页链接':'https://chin.nju.edu.cn/'},
    {'姓名':'王芊','邮箱':'qian_clytie@163.com','学院':'文学院','职称':'','主页链接':'https://chin.nju.edu.cn/'},
]

# 3. 去重合并
added = 0
skipped = 0
for t in new_teachers:
    name = t['姓名'].strip()
    dept = t['学院'].strip()
    key = (name, dept)
    if key not in existing_keys:
        existing_rows.append(t)
        existing_keys.add(key)
        added += 1
    else:
        skipped += 1

print(f'新增: {added} 条, 跳过重复: {skipped} 条')
print(f'合并后总数: {len(existing_rows)} 条')

# 4. 统计
print('\n========== 各学院统计 ==========')
dept_count = Counter(r['学院'] for r in existing_rows)
for dept, cnt in dept_count.most_common():
    has_email = sum(1 for r in existing_rows
                    if r['学院'] == dept
                    and r.get('邮箱', '').strip()
                    and '无邮箱' not in r.get('邮箱', ''))
    print(f'  {dept}: {cnt}人, 有邮箱{has_email}人')

total = len(existing_rows)
has_email = sum(1 for r in existing_rows
                if r.get('邮箱', '').strip()
                and '无邮箱' not in r.get('邮箱', ''))
print(f'\n总计: {total} 人, 有邮箱 {has_email} 人')

# 5. 保存文件
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
csv_path = f'outputs/南京大学_教师邮箱_最终合并_{timestamp}.csv'

with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    # 标准化所有行只保留5个字段
    clean_rows = []
    for r in existing_rows:
        clean = {
            '姓名': r.get('姓名', '').strip(),
            '邮箱': r.get('邮箱', '').strip(),
            '学院': r.get('学院', '').strip(),
            '职称': r.get('职称', '').strip(),
            '主页链接': r.get('主页链接', '').strip(),
        }
        clean_rows.append(clean)

    writer = csv.DictWriter(f, fieldnames=['姓名', '邮箱', '学院', '职称', '主页链接'])
    writer.writeheader()
    writer.writerows(clean_rows)

print(f'\nCSV: {csv_path}')

# XLSX
try:
    import pandas as pd
    df = pd.DataFrame(clean_rows)
    xlsx_path = csv_path.replace('.csv', '.xlsx')
    df.to_excel(xlsx_path, index=False)
    print(f'XLSX: {xlsx_path}')
except ImportError:
    print('(未安装pandas，跳过XLSX)')
