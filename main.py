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
    except: pass
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
    except: pass
    return sectors, hot_sectors

SECTOR_MAP, HOT_SECTORS = fetch_all_sectors()

# ======================
# 纯资金主线探测 (更敏感的阈值)
# ======================
def get_top_capital_sectors(limit=2):
    valid_sectors = []
    for name, data in HOT_SECTORS.items():
        change = data.get("change", 0)
        inflow = data.get("inflow", 0)
        
        if not isinstance(change, (int, float)): continue
        if not isinstance(inflow, (int, float)): continue
        
        # 只要板块微红，且主力流入超2000万即视为有资金关照
        if change >= 0.2 and inflow > 20000000:
            score = (inflow / 10000000) * change
            valid_sectors.append({
                "name": name,
                "code": SECTOR_MAP.get(name),
                "change": change,
                "inflow_yi": round(inflow / 100000000, 2),
                "score": score
            })
            
    valid_sectors.sort(key=lambda x: x["score"], reverse=True)
    return valid_sectors[:limit]

# ======================
# V27 顶级游资量化引擎 (黄金市值段 + 暗流监控)
# ======================
def auto_quant_stock_pick(target_code):
    if not target_code: return []

    valid_stocks = []
    try:
        url = f"https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=b:{target_code}&fields=f12,f14,f2,f3,f8,f10,f62,f7,f64,f22,f116"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if res and "data" in res and res["data"]:
                for item in res["data"]["diff"]:
                    code = item["f12"]
                    
                    if not (code.startswith('00') or code.startswith('30') or code.startswith('60')):
                        continue
                        
                    name = item["f14"]
                    price = item["f2"]         
                    change = item["f3"]        
                    turnover = item["f8"]      
                    vol_ratio = item["f10"]    
                    amplitude = item["f7"]     
                    super_inflow = item["f64"] 
                    mkt_cap = item["f116"]     
                    
                    if not isinstance(change, (int, float)): continue
                    if not isinstance(price, (int, float)): continue
                    if not isinstance(vol_ratio, (int, float)): vol_ratio = 0
                    if not isinstance(turnover, (int, float)): turnover = 0
                    if not isinstance(amplitude, (int, float)): amplitude = 0
                    if not isinstance(super_inflow, (int, float)): super_inflow = 0
                    if not isinstance(mkt_cap, (int, float)): mkt_cap = 0
                    
                    # 1. 绝对的避雷绞肉机
                    if "ST" in name or "退" in name or price < 3.0: 
                        continue
                    
                    # 2. 【核心优化】锁定黄金游资场：总市值严格卡在 30亿 到 300亿 之间
                    if not (30 * 100000000 <= mkt_cap <= 300 * 100000000): 
                        continue
                    
                    # 3. 反人性压盘过滤网：
                    # 涨跌幅：-4% ~ +5% (拒绝追高)
                    # 量比：> 1.5 (成交量必须温和放大，说明有人在默默建仓)
                    # 大单：必须有超大单正向流入
                    if (-4.0 <= change <= 5.0) and (super_inflow > 0) and (vol_ratio >= 1.5):
                        super_wan = round(super_inflow / 10000, 1) 
                        mkt_cap_yi = round(mkt_cap / 100000000, 1)
                        
                        # 背离打分：换手 * 超大单 * (10-涨幅)。跌得越多买得越凶，分越高
                        smart_money_score = super_wan * turnover * (10 - change)
                        
                        valid_stocks.append({
                            "name": name, 
                            "code": code,
                            "price": price,
                            "change": change, 
                            "vol_ratio": vol_ratio,
                            "super_wan": super_wan,
                            "mkt_cap_yi": mkt_cap_yi,
                            "score": smart_money_score
                        })
    except: pass

    valid_stocks.sort(key=lambda x: x["score"], reverse=True)
    return valid_stocks

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
# 数据处理
# ======================
with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
try:
    with open("hot_streak.json", "r", encoding="utf-8") as f: hot_streak = json.load(f)
except: hot_streak = {}
try:
    with open("history.json", "r", encoding="utf-8") as f: history = json.load(f)
except: history = []
history_set = set(history)

all_news = [] 
for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if isinstance(item, str): all_news.append({"title": item, "link": ""})
                elif isinstance(item, dict): all_news.append({"title": item.get("title", ""), "link": item.get("link", "")})
    except: pass

unique_news = {}
for news in all_news: unique_news[news["title"]] = news
all_news = list(unique_news.values())

new_news = [n for n in all_news if n["title"] not in history_set]
for news in new_news:
    get_translation(news["title"]) 

with open("trans_cache.json", "w", encoding="utf-8") as f:
    json.dump(trans_cache, f, ensure_ascii=False, indent=2)

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

# ======================
# V27 拼装：政策逻辑 + 纯资金暗盘逻辑
# ======================
header = "<b>【A股游资全息雷达 V27】</b>\n\n"
header += f"发现新政策/事件：{len(new_news)}条\n"
header += "✅ 锁定30亿-300亿游资猎场 | ✅ 无未来函数，纯Tick级暗盘\n\n"

message_body = ""

# --- 模块1：政策面驱动 ---
has_policy_content = False
for topic, info in sorted(result.items(), key=lambda x: x[1]["count"], reverse=True):
    topic_new_news = [n for n in new_news if any(a.lower() in n["title"].lower() for a in KEYWORDS.get(topic, []))]
    
    target_code = None
    for name, code in SECTOR_MAP.items():
        if any(a in name for a in [topic] + KEYWORDS.get(topic, [])):
            target_code = code
            break
            
    quant_stocks = auto_quant_stock_pick(target_code) if target_code else []
    
    if not topic_new_news and not quant_stocks:
        continue

    has_policy_content = True
    total_s, main_s, money_s, is_res, res_desc = calc_score(info["count"], hot_rank.get(topic, 0), hot_streak.get(topic, {}).get("streak", 0), topic, KEYWORDS.get(topic, []))
    
    stars = "★★★★★" if total_s >= 30 else ("★★★★" if total_s >= 15 else "★★★")
    message_body += f"<b>{stars} {topic} (政策驱动)</b>\n"
    if is_res: message_body += f"{res_desc}\n"
    message_body += f"🎯 综合评分：{total_s}分\n\n"

    if topic_new_news:
        message_body += "<b>📢 最新驱动：</b>\n"
        for news in topic_new_news[:3]:
            en_title = escape_html(news["title"])
            cn_title = escape_html(get_translation(news["title"]))
            link = escape_html(news.get("link", ""))
            if link and link.startswith("http"): message_body += f"• <a href='{link}'>{cn_title}</a>\n"
            else: message_body += f"• {cn_title}\n"
            if cn_title != en_title: message_body += f"  <i>└ {en_title}</i>\n"
        message_body += "\n"

    if quant_stocks:
        message_body += f"<b>💡 游资暗潜 (精选30-300亿市值)：</b>\n"
        for stock in quant_stocks[:3]:
            trend_hint = "💧跌盘强吸" if stock['change'] <= 0 else "🔥温和建仓"
            message_body += f"• <code>{stock['name']}</code> ({trend_hint} 涨:{stock['change']}%, 量比:{stock['vol_ratio']}, 暗盘:+{stock['super_wan']}万, 盘:{stock['mkt_cap_yi']}亿)\n"
        message_body += "\n"

    message_body += "--------------------\n\n"

# --- 模块2：纯资金暗流驱动 (无视消息面) ---
capital_sectors = get_top_capital_sectors(limit=2)
has_capital_content = False
capital_body = "<b>🦈 纯资金主线 (全网异动最高)</b>\n\n"

for sector in capital_sectors:
    quant_stocks = auto_quant_stock_pick(sector["code"])
    if quant_stocks:
        has_capital_content = True
        capital_body += f"<b>🔥 {sector['name']}</b> (涨幅 {sector['change']}%, 主力流入 {sector['inflow_yi']}亿)\n"
        for stock in quant_stocks[:3]:
            trend_hint = "💧逆势吃货" if stock['change'] <= 0 else "🔥右侧试盘"
            capital_body += f"• <code>{stock['name']}</code> ({trend_hint} 涨:{stock['change']}%, 量比:{stock['vol_ratio']}, 暗盘:+{stock['super_wan']}万, 盘:{stock['mkt_cap_yi']}亿)\n"
        capital_body += "\n"

if has_capital_content:
    message_body += capital_body + "--------------------\n\n"

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

# 无论有无内容，都发送消息（保证每次运行都有回音，解决你没收到消息的疑惑）
if has_policy_content or has_capital_content:
    final_message = header + message_body
    send_to_telegram(final_message)
else:
    # 增加心跳防守消息，让你明确知道程序活着，只是大盘太垃圾
    heartbeat_msg = "<b>【A股游资全息雷达 V27】</b>\n\n"
    heartbeat_msg += "🛡 <b>当前状态：大盘极度静默 / 情绪冰点</b>\n"
    heartbeat_msg += "• 政策面：无任何新增政策驱动\n"
    heartbeat_msg += "• 资金面：全市场未探测到符合安全边际（30-300亿）的机构压盘动作。\n"
    heartbeat_msg += "• 交易策略：<b>管住手，空仓防守，切勿被杂音骗炮。</b>"
    send_to_telegram(heartbeat_msg)

# ======================
# 落盘保存
# ======================
history.extend([n["title"] for n in new_news])
with open("history.json", "w", encoding="utf-8") as f: json.dump(history, f, ensure_ascii=False, indent=2)
with open("hot_rank.json", "w", encoding="utf-8") as f: json.dump(hot_rank, f, ensure_ascii=False, indent=2)
with open("hot_streak.json", "w", encoding="utf-8") as f: json.dump(hot_streak, f, ensure_ascii=False, indent=2)
