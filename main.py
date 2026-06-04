import os
import requests
import feedparser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

rss_url = "https://www.gov.cn/zhengce/zuixin/home.htm"

message = "【A股AI超级雷达】\n\n"

try:
    response = requests.get(rss_url, timeout=20)

    if response.status_code == 200:
        message += "国务院政策页面访问成功\n"
        message += f"状态码：{response.status_code}\n"
    else:
        message += "国务院页面访问失败\n"

except Exception as e:
    message += f"错误：{str(e)}\n"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
