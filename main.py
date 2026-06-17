import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta

# ======================
# 1. 核心配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")
GITHUB_PAGES_URL = "https://toneriper.github.io/ashare-ai-radar/"

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

# ======================
# 2. 数据引擎
# ======================
def get_top_sectors():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=8&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, timeout=5).json()
        sectors = res['data']['diff']
        result = []
        for s in sectors:
            name = s['f14']
            change = s['f3']
            net_inflow = s['f62'] / 100000000 if s['f62'] else 0
            result.append(f"[{name}] {change}%({net_inflow:.1f}亿)")
        return " | ".join(result)
    except:
        return "数据获取异常"

def get_realtime_stock_data(stock_code):
    code = re.sub(r'\D', '', str(stock_code))
    if not code or len(code) != 6: return None
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    try:
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        res = requests.get(url, timeout=5)
        data = res.text.split('~')
        if len(data) > 49:
            return {
                "name": data[1], "code": code,
                "change": float(data[32]), "vol_ratio": float(data[49]),
                "turnover": float(data[38])
            }
    except: pass
    return None

# ======================
# 3. 推送中枢
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": full_text}, timeout=10)
        
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": full_text,
            "disable_web_page_preview": True
        }
        requests.post(tg_url, json=payload, timeout=15)

def generate_dashboard(topic_counts, review_text, today_str):
    labels = list(topic_counts.keys())
    data_values = list(topic_counts.values())
    pie_data = [{"value": val, "name": name} for val, name in zip(data_values, labels)]
    pie_data_str = json.dumps(pie_data, ensure_ascii=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="google" content="notranslate">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>游资暗潜雷达 - 决策大屏</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            body {{ background-color: #0f172a; color: #e2e8f0; font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; }}
            .header {{ text-align: center; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }}
            .header h1 {{ color: #38bdf8; margin: 0; }}
            .container {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); flex: 1; min-width: 300px; max-width: 600px; }}
            .card h2 {{ color: #fbbf24; border-bottom: 2px solid #fbbf24; padding-bottom: 10px; margin-top: 0; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 15px; line-height: 1.6; color: #cbd5e1; }}
            #chart {{ width: 100%; height: 400px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 A股语义全视野决策大屏 (V54)</h1>
            <p>更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日全网情报热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 核心战报与异动推演</h2>
                <pre>{review_text if review_text else "数据采集中..."}</pre>
            </div>
        </div>
        <script>
            var chart = echarts.init(document.getElementById('chart'));
            var option = {{ tooltip: {{ trigger: 'item' }}, series: [{{ name: '热度', type: 'pie', radius: ['40%', '70%'], itemStyle: {{ borderRadius: 10, borderColor: '#1e293b', borderWidth: 2 }}, label: {{ color: '#e2e8f0', fontSize: 14 }}, data: {pie_data_str} }}] }};
            chart.setOption(option);
        </script>
    </body>
    </html>
    """
    try:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    except: pass

# ======================
# 4. 游资大脑核心 AI 引擎
# ======================
def get_semantic_intraday_alert(latest_news_list, top_sectors):
    news_text = "\n".join(latest_news_list[:15])
    prompt = f"""你是A股顶级短线游资策略师。请深度阅读并剖析以下新闻情报，同时结合今日资金盘面({top_sectors})。

【强制执行铁律】：
1. 必须挑出最具备炒作深度或宏观定调的新闻进行深度联想，绝不能说“无”。
2. 每一个分析下，必须用游资思维进行【深度拷问】（为什么发消息？资金提前埋伏没？诱多还是突破？）。
3. 必须推荐股票！严格禁止出现千亿大盘股。只准挖掘市值在 50亿-300亿 之间、活跃的先锋股或底部蓄力补涨股，数量在 4-5 只。

新闻：
{news_text}

严格按以下格式输出（保留排版换行）：
【核心线索】摘录并总结最具爆发力的新闻。
【大局观拷问】深度联想，一针见血拷问资金意图和事件本质。
【盘口共振】分析该新闻利好与今天主力资金主攻方向是否一致。
【尖刀标的】(格式：代码 股票名称，例如: 000001 平安银行)"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return response.choices[0].message.content.strip()
    except: return "情报剖析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50 尾盘潜伏。今日主攻：{top_sectors}。
挖掘 10 只可能存在“洗盘承接”的妖股潜力种子（市值50-300亿，活跃游资票）。
只输出10个6位数字代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""晚上9点盘后复盘。结合情报({news_text})及资金流向({top_sectors})撰写。
【铁律】：必须包含国家级事件或前沿政策；深度拷问逻辑；禁推千亿市值大盘股。主线和暗线各给5只(50-300亿)活跃标的代码。

格式：
【宏观大局观】政策会议精神解读，资金情绪定调。
【主线战旗】逻辑拷问。核心标的(名字+代码)：
【暗线火种】逻辑联想。核心标的(名字+代码)：
【异动冷思考】分析今日异常板块或个股。
【避险防雷】明日退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 雷达调度大枢纽 (解除时段互斥)
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    all_news = []
    titles_only = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in reversed(data): 
                        title = item if isinstance(item, str) else item.get("title", "")
                        if title: 
                            all_news.append({"title": title})
                            titles_only.append(title)
            except: pass

    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    current_hour = bjt_now.hour

    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    top_sectors = get_top_sectors()
    
    final_message = f"【A股刺客雷达】 {today_str}\n\n"
    final_message += f"💰 实时资金主攻方向：\n{top_sectors}\n\n"

    # --- 模块 1：日常基础情报与联想 (每次必运行) ---
    final_message += "📋 近期核心情报提炼：\n"
    for title in titles_only[:3]:
         final_message += f"- {title}\n"
    final_message += "\n🧠 游资大脑跨级推演拷问：\n"
    
    semantic_alert = get_semantic_intraday_alert(titles_only, top_sectors)
    final_message += f"{semantic_alert}\n"
    
    stock_codes_daily = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes_daily:
        final_message += "\n📊 推荐标的实时盘口：\n"
        for code in list(dict.fromkeys(stock_codes_daily))[:5]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                status = "火爆抢筹" if real_data['vol_ratio'] > 1.5 else "主力锁仓"
                final_message += f" • {real_data['name']}({code}) 涨跌: {real_data['change']}% | 量比: {real_data['vol_ratio']} ({status})\n"
    final_message += "\n--------------------\n"

    # --- 模块 2：尾盘 14:00 - 14:59 附加尾盘狙击 ---
    if current_hour == 14:
        final_message += "🎯【附加模块：14:50 尾盘异常个股狙击】\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data:
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        if ambush_list:
            final_message += "🚨 尾盘洗盘放量标的：\n"
            for data in ambush_list[:5]:
                final_message += f" • {data['name']}({data['code']}) | 跌幅: {data['change']}% | 换手: {data['turnover']}% | 量比: {data['vol_ratio']}\n"
            final_message += "💡 逻辑：强主线个股放量收绿，大概率为极限洗筹，博弈次日反包高开。\n"
        else:
            forced_seeds = ["002230", "300033", "002415"] 
            final_message += "🚨 未发现完美背离标的，参考备选风向标：\n"
            for code in forced_seeds:
                d = get_realtime_stock_data(code)
                if d: final_message += f" • {d['name']}({code}) | 涨跌: {d['change']}% | 量比: {d['vol_ratio']}\n"
        final_message += "\n--------------------\n"

    # --- 模块 3：晚上 20:00 以后附加宏观复盘 ---
    review_text_for_dashboard = ""
    if current_hour >= 20:
        final_message += "🌑【附加模块：守夜人极致复盘】\n"
        review_text = get_daily_review(titles_only, top_sectors)
        review_text_for_dashboard = review_text # 用于大屏
        final_message += f"{review_text}\n"
        
        stock_codes_night = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes_night:
            final_message += "\n📊 推演标的穿透验证：\n"
            for code in list(dict.fromkeys(stock_codes_night))[:8]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "放量异动" if real_data['vol_ratio'] > 1.5 else "静默吸筹"
                    final_message += f" • {real_data['name']}({code}) 涨跌: {real_data['change']}% | 量比: {real_data['vol_ratio']} ({status})\n"

    # 执行统一推送与大屏更新
    send_alert(final_message)
    generate_dashboard(topic_counts, review_text_for_dashboard, today_str)

if __name__ == "__main__":
    run_radar()
