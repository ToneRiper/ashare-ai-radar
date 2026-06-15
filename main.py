import os
import json
import requests
from openai import OpenAI

# 环境变量初始化
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

# --- 这里放入你之前那些完整的 fetch_all_sectors, auto_quant_stock_pick, get_translation 等函数 ---
# (为了保证运行成功，这些函数定义必须放在 run_radar 之前)

def get_ai_insight(news_title):
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是资深游资。基于新闻，输出：【题材】逻辑简述。"},
                {"role": "user", "content": news_title}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except: return "【监控】等待资金注入..."

def run_radar():
    # 确保这些变量在函数内能被访问到
    # 加载数据 (保持你原本的加载路径)
    with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    # ... (这里包含你原本的 load history, hot_rank 等代码) ...
    
    # 重新计算 result 变量 (这就是报错的根源，现在我们把它放在这里)
    result = {}
    for topic, aliases in KEYWORDS.items():
        matched_news = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched_news:
            result[topic] = {"count": len(matched_news), "all_news": matched_news}
    
    # 逻辑处理
    message_body = "<b>【A股游资全息雷达 V29】</b>\n\n"
    for topic, info in result.items():
        # ... (你的循环逻辑) ...
        pass
    
    # 执行发送
    if message_body:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": message_body, "parse_mode": "HTML"})
        if SERVER_KEY:
            requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "游资雷达", "desp": message_body})

if __name__ == "__main__":
    run_radar()
