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

MACRO_WORDS = ["美联储", "降息", "非农", "央行", "国务院", "工信部", "发改委", "药监局", "NMPA", "商务部", "印发", "规划", "条例", "CPI", "关税"]
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "利好", "获批", "量产", "准入"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌", "制裁", "下发"]
ALL_MONITOR_WORDS = MACRO_WORDS + BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "期指"]

# ======================
# 2. 强力数据底座 (全面切换至 AkShare 接口，杜绝封锁)
# ======================
def get_live_news_robust():
    flash_news = []
    try:
        # 使用 AkShare 获取新浪财经 7x24 小时全球实时财经新闻
        news_df = ak.news_economic_baidu() # 百度财经/新浪接口轮换保障
        if not news_df.empty:
            for index, row in news_df.head(40).iterrows():
                text = str(row.get('摘要', '')) or str(row.get('内容', ''))
                if any(k in text for k in ALL_MONITOR_WORDS):
                    if any(b in text for b in BEAR_WORDS): prefix = "[⚠️致命雷区]"
                    elif any(b in text for b in MACRO_WORDS): prefix = "[🌍宏观/政务]"
                    elif any(b in text for b in BULL_WORDS): prefix = "[🔥产业催化]"
                    else: prefix = "[📰核心快讯]"
                    flash_news.append(f"{prefix} {text[:200]}")
    except Exception as e:
        print(f"新闻源异常: {e}")
    return flash_news

def get_market_temperature():
    try:
        # 使用 AkShare 获取 A 股核心指数实时行情
        index_df = ak.stock_zh_index_spot()
        target_indices = ['上证指数', '深证成指', '创业板指']
        filtered_df = index_df[index_df['名称'].isin(target_indices)]
        
        idx_data = []
        for index, row in filtered_df.iterrows():
            idx_data.append(f"[{row['名称']}] {row['涨跌幅']}%")
        return " | ".join(idx_data) if idx_data else "板块数据盲区"
    except:
        return "大盘获取受限"

def get_realtime_active_stocks():
    """
    【革命性修复】：使用 AkShare 抓取全市场实时行情，彻底绕开东财的反爬 IP 封锁。
    在 Python 层面完成市值、涨跌幅、换手率的绝对清洗！
    """
    if not HAS_QUANT: return []
    try:
        # 获取沪深A股实时行情
        df = ak.stock_zh_a_spot_em()
        
        # 1. 过滤代码：只要 00, 30, 60 开头，且排除 688
        df = df[df['代码'].astype(str).str.match(r'^(00|30|60)') & ~df['代码'].astype(str).str.startswith('688')]
        
        # 2. 过滤飞刀与死水：涨跌幅 > -5% (不接暴跌)，换手率 > 3% (保证活跃)
        df = df[df['涨跌幅'] > -5.0]
        df = df[df['换手率'] > 3.0]
        
        # 3. 按换手率和成交额排序，提取全市场最活跃的前 15 只股票
        df = df.sort_values(by=['换手率', '成交额'], ascending=[False, False])
        top_stocks = df.head(15)
        
        return top_stocks.to_dict('records')
    except Exception as e:
        print(f"实时行情获取异常: {e}")
        return []

def get_quant_evidence(active_stocks):
    """提取真实价格与指标，彻底杀死 AI 的价格幻觉"""
    if not active_stocks: return "当前底层接口被完全封锁或无达标数据，禁止选股。"
    
    quant_reports = []
    for stock in active_stocks:
        code = stock['代码']
        name = stock['名称']
        price = stock['最新价']
        change = stock['涨跌幅']
        turnover = stock['换手率']
        
        try:
            # 获取历史数据算均线，只取最近 15 天以加快速度
            hist_df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(hist_df) < 10: continue
            
            ma10 = hist_df['收盘'].tail(10).mean()
            ma5 = hist_df['收盘'].tail(5).mean()
            bias5 = (price - ma5) / ma5 * 100
            
            has_zt = "近端涨停基因" if hist_df.tail(10)['涨跌幅'].max() > 9.5 else "无近端涨停"
            
            # 这里的文字是直接喂给 AI 的事实，包含绝对真实的价格！
            quant_reports.append(f"【真实标的】代码:{code} 名称:{name} | 现价:{price:.2f}元 (涨幅{change}%, 换手{turnover}%) | 5日乖离:{bias5:.1f}%, 10日线支撑:{'确认' if price>=ma10 else '破位'}, {has_zt}")
        except:
            continue
            
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
# 4. 顶级合伙人 AI 大脑 (绝对反幻觉指令注入)
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode_type, current_time):
    news_text = "\n".join(news_list[:30]) 
    
    if mode_type == "morning":
        prompt_mission = "1. 挖掘今日宏观/全球/垂直政务利好预判主攻方向。\n2. 从量化标的池中选出 2-4 只最具抢筹潜力的先锋股。"
    elif mode_type == "tail_end":
        prompt_mission = "1. 从量化池中精准挑选 3-5 只极具次日溢价空间（N字反包、缩量回踩）的标的进行尾盘潜伏。\n2. 强制要求：推荐的股票必须涵盖完全不同的产业题材以分散风险。"
    elif mode_type == "review":
        prompt_mission = "1. 总结今日大A情绪与宏观利好/利空发酵。\n2. 从全天高活跃池中挖掘 3-5 只明日具备极强反包/连板潜力的标的。"
    else:
        prompt_mission = "1. 紧盯最新突发的利好/利空解读量化资金冲击。\n2. 捕捉 2-4 只最具爆发潜力的活水标的。"

    prompt = f"""你是华尔街顶级量化基金PM兼A股一线游资总舵主。你的绝对使命是帮我赚钱、控回撤。
当前时间：{current_time}

【底层绝对真实数据】：
* 大盘风向：{top_sectors}
* 真实量化活水池 (带有最新真实现价，包含代码和名字)：\n{quant_data}
* 全网多空/宏观/政务情报：\n{news_text}

【你的核心任务】：
{prompt_mission}

【！！！绝对红线与防幻觉死命令！！！】：
1. 绝对禁止编造代码与价格！如果上方【真实量化活水池】提示“无数据”或为空，你必须在选股环节明确回复“今日底层数据缺失，强行空仓观望”，绝不允许为了完成任务而凭空捏造带“XXX”的代码或假名字！
2. 如果活水池有数据，你推荐的股票必须【100%原样复制】我提供的真实6位数字代码、真实名称和真实价格。
3. 必须拆解每一只票的核心量价逻辑（FVG缺口、堆量、套牢盘厚度等）和明确的防守底线。

【排版要求】：
**🌍 宏观/政务与产业前瞻 (预期差挖掘)**
(深挖我提供的新闻，寻找散户还没注意到的信息预期差)

**🎯 核心主攻阵地与雷区规避**
(当前资金抱团的共识在哪？哪个板块必须防核按钮？)

**🗡️ 优选实战交易计划 (必须填写真实代码，强制跨界分散)**
* `[填入真实6位代码]` [填入真实股票名称] (现价: [填入真实价格]元) | 题材: [填入真实板块] 
  - 【催化逻辑】：(结合新闻与行业利好，为什么选它)
  - 【量价解剖】：(FVG缺口支撑、堆量情况、主力资金背离状态)
  - 【操盘计划】：(博弈次日溢价的抓手，以及明确的止损防守底线)
* (继续列举，确保题材绝对不同...)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.1).choices[0].message.content.strip()
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
    
    # 获取真实存活池
    active_stocks = get_realtime_active_stocks()
    quant_evidence = get_quant_evidence(active_stocks)

    report = f"**【顶流量化合伙人 · {mode_title}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    # 我把 AI 的 temperature 直接降到了 0.1，这是几乎剥夺了它“自由发挥”的极限低温，逼它只能陈述事实。
    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode_type, today_str)
    report += ai_analysis

    send_alert(report)

if __name__ == "__main__":
    run_radar()
