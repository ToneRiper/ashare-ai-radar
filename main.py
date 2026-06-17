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
GITHUB_PAGES_URL = "https://toneriper.github.io/ashare-ai-radar/"

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

# ======================
# 2. 强力破壁引擎 (双重备用源 + 浏览器伪装)
# ======================
def get_live_flash_news():
    """实时抓取全市场最新快讯，扩大抓取量稀释单一板块"""
    flash_news = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=40&version=1.2.4"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=8).json()
        items = res.get('result', {}).get('data', [])
        for item in items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content:
                if any(k in full_content for k in ["股", "市", "板块", "概念", "发行", "涨", "跌", "会", "政策", "公告", "产业", "部委"]):
                    flash_news.append(full_content[:80])
    except: pass
    return flash_news

def get_top_sectors():
    """带备用引擎的资金面获取，东财被封自动切新浪"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0'}
    
    # [引擎1] 东方财富资金流向
    for attempt in range(2):
        try:
            url1 = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
            res = requests.get(url1, headers=headers, timeout=5).json()
            sectors = res['data']['diff']
            result = [f"[{s['f14']}] 涨:{s['f3']}%(流入:{s['f62']/100000000:.1f}亿)" for s in sectors if s.get('f14')]
            if result: return " | ".join(result)
        except: time.sleep(1)
        
    # [引擎2] 新浪财经行业涨幅榜 (底层正则解析，无视API加密)
    try:
        url2 = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=6&sort=changeratio&asc=0&node=new_blhy&symbol=&_s_r_a=init"
        res = requests.get(url2, headers=headers, timeout=5).text
        matches = re.findall(r'name:"([^"]+)".*?changeratio:"([^"]+)"', res)
        if matches:
            result = [f"[{name}] 涨幅:{float(change):.1f}%" for name, change in matches]
            return " | ".join(result) + " (启用备用新浪节点)"
    except: pass
    
    return "资金网关受限，已启动盲打推演模式"

def get_realtime_stock_data(stock_code):
    code = re.sub(r'\D', '', str(stock_code))
    if not code or len(code) != 6: return None
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    headers = {'User-Agent': 'Mozilla/5.0'}
    for attempt in range(2):
        try:
            url = f"http://qt.gtimg.cn/q={prefix}{code}"
            res = requests.get(url, headers=headers, timeout=5)
            data = res.text.split('~')
            if len(data) > 49:
                return {
                    "name": data[1], "code": code,
                    "change": float(data[32]), "vol_ratio": float(data[49]),
                    "turnover": float(data[38])
                }
        except: time.sleep(1)
    return None

# ======================
# 3. 推送与大屏
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": full_text}, timeout=10)
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": full_text, "disable_web_page_preview": True}
        requests.post(tg_url, json=payload, timeout=15)

def generate_dashboard(topic_counts, review_text, today_str):
    labels = list(topic_counts.keys())
    data_values = list(topic_counts.values())
    pie_data = [{"value": val, "name": name} for val, name in zip(data_values, labels)]
    pie_data_str = json.dumps(pie_data, ensure_ascii=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="google" content="notranslate">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>游资暗潜雷达 - 决策大屏</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            body {{ background-color: #0f172a; color: #e2e8f0; font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; }}
            .header {{ text-align: center; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }}
            .header h1 {{ color: #38bdf8; margin: 0; }}
            .container {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); flex: 1; min-width: 300px; max-width: 600px; }}
            .card h2 {{ color: #fbbf24; border-bottom: 2px solid #fbbf24; padding-bottom: 10px; margin-top: 0; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 15px; line-height: 1.6; color: #cbd5e1; }}
            #chart {{ width: 100%; height: 400px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 A股高维全透决策大屏 (V59)</h1>
            <p>实时更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 宏观与产业链热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 核心推演与战报分析</h2>
                <pre>{review_text if review_text else "数据异常，请检查接口"}</pre>
            </div>
        </div>
        <script>
            var chart = echarts.init(document.getElementById('chart'));
            var option = {{ tooltip: {{ trigger: 'item' }}, series: [{{ name: '热度', type: 'pie', radius: ['40%', '70%'], itemStyle: {{ borderRadius: 10, borderColor: '#1e293b', borderWidth: 2 }}, label: {{ color: '#e2e8f0', fontSize: 14 }}, data: {pie_data_str} }}] }};
            chart.setOption(option);
        </script>
    </body>
    </html>
    """
    try:
        with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)
    except: pass

# ======================
# 4. 游资大脑核心 AI 引擎 (植入三大铁律)
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors, focus_keywords):
    news_text = "\n".join(latest_news_list[:30])
    prompt = f"""你是A股顶尖黑客游资。结合快讯与今日资金面({top_sectors})进行推演。

【游资三大铁律强制执行】：
1. 严禁偏科！必须从快讯中挖掘至少 2 个不同维度的机会（覆盖我们的核心清单：{focus_keywords}）。
2. 深度拷问：是启动期、高潮期还是退潮期？主力是在借利好出货，还是底部拿先手？
3. 必须推荐标的！严禁推千亿市值巨头。只准推 50-300亿 之间、近期活跃、有资金记忆的先锋股，共计 4-5 只。

快讯内容：
{news_text}

严格输出格式：
【核心线索提炼】总结最具爆发力或宏观定调的快讯。
【刀尖深度拷问】字字见血，直切资金野心，拷问其背后的真实周期与真实意图。
【主力资金共振】利好板块是否与今日真金白银方向一致。
【尖刀潜伏个股】(老少搭配，必须带代码，格式：000001 平安银行)
【盘中防雷警示】指出当前可能面临被“核按钮”的退潮板块。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "动态分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""现在是14:50尾盘。主力资金主攻：{top_sectors}。
请挖掘 10 只存在“洗盘诱空、放量大绿柱、仙人指路”特征的标的。
市值50-300亿，绝对禁推超级权重，必须是活跃游资票。只输出10个6位代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors, focus_keywords):
    news_text = "\n".join(news_list[:40])
    prompt = f"""晚上大复盘。新闻：{news_text}。资金：{top_sectors}。
【铁律】：
1. 涵盖宏观大事及核心清单({focus_keywords})，不偏科！
2. 禁推千亿大票；主暗线各挖5只(50-300亿)活跃小盘代码。

格式：
【宏观大局观】政策定调，情绪周期（冰点/高潮）拆解。
【主线战旗】刀尖级逻辑拷问。核心标的(5只，含代码)：
【暗线火种】产业链发酵联想。核心标的(5只，含代码)：
【异动冷思考】暴捶洗盘或超预期背后的真实主力逻辑。
【明日防雷区】坚决不碰的退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 雷达融合调度大中枢
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    focus_keywords_str = "、".join(KEYWORDS.keys())

    all_news = []
    titles_only = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in reversed(data): 
                        title = item if isinstance(item, str) else item.get("title", "")
                        if title: 
                            all_news.append({"title": title})
                            titles_only.append(title)
            except: pass

    live_flash = get_live_flash_news()
    titles_only = live_flash + titles_only  

    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    current_hour = bjt_now.hour

    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    top_sectors = get_top_sectors()
    
    final_message = f"【A股刺客雷达 · 全视网】 {today_str}\n\n"
    final_message += f"💰 实时资金风向：\n{top_sectors}\n\n"

    final_message += "📡 快讯前沿阵地侦察：\n"
    for title in titles_only[:4]:
         final_message += f"- {title}\n"
         
    final_message += "\n🧠 游资大脑深层推演：\n"
    semantic_alert = get_semantic_intraday_alert(titles_only, top_sectors, focus_keywords_str)
    dashboard_display_text = semantic_alert 
    final_message += f"{semantic_alert}\n"
    
    stock_codes_daily = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes_daily:
        final_message += "\n📊 标的盘口与筹码穿透：\n"
        for code in list(dict.fromkeys(stock_codes_daily))[:5]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                # 停牌及死水股智能排雷
                if real_data['vol_ratio'] == 0 and real_data['turnover'] == 0:
                    status = "🛑停牌/无交易"
                elif real_data['vol_ratio'] > 1.5 and real_data['turnover'] > 3.0:
                    status = "🔥抢筹活跃"
                elif real_data['turnover'] < 1.0:
                    status = "⚠️死水换手"
                else:
                    status = "➖主力锁仓"
                final_message += f" • {real_data['name']}({code}) | 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"
                
    final_message += "\n" + "="*20 + "\n\n"

    # --- 14:50 尾盘附加 ---
    if current_hour == 14:
        final_message += "🎯【14:50 尾盘洗盘异动狙击】\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                # 排除停牌股，寻找真实承接
                if real_data['vol_ratio'] > 0 and -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        final_message += "🚨 诱空洗筹/大绿柱承接标的：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                final_message += f" • {data['name']}({data['code']}) | 跌幅:{data['change']}% | 换手:{data['turnover']}% | <b>量比:{data['vol_ratio']}</b>\n"
            final_message += "\n💡 量化反人性逻辑：大环境不差且放量收绿，排除钝刀子割肉，多为强庄极限洗筹，博弈次日资金回流反包。"
            dashboard_display_text += "\n\n【14:50 尾盘量化监控已触发，详见推送】" 
        else:
            forced_seeds = ["002230", "300033", "002415"] 
            for code in forced_seeds:
                d = get_realtime_stock_data(code)
                if d and d['vol_ratio'] > 0: 
                    final_message += f" • [备选风向] {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"
        final_message += "\n" + "="*20 + "\n\n"

    # --- 20:00 晚间附加 ---
    if current_hour >= 20:
        final_message += "🌑【守夜人：极致盘后大复盘】\n\n"
        review_text = get_daily_review(titles_only, top_sectors, focus_keywords_str)
        dashboard_display_text = review_text 
        final_message += f"{review_text}\n\n"
        
        stock_codes_night = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes_night:
            final_message += "📊 复盘标的盘口量价：\n"
            for code in list(dict.fromkeys(stock_codes_night))[:8]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖潜伏"
                    final_message += f" • {real_data['name']}({code}) 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"

    send_alert(final_message)
    generate_dashboard(topic_counts, dashboard_display_text, today_str)

if __name__ == "__main__":
    run_radar()
