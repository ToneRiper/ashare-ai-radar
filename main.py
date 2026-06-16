import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta

# ======================
# 1. 核心配置 (记得替换你的真实域名)
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")
GITHUB_PAGES_URL = "https://toneriper.github.io/ashare-ai-radar/" 

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

# ======================
# 2. 实时行情与竞价检测引擎
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
                "change": float(data[32]), "open_price": float(data[5]),
                "pre_close": float(data[4]), "vol_ratio": float(data[49])
            }
    except: pass
    return None

# ======================
# 3. AI 复盘与决策引擎
# ======================
def get_daily_review(all_news_titles):
    news_text = "\n".join(all_news_titles[:20])
    prompt = f"晚上9点复盘。情报：{news_text}。\n严格按此格式输出：\n【大局观】情绪周期阶段？\n【核心主线】主线逻辑+3只核心股代码(主线:000001,600000,600001)\n【暗线机会】暗线逻辑+3只核心股代码(暗线:000002,600002,600003)\n【盲区预警】什么票要核按钮？"
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return response.choices[0].message.content.strip()
    except: return "复盘失败"

# ======================
# 4. 推送引擎
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 [点击查看可视化大屏]({GITHUB_PAGES_URL})"
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股雷达战报", "desp": full_text.replace("<b>", "**").replace("</b>", "**")})
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": full_text, "parse_mode": "HTML", "disable_web_page_preview": True})

# ======================
# 5. 主程序 (包含竞价核按钮检测)
# ======================
def run_radar():
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    current_hour = bjt_now.hour
    
    # 获取新闻并执行 AI 逻辑... (此处省略，保持你原有的读取逻辑)
    # ...
    
    # 在 9:25-9:30 扫描核按钮：
    if 9 <= bjt_now.hour <= 10:
        message_body = "<b>【🚨 竞价防核爆扫描】</b>\n"
        # 抓取昨晚妖股池，如果有竞价 < -3%，立即触发警告
        # ...
        send_alert(message_body)

if __name__ == "__main__":
    run_radar()
