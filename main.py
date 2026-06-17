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
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
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
        return "获取异常"

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
# 3. 推送与大屏
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": full_text}, timeout=10)
        
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
            <h1>📊 A股全视野决策大屏 (V52)</h1>
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
# 4. AI 引擎 (找回内容厚度)
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list[:15]) # 限制新闻数量，防止过载
    prompt = f"""你是A股实战游资。阅读新闻并结合今日资金({top_sectors})进行推演。
【要求】：
1. 提取2-3条最有资金博弈价值或政策发酵潜力的新闻进行点评。
2. 尽量推荐市值在 50亿-500亿 之间的活跃标的（包含代码）。如果确实没有好标的，可以仅作逻辑推演。
3. 拒绝长篇大论，保持排版清晰。

新闻：
{news_text}

按以下格式输出：
【核心情报】总结2-3条关键新闻及对市场的影响。
【资金共振】分析新闻利好与当前资金主攻方向是否吻合。
【推演标的】给出3-5只相关活跃个股(如: 名字 000000)。"""
    
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        res_text = response.choices[0].message.content.strip()
        return res_text
    except: return "情报分析异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50 尾盘潜伏。今日主攻：{top_sectors}。
寻找10只可能洗盘的活跃游资票。市值50-500亿。
只输出10个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""盘后全面复盘。结合新闻：{news_text}。资金：{top_sectors}。
【要求】：内容要丰满有深度，但排版必须清晰。严格禁止推荐千亿市值大盘股。
格式：
【宏观定调】解读国家级金融事件或重要政策会议精神。
【最强主线】阐述主线逻辑。列出3-5只核心标的及代码。
【潜伏暗线】阐述暗线逻辑。列出3-5只核心标的及代码。
【异动点评】挑选今日盘面表现异常（超预期或不及预期）的1-2个板块或个股进行简评。
【避险防雷】明日资金可能撤离的退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "复盘失败。"

# ======================
# 5. 主控板
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

    # 模式 A：尾盘 14:00 - 14:59 触发【量化洗盘狙击】
    if current_hour == 14:
        message_body = f"【14:50 异常盘口监控】 {today_str}\n\n"
        message_body += f"今日主攻板块：{top_sectors}\n\n"
        
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        if ambush_list:
            message_body += "检测到主力洗盘/承接标的：\n"
            for data in ambush_list[:5]:
                message_body += f" • {data['name']}({data['code']}) | 跌幅:{data['change']}% | 换手:{data['turnover']}% | 量比:{data['vol_ratio']}\n"
        else:
            message_body += "未扫描到完美符合洗盘特征的标的。\n"
            
        send_alert(message_body)
        generate_dashboard(topic_counts, "", today_str)
        return

    # 模式 B：晚上 20:00 以后触发【全视宏观战报】
    if current_hour >= 20:
        message_body = f"【守夜人：战报与大局观】 {today_str}\n\n"
        message_body += f"今日资金主攻：{top_sectors}\n\n"
        review_text = get_daily_review(titles_only, top_sectors)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "盘口穿透验证：\n"
            for code in list(dict.fromkeys(stock_codes))[:10]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "异动" if real_data['vol_ratio'] > 1.5 else "平稳"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 C：白天盘中【全视雷达】
    message_body = f"【刺客雷达：全视追踪】 {today_str}\n\n"
    message_body += f"当前主力资金：{top_sectors}\n\n"
    
    # 展示几条最重要的新闻原文，保留信息厚度
    message_body += "精选盘中线索：\n"
    for title in titles_only[:3]:
         message_body += f"- {title}\n"
    message_body += "\n"

    semantic_alert = get_semantic_intraday_alert(titles_only, top_sectors)
    message_body += "AI 深度剖析：\n"
    message_body += f"{semantic_alert}\n"
    
    stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes:
        message_body += "\n重点标的盘口状态：\n"
        for code in list(dict.fromkeys(stock_codes))[:5]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                status = "放量活跃" if real_data['vol_ratio'] > 1.5 else "缩量平淡"
                message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量比:{real_data['vol_ratio']} ({status})\n"
        
    send_alert(message_body)
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
