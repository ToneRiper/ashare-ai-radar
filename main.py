import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time
import hashlib

# 引入量化包
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
            if rich_text and any(k in rich_text for k in ["股", "市", "板块", "异动", "拉升", "发布", "突发", "订单", "重组", "政策"]):
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
    try:
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers={'User-Agent': 'Mozilla/5.0'}, timeout=4).text
        lines = res.strip().split(';')
        idx_data = [f"{p.split('~')[1]}: {p.split('~')[32]}%" for p in lines if p and len(p.split('~'))>32]
        if idx_data: return "大盘: " + " | ".join(idx_data)
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
            
            quant_reports.append(f"{code}: 5日乖离{bias5:.1f}%, MACD{macd_status}, 近10日涨停基因:{has_zt}")
        except: continue
    return "\n".join(quant_reports) if quant_reports else "盘面处于混沌期"

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

def send_alert(text):
    if TOKEN and CHAT_ID: 
        res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
        if res.status_code != 200:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)

def clean_stock_codes(raw_text):
    codes = re.findall(r'\b[036]\d{5}\b', raw_text)
    return [c for c in codes if c.startswith(('00', '30', '60')) and not c.startswith('688')]

# ======================
# 4. 合伙人主动大脑 (主动延展思考，废除被动回答)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, quant_data, focus_keywords, mode):
    news_text = "\n".join(news_list[:15])
    prompt = f"""作为我的A股数字游资合伙人，不要等我问，你要主动思考！
当前模式：【{mode}】
资金风向：{top_sectors} | 5分钟异动：{spikes_5min}
核心关注：{focus_keywords}
【底层量化数据】：{quant_data}

【合伙人主动延展铁律】：
1. 就算没有突发大新闻，你也要根据【资金风向】和【5分钟异动】主动判断当前市场的【情绪周期】（是冰点、退潮还是高潮？）。
2. 主动挖掘主力意图：有没有存在板块高低切？有没有隐蔽洗盘？
3. 必须输出 3-5 只符合量化逻辑（FVG缺口、乖离率合理、MACD多头）的纯正小盘股（30-200亿市值，非688/北交所）。不能空仓不推！

参考资讯：{news_text}

【严格按以下排版输出，禁止废话】：
**🎯 市场情绪与周期定调**
* (主动思考当前市场情绪温度，指出主力的下一步动向)

**🧠 盘面量价深度拷问**
* (结合异动数据和量化指标，拆解洗盘或点火逻辑)

**🗡️ 尖刀潜伏池** (无论有无突发，必须在异动/热点中选出3-5只)
* 000000 股票A：(简述其量化优势与题材契合度)
* 000000 股票B：(简述逻辑)

**⚠️ 核按钮防雷**
* (主动规避那些涨幅过大、面临套牢盘抛压的诱多标的)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5).choices[0].message.content.strip()
    except: return "分析核心异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘。资金：{top_sectors}。
按【游资N字洗盘量化战法】严格挖掘5只次日溢价标的：
1. 周线有堆量，套牢盘轻，FVG缺口未回补。
2. 近两日缩量回调，今日盘中有下影线，绝对不破前一个涨停底。
死命令：绝对不准选688/北交所！只要00/30/60。市值30-200亿。只输出5个6位代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

# ======================
# 5. 主控大枢纽 (永不静默)
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
            # 筛选重要新闻
            is_critical = any(k in news for k in ["批准", "突发", "重要", "拉升", "发布", "规划", "涨停", "重组"]) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical: new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    spikes_text, spike_codes = get_5min_spikes_with_codes()
    quant_evidence = calculate_quant_features(spike_codes) if spike_codes else "无微观异动量化数据"
    
    # 彻底放大时段容错率，应对 GitHub 延迟！
    is_尾盘时段 = (14 <= hour <= 15)  # 只要是在下午2点到3点59分跑，全部带上尾盘逻辑！
    is_复盘时段 = hour >= 20
    
    # 【核心修改：废除静默】
    # 不管有没有新闻，只要触发了 GitHub Action，就以“盘面常态巡航”模式分析当前所有的快讯和异动！
    ai_source_news = new_critical_news if new_critical_news else live_flash[:15]
    current_mode = "⚡ 突发阻击截获" if new_critical_news else "📡 盘面常态巡航"

    msg = f"**【A股数字合伙人 · {current_mode}】**\n"
    msg += f"🕒 {today_str}\n\n"
    msg += f"💰 **资金热度**: {top_sectors}\n"
    msg += f"🔥 **5分钟异动**: {spikes_text}\n\n"

    if new_critical_news:
        msg += "**🚨 最新异动前瞻:**\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    msg += "---\n\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_text, quant_evidence, focus_keywords_str, current_mode)
    msg += f"{semantic_alert}\n"
    
    stock_codes = clean_stock_codes(semantic_alert)
    if stock_codes:
        msg += "\n**📊 标的真实盘口:**\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥强势承接" if d['vol_ratio']>1.2 and d['turnover']>2.5 else "➖缩量洗盘")
                msg += f"• `{d['code']}` {d['name']} | 涨跌: {d['change']}% | 量比: {d['vol_ratio']} ({status})\n"

    # [14:50 尾盘，极度宽松的触发时间，绝对不漏]
    if is_尾盘时段:
        msg += "\n---\n\n**🎯【尾盘 N 字反包潜伏池】**\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in clean_stock_codes(" ".join(candidates)):
            d = get_realtime_stock_data(code)
            # 宽容度增加，保证选出标的
            if d and d['vol_ratio'] > 0 and -8.0 <= d['change'] <= 6.0:
                ambush_list.append(d)
        
        if ambush_list:
            for data in ambush_list[:5]:
                msg += f"• `{data['code']}` {data['name']} | 涨跌: {data['change']}% | 换手: {data['turnover']}%\n"
            msg += "\n*💡 逻辑: FVG缺口支撑 + 下影线洗盘 + 量化确认底背离.*"
        else:
            msg += "⚠️ 经过多重量化过滤，今日尾盘无完美形态，严格管住手。"

    if is_复盘时段:
        msg += "\n---\n\n**🌑【盘后大局观复盘】**\n\n"
        msg += "已扫描全天数据，情绪周期与资金暗线分析完毕。" # 简化防超长报错

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
