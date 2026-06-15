import os
import json
import requests
from deep_translator import GoogleTranslator

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ======================
# 综合评分引擎 (Score Engine)
# ======================
def calc_score(policy, total_hot, streak):
    # 主线评分：政策驱动 + 历史底蕴
    main_score = round(policy * 5 + total_hot * 0.2, 1)
    # 资金评分：连续升温加速
    money_score = round(streak * 8, 1)
    # 综合评分
    total_score = round(main_score + money_score, 1)
    
    return total_score, main_score, money_score

# ======================
# 关键词库
# ======================

with open("keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS = json.load(f)

# ======================
# 观察池
# ======================

with open("watchlist.json", "r", encoding="utf-8") as f:
    WATCHLIST = json.load(f)

with open("stock_pool.json", "r", encoding="utf-8") as f:
    STOCK_POOL = json.load(f)

# ======================
# 连续升温库
# ======================

try:
    with open("hot_streak.json", "r", encoding="utf-8") as f:
        hot_streak = json.load(f)
except:
    hot_streak = {}

# ======================
# 历史记录
# ======================

try:
    with open("history.json", "r", encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history, list):
        history = []
except:
    history = []

history_set = set(history)

# ======================
# 读取标题
# ======================

all_titles = []

for file in [
    "data/miit_titles.json",
    "data/ndrc_titles.json",
    "data/gov_titles.json",
    "data/global_titles.json"
]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            all_titles.extend(json.load(f))
    except:
        pass

all_titles = list(dict.fromkeys(all_titles))
print(f"总标题：{len(all_titles)}")

# ======================
# 新增标题
# ======================

new_titles = []

for title in all_titles:
    if title not in history_set:
        new_titles.append(title)

print(f"新增标题：{len(new_titles)}")

if len(new_titles) == 0:
    print("没有新增政策")
    new_titles = []

# ======================
# 自动翻译
# ======================

translated_titles = {}

for title in new_titles:
    try:
        if any('\u4e00' <= c <= '\u9fff' for c in title):
            translated_titles[title] = title
        else:
            translated_titles[title] = GoogleTranslator(
                source="auto",
                target="zh-CN"
            ).translate(title)
    except:
        translated_titles[title] = title

# ======================
# 热点统计
# ======================

result = {}

for topic, aliases in KEYWORDS.items():
    matched = []
    for title in all_titles:
        for alias in aliases:
            if alias.lower() in title.lower():
                matched.append(title)
                break
    if matched:
        result[topic] = {
            "count": len(matched),
            "titles": matched[:3]
        }

# ======================
# 热度总榜更新
# ======================

try:
    with open("hot_rank.json", "r", encoding="utf-8") as f:
        hot_rank = json.load(f)
except:
    hot_rank = {}

for topic, info in result.items():
    hot_rank[topic] = hot_rank.get(topic, 0) + info["count"]

with open("hot_rank.json", "w", encoding="utf-8") as f:
    json.dump(hot_rank, f, ensure_ascii=False, indent=2)


# ======================
# 连续升温 & 趋势更新 (前置计算，为打分提供最新数据)
# ======================

# 更新升温统计
for topic, info in result.items():
    score = info["count"]
    old = hot_streak.get(topic, {"last": 0, "streak": 0})
    if score > old["last"]:
        streak = old["streak"] + 1
    else:
        streak = 0
    hot_streak[topic] = {"last": score, "streak": streak}

# 更新趋势数据库
try:
    with open("trend.json", "r", encoding="utf-8") as f:
        trend = json.load(f)
except:
    trend = {}

run_id = str(len(trend) + 1)
trend[run_id] = {topic: info["count"] for topic, info in result.items()}

# 爆发预警生成
alert_text = ""
if len(trend) >= 2:
    keys = list(trend.keys())
    latest = trend[keys[-1]]
    previous = trend[keys[-2]]
    for topic in latest:
        now_count = latest.get(topic, 0)
        old_count = previous.get(topic, 0)
        if old_count > 0:
            increase = ((now_count - old_count) / old_count) * 100
            if increase >= 50:
                alert_text += f"🚨 {topic} 爆发 +{int(increase)}%\n"

if alert_text:
    alert_text += "\n====================\n\n"

# ======================
# 计算综合评分
# ======================

for topic, info in result.items():
    policy_score = info["count"]
    total_hot_score = hot_rank.get(topic, 0)
    streak_score = hot_streak.get(topic, {}).get("streak", 0)
    
    total_s, main_s, money_s = calc_score(policy_score, total_hot_score, streak_score)
    
    info["total_score"] = total_s
    info["main_score"] = main_s
    info["money_score"] = money_s

# ======================
# 消息组装
# ======================

rank_text = "🔥 热度总榜\n\n"
for idx, item in enumerate(sorted(hot_rank.items(), key=lambda x: x[1], reverse=True)[:5], start=1):
    rank_text += f"{idx}. {item[0]}（{item[1]}）\n"
rank_text += "\n====================\n\n"

message = ""

# 热度前三
rank_list = sorted(hot_rank.items(), key=lambda x: x[1], reverse=True)[:3]
medals = ["🥇", "🥈", "🥉"]

message += "🔥 今日最强题材\n\n"
for idx, (topic, score) in enumerate(rank_list):
    message += f"{medals[idx]} {topic}（{score}）\n"
    if topic in WATCHLIST:
        message += "龙头观察：\n"
        for stock in WATCHLIST[topic][:3]:
            message += f"• {stock}\n"
    message += "\n"
message += "====================\n\n"

# 最强主线
top_topic = None
if len(result) > 0:
    top_topic = max(result.items(), key=lambda x: x[1]["count"])[0]

leader_text = ""
if top_topic and top_topic in STOCK_POOL:
    leader_text += "🔥 今日最强主线\n\n"
    leader_text += f"{top_topic}（{hot_rank.get(top_topic,0)}）\n\n"
    leader_text += "核心龙头：\n"
    for stock in STOCK_POOL[top_topic][:3]:
        leader_text += f"• {stock}\n"
    leader_text += "\n====================\n\n"

# 连续升温显示
streak_text = ""
for topic, data in sorted(hot_streak.items(), key=lambda x: x[1]["streak"], reverse=True):
    if data["streak"] >= 3:
        streak_text += f"🔥 {topic} 连续升温 {data['streak']} 次\n"

if streak_text:
    streak_text += "\n====================\n\n"
    
# 拼接头部
message = (
    alert_text
    + streak_text
    + leader_text
    + rank_text
    + "【A股AI超级雷达 V14】\n\n"
)

message += f"新增政策：{len(new_titles)}条\n\n"
message += "✅ 综合评分已启用（Score Engine）\n\n"

# 核心变化：按综合评分排序
for topic, info in sorted(result.items(), key=lambda x: x[1]["total_score"], reverse=True):
    score = info["count"]
    
    if info["total_score"] >= 30:
        stars = "★★★★★"
    elif info["total_score"] >= 15:
        stars = "★★★★"
    else:
        stars = "★★★"

    message += f"{stars} {topic}\n\n"
    
    # 增加评分显示
    message += f"🎯 综合评分：{info['total_score']}分\n"
    message += f"┣ 主线评分：{info['main_score']}\n"
    message += f"┗ 资金评分：{info['money_score']}\n\n"
    
    message += f"今日新增：{score}\n"
    message += f"累计热度：{hot_rank.get(topic, 0)}\n\n"

    message += "政策：\n"
    for title in info["titles"]:
        show_title = translated_titles.get(title, title)
        message += f"• {show_title}\n"
    message += "\n"

    if topic in WATCHLIST:
        message += "观察：\n"
        for stock in WATCHLIST[topic]:
            message += f"• {stock}\n"

    message += "\n--------------------\n\n"

print(message)

# ======================
# Telegram 发送
# ======================

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)

# ======================
# 保存历史及更新库
# ======================

history.extend(new_titles)
with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)
print(f"历史记录已保存：{len(history)}条")

with open("hot_streak.json", "w", encoding="utf-8") as f:
    json.dump(hot_streak, f, ensure_ascii=False, indent=2)

with open("trend.json", "w", encoding="utf-8") as f:
    json.dump(trend, f, ensure_ascii=False, indent=2)
print("趋势库及升温库已更新")

# ======================
# 控制台趋势分析
# ======================

print("\n===== 热度趋势 =====")

if len(trend) >= 2:
    keys = list(trend.keys())
    latest = trend[keys[-1]]
    previous = trend[keys[-2]]

    for topic in latest:
        now_count = latest.get(topic, 0)
        old_count = previous.get(topic, 0)

        if now_count > old_count:
            arrow = "↑"
        elif now_count < old_count:
            arrow = "↓"
        else:
            arrow = "→"

        print(f"{topic}: {arrow} ({old_count} -> {now_count})")
else:
    print("趋势数据不足，需要至少运行2次")
