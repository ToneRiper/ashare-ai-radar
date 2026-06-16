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
# 2. AI 引擎：日内刺客
# ======================
def get_intraday_decision(news_title, topic):
    prompt = f"""你是A股顶级游资。情报：{news_title}。题材：{topic}。
80字内输出：
【核心】一句话本质。
【暗线】资金下一步切哪个上下游？
【结论】买点或防守信号。
【妖股】3只历史股性最强代码(仅输出6位代码，逗号隔开)。"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3
        )
        return escape_html(response.choices[0].message.content.strip())
    except: return "解析异常"

# ======================
# 3. AI 引擎：盘后大局观战报 (核心重构升级)
# ======================
def get_daily_review(all_news_titles):
    news_text = "\n".join(all_news_titles[:20]) # 取最重要的前20条
    prompt = f"""作为我的核心操盘手，现在是晚上9点。我们需要基于以下今日全网核心情报，推演【明日A股的剧本】。
今日情报速览：
{news_text}

请你摒弃散户思维，站在顶级游资的大局观，严格按以下结构向我汇报（总字数控制在400字内，刀刀见血）：
【大局定调】今天政策面的核心导向是在放水强攻，还是在维稳防守？
【情绪周期与明日预判】（这是重点！）结合今日事件的密集度和力度，判断当前市场情绪处于什么阶段（冰点/启动/发酵/高潮/退潮）？基于此阶段，推演明日大盘及核心主线的资金走向（大概率是加速顶一字、巨量分歧，还是利好兑现被砸？）
【主线与暗线概念】明确指出当前最强的“明牌概念板块”是什么？哪一条“暗线板块”正在悄悄蓄力准备补涨？
【游资盲区预警】指出大部分散户目前可能忽略的致命风险（例如：旧题材阴跌、机构借利好出货等）。
【明日竞价剧本】明早9:25，我们需要盯死哪类核心现象（如某只高标龙头的封单量）来确认情绪的真伪？
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5
        )
        return escape_html(response.choices[0].message.content.strip())
    except Exception as e: return f"复盘生成失败: {e}"

# ======================
# 4. 强推模块
# ======================
def send_alert(text):
    if SERVER_KEY:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        md_text = text.replace("<b>", "**").replace("</b>", "**").replace("<a href='", "[").replace("'>", "](").replace("</a>", ")")
        requests.post(sc_url, data={"title": "A股游资内参", "desp": md_text}, timeout=10)
        
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(tg_url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)

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
                        link = "" if isinstance(item, str) else item.get("link", "")
                        if title: 
                            all_news.append({"title": title, "link": link})
                            titles_only.append(title)
            except: pass

    # UTC 转 北京时间
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d")
    current_hour = bjt_now.hour

    # 模式 A：晚间复盘战报 (20点以后)
    if current_hour >= 20:
        print("执行盘后深度复盘...")
        message_body = f"<b>【🌑 守夜人：宏观战报与明日推演】 {today_str}</b>\n\n"
        message_body += get_daily_review(titles_only)
        send_alert(message_body)
        return 

    # 模式 B：盘中刺客模式
    print("执行日内刺客扫描...")
    message_body = f"<b>【☀️ 刺客雷达：盘中异动】 {today_str}</b>\n\n"
    has_target = False

    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if not matched: continue
        
        latest = matched[0]
        decision = get_intraday_decision(latest["title"], topic)
        
        core = deduce = strike = ""
        stock_codes = []
        for line in decision.split('\n'):
            if line.startswith('【核心'): core = line.split('】')[-1].strip()
            if line.startswith('【暗线'): deduce = line.split('】')[-1].strip()
            if line.startswith('【结论'): strike = line.split('】')[-1].strip()
            if line.startswith('【妖股'): 
                raw_codes = line.split('】')[-1]
                stock_codes = [c.strip() for c in re.split(r'[,，\s]+', raw_codes) if c.strip().isdigit() and len(c.strip())==6]

        has_target = True
        link_str = f" | <a href='{latest['link']}'>源</a>" if latest['link'] else ""
        message_body += f"<b>📌 题材：{topic}</b>{link_str}\n"
        message_body += f"📰 <b>本质：</b>{core}\n"
        message_body += f"🧠 <b>推演：</b>{deduce}\n"
        message_body += f"🎯 <b>结论：</b>{strike}\n"
        
        message_body += "📊 <b>盘口实时状态：</b>\n"
        for code in stock_codes[:4]: 
            real_data = get_realtime_stock_data(code)
            if real_data:
                if real_data['turnover'] < 1.0 and real_data['amplitude'] < 2.0: status, label = "🧟", "死水"
                elif real_data['vol_ratio'] > 2.0 or real_data['amplitude'] > 5.0: status, label = "🔥", "突袭"
                else: status, label = "➖", "跟随"
                message_body += f" • {status} {real_data['name']}({real_data['code']}) | 涨:{real_data['change']}% | 量:{real_data['vol_ratio']} ({label})\n"
        message_body += "--------------------\n"

    if has_target:
        send_alert(message_body)

if __name__ == "__main__":
    run_radar()
