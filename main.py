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

MACRO_WORDS = ["美联储", "降息", "非农", "央行", "国务院", "工信部", "发改委", "药监局", "NMPA", "商务部", "印发", "规划", "条例", "CPI", "关税"]
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "利好", "获批", "量产", "准入"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌", "制裁", "下发"]
ALL_MONITOR_WORDS = MACRO_WORDS + BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "期指"]

# ======================
# 2. 基础中枢 (新闻去重)
# ======================
def load_processed_hashes():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: return set(json.load(f))
        except: return set()
    return set()

def save_processed_hashes(hashes):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f: json.dump(list(hashes), f, ensure_ascii=False)
    except: pass

# ======================
# 3. 强力数据底座 (加入价格与市值硬拦截)
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
                    else: prefix = "[📰核心快讯]"
                    flash_news.append(f"{prefix} {clean_text[:200]}")
    except Exception as e:
        pass
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

def get_realtime_active_stocks():
    if not HAS_QUANT: return []
    df = pd.DataFrame()
    
    try:
        df = ak.stock_zh_a_spot_em()
    except:
        try:
            df = ak.stock_zh_a_spot()
        except:
            return []

    if df.empty: return []

    try:
        code_col = '代码' if '代码' in df.columns else 'symbol'
        name_col = '名称' if '名称' in df.columns else 'name'
        pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'percent'
        turnover_col = '换手率' if '换手率' in df.columns else 'turnoverratio'
        amount_col = '成交额' if '成交额' in df.columns else 'amount'
        price_col = '最新价' if '最新价' in df.columns else 'trade'

        # 1. 基础过滤：代码开头与飞刀死水过滤
        df[code_col] = df[code_col].astype(str).str.extract(r'(\d{6})')[0]
        df = df.dropna(subset=[code_col])
        df = df[df[code_col].str.match(r'^(00|30|60)') & ~df[code_col].str.startswith('688')]
        
        df[pct_col] = pd.to_numeric(df[pct_col], errors='coerce').fillna(0)
        df[turnover_col] = pd.to_numeric(df[turnover_col], errors='coerce').fillna(0)
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)
        
        df = df[df[pct_col] > -5.0]
        df = df[df[turnover_col] > 3.0]
        
        # 2. 【硬性过滤1：绝对价格天花板】 拒绝百元大票，价格限制在 45 元以下
        df = df[(df[price_col] > 0) & (df[price_col] <= 45.0)]

        # 3. 【硬性过滤2：流通市值过滤】 限制在 30亿 - 200亿 之间
        cap_cols = [c for c in df.columns if '市值' in c]
        if cap_cols:
            c_name = cap_cols[0] # 通常为 '流通市值' 或 '总市值'
            df[c_name] = pd.to_numeric(df[c_name], errors='coerce').fillna(0)
            df = df[(df[c_name] >= 3e9) & (df[c_name] <= 200e9)]
        
        # 排序并取前15只最活跃标的
        df = df.sort_values(by=[turnover_col, amount_col], ascending=[False, False])
        top_stocks = df.head(15)
        
        result = []
        for _, row in top_stocks.iterrows():
            result.append({
                '代码': row[code_col],
                '名称': row[name_col],
                '最新价': float(row[price_col]),
                '涨跌幅': float(row[pct_col]),
                '换手率': float(row[turnover_col])
            })
        return result
    except Exception as e:
        print(f"数据清洗异常: {e}")
        return []

def get_quant_evidence(active_stocks):
    if not active_stocks: return "底层数据接口无符合市值/价格条件的标的。"
    quant_reports = []
    
    for stock in active_stocks:
        code, name, price, change, turnover = stock['代码'], stock['名称'], stock['最新价'], stock['涨跌幅'], stock['换手率']
        try:
            hist_df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(hist_df) < 10: continue
            
            ma10 = hist_df['收盘'].tail(10).mean()
            ma5 = hist_df['收盘'].tail(5).mean()
            bias5 = (price - ma5) / ma5 * 100
            has_zt = "近端涨停基因" if hist_df.tail(10)['涨跌幅'].max() > 9.5 else "无近端涨停"
            
            quant_reports.append(f"【真实标的】代码:{code} 名称:{name} | 现价:{price:.2f}元 (涨幅{change}%, 换手{turnover}%) | 5日乖离:{bias5:.1f}%, 10日线支撑:{'确认' if price>=ma10 else '破位'}, {has_zt}")
        except: continue
            
    return "\n".join(quant_reports) if quant_reports else "当前池无有效解析标的。"

# ======================
# 4. 分发引擎
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
# 5. 顶级合伙人 AI 大脑
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode_type, current_time):
    news_text = "\n".join(news_list[:30]) 
    
    if mode_type == "morning":
        prompt_mission = "1. 挖掘今日宏观/政务利好预判主攻方向。\n2. 从量化标的池中选出 2-4 只最具抢筹潜力的先锋股。"
    elif mode_type == "tail_end":
        prompt_mission = "1. 必须从量化池中精准挑选 3-5 只极具次日溢价空间（N字反包、缩量回踩）的标的。\n2. 强制要求：推荐的股票必须涵盖完全不同的产业题材。"
    elif mode_type == "review":
        prompt_mission = "1. 总结今日大A情绪与宏观利好/利空发酵。\n2. 从高活跃池中挖掘 3-5 只明日具备极强反包潜力的标的。"
    else:
        prompt_mission = "1. 紧盯最新突发的利好/利空解读资金冲击。\n2. 捕捉 2-4 只最具爆发潜力的活水标的。"

    prompt = f"""【最高指令】：直接输出研报正文！绝对禁止输出“指令已确认”、“身份：”、“收到”、“好的”等任何过渡性废话。

当前时间：{current_time}
【底层绝对真实数据】：
* 大盘风向：{top_sectors}
* 真实量化活水池 (这是你唯一的选股库，严禁编造代码与价格！)：\n{quant_data}
* 情报：\n{news_text}

【核心任务】：
{prompt_mission}

【防幻觉与合规底线】：
1. 绝对禁止编造代码与价格！如果上方【活水池】提示“无数据”或为空，你必须明确回复“今日底层数据缺失，强行空仓观望”。
2. 如果活水池有数据，推荐的股票必须【100%原样复制】我提供的真实6位数字代码、真实名称和真实价格。
3. 必须拆解每一只票的核心量价逻辑（FVG缺口、堆量、洗盘）和防守底线。

【排版要求】：
**🌍 宏观/政务与预期差挖掘**
(深挖我提供的新闻，分析政策落地对A股的实质性冲击)

**🎯 核心主攻阵地与雷区规避**
(资金抱团的共识在哪？哪个板块必须防跌停？)

**🗡️ 优选实战交易计划 (必须填写真实代码，强制跨界分散)**
* `[填入真实6位代码]` [填入真实股票名称] (现价: [填入真实价格]元) | 题材: [填入真实板块] 
  - 【催化逻辑】：(结合新闻与行业利好)
  - 【量价解剖】：(支撑位、洗盘状态)
  - 【操盘计划】：(买入博弈点与明确止损线)
"""
    try:
        return client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.1).choices[0].message.content.strip()
    except Exception as e:
        return f"深度推演引擎报错: {str(e)}"

# ======================
# 6. 调度中枢
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

    processed_hashes = load_processed_hashes()
    raw_flash = get_live_news_robust()
    live_flash = []
    
    for news in raw_flash:
        news_hash = hashlib.md5(news.encode('utf-8')).hexdigest()
        if news_hash not in processed_hashes:
            processed_hashes.add(news_hash)
            live_flash.append(news)
            
    save_processed_hashes(processed_hashes)
    
    is_fixed_time = mode_type in ["morning", "tail_end", "review"]
    if not live_flash and not is_fixed_time:
        return

    top_sectors = get_market_temperature()
    active_stocks = get_realtime_active_stocks()
    quant_evidence = get_quant_evidence(active_stocks)

    report = f"**【顶流量化合伙人 · {mode_title}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    ai_news_feed = live_flash if live_flash else raw_flash[:15]
    ai_analysis = get_deep_analysis(ai_news_feed, top_sectors, quant_evidence, mode_type, today_str)
    report += ai_analysis

    send_alert(report)

if __name__ == "__main__":
    run_radar()
