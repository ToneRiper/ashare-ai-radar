import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time
import hashlib

# ======================
# 1. 核心配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")
GITHUB_PAGES_URL = "https://toneriper.github.io/ashare-ai-radar/"

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")
CACHE_FILE = "data/sent_news.json"

# ======================
# 2. 极速电报数据源 
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=40&top_id=152&type=0&dpc=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=8).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ["股", "市", "板块", "概念", "异动", "拉升", "发布", "突发", "订单", "重组"]):
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                flash_news.append(clean_text[:120])
    except: pass
    return flash_news

def get_top_sectors():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url1 = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url1, headers=headers, timeout=4).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        if result: return " | ".join(result)
    except: pass
    try:
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers=headers, timeout=4).text
        lines = res.strip().split(';')
        idx_data = [f"{p.split('~')[1]}: {p.split('~')[32]}%" for p in lines if p and len(p.split('~'))>32]
        if idx_data: return "大盘: " + " | ".join(idx_data)
    except: pass
    return "资金接口受限"

def get_5min_spikes():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f14,f3,f11"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        data = res.get('data', {}).get('diff', [])
        spikes = [f"{s['f14']}(拉升{s['f11']}%)" for s in data if s.get('f11') and s['f11'] > 1.5]
        return " | ".join(spikes) if spikes else "无异常拉升"
    except: return "监控中"

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

# ======================
# 3. 去重与物理屏蔽 
# ======================
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
    if SERVER_KEY: requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资刺客", "desp": text}, timeout=10)
    if TOKEN and CHAT_ID: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=15)

def clean_stock_codes(raw_text):
    """绝对封杀 688 和 北交所"""
    codes = re.findall(r'\b[036]\d{5}\b', raw_text)
    return [c for c in codes if c.startswith(('00', '30', '60')) and not c.startswith('688')]

# ======================
# 4. 游资高阶大脑 (量价心法注入 + 排版重构)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, focus_keywords, mode):
    news_text = "\n".join(news_list[:15])
    prompt = f"""你是顶级游资大脑，具有强大的量价结构推理能力。模式：【{mode}】
风向：{top_sectors} | 5分钟拉升：{spikes_5min} | 核心池：{focus_keywords}

【高阶选股铁律（违者严惩）】：
1. 物理条件：仅限00/30/60开头。市值30-200亿。剔除高价股、千亿盘、688和北交所。
2. 量价结构推演（必须在逻辑中体现）：
   - 屠龙刀/N字型：近期有过涨停，回踩不破底。
   - FVG缺口理论：判断该板块个股是否存在“第一根和第三根K线未回补的向上资金缺口（订单块）”。
   - 隐蔽洗盘：今日盘口必须是缩量且带有明显下影线的承接。
   - 避免未来函数：基于当前盘面已知事实，预判上方“套牢盘”是否已被清洗。

快讯情报：{news_text}

【严格按以下排版输出，拒绝冗长文字墙，多用短句和列表】：
**🎯 核心阵地研判**
* (一句话点出最强逻辑，及是否有资金共振)

**🧠 深度量价拷问**
* (用FVG缺口、洗盘手法、套牢盘等高阶逻辑拆解主力的真实意图)

**🗡️ 尖刀潜伏池** (给足4-5只纯正小盘股，格式如下)
* 000000 股票A：(简短说明其量价基因，如：周线堆量+涨停回踩不破)
* 000000 股票B：(简短说明其量价基因)

**⚠️ 核按钮防雷**
* (简短指出诱多或面临套牢盘抛压的方向)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content.strip()
    except: return "联动分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘潜伏。资金：{top_sectors}。
按【游资高阶N字洗盘战法】严格挖掘5只次日溢价标的：
1. 周线吸筹：近期周K线有明显的资金堆量。
2. 隐蔽洗盘：近两日缩量回调，今日收长下影线，绝对不破前一个涨停底，且上方套牢盘较轻。
3. FVG缺口：日线级别存在向上的未回补资金缺口支撑。
选股死命令：绝对不准选688和北交所！只要00/30/60。市值30-200亿，概念纯正。只输出5个6位代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:20])
    prompt = f"""大复盘。资金：{top_sectors}。
要求同上：禁推688/北交所，挖纯正小盘(30-200亿)。结合MACD和BOLL形态做复盘。
【严格排版】：
**宏观与情绪**
* (短句总结)

**主线战旗**
* 000000 股票A：(形态分析)

**暗线火种**
* 000000 股票B：(形态分析)

**明日避险**
* (退潮方向)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content.strip()
    except: return "复盘异常"

# ======================
# 5. 主控大枢纽 
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    focus_keywords_str = "、".join(KEYWORDS.keys())
    live_flash = get_live_flash_news()
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour

    processed_hashes = load_processed_hashes()
    new_critical_news = []
    
    for news in live_flash:
        news_hash = hashlib.md5(news.encode('utf-8')).hexdigest()
        if news_hash not in processed_hashes:
            processed_hashes.add(news_hash)
            is_critical = any(k in news for k in ["批准", "通过", "突发", "重要", "拉升", "发布", "规划", "涨停", "重组"]) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical: new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    spikes_5min = get_5min_spikes() if 9 <= hour <= 15 else "休市无异动"
    
    is_尾盘时段 = (hour == 14 or (hour == 15 and bjt_now.minute <= 30))
    is_复盘时段 = hour >= 20
    is_定点时段 = is_尾盘时段 or is_复盘时段 or (hour == 9 and bjt_now.minute >= 20)
    
    if not is_定点时段 and not new_critical_news:
        print("静默")
        return

    ai_source_news = new_critical_news if new_critical_news else live_flash
    current_mode = "⚡ 突发截获" if (new_critical_news and not is_定点时段) else f"⏱️ 追踪({hour}:{bjt_now.minute})"

    # --- 采用全新清爽排版输出 ---
    msg = f"**【A股刺客雷达 · {current_mode}】**\n"
    msg += f"🕒 {today_str}\n\n"
    msg += f"💰 **资金风向**: {top_sectors}\n"
    msg += f"🔥 **极速异动**: {spikes_5min}\n\n"

    if new_critical_news:
        msg += "**🚨 重磅电报:**\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    msg += "--- \n\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_5min, focus_keywords_str, current_mode)
    msg += f"{semantic_alert}\n"
    
    stock_codes = clean_stock_codes(semantic_alert)
    if stock_codes:
        msg += "\n**📊 盘口实测:**\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥承接强" if d['vol_ratio']>1.2 and d['turnover']>2.5 else "➖偏弱")
                msg += f"• `{d['code']}` {d['name']} | 涨跌: {d['change']}% | 量比: {d['vol_ratio']} ({status})\n"

    # [14:50 尾盘]
    if is_尾盘时段:
        msg += "\n--- \n\n**🎯【14:50 尾盘 N 字潜伏】**\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in clean_stock_codes(" ".join(candidates)):
            d = get_realtime_stock_data(code)
            if d and d['vol_ratio'] > 0 and -6.0 <= d['change'] <= 5.0 and d['turnover'] > 2.0:
                ambush_list.append(d)
        
        msg += "**🚨 严选蓄力池 (剔除大票/科创):**\n"
        if ambush_list:
            for data in ambush_list[:5]:
                msg += f"• `{data['code']}` {data['name']} | 涨跌: {data['change']}% | 换手: {data['turnover']}%\n"
            msg += "\n*💡 逻辑: FVG缺口支撑 + 长下影缩量洗盘 + 套牢盘轻.*"
        else:
            msg += "⚠️ 过滤后未见完美形态，管住手。"

    # [晚间复盘]
    if is_复盘时段:
        msg += "\n--- \n\n**🌑【盘后深度复盘】**\n\n"
        review = get_daily_review(ai_source_news, top_sectors)
        msg += f"{review}\n\n"
        codes_night = clean_stock_codes(review)
        if codes_night:
            msg += "**📊 数据穿透:**\n"
            for code in list(dict.fromkeys(codes_night))[:5]:
                d = get_realtime_stock_data(code)
                if d: msg += f"• `{d['code']}` {d['name']} | 涨跌: {d['change']}%\n"

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
