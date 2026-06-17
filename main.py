import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta

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
# 2. 7x24小时全市场快讯与真金白银数据引擎
# ======================
def get_live_flash_news():
    """实时抓取全市场最新快讯(平替财联社电报)"""
    flash_news = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=20&version=1.2.4"
        res = requests.get(url, timeout=5).json()
        items = res.get('result', {}).get('data', [])
        for item in items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content:
                if any(k in full_content for k in ["股", "市", "板块", "概念", "发行", "上涨", "下跌", "会议", "论坛", "政策", "公告", "公司", "产业"]):
                    flash_news.append(full_content[:80])
    except: pass
    return flash_news

def get_top_sectors():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=8&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, timeout=5).json()
        sectors = res['data']['diff']
        result = []
        for s in sectors:
            name = s['f14']
            change = s['f3']
            net_inflow = s['f62'] / 100000000 if s['f62'] else 0
            result.append(f"[{name}] {change}%({net_inflow:.1f}亿)")
        return " | ".join(result)
    except:
        return "资金数据获取异常"

def get_realtime_stock_data(stock_code):
    code = re.sub(r'\D', '', str(stock_code))
    if not code or len(code) != 6: return None
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    try:
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        res = requests.get(url, timeout=5)
        data = res.text.split('~')
        if len(data) > 49:
            return {
                "name": data[1], "code": code,
                "change": float(data[32]), "vol_ratio": float(data[49]),
                "turnover": float(data[38])
            }
    except: pass
    return None

# ======================
# 3. 推送中枢
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
            <h1>📊 A股全视野决策大屏 (V56)</h1>
            <p>实时更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日全网情报热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 实时核心战报与异动推演</h2>
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
# 4. 游资大脑核心 AI 引擎
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list[:20])
    prompt = f"""你是A股独狼游资大佬。拒绝任何外交辞令。基于以下最新一线电报快讯与今日资金面({top_sectors})进行跨级跨题材联想。

【死命令限制】：
1. 必须优先捕捉宏观金融大会（如陆家嘴论坛、国常会、央行定调）、部委/地方前沿破局动作。
2. 必须深度拷问：主力资金在借这个消息做什么暗线？是高位出逃还是低位建仓？为什么选这个时点爆出来？
3. 必须推荐标的！严禁推几千亿的大盘股。死死锁住市值 50亿-300亿 之间、股性妖辣、有主升浪基因的活跃游资票，给出 4-5 只。

快讯内容：
{news_text}

严格按以下格式输出，不要废话：
【核心线索提炼】一句话总结最具突袭价值或定调级别的快讯本质。
【游资深度拷问】直切资金野心，拷问其背后不为人知的做多方向或诱多圈套。
【主力资金共振】点明该题材是否与今日主力真金白银攻击的板块相吻合。
【尖刀潜伏个股】(格式：代码 股票名称，例如: 000001 平安银行)"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return response.choices[0].message.content.strip()
    except: return "动态分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""现在是14:50尾盘。今日主力资金主攻：{top_sectors}。
请利用主力洗盘形态和数据背离行为，在当前热点及近期妖股中，挖掘 10 只存在“假摔诱空、大绿柱放量承接、仙人指路”特征的标的。
市值绝对限制在 50-300 亿，必须近期拿过涨停，极度活跃。只输出10个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:35])
    prompt = f"""晚上9点大复盘。全天新闻汇总：{news_text}。资金主攻：{top_sectors}。
【铁律】：全盘复盘今日国家级/地方重点事件长远逻辑；绝对不碰千亿大票；主线暗线各挖5只(50-300亿)活跃小盘代码。

格式：
【宏观大局观】政策/论坛精神拆解，情绪周期定调。
【主线战旗】深度拷问。核心潜力股(5只，名字+代码)：
【暗线火种】产业链跨级联想。核心潜力股(5只，名字+代码)：
【异动冷思考】分析今日表现最诡异/暴捶洗盘的板块。
【避险防雷】明天坚决不碰、可能遭遇核按钮的退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 雷达全功能融合调度大中枢
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

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

    # 强力并入全市场 7x24 实时电报快讯
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
    
    # 构建基础全视野推送主体
    final_message = f"【A股刺客雷达 · 全视高透网】 {today_str}\n\n"
    final_message += f"💰 当前主力真金白银方向：\n{top_sectors}\n\n"

    final_message += "📡 盘中前沿线索侦察：\n"
    for title in titles_only[:4]:
         final_message += f"- {title}\n"
         
    final_message += "\n🧠 游资大脑情报联想与拷问：\n"
    semantic_alert = get_semantic_intraday_alert(titles_only, top_sectors)
    
    # 【核心改动】：将白天的深度分析也保存，用于填补大屏右侧的空白！
    dashboard_display_text = semantic_alert 
    
    final_message += f"{semantic_alert}\n"
    
    stock_codes_daily = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes_daily:
        final_message += "\n📊 精选狙击标的实时盘口：\n"
        for code in list(dict.fromkeys(stock_codes_daily))[:5]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                status = "高能抢筹" if real_data['vol_ratio'] > 1.4 else "强庄锁仓"
                final_message += f" • {real_data['name']}({code}) | 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"
                
    final_message += "\n" + "="*20 + "\n\n"

    # --- 阶段叠加 1：尾盘狙击 ---
    if current_hour == 14:
        final_message += "🎯【特设时段：14:50 尾盘洗盘个股狙击】\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        final_message += "🚨 尾盘放量洗筹/分歧承接核心标的：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                final_message += f" • {data['name']}({data['code']}) | 跌幅:{data['change']}% | 换手:{data['turnover']}% | 量比:{data['vol_ratio']}\n"
            final_message += "\n💡 量化反行为逻辑：热门板块核心标的，分歧收绿大绿柱，但量能承接明显放大。博弈其次日弱转强反包高开。"
            dashboard_display_text += "\n\n【14:50 尾盘量化监控】\n捕获到强力洗盘标的，详情请查阅 Telegram 推送。" # 在大屏上也稍微提一嘴
        else:
            forced_seeds = ["002230", "300033", "002415"] 
            for code in forced_seeds:
                d = get_realtime_stock_data(code)
                if d: final_message += f" • [资金面先锋补位] {d['name']}({code}) | 涨跌:{d['change']}% | 量比:{d['vol_ratio']}\n"
        final_message += "\n" + "="*20 + "\n\n"

    # --- 阶段叠加 2：晚间复盘 ---
    if current_hour >= 20:
        final_message += "🌑【特设时段：守夜人极致盘后大复盘】\n\n"
        review_text = get_daily_review(titles_only, top_sectors)
        
        # 【核心改动】：如果到了晚上，用晚上的深度复盘替换掉白天的分析，展示在大屏上！
        dashboard_display_text = review_text 
        
        final_message += f"{review_text}\n\n"
        
        stock_codes_night = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes_night:
            final_message += "📊 复盘标的盘口量价验证：\n"
            for code in list(dict.fromkeys(stock_codes_night))[:8]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "主力放量异动" if real_data['vol_ratio'] > 1.5 else "静默蓄力吸筹"
                    final_message += f" • {real_data['name']}({code}) 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"

    # 发送并用实时的文字去渲染网页大屏，再也没有空白！
    send_alert(final_message)
    generate_dashboard(topic_counts, dashboard_display_text, today_str)

if __name__ == "__main__":
    run_radar()
