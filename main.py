import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import hashlib

try:
    import pandas as pd
    import akshare as ak
    HAS_QUANT = True
except ImportError:
    HAS_QUANT = False

# ======================
# 1. 核心配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")  # 新增飞书配置
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")
CACHE_FILE = "data/sent_news.json"

# ======================
# 2. 极速数据与量化引擎
# ======================
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "涨停", "利好"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌"]
CORE_WORDS = ["股", "市", "板块", "融资", "期指", "央行"]
ALL_MONITOR_WORDS = BULL_WORDS + BEAR_WORDS + CORE_WORDS

def get_live_flash_news():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=40&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ALL_MONITOR_WORDS):
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                prefix = "[⚠️利空]" if any(b in clean_text for b in BEAR_WORDS) else ("[🔥利好]" if any(b in clean_text for b in BULL_WORDS) else "[📰快讯]")
                flash_news.append(f"{prefix} {clean_text[:120]}")
    except: pass
    return flash_news

def get_top_sectors():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        if result: return " | ".join(result)
    except: pass
    return "接口受限"

def get_5min_spikes_with_codes():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        data = res.get('data', {}).get('diff', [])
        
        spikes_text = []
        codes = []
        for s in data:
            if s.get('f11') and s['f11'] > 1.2:
                if not str(s['f12']).startswith(('688', '8', '4')):
                    spikes_text.append(f"{s['f12']}{s['f14']}(拉升{s['f11']}%)")
                    codes.append(str(s['f12']))
        return " | ".join(spikes_text) if spikes_text else "无显著异动", codes
    except: return "监控中", []

def calculate_quant_features(codes):
    if not HAS_QUANT or not codes: return "暂无量化数据"
    quant_reports = []
    for code in codes[:8]: 
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 20: continue
            df = df.tail(20)
            close_price = df['收盘'].iloc[-1]
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            exp1 = df['收盘'].ewm(span=12, adjust=False).mean()
            exp2 = df['收盘'].ewm(span=26, adjust=False).mean()
            macd_line = exp1 - exp2
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = (macd_line - signal_line) * 2
            
            macd_status = "水上金叉" if (macd_line.iloc[-1] > 0 and macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0) else ("多头" if macd_hist.iloc[-1] > 0 else "空头")
            recent_10 = df.tail(10)
            has_zt = "有" if recent_10['涨跌幅'].max() > 9.5 else "无"
            
            quant_reports.append(f"[{code}] 5日乖离:{bias5:.1f}%, MACD:{macd_status}, 涨停基因:{has_zt}")
        except: continue
    return "\n".join(quant_reports) if quant_reports else "盘面混沌"

def get_realtime_stock_data(stock_code):
    code = re.sub(r'\D', '', str(stock_code))
    if len(code) != 6: return None
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    try:
        res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=4).text.split('~')
        if len(res) > 49:
            return {"name": res[1], "code": code, "change": float(res[32]), "vol_ratio": float(res[49]), "turnover": float(res[38])}
    except: pass
    return None

def load_processed_hashes():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: return set(json.load(f))
        except: return set()
    return set()

def save_processed_hashes(hashes):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f: json.dump(list(hashes), f, ensure_ascii=False)
    except: pass

def send_alert(text):
    # 1. 飞书推送 (极速直接推)
    if FEISHU_WEBHOOK:
        try:
            requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": text.replace('*', '').replace('_', '')}}, timeout=10)
        except Exception as e:
            print(f"飞书推送失败: {e}")

    # 2. Telegram 切片推送 (防止超长被拦截)
    if TOKEN and CHAT_ID: 
        max_length = 3800
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for part in parts:
            try:
                res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
                if res.status_code != 200:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)
            except Exception as e:
                print(f"Telegram推送失败: {e}")

def clean_stock_codes(raw_text):
    codes = re.findall(r'\b[036]\d{5}\b', raw_text)
    return [c for c in codes if c.startswith(('00', '30', '60')) and not c.startswith('688')]

# ======================
# 4. 游资全息主动大脑 (军情标签化排版 + 杜绝假代码)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, quant_data, focus_keywords, mode):
    news_text = "\n".join(news_list[:10])
    prompt = f"""你是游资指挥官。禁止写万字长文，用最精简的【军事情报标签流】汇报！
风向：{top_sectors} | 核心库：{focus_keywords}
真实异动池：{spikes_5min}
量价证据：{quant_data}
快讯：{news_text}

【铁律1：绝不捏造代码】：你推荐的股票必须且只能从上方的【真实异动池】和【量价证据】中提取！绝不允许出现类似 XXX 这样的假代码。选不出就不推，宁缺毋滥！
【铁律2：军情排版】：绝不要散文。个股分析必须按标签化格式（严格限制20字内），强制分散在2-3个不同题材。

【严格按此格式输出】：
**🎯 阵地大局观**
* (一句话总结周期与主力情绪，如：高标退潮，资金高低切入半导体)

**🚨 雷区预警**
* (一句话指出利空发酵区或中位股绞杀风险)

**🗡️ 异动尖刀池 (2-4只)**
* `代码` 股票名称 [所属题材] | 亮点: FVG缺口+多头 | 抛压: 较轻
* `代码` 股票名称 [所属题材] | 亮点: 周线堆量+涨停基因 | 抛压: 中等"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.2).choices[0].message.content.strip()
    except: return "分析异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘。风向：{top_sectors}。
挖掘2-4只次日溢价标的。
条件：分散题材、周线堆量、FVG缺口、缩量不破底。
死命令：限00/30/60开头。市值30-200亿。只输出6位真实代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.2).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:20])
    prompt = f"""盘后复盘。禁止写小作文，采用军情极简标签流！
今日快讯：{news_text}

【铁律】：拒绝长篇大论！选股必须从真实市场逻辑出发，推荐3-5只，强制分散题材。单只股票分析不超过20字。

【严格排版】：
**🌑 盘面全维透视**
* (一句话拆解龙虎榜/暗线/衍生品风险)

**⚠️ 核按钮梳理**
* (一句话总结今日踩踏重灾区)

**🔥 次日备选阵地 (3-5只)**
* `代码` 股票名称 [所属题材] | 核心: FVG支撑+洗盘结束 | 风险: 大盘拖累
* (继续列举...)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.2).choices[0].message.content.strip()
    except: return "复盘异常"

# ======================
# 5. 主控大枢纽 
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    live_flash = get_live_flash_news()
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%m-%d %H:%M") # 精简时间显示
    hour = bjt_now.hour

    processed_hashes = load_processed_hashes()
    new_critical_news = []
    
    for news in live_flash:
        news_hash = hashlib.md5(news.encode('utf-8')).hexdigest()
        if news_hash not in processed_hashes:
            processed_hashes.add(news_hash)
            is_critical = any(k in news for k in ALL_MONITOR_WORDS) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical: new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    spikes_text, spike_codes = get_5min_spikes_with_codes()
    quant_evidence = calculate_quant_features(spike_codes) if spike_codes else "无异动"
    
    is_尾盘时段 = (14 <= hour <= 15)  
    is_复盘时段 = hour >= 20
    
    ai_source_news = new_critical_news if new_critical_news else live_flash[:10]
    
    if new_critical_news and any("[⚠️利空]" in n for n in new_critical_news):
        current_mode = "🚨 雷区预警"
    elif new_critical_news:
        current_mode = "⚡ 情报截获"
    else:
        current_mode = "📡 常态巡航"

    # 全新极简排版界面
    msg = f"**【游资合伙人 · {current_mode}】** ({today_str})\n"
    msg += f"风向: {top_sectors}\n"
    msg += f"异动: {spikes_text}\n\n"

    if new_critical_news:
        msg += "**📢 核心快讯:**\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    msg += "---\n"
    focus_keywords_str = "、".join(KEYWORDS.keys())
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_text, quant_evidence, focus_keywords_str, current_mode)
    msg += f"{semantic_alert}\n"
    
    stock_codes = clean_stock_codes(semantic_alert)
    if stock_codes:
        msg += "\n**📊 盘口实测:**\n"
        for code in list(dict.fromkeys(stock_codes))[:4]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑" if d['vol_ratio']==0 else ("🔥" if d['vol_ratio']>1.2 and d['turnover']>2.5 else "➖")
                msg += f"`{d['code']}` {d['name']} | 涨跌:{d['change']}% | 量:{d['vol_ratio']} {status}\n"

    if is_尾盘时段:
        msg += "\n---\n**🎯【尾盘 N 字博弈池】**\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in clean_stock_codes(" ".join(candidates)):
            d = get_realtime_stock_data(code)
            if d and d['vol_ratio'] > 0 and -8.0 <= d['change'] <= 6.0:
                ambush_list.append(d)
        
        if ambush_list:
            for data in ambush_list[:4]:
                msg += f"`{data['code']}` {data['name']} | 涨跌:{data['change']}% | 换手:{data['turnover']}%\n"
        else:
            msg += "⚠️ 过滤后无完美形态，空仓观望。"

    if is_复盘时段:
        msg += "\n---\n**🌑【盘后全维复盘】**\n"
        review_content = get_daily_review(ai_source_news, top_sectors)
        msg += f"{review_content}\n"

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
