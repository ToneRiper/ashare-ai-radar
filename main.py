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

# 【非常重要：这里填入你的 GitHub Pages 网址】
# 例如：https://your-username.github.io/your-repo-name/
GITHUB_PAGES_URL = "https://你的用户名.github.io/你的仓库名/" 

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
                "change": float(data[32]), "turnover": float(data[38]),
                "amplitude": float(data[43]), "vol_ratio": float(data[49])
            }
    except: pass
    return None

# ======================
# 2. 强力双端推送引擎 (V45 极致纯净文字版)
# ======================
def send_alert(text):
    # 添加统一的大屏入口
    full_text = text + f"\n\n🌐 [点击查看今日热力图与可视化大屏]({GITHUB_PAGES_URL})"
    
    # --- 1. 微信 (Server酱) ---
    if SERVER_KEY:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        # 微信 Markdown 适配
        wx_text = full_text.replace("<b>", "**").replace("</b>", "**")
        wx_text = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', wx_text) # HTML 链接转 Markdown
        requests.post(sc_url, data={"title": "A股游资内参", "desp": wx_text}, timeout=10)

    # --- 2. Telegram ---
    if TOKEN and CHAT_ID:
        tg_msg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        # TG 需要 HTML，所以要把附加的大屏链接转成 HTML
        tg_text = text + f"\n\n🌐 <a href='{GITHUB_PAGES_URL}'>点击查看今日热力图与可视化大屏</a>"
        try:
            res = requests.post(tg_msg_url, json={"chat_id": CHAT_ID, "text": tg_text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
            # 容错：如果 HTML 解析失败，剥离所有格式重发纯净版
            if res.status_code != 200:
                print(f"TG HTML解析失败: {res.text}，触发降级重发")
                clean_tg_text = tg_text.replace("<b>", "").replace("</b>", "")
                clean_tg_text = re.sub(r'<a href=".*?">(.*?)</a>', r'\1', clean_tg_text)
                requests.post(tg_msg_url, json={"chat_id": CHAT_ID, "text": clean_tg_text}, timeout=15)
        except Exception as e: print(f"TG 发送异常: {e}")

# ======================
# 3. 自动生成前端 Web 大屏
# ======================
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>游资暗潜雷达 - 可视化大屏</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            body {{ background-color: #0f172a; color: #e2e8f0; font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; }}
            .header {{ text-align: center; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }}
            .header h1 {{ color: #38bdf8; margin: 0; }}
            .container {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); flex: 1; min-width: 300px; max-width: 600px; }}
            .card h2 {{ color: #fbbf24; border-bottom: 2px solid #fbbf24; padding-bottom: 10px; margin-top: 0; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 15px; line-height: 1.6; }}
            #chart {{ width: 100%; height: 400px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 A股游资雷达决策大屏</h1>
            <p>数据更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日题材热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 宏观战报与推演</h2>
                <pre>{review_text if review_text else "暂无晚间复盘数据，或处于盘中扫描时段。"}</pre>
            </div>
        </div>
        <script>
            var chart = echarts.init(document.getElementById('chart'));
            var option = {{
                tooltip: {{ trigger: 'item' }},
                series: [{{
                    name: '新闻热度', type: 'pie', radius: ['40%', '70%'],
                    itemStyle: {{ borderRadius: 10, borderColor: '#1e293b', borderWidth: 2 }},
                    label: {{ color: '#e2e8f0' }},
                    data: {pie_data_str}
                }}]
            }};
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
# 4. AI 推演引擎
# ======================
def get_daily_review(all_news_titles):
    news_text = "\n".join(all_news_titles[:20])
    prompt = f"现在是晚上9点。推演【明日A股的剧本】。\n情报速览：{news_text}\n按以下结构汇报，严禁废话：\n【大局观】情绪周期处于什么阶段？\n【主线与妖股】1条主线和1条暗线。每条线推荐2-3只最强代码(格式：主线：000001,600000)。\n【盲区预警】散户最容易踩什么坑？"
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return escape_html(response.choices[0].message.content.strip())
    except: return "复盘生成失败"

def get_intraday_decision(news_title, topic):
    prompt = f"游资视角。情报：{news_title}。题材：{topic}。\n【本质】一句话翻译。\n【推演】切哪个方向？\n【妖股】3只相关代码(仅数字逗号隔开)。"
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return escape_html(response.choices[0].message.content.strip())
    except: return "解析异常"

# ======================
# 5. 雷达主控板
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

    # 模式 A：晚间复盘
    if current_hour >= 20:
        message_body = f"<b>【🌑 守夜人：宏观战报】 {today_str}</b>\n\n"
        review_text = get_daily_review(titles_only)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "📊 <b>盘口穿透验证：</b>\n"
            for code in list(dict.fromkeys(stock_codes))[:6]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖平稳"
                    message_body += f" • {real_data['name']}({code}) | 涨幅:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"
        
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 B：盘中刺客
    message_body = f"<b>【☀️ 刺客雷达】 {today_str}</b>\n\n"
    has_target = False

    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if not matched: continue
        
        decision = get_intraday_decision(matched[0]["title"], topic)
        
        core = deduce = ""
        stock_codes = []
        for line in decision.split('\n'):
            if line.startswith('【本质'): core = line.split('】')[-1].strip()
            if line.startswith('【推演'): deduce = line.split('】')[-1].strip()
            if line.startswith('【妖股'): 
                raw_codes = line.split('】')[-1]
                stock_codes = [c.strip() for c in re.split(r'[,，\s]+', raw_codes) if c.strip().isdigit() and len(c.strip())==6]

        has_target = True
        message_body += f"<b>📌 {topic}</b>\n"
        message_body += f"📰 <b>本质：</b>{core}\n"
        message_body += f"🧠 <b>推演：</b>{deduce}\n"
        
        message_body += "📊 <b>实时状态：</b>\n"
        for code in stock_codes[:3]: 
            real_data = get_realtime_stock_data(code)
            if real_data:
                status = "🔥" if real_data['vol_ratio'] > 2.0 else "➖"
                message_body += f" • {status} {real_data['name']} | 涨:{real_data['change']}% | 量:{real_data['vol_ratio']}\n"
        message_body += "--------------------\n"

    if has_target:
        send_alert(message_body)
    
    generate_dashboard(topic_counts, "盘中刺客模式：重点关注手机推送的实时异动卡片。", today_str)

if __name__ == "__main__":
    run_radar()
