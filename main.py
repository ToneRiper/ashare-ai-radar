import os
import json
import requests
from openai import OpenAI

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def get_ai_insight(news_title):
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你是资深游资，分析新闻利好与逻辑。输出：【题材】逻辑简述。"},
                      {"role": "user", "content": news_title}],
            stream=False
        )
        return response.choices[0].message.content
    except: return "【监控】等待资金确认"

def run_radar():
    # 1. 集中加载所有数据
    with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    try:
        with open("history.json", "r", encoding="utf-8") as f: history = json.load(f)
    except: history = []
    
    all_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    all_news.append({"title": item if isinstance(item, str) else item.get("title", "")})
        except: pass

    # 2. 计算 result
    result = {}
    for topic, aliases in KEYWORDS.items():
        matched_news = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched_news:
            result[topic] = {"all_news": matched_news}

    # 3. 组装推送内容
    message_body = "<b>【A股游资全息雷达 V29】</b>\n\n"
    has_content = False
    for topic, info in result.items():
        insight = get_ai_insight(info["all_news"][0]["title"])
        message_body += f"<b>🔥 {topic}</b>\n💡 AI决策: {insight}\n--------------------\n"
        has_content = True

    # 4. 执行推送
    if has_content:
        # Telegram
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": message_body, "parse_mode": "HTML"})
        # Server酱
        if SERVER_KEY:
            requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "游资雷达信号", "desp": message_body})
        print("推送成功")
    else:
        print("暂无新内容")

if __name__ == "__main__":
    run_radar()
