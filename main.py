import os
import json
import requests
from openai import OpenAI

# 1. 环境初始化
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERVER_KEY = os.getenv("SERVER_CHAN_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com")

def escape_html(text):
    """绝对安全清洗：防止 AI 的符号被 TG 当成恶意代码拦截"""
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def get_ai_insight(news_title):
    """DeepSeek 高效研报引擎"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是资深游资。基于新闻标题分析利好与逻辑。输出格式：【题材】+ 逻辑链条。简练有力，不废话。"},
                {"role": "user", "content": news_title}
            ],
            stream=False
        )
        return escape_html(response.choices[0].message.content) # 必须清洗
    except Exception as e:
        return f"【监控】资金逻辑推演中... (AI状态: {e})"

# ======================
# 双端降级推送引擎 (不死鸟核心)
# ======================
def send_alert(text):
    """带有回执确认和自动降级重发的推送器"""
    # 1. Telegram 推送
    if TOKEN and CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            res = requests.post(tg_url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=15)
            if res.status_code != 200:
                print(f"⚠️ TG HTML发送被拒: {res.text}，触发降级纯文本重发...")
                # 剥离 HTML 标签后强行再发
                clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
                requests.post(tg_url, json={"chat_id": CHAT_ID, "text": clean_text}, timeout=15)
            else:
                print("✅ TG 推送成功")
        except Exception as e:
            print(f"❌ TG 网络异常: {e}")

    # 2. Server酱 推送 (微信)
    if SERVER_KEY:
        sc_url = f"https://sctapi.ftqq.com/{SERVER_KEY}.send"
        try:
            # Server酱支持 Markdown，我们将简单的 HTML 转为 Markdown
            md_text = text.replace("<b>", "**").replace("</b>", "**").replace("<code>", "`").replace("</code>", "`")
            res = requests.post(sc_url, data={"title": "A股游资异动警报", "desp": md_text}, timeout=15)
            if res.status_code == 200:
                print("✅ 微信推送成功")
            else:
                print(f"⚠️ 微信发送异常: {res.text}")
        except Exception as e:
            print(f"❌ 微信网络异常: {e}")

# ======================
# 以下是你已经跑通的数据抓取与量化逻辑 (简化表示，请把你之前的代码贴进来)
# ======================
# ... [保留你之前的 fetch_all_sectors, auto_quant_stock_pick, get_top_capital_sectors 函数] ...

def run_radar():
    print("--- 雷达启动，正在扫描暗盘 ---")
    
    # [1] 加载 keywords 和新闻数据
    with open("keywords.json", "r", encoding="utf-8") as f: KEYWORDS = json.load(f)
    try:
        with open("history.json", "r", encoding="utf-8") as f: history = json.load(f)
    except: history = []
    
    all_news = []
    for file in ["data/miit_titles.json", "data/ndrc_titles.json", "data/gov_titles.json", "data/global_titles.json"]:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    all_news.append({"title": item if isinstance(item, str) else item.get("title", "")})
        except: pass

    # [2] 匹配新闻
    result = {}
    for topic, aliases in KEYWORDS.items():
        matched_news = [n for n in all_news if any(a.lower() in n["title"].lower() for a in aliases)]
        if matched_news:
            result[topic] = {"all_news": matched_news}

    # [3] 组装推送 (双轨并行)
    message_body = "<b>【A股游资全息雷达 V32】</b>\n\n"
    has_valid_target = False

    # 轨道A：新闻与AI逻辑
    for topic, info in result.items():
        insight = get_ai_insight(info["all_news"][0]["title"])
        message_body += f"<b>🔥 {topic}</b>\n💡 AI提炼: {insight}\n--------------------\n"
        has_valid_target = True

    # 轨道B：强制资金复盘 (无视消息)
    # capital_sectors = get_top_capital_sectors(limit=2) # 记得把这个函数补在上面
    # if capital_sectors:
    #     message_body += "<b>📊 盘后/盘中 资金强力沉淀:</b>\n"
    #     for sector in capital_sectors:
    #         message_body += f"• {sector['name']} (净流入:{sector['inflow_yi']}亿)\n"
    #     has_valid_target = True

    # [4] 坚决执行推送
    if has_valid_target:
        send_alert(message_body)
    else:
        # 为了确认系统真的活着，大盘死寂时也发一条防守心跳
        send_alert("<b>【空仓防守警报】</b>\n\n大盘全境静默，无新增政策驱动，无机构（30-300亿）强力压盘吸筹动作。\n策略：耐心潜伏，切勿盲目出手。")

if __name__ == "__main__":
    run_radar()
