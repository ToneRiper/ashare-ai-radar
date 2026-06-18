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
# 2. 强力破壁与增量去重引擎
# ======================
def get_live_flash_news():
    flash_news = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=60&version=1.2.4"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=8).json()
        items = res.get('result', {}).get('data', [])
        for item in items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content and any(k in full_content for k in ["股", "市", "板块", "概念", "会", "政策", "公告", "产业", "异动", "拉升", "走强", "涨停", "批准", "通过", "突发"]):
                flash_news.append(full_content[:100])
    except: pass
    return flash_news

def get_top_sectors():
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/122.0.0.0', 'Referer': 'http://quote.eastmoney.com/'}
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
    return "接口受限，已激活【AI快讯反推资金流】"

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
# 3. 去重状态中枢
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

# ======================
# 4. 统一推送
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看大屏: {GITHUB_PAGES_URL}"
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资刺客内参", "desp": full_text}, timeout=10)
    if TOKEN and CHAT_ID:
        payload = {"chat_id": CHAT_ID, "text": full_text, "disable_web_page_preview": True}
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=15)

def generate_dashboard(topic_counts, review_text, today_str):
    labels = list(topic_counts.keys())
    data_values = list(topic_counts.values())
    pie_data = [{"value": val, "name": name} for val, name in zip(data_values, labels)]
    pie_data_str = json.dumps(pie_data, ensure_ascii=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN"><head><meta charset="UTF-8"><title>游资暗潜雷达</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>body{{background-color:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:20px;}} .container{{display:flex;flex-wrap:wrap;gap:20px;}} .card{{background:#1e293b;border-radius:12px;padding:20px;flex:1;min-width:300px;}} pre{{white-space:pre-wrap;color:#cbd5e1;line-height:1.6;}}</style></head>
    <body><h2>📊 A股瞬时高透决策大屏 (V65)</h2><p>更新时间：{today_str}</p>
    <div class="container"><div class="card"><h2>🔥 产业链热力图</h2><div id="chart" style="width:100%;height:400px;"></div></div>
    <div class="card" style="flex:2;"><pre>{review_text if review_text else "暂无突发事件推演"}</pre></div></div>
    <script>var chart=echarts.init(document.getElementById('chart'));chart.setOption({{tooltip:{{}},series:[{{type:'pie',radius:['40%','70%'],data:{pie_data_str}}}]}});</script></body></html>
    """
    try:
        with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)
    except: pass

# ======================
# 5. AI 大脑核心
# ======================
def get_semantic_intraday_alert(news_list, top_sectors, focus_keywords, mode="盘中突发"):
    news_text = "\n".join(news_list[:20])
    prompt = f"""你是A股顶尖短线游资。当前运行模式：【{mode}】。资金风向：{top_sectors}。关注清单：{focus_keywords}。
请对以下最新突发快讯进行字字见血的跨级推演。

【死命令】：
1. 深度拷问：主力为什么现在放这个消息？这是掩护出货（诱多）、高低切，还是真突破点火？
2. 强制选股：必须推荐 4-5 只 50亿-300亿 市值、股性极度活跃、有连板基因的对应先锋个股，严禁推千亿大盘股！

快讯：
{news_text}

格式：
【AI反推资金眼】提炼当前快讯中资金最亢奋、正在拉升流入的细分方向。
【刀尖深度拷问】一针见血剖析主力的做多野心或设下的诱多圈套。
【主力资金共振】该消息是否能得到市场真金白银方向的支持。
【狙击尖刀标的】(格式：代码 名字，必须给足4-5只活跃小盘票)
【盘中防雷警示】指出今天或明天坚决不能碰、可能遭遇核按钮退潮的方向。"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5).choices[0].message.content.strip()
    except: return "动态分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘潜伏。资金：{top_sectors}。
严格按【N字反包战法】（近一周有涨停、近两日缩量回调不破涨停最低价、无跌停、换手活跃、50-300亿市值）挖掘5只潜力活跃妖股。只输出5个6位代码，逗号隔开。"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.4).choices[0].message.content
        return re.findall(r'\b[036]\d{5}\b', res)
    except: return []

def get_daily_review(news_list, top_sectors, keywords):
    news_text = "\n".join(news_list[:35])
    prompt = f"""晚上大复盘。线索：{news_text}。资金：{top_sectors}。聚焦领域：{keywords}。
格式：
【宏观大局观】政策定调与情绪周期。
【主线战旗】逻辑拷问与5只标的(50-300亿含代码)。
【暗线火种】产业链发酵与5只标的(50-300亿含代码)。
【异动冷思考】分析异常板块。
【明日防雷区】退潮方向。"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5).choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 6. 主控融合大枢纽
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    focus_keywords_str = "、".join(KEYWORDS.keys())
    
    # 获取基础离线文件数据
    all_file_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    for item in reversed(json.load(f)):
                        t = item if isinstance(item, str) else item.get("title", "")
                        if t: all_file_news.append(t)
            except: pass

    # 获取实时最新快讯
    live_flash = get_live_flash_news()
    
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour
    minute = bjt_now.minute

    # --- 核心：增量去重拦截机制 ---
    processed_hashes = load_processed_hashes()
    new_critical_news = []
    
    for news in live_flash:
        news_hash = hashlib.md5(news.encode('utf-8')).hexdigest()
        if news_hash not in processed_hashes:
            processed_hashes.add(news_hash)
            # 筛选：如果是高能词汇（红头、通过、突发、异动拉升），或者是自选核心领域，列为突发高值新闻
            is_critical = any(k in news for k in ["批准", "通过", "突发", "重要决定", "国常会", "拉升", "暴涨"]) or \
                          any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values())
            if is_critical:
                new_critical_news.append(news)
                
    save_processed_hashes(processed_hashes)

    top_sectors = get_top_sectors()
    
    # 判断当前触发状态
    is_定点时段 = (hour == 9 and 20 <= minute <= 35) or (hour == 14 and 45 <= minute <= 59) or (hour >= 20)
    
    # 策略路由：如果没有定点任务，且今天运行没有抓到任何“全新的未处理重磅头条”，直接静默退出，不发无用信息。
    if not is_定点时段 and not new_critical_news:
        print("盘中巡逻：未截获全新重磅消息，雷达保持静默。")
        return

    # 确定本次 AI 分析的数据源
    ai_source_news = new_critical_news if (new_critical_news and not is_定点时段) else (live_flash + all_file_news)
    current_mode = "⚡ 盘中特发突发刺客" if (new_critical_news and not is_定点时段) else f"⏱️ 时段定点追踪({hour}:{minute})"

    msg = f"【A股刺客雷达 · {current_mode}】\n更新时间：{today_str}\n\n"
    msg += f"💰 盘面实时风向：\n{top_sectors}\n\n"

    if new_critical_news and not is_定点时段:
        msg += "🚨 截获全网首发重磅头条：\n"
        for n in new_critical_news[:3]: msg += f"• {n}\n"
        msg += "\n"

    # 运行日常穿透
    msg += "🧠 游资大脑深层剖析与拷问：\n"
    semantic_alert = get_semantic_intraday_alert(ai_source_news, top_sectors, focus_keywords_str, current_mode)
    dashboard_text = semantic_alert
    msg += f"{semantic_alert}\n"
    
    # 行情穿透验证
    stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes:
        msg += "\n📊 涉及个股真实盘口：\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            d = get_realtime_stock_data(code)
            if d:
                status = "🛑停牌" if d['vol_ratio']==0 else ("🔥活跃" if d['vol_ratio']>1.4 and d['turnover']>3 else "➖洗盘")
                msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']} ({status})\n"
    msg += "\n" + "="*20 + "\n\n"

    # [叠加时段 1：14:50 尾盘潜伏]
    if hour == 14 and 45 <= minute <= 59:
        msg += "🎯【14:50 极限洗盘潜伏狙击】\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            d = get_realtime_stock_data(code)
            if d and d['vol_ratio'] > 0 and -8.0 <= d['change'] <= 4.0 and d['turnover'] > 2.5:
                ambush_list.append(d)
        
        msg += "🚨 N字反包/缩量不破底核心池（严选）：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                msg += f" • {data['name']}({data['code']}) | 跌幅:{data['change']}% | 换手:{data['turnover']}% | 量比:{data['vol_ratio']}\n"
        else:
            for code in ["002230", "300033", "002415"]:
                d = get_realtime_stock_data(code)
                if d: msg += f" • [备选风向标] {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"
        msg += "\n" + "="*20 + "\n\n"

    # [叠加时段 2：晚间大复盘]
    if hour >= 20:
        msg += "🌑【守夜人：极致盘后大复盘战报】\n\n"
        review = get_daily_review(ai_source_news, top_sectors, focus_keywords_str)
        dashboard_text = review
        msg += f"{review}\n\n"
        codes_night = re.findall(r'\b[036]\d{5}\b', review)
        if codes_night:
            msg += "📊 复盘个股盘口量价：\n"
            for code in list(dict.fromkeys(codes_night))[:6]:
                d = get_realtime_stock_data(code)
                if d: msg += f" • {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"

    send_alert(msg)
    topic_counts = {} # 保持大屏幕切片正常
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_file_news if any(a.lower() in n.lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
    generate_dashboard(topic_counts, dashboard_text, today_str)

if __name__ == "__main__":
    run_radar()
