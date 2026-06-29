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

# 多空双轨监控词库 (加入了更多政务、认证类的词汇)
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "涨停", "利好", "获批", "证书", "许可", "专利"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌"]
ALL_MONITOR_WORDS = BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "融资", "期指", "央行"]

# ======================
# 2. 强力数据底座 (切换防封锁引擎)
# ======================
def get_live_news_robust():
    """获取新闻，加入容错"""
    flash_news = []
    try:
        # 新浪7x24作为宏观底座
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=50&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text and any(k in rich_text for k in ALL_MONITOR_WORDS):
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                prefix = "[⚠️利空]" if any(b in clean_text for b in BEAR_WORDS) else ("[🔥利好/突破]" if any(b in clean_text for b in BULL_WORDS) else "[📰快讯]")
                flash_news.append(f"{prefix} {clean_text[:150]}") 
    except Exception as e:
        print(f"新闻源获取失败: {e}")
    return flash_news

def get_market_temperature():
    """彻底弃用东财，切换至腾讯接口，解决受限问题"""
    try:
        # sh000001(上证), sz399001(深证), sz399006(创业板)
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).text
        lines = res.strip().split(';')
        idx_data = []
        for line in lines:
            if not line: continue
            parts = line.split('~')
            if len(parts) > 32:
                name = parts[1]
                change_pct = parts[32]
                idx_data.append(f"[{name}] {change_pct}%")
        return " | ".join(idx_data) if idx_data else "板块数据暂时盲区"
    except:
        return "大盘数据获取受限，激活盲飞逻辑"

def get_expanded_spikes():
    """获取异动标的，自带清洗逻辑"""
    try:
        # 异动榜依然需要东财，但加上更强的伪装
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'http://quote.eastmoney.com/'
        }
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"
        res = requests.get(url, headers=headers, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            if not code.startswith(('00', '30', '60')) or code.startswith('688'):
                continue
            change = s.get('f3', 0)
            # 过滤今日大跌的飞刀
            if change > -4.0 and s.get('f38', 0) > 1.5:
                codes_for_quant.append(code)
        return codes_for_quant
    except Exception as e:
        print(f"异动获取异常: {e}")
        return []

def get_quant_evidence(codes):
    """量化特征清洗"""
    if not HAS_QUANT or not codes: return "无量化数据支撑"
    quant_reports = []
    
    for code in codes: 
        if len(quant_reports) >= 10: break 
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 35: continue
            
            recent_3 = df.tail(3)
            recent_10 = df.tail(10)
            close_price = df['收盘'].iloc[-1]
            
            if recent_3['涨跌幅'].min() < -9.5: continue
            if recent_10['涨跌幅'].max() < 9.5: continue
            
            ma10 = df['收盘'].rolling(10).mean().iloc[-1]
            if close_price < ma10: continue
            
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            name = ak.stock_info_a_code_name().set_index('code').to_dict()['name'].get(code, "未知")
            quant_reports.append(f"标的[{code} {name}]: 5日乖离{bias5:.1f}%, 10日线支撑确认, 具备涨停基因, 近3日未核按钮。")
        except: continue
        
    return "\n".join(quant_reports) if quant_reports else "当前异动池无完全达标标的。"

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
                pass

    if TOKEN and CHAT_ID:
        for part in parts:
            try:
                res = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=15)
                if res.status_code != 200:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": part.replace('*', '').replace('_', ''), "disable_web_page_preview": True}, timeout=15)
                time.sleep(0.5)
            except Exception as e:
                pass

# ======================
# 4. 游资合伙人 AI 大脑 (绝对无废话机器)
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode):
    news_text = "\n".join(news_list[:20])
    
    prompt = f"""【系统死命令】：你是一个冰冷的、无感情的情报输出机器。绝对不准包含任何开场白、问候语或解释性的废话（如“好的，这是报告”）。直接从标题开始输出正文内容！

当前任务：【{mode}】
【盘面硬核数据】：
* 大盘温度：{top_sectors}
* 存活的真实标的：\n{quant_data}
* 快讯：\n{news_text}

【战术执行纪律】：
1. 代码锁死：只准从上方“存活的真实标的”中选，绝对禁止自己编造。如果没有合适的，直接回复“量价模型未捕捉到安全标的”。
2. 绝对分散：如果推荐2只以上标的，必须确保它们分属【完全不同】的概念板块，以分散风险。
3. 验尸级拆解：每只票必须写明6位代码及名称，深入分析其量价死穴（FVG缺口、套牢盘厚度、洗盘迹象、明日博弈点）。

【严格排版】：
**🎯 市场全息定调**
(深度分析情绪周期与大资金意图)

**🚨 雷区预警与防核**
(指出利空发酵区或量价背离陷阱)

**🗡️ 实战跨界潜伏池（强制题材分散）**
* `代码` 股票名称 [所属唯一题材]
  - 【深度结构剖析】：(详细展开FVG缺口、堆量、套牢盘情况)
  - 【实战博弈点】：(结合新闻与量价的次日溢价抓手)
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

    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    
    codes_for_quant = get_expanded_spikes()
    quant_evidence = get_quant_evidence(codes_for_quant)

    is_尾盘 = (14 <= hour <= 15)
    is_复盘 = hour >= 20
    
    if is_尾盘:
        mode = "🎯 尾盘量化潜伏"
    elif is_复盘:
        mode = "🌑 盘后万字级大复盘"
    else:
        mode = "🚨 盘中突发雷区预警" if any("[⚠️利空]" in n for n in live_flash) else "📡 盘中异动深度透视"

    report = f"**【游资合伙人 · {mode}】** ({today_str})\n\n"
    report += f"💰 **大盘温度**: {top_sectors}\n\n"
    
    if live_flash:
        report += "**📢 全网核心情报:**\n"
        for n in live_flash[:6]: report += f"• {n}\n"
        report += "\n---\n\n"

    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode)
    report += ai_analysis

    send_alert(report)

if __name__ == "__main__":
    run_radar()
