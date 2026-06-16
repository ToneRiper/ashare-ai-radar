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

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def get_realtime_stock_data(stock_code):
    """提取收盘/盘中真实数据"""
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
# 2. 生成可视化图片链接 (黑客方案修复版)
# ======================
def get_chart_image_url(topic_counts):
    """利用免费图表API，将数据瞬间转为高质量PNG图片链接"""
    if not topic_counts: return None
    
    # 修复序列化问题：强制将 keys 和 values 转换为普通的 list
    labels = list(topic_counts.keys())
    data = list(topic_counts.values())
    
    # 构造深色模式饼图的 JSON 配置
    chart_config = {
        "type": "outlabeledPie",
        "data": {
            "labels": labels,
            "datasets": [{
                "backgroundColor": ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899"], 
                "data": data
            }]
        },
        "options": {
            "backgroundColor": "#0f172a",
            "plugins": {
                "legend": {"display": False},
                "outlabels": {
                    "text": "%l (%v)", 
                    "color": "white", 
                    "stretch": 35, 
                    "font": {"resizable": True, "minSize": 12, "maxSize": 18}
                }
            }
        }
    }
    
    try:
        url = f"https://quickchart.io/chart?width=600&height=400&c={json.dumps(chart_config)}"
        return url
    except Exception as e:
        print(f"图表生成失败: {e}")
        return None

# ======================
# 3. 双端强力图文推送
# ======================
def send_alert_with_image(text, image_url=None):
    # 1. 微信 Server酱 (支持 Markdown 图片)
    if SERVER_KEY:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        md_text = text.replace("<b>", "**").replace("</b>", "**").replace("<a href='", "[").replace("'>", "](").replace("</a>", ")")
        if image_url:
            md_text = f"![热力图]({image_url})\n\n" + md_text
        requests.post(sc_url, data={"title": "A股游资内参", "desp": md_text}, timeout=10)
        
    # 2. Telegram (支持原生发送图片+排版文字)
    if TOKEN and CHAT_ID:
        try:
            if image_url:
                # 先发图，附带简短说明
                tg_photo_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                requests.post(tg_photo_url, json={"chat_id": CHAT_ID, "photo": image_url, "caption": "📊 今日题材热力图"}, timeout=10)
            
            # 再发详细文字
            tg_msg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            res = requests.post(tg_msg_url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
            if res.status_code != 200:
                clean_text = text.replace("<b>", "").replace("</b>", "")
                clean_text = re.sub(r'<a href=".*?">(.*?)</a>', r'\1', clean_text)
                requests.post(tg_msg_url, json={"chat_id": CHAT_ID, "text": clean_text}, timeout=10)
        except: pass

# ======================
# 4. AI 盘后复盘引擎 (加入个股穿透)
# ======================
def get_daily_review(all_news_titles):
    news_text = "\n".join(all_news_titles[:20])
    prompt = f"""现在是晚上9点。基于以下情报，推演【明日A股的剧本】。
情报速览：
{news_text}

严格按以下结构汇报，剔除一切AI废话，用游资黑话：
【大局观】今天政策是强攻还是防守？处于情绪周期的什么阶段？
【主线与妖股】明确1条最强主线和1条正在蓄力的暗线。每条线必须强制推荐2-3只最具辨识度的核心股票代码（格式严格为：主线代码：000001,600000；暗线代码：000002,600002）。
【盲区预警】哪个旧题材正在诱多出货？散户最容易在明天开盘踩什么坑？
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5
        )
        return escape_html(response.choices[0].message.content.strip())
    except: return "复盘生成失败"

def get_intraday_decision(news_title, topic):
    prompt = f"你是A股顶级游资。情报：{news_title}。题材：{topic}。\n80字内输出：\n【本质】一句话翻译。\n【推演】切哪个方向？\n【妖股】3只相关代码(仅数字逗号隔开)。"
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
    today_str = bjt_now.strftime("%Y-%m-%d")
    current_hour = bjt_now.hour

    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    chart_url = get_chart_image_url(topic_counts)

    # 模式 A：晚间复盘战报
    if current_hour >= 20:
        message_body = f"<b>【🌑 守夜人：宏观战报与核心标的】 {today_str}</b>\n\n"
        review_text = get_daily_review(titles_only)
        message_body += f"{review_text}\n\n"
        
        # 提取复盘中的所有股票代码并进行收盘盘口验证
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "📊 <b>收盘盘口穿透验证：</b>\n"
            # 去重并只取前6只
            for code in list(dict.fromkeys(stock_codes))[:6]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖平稳"
                    message_body += f" • {real_data['name']}({code}) | 涨幅:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"
        
        send_alert_with_image(message_body, chart_url)
        return 

    # 模式 B：盘中刺客
    message_body = f"<b>【☀️ 刺客雷达：盘中异动】 {today_str}</b>\n\n"
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
        message_body += f"<b>📌 题材：{topic}</b>\n"
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
        send_alert_with_image(message_body, chart_url)

if __name__ == "__main__":
    run_radar()
