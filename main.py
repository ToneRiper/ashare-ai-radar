import os
import json
import requests
import urllib.parse
import hashlib
import random
import time
from deep_translator import GoogleTranslator, MyMemoryTranslator

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BAIDU_APP_ID = os.getenv("BAIDU_APP_ID")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Connection": "keep-alive"
}

# ======================
# 文本转义 (修复 Telegram 报错漏代码的问题)
# ======================
def escape_html(text):
    if not text:
        return ""
    # 必须先替换 &，再替换 <> 
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ======================
# 百度翻译接入
# ======================
def baidu_translate(query):
    if not BAIDU_APP_ID or not BAIDU_SECRET_KEY:
        return None
    salt = str(random.randint(32768, 65536))
    sign_str = BAIDU_APP_ID + query + salt + BAIDU_SECRET_KEY
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
    url = f"http://api.fanyi.baidu.com/api/trans/vip/translate?q={urllib.parse.quote(query)}&from=auto&to=zh&appid={BAIDU_APP_ID}&salt={salt}&sign={sign}"
    try:
        res = requests.get(url, timeout=15).json()
        time.sleep(1.2)
        if "trans_result" in res:
            return res["trans_result"][0]["dst"]
    except Exception as e:
        print(f"百度翻译异常: {e}")
    return None

def safe_translate(text):
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        return text
    bd_res = baidu_translate(text)
    if bd_res: return bd_res
    try: return GoogleTranslator(source="auto", target="zh-CN").translate(text)
    except: pass
    try: return MyMemoryTranslator(source="en", target="zh-CN").translate(text)
    except: return text

# ======================
# 东财全量板块 & 资金抓取
# ======================
def fetch_all_sectors():
    """抓取全市场所有板块及其代码，用于自动选股映射"""
    sectors = {}
    hot_sectors = {}
    try:
        # m:90 t:2 (行业板块), m:90 t:3 (概念板块)
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1000&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2,m:90+t:3&fields=f12,f14,f3,f62"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            res = r.json()
            if res and "data" in res and res["data"]:
                for item in res["data"]["diff"]:
                    code = item["f12"]
                    name = item["f14"]
                    change = item["f3"]
                    inflow = item["f62"]
                    sectors[name] = code
                    # 同时记录资金数据供打分用
                    hot_sectors[name] = {"change": change, "inflow": inflow}
    except Exception as e:
        print(f"全量板块抓取异常: {e}")
    return sectors, hot_sectors

SECTOR_MAP, HOT_SECTORS = fetch_all_sectors()

# ======================
# 核心革命：智能量化自动选股 (彻底替代手动股票池)
# ======================
def auto_quant_stock_pick(topic_name, aliases):
    # 1. 寻找对应的东方财富板块代码
    target_code = None
    target_name = None
    for name, code in SECTOR_MAP.items():
        if any(alias in name for alias in [topic_name] + aliases):
            target_code = code
            target_name = name
            break
            
    if not target_code:
        return None, [] # 没找到对应板块

    # 2. 抓取该板块下所有成份股
    valid_stocks = []
    try:
        # f3:涨幅, f8:换手率, f10:量比, f62:主力净流入
        url = f"https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=b:{target_code}&fields=f12,f14,f3,f8,f10,f62"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if res and "data" in res and res["data"]:
                for item in res["data"]["diff"]:
                    name = item["f14"]
                    change = item["f3"]
                    vol_ratio = item["f10"] # 量比
                    inflow = item["f62"]    # 主力净流入
                    
                    # 容错处理：停牌或没数据的字段东财会返回 "-"
                    if not isinstance(change, (int, float)): continue
                    if not isinstance(vol_ratio, (int, float)): vol_ratio = 0
                    if not isinstance(inflow, (int, float)): inflow = 0
                    
                    # ===============
                    # 量化过滤网
                    # ===============
                    # 1. 涨跌幅在 1% ~ 6% 之间（中低位）
                    # 2. 量比 > 1.2 (成交活跃，有增量资金)
                    # 3. 主力净流入 > 0 (跟着主力喝汤)
                    if (1.0 <= change <= 6.0) and (vol_ratio > 1.2) and (inflow > 0):
                        inflow_wan = round(inflow / 10000, 1) # 转成万
                        valid_stocks.append({
                            "name": name, 
                            "change": change, 
                            "vol_ratio": vol_ratio,
                            "inflow_wan": inflow_wan
                        })
    except Exception as e:
        print(f"成份股拉取异常: {e}")

    # 按主力净流入资金大小进行排序，选出最有底气的票
    valid_stocks.sort(key=lambda x: x["inflow_wan"], reverse=True)
    return target_name, valid_stocks

# ======================
# 综合评分 V2
# ======================
def calc_score(policy, total_hot, streak, topic_name, aliases):
    main_score = round(policy * 5 + total_hot * 0.2, 1)
    money_score = streak * 8
    
    is_resonance = False
    resonance_desc = ""
    for sector_name, data in HOT_SECTORS.items():
        if any(alias in sector_name for alias in [topic_name] + aliases):
            change = data.get("change", 0)
            inflow = data.get("inflow", 0)
            if change > 0:
                is_resonance = True
                money_score += 20
                if isinstance(inflow, (int, float)):
                    inflow_yi = round(inflow / 100000000, 2)
                    resonance_desc = f"[🚀 资金共振: {sector_name}板块 涨 {change}% | 流入 {inflow_yi}亿]"
                else:
                    resonance_desc = f"[🚀 资金共振: {sector_name}板块 涨 {change}%]"
            break
            
    return round(main_score + money_score, 1), main_score, round(money_score, 1), is_resonance, resonance_desc

# ======================
# 加载基础库
# ======================
with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
with open("watchlist.json", "r", encoding="utf-8") as f: WATCHLIST = json.load(f)

try:
    with open("hot_streak.json", "r", encoding="utf-8") as f: hot_streak = json.load(f)
except: hot_streak = {}

try:
    with open("history.json", "r", encoding="utf-8") as f: history = json.load(f)
except: history = []
history_set = set(history)

# ======================
# 读取标题与去重
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

translated_titles = {}
for news in new_news:
    translated_titles[news["title"]] = safe_translate(news["title"])

# ======================
# 热点统计 & 更新数据库
# ======================
result = {}
for topic, aliases in KEYWORDS.items():
    matched_news = []
    for news in all_news:
        if any(alias.lower() in news["title"].lower() for alias in aliases):
            matched_news.append(news)
    if matched_news:
        result[topic] = {"count": len(matched_news), "news_list": matched_news[:3]}

try:
    with open("hot_rank.json", "r", encoding="utf-8") as f: hot_rank = json.load(f)
except: hot_rank = {}

for topic, info in result.items():
    hot_rank[topic] = hot_rank.get(topic, 0) + info["count"]
    score = info["count"]
    old = hot_streak.get(topic, {"last": 0, "streak": 0})
    hot_streak[topic] = {"last": score, "streak": old["streak"] + 1 if score > old["last"] else 0}

try:
    with open("trend.json", "r", encoding="utf-8") as f: trend = json.load(f)
except: trend = {}
trend[str(len(trend) + 1)] = {topic: info["count"] for topic, info in result.items()}

# ======================
# 评分与排版
# ======================
for topic, info in result.items():
    total_s, main_s, money_s, is_res, res_desc = calc_score(
        info["count"], hot_rank.get(topic, 0), hot_streak.get(topic, {}).get("streak", 0), topic, KEYWORDS.get(topic, [])
    )
    info.update({"total_score": total_s, "main_score": main_s, "money_score": money_s, "is_resonance": is_res, "resonance_desc": res_desc})

message = "<b>【A股AI超级雷达 V21】</b>\n\n"
message += f"新增政策：{len(new_news)}条\n"
message += "✅ 全自动量化选股联机 (量比+资金双过滤)\n\n"

for topic, info in sorted(result.items(), key=lambda x: x[1]["total_score"], reverse=True):
    stars = "★★★★★" if info["total_score"] >= 30 else ("★★★★" if info["total_score"] >= 15 else "★★★")
    message += f"<b>{stars} {topic}</b>\n"
    if info["is_resonance"]: message += f"{info['resonance_desc']}\n"
    message += f"🎯 综合评分：{info['total_score']}分 (主线{info['main_score']} | 资金{info['money_score']})\n\n"

    message += "<b>政策精选：</b>\n"
    for news in info["news_list"]:
        en_title = escape_html(news["title"])
        cn_title = escape_html(translated_titles.get(news["title"], news["title"]))
        link = escape_html(news.get("link", ""))
        
        if link and link.startswith("http"):
            message += f"• <a href='{link}'>{cn_title}</a>\n"
        else:
            message += f"• {cn_title}\n"
            
        if cn_title != en_title:
            message += f"  <i>└ {en_title}</i>\n"
    message += "\n"

    # ======================
    # 核心展示：全自动量化选股池
    # ======================
    aliases = KEYWORDS.get(topic, [])
    sector_name, quant_stocks = auto_quant_stock_pick(topic, aliases)
    
    if sector_name:
        message += f"<b>💡 {sector_name} - 异动潜伏池：</b>\n"
        if quant_stocks:
            # 只取满足条件的前 4 名
            for stock in quant_stocks[:4]:
                message += f"• <code>{stock['name']}</code> (涨: {stock['change']}%, 量比: {stock['vol_ratio']}, 主力: +{stock['inflow_wan']}万)\n"
        else:
            message += "• 暂无符合 [涨幅1-6% + 量比>1.2 + 主力净流入] 的优质标的\n"
    else:
        # 如果没找到对应的东财板块，回退显示核心标杆
        if topic in WATCHLIST:
            message += "<b>核心标杆 (参考)：</b>\n"
            message += " ".join([f"<code>{s}</code>" for s in WATCHLIST[topic][:3]]) + "\n"

    message += "\n--------------------\n\n"

# ======================
# Telegram 安全发送模块
# ======================
def send_to_telegram(text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text[:4000],
        "disable_web_page_preview": True
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
        
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            print(f"Telegram 消息发送成功")
        else:
            print(f"HTML格式发送失败，拦截原因: {res.text}")
            if parse_mode == "HTML":
                print(">> 触发降级重发机制...")
                clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
                send_to_telegram(clean_text, parse_mode=None)
    except Exception as e:
        print(f"Telegram 请求失败: {e}")

send_to_telegram(message)

# ======================
# 落盘保存
# ======================
history.extend([n["title"] for n in new_news])
with open("history.json", "w", encoding="utf-8") as f: json.dump(history, f, ensure_ascii=False, indent=2)
with open("hot_rank.json", "w", encoding="utf-8") as f: json.dump(hot_rank, f, ensure_ascii=False, indent=2)
with open("hot_streak.json", "w", encoding="utf-8") as f: json.dump(hot_streak, f, ensure_ascii=False, indent=2)
with open("trend.json", "w", encoding="utf-8") as f: json.dump(trend, f, ensure_ascii=False, indent=2)
