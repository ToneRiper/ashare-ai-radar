import os
import json
import requests
import urllib.parse
from deep_translator import GoogleTranslator

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 全局请求头，伪装真实浏览器，防止 GitHub Actions 海外 IP 被东财拦截
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ======================
# 东方财富实时 API：资金异动板块 & 个股中低位筛选
# ======================
def fetch_eastmoney_hot_sectors():
    """抓取东方财富概念板块实时资金流向与涨幅"""
    sectors = {}
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f14,f3,f62"
        res = requests.get(url, headers=HEADERS, timeout=10).json()
        if res and "data" in res and res["data"]:
            for item in res["data"]["diff"]:
                name = item["f14"]  # 板块名称
                change = item["f3"] # 涨跌幅 %
                inflow = item["f62"] # 主力净流入 (元)
                sectors[name] = {"change": change, "inflow": inflow}
        print(f"成功抓取东财资金板块，共 {len(sectors)} 个")
    except Exception as e:
        print(f"获取板块资金异动失败: {e}")
    return sectors

HOT_SECTORS = fetch_eastmoney_hot_sectors()

def fetch_mid_low_stocks(stock_names):
    """
    输入股票名称列表，从东财实时获取涨跌幅。
    返回低位潜伏池（涨幅在 1% ~ 6% 之间）的高性价比标的。
    """
    if not stock_names:
        return []
    
    secids = []
    # 1. 通过搜索接口，将名称转换为东财的 secid
    for name in stock_names:
        try:
            encoded_name = urllib.parse.quote(name)
            search_url = f"https://searchapi.eastmoney.com/api/suggest/get?input={encoded_name}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
            search_res = requests.get(search_url, headers=HEADERS, timeout=5).json()
            if search_res.get("QuotationCodeTable") and search_res["QuotationCodeTable"].get("Data"):
                stock_info = search_res["QuotationCodeTable"]["Data"][0]
                code = stock_info["Code"]
                # 区分沪深前缀：6开头为沪市(1)，0或3开头为深市(0)
                prefix = "1" if code.startswith("6") else "0"
                secids.append(f"{prefix}.{code}")
        except Exception as e:
            continue
            
    if not secids:
        return []

    # 2. 批量获取实时涨跌幅
    valid_stocks = []
    try:
        secids_str = ",".join(secids)
        quote_url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids_str}&fields=f12,f14,f3"
        quote_res = requests.get(quote_url, headers=HEADERS, timeout=5).json()
        if quote_res and "data" in quote_res and quote_res["data"]:
            for item in quote_res["data"]["diff"]:
                name = item["f14"]
                change = item["f3"]
                # 核心过滤逻辑：不要 > 6% 的高位股，不要 < 1% 的弱势股，只抓 1% ~ 6% 之间的起步股
                if isinstance(change, (int, float)) and 1.0 <= change <= 6.0:
                    valid_stocks.append({"name": name, "change": change})
    except Exception as e:
        print(f"获取个股行情失败: {e}")

    # 按涨跌幅排序（涨得好的靠前，但已被掐头去尾）
    valid_stocks.sort(key=lambda x: x["change"], reverse=True)
    return valid_stocks

# ======================
# 综合评分引擎 V2
# ======================
def calc_score(policy, total_hot, streak, topic_name, aliases):
    main_score = round(policy * 5 + total_hot * 0.2, 1)
    money_score = streak * 8
    
    is_resonance = False
    resonance_desc = ""
    for sector_name, data in HOT_SECTORS.items():
        # 模糊匹配：只要东财板块名里包含我们的关键词，就算命中
        if any(alias in sector_name for alias in [topic_name] + aliases):
            change = data.get("change", 0)
            inflow = data.get("inflow", 0)
            if change > 0:
                is_resonance = True
                money_score += 20
                inflow_yi = round(inflow / 100000000, 2)
                resonance_desc = f"[🚀 资金共振: {sector_name}板块 涨 {change}% | 主力流入 {inflow_yi}亿]"
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
except:
    history = []
history_set = set(history)

# ======================
# 读取标题 (严格适配带 link 的字典)
# ======================
all_news = [] 

for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                if isinstance(item, str):
                    all_news.append({"title": item, "link": ""})
                elif isinstance(item, dict):
                    all_news.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", item.get("url", ""))
                    })
    except:
        pass

unique_news = {}
for news in all_news:
    if news["title"] not in unique_news:
        unique_news[news["title"]] = news
all_news = list(unique_news.values())

new_news = [n for n in all_news if n["title"] not in history_set]
print(f"总数据：{len(all_news)} | 新增：{len(new_news)}")

# ======================
# 自动翻译 (增加异常打印)
# ======================
translated_titles = {}
for news in new_news:
    title = news["title"]
    try:
        if any('\u4e00' <= c <= '\u9fff' for c in title):
            translated_titles[title] = title
        else:
            translated_titles[title] = GoogleTranslator(source="auto", target="zh-CN").translate(title)
    except Exception as e:
        print(f"翻译失败 (降级为原文): {title} -> 报错: {e}")
        translated_titles[title] = title

# ======================
# 热点统计
# ======================
result = {}
for topic, aliases in KEYWORDS.items():
    matched_news = []
    for news in all_news:
        for alias in aliases:
            if alias.lower() in news["title"].lower():
                matched_news.append(news)
                break
    if matched_news:
        result[topic] = {
            "count": len(matched_news),
            "news_list": matched_news[:3]
        }

# ======================
# 数据库更新
# ======================
try:
    with open("hot_rank.json", "r", encoding="utf-8") as f:
        hot_rank = json.load(f)
except:
    hot_rank = {}

for topic, info in result.items():
    hot_rank[topic] = hot_rank.get(topic, 0) + info["count"]
    score = info["count"]
    old = hot_streak.get(topic, {"last": 0, "streak": 0})
    hot_streak[topic] = {"last": score, "streak": old["streak"] + 1 if score > old["last"] else 0}

try:
    with open("trend.json", "r", encoding="utf-8") as f:
        trend = json.load(f)
except:
    trend = {}

run_id = str(len(trend) + 1)
trend[run_id] = {topic: info["count"] for topic, info in result.items()}

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
# 评分与组装
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

rank_text = "🔥 <b>热度总榜</b>\n\n"
for idx, item in enumerate(sorted(hot_rank.items(), key=lambda x: x[1], reverse=True)[:5], start=1):
    rank_text += f"{idx}. {item[0]}（{item[1]}）\n"
rank_text += "\n====================\n\n"

message = alert_text + rank_text + "<b>【A股AI超级雷达 V16】</b>\n\n"
message += f"新增政策：{len(new_news)}条\n"
message += "✅ 量化资金共振联机 | ✅ 中低位潜伏过滤开启\n\n"

for topic, info in sorted(result.items(), key=lambda x: x[1]["total_score"], reverse=True):
    stars = "★★★★★" if info["total_score"] >= 30 else ("★★★★" if info["total_score"] >= 15 else "★★★")

    message += f"<b>{stars} {topic}</b>"
    if info["is_resonance"]:
        message += f"\n{info['resonance_desc']}"
    message += "\n\n"
    
    message += f"🎯 综合评分：{info['total_score']}分 (主线{info['main_score']} | 资金{info['money_score']})\n\n"

    message += "<b>政策精选：</b>\n"
    for news in info["news_list"]:
        en_title = news["title"].replace("<", "&lt;").replace(">", "&gt;")
        cn_title = translated_titles.get(news["title"], news["title"]).replace("<", "&lt;").replace(">", "&gt;")
        link = news.get("link", "")
        
        if link and link.startswith("http"):
            message += f"• <a href='{link}'>{cn_title}</a>\n"
        else:
            message += f"• {cn_title}\n"
        if cn_title != en_title:
            message += f"  <i>└ {en_title}</i>\n"
    message += "\n"

    # 新版选股逻辑展示
    if topic in STOCK_POOL:
        # 获取低位潜伏股（基于 STOCK_POOL 中的备选股票）
        mid_low_stocks = fetch_mid_low_stocks(STOCK_POOL[topic])
        
        message += "<b>资金跟涨/低位潜伏：</b>\n"
        if mid_low_stocks:
            for stock in mid_low_stocks[:4]:  # 取前4个性价比最高的
                message += f"• <code>{stock['name']}</code> (涨幅: {stock['change']} %)\n"
        else:
            message += "• 暂无符合 [1%~6%] 涨幅区间的蓄势标的\n"
            
        message += "\n<b>核心标杆 (参考)：</b>\n"
        if topic in WATCHLIST:
            message += " ".join([f"<code>{s}</code>" for s in WATCHLIST[topic][:3]]) + "\n"

    message += "\n--------------------\n\n"

# ======================
# Telegram 发送
# ======================
payload = {
    "chat_id": CHAT_ID,
    "text": message[:4000],
    "parse_mode": "HTML",
    "disable_web_page_preview": True
}
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload)

# ======================
# 落盘
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
