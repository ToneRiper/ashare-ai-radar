import os
import json
import requests
from openai import OpenAI

# 环境变量
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def send_message(text):
    """强制推送：双端同时执行，且包含错误捕获"""
    # 1. 发送至 Telegram
    try:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        tg_res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        print(f"TG 发送状态: {tg_res.status_code}")
    except Exception as e: print(f"TG 失败: {e}")

    # 2. 发送至 Server酱 (微信)
    try:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        sc_res = requests.post(sc_url, data={"title": "游资雷达信号", "desp": text}, timeout=10)
        print(f"微信发送状态: {sc_res.status_code}")
    except Exception as e: print(f"微信失败: {e}")

def run_radar():
    # 强制生成一段心跳测试文本，看看是否能触达
    test_msg = "<b>【雷达自检】</b>\n链路正常，系统已启动。\n当前时间: 2026-06-16"
    
    # 执行逻辑... (保持你之前的 news/quant 逻辑)
    # 无论有无异动，发送一次测试
    send_message(test_msg)

if __name__ == "__main__":
    run_radar()
