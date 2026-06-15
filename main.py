import os
import requests
from openai import OpenAI
import google.generativeai as genai

# 初始化双 AI
ds_client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

def get_ai_insight(news_title):
    """DeepSeek 处理：快速盘中逻辑提炼"""
    try:
        res = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"游资视角分析：{news_title}，简述利好板块与逻辑。"}]
        )
        return res.choices[0].message.content
    except: return "【等待确认】"

def get_gemini_review(summary_data):
    """Gemini 处理：盘后深度复盘推理"""
    try:
        response = gemini_model.generate_content(f"基于以下资金流向数据做复盘分析：{summary_data}")
        return response.text
    except: return "【复盘中】"

# ======================
# 双轨执行逻辑
# ======================
# 1. 盘中：新闻进来 -> DeepSeek 极速提炼
# 2. 盘后：资金数据 -> Gemini 深度推演
