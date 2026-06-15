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

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ======================
# 翻译引擎与永久缓存
# ======================
try:
    with open("trans_cache.json", "r", encoding="utf-8") as f:
        trans_cache = json.load(f)
except:
    trans_cache = {}

def baidu_translate(query):
    if not BAIDU_APP_ID or not BAIDU_SECRET_KEY: return None
    salt = str(random.randint(32768, 65536))
    sign_str = BAIDU_APP_ID + query + salt + BAIDU_SECRET_KEY
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
    url = f"http://api.fanyi.baidu.com/api/trans/vip/translate?q={urllib.parse.quote(query)}&from=auto&to=zh&appid={BAIDU_APP_ID}&salt={salt}&sign={sign}"
    try:
        res = requests.get(url, timeout=15).json()
        time.sleep(1.2)
        if "trans_result" in res: return res["trans_result"][0]["dst"]
    except Exception as e:
        print(f"百度翻译异常: {e}")
    return None

def get_translation(text):
    if any('\u4e00' <= c <= '\u9fff' for c in text): return text
    if text in trans_cache: return trans_cache[text]
    
    bd_res = baidu_translate(text)
    if bd_res: 
        trans_cache[text] = bd_res
        return bd_res
    
    try:
        gt_res = GoogleTranslator(source="auto", target="zh-CN").translate(text)
        trans_cache[text] = gt_res
        return gt_res
    except: pass
    
    return text

# ======================
# 东财全量板块抓取
# ======================
def fetch_all_sectors():
    sectors, hot_sectors = {}, {}
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1000&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2,m:90+t:3&fields=f12,f14,f3,f62"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            res = r.json()
            if res and "data" in res and res["data"]:
                for item in res["data"]["diff"]:
                    sectors[item["f14"]] = item["f12"]
                    hot_sectors[item["f14"]] = {"change": item["f3"], "inflow": item["f62"]}
    except Exception as e:
        print(f"全量板块异常: {e}")
    return sectors, hot_sectors

SECTOR_MAP, HOT_SECTORS = fetch_all_sectors()

# ======================
# 核心升级：游资异动量化引擎 2.0 (重构版)
# ======================
def auto_quant_stock_pick(topic_name, aliases):
    target_code, target_name = None, None
    for name, code in SECTOR_MAP.items():
        if any(alias in name for alias in [topic_name] + aliases):
            target_code, target_name = code, name
            break
            
    if not target_code: return None, []

    valid_stocks = []
    try:
        url = f"https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=b:{target_code}&fields=f12,f14,f3,f8,f10,f62"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if res and "data" in res and res["data"]:
                for item in res["data"]["diff"]:
                    name, change, vol_ratio, turnover, inflow = item["f14"], item["f3"], item["f10"], item["f8"], item["f62"]
                    
                    if not isinstance(change, (int, float)): continue
                    if not isinstance(vol_ratio, (int, float)): vol_ratio = 0
                    if not isinstance(turnover, (int, float)): turnover = 0
                    if not isinstance(inflow, (int, float)): inflow = 0
                    
                    # 【全新过滤规则】：
                    # 1. 涨幅放宽至 -3% ~ 8% (捕捉水下换手和蓄势拉升)
                    # 2. 活跃度双通道：量比 > 1.2 或 换手率 > 5%
                    if (-3.0 <= change <= 8.0) and (vol_ratio >= 1.2 or turnover >= 5.0):
                        inflow_wan = round(inflow / 10000, 1)
                        # 综合活跃度打分：换手率权重极高，体现游资活跃程度
                        activity_score = (turnover * 3) + (vol_ratio * 5)
                        valid_stocks.append({
                            "name": name, 
                            "change": change, 
                            "vol_ratio": vol_ratio,
                            "turnover": turnover,
                            "inflow_wan": inflow_wan,
                            "activity": activity_score
                        })
    except Exception as e:
        print(f"成份股拉取异常: {e}")

    # 按活跃度总分降序，而不是单纯的主力流入
    valid_stocks.sort(key=lambda x: x["activity"], reverse=True)
    return target_name, valid_stocks

# ======================
# 综合评分
# ======================
def calc_score(policy, total_hot, streak, topic_name, aliases):
    main_score = round(policy * 5 + total_hot * 0.2, 1)
    money_score = streak * 8
    is_resonance, resonance_desc = False, ""
    
    for sector_name, data in HOT_SECTORS.items():
        if any(alias in sector_name for alias in [topic_name] + aliases):
            change = data.get("change", 0)
            if change > 0:
                is_resonance = True
                money_score += 20
                resonance_desc = f"[🚀 资金共振: {sector_name}板块 涨 {change}%]"
            break
            
    return round(main_score + money_score, 1), main_score, round(money_score, 1), is_resonance, resonance_desc

# ======================
# 加载库与历史处理
# ======================
with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
try:
    with open("hot_streak.json", "r", encoding="utf-8") as f: hot_streak = json.load(f)
except: hot_streak = {}
try:
    with open("history.json", "r", encoding="utf-8") as f: history = json.load(f)
except: history = []
history_set = set(history)

# 读取数据
all_news = [] 
for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if isinstance(item, str): all_news.append({"title": item, "link": ""})
                elif isinstance(item, dict): all_news.append({"title": item.get("title", ""), "link": item.get("link", "")})
    except: pass

# 去重
unique_news = {}
for news in all_news: unique_news[news["title"]] = news
all_news = list(unique_news.values())

# 提取增量并执行翻译
new_news = [n for n in all_news if n["title"] not in history_set]
for news in new_news:
    get_translation(news["title"]) # 存入 trans_cache

# 保存翻译缓存
with open("trans_cache.json", "w", encoding="utf-8") as f:
    json.dump(trans_cache, f, ensure_ascii=False, indent=2)

# ======================
# 统计与生成报告
# ======================
result = {}
for topic, aliases in KEYWORDS.items():
    matched_news = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
    if matched_news:
        result[topic] = {"count": len(matched_news), "all_news": matched_news}

try:
    with open("hot_rank.json", "r", encoding="utf-8") as f: hot_rank = json.load(f)
except: hot_rank = {}

for topic, info in result.items():
    hot_rank[topic] = hot_rank.get(topic, 0) + info["count"]
    old = hot_streak.get(topic, {"last": 0, "streak": 0})
    hot_streak[topic] = {"last": info["count"], "streak": old["streak"] + 1 if info["count"] > old["last"] else 0}

message = "<b>【A股AI超级雷达 V22】</b>\n\n"
message += f"发现新政策/事件：{len(new_news)}条\n"
message += "✅ 翻译永久记忆缓存 | ✅ 游资异动宽频过滤网\n\n"

for topic, info in sorted(result.items(), key=lambda x: x[1]["count"], reverse=True):
    total_s, main_s, money_s, is_res, res_desc = calc_score(info["count"], hot_rank.get(topic, 0), hot_streak.get(topic, {}).get("streak", 0), topic, KEYWORDS.get(topic, []))
    
    stars = "★★★★★" if total_s >= 30 else ("★★★★" if total_s >= 15 else "★★★")
    message += f"<b>{stars} {topic}</b>\n"
    if is_res: message += f"{res_desc}\n"
    message += f"🎯 综合评分：{total_s}分\n\n"

    # 新老资讯隔离排版
    topic_new_news = [n for n in new_news if any(a.lower() in n["title"].lower() for a in KEYWORDS.get(topic, []))]
    
    message += "<b>📢 最新驱动：</b>\n"
    if topic_new_news:
        for news in topic_new_news[:3]:
            en_title = escape_html(news["title"])
            cn_title = escape_html(get_translation(news["title"]))
            link = escape_html(news.get("link", ""))
            
            if link and link.startswith("http"): message += f"• <a href='{link}'>{cn_title}</a>\n"
            else: message += f"• {cn_title}\n"
                
            if cn_title != en_title: message += f"  <i>└ {en_title}</i>\n"
    else:
        message += "• 暂无新增消息（底层逻辑延烧中）\n"
    message += "\n"

    # 异动潜伏池
    sector_name, quant_stocks = auto_quant_stock_pick(topic, KEYWORDS.get(topic, []))
    if sector_name:
        message += f"<b>💡 {sector_name} - 异动潜伏池：</b>\n"
        if quant_stocks:
            for stock in quant_stocks[:4]:
                message += f"• <code>{stock['name']}</code> (涨: {stock['change']}%, 换手: {stock['turnover']}%, 量比: {stock['vol_ratio']})\n"
        else:
            message += "• 暂无符合 [高换手/放量异动] 的优质标的\n"

    message += "\n--------------------\n\n"

# ======================
# Telegram 发送
# ======================
def send_to_telegram(text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text[:4000], "disable_web_page_preview": True}
    if parse_mode: payload["parse_mode"] = parse_mode
        
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code != 200 and parse_mode == "HTML":
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
            send_to_telegram(clean_text, parse_mode=None)
    except: pass

send_to_telegram(message)

# ======================
# 落盘保存
# ======================
history.extend([n["title"] for n in new_news])
with open("history.json", "w", encoding="utf-8") as f: json.dump(history, f, ensure_ascii=False, indent=2)
with open("hot_rank.json", "w", encoding="utf-8") as f: json.dump(hot_rank, f, ensure_ascii=False, indent=2)
with open("hot_streak.json", "w", encoding="utf-8") as f: json.dump(hot_streak, f, ensure_ascii=False, indent=2)
