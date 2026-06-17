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

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ======================
# 2. 真实资金流向与盘口穿透
# ======================
def get_top_sectors():
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f14,f3,f62"
        res = requests.get(url, timeout=5).json()
        sectors = res['data']['diff']
        result = []
        for s in sectors:
            name = s['f14']
            change = s['f3']
            net_inflow = s['f62'] / 100000000 if s['f62'] else 0
            result.append(f"[{name}] 涨幅:{change}%, 净流入:{net_inflow:.1f}亿")
        return " | ".join(result)
    except:
        return "资金流向获取异常"

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
                "change": float(data[32]), "vol_ratio": float(data[49])
            }
    except: pass
    return None

# ======================
# 3. 推送引擎与大屏生成
# ======================
def send_alert(text):
    full_text = text + f"\n\n🌐 [点击查看今日可视化大屏]({GITHUB_PAGES_URL})"
    
    if SERVER_KEY:
        wx_text = full_text.replace("<b>", "**").replace("</b>", "**")
        wx_text = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', wx_text)
        requests.post(f"https://sctapi.ftqq.com/{SERVER_KEY}.send", data={"title": "A股游资内参", "desp": wx_text}, timeout=10)

    if TOKEN and CHAT_ID:
        tg_text = text + f"\n\n🌐 <a href='{GITHUB_PAGES_URL}'>点击查看今日大屏</a>"
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": tg_text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
            if res.status_code != 200:
                clean_tg_text = tg_text.replace("<b>", "").replace("</b>", "")
                clean_tg_text = re.sub(r'<a href=".*?">(.*?)</a>', r'\1', clean_tg_text)
                requests.post(tg_url, json={"chat_id": CHAT_ID, "text": clean_tg_text}, timeout=15)
        except: pass

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
            <h1>📊 A股语义雷达决策大屏 (V48)</h1>
            <p>数据更新时间：{today_str}</p>
        </div>
        <div class="container">
            <div class="card">
                <h2>🔥 今日产业链资金热力图</h2>
                <div id="chart"></div>
            </div>
            <div class="card" style="flex: 2; max-width: 800px;">
                <h2>🌑 核心战报与次日推演</h2>
                <pre>{review_text if review_text else "等待晚间 20:00 数据生成..."}</pre>
            </div>
        </div>
        <script>
            var chart = echarts.init(document.getElementById('chart'));
            var option = {{
                tooltip: {{ trigger: 'item' }},
                series: [{{
                    name: '热度', type: 'pie', radius: ['40%', '70%'],
                    itemStyle: {{ borderRadius: 10, borderColor: '#1e293b', borderWidth: 2 }},
                    label: {{ color: '#e2e8f0', fontSize: 14 }},
                    data: {pie_data_str}
                }}]
            }};
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
# 4. 游资大脑 AI 引擎 (全面升级：语义联想与过滤)
# ======================
def get_daily_review(news_list, top_sectors):
    news_text = "\n".join(news_list[:30])
    prompt = f"""你是顶级A股游资。现在进行盘后复盘。
今日全网新闻标题摘录：{news_text}
今日真实资金买入前五板块：{top_sectors}

【严格铁律】：
1. 极度精简，像军队战报，严禁废话。
2. 绝对禁推市值超 500 亿或高价大盘股！只推 50亿-300亿 且股性极其活跃的票。
3. 挖掘2条主/暗线。每条线必须推荐 5 只股票：包含 1 只核心人气风向标，加 4 只底部蓄力、有资金异动的小盘潜力股。

严格输出格式：
【大局观】一句话概括情绪与明日基调。
【最强主线】一句话逻辑。核心标的：(仅6位代码: 000001,000002...共5只)。
【潜伏暗线】一句话逻辑。核心标的：(仅6位代码: 000003,000004...共5只)。
【避险防雷】一句话指出明日退潮坚决不碰的方向。"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return escape_html(response.choices[0].message.content.strip())
    except: return "复盘推演失败。"

def get_semantic_intraday_alert(latest_news_list, top_sectors, keywords_str):
    news_text = "\n".join(latest_news_list)
    prompt = f"""你是A股敏锐的游资情报官。
请通过【语义联想】阅读以下最新获取的新闻标题，寻找是否有引发A股炒作的爆点（哪怕新闻里没带我们词库里的字眼，只要实质利好也要挑出来）。
我们关注的核心领域参考：{keywords_str}
当前市场资金主攻方向：{top_sectors}

最新新闻：
{news_text}

任务：
如果在这批新闻中发现了【极具A股炒作价值】的情报，请挑选出最核心的 1 条进行推演。如果没有，只回复“无”。
如果有，严格按此格式输出（总字数控制在100字内）：
📌 【题材命中】（写出利好的板块名称）
【事件本质】（一句话大白话翻译）
【资金推演】（一句话说明利好什么细分环节）
【龙头与潜力】（给5只50-300亿市值、低位活跃的相关标的代码，仅6位数字，逗号隔开）"""
    try:
        response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return escape_html(response.choices[0].message.content.strip())
    except: return "无"

# ======================
# 5. 雷达主控板
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

    # 用于大屏饼图的粗略统计（字面匹配依然适用于画图，保证效率）
    topic_counts = {}
    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched: topic_counts[topic] = len(matched)
        
    top_sectors = get_top_sectors()

    # 模式 A：晚上 20:00 以后触发【宏观大局观复盘】
    if current_hour >= 20:
        message_body = f"<b>【🌑 守夜人：极致战报与精选】 {today_str}</b>\n\n"
        message_body += f"💰 <b>今日资金主攻：</b>\n{top_sectors}\n\n"
        
        review_text = get_daily_review(titles_only, top_sectors)
        message_body += f"{review_text}\n\n"
        
        stock_codes = re.findall(r'\b[036]\d{5}\b', review_text)
        if stock_codes:
            message_body += "📊 <b>核心标的量价穿透验证：</b>\n"
            for code in list(dict.fromkeys(stock_codes))[:10]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥异动" if real_data['vol_ratio'] > 1.5 else "➖潜伏"
                    message_body += f" • {real_data['name']}({code}) 涨:{real_data['change']}% 量:{real_data['vol_ratio']} ({status})\n"
        
        send_alert(message_body)
        generate_dashboard(topic_counts, review_text, today_str) 
        return 

    # 模式 B：白天盘中触发【AI 语义刺客狙击】
    message_body = f"<b>【☀️ 刺客雷达：盘中情报】 {today_str}</b>\n\n"
    
    # 取最新的20条新闻发给AI进行“语义过滤”，不再依赖死板匹配
    latest_20_news = titles_only[:20] if len(titles_only) > 20 else titles_only
    keywords_str = "、".join(KEYWORDS.keys())
    
    semantic_alert = get_semantic_intraday_alert(latest_20_news, top_sectors, keywords_str)
    
    if semantic_alert != "无" and "【事件本质】" in semantic_alert:
        # 如果AI语义引擎抓到了东西
        decision_clean = semantic_alert
        stock_codes = re.findall(r'\b[036]\d{5}\b', semantic_alert)
        if stock_codes:
            decision_clean += "\n📊 <b>实时盘口状态：</b>\n"
            for code in list(dict.fromkeys(stock_codes))[:5]:
                real_data = get_realtime_stock_data(code)
                if real_data:
                    status = "🔥" if real_data['vol_ratio'] > 1.5 else "➖"
                    decision_clean += f" • {status}{real_data['name']} 涨:{real_data['change']}% 量:{real_data['vol_ratio']}\n"

        message_body = f"💰 <b>盘中主力资金：</b>\n{top_sectors}\n\n" + decision_clean
        send_alert(message_body)
    else:
        # 心跳包
        send_alert(f"<b>【雷达心跳】 {today_str}</b>\n\nAI语义扫描未发现高爆发价值情报。\n💰 <b>目前资金主攻：</b>\n{top_sectors}")
        
    generate_dashboard(topic_counts, "", today_str)

if __name__ == "__main__":
    run_radar()
