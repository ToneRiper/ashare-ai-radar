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
# 请务必替换为你真实的 GitHub Pages 网址
GITHUB_PAGES_URL = "https://toneriper.github.io/ashare-ai-radar/" 

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def send_tg(text):
    """强制发送纯净文字，确保不报错"""
    tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    }
    requests.post(tg_url, json=payload, timeout=10)

def run_radar():
    # 1. 读取所有新闻
    all_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in reversed(data):
                        # 确保兼容性
                        title = item if isinstance(item, str) else item.get("title", "")
                        if title: all_news.append(title)
            except: pass

    # 2. 读取关键词
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {"测试": ["中国", "华为", "科技"]}

    # 3. 匹配逻辑 (改成更灵敏的遍历匹配)
    today_news = []
    for news in all_news:
        for topic, aliases in KEYWORDS.items():
            if any(a.lower() in news.lower() for a in aliases):
                today_news.append(f"• [{topic}] {news}")
    
    # 4. 构建推送内容
    bjt = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    if not today_news:
        msg = f"<b>【雷达监控】{bjt}</b>\n\n今日暂无关键词命中。\n\n🌐 <a href='{GITHUB_PAGES_URL}'>查看可视化大屏</a>"
    else:
        msg = f"<b>【雷达发现异动】{bjt}</b>\n\n" + "\n".join(today_news[:10]) + f"\n\n🌐 <a href='{GITHUB_PAGES_URL}'>查看可视化大屏</a>"

    # 5. 强制发送
    print("正在推送至 TG...")
    send_tg(msg)
    print("推送完成。")

if __name__ == "__main__":
    run_radar()
