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

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ======================
# 2. 数据引擎 (资金与盘口)
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
    full_text = text + f"\n\n🌐 [查看决策大屏]({GITHUB_PAGES_URL})"
    if SERVER_KEY:
        wx_text = full_text.replace("<b>", "**").replace("</b>", "**")
        wx_text = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', wx_text)
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": wx_text}, timeout=10)
    if TOKEN and CHAT_ID:
        tg_text = text + f"\n\n🌐 <a href='{GITHUB_PAGES_URL}'>查看决策大屏</a>"
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": tg_text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
            if res.status_code != 200:
                clean_tg_text = tg_text.replace("<b>", "").replace("</b>", "")
                clean_tg_text = re.sub(r'<a href=".*?">(.*?)</a>', r'\1', clean_tg_text)
                requests.post(tg_url, json={"chat_id": CHAT_ID, "text": clean_tg_text}, timeout=15)
        except: pass

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
            <h1>📊 A股全视野决策大屏 (V50)</h1>
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
# 4. AI 全视引擎 (修复宏观盲区与强化量化洗盘)
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list)
    prompt = f"""你是A股游资大局观策略师。结合今日资金主攻({top_sectors})，分析以下新闻：
【重要强制指令】：绝对不能遗漏国家级宏观金融会议（如陆家嘴论坛、央行讲话、重要部委定调）！如果有此类大政方针，必须优先列出！
如果没有宏观大事，就寻找具体产业爆发点。

最新新闻：
{news_text}

如果全是无效杂音且无大事件，请回复“新闻静默，纯看盘面”。
如果有高价值情报或宏观大事，按以下格式输出：
📌 【情报级别】(S级宏观/A级产业)
【事件本质】大白话翻译并点出对股市大盘或具体板块的影响
【龙头与潜力】给出3-5只50-300亿市值低位活跃相关标的(仅代码)"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return escape_html(response.choices[0].message.content.strip())
    except: return "异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""现在是A股 14:50 尾盘潜伏时间。今日资金主攻：{top_sectors}。
你是顶尖量化黑客，专门寻找【反常行为】与【洗盘异动】。
请在今日热门概念或昨日强势股中，选出10只可能存在以下行为的股票：
1. 强板块下的分歧洗盘（诱空）
2. 试盘仙人指路回落
3. 资金承接极强的大绿柱
【严禁超大盘股】：市值严格控制在 50-300 亿，必须是近期有涨停基因的活跃游资票！
不要任何解释，只输出10个6位数字代码，用逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""你是顶级A股游资。盘后复盘。新闻：{news_text}。今日资金主攻：{top_sectors}。
【铁律】：必须涵盖今日所有国家级金融大事件；必须挖掘资金面与政策面共振的方向；禁推超500亿大盘股。
格式：
【宏观大局】大政方针与资金情绪定调。
【最强主线】逻辑。核心标的：(仅代码，共5只，老少搭配)。
【潜伏暗线】逻辑。核心标的：(仅代码，共5只)。
【避险防雷】明日资金可能出逃的退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return escape_html(response.choices[0].message.content.strip())
    except: return "复盘失败。"

def analyze_tape_reading(top_sectors):
    """当没有重要新闻时，启用纯盘口逻辑分析资金行为"""
    prompt = f"""新闻处于静默期，游资开始纯看盘口博弈。
当前全市场真实资金主攻方向为：{top_sectors}。
请用游资视角，用一句话点评这些资金去了哪里，是在做高低切、避险还是主攻？并给出2只可能作为该方向先锋的代表代码(仅6位数字)。格式如下：
【资金眼】点评内容
【代表标的】000000, 111111"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return escape_html(response.choices[0].message.content.strip())
    except: return ""

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
        message_body = f"<b>【🎯 14:50 异常行为监控】 {today_str}</b>\n\n"
        message_body += f"💰 <b>今日主攻板块：</b>\n{top_sectors}\n\n"
        
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                # 寻找异常行为：跌幅不超-8%，但量比放大(>1.1)说明有资金承接洗盘
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        if ambush_list:
            message_body += "🚨 <b>检测到主力反常行为(强板块/弱个股/资金承接)：</b>\n"
            for data in ambush_list[:5]:
                message_body += f" • {data['name']}({data['code']}) | 跌幅: <span style='color:green;'>{data['change']}%</span> | 换手: {data['turnover']}% | <b>量比: {data['vol_ratio']}</b>\n"
            message_body += "\n💡 <i>量化逻辑：大环境不差且放量收跌，过滤掉钝刀子割肉，大概率为主力暴力洗筹，博弈次日弱转强高开。</i>"
        else:
            message_body += "⚠️ 未扫描到完美符合【高量承接洗盘】特征的标的，不建议盲目拿先手。"
            
        send_alert(message_body)
        generate_dashboard(topic_counts, "", today_str)
        return

    # 模式 B：晚上 20:00 以后触发【全视宏观战报】
    if current_hour >= 20:
        message_body = f"<b>【🌑 守夜人：大局观与战报】 {today_str}</b>\n\n"
        message_body += f"💰 <b>资金主攻：</b>\n{top_sectors}\n\n"
        review_text = get_daily_review(titles_only, top_sectors)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "📊 <b>盘口穿透验证：</b>\n"
            for code in list(dict.fromkeys(stock_codes))[:10]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖潜伏"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 C：白天盘中【宏观不漏 + 纯盘口推演】
    message_body = f"<b>【☀️ 刺客雷达：全视雷达】 {today_str}</b>\n\n"
    message_body += f"💰 <b>主力真实资金：</b>\n{top_sectors}\n\n"
    
    # 将最新30条新闻交由全视引擎处理
    latest_news = titles_only[:30] if len(titles_only) > 30 else titles_only
    semantic_alert = get_semantic_intraday_alert(latest_news, top_sectors)
    
    if "新闻静默" in semantic_alert:
        # 当新闻确实没有任何宏观或产业异动时，不再直接过滤，而是开启【盘口推演】
        message_body += "🧠 <b>情报静默，启动纯资金面推演：</b>\n"
        tape_reading = analyze_tape_reading(top_sectors)
        message_body += f"{tape_reading}\n"
    else:
        # 抓到了宏观大会或产业爆发
        message_body += "🧠 <b>宏观/产业语义扫描：</b>\n"
        message_body += semantic_alert
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
        if stock_codes:
            message_body += "\n📊 <b>标的盘口状态：</b>\n"
            for code in list(dict.fromkeys(stock_codes))[:5]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥" if real_data['vol_ratio'] > 1.5 else "➖"
                    message_body += f" • {status}{real_data['name']} 涨:{real_data['change']}% 量:{real_data['vol_ratio']}\n"
        
    send_alert(message_body)
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
