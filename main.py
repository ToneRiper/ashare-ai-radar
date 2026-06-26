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

# 量价分析引擎标志
try:
    import pandas as pd
    import akshare as ak
    HAS_QUANT = True
except ImportError:
    HAS_QUANT = False

# 监控词库：多空双轨
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "涨停", "利好"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌"]
ALL_MONITOR_WORDS = BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "融资", "期指", "央行"]

# ======================
# 2. 强力数据底座 (带容错与重试)
# ======================
def get_live_news_robust():
    """获取新闻，自带异常捕获，绝不让主程序崩溃"""
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
                flash_news.append(f"{prefix} {clean_text[:150]}") # 增加截取长度，保留更多信息
    except Exception as e:
        print(f"新闻源A获取失败: {e}")
        # 如果新浪挂了，这里可以优雅降级，但为了保持稳定性，暂返回空列表让系统依靠大盘数据运行
    return flash_news

def get_market_temperature():
    """大盘温度计，东财接口挂了也能降级处理"""
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        return " | ".join(result) if result else "板块数据暂时盲区"
    except:
        return "大盘数据获取受限，进入盲飞推演模式"

def get_strict_spikes():
    """
    【核心革命】：Python端物理过滤，绝不把垃圾标的喂给AI。
    这里直接剔除 688、北交所，并锁定换手和量比，只把最真实的票给AI做开卷考试。
    """
    try:
        # 获取涨速榜
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38,f49"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        valid_spikes = []
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            # 物理死命令1：只要 00, 30, 60开头，剔除科创和北交
            if not code.startswith(('00', '30', '60')) or code.startswith('688'):
                continue
            
            pull_up = s.get('f11', 0)
            change = s.get('f3', 0)
            turnover = s.get('f38', 0) # 换手率
            
            # 物理死命令2：5分钟拉升>1.2%，且当天换手>2%（剔除死水股）
            if pull_up > 1.2 and turnover > 2.0:
                valid_spikes.append(f"[{code}] {s['f14']}(拉升{pull_up}%, 涨{change}%, 换手{turnover}%)")
                codes_for_quant.append(code)
                
        return valid_spikes, codes_for_quant
    except Exception as e:
        print(f"异动获取异常: {e}")
        return [], []

def get_quant_evidence(codes):
    """【量化证据链】：Python算好给AI，不让AI瞎编"""
    if not HAS_QUANT or not codes: return "无量化数据支撑"
    quant_reports = []
    for code in codes[:10]: # 最多算10个，控制时间
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 20: continue
            df = df.tail(20)
            
            # 计算乖离与MACD
            close_price = df['收盘'].iloc[-1]
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            exp1 = df['收盘'].ewm(span=12, adjust=False).mean()
            exp2 = df['收盘'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            hist = (macd - signal) * 2
            macd_stat = "水上金叉" if (macd.iloc[-1]>0 and hist.iloc[-1]>0 and hist.iloc[-2]<=0) else ("多头" if hist.iloc[-1]>0 else "洗盘")
            
            # 计算涨停基因
            has_zt = "有涨停基因" if df.tail(10)['涨跌幅'].max() > 9.5 else "无涨停基因"
            
            quant_reports.append(f"标的[{code}]: 乖离{bias5:.1f}%, MACD{macd_stat}, {has_zt}")
        except: continue
    return "\n".join(quant_reports)

# ======================
# 3. 强力分发引擎 (解决信息被截断问题)
# ======================
def send_alert(text):
    """智能切片推送，保证万字长文不丢字，多端同步触达"""
    if not text.strip(): return
    
    max_length = 3500 # Telegram 安全限制
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    # 飞书推送
    if FEISHU_WEBHOOK:
        for part in parts:
            try:
                requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": part}}, timeout=10)
                time.sleep(0.5) # 防止发太快被限流
            except Exception as e:
                print(f"飞书推送报错: {e}")

    # Telegram 推送
    if TOKEN and CHAT_ID:
        for part in parts:
            try:
                res = requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                    json={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}, 
                    timeout=15
                )
                if res.status_code != 200:
                    # 格式容错降级
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                        json={"chat_id": CHAT_ID, "text": part.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, 
                        timeout=15
                    )
                time.sleep(0.5)
            except Exception as e:
                print(f"Telegram推送报错: {e}")

# ======================
# 4. 游资合伙人 AI 大脑 (彻底释放思考深度)
# ======================
def get_deep_analysis(news_list, top_sectors, spikes_text, quant_data, mode):
    news_text = "\n".join(news_list[:20])
    
    prompt = f"""你是我的顶级数字游资合伙人。现在是【{mode}】。
请展开深度思考，我不需要你简写，我需要你像专业机构研报一样，把逻辑揉碎了掰开分析给我看！字数不限，越透彻越好！

【当前真实市场数据（这是你的全部依据）】：
* 宏观资金温度：{top_sectors}
* 真实发生的异动标的：{spikes_text}
* 异动标的的硬核量化证据：\n{quant_data}
* 多空快讯：\n{news_text}

【你的合伙人级思考任务（死命令）】：
1. 绝对杜绝假代码：如果我要你推荐股票，你【必须且只能】从上面提供的【真实发生的异动标的】里挑选！如果池子里没有符合逻辑的，直接回答“当前无安全标的，管住手”。敢捏造一个 XXX 代码，就是严重违规！
2. 深度穿透剖析：大盘是高低切还是掩护出货？如果新闻有利空，哪些板块必须防雷？
3. 标的深度解剖（重中之重）：选出的 3-5 只股票，必须强制分散在不同题材。并且对每一只，进行详尽的【量价死穴与潜力拆解】，包括：它是否有潜在的FVG（公允价值缺口）支撑？最近的周线是否吸筹？上方套牢盘压力如何？主力是不是在刻意缩量洗盘？

【排版要求】（使用清晰的层级，内容必须详尽）：
**🎯 市场全息定调与多空博弈深度分析**
(详细分析当前情绪周期、期指或衍生品潜在影响，以及大资金真实意图，不少于200字)

**🚨 雷区预警与防核指南**
(详细指出今日利空发酵区，或高位股中位股的绞杀风险，逻辑要透彻)

**🗡️ 深度拆解：次日实战跨界潜伏池** (只从提供的数据中选，3-5只，必须带6位代码)
* `代码` 股票名称 [题材]
  - 【深度量价结构剖析】：(详细展开FVG缺口、堆量、套牢盘密集区、洗盘动作，体现专业深度)
  - 【逻辑与实战博弈点】：(这只票次日溢价的抓手在哪，结合新闻逻辑详述)
* (继续列举下一只，确保题材分散...)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错，请检查 API 或网络: {str(e)}"

# ======================
# 5. 调度中枢 (独立解耦，全天候运转)
# ======================
def run_radar():
    # 状态初始化
    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    hour = bjt_now.hour

    # 1. 抓取所有底层数据 (容错处理)
    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    spikes_list, codes_for_quant = get_strict_spikes()
    
    spikes_text = "\n".join(spikes_list) if spikes_list else "当前盘面无有效异动数据"
    quant_evidence = get_quant_evidence(codes_for_quant) if codes_for_quant else "无底层量化支撑"

    # 2. 判断当前任务模式 (不再互相挤占，全天候提供价值)
    is_尾盘 = (14 <= hour <= 15)
    is_复盘 = hour >= 20
    
    if is_尾盘:
        mode = "🎯 尾盘潜伏与日内总结"
    elif is_复盘:
        mode = "🌑 盘后万字级全维大复盘"
    else:
        # 盘中如有雷，标题见血
        mode = "🚨 盘中突发雷区预警" if any("[⚠️利空]" in n for n in live_flash) else "📡 盘中异动深度透视"

    # 3. 组装头部报表
    report = f"**【游资合伙人 · {mode}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    if live_flash:
        report += "**📢 全网核心情报:**\n"
        for n in live_flash[:6]: report += f"• {n}\n"
        report += "\n---\n\n"

    # 4. 调用 AI 深度大脑 (字数不设限)
    ai_analysis = get_deep_analysis(live_flash, top_sectors, spikes_text, quant_evidence, mode)
    report += ai_analysis

    # 5. 智能切片分发
    send_alert(report)

if __name__ == "__main__":
    run_radar()
