import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime, timedelta
import time

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
# 2. 强力破壁引擎 (包含异动词汇强化抓取)
# ======================
def get_live_flash_news():
    """实时抓取快讯，强化提取盘面资金异动字眼"""
    flash_news = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&num=80&version=1.2.4"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=8).json()
        items = res.get('result', {}).get('data', [])
        for item in items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full_content = title if len(title) > len(summary) else summary
            if full_content:
                # 增加了“异动、拉升、流入、走强、涨停”等盘口资金特征词
                if any(k in full_content for k in ["股", "市", "板块", "概念", "会", "政策", "公告", "产业", "异动", "拉升", "流入", "走强", "涨停"]):
                    flash_news.append(full_content[:100])
    except: pass
    return flash_news

def get_top_sectors():
    """多级降级防抖，被封锁时触发 AI 反推警报"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36', 'Referer': 'http://quote.eastmoney.com/'}
    
    # [引擎1] 东财行业资金榜
    try:
        url1 = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url1, headers=headers, timeout=4).json()
        result = [f"[{s['f14']}] {s['f3']}%" for s in res['data']['diff'] if s.get('f14')]
        if result: return " | ".join(result)
    except: pass
        
    # [引擎2] 腾讯大盘底层节点 (防封锁兜底)
    try:
        res = requests.get("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", headers=headers, timeout=4).text
        lines = res.strip().split(';')
        idx_data = []
        for line in lines:
            if not line: continue
            parts = line.split('~')
            if len(parts) > 32:
                idx_data.append(f"{parts[1]}: {parts[32]}%")
        if idx_data: return "上证/深证/创业板: " + " | ".join(idx_data) + "\n(⚠️ 接口受限，已激活【AI快讯反推资金流】模块)"
    except: pass
    
    return "(⚠️ 全网接口受限，已激活【AI快讯反推资金流】模块)"

def get_realtime_stock_data(stock_code):
    code = re.sub(r'\D', '', str(stock_code))
    if not code or len(code) != 6: return None
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        res = requests.get(url, headers=headers, timeout=4)
        data = res.text.split('~')
        if len(data) > 49:
            return {
                "name": data[1], "code": code,
                "change": float(data[32]), "vol_ratio": float(data[49]),
                "turnover": float(data[38])
            }
    except: pass
    
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        headers['Referer'] = 'https://finance.sina.com.cn'
        res = requests.get(url, headers=headers, timeout=4).text
        parts = res.split(',')
        if len(parts) > 31:
            name = parts[0].split('"')[1]
            pre_close, price = float(parts[2]), float(parts[3])
            change = round((price - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0
            return {"name": name, "code": code, "change": change, "vol_ratio": 1.2, "turnover": 5.0} 
    except: pass
    return None

# ======================
# 3. 推送与大屏
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 点击查看决策大屏: {GITHUB_PAGES_URL}"
    if SERVER_KEY:
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": full_text}, timeout=10)
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": full_text, "disable_web_page_preview": True}
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
            <h1>📊 A股逆向高透决策大屏 (V62)</h1>
            <p>实时更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 核心关注产业链热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 核心战报与异动发掘</h2>
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
        with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)
    except: pass

# ======================
# 4. 游资大脑核心 AI 引擎 (加入资金逆向提取)
# ======================
def get_semantic_intraday_alert(core_news, global_news, top_sectors, focus_keywords):
    core_text = "\n".join(core_news[:15])
    global_text = "\n".join(global_news[:25])
    
    prompt = f"""你是A股顶尖游资。市场资金数据：{top_sectors}。

【紧急铁律】：
1. 若上述资金数据带有“API/接口/网关受限”字样，说明缺失板块资金流数据。此时你必须启动【AI反推】，从以下快讯中寻找“异动”、“走强”、“拉升”、“流入”等字眼，人工推断出今日最吸金的 1-2 个板块！
2. 必须覆盖核心清单：{focus_keywords}，并在全网快讯中发掘1个破圈机会。
3. 绝对禁推千亿大盘股，推荐 4-5 只 50-300亿市值活跃先锋股，含6位代码。

【核心情报】：{core_text}
【全网快讯】：{global_text}

严格输出格式：
【AI反推资金眼】(必须有！提炼快讯中的板块异动/拉升情况，弥补资金接口缺失)
【核心阵地推演】一针见血点评核心情报，是洗盘还是主升？
【尖刀潜伏标的】(代码+名称，核心阵地相关)
【破圈异动发掘】解读全网快讯中的新题材及龙头代码。
【盘中防雷区】今日将被核按钮或退潮的板块。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "动态分析链路异常"

def get_tail_end_stocks(top_sectors):
    prompt = f"""14:50尾盘。当前风向：{top_sectors}。
挖掘 10 只“洗盘诱空、放量大绿柱”标的。市值50-300亿，禁推权重，必须是活跃游资票。只输出10个6位代码，逗号隔开。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return re.findall(r'\b[036]\d{5}\b', response.choices[0].message.content)
    except: return []

def get_daily_review(core_news, global_news, top_sectors, focus_keywords):
    core_text = "\n".join(core_news[:20])
    global_text = "\n".join(global_news[:20])
    
    prompt = f"""晚上大复盘。
资金面：{top_sectors}。
【铁律】：
1. 若资金面受限，必须根据快讯反推资金主攻板块。
2. 涵盖【核心清单】({focus_keywords})与【新破圈异动】。
3. 禁推千亿大票；主暗线各挖3-5只(50-300亿)活跃代码。

【核心情报】：{core_text}
【全网快讯】：{global_text}

格式：
【AI反推资金眼】结合快讯总结今日真实的板块资金去向。
【核心主线战旗】针对核心情报拷问。标的(含代码)：
【破圈暗线火种】挖掘新题材。标的(含代码)：
【异动冷思考】暴捶洗盘背后的真实主力逻辑。
【明日防雷区】坚决不碰的退潮方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except: return "复盘异常。"

# ======================
# 5. 雷达融合调度大中枢
# ======================
def run_radar():
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except: KEYWORDS = {}

    focus_keywords_str = "、".join(KEYWORDS.keys())
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

    live_flash = get_live_flash_news()
    core_flash = []
    global_flash = []
    
    for news in live_flash:
        if any(any(a.lower() in news.lower() for a in aliases) for aliases in KEYWORDS.values()):
            core_flash.append(news)
        else:
            global_flash.append(news)
            
    core_news = core_flash + titles_only
    global_news = global_flash

    bjt_now = datetime.utcnow() + timedelta(hours=8)
    today_str = bjt_now.strftime("%Y-%m-%d %H:%M")
    current_hour = bjt_now.hour

    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    top_sectors = get_top_sectors()
    
    final_message = f"【A股刺客雷达 · 逆向反推版】 {today_str}\n\n"
    final_message += f"💰 盘面资金风向：\n{top_sectors}\n\n"
         
    final_message += "🧠 游资大脑深层推演：\n"
    semantic_alert = get_semantic_intraday_alert(core_news, global_news, top_sectors, focus_keywords_str)
    dashboard_display_text = semantic_alert 
    final_message += f"{semantic_alert}\n"
    
    stock_codes_daily = re.findall(r'\b[036]\d{5}\b', semantic_alert)
    if stock_codes_daily:
        final_message += "\n📊 标的盘口实时侦察：\n"
        for code in list(dict.fromkeys(stock_codes_daily))[:6]:
            real_data = get_realtime_stock_data(code)
            if real_data:
                if real_data['vol_ratio'] == 0 and real_data['turnover'] == 0:
                    status = "🛑停牌/无交易"
                elif real_data['vol_ratio'] > 1.5 and real_data['turnover'] > 3.0:
                    status = "🔥抢筹活跃"
                elif real_data['turnover'] < 1.0:
                    status = "⚠️死水换手"
                else:
                    status = "➖稳健运行"
                final_message += f" • {real_data['name']}({code}) | 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"
                
    final_message += "\n" + "="*20 + "\n\n"

    # --- 14:50 尾盘附加 ---
    if current_hour == 14:
        final_message += "🎯【14:50 尾盘洗盘异动狙击】\n\n"
        candidates = get_tail_end_stocks(top_sectors)
        ambush_list = []
        for code in candidates:
            real_data = get_realtime_stock_data(code)
            if real_data and real_data['vol_ratio'] > 0:
                if -8.0 <= real_data['change'] <= -0.5 and real_data['vol_ratio'] > 1.1:
                    ambush_list.append(real_data)
        
        final_message += "🚨 诱空洗筹/大绿柱承接标的：\n"
        if ambush_list:
            for data in ambush_list[:5]:
                final_message += f" • {data['name']}({data['code']}) | 跌幅:{data['change']}% | 换手:{data['turnover']}% | <b>量比:{data['vol_ratio']}</b>\n"
            final_message += "\n💡 量化反人性逻辑：放量收绿，多为强庄极限洗筹，博弈资金回流反包。"
        else:
            final_message += "⚠️ 未发现完美符合洗盘特征标的，不建议盲动。\n"
        final_message += "\n" + "="*20 + "\n\n"

    # --- 20:00 晚间附加 ---
    if current_hour >= 20:
        final_message += "🌑【守夜人：极致盘后大复盘】\n\n"
        review_text = get_daily_review(core_news, global_news, top_sectors, focus_keywords_str)
        dashboard_display_text = review_text 
        final_message += f"{review_text}\n\n"
        
        stock_codes_night = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes_night:
            final_message += "📊 复盘标的盘口量价：\n"
            for code in list(dict.fromkeys(stock_codes_night))[:8]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖潜伏"
                    final_message += f" • {real_data['name']}({code}) 涨跌:{real_data['change']}% | 量比:{real_data['vol_ratio']} ({status})\n"

    send_alert(final_message)
    generate_dashboard(topic_counts, dashboard_display_text, today_str)

if __name__ == "__main__":
    run_radar()
