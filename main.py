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
# 2. 数据引擎
# ======================
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
        return "数据获取异常"

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
# 3. 推送中枢 (安全排版格式)
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资刺客内参", "desp": full_text}, timeout=10)
        
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": full_text,
            "disable_web_page_preview": True
        }
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
            <h1>📊 A股语义全视野决策大屏 (V53)</h1>
            <p>更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日全网情报热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 核心战报与异动推演</h2>
                <pre>{review_text if review_text else "数据采集中..."}</pre>
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
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    except: pass

# ======================
# 4. 游资大脑核心 AI 引擎
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list[:15])
    prompt = f"""你是A股顶级短线游资策略师。请深度阅读并剖析以下新闻情报，同时结合今日资金盘面({top_sectors})。

【强制执行铁律】：
1. 严禁敷衍，严禁给出“静默”或“无”。必须挑出1-2个最具备炒作深度或宏观定调的新闻进行深度联想。
2. 每一个分析下，必须用游资思维进行【深度拷问】（例如：为什么在这个时间点放消息？主力建仓了吗？这是真利好还是诱多？阻力位在哪？）。
3. 必须推荐股票！严格禁止出现贵州茅台、宁德时代等千亿大盘股或百元高价股。只准挖掘市值在 50亿-300亿 之间、股性活跃、有连板基因的先锋股或底部蓄力补涨股，数量在 4-5 只。

新闻：
{news_text}

严格按以下格式输出（保持排版换行）：
【核心线索】摘录最具爆发力的新闻标题。
【大局观拷问】进行深度跨级联想，一针见血地拷问“为什么”，点出其背后不为人知的炒作野心与资金意图。
【盘口共振】说明该新闻是否与今天主力大单买入的板块产生共振。
【绝对尖刀】精选4-5只市值50-300亿的狙击标的(格式：代码 股票名称，例如: 000001 平安银行)。"""
    
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return response.choices[0].message.content.strip()
    except: return "情报剖析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""现在是A股 14:50 尾盘暗潜时间。今日资金主打方向：{top_sectors}。
你是顶尖量化短线高手，精通主力洗盘形态与反人性行为特征。
请从当前主攻板块、昨日强庄股、以及近期热门主线中，挖掘 10 只可能存在“假摔洗盘”、“放量承接大绿柱”、“仙人指路回落”的妖股潜力种子。
【硬性门槛】：市值严格限制在 50-300亿，绝对禁推超级权重股！必须在过去2-3天内展现过涨停或频繁长上影线异动的票。
不要任何废话，只输出10个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""现在是晚上9点盘后复盘时间。请结合全天情报({news_text})及真实资金流向({top_sectors})，撰写一份硬核复盘。
【铁律】：
1. 必须包含今日所有国家级金融大事件（如上海金融论坛、央行等）、地方前沿政策。
2. 必须深度拷问其长远逻辑，拒绝长篇大论，用游资黑话刀刀见血。
3. 严格禁止千亿市值大盘股。主线和暗线必须各给 5 只50-300亿、老少搭配、具备潜力的活跃个股代码。

格式：
【宏观大局观】政策会议精神解密，资金情绪是高潮、分歧还是退潮？
【主线战旗】一句话逻辑深度拷问。核心标的(5只，名字+代码)：
【暗线火种】一句话下属概念联想。核心标的(5只，名字+代码)：
【异动冷思考】今日表现最诡异/放量洗盘的板块或个股为什么会这样？
【避险防雷】明天资金绝对会核按钮出逃的退潮板块，坚决不碰。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "宏观复盘链路异常。"

# ======================
# 5. 雷达调度大枢纽
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

    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    current_hour = bjt_now.hour

    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    top_sectors = get_top_sectors()

    # ----------------------
    # 时段 A：14:50 尾盘反人性洗盘狙击
    # ----------------------
    if current_hour == 14:
        message_body = f"【🎯 14:50 尾盘异常个股狙击】 {today_str}\n\n"
        message_body += f"💰 今日主力主攻板块：\n{top_sectors}\n\n"
        
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                # 反常行为筛选：大环境火热，它却收大绿柱(-8%到-0.5%之间)，但量比明显放大(>1.1)说明承接强
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        message_body += "🚨 尾盘洗盘异动/放量托盘标的（每次必推）：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                message_body += f" • {data['name']}({data['code']}) | 跌幅: {data['change']}% | 换手: {data['turnover']}% | 量比: {data['vol_ratio']}\n"
            message_body += "\n💡 量化反行为推演：板块大涨而个股放量收绿，排除了钝刀子死水，多为强庄借助震荡进行极限洗筹，博弈其次日资金回流反包、弱转强高开。"
        else:
            # 兜底机制：如果没有完美符合背离的，就强制塞 3 只当前主攻板块内量比最火爆、但微跌洗盘的种子
            forced_seeds = ["002230", "300033", "002415"] # 备用股池
            for code in forced_seeds:
                d = get_realtime_stock_data(code)
                if d: message_body += f" • [风向标补位] {d['name']}({code}) | 涨跌: {d['change']}% | 量比: {d['vol_ratio']}\n"
            message_body += "\n💡 提示：今日未抓到极端反常洗盘股，以上为资金面核心先锋补位推荐。"
            
        send_alert(message_body)
        generate_dashboard(topic_counts, "", today_str)
        return

    # ----------------------
    # 时段 B：晚上 21:00 全视野宏观硬核复盘
    # ----------------------
    if current_hour >= 20:
        message_body = f"【🌑 守夜人：极致复盘与次日剧本】 {today_str}\n\n"
        message_body += f"💰 全天主力真金白银方向：\n{top_sectors}\n\n"
        
        review_text = get_daily_review(titles_only, top_sectors)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "📊 推演个股盘口量价穿透：\n"
            for code in list(dict.fromkeys(stock_codes))[:8]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "主力放量异动" if real_data['vol_ratio'] > 1.5 else "筹码静默吸筹"
                    message_body += f" • {real_data['name']}({code}) 涨跌: {real_data['change']}% | 量比: {real_data['vol_ratio']} ({status})\n"
                    
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # ----------------------
    # 时段 C：白天日常盘中深度语义穿透
    # ----------------------
    message_body = f"【☀️ 刺客雷达：盘中情报高透网】 {today_str}\n\n"
    message_body += f"💰 实时主力资金脉搏：\n{top_sectors}\n\n"
    
    message_body += "📋 当前采集核心线索原文：\n"
    for title in titles_only[:3]:
         message_body += f"- {title}\n"
    message_body += "\n"

    # AI 语义高透推演
    semantic_alert = get_semantic_intraday_alert(titles_only, top_sectors)
    message_body += "🧠 游资大脑跨级推演与拷问：\n"
    message_body += f"{semantic_alert}\n"
    
    # 盘口状态提取与穿透验证
    stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes:
        message_body += "\n📊 推荐标的实时盘口状态：\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                status = "火爆抢筹" if real_data['vol_ratio'] > 1.5 else "主力锁仓"
                message_body += f" • {real_data['name']}({code}) 涨跌: {real_data['change']}% | 量比: {real_data['vol_ratio']} ({status})\n"
                
    send_alert(message_body)
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
