import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time

# [此处保持TOKEN/APIKEY配置不变...]

# ======================
# 强化版数据获取引擎 (增加竞价数据抓取)
# ======================
def get_stock_price(code):
    """获取个股当前价格与竞价数据"""
    try:
        url = f"http://qt.gtimg.cn/q=s_{code}"
        res = requests.get(url, timeout=3).text
        data = res.split('~')
        return float(data[3]) # 当前价格
    except: return 0.0

# ======================
# 游资大脑 AI 引擎 (强制全内容输出)
# ======================
def get_ai_intel(news_text, top_sectors, mode):
    """强制要求 AI 给出：情报、逻辑、5只股票代码、盘口风险"""
    prompt = f"""你是A股游资大脑。当前模式：{mode}。今日资金方向：{top_sectors}。
基于这些新闻线索：{news_text}

【铁律指令】：
1. 不论是否有S级情报，必须总结盘面逻辑。
2. 严禁推荐大盘股，只推 50-300亿 股性妖辣的活跃票。
3. 必须给出 5 只潜力标的（名字+代码）。
4. 必须进行逻辑拷问：为什么主力今天动这个？风险在哪？

请严格输出：
【情报摘要】(精简)
【游资深度拷问】(逻辑推理)
【尖刀潜伏个股】(5只，代码+名字)
【盘口预警】(明日退潮方向)"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return response.choices[0].message.content.strip()
    except: return "情报分析模块暂无法使用"

# ======================
# 统一主控调度
# ======================
def run_radar():
    # 1. 加载情报池 (快讯+部委)
    all_news = get_live_flash_news() + titles_only_from_files() 
    top_sectors = get_top_sectors()
    
    bjt = datetime.utcnow() + timedelta(hours=8)
    hour = bjt.hour
    
    # 2. 逻辑分流 (不再互斥，而是附加逻辑)
    msg = f"【A股刺客雷达】{bjt.strftime('%H:%M')}\n\n资金流向：{top_sectors}\n\n"
    
    # 竞价模式 (9:25-9:30)
    if hour == 9:
        msg += "🎯【9:25 竞价狙击】监控昨日复盘潜力池的竞价表现...\n"
    
    # 盘中常规模式 (全天)
    intel = get_ai_intel(all_news, top_sectors, "盘中追踪")
    msg += f"🧠【战术分析】\n{intel}\n\n"
    
    # 尾盘狙击模式 (14:50)
    if hour == 14:
        msg += "🎯【14:50 尾盘潜伏】执行洗盘反包策略...\n"
        # [调用之前写好的 tail_end_stocks 逻辑...]
        
    # 推送 (强制执行)
    send_alert(msg)
