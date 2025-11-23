import os
import json
from curl_cffi import requests as crequests # <--- USING THE ANTI-BLOCK TOOL
import psycopg2
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

# --- CONFIGURATION ---
DATABASE_URL = os.environ.get("DATABASE_URL")
EXTERNAL_API_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json"

def fetch_and_clean_data():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 1️⃣ START: Job triggered", flush=True)
    conn = None
    try:
        # Pretend to be Chrome 120 using curl_cffi
        response = crequests.get(
            EXTERNAL_API_URL,
            impersonate="chrome120", 
            timeout=15
        )
        
        if response.status_code == 403:
            print("❌ BLOCKED: Railway IP is 403 Forbidden.", flush=True)
            return

        if response.status_code != 200:
            print(f"⚠️ API Error: {response.status_code}", flush=True)
            return
            
        raw_json = response.json()
        
        # Handle Data Structure
        if isinstance(raw_json, list): items = raw_json
        elif 'data' in raw_json and isinstance(raw_json['data'], list): items = raw_json['data']
        elif 'list' in raw_json: items = raw_json['list']
        elif 'data' in raw_json and 'list' in raw_json['data']: items = raw_json['data']['list']
        else: items = [raw_json]

        # Connect DB
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                period BIGINT PRIMARY KEY,
                draw_time TIMESTAMP,
                winning_number INT,
                result_color TEXT,
                result_size TEXT,
                raw_json JSONB
            );
        """)
        
        saved = 0
        for item in items:
            period = item.get('issueNumber') or item.get('period')
            number = item.get('number') or item.get('winningNumber')
            
            if period and number is not None:
                n = int(number)
                color = "Green" if n % 2 != 0 else "Red"
                if n in [0, 5]: color = "Violet"
                size = "Big" if n >= 5 else "Small"

                cur.execute("""
                    INSERT INTO history (period, draw_time, winning_number, result_color, result_size, raw_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (period) DO NOTHING;
                """, (int(period), datetime.now(), n, color, size, json.dumps(item)))
                if cur.rowcount > 0: saved += 1
        
        conn.commit()
        cur.close()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Saved {saved} new rounds.", flush=True)

    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
    finally:
        if conn: conn.close()

# --- SCHEDULER ---
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(fetch_and_clean_data, 'interval', seconds=10)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def home():
    return {"message": "Railway Bot is Running"}
