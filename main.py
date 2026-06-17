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
# 3. 推送与大屏 (彻底解决乱码)
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    
    # 微信推送 (SERVER酱)
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": full_text}, timeout=10)
        
    # Telegram 推送 (改用安全的文本格式，不再用 HTML 标签防乱码)
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
            <h1>📊 A股全视野决策大屏 (V51)</h1>
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
# 4. AI 引擎 (加强硬拦截)
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list)
    prompt = f"""你是A股实战游资。结合今日资金({top_sectors})，分析以下新闻。
【绝对铁律】：
1. 绝对不能漏掉任何国家级宏观事件、央行、证监会、知名论坛定调。
2. 选股绝对禁止出现：贵州茅台、宁德时代、中国石油等千亿巨头！只能给 50-300亿的连板活跃票。
3. 必须包含具体的6位数字股票代码。

新闻：
{news_text}

如果没有宏观大事或爆发点，仅回复“静默”。如果有，按以下格式输出（保留换行）：
【情报级别】S级宏观 / A级产业
【事件本质】翻译并点出影响
【龙头与潜力】(仅填代码，例如: 000001, 000002)"""
    
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        res_text = response.choices[0].message.content.strip()
        # 硬拦截大盘股
        if any(bad in res_text for bad in ["贵州茅台", "宁德时代", "中国石油", "招商银行", "工商银行"]):
            return "静默"
        return res_text
    except: return "异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50 尾盘潜伏。今日主攻：{top_sectors}。
寻找10只可能洗盘的游资票。
市值严格在50-300亿，绝对禁推超级权重股。
只输出10个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def analyze_tape_reading(top_sectors):
    prompt = f"""纯看盘口博弈。全市场资金主攻为：{top_sectors}。
用一句话点评资金去向（高低切、避险或主攻？）。
然后给出2只作为该方向先锋的代码(仅6位数字，禁推千亿龙头)。格式：
【资金眼】点评内容
【代表标的】000000, 111111"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return response.choices[0].message.content.strip()
    except: return ""

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""盘后复盘。新闻：{news_text}。资金：{top_sectors}。
【铁律】：涵盖宏观大事；禁推千亿大盘股(如茅台)；要有代码。
格式：
【宏观大局】情绪定调。
【最强主线】逻辑 + 代码。
【潜伏暗线】逻辑 + 代码。
【避险防雷】退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
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
            message_body += "未扫描到符合洗盘特征的完美标的，切勿盲目拿先手。"
            
        send_alert(message_body)
        generate_dashboard(topic_counts, "", today_str)
        return

    # 模式 B：晚上 20:00 以后触发【全视宏观战报】
    if current_hour >= 20:
        message_body = f"【守夜人：战报与大局观】 {today_str}\n\n"
        message_body += f"资金主攻：{top_sectors}\n\n"
        review_text = get_daily_review(titles_only, top_sectors)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "盘口穿透验证：\n"
            for code in list(dict.fromkeys(stock_codes))[:10]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "异动" if real_data['vol_ratio'] > 1.5 else "潜伏"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 C：白天盘中【全视雷达】
    message_body = f"【刺客雷达：全视追踪】 {today_str}\n\n"
    message_body += f"主力真实资金：{top_sectors}\n\n"
    
    latest_news = titles_only[:30] if len(titles_only) > 30 else titles_only
    semantic_alert = get_semantic_intraday_alert(latest_news, top_sectors)
    
    if "静默" in semantic_alert:
        message_body += "情报静默，启动纯资金面推演：\n"
        tape_reading = analyze_tape_reading(top_sectors)
        message_body += f"{tape_reading}\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', tape_reading)
        if stock_codes:
            message_body += "\n标的盘口状态：\n"
            for code in list(dict.fromkeys(stock_codes))[:5]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "活跃" if real_data['vol_ratio'] > 1.5 else "平淡"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
    else:
        message_body += "宏观/产业扫描结论：\n"
        message_body += f"{semantic_alert}\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
        if stock_codes:
            message_body += "\n标的盘口状态：\n"
            for code in list(dict.fromkeys(stock_codes))[:5]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "活跃" if real_data['vol_ratio'] > 1.5 else "平淡"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
        
    send_alert(message_body)
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
