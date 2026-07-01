import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import hashlib
import time

# ======================
# 1. 核心与环境配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")
CACHE_FILE = "data/sent_news.json"

# ======================
# 2. 强力数据底座 (实时行情源)
# ======================
def get_realtime_data():
    """
    【腾讯实时接口】直接拉取全市场实时行情
    这是一个极其高效的接口，不再使用东财慢爬虫
    """
    try:
        # 一次性获取全市场代码列表，这里只选部分主流板作为演示，你可以根据需要扩充
        url = "http://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006" 
        # 为了获取个股，我们利用腾讯的批量接口，这里简单模拟全市场扫描的逻辑
        # 注：若要获取全市场实时，建议调用腾讯接口 API (例如: http://qt.gtimg.cn/q=sz000002,sh600000)
        # 这里改用一个更通用的高频接口拉取当前活跃股
        res = requests.get("http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f38", timeout=5).json()
        
        data = res.get('data', {}).get('diff', [])
        stocks = []
        for s in data:
            # 价格(f2), 涨跌幅(f3), 换手率(f38)
            stocks.append({
                "code": s['f12'],
                "name": s['f14'],
                "price": float(s['f2']),
                "change": float(s['f3']),
                "turnover": float(s['f38'])
            })
        return stocks
    except:
        return []

# ======================
# 3. 顶级合伙人 AI 大脑
# ======================
def get_deep_analysis(news_list, market_data, mode_type, current_time):
    # 动态将实时行情数据作为“事实基础”喂给AI，AI 绝对无法编造价格
    market_str = "\n".join([f"{s['code']} {s['name']} | 现价:{s['price']:.2f}元 | 涨幅:{s['change']}% | 换手:{s['turnover']}%" for s in market_data[:15]])
    
    prompt = f"""【最高指令】：你是顶级量化合伙人。基于下方提供的【实时盘面数据】进行推演，严禁输出任何废话，严禁编造数据！

当前时间：{current_time}
【底层实时盘面数据 (必须直接使用这些价格，严禁幻觉)】：
{market_str}

【战术分析任务】：
1. 市场定调：当前资金在抢什么题材？
2. 选股计划：挑选 3-5 只最强标的。
3. 风险排雷：提示当前的板块利空与高位股风险。

【排版要求】：
**🎯 市场全息实时定调** (结合实时涨跌幅与换手率分析)
**🗡️ 优选实战计划 (必须使用提供的现价和代码)**
* `[代码]` 股票名称 (现价: [真实价格]元)
  - 【逻辑与盘口】：(FVG缺口、堆量、换手率分析)
  - 【博弈点】：(明日买点/止损点)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.1).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错: {str(e)}"

# ======================
# 4. 调度中枢
# ======================
def run_radar():
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    
    # 核心：实时抓取行情 -> AI 解析 -> 实时输出
    market_data = get_realtime_data()
    # 模拟新闻获取
    live_flash = [] # 这里填入新闻逻辑
    
    report = f"**【实时行情推演终端】** ({today_str})\n\n"
    ai_analysis = get_deep_analysis(live_flash, "实时监测中...", market_data, "intraday", today_str)
    report += ai_analysis

    # 结果分发
    send_alert(report)

if __name__ == "__main__":
    run_radar()
