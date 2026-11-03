import os
import time
import json
import datetime
import urllib.parse
import feedparser
import requests
from google import genai
from google.genai import types

# ১. কনফিগারেশন এবং এপিআই কি
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def gn_bn(query):
    """বাংলা গুগলের ২৪ ঘণ্টার সার্চ ফিড তৈরি করে"""
    q = urllib.parse.quote(f"{query} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=bn&gl=BD&ceid=BD:bn"

def gn_en(query):
    """ইংরেজিতে নির্দিষ্ট ব্যক্তি বা বিষয়ের ২৪ ঘণ্টার সার্চ ফিড তৈরি করে"""
    q = urllib.parse.quote(f"{query} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-BD&gl=BD&ceid=BD:en"

# ২. ফেসবুক, রাজনীতি, টকশো ও পডকাস্টের টার্গেটেড সোর্স
RSS_SOURCES = {
    # ফ্যাক্ট চেক ও গুজব স্ক্যানার
    "FACT_CHECK_RUMOR_SCANNER": "https://rumorscanner.com/feed",
    "FACT_CHECK_DISMISLAB_BN": "https://dismislab.com/feed/",
    "FACT_CHECK_DISMISLAB_EN": "https://en.dismislab.com/feed/",
    
    # ফেসবুক স্ট্যাটাস ও ভাইরাল আলোচনা
    "FB_VIRAL_POSTS_BN": gn_bn('"ফেসবুক পোস্টে" OR "ফেসবুক স্ট্যাটাসে" OR "ফেসবুক লাইভে" OR "ভাইরাল"'),
    
    # এনসিপি, হাসনাত আবদুল্লাহ, নাসিরউদ্দিন পাটোয়ারী, তাহসিন রিয়াজ ও অন্যান্য নেতা
    "NCP_AND_LEADERS_BN": gn_bn('"হাসনাত আবদুল্লাহ" OR "নাসিরউদ্দিন পাটোয়ারী" OR "তাহসিন রিয়াজ" OR "জাতীয় নাগরিক পার্টি" OR "এনসিপি" OR "সারজিস আলম" OR "নাহিদ ইসলাম"'),
    
    # বিএনপি ও জামায়াতে ইসলামী
    "BNP_PULSE_BN": gn_bn('"বিএনপি" OR "তারেক রহমান" OR "মির্জা ফখরুল" OR "রুমিন ফারহানা"'),
    "JAMAAT_SHIBIR_PULSE_BN": gn_bn('"জামায়াতে ইসলামী" OR "শফিকুর রহমান" OR "ছাত্রশিবির" OR "জামায়াত"'),
    
    # টকশো ও রাজনৈতিক ডিবেট (তৃতীয় মাত্রা, যমুনা, চ্যানেল ২৪, চ্যানেল ওয়ান, একাত্তর)
    "TALK_SHOWS_BN": gn_bn('"টকশো" OR "তৃতীয় মাত্রা" OR "যমুনা টিভি" OR "চ্যানেল ২৪" OR "চ্যানেল ওয়ান" OR "একাত্তর টিভি"'),
    
    # পডকাস্ট ও ক্রিয়েটর (2 Cents Podcast, Trinomial Podcast, এনায়েত চৌধুরী, খালিদ ফারহান ইত্যাদি)
    "PODCASTS_AND_CREATORS": gn_en('("2 Cents Podcast" OR "Trinomial Podcast" OR "Enayet Chowdhury" OR "Khalid Farhan" OR "Sadman Sadik" OR "Tahsin Riaz")'),
    
    # সাধারণ প্রধান খবর
    "NEWS_JAGONEWS_BN": "https://www.jagonews24.com/rss/rss.xml",
}

REDDIT_SUBS = ["bangladesh", "Dhaka"]
HISTORY_FILE = "history_log.json"

def fetch_rss_items():
    collected = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for label, url in RSS_SOURCES.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:8]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:200]
                collected.append(f"[{label}] {title} | {summary} | Link: {link}")
        except Exception as e:
            print(f"Skipped {label}: {e}")
    return "\n".join(collected)

def fetch_reddit_flow():
    posts = []
    headers = {"User-Agent": "android:bd.nightly.pulse:v2.0 (by /u/bd_reader)"}
    for sub in REDDIT_SUBS:
        for sort_type in ["hot", "top"]:
            url = f"https://www.reddit.com/r/{sub}/{sort_type}/.json?t=day&limit=10"
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    children = r.json().get("data", {}).get("children", [])
                    for item in children:
                        d = item["data"]
                        title = d.get("title", "")
                        selftext = d.get("selftext", "")[:350].replace("\n", " ")
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
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-35:], f, ensure_ascii=False, indent=2)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        })

def generate_with_fallback(client, prompt):
    models = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro",
        "gemini-3.1-pro-preview",
        "gemini-4-argon"
    ]
    for model_name in models:
        for attempt in range(2):
            try:
                print(f"Trying {model_name} (attempt {attempt + 1}) with Google Search Grounding...")
                try:
                    config = types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                    res = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )
                except Exception:
                    res = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                if res and res.text:
                    return res.text
            except Exception as e:
                print(f"{model_name} busy or unavailable: {e}")
                time.sleep(6)
    raise RuntimeError("সকল মডেল ব্যস্ত রয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।")

def main():
    today = datetime.date.today()
    date_str = today.strftime("%d %B %Y")
    
    raw_rss = fetch_rss_items()
    raw_reddit = fetch_reddit_flow()
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    daily_prompt = f"""
    তুমি আমার ব্যক্তিগত "বাংলাদেশ ফেসবুক ও রাজনৈতিক পালস" এডিটর। আজকের তারিখ {date_str}।
    আমি ফেসবুক আনইনস্টল করেছি, তাই প্রতিদিন ঘুমানোর আগে বাংলাদেশের আসল ফেসবুক ট্রেন্ড, রাজনৈতিক আপডেট, টকশো এবং পডকাস্টের খবরগুলো আমার মতো করে গুছিয়ে দিতে হবে। 

    নিচের র ডেটা এবং তোমার গুগুল সার্চ টুল ব্যবহার করে গত ২৪-৪৮ ঘণ্টার আপডেট সংগ্রহ করো। **সম্পূর্ণ প্রতিবেদনটি সাবলীল বাংলায় (বাংলা ভাষায়)** সুন্দর ফরম্যাটে তৈরি করো:

    ১. 📱 ফেসবুক স্ট্যাটাস যুদ্ধ ও ভাইরাল বিতর্ক:
       - আজ ফেসবুক বা সামাজিক মাধ্যমে প্রধান রাজনৈতিক ব্যক্তিত্ব ও ইনফ্লুয়েন্সাররা কী পোস্ট করেছেন?
       - বিশেষভাবে চেক করো এবং জানাও: হাসনাত আবদুল্লাহ, নাসিরউদ্দিন পাটোয়ারী, তাহসিন রিয়াজ, সারজিস আলম, নাহিদ ইসলাম, রুমিন ফারহানা বা পিনাকী ভট্টাচার্যরা কী নিয়ে স্ট্যাটাস দিয়েছেন বা বিতর্ক তৈরি হয়েছে।

    ২. 🏛️ এনসিপি, বিএনপি, জামায়াত ও রাজনৈতিক আন্দোলন:
       - জাতীয় নাগরিক পার্টি (NCP), বিএনপি এবং জামায়াতে ইসলামী / ছাত্রশিবিরের আজকের রাজনৈতিক কর্মসূচি, বক্তব্য, বা অভ্যন্তরীণ আলোচনা নিয়ে বিস্তারিত জানাও। পর্দার পেছনের আসল প্রেক্ষাপট কী?

    ৩. 🎙️ টকশো ও পডকাস্ট রাডার (2 Cents, Trinomial, টিভি ডিবেট):
       - আজকের বাংলাদেশি টিভি টকশো (তৃতীয় মাত্রা, যমুনা টিভি, চ্যানেল ২৪, চ্যানেল ওয়ান, একাত্তর টিভি)-র আলোচিত বিতর্কগুলোর সারসংক্ষেপ দাও।
       - 2 Cents Podcast, The Trinomial Podcast (এনায়েত চৌধুরী, খালিদ ফারহান, সাদমান সাদিক) বা অন্যান্য জনপ্রিয় পডকাস্টের নতুন কোনো পর্ব বা আলোচনা থাকলে তা হাইলাইট করো।

    ৪. 🚨 রিউমর স্ক্যানার, স্ক্যাম ও ফ্যাক্ট-চেক সত্যতা যাচাই:
       - আজ ফেসবুকে কী ধরনের গুজব, এআই ভিডিও, ভুয়া উদ্ধৃতি বা আর্থিক কেলেঙ্কারী/স্ক্যাম ছড়াচ্ছে?
       - রিউমর স্ক্যানার ও ডিসমিসল্যাব-এর তথ্য অনুযায়ী সেগুলোকে [নিশ্চিত ভুয়া], [বিভ্রান্তিকর] বা [অযাচিভিত গসিপ] হিসেবে আলাদা করো।

    ৫. 😂 ফানি, মেমে ও নেটিজেনদের আড্ডা (r/Bangladesh ও r/Dhaka):
       - আজ রেডডিট বা সাধারণ ফেসবুক গ্রুপগুলোতে মানুষ কী নিয়ে হাসাহাসি, ট্রোল বা সমালোচনা করছে?

    আজকের সংগৃহীত ডেটা:
    {raw_rss}
    {raw_reddit}
    """
    
    daily_text = generate_with_fallback(client, daily_prompt)
    daily_digest = f"🌙 বিডি নাইটলি পালস — {date_str}\n\n" + daily_text
    send_telegram_message(daily_digest)
    
    # উইকলি ও মান্থলি হিস্ট্রি সেভ করা
    history = load_history()
    history.append({"date": str(today), "summary": daily_text})
    save_history(history)
    
    # প্রতি রবিবার উইকলি রিপোর্ট
    if today.weekday() == 6 and len(history) >= 3:
        last_7 = "\n\n---\n\n".join([f"তারিখ: {h['date']}\n{h['summary']}" for h in history[-7:]])
        weekly_prompt = f"""
        গত ৭ দিনের দৈনিক ব্রিফিংগুলো বিশ্লেষণ করে একটি '📅 সাপ্তাহিক বাংলাদেশ ইনসাইডার সামারি' বাংলায় তৈরি করো:
        - এ সপ্তাহের সবচেয়ে বড় রাজনৈতিক ও সামাজিক পরিবর্তন (এনসিপি, বিএনপি, জামায়াত)
        - সবচেয়ে আলোচিত ফেসবুক বিতর্ক, টকশো ও পডকাস্ট হাইলাইট
        - সপ্তাহের শীর্ষ গুজব ও স্ক্যামগুলোর তালিকা
        
        ডেটা:
        {last_7}
        """
        weekly_text = generate_with_fallback(client, weekly_prompt)
        send_telegram_message(f"📅 বিডি উইকলি রোল-আপ ({date_str})\n\n" + weekly_text)

    # প্রতি মাসের ১ তারিখে মান্থলি রিপোর্ট
    if today.day == 1 and len(history) >= 10:
        last_30 = "\n\n---\n\n".join([f"তারিখ: {h['date']}\n{h['summary']}" for h in history[-30:]])
        monthly_prompt = f"""
        গত এক মাসের দৈনিক ব্রিফিংগুলো বিশ্লেষণ করে একটি '📊 মাসিক বাংলাদেশ রাজনৈতিক ও সামাজিক স্টেট রিপোর্ট' বাংলায় লেখো:
        - প্রধান রাজনৈতিক গতিপ্রকৃতি, এনসিপি-বিএনপি-জামায়াত মুভমেন্ট
        - মাসের সবচেয়ে বড় ভাইরাল ওয়েব, পডকাস্ট এবং অপপ্রচারের ধরণ
        
        ডেটা:
        {last_30}
        """
        monthly_text = generate_with_fallback(client, monthly_prompt)
        send_telegram_message(f"📊 বিডি মান্থলি রিপোর্ট ({date_str})\n\n" + monthly_text)

if __name__ == "__main__":
    main()
