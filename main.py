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
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")
CACHE_FILE = "data/sent_news.json"

# ======================
# 2. 极速数据与量化引擎 
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=40&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ["股", "市", "板块", "异动", "拉升", "发布", "突发", "订单", "重组", "政策", "融资", "期指"]):
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                flash_news.append(clean_text[:120])
    except: pass
    return flash_news

def get_top_sectors():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        if result: return " | ".join(result)
    except: pass
    return "资金接口受限"

def get_5min_spikes_with_codes():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=8&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        data = res.get('data', {}).get('diff', [])
        
        spikes_text = []
        codes = []
        for s in data:
            if s.get('f11') and s['f11'] > 1.2:
                if not str(s['f12']).startswith(('688', '8', '4')):
                    spikes_text.append(f"{s['f14']}(拉升{s['f11']}%)")
                    codes.append(str(s['f12']))
        return " | ".join(spikes_text) if spikes_text else "无极端拉升", codes
    except: return "监控中", []

def calculate_quant_features(codes):
    if not HAS_QUANT or not codes: return "暂无量化数据支撑"
    quant_reports = []
    for code in codes[:5]: 
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
            
            if macd_line.iloc[-1] > 0 and macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0:
                macd_status = "水上金叉"
            elif macd_hist.iloc[-1] > 0:
                macd_status = "多头"
            else:
                macd_status = "洗盘/空头"
                
            recent_10 = df.tail(10)
            has_zt = "有" if recent_10['涨跌幅'].max() > 9.5 else "无"
            quant_reports.append(f"{code}: 5日乖离{bias5:.1f}%, MACD{macd_status}, 近10日涨停:{has_zt}")
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
    if TOKEN and CHAT_ID: 
        res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
        if res.status_code != 200:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)

def clean_stock_codes(raw_text):
    codes = re.findall(r'\b[036]\d{5}\b', raw_text)
    return [c for c in codes if c.startswith(('00', '30', '60')) and not c.startswith('688')]

# ======================
# 4. 游资全息主动大脑 (自我进化与多维融合)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, quant_data, focus_keywords, mode):
    news_text = "\n".join(news_list[:15])
    prompt = f"""你是具备独立思考与跨界算力的顶级游资合伙人。你不仅要用我教你的逻辑，还要用你自己的高阶量化认知来帮我避坑选股。
模式：【{mode}】 | 风向：{top_sectors} | 异动：{spikes_5min} | 硬核指标：{quant_data}

【合伙人主动算力指令】：
1. 你的主动思考维度（必须融入分析）：
   - 跨市场嗅觉：结合大盘情况，预判是否存在“现货拉升掩护期指空单”的衍生品挤压风险？
   - 绞杀陷阱判断：当前板块异动是龙头启动，还是高潮末期的“中位股诱多绞杀”？
   - 资金底牌：去排查异动个股的量价，有没有Level-2拆单骗炮嫌疑？有没有融资盘踩踏风险？
2. 选股死命令：必须推荐 5-8 只最优标的，且强制分散在至少 3 个完全不同的板块！只准要00/30/60开头，30-200亿市值。
3. 对每一只推荐的票，写明它的【高阶死穴拆解】（包含：FVG缺口、套牢盘密度、主力缩量洗盘动作、以及中位股风险排查）。

参考快讯：{news_text}

【严格排版】：
**🎯 市场全息定调 (衍生品与情绪跨界视角)**
* (主动输出：情绪处于什么周期？是否存在期指贴水或杠杆踩踏风险？主力在玩什么把戏？)

**🔥 多维分散尖刀池 (精选5-8只，强制跨界3个题材)**
* `代码` 股票名称 | 所属板块
  - 【全息死穴拆解】：(结合周线堆量、日线FVG缺口、套牢盘压力、撤单骗炮风险排查)
  - 【实战潜伏点】：(核心买入逻辑)
* (继续列出，确保分散)

**⚠️ 绝对禁区 (高潮中位股与爆仓雷区)**
* (主动指出哪些标的或板块正处于“中位股绞杀”阶段，坚决防核)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5).choices[0].message.content.strip()
    except: return "分析核心异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘。资金风向：{top_sectors}。
挖掘5-8只次日溢价标的，执行最高级别多维过滤：
1. 题材强制分散在3个不同板块。
2. 形态：周线堆量，存在日线向上FVG缺口。
3. 你的主动排雷：绝对不碰处于连续阴跌且融资余额极高（面临爆仓踩踏）的票；绝对不碰量比畸高但无下影线承接的票。
要求：只要00/30/60。市值30-200亿。只输出6位代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""收盘大复盘。严禁留白，必须全量输出干货！资金：{top_sectors}。
今日全网快讯：{news_text}

【合伙人复盘铁律】：
1. 用你的大局观：不要只读报纸，分析今天的龙虎榜协同效应（游资和机构是在合力还是在互相出货？）、微盘股流动性抽血效应。
2. 选股：挑选 5-8 只纯血小盘股（30-200亿，限00/30/60）。必须分散在至少 3 个题材。
3. 穿透拆解：每只票都必须带上【周线堆量】、【FVG缺口位置】、【套牢盘压力区】以及【洗盘/杠杆风险】的综合点评。

【严格排版】：
**🌑 盘后全维度周期透视**
* (深度拆解资金暗线、衍生品溢出效应与龙虎榜协同逻辑)

**🔥 次日备战跨界分散池 (5-8只)**
* `代码` 股票名称 | 题材板块
  - 【多维结构解剖】：(FVG缺口、套牢盘、融资盘踩踏预警、洗盘质量)
  - 【明日博弈点】：(实战预期)
* (继续列举...)

**⚠️ 绞杀阵地防核指南**
* (指出当前的高潮退潮区、中位股陷阱和散户接盘重灾区)"""
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
            is_critical = any(k in news for k in ["批准", "突发", "拉升", "发布", "规划", "涨停", "重组", "融资", "爆仓", "期指"]) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical: new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    spikes_text, spike_codes = get_5min_spikes_with_codes()
    quant_evidence = calculate_quant_features(spike_codes) if spike_codes else "无异动数据"
    
    is_尾盘时段 = (14 <= hour <= 15)  
    is_复盘时段 = hour >= 20
    
    ai_source_news = new_critical_news if new_critical_news else live_flash[:15]
    current_mode = "⚡ 突发截获与全息穿透" if new_critical_news else "📡 盘面全维常态巡航"

    msg = f"**【A股数字合伙人 · {current_mode}】**\n"
    msg += f"🕒 {today_str}\n\n"
    msg += f"💰 **资金热度**: {top_sectors}\n"
    msg += f"🔥 **5分钟异动**: {spikes_text}\n\n"

    if new_critical_news:
        msg += "**🚨 异动与跨市场雷达:**\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    msg += "---\n\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_text, quant_evidence, focus_keywords_str, current_mode)
    msg += f"{semantic_alert}\n"
    
    stock_codes = clean_stock_codes(semantic_alert)
    if stock_codes:
        msg += "\n**📊 推荐池实时盘口量化验证:**\n"
        for code in list(dict.fromkeys(stock_codes))[:8]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥强势抢筹" if d['vol_ratio']>1.2 and d['turnover']>2.5 else "➖缩量洗盘/诱多嫌疑")
                msg += f"• `{d['code']}` {d['name']} | 涨跌: {d['change']}% | 量比: {d['vol_ratio']} ({status})\n"

    if is_尾盘时段:
        msg += "\n---\n\n**🎯【尾盘 N 字反包极致严选池】**\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in clean_stock_codes(" ".join(candidates)):
            d = get_realtime_stock_data(code)
            if d and d['vol_ratio'] > 0 and -8.0 <= d['change'] <= 6.0:
                ambush_list.append(d)
        
        if ambush_list:
            msg += "**🚨 尾盘跨题材严选筹码 (过滤杠杆踩踏/中位陷阱):**\n"
            for data in ambush_list[:8]:
                msg += f"• `{data['code']}` {data['name']} | 涨跌: {data['change']}% | 换手: {data['turnover']}%\n"
            msg += "\n*💡 终极过滤: 跨越至少3题材分散 + FVG公允缺口支撑 + 避开融资盘密集区.*"
        else:
            msg += "⚠️ 经过全息量化与风控过滤，今日尾盘无完美形态，管住手。"
        msg += "\n" + "="*20 + "\n\n"

    if is_复盘时段:
        msg += "\n---\n\n**🌑【守夜人 · 盘后极致大复盘战报】**\n\n"
        review_content = get_daily_review(ai_source_news, top_sectors)
        msg += f"{review_content}\n\n"
        
        codes_night = clean_stock_codes(review_content)
        if codes_night:
            msg += "**📊 复盘池量价数据底线:**\n"
            for code in list(dict.fromkeys(codes_night))[:8]:
                d = get_realtime_stock_data(code)
                if d: msg += f"• `{d['code']}` {d['name']} | 当前价: {d['change']}% | 换手: {d['turnover']}%\n"

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
