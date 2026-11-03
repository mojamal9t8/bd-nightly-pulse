import os
import json
import datetime
import feedparser
import requests
from google import genai

# 1. Configuration & Sources
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_SOURCES = {
    "FACT_CHECK_RUMOR_SCANNER": "https://rumorscanner.com/feed",
    "FACT_CHECK_DISMISLAB": "https://dismislab.com/feed/",
    "FACT_CHECK_DISMISLAB_EN": "https://en.dismislab.com/feed/",
    "NEWS_PROTHOM_ALO_EN": "https://en.prothomalo.com/feed/",
    "NEWS_DAILY_STAR": "https://www.thedailystar.net/frontpage/rss.xml",
    "NEWS_JAGONEWS_BN": "https://www.jagonews24.com/rss/rss.xml",
    "TALK_SHOWS_AND_SPEECHES": "https://news.google.com/rss/search?q=Bangladesh+(%22talk+show%22+OR+speech+OR+movement+OR+podcast+OR+Tritiyo+Matra)+when:1d&hl=en-BD&gl=BD&ceid=BD:en",
}

REDDIT_SUBS = ["bangladesh", "Dhaka"]
HISTORY_FILE = "history_log.json"

def fetch_rss_items():
    collected = []
    headers = {"User-Agent": "Mozilla/5.0 (Android; BD-Pulse-Bot/1.0)"}
    for label, url in RSS_SOURCES.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:250]
                collected.append(f"[{label}] {title} | Summary: {summary} | Link: {link}")
        except Exception as e:
            print(f"Skipped {label}: {e}")
    return "\n".join(collected)

def fetch_reddit_flow():
    posts = []
    headers = {"User-Agent": "android:bd.nightly.pulse:v1.0 (by /u/bd_reader)"}
    for sub in REDDIT_SUBS:
        url = f"https://www.reddit.com/r/{sub}/top/.json?t=day&limit=12"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                children = r.json().get("data", {}).get("children", [])
                for item in children:
                    d = item["data"]
                    title = d.get("title", "")
                    selftext = d.get("selftext", "")[:300].replace("\n", " ")
                    permalink = f"https://reddit.com{d.get('permalink', '')}"
                    score = d.get("score", 0)
                    posts.append(f"[REDDIT r/{sub} | Upvotes: {score}] {title} - {selftext} ({permalink})")
        except Exception as e:
            print(f"Skipped r/{sub}: {e}")
    return "\n".join(posts)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    # Keep last 35 days for monthly rollups
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-35:], f, ensure_ascii=False, indent=2)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Split long messages cleanly if over Telegram's 4096 char limit
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        })

def main():
    today = datetime.date.today()
    date_str = today.strftime("%d %B %Y")
    
    raw_rss = fetch_rss_items()
    raw_reddit = fetch_reddit_flow()
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    daily_prompt = f"""
    You are my personal Bangladesh Nightly News & Social Flow Editor. Today is {date_str}.
    Below are today's raw feeds from Bangladesh newspapers, Fact-Checkers (Rumor Scanner, Dismislab), Talk Shows/Speeches, and Reddit (r/Bangladesh, r/Dhaka).

    Write a clean, engaging nightly briefing formatted for mobile reading on Telegram using plain text and emojis:

    1. 🇧🇩 TOP STORIES & CONTEXT TODAY:
       - Pick the 4-5 most important events (politics, movements, economy, major incidents).
       - Explain WHAT happened, WHY it matters, and the real context behind it. Include source links.

    2. 🚨 RUMOR SCANNER, SCAMS & FACT-CHECK RADAR:
       - List viral Facebook rumors, fake photos/videos, or financial scams circulating today.
       - Clearly mark each with [CONFIRMED FAKE], [MISLEADING], or [UNVERIFIED STREET CHATTER] based on Rumor Scanner and Dismislab data.

    3. 🎙️ TALK SHOWS, SPEECHES & POLITICAL PULSE:
       - Summarize key speeches, press conferences, movements, or late-night talk show debates from today.

    4. 🔥 VIRAL FLOW, MEMES & NETIZEN TALK:
       - What are normal people arguing, joking, or complaining about today on r/Bangladesh and r/Dhaka?

    RAW DATA:
    {raw_rss}
    {raw_reddit}
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=daily_prompt
    )
    daily_digest = f"🌙 BD NIGHTLY PULSE — {date_str}\n\n" + response.text
    send_telegram_message(daily_digest)
    
    # Save to history for Weekly & Monthly rollups
    history = load_history()
    history.append({"date": str(today), "summary": response.text})
    save_history(history)
    
    # 5. Weekly Rollup (Every Sunday -> weekday() == 6)
    if today.weekday() == 6 and len(history) >= 3:
        last_7 = "\n\n---\n\n".join([f"Date: {h['date']}\n{h['summary']}" for h in history[-7:]])
        weekly_prompt = f"""
        Based on the last 7 daily briefings below, create a '📅 WEEKLY BANGLADESH MACRO BRIEFING':
        - Biggest political & social shifts this week
        - Top debunked rumors & scams of the week
        - Overall mood and trajectory of the country
        
        DATA:
        {last_7}
        """
        weekly_res = client.models.generate_content(model="gemini-2.5-flash", contents=weekly_prompt)
        send_telegram_message(f"📅 BD WEEKLY ROLL-UP ({date_str})\n\n" + weekly_res.text)

    # 6. Monthly Rollup (1st of every month)
    if today.day == 1 and len(history) >= 10:
        last_30 = "\n\n---\n\n".join([f"Date: {h['date']}\n{h['summary']}" for h in history[-30:]])
        monthly_prompt = f"""
        Based on the past month's daily briefings below, write a '📊 MONTHLY BANGLADESH STATE OF THE NATION REPORT':
        - Major political movements, policy changes, and economic trends
        - Biggest viral waves, controversies, and misinformation themes of the month
        - What to watch out for next month
        
        DATA:
        {last_30}
        """
        monthly_res = client.models.generate_content(model="gemini-2.5-flash", contents=monthly_prompt)
        send_telegram_message(f"📊 BD MONTHLY REPORT ({date_str})\n\n" + monthly_res.text)

if __name__ == "__main__":
    main()
