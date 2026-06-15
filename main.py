import os
import json
import requests
from deep_translator import GoogleTranslator

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ======================
# 东方财富 实时资金异动监控
# ======================
def fetch_eastmoney_hot_sectors():
    """抓取东方财富概念板块实时资金流向与涨幅"""
    sectors = {}
    try:
        # 东财公开API: 获取概念板块行情及资金流 (pn=1页数, pz=50获取前50个热点板块)
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f14,f3,f62"
        res = requests.get(url, timeout=10).json()
        if res and "data" in res and res["data"]:
            for item in res["data"]["diff"]:
                name = item["f14"]  # 板块名称
                change = item["f3"] # 涨跌幅 %
                inflow = item["f62"] # 主力净流入 (元)
                sectors[name] = {
                    "change": change,
                    "inflow": inflow
                }
    except Exception as e:
        print(f"获取资金异动失败: {e}")
    return sectors

HOT_SECTORS = fetch_eastmoney_hot_sectors()

# ======================
# 综合评分引擎 (Score Engine V2 - 加入资金共振)
# ======================
def calc_score(policy, total_hot, streak, topic_name, aliases):
    # 1. 主线评分：政策驱动 + 历史底蕴
    main_score = round(policy * 5 + total_hot * 0.2, 1)
    
    # 2. 资金评分基础：连续升温加速
    money_score = streak * 8
    
    # 3. 真实资金共振溢价 (扫描东财榜单)
    is_resonance = False
    resonance_desc = ""
    for sector_name, data in HOT_SECTORS.items():
        # 如果题材名或其别名包含在东财的强势板块中
        if any(alias in sector_name for alias in [topic_name] + aliases):
            change = data.get("change", 0)
            inflow = data.get("inflow", 0)
            if change > 0:
                is_resonance = True
                # 资金评分大幅加成
                money_score += 20
                inflow_yi = round(inflow / 100000000, 2) # 转为亿元
                resonance_desc = f"[🚀 资金共振: 涨 {change}% | 主力流入 {inflow_yi}亿]"
            break
            
    money_score = round(money_score, 1)
    total_score = round(main_score + money_score, 1)
    
    return total_score, main_score, money_score, is_resonance, resonance_desc

# ======================
# 加载基础库
# ======================
with open("keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS = json.load(f)

with open("watchlist.json", "r", encoding="utf-8") as f:
    WATCHLIST = json.load(f)

with open("stock_pool.json", "r", encoding="utf-8") as f:
    STOCK_POOL = json.load(f)

try:
    with open("hot_streak.json", "r", encoding="utf-8") as f:
        hot_streak = json.load(f)
except:
    hot_streak = {}

try:
    with open("history.json", "r", encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history, list):
        history = []
except:
    history = []
history_set = set(history)

# ======================
# 读取标题 (兼容纯文本与字典格式)
# ======================
all_news = [] # 存储字典: {"title": "", "link": ""}

for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                # 兼容旧版的纯字符串列表
                if isinstance(item, str):
                    all_news.append({"title": item, "link": ""})
                # 适配新版带超链接的字典格式
                elif isinstance(item, dict):
                    all_news.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", item.get("url", ""))
                    })
    except:
        pass

# 去重 (以标题为准)
unique_news = {}
for news in all_news:
    if news["title"] not in unique_news:
        unique_news[news["title"]] = news
all_news = list(unique_news.values())
print(f"总数据：{len(all_news)}")

# ======================
# 新增策略提取
# ======================
new_news = []
for news in all_news:
    if news["title"] not in history_set:
        new_news.append(news)

print(f"新增政策：{len(new_news)}")
if len(new_news) == 0:
    print("没有新增政策")
    new_news = []

# ======================
# 自动翻译
# ======================
translated_titles = {}
for news in new_news:
    title = news["title"]
    try:
        # 如果包含中文字符，则不翻译
        if any('\u4e00' <= c <= '\u9fff' for c in title):
            translated_titles[title] = title
        else:
            translated_titles[title] = GoogleTranslator(source="auto", target="zh-CN").translate(title)
    except:
        translated_titles[title] = title

# ======================
# 热点统计 & 匹配
# ======================
result = {}
for topic, aliases in KEYWORDS.items():
    matched_news = []
    for news in all_news:
        title = news["title"]
        for alias in aliases:
            if alias.lower() in title.lower():
                matched_news.append(news)
                break
    if matched_news:
        result[topic] = {
            "count": len(matched_news),
            "news_list": matched_news[:3] # 取前3条
        }

# ======================
# 数据库更新 (热度、趋势、连续升温)
# ======================
try:
    with open("hot_rank.json", "r", encoding="utf-8") as f:
        hot_rank = json.load(f)
except:
    hot_rank = {}

for topic, info in result.items():
    hot_rank[topic] = hot_rank.get(topic, 0) + info["count"]

for topic, info in result.items():
    score = info["count"]
    old = hot_streak.get(topic, {"last": 0, "streak": 0})
    if score > old["last"]:
        streak = old["streak"] + 1
    else:
        streak = 0
    hot_streak[topic] = {"last": score, "streak": streak}

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
                alert_text += f"🚨 <b>{topic} 爆发 +{int(increase)}%</b>\n"
if alert_text:
    alert_text += "\n====================\n\n"

# ======================
# 计算综合评分 V2
# ======================
for topic, info in result.items():
    policy_score = info["count"]
    total_hot_score = hot_rank.get(topic, 0)
    streak_score = hot_streak.get(topic, {}).get("streak", 0)
    aliases = KEYWORDS.get(topic, [])
    
    total_s, main_s, money_s, is_res, res_desc = calc_score(
        policy_score, total_hot_score, streak_score, topic, aliases
    )
    
    info["total_score"] = total_s
    info["main_score"] = main_s
    info["money_score"] = money_s
    info["is_resonance"] = is_res
    info["resonance_desc"] = res_desc

# ======================
# Telegram HTML 消息组装
# ======================
rank_text = "🔥 <b>热度总榜</b>\n\n"
for idx, item in enumerate(sorted(hot_rank.items(), key=lambda x: x[1], reverse=True)[:5], start=1):
    rank_text += f"{idx}. {item[0]}（{item[1]}）\n"
rank_text += "\n====================\n\n"

message = ""

# 热度前三
rank_list = sorted(hot_rank.items(), key=lambda x: x[1], reverse=True)[:3]
medals = ["🥇", "🥈", "🥉"]

message += "🔥 <b>今日最强题材</b>\n\n"
for idx, (topic, score) in enumerate(rank_list):
    message += f"{medals[idx]} <b>{topic}</b>（{score}）\n"
    if topic in WATCHLIST:
        message += "<i>龙头观察：</i>"
        message += " ".join(WATCHLIST[topic][:3]) + "\n"
    message += "\n"
message += "====================\n\n"

# 连续升温显示
streak_text = ""
for topic, data in sorted(hot_streak.items(), key=lambda x: x[1]["streak"], reverse=True):
    if data["streak"] >= 3:
        streak_text += f"🔥 <b>{topic}</b> 连续升温 {data['streak']} 次\n"
if streak_text:
    streak_text += "\n====================\n\n"
    
# 拼接头部
message = (
    alert_text
    + streak_text
    + message
    + rank_text
    + "<b>【A股AI超级雷达 V15】</b>\n\n"
)

message += f"新增政策：{len(new_news)}条\n"
message += "✅ 综合评分已启用 | 资金异动监控已联机\n\n"

# 核心变化：按综合评分排序
for topic, info in sorted(result.items(), key=lambda x: x[1]["total_score"], reverse=True):
    score = info["count"]
    
    if info["total_score"] >= 30:
        stars = "★★★★★"
    elif info["total_score"] >= 15:
        stars = "★★★★"
    else:
        stars = "★★★"

    message += f"<b>{stars} {topic}</b> "
    if info["is_resonance"]:
        message += f" {info['resonance_desc']}"
    message += "\n\n"
    
    message += f"🎯 综合评分：{info['total_score']}分\n"
    message += f"┣ 主线评分：{info['main_score']}\n"
    message += f"┗ 资金评分：{info['money_score']}\n\n"

    message += "<b>政策：</b>\n"
    for news in info["news_list"]:
        en_title = news["title"]
        # 获取翻译，如果在translated_titles里找不到就用原文
        cn_title = translated_titles.get(en_title, en_title)
        link = news.get("link", "")

        # 防御 HTML 转义符对 TG 格式的破坏
        cn_title_safe = cn_title.replace("<", "&lt;").replace(">", "&gt;")
        en_title_safe = en_title.replace("<", "&lt;").replace(">", "&gt;")
        
        if link and link.startswith("http"):
            message += f"• <a href='{link}'>{cn_title_safe}</a>\n"
        else:
            message += f"• {cn_title_safe}\n"
        
        # 中英文对照：如果翻译过，则下面附加斜体英文
        if cn_title != en_title:
            message += f"  <i>└ {en_title_safe}</i>\n"
            
    message += "\n"

    if topic in WATCHLIST:
        message += "<b>观察池：</b>\n"
        for stock in WATCHLIST[topic]:
            message += f"• <code>{stock}</code>\n"

    message += "\n--------------------\n\n"

print("消息总长度:", len(message))

# ======================
# Telegram 发送 (启用 HTML 模式)
# ======================
payload = {
    "chat_id": CHAT_ID,
    "text": message[:4000],
    "parse_mode": "HTML",       # 核心变动：启用HTML渲染超链接和加粗
    "disable_web_page_preview": True # 防止链接自动生成一堆预览图刷屏
}

res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload)
print(f"Telegram 响应: {res.text}")

# ======================
# 保存历史及更新库
# ======================
history.extend([n["title"] for n in new_news])
with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

with open("hot_rank.json", "w", encoding="utf-8") as f:
    json.dump(hot_rank, f, ensure_ascii=False, indent=2)

with open("hot_streak.json", "w", encoding="utf-8") as f:
    json.dump(hot_streak, f, ensure_ascii=False, indent=2)

with open("trend.json", "w", encoding="utf-8") as f:
    json.dump(trend, f, ensure_ascii=False, indent=2)
