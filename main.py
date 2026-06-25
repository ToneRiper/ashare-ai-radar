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
# 2. 强力破壁与微观异动引擎 
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        # 扩大抓取量到 80 条，不再漏掉任何新闻
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=80&version=1.2.4"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=8).json()
        for item in res.get('result', {}).get('data', []):
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content and any(k in full_content for k in ["股", "市", "板块", "概念", "异动", "拉升", "走强", "涨停", "批准", "突发"]):
                flash_news.append(full_content[:150]) # 放宽字数限制，保留更多信息
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
        if idx_data: return "上证/深证/创业板: " + " | ".join(idx_data)
    except: pass
    return "接口受限，已激活AI反推"

def get_5min_spikes():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f14,f3,f11"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=4).json()
        data = res.get('data', {}).get('diff', [])
        spikes = [f"{s['f14']}(5分拉升:{s['f11']}%, 现涨:{s['f3']}%)" for s in data if s.get('f11') and s['f11'] > 1.5]
        return " | ".join(spikes) if spikes else "当前无明显垂直拉升异动"
    except:
        return "5分钟异动数据监控中..."

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
# 3. 去重与推送中枢
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
    full_text = text + f"\n\n🌐 点击查看大屏: {GITHUB_PAGES_URL}"
    if SERVER_KEY: requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资刺客", "desp": full_text}, timeout=10)
    if TOKEN and CHAT_ID: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": full_text, "disable_web_page_preview": True}, timeout=15)

def generate_dashboard(topic_counts, review_text, today_str):
    labels = list(topic_counts.keys())
    data_values = list(topic_counts.values())
    pie_data = [{"value": val, "name": name} for val, name in zip(data_values, labels)]
    pie_data_str = json.dumps(pie_data, ensure_ascii=False)
    html_content = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>游资暗潜雷达</title><script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script><style>body{{background-color:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:20px;}} .container{{display:flex;flex-wrap:wrap;gap:20px;}} .card{{background:#1e293b;border-radius:12px;padding:20px;flex:1;min-width:300px;}} pre{{white-space:pre-wrap;color:#cbd5e1;line-height:1.6;}}</style></head><body><h2>📊 A股联动全透大屏 (V67)</h2><p>更新时间：{today_str}</p><div class="container"><div class="card"><h2>🔥 产业链热力图</h2><div id="chart" style="width:100%;height:400px;"></div></div><div class="card" style="flex:2;"><pre>{review_text if review_text else "暂无推演"}</pre></div></div><script>var chart=echarts.init(document.getElementById('chart'));chart.setOption({{tooltip:{{}},series:[{{type:'pie',radius:['40%','70%'],data:{pie_data_str}}}]}});</script></body></html>"""
    try:
        with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)
    except: pass

# ======================
# 4. 游资大脑核心 AI 引擎 (反人性重构版)
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, spikes_5min, focus_keywords, mode):
    # 扩大送给 AI 的新闻量，让它能进行板块级聚类
    news_text = "\n".join(news_list[:35]) 
    prompt = f"""你是A股反人性游资。模式：【{mode}】。
宏观资金：{top_sectors}
【极短期微观异动】：最近5分钟全市场爆拉个股：{spikes_5min}
核心监控库：{focus_keywords}

【终极排雷与过滤铁律】(如违反直接视为失败)：
1. 绝对剔除千亿市值大白马（如工业富联、中芯国际等），只能在 50亿-300亿 之间找票。
2. 绝对剔除近期已经连续大涨、处于高位加速阶段的票，寻找“低位首板起爆”或“洗盘后长下影线”的标的。
3. 把全网新闻按板块归类，提取最强的一条主线进行逻辑拷问。如果新闻吹的票没有出现在5分钟异动里，直接判定为“嘴炮诱多”。

快讯池：{news_text}

严格输出格式：
【主线资金联动】(提取新闻中真正有资金在打火点火的板块)
【刀尖深度拷问】(反人性剖析：散户看到了什么，主力实际在干什么)
【绝对尖刀标的】(格式：代码 名字，强制50-300亿市值，给足4只)
【盘中防雷警示】(指出高位滞涨或即将被核按钮的方向)"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content.strip()
    except: return "联动分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘。资金风向：{top_sectors}。
按【N字反包战法】挖5只潜力妖股。
【铁律】：
1. 市值严格限制 50亿-300亿 之间。
2. 近一周内有过涨停，近两日处于缩量回调。
3. 今日必须有下影线承接，且绝对未跌破前一个涨停板的最低价。
只输出5个6位代码，逗号隔开，不要任何废话。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

def get_daily_review(news_list, top_sectors, focus_keywords):
    news_text = "\n".join(news_list[:40])
    prompt = f"""晚上大复盘。重点看这堆新闻：{news_text}。资金：{top_sectors}。
【铁律】：
1. 必须涵盖核心库：{focus_keywords}。
2. 禁推大盘股，只推50-300亿的。

格式：
【宏观情绪大局观】
【主线逻辑与标的】(带代码，50-300亿)
【暗线火种与标的】(带代码，50-300亿)
【防雷避险区】"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 主控融合大枢纽
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    focus_keywords_str = "、".join(KEYWORDS.keys())
    
    all_file_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    for item in reversed(json.load(f)):
                        t = item if isinstance(item, str) else item.get("title", "")
                        if t: all_file_news.append(t)
            except: pass

    live_flash = get_live_flash_news()
    
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour

    # --- 增量去重拦截 ---
    processed_hashes = load_processed_hashes()
    new_critical_news = []
    
    for news in live_flash:
        news_hash = hashlib.md5(news.encode('utf-8')).hexdigest()
        if news_hash not in processed_hashes:
            processed_hashes.add(news_hash)
            # 只要包含哪怕一个核心词或者异动词，都算新情报
            is_critical = any(k in news for k in ["批准", "通过", "突发", "拉升", "暴涨", "异动", "主力", "封板"]) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical: new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    spikes_5min = get_5min_spikes() if 9 <= hour <= 15 else "非交易时段无微观异动"
    
    # 彻底废除分钟级锁定，只认小时。GitHub延迟再严重，也不可能拖过一个小时。
    # 早盘9点段、尾盘14点段（兼容拖延到15点的情况）、晚盘20点以后。
    is_定点 = (hour == 9) or (hour in [14, 15]) or (hour >= 20)
    
    # 彻底废除静默退出。现在不管有没有新消息，只要执行就必须发大盘播报，当作“心跳存活证明”。
    ai_source_news = new_critical_news if new_critical_news else (live_flash + all_file_news)
    current_mode = "⚡ 盘中特发突发刺客" if (new_critical_news and not is_定点) else f"⏱️ 时段定点追踪({hour}点档)"

    msg = f"【A股刺客雷达 · {current_mode}】\n更新时间：{today_str}\n\n"
    msg += f"💰 资金风向：{top_sectors}\n"
    msg += f"🔥 5分钟极速异动：{spikes_5min}\n\n"

    # [早盘 9 点档竞价模块]
    if hour == 9:
        msg += "🎯【早盘竞价与开盘盯盘】\n结合隔夜发酵与早盘异动进行排雷推演...\n\n"

    if new_critical_news and not is_定点:
        msg += "🚨 截获突发线索：\n"
        for n in new_critical_news[:4]: msg += f"• {n}\n"
        msg += "\n"

    msg += "🧠 游资大脑【联动研判】：\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, spikes_5min, focus_keywords_str, current_mode)
    dashboard_text = semantic_alert
    msg += f"{semantic_alert}\n"
    
    stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes:
        msg += "\n📊 标的盘口验证：\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥强势抢筹" if d['vol_ratio']>1.4 and d['turnover']>3 else "➖洗盘震荡")
                msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']} ({status})\n"
    msg += "\n" + "="*20 + "\n\n"

    # [尾盘潜伏模块：兼容 14点和15点运行，防止 GitHub 延迟错过]
    if hour in [14, 15]:
        msg += "🎯【极限洗盘潜伏狙击 (N字反包)】\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            d = get_realtime_stock_data(code)
            # 严格过滤：涨幅不能超，要有换手托底
            if d and d['vol_ratio'] > 0 and -8.0 <= d['change'] <= 4.0 and d['turnover'] > 2.0:
                ambush_list.append(d)
        
        msg += "🚨 严选缩量不破底核心池：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                msg += f" • {data['name']}({data['code']}) | 涨跌:{data['change']}% | 换手:{data['turnover']}% | 量比:{data['vol_ratio']}\n"
            msg += "\n💡 逻辑：近一周有涨停，今日承接企稳不破底，博弈次日回流反包。"
        else:
            msg += "⚠️ 扫描全市场，未发现完美符合【涨停回调不破底+市值50-300亿】特征的标的，当前管住手，不盲目潜伏。\n"
        msg += "\n" + "="*20 + "\n\n"

    # [晚间大复盘模块]
    if hour >= 20 or hour < 8: # 兼容拖到凌晨才跑完的情况
        msg += "🌑【守夜人：极致盘后大复盘战报】\n\n"
        review = get_daily_review(ai_source_news, top_sectors, focus_keywords_str)
        dashboard_text = review
        msg += f"{review}\n\n"
        codes_night = re.findall(r'\b[036]\d{5}\b', review)
        if codes_night:
            msg += "📊 盘后数据穿透：\n"
            for code in list(dict.fromkeys(codes_night))[:6]:
                d = get_realtime_stock_data(code)
                if d: msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"

    send_alert(msg)
    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_file_news if any(a.lower() in n.lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
    generate_dashboard(topic_counts, dashboard_text, today_str)

if __name__ == "__main__":
    run_radar()
