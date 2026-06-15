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
# 百度翻译接入 + 强制并发限流
# ======================
def baidu_translate(query):
    if not BAIDU_APP_ID or not BAIDU_SECRET_KEY:
        print("未配置百度 API Key，跳过百度翻译")
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
        else:
            print(f"百度翻译接口返回异常: {res}")
    except Exception as e:
        print(f"百度翻译请求网络异常: {e}")
    return None

def safe_translate(text):
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        return text
    
    bd_res = baidu_translate(text)
    if bd_res:
        return bd_res
        
    try:
        return GoogleTranslator(source="auto", target="zh-CN").translate(text)
    except:
        pass
        
    try:
        return MyMemoryTranslator(source="en", target="zh-CN").translate(text)
    except Exception as e:
        print(f"全线翻译失败: {e}")
        return text

# ======================
# 东财实时数据抓取 (增加延迟容忍度)
# ======================
def fetch_eastmoney_hot_sectors():
    sectors = {}
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f14,f3,f62"
        # 延长到 20 秒，防跨洋超时
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            try:
                res = r.json()
                if res and "data" in res and res["data"]:
                    for item in res["data"]["diff"]:
                        sectors[item["f14"]] = {"change": item["f3"], "inflow": item["f62"]}
            except ValueError:
                print("板块抓取被东财拦截")
    except Exception as e:
        print(f"板块抓取网络异常: {e}")
    return sectors

HOT_SECTORS = fetch_eastmoney_hot_sectors()

def fetch_mid_low_stocks(stock_names):
    if not stock_names:
        return []
    
    secids = []
    for name in stock_names:
        try:
            encoded_name = urllib.parse.quote(name)
            search_url = f"https://searchapi.eastmoney.com/api/suggest/get?input={encoded_name}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
            r = requests.get(search_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                try:
                    search_res = r.json()
                    if search_res.get("QuotationCodeTable") and search_res["QuotationCodeTable"].get("Data"):
                        code = search_res["QuotationCodeTable"]["Data"][0]["Code"]
                        prefix = "1" if code.startswith("6") else "0"
                        secids.append(f"{prefix}.{code}")
                except ValueError:
                    pass
        except:
            continue
            
    if not secids:
        return []

    valid_stocks = []
    try:
        secids_str = ",".join(secids)
        quote_url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids_str}&fields=f12,f14,f3"
        # 延长到 20 秒
        r = requests.get(quote_url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            try:
                quote_res = r.json()
                if quote_res and "data" in quote_res and quote_res["data"]:
                    for item in quote_res["data"]["diff"]:
                        name = item["f14"]
                        change = item["f3"]
                        if isinstance(change, (int, float)) and 1.0 <= change <= 6.0:
                            valid_stocks.append({"name": name, "change": change})
            except ValueError:
                print("个股行情被拦截")
    except Exception as e:
        print(f"个股行情请求异常: {e}")

    valid_stocks.sort(key=lambda x: x["change"], reverse=True)
    return valid_stocks

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
                inflow_yi = round(inflow / 100000000, 2)
                resonance_desc = f"[🚀 资金共振: {sector_name} 涨 {change}% | 流入 {inflow_yi}亿]"
            break
            
    return round(main_score + money_score, 1), main_score, round(money_score, 1), is_resonance, resonance_desc

# ======================
# 加载基础库
# ======================
with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
with open("watchlist.json", "r", encoding="utf-8") as f: WATCHLIST = json.load(f)
with open("stock_pool.json", "r", encoding="utf-8") as f: STOCK_POOL = json.load(f)

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
print(f"总数据：{len(all_news)} | 新增政策：{len(new_news)}")

# 执行翻译
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

message = "<b>【A股AI超级雷达 V20】</b>\n\n"
message += f"新增政策：{len(new_news)}条\n"
message += "✅ 百度机器翻译联机 | ✅ 双向容错降级推送\n\n"

for topic, info in sorted(result.items(), key=lambda x: x[1]["total_score"], reverse=True):
    stars = "★★★★★" if info["total_score"] >= 30 else ("★★★★" if info["total_score"] >= 15 else "★★★")
    message += f"<b>{stars} {topic}</b>\n"
    if info["is_resonance"]: message += f"{info['resonance_desc']}\n"
    message += f"🎯 综合评分：{info['total_score']}分 (主线{info['main_score']} | 资金{info['money_score']})\n\n"

    message += "<b>政策精选：</b>\n"
    for news in info["news_list"]:
        en_title = news["title"].replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
        cn_title = translated_titles.get(news["title"], news["title"]).replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
        link = news.get("link", "").replace("&", "&amp;")
        
        if link and link.startswith("http"):
            message += f"• <a href='{link}'>{cn_title}</a>\n"
        else:
            message += f"• {cn_title}\n"
            
        if cn_title != en_title:
            message += f"  <i>└ {en_title}</i>\n"
    message += "\n"

    if topic in STOCK_POOL:
        mid_low_stocks = fetch_mid_low_stocks(STOCK_POOL[topic])
        message += "<b>资金跟涨/低位潜伏：</b>\n"
        if mid_low_stocks:
            for stock in mid_low_stocks[:4]:
                message += f"• <code>{stock['name']}</code> (涨幅: {stock['change']} %)\n"
        else:
            message += "• 暂无符合 [1%~6%] 涨幅区间的蓄势标的\n"

    message += "\n--------------------\n\n"

# ======================
# Telegram 安全发送模块 (防静默失败)
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
            print(f"Telegram 消息发送成功 (模式: {parse_mode})")
        else:
            print(f"Telegram 发送失败！状态码: {res.status_code}, 返回: {res.text}")
            # 如果 HTML 模式被拒，剥离格式降级为纯文本重发
            if parse_mode == "HTML":
                print(">> 尝试降级为无格式纯文本重发...")
                # 简单清洗 HTML 标签，防止纯文本也看着乱
                clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
                send_to_telegram(clean_text, parse_mode=None)
    except Exception as e:
        print(f"Telegram 请求完全失败: {e}")

send_to_telegram(message)

# ======================
# 落盘保存
# ======================
history.extend([n["title"] for n in new_news])
with open("history.json", "w", encoding="utf-8") as f: json.dump(history, f, ensure_ascii=False, indent=2)
with open("hot_rank.json", "w", encoding="utf-8") as f: json.dump(hot_rank, f, ensure_ascii=False, indent=2)
with open("hot_streak.json", "w", encoding="utf-8") as f: json.dump(hot_streak, f, ensure_ascii=False, indent=2)
with open("trend.json", "w", encoding="utf-8") as f: json.dump(trend, f, ensure_ascii=False, indent=2)
