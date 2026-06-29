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

# 多空双轨 + 垂直政务监控词库
BULL_WORDS = ["增持", "回购", "突破", "中标", "批复", "重组", "借壳", "异动", "拉升", "发布", "突发", "订单", "政策", "涨停", "利好", "获批", "证书", "许可", "专利", "NMPA", "药监局", "工信部", "发改委"]
BEAR_WORDS = ["减持", "立案", "调查", "亏损", "爆雷", "退市", "问询", "澄清", "违规", "跌停", "闪崩", "黑天鹅", "警示", "利空", "大跌"]
ALL_MONITOR_WORDS = BULL_WORDS + BEAR_WORDS + ["股", "市", "板块", "融资", "期指", "央行"]

# ======================
# 2. 强力数据底座 (日夜双轨双擎)
# ======================
def get_live_news_robust():
    """获取新闻，自带兜底机制，保证绝不为空"""
    flash_news = []
    try:
        url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&num=60&top_id=152&type=0&dpc=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        items = res.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
        
        for item in items:
            rich_text = item.get('rich_text', '')
            if rich_text:
                clean_text = re.sub(r'<[^>]+>', '', rich_text)
                # 如果包含我们的核心监控词，优先抓取
                if any(k in clean_text for k in ALL_MONITOR_WORDS):
                    prefix = "[⚠️利空]" if any(b in clean_text for b in BEAR_WORDS) else ("[🔥利好/突破]" if any(b in clean_text for b in BULL_WORDS) else "[📰快讯]")
                    flash_news.append(f"{prefix} {clean_text[:150]}")
        
        # 【兜底逻辑】：如果深夜实在没有触发关键词的新闻，强行提取前 5 条金融头条，保证大盘有情报支撑
        if not flash_news and items:
            for item in items[:5]:
                clean_text = re.sub(r'<[^>]+>', '', item.get('rich_text', ''))
                flash_news.append(f"[📡日常巡航] {clean_text[:100]}")

    except Exception as e:
        print(f"新闻源获取失败: {e}")
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
                name = parts[1]
                change_pct = parts[32]
                idx_data.append(f"[{name}] {change_pct}%")
        return " | ".join(idx_data) if idx_data else "板块数据暂时盲区"
    except:
        return "大盘数据获取受限，激活盲飞逻辑"

def get_expanded_spikes(hour):
    """
    【核心修复：日夜双轨引擎】
    盘中看异动（f11），盘后看换手（f8）。绝对保证盘后有票可复！
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}
        
        if 9 <= hour < 15:
            # 盘中：抓 5分钟异动榜 (f11)
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f11&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"
        else:
            # 盘后：抓 全天换手率活跃榜 (f8)，过滤掉死水股
            url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f8&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f3,f11,f38"

        res = requests.get(url, headers=headers, timeout=5).json()
        data = res.get('data', {}).get('diff', [])
        
        codes_for_quant = []
        for s in data:
            code = str(s.get('f12', ''))
            # 物理死规矩：00, 30, 60开头，不选科创北交
            if not code.startswith(('00', '30', '60')) or code.startswith('688'):
                continue
            
            change = s.get('f3', 0)
            turnover = s.get('f38', 0)
            
            # 不接飞刀：只要今天跌幅没超过 -5%，且换手活跃 (>3%)，统统拉进备选池！
            if change > -5.0 and turnover > 3.0:
                codes_for_quant.append(code)
                
        return codes_for_quant
    except Exception as e:
        print(f"异动获取异常: {e}")
        return []

def get_quant_evidence(codes):
    """【放宽过滤，让AI去抉择】"""
    if not HAS_QUANT or not codes: return "无底层量化数据支撑"
    quant_reports = []
    
    for code in codes: 
        if len(quant_reports) >= 15: break # 给AI喂足15个高质量备选
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if len(df) < 35: continue
            
            close_price = df['收盘'].iloc[-1]
            ma10 = df['收盘'].rolling(10).mean().iloc[-1]
            ma5 = df['收盘'].rolling(5).mean().iloc[-1]
            bias5 = (close_price - ma5) / ma5 * 100
            
            recent_10_max = df.tail(10)['涨跌幅'].max()
            has_zt = "【有涨停基因】" if recent_10_max > 9.5 else "【无近端涨停】"
            trend = "10日线上多头" if close_price >= ma10 else "破位10日线"
            
            name = ak.stock_info_a_code_name().set_index('code').to_dict()['name'].get(code, "未知")
            # 不再用 continue 杀死股票，把属性如实汇报给 AI，让 AI 根据大盘决定
            quant_reports.append(f"标的[{code} {name}]: 乖离{bias5:.1f}%, {trend}, {has_zt}。")
        except: continue
        
    return "\n".join(quant_reports) if quant_reports else "当前池无有效解析标的。"

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
# 4. 游资合伙人 AI 大脑
# ======================
def get_deep_analysis(news_list, top_sectors, quant_data, mode):
    news_text = "\n".join(news_list[:20])
    
    prompt = f"""【系统死命令】：你是一个冰冷、专业的量化游资推演机器。绝对禁止输出“好的、明白”等废话。直接输出正文！

当前模式：【{mode}】
【盘面硬核数据】：
* 大盘温度：{top_sectors}
* 今日全市场高活跃存活标的池：\n{quant_data}
* 快讯情报：\n{news_text}

【战术执行纪律（违令必究）】：
1. 强制推票底线：上方“存活标的池”中已经为你准备了当日最活跃的股票。你【必须】从中挑选 3-5 只最符合游资战法的票推荐出来，并附上完整的6位代码及名称。绝不允许因为市场弱就交白卷！
2. 强制题材分散：推荐的这 3-5 只股票，必须【绝对属于不同的产业题材】（例如不能出现两只都属半导体），必须实现仓位避险。
3. 万字级验尸拆解：对每一只推荐的票，写明它的【量价死穴】（FVG缺口支撑在哪？周线是否有堆量？上方套牢盘有多重？次日溢价的博弈点在哪？）。

【严格排版（内容必须极度详实，要长篇深度推演）】：
**🎯 市场全息定调**
(深度分析情绪周期、衍生品博弈与大资金意图。如果是盘后，详细总结今日龙虎榜和做空力量)

**🚨 雷区预警与防核**
(指出利空发酵区、中位股陷阱、或量价背离的死亡板块)

**🗡️ 深度拆解：实战跨界潜伏池（强制分散，严选3-5只）**
* `代码` 股票名称 [所属唯一题材]
  - 【深度量价结构剖析】：(详细展开FVG缺口、堆量、套牢盘厚度、洗盘质量)
  - 【次日实战博弈点】：(结合情报与量价的接力预期，哪里是买点，哪里是止损死穴)
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

    # 1. 抓底座数据
    live_flash = get_live_news_robust()
    top_sectors = get_market_temperature()
    
    # 2. 【日夜双擎】抓标的
    codes_for_quant = get_expanded_spikes(hour)
    quant_evidence = get_quant_evidence(codes_for_quant)

    # 3. 模式判定
    is_尾盘 = (14 <= hour <= 15)
    is_复盘 = hour >= 20
    
    if is_尾盘:
        mode = "🎯 尾盘潜伏狙击 (量价筛选模式)"
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

    # 4. 深度推演
    ai_analysis = get_deep_analysis(live_flash, top_sectors, quant_evidence, mode)
    report += ai_analysis

    # 5. 双重分发
    send_alert(report)

if __name__ == "__main__":
    run_radar()
