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

# ======================
# 2. 实时行情与活体检测 (保持你最爱的 V38 逻辑)
# ======================
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
# 3. AI 双核引擎：盘中刺客 vs 盘后守夜人
# ======================
def get_intraday_decision(news_title, topic):
    """日内刺客模式：短平快，看穿对倒，只给结论"""
    prompt = f"""你是A股顶级游资。情报：{news_title}。题材：{topic}。
80字内输出：
【核心】一句话翻译本质。
【暗线】下一步切哪个上下游？
【结论】买点或防守信号。
【妖股】3只相关历史妖股代码(仅代码，逗号隔开)。"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3
        )
        return escape_html(response.choices[0].message.content.strip())
    except: return "解析异常"

def get_daily_review(all_news_titles):
    """盘后守夜人模式：全局板块、大局观定调、盲区拷问"""
    news_text = "\n".join(all_news_titles[:15]) # 取今天最重要的15条新闻
    prompt = f"""作为我的核心操盘手，现在是晚上9点，我们需要对今天的全网宏观及产业新闻进行深度复盘。
以下是今天抓取的核心情报速览：
{news_text}

请你跳出单一题材的局限，站位“大局观”，严格按以下结构向我汇报（字数控制在300字内，拒绝废话）：
【大局定调】今天政策面的核心导向是什么？是在维稳、放水，还是在默许游资炒妖？
【主线与板块】结合上述新闻，提炼出当前市场最强的一条主线概念，以及一条正在暗中蓄力的支线概念。
【游资盲区预警】（最重要！）指出大部分散户和我们目前可能忽略的风险。比如：是否有旧题材正在悄悄退潮？主力是否在借利好明牌掩护出货？
【明日剧本】明早集合竞价我们该盯什么现象（如：某龙头是否超预期被顶一字）来确认做多情绪？
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5
        )
        return escape_html(response.choices[0].message.content.strip())
    except Exception as e: return f"复盘生成失败: {e}"

# ======================
# 4. 强力推送模块
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
# 5. 雷达主控
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

    # 获取北京时间判断模式 (UTC+8)
    utc_now = datetime.utcnow()
    bjt_now = utc_now + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d")
    current_hour = bjt_now.hour

    message_body = ""

    # ==========================================
    # 模式 A：晚上 20:00 - 23:59 触发【深度复盘模式】
    # ==========================================
    if current_hour >= 20:
        print("进入盘后深度复盘模式...")
        message_body = f"<b>【🌑 守夜人：晚间深度复盘】 {today_str}</b>\n\n"
        review_text = get_daily_review(titles_only)
        message_body += review_text
        send_alert(message_body)
        return # 复盘发完直接结束，不再做零碎的异动推送

    # ==========================================
    # 模式 B：白天触发【日内刺客模式】
    # ==========================================
    print("进入日内刺客扫描模式...")
    message_body = f"<b>【☀️ 刺客雷达：盘中异动】 {today_str}</b>\n\n"
    has_target = False

    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if not matched: continue
        
        latest = matched[0]
        decision = get_intraday_decision(latest["title"], topic)
        
        # 解析日内输出...
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
                message_body += f" • {status} {real_data['name']}({real_data['code']}) | 涨:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({label})\n"
        message_body += "--------------------\n"

    if has_target:
        send_alert(message_body)
    else:
        print("盘中静默，无信号。")

if __name__ == "__main__":
    run_radar()
