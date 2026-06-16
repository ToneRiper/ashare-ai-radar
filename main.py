import os
import json
import requests
import re
from openai import OpenAI
from datetime import datetime

# ======================
# 1. 核心配置
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ======================
# 2. 腾讯实时行情穿透接口
# ======================
def get_realtime_stock_data(stock_code):
    """
    调用腾讯财经接口，获取真实的量价异动数据。
    支持自动识别沪市(sh)和深市(sz)。
    """
    # 简单清洗代码，只保留数字
    code = re.sub(r'\D', '', str(stock_code))
    if not code or len(code) != 6: return None
    
    # 判断沪深
    prefix = "sh" if code.startswith(('6', '9')) else "sz"
    full_code = f"{prefix}{code}"
    
    try:
        url = f"http://qt.gtimg.cn/q={full_code}"
        res = requests.get(url, timeout=5)
        data = res.text.split('~')
        if len(data) > 30:
            name = data[1]           # 股票名称
            price = float(data[3])   # 当前价格
            change = float(data[32]) # 涨跌幅 %
            turnover = data[38]      # 换手率 %
            volume_ratio = data[49]  # 量比 (反人性核心指标，看资金是否突然介入)
            return {"name": name, "code": code, "change": change, "turnover": turnover, "vol_ratio": volume_ratio}
    except Exception as e:
        return None
    return None

# ======================
# 3. AI 毒舌评委 (过滤垃圾，提取代码)
# ======================
def get_ai_decision(news_title, topic):
    """
    逼迫 AI 打分，低于 7 分直接丢弃。
    同时要求 AI 返回真实的游资妖股代码。
    """
    prompt = f"""你是一个杀伐果断、反人性的 A 股顶级游资。
当前题材：【{topic}】
最新驱动事件：{news_title}

请严格按以下步骤思考并输出：
1. 若是英文先自行翻译。评估该事件对A股的【情绪爆发力】(1-10分)。
2. 若爆发力低于7分，直接回复单词：IGNORE （不要有任何其他字符）。
3. 若大于等于7分，提取出最具辨识度的 3-5 只历史妖股/龙头股代码。

如果大于等于7分，严格按以下两行格式输出：
逻辑：[30字以内极简逻辑，一语道破资金意图，绝不废话]
代码：[仅输出6位数字代码，用逗号隔开，如: 000001, 600000]
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, # 降低发散，提高代码准确度
            stream=False
        )
        return response.choices[0].message.content.strip()
    except:
        return "IGNORE"

# ======================
# 4. 强力推送引擎
# ======================
def send_alert(text):
    print("准备发送信号...")
    if SERVER_KEY:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        md_text = text.replace("<b>", "**").replace("</b>", "**")
        requests.post(sc_url, data={"title": "A股游资暗潜雷达", "desp": md_text}, timeout=10)
        
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        if res.status_code != 200:
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("💡", "").replace("🔥", "")
            requests.post(tg_url, json={"chat_id": CHAT_ID, "text": clean_text}, timeout=10)

# ======================
# 5. 主程序雷达
# ======================
def run_radar():
    print("--- 游资雷达启动：深度穿透模式 ---")
    
    # 1. 关键词库
    try:
        with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    except:
        KEYWORDS = {"低空经济": ["低空", "飞行汽车"], "算力": ["算力", "GPU"], "商业航天": ["航天", "SpaceX", "卫星"]}

    # 2. 读取新闻 (确保拿到的是最新的，这里用了倒序逆转)
    all_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in reversed(data): # 倒序，把最新的顶到前面
                        title = item if isinstance(item, str) else item.get("title", "")
                        if title: all_news.append({"title": title})
            except: pass

    # 3. 匹配与 AI 筛选
    today_str = datetime.now().strftime("%Y-%m-%d")
    message_body = f"<b>【A股异动雷达】 {today_str}</b>\n\n"
    has_target = False

    for topic, aliases in KEYWORDS.items():
        matched = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if not matched: continue
        
        latest_news = matched[0]["title"] # 取最新的一条
        
        # 将新闻交给 AI 进行 7 分过滤
        decision = get_ai_decision(latest_news, topic)
        
        if "IGNORE" in decision:
            continue # 爆发力不够，直接丢弃，不推给你看！
            
        # 解析 AI 的输出
        logic_line = "逻辑解析中..."
        stock_codes = []
        for line in decision.split('\n'):
            if line.startswith('逻辑：'): logic_line = line.replace('逻辑：', '').strip()
            if line.startswith('代码：'): 
                stock_codes = [c.strip() for c in line.replace('代码：', '').split(',') if c.strip()]

        if not stock_codes: continue # 没选出股票也跳过

        has_target = True
        message_body += f"<b>🔥 {topic}</b>\n"
        message_body += f"📰 驱动：{latest_news[:40]}...\n"
        message_body += f"💡 逻辑：{escape_html(logic_line)}\n"
        message_body += "🎯 真实量价潜伏池：\n"
        
        # 遍历 AI 给出的代码，去腾讯接口拿实时数据
        for code in stock_codes[:5]: # 最多看5只
            real_data = get_realtime_stock_data(code)
            if real_data:
                # 反人性指标：量比 > 2 代表资金突袭，换手率确保活跃
                vol_status = "🔥异动" if float(real_data['vol_ratio']) > 2.0 else "平稳"
                message_body += f" • {real_data['name']}({real_data['code']}) | 涨幅: {real_data['change']}% | 量比: {real_data['vol_ratio']} ({vol_status}) | 换手: {real_data['turnover']}%\n"
            else:
                message_body += f" • 暂无行情 ({code})\n"
        
        message_body += "--------------------\n"

    # 4. 落地推送
    if has_target:
        send_alert(message_body)
    else:
        send_alert(f"<b>【空仓警报】 {today_str}</b>\n\n所有新闻均未通过 AI 的 7分爆发力测试。无确定性逻辑，严格防守，管住手。")

if __name__ == "__main__":
    run_radar()
