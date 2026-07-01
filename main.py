import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time

try:
    import pandas as pd
    import akshare as ak
    HAS_QUANT = True
except ImportError:
    HAS_QUANT = False

# ======================
# 1. 核心与环境配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

# 【全维情报网】：加入全球宏观、央行、垂直部委，绝不漏掉底层驱动
MACRO_WORDS = ["美联储", "降息", "非农", "央行", "国务院", "工信部", "发改委", "药监局", "NMPA", "商务部", "印发", "规划", "条例", "CPI", "关税"]
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "利好", "获批", "量产", "准入"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌", "制裁", "下发"]
ALL_MONITOR_WORDS = MACRO_WORDS + BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "期指"]

# ======================
# 2. 强力数据底座
# ======================
def get_live_news_robust():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=80&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text:
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                if any(k in clean_text for k in ALL_MONITOR_WORDS):
                    if any(b in clean_text for b in BEAR_WORDS): prefix = "[⚠️致命雷区]"
                    elif any(b in clean_text for b in MACRO_WORDS): prefix = "[🌍宏观/政务]"
                    elif any(b in clean_text for b in BULL_WORDS): prefix = "[🔥产业催化]"
                    else: prefix = "[📰异动快讯]"
                    flash_news.append(f"{prefix} {clean_text[:200]}")
    except Exception as e:
        print(f"新闻源异常: {e}")
    return flash_news

def get_market_temperature():
    try:
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).text
        lines = res.strip().split(';')
        idx_data = []
        for line in lines:
            if not line: continue
            parts = line.split('~')
            if len(parts) > 32:
                idx_data.append(f"[{parts[1]}] {parts[32]}%")
        return " | ".join(idx_data) if idx_data else "板块数据盲区"
    except:
        return "大盘获取受限"

def get_expanded_spikes(mode_type):
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}
        if mode_type == "morning":
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f38"
        elif mode_type == "intraday":
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"
        else:
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=60&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f8&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f38"

        res = requests.get(url, headers=headers, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            if not code.startswith(('00', '30', '60')) or code.startswith('688'): continue
            change = s.get('f3', 0)
            if change > -6.0: codes_for_quant.append(code)
        return codes_for_quant
    except: return []

def get_quant_evidence(codes):
    if not HAS_QUANT or not codes: return "无底层数据"
    quant_reports = []
    
    for code in codes: 
        if len(quant_reports) >= 20: break 
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 35: continue
            
            close_price = df['收盘'].iloc[-1]
            ma10 = df['收盘'].rolling(10).mean().iloc[-1]
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            recent_10_max = df.tail(10)['涨跌幅'].max()
            has_zt = "近端有涨停" if recent_10_max > 9.5 else "无近端涨停"
            
            name = ak.stock_info_a_code_name().set_index('code').to_dict()['name'].get(code, "未知")
            
            quant_reports.append(f"标的[{code} {name}] 现价:{close_price:.2f}元 | 乖离:{bias5:.1f}%, 10日线支撑:{'是' if close_price>=ma10 else '否'}, {has_zt}")
        except: continue
        
    return "\n".join(quant_reports) if quant_reports else "当前池无有效解析标的。"

# ======================
# 3. 分发引擎
# ======================
def send_alert(text):
    if not text.strip(): return
    max_length = 3500 
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    if FEISHU_WEBHOOK:
        for part in parts:
            try:
                requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": part}}, timeout=10)
                time.sleep(0.5) 
            except: pass

    if TOKEN and CHAT_ID:
        for part in parts:
            try:
                res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
                if res.status_code != 200:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)
                time.sleep(0.5)
            except: pass

# ======================
# 4. 顶级合伙人 AI 大脑 (全网顶级机构逻辑注入)
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode_type, current_time):
    news_text = "\n".join(news_list[:30]) 
    
    if mode_type == "morning":
        prompt_mission = """【早盘核心定调】：
1. 挖掘今日宏观/全球/垂直政务利好，指明今日大A可能主攻的【核心主线】及【预期差】。
2. 从量化标的池中选出 3-5 只最具【集合竞价抢筹】潜力的先锋股。"""
    elif mode_type == "tail_end":
        prompt_mission = """【尾盘5只黄金潜伏计划】：
1. 必须精准推荐 5 只最优潜力的股票！
2. 绝对分散与避险：这 5 只票必须涵盖完全不同的产业题材。
3. 机构级风险定价：必须为每一只标的给出【入场逻辑】和明确的【防守底线(止损逻辑)】。"""
    elif mode_type == "review":
        prompt_mission = """【盘后机构级全维复盘】：
1. 总结今日大A情绪、宏观异动，判定题材处于【朦胧期/爆发期/高潮派发期/衰退期】的哪个阶段。
2. 给出明日的主攻方向。
3. 挖掘 3-5 只明日具备极强反包/连板潜力的标的。"""
    else:
        prompt_mission = """【盘中情报狙击】：
1. 紧盯最新突发的利好/利空，解读量化资金冲击。
2. 捕捉 2-4 只最具爆发潜力的活水标的。"""

    prompt = f"""你是华尔街顶级量化基金PM兼A股一线游资总舵主。你的绝对使命是帮我赚钱、控回撤。你精通宏观周期、量价结构(FVG缺口)、主力筹码博弈和题材生命周期。
严禁说任何废话，直接输出极其专业的深度实战交易报告！

当前时间：{current_time}
【底层绝对真实数据】：
* 大盘风向：{top_sectors}
* 真实量化活水池 (带有最新现价，这是你唯一的选股库，严禁编造代码与价格！)：\n{quant_data}
* 全网多空/宏观/政务情报：\n{news_text}

【你的核心任务】：
{prompt_mission}

【交易纪律死命令】：
1. 必须绝对忠实于我提供给你的最新现价，严禁基于历史记忆胡编乱造价格！
2. 如果推荐股票，必须给出这只票在【题材生命周期】中的具体定位，以及明确的【盈亏比估算】和【防守底线（止损动作）】。

【排版要求（硬核、穿透力、逻辑严密）】：
**🌍 宏观/政务与产业前瞻 (预期差挖掘)**
(深挖我提供的情报，美联储、部委批复等对A股流动性和板块的实质性冲击，寻找散户还没注意到的信息预期差)

**🎯 核心主攻阵地与雷区规避**
(当前资金抱团的共识在哪？哪个板块进入了【高潮派发期】必须防核按钮？)

**🗡️ 优选实战交易计划 (强制跨界分散)**
* `代码` 股票名称 (现价: X.XX元) | 题材: XXX | 阶段: [爆发期/退潮洗盘...]
  - 【催化逻辑】：(结合新闻与行业利好，为什么选它)
  - 【量价解剖】：(FVG缺口支撑、堆量情况、主力资金背离状态)
  - 【操盘计划】：(博弈次日溢价的抓手，以及明确的止损防守底线)
* (继续列举，确保题材绝对不同...)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.2).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错: {str(e)}"

# ======================
# 5. 调度中枢
# ======================
def run_radar():
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour
    minute = bjt_now.minute

    if hour == 9 and 20 <= minute <= 45:
        mode_type = "morning"
        mode_title = "🌅 09:25 早盘核心定调与机会"
    elif hour == 14 and 30 <= minute <= 59:
        mode_type = "tail_end"
        mode_title = "🎯 14:30 尾盘黄金潜伏计划"
    elif hour >= 20:
        mode_type = "review"
        mode_title = "🌑 盘后机构级深度大复盘"
    else:
        mode_type = "intraday"
        mode_title = "⚡ 盘中情报狙击与异动抓取"

    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    codes_for_quant = get_expanded_spikes(mode_type)
    quant_evidence = get_quant_evidence(codes_for_quant)

    report = f"**【顶流量化合伙人 · {mode_title}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode_type, today_str)
    report += ai_analysis

    send_alert(report)

if __name__ == "__main__":
    run_radar()
