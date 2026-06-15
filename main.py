import os
import json
import requests
from openai import OpenAI

# 环境变量读取
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def get_ai_insight(news_title):
    """DeepSeek 高效研报引擎"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是资深游资。基于新闻标题，分析题材与逻辑，输出格式：【题材】+ 逻辑链。简练有力。"},
                {"role": "user", "content": news_title}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return "【监控】等待资金注入..."

def send_to_serverchan(text):
    """Server酱 微信推送"""
    if not SERVER_KEY: return
    url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
    data = {"title": "A股游资雷达信号", "desp": text.replace("\n", "\n\n")}
    requests.post(url, data=data)

# ... [保留 fetch_all_sectors, auto_quant_stock_pick 等核心逻辑函数] ...
# (确保这些函数定义在 run_radar 之前)

# ======================
# V29 最终整合版
# ======================
def run_radar():
    message_body = "<b>【A股游资全息雷达 V29】</b>\n\n"
    has_content = False

    # 1. AI 驱动的新闻与逻辑提炼
    for topic, info in result.items():
        topic_news = [n for n in new_news if any(a in n["title"] for a in KEYWORDS.get(topic, []))]
        if topic_news:
            has_content = True
            insight = get_ai_insight(topic_news[0]["title"])
            message_body += f"<b>🔥 {topic}</b>\n💡 AI决策: {insight}\n"
            
            # 资金潜伏池 (调用你的选股逻辑)
            stocks = auto_quant_stock_pick(target_code) 
            for s in stocks[:3]:
                message_body += f"• <code>{s['name']}</code> (涨:{s['change']}%, 暗盘:{s['super_wan']}万)\n"
            message_body += "--------------------\n"

    # 2. 纯资金暗盘复盘 (无视消息面)
    capital = get_top_capital_sectors(limit=2)
    if capital:
        message_body += "<b>📊 今日强力资金沉淀:</b>\n"
        for sector in capital:
            message_body += f"• {sector['name']} (流入:{sector['inflow_yi']}亿)\n"

    # 3. 双端推送
    if has_content or capital:
        send_to_telegram(message_body)
        send_to_serverchan(message_body)
    else:
        print("大盘极度静默，保持防守。")

if __name__ == "__main__":
    run_radar()
