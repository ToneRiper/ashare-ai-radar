import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time
import hashlib

# 尝试导入量化包，如果没有则静默容错
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
# 2. 极速数据与量化计算引擎 
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=40&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ["股", "市", "板块", "概念", "异动", "拉升", "发布", "突发", "订单", "重组"]):
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
    """获取5分钟异动，并返回详细信息和股票代码列表"""
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=8&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).json()
        data = res.get('data', {}).get('diff', [])
        
        spikes_text = []
        codes = []
        for s in data:
            if s.get('f11') and s['f11'] > 1.2:
                # 屏蔽科创板和北交所
                if not str(s['f12']).startswith(('688', '8', '4')):
                    spikes_text.append(f"{s['f14']}(拉升{s['f11']}%)")
                    codes.append(str(s['f12']))
                    
        return " | ".join(spikes_text) if spikes_text else "无异常拉升", codes
    except: return "监控中", []

def calculate_quant_features(codes):
    """【V69 核心量化引擎】调用 AkShare 计算 K线指标"""
    if not HAS_QUANT or not codes: return "量化计算模块未激活或无异动代码"
    
    quant_reports = []
    for code in codes[:5]:  # 只算前5个最猛的，防止超时
        try:
            # 获取最近 30 个交易日的日 K 线
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 20: continue
            
            df = df.tail(20)
            close_price = df['收盘'].iloc[-1]
            
            # 1. 计算 5日均线及乖离率
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            # 2. 计算简易 MACD
            exp1 = df['收盘'].ewm(span=12, adjust=False).mean()
            exp2 = df['收盘'].ewm(span=26, adjust=False).mean()
            macd_line = exp1 - exp2
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = (macd_line - signal_line) * 2
            
            # 判定 MACD 状态
            if macd_line.iloc[-1] > 0 and macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0:
                macd_status = "水上金叉(极强)"
            elif macd_hist.iloc[-1] > 0:
                macd_status = "多头趋势"
            else:
                macd_status = "空头/洗盘"
                
            # 3. 判定涨停基因 (近10日是否有>9.5%的涨幅)
            recent_10 = df.tail(10)
            has_zt = "有" if recent_10['涨跌幅'].max() > 9.5 else "无"
            
            quant_reports.append(f"{code}: 5日乖离率{bias5:.1f}%, MACD{macd_status}, 近10日涨停基因:{has_zt}")
        except: continue
        
    return "\n".join(quant_reports) if quant_reports else "无符合条件的量化数据"

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
# 3. 去重与推送
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
    if TOKEN and CHAT_ID: 
        # 发送请求，如果失败打印错误日志（防止假死）
        res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
        if res.status_code != 200:
            # 如果 Markdown 解析报错，降级为普通文本重发
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)

def clean_stock_codes(raw_text):
    codes = re.findall(r'\b[036]\d{5}\b', raw_text)
    return [c for c in codes if c.startswith(('00', '30', '60')) and not c.startswith('688')]

# ======================
# 4. 游资量化大脑 (融合硬核数学指标)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, quant_data, focus_keywords, mode):
    news_text = "\n".join(news_list[:15])
    prompt = f"""你是顶级量化游资大脑。模式：【{mode}】
风向：{top_sectors} | 核心池：{focus_keywords}
【5分钟拉升】：{spikes_5min}
【后台计算好的量价数学证据(极度重要)】：
{quant_data}

【高阶量化选股铁律（违者严惩）】：
1. 交叉比对：快讯题材是否与上述量化证据中的活跃个股重合？
2. 数据判刑：如果你选的股票乖离率>10%，直接判定为“追高风险”予以排除。优先选择“MACD多头/水上金叉”且“有涨停基因”的票。
3. 必须推荐 4-5 只纯正小盘股（30-200亿），附带量化逻辑说明。

快讯情报：{news_text}

【严格按以下排版输出】：
**🎯 核心阵地研判**
* (结合新闻与量化证据，点出最强逻辑)

**🧠 深度量价拷问**
* (用FVG缺口、隐蔽洗盘手法、以及我提供的MACD和乖离率证据来拆解主力)

**🗡️ 尖刀潜伏池** * 000000 股票A：(说明其新闻题材 + 量化指标状态，例如：乖离率低+金叉)
* 000000 股票B：(说明逻辑)

**⚠️ 核按钮防雷**
* (指出乖离率过大或面临套牢盘的诱多方向)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content.strip()
    except: return "联动分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘潜伏。资金：{top_sectors}。
按【量化N字洗盘战法】严格挖掘5只次日溢价标的：
1. 周线级别有堆量吸筹，套牢盘轻。
2. 隐蔽洗盘：近两日缩量回调，今日收长下影线，绝对不破前一个涨停底。
选股死命令：绝对不准选688和北交所！只要00/30/60。市值30-200亿。只输出5个6位代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

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
    spikes_text, spike_codes = get_5min_spikes_with_codes()
    
    # 获取硬核量化数据！
    quant_evidence = calculate_quant_features(spike_codes) if spike_codes else "无"
    
    is_尾盘时段 = (hour == 14 or (hour == 15 and bjt_now.minute <= 30))
    is_复盘时段 = hour >= 20
    is_定点时段 = is_尾盘时段 or is_复盘时段 or (hour == 9 and bjt_now.minute >= 20)
    
    if not is_定点时段 and not new_critical_news:
        print("静默：无新重磅消息或非定点时段。")
        return

    ai_source_news = new_critical_news if new_critical_news else live_flash
    current_mode = "⚡ 量化突发截获" if (new_critical_news and not is_定点时段) else f"⏱️ 量化追踪({hour}:{bjt_now.minute})"

    msg = f"**【A股量化刺客 · {current_mode}】**\n"
    msg += f"🕒 {today_str}\n\n"
    msg += f"💰 **资金风向**: {top_sectors}\n"
    msg += f"🔥 **极速异动**: {spikes_text}\n\n"

    if new_critical_news:
        msg += "**🚨 重磅电报:**\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    msg += "---\n\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_text, quant_evidence, focus_keywords_str, current_mode)
    msg += f"{semantic_alert}\n"
    
    stock_codes = clean_stock_codes(semantic_alert)
    if stock_codes:
        msg += "\n**📊 盘口实测:**\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥承接强" if d['vol_ratio']>1.2 and d['turnover']>2.5 else "➖偏弱")
                msg += f"• `{d['code']}` {d['name']} | 涨跌: {d['change']}% | 量比: {d['vol_ratio']} ({status})\n"

    if is_尾盘时段:
        msg += "\n---\n\n**🎯【14:50 尾盘 N 字潜伏】**\n\n"
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
            msg += "\n*💡 逻辑: FVG缺口支撑 + 长下影缩量洗盘 + 量化金叉验证.*"
        else:
            msg += "⚠️ 过滤后未见完美形态，管住手。"

    if is_复盘时段:
        msg += "\n---\n\n**🌑【盘后深度复盘】**\n\n"
        msg += f"*(大盘概览与明日防雷策略生成中...)*\n"
        # 晚间复盘简化，避免篇幅超长被 Telegram 拦截

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
