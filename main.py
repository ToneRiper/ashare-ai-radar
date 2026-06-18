import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time

# ======================
# 1. 核心配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

# ======================
# 2. 强力破壁数据引擎 
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=60&version=1.2.4"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=8).json()
        items = res.get('result', {}).get('data', [])
        for item in items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content and any(k in full_content for k in ["股", "市", "板块", "概念", "会", "政策", "公告", "产业", "部委"]):
                flash_news.append(full_content[:100])
    except: pass
    return flash_news

def get_top_sectors():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url1 = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url1, headers=headers, timeout=4).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        if result: return " | ".join(result)
    except: pass
    try:
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers=headers, timeout=4).text
        lines = res.strip().split(';')
        idx_data = [f"{p.split('~')[1]}: {p.split('~')[32]}%" for p in lines if p and len(p.split('~'))>32]
        if idx_data: return "大盘风向: " + " | ".join(idx_data)
    except: pass
    return "全网节点拦截，切换至盲打推演"

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
# 3. 推送引擎 (纯净 Markdown)
# ======================
def send_alert(text):
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": text}, timeout=10)
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=15)

# ======================
# 4. 游资大脑核心 AI 引擎
# ======================
def get_semantic_intraday_alert(core_news, top_sectors, keywords):
    news_text = "\n".join(core_news[:25])
    prompt = f"""你是A股游资。资金风向：{top_sectors}。关注领域：{keywords}。
线索：{news_text}
【铁律】：
1. 必须提炼2条核心情报并做逻辑拷问（为什么发？诱多还是真突破？）。
2. 给 3-5 只 50-300亿 市值活跃标的（带6位代码）。绝对禁推千亿大盘股。
格式：
【核心情报与拷问】
【尖刀标的】(代码 名字)
【盘中防雷区】"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6).choices[0].message.content.strip()
    except: return "动态分析异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""现在是14:50尾盘潜伏。资金风向：{top_sectors}。
请严格按以下【游资N字反包战法】条件，挖掘 5 只潜力妖股：
1. 【涨停基因】近一周内（最好2-3天前）必须有过明确涨停板。
2. 【强支撑】近两日处于回调，但绝对没有跌破前一个涨停板的最低价（最好回踩5日/10日线）。
3. 【洗盘量能】回调期间总体缩量，且绝对无跌停。
4. 【题材共振】必须属于当前热门主线。
5. 【市值要求】50-300亿之间，绝不碰死水股。
不准废话，只输出5个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(core_news, top_sectors):
    news_text = "\n".join(core_news[:30])
    prompt = f"""晚上盘后大复盘。资金：{top_sectors}。线索：{news_text}。
【铁律】：复盘宏观情绪；主暗线各挖3-5只(50-300亿)标的(带代码)。
格式：
【宏观与情绪周期】
【主线逻辑与标的】
【暗线火种与标的】
【明日防雷退潮区】"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6).choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 雷达调度中枢
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

    top_sectors = get_top_sectors()
    
    msg = f"【A股战术雷达】 {today_str}\n\n"
    msg += f"💰 资金风向：{top_sectors}\n\n"

    # [常规模块：每天每次运行都有，保证新闻和股票推荐不空缺]
    msg += "🧠 盘中逻辑拷问与推演：\n"
    semantic_alert = get_semantic_intraday_alert(live_flash, top_sectors, focus_keywords_str)
    msg += f"{semantic_alert}\n\n"
    
    stock_codes_daily = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes_daily:
        msg += "📊 推演标的实时盘口：\n"
        for code in list(dict.fromkeys(stock_codes_daily))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🔥抢筹" if d['vol_ratio'] > 1.5 else ("⚠️死水" if d['turnover'] < 1.0 else "➖洗盘")
                msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 换手:{d['turnover']}% | 量比:{d['vol_ratio']} ({status})\n"

    # [14:50 尾盘狙击模块]
    if hour == 14:
        msg += "\n" + "="*20 + "\n\n🎯【14:50 极限洗盘潜伏狙击】\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            d = get_realtime_stock_data(code)
            if d and d['vol_ratio'] > 0:
                # 过滤掉涨停的，寻找缩量回调或分歧承接的
                if d['change'] < 5.0 and d['turnover'] > 3.0: 
                    ambush_list.append(d)
        
        if ambush_list:
            msg += "🚨 N字反包/缩量不破底标的：\n"
            for data in ambush_list[:5]:
                msg += f" • {data['name']}({data['code']}) | 涨跌:{data['change']}% | 换手:{data['turnover']}% | 量比:{data['vol_ratio']}\n"
            msg += "💡 逻辑：近一周有涨停基因，今日缩量企稳不破底，换手活跃，博弈次日资金记忆回流反包。"
        else:
            msg += "⚠️ 未扫描到完美符合【涨停回调不破底】特征的标的，管住手。"

    # [20:00 晚间复盘模块]
    if hour >= 20:
        msg += "\n" + "="*20 + "\n\n🌑【守夜人：极致盘后大复盘】\n"
        review = get_daily_review(live_flash, top_sectors)
        msg += f"{review}\n\n"
        codes_night = re.findall(r'\b[036]\d{5}\b', review)
        if codes_night:
            msg += "📊 盘口验证：\n"
            for code in list(dict.fromkeys(codes_night))[:5]:
                d = get_realtime_stock_data(code)
                if d: msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"

    send_alert(msg)

if __name__ == "__main__":
    run_radar()
