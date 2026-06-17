import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta

# ======================
# 1. 核心配置 (请确保填入你真实的 Github Pages 网址)
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
# 2. 强力防断连推送引擎 (双端净化)
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 [点击查看今日可视化大屏]({GITHUB_PAGES_URL})"
    
    # 微信推送
    if SERVER_KEY:
        wx_text = full_text.replace("<b>", "**").replace("</b>", "**")
        wx_text = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', wx_text)
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": wx_text}, timeout=10)

    # TG 推送
    if TOKEN and CHAT_ID:
        tg_text = text + f"\n\n🌐 <a href='{GITHUB_PAGES_URL}'>点击查看今日可视化大屏</a>"
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": tg_text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
            if res.status_code != 200:
                clean_tg_text = tg_text.replace("<b>", "").replace("</b>", "")
                clean_tg_text = re.sub(r'<a href=".*?">(.*?)</a>', r'\1', clean_tg_text)
                requests.post(tg_url, json={"chat_id": CHAT_ID, "text": clean_tg_text}, timeout=15)
        except: pass

# ======================
# 3. 大屏前端生成器 (新增强制拒翻标签)
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
            <h1>📊 A股游资雷达决策大屏</h1>
            <p>数据更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日政策与情报热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 宏观战报与明日推演</h2>
                <pre>{review_text if review_text else "正在等待晚间 21:00 全市场复盘数据生成..."}</pre>
            </div>
        </div>
        <script>
            var chart = echarts.init(document.getElementById('chart'));
            var option = {{
                tooltip: {{ trigger: 'item' }},
                series: [{{
                    name: '新闻热度', type: 'pie', radius: ['40%', '70%'],
                    itemStyle: {{ borderRadius: 10, borderColor: '#1e293b', borderWidth: 2 }},
                    label: {{ color: '#e2e8f0', fontSize: 14 }},
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
# 4. 游资大脑 AI 引擎 (重装归位)
# ======================
def get_daily_review(news_list):
    news_text = "\n".join(news_list[:25])
    prompt = f"""你是顶级A股游资。现在是晚上9点，基于以下今日全网核心情报，推演【明日大局观与操作剧本】。
情报：{news_text}

严禁任何废话，直接用游资黑话输出：
【大局观定调】今日政策与消息面偏向进攻还是防守？资金大概率的高低切方向在哪？
【主线推演】提炼出最有可能爆发的1条主线和1条暗线。
【核心标的】为你推演的主线和暗线，分别提供至少2只最具辨识度的核心龙头代码（格式要求：主线代码：000001；暗线代码：600000）。
【避险盲区】指出明天绝对不能接盘的旧题材退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return escape_html(response.choices[0].message.content.strip())
    except: return "复盘推演失败，API异常。"

def get_intraday_decision(news_title, topic):
    prompt = f"游资视角分析。情报：{news_title}。题材：{topic}。\n【事件本质】一句话翻译。\n【资金推演】利好哪个细分环节？\n【龙头代码】提供2只相关性最高的A股代码(仅数字)。"
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

    # 模式 A：晚上 20:00 以后触发【宏观大局观复盘】
    if current_hour >= 20:
        message_body = f"<b>【🌑 守夜人：宏观战报与明日推演】 {today_str}</b>\n\n"
        review_text = get_daily_review(titles_only)
        message_body += f"{review_text}\n"
        
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 B：白天盘中触发【刺客异动狙击】
    message_body = f"<b>【☀️ 刺客雷达：盘中情报】 {today_str}</b>\n\n"
    has_target = False

    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if not matched: continue
        
        decision = get_intraday_decision(matched[0]["title"], topic)
        has_target = True
        message_body += f"<b>📌 题材命中：{topic}</b>\n{decision}\n--------------------\n"

    if has_target:
        send_alert(message_body)
    else:
        # 心跳包机制：即使没异动，也要报平安，防止你觉得系统坏了
        send_alert(f"<b>【雷达心跳】 {today_str}</b>\n\n当前时段政策情报面无重大异动，保持静默监控。")
        
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
