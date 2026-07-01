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

# 【情报网重构】：加入宏观、国际、垂直部委，绝不漏掉底层驱动利好
MACRO_WORDS = ["美联储", "降息", "非农", "央行", "国务院", "工信部", "发改委", "药监局", "NMPA", "商务部", "印发", "规划", "条例"]
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "利好", "获批", "量产"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌", "制裁"]
ALL_MONITOR_WORDS = MACRO_WORDS + BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "期指"]

# ======================
# 2. 强力数据底座
# ======================
def get_live_news_robust():
    flash_news = []
    try:
        # 扩大抓取量至 80 条，防止遗漏
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=80&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text:
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                if any(k in clean_text for k in ALL_MONITOR_WORDS):
                    # 智能打标签
                    if any(b in clean_text for b in BEAR_WORDS): prefix = "[⚠️重磅利空]"
                    elif any(b in clean_text for b in MACRO_WORDS): prefix = "[🌍宏观/政务]"
                    elif any(b in clean_text for b in BULL_WORDS): prefix = "[🔥产业利好]"
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
    """根据时间段智能切换异动抓取策略"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}
        if mode_type == "morning":
            # 盘前/早盘：抓取竞价和资金抢筹榜
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f38"
        elif mode_type == "intraday":
            # 盘中：抓 5分钟急速拉升 (f11)
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"
        else:
            # 尾盘/复盘：抓全天高换手活跃池 (f8)
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=60&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f8&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f38"

        res = requests.get(url, headers=headers, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            # 剔除大票/科创/北交，只保留 00/30/60
            if not code.startswith(('00', '30', '60')) or code.startswith('688'): continue
            change = s.get('f3', 0)
            
            # 不接暴跌飞刀
            if change > -6.0:
                codes_for_quant.append(code)
        return codes_for_quant
    except Exception as e:
        return []

def get_quant_evidence(codes):
    """【彻底杜绝价格幻觉】：强制传回真实价格与市值过滤"""
    if not HAS_QUANT or not codes: return "无底层数据"
    quant_reports = []
    
    for code in codes: 
        if len(quant_reports) >= 20: break # 给AI足够多的活水备选
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
            
            # 核心修复：把真实【现价】写死送给 AI，断绝幻觉！
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
# 4. 顶级合伙人 AI 大脑 (四轴驱动提示词)
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode_type, current_time):
    news_text = "\n".join(news_list[:30]) # 给足新闻
    
    # 根据时间段，彻底切换AI的工作重点
    if mode_type == "morning":
        prompt_mission = """【早盘核心定调】：
1. 挖掘今日宏观/全球利好，指明今日大A可能主攻的方向。
2. 从量化标的池中选出 3-5 只最具【集合竞价抢筹】潜力的先锋股。"""
    elif mode_type == "tail_end":
        prompt_mission = """【尾盘5只黄金潜伏】：
1. 必须精准推荐 5 只最优潜力的股票，绝不多推或少推！
2. 绝对分散：这 5 只票必须涵盖完全不同的产业题材（龙头、次龙、补涨皆可搭配）。
3. 价格亲民：不选百元大票，挑选价格适中、极具次日溢价空间（N字反包、缩量回踩）的标的。"""
    elif mode_type == "review":
        prompt_mission = """【盘后全维度深度复盘】：
1. 详细总结今日大A情绪、利好/利空发酵情况。
2. 给出明日的干货方向与机会。
3. 从全天高活跃池中挖掘 3-5 只明日具备极强反包/连板潜力的标的。"""
    else:
        prompt_mission = """【盘中异动与情报狙击】：
1. 紧盯最新突发的利好/利空情报，解读其对相关板块的量化冲击。
2. 从 5分钟异动池中捕捉 2-4 只最具涨停潜力或联动爆发的活水标的。"""

    prompt = f"""作为国际顶尖的量化游资合伙人，严禁说任何废话，直接按格式输出极其专业的深度研报。

当前时间：{current_time}
【底层绝对真实数据】：
* 大盘风向：{top_sectors}
* 真实量化活水池 (带有最新现价，严禁私自篡改价格或编造代码)：\n{quant_data}
* 全网多空/政务重磅情报：\n{news_text}

【你的核心任务】：
{prompt_mission}

【纪律死命令】：
1. 价格与代码必须绝对真实，直接引用我提供给你的现价！
2. 每只推荐票必须拆解【核心量价逻辑】（FVG缺口、堆量、套牢盘厚度等）和【题材驱动逻辑】。

【排版要求（层次分明，内容详实）】：
**🌍 全球与国内宏观/产业前瞻**
(深挖我提供的新闻，分析政策落地、国际波动对大A的直接影响)

**🎯 核心阵地与雷区避险**
(今日资金主攻方向是什么？哪些板块面临利空或兑现压力必须规避？)

**🗡️ 优选实战标的池 (强制跨界分散)**
* `代码` 股票名称 (现价: X.XX元) | 所属板块: XXX
  - 【驱动逻辑】：(结合新闻与行业利好)
  - 【量价拆解】：(详细分析支撑位、洗盘状态、次日博弈点)
* (继续列举，确保题材绝对不同...)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错: {str(e)}"

# ======================
# 5. 调度中枢 (严格卡点执行)
# ======================
def run_radar():
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour
    minute = bjt_now.minute

    # 严格的四轴时间线判断
    if hour == 9 and 20 <= minute <= 45:
        mode_type = "morning"
        mode_title = "🌅 09:25 早盘核心定调与机会"
    elif hour == 14 and 30 <= minute <= 59:
        mode_type = "tail_end"
        mode_title = "🎯 14:30 尾盘潜伏 (5只最优优选)"
    elif hour >= 20:
        mode_type = "review"
        mode_title = "🌑 盘后深度复盘与明日沙盘"
    else:
        mode_type = "intraday"
        mode_title = "⚡ 盘中情报狙击与异动抓取"

    # 拉取数据
    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    codes_for_quant = get_expanded_spikes(mode_type)
    quant_evidence = get_quant_evidence(codes_for_quant)

    # 组装报表
    report = f"**【游资合伙人 · {mode_title}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode_type, today_str)
    report += ai_analysis

    # 分发
    send_alert(report)

if __name__ == "__main__":
    run_radar()
