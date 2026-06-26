import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import hashlib
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
CACHE_FILE = "data/sent_news.json"

# 多空双轨监控词库
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "涨停", "利好"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌"]
ALL_MONITOR_WORDS = BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "融资", "期指", "央行"]

# ======================
# 2. 强力数据底座 
# ======================
def get_live_news_robust():
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=40&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ALL_MONITOR_WORDS):
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                prefix = "[⚠️利空]" if any(b in clean_text for b in BEAR_WORDS) else ("[🔥利好]" if any(b in clean_text for b in BULL_WORDS) else "[📰快讯]")
                flash_news.append(f"{prefix} {clean_text[:150]}") 
    except Exception as e:
        print(f"新闻源获取失败: {e}")
    return flash_news

def get_market_temperature():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        return " | ".join(result) if result else "板块数据暂时盲区"
    except:
        return "大盘数据获取受限，激活盲飞逻辑"

def get_expanded_spikes():
    """
    【扩容池子】：把池子扩大到前30名异动，解决漏掉好票的问题。
    底层第一道防线：剔除垃圾股，绝不看跌停股。
    """
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            if not code.startswith(('00', '30', '60')) or code.startswith('688'):
                continue
            change = s.get('f3', 0)
            # 融合截图逻辑：今日涨幅必须 > -5%，不接飞刀
            if change > -5.0 and s.get('f38', 0) > 2.0:
                codes_for_quant.append(code)
        return codes_for_quant
    except Exception as e:
        print(f"异动获取异常: {e}")
        return []

def get_quant_evidence(codes):
    """
    【核心计算】：融合抖音选股截图的高阶趋势过滤逻辑。
    """
    if not HAS_QUANT or not codes: return "无量化数据支撑"
    quant_reports = []
    
    # 虽然拿到30只，但在计算这层进行数学过滤，最后只给AI最优的证据
    for code in codes: 
        if len(quant_reports) >= 12: break # 最多喂给AI 12只经过严筛的标的
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 35: continue
            
            # 基础数据
            recent_3 = df.tail(3)
            recent_10 = df.tail(10)
            close_price = df['收盘'].iloc[-1]
            
            # 融合截图逻辑1：近3日无跌停 (跌幅不低于-9.5%)
            if recent_3['涨跌幅'].min() < -9.5: continue
            
            # 融合截图逻辑2：近期有涨停基因 (近10日最大涨幅>9.5%)
            if recent_10['涨跌幅'].max() < 9.5: continue
            
            # 融合截图逻辑3：趋势护航 (股价在10日线上)
            ma10 = df['收盘'].rolling(10).mean().iloc[-1]
            ma30 = df['收盘'].rolling(30).mean().iloc[-1]
            if close_price < ma10: continue
            
            # 计算乖离与状态
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            trend_status = "多头护航" if ma10 > ma30 else "趋势震荡"
            
            # 获取股票名称 (简化调用)
            name = ak.stock_info_a_code_name().set_index('code').to_dict()['name'].get(code, "未知")
            
            quant_reports.append(f"标的[{code} {name}]: 5日乖离{bias5:.1f}%, 10日线支撑:{trend_status}, 具备涨停基因, 近3日未核按钮。")
        except: continue
        
    return "\n".join(quant_reports) if quant_reports else "经过[趋势+涨停+防飞刀]量化模型过滤，当前异动池无完全达标标的。"

# ======================
# 3. 强力分发引擎
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
            except Exception as e:
                print(f"飞书推送报错: {e}")

    if TOKEN and CHAT_ID:
        for part in parts:
            try:
                res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
                if res.status_code != 200:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)
                time.sleep(0.5)
            except Exception as e:
                print(f"Telegram推送报错: {e}")

# ======================
# 4. 游资合伙人 AI 大脑
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode):
    news_text = "\n".join(news_list[:20])
    
    prompt = f"""你是我的顶级数字游资合伙人。现在是【{mode}】。
请抛弃所有敷衍的精简模式，用实盘操盘手的第一视角，进行万字级的深度剖析！

【当前全息盘面数据】：
* 宏观资金温度：{top_sectors}
* 经过量化模型(防接飞刀+涨停基因+均线护航)严筛后存活的真实标的：\n{quant_data}
* 多空快讯：\n{news_text}

【合伙人核心作业（违令必究）】：
1. 绝对规避代码幻觉：如果上方“存活的真实标的”为空，或者你认为不可靠，直接输出“今日量价模型未能筛出绝对安全标的，管住手”。【绝对不准凭空捏造任何代码】！
2. 强制题材分散（避险铁律）：满仓可以，但不能同板块赴死！如果你推荐了 3-5 只标的，它们【必须分属完全不同的题材/行业】（比如：一只算力、一只医药、一只券商）。如果出现两只同属一个热门板块，就是重大风控违规！
3. 验尸级微观解剖：对于选出的每一只真实标的，必须带出完整的 6位代码+名字。并且详细剖析它的【量价死穴】：包含是否有 FVG公允缺口？周线是否堆量？目前的缩量回踩是否洗清了套牢盘？

【排版要求】（不要怕字数多，我要的是逻辑推演的深度）：
**🎯 市场全息定调与多空博弈深度分析**
(详细分析当前情绪周期、大资金真实意图，指出是高低切还是掩护撤退)

**🚨 雷区预警与防核指南**
(详细指出今日利空发酵区，或者量能背离可能带来的中位股绞杀风险)

**🗡️ 实战跨界潜伏池（强制分散，拒接飞刀）** (从提供的数据中选，确保每个标的题材绝对不同)
* `代码` 股票名称 [所属不同题材]
  - 【深度量价结构剖析】：(详细展开FVG缺口、堆量情况、10日线支撑确认、套牢盘密集区、洗盘动作等，体现深度)
  - 【逻辑与实战博弈点】：(这只票次日溢价的抓手在哪，如何配合新闻逻辑)
* (继续列举，必须跨行业...)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错: {str(e)}"

# ======================
# 5. 调度中枢
# ======================
def run_radar():
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour

    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    
    # 拿到扩容后的池子，并在后台完成量化严筛
    codes_for_quant = get_expanded_spikes()
    quant_evidence = get_quant_evidence(codes_for_quant)

    is_尾盘 = (14 <= hour <= 15)
    is_复盘 = hour >= 20
    
    if is_尾盘:
        mode = "🎯 尾盘量化潜伏 (防飞刀模式)"
    elif is_复盘:
        mode = "🌑 盘后万字级全维大复盘"
    else:
        mode = "🚨 盘中突发雷区预警" if any("[⚠️利空]" in n for n in live_flash) else "📡 盘中异动深度透视"

    report = f"**【游资合伙人 · {mode}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    if live_flash:
        report += "**📢 全网核心情报:**\n"
        for n in live_flash[:6]: report += f"• {n}\n"
        report += "\n---\n\n"

    # AI 只负责“看量化结果写深度研报”，不再负责“算术”
    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode)
    report += ai_analysis

    send_alert(report)

if __name__ == "__main__":
    run_radar()
