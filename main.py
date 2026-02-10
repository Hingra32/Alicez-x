import sys
import os
import threading
import time
from flask import Flask, request
from handlers.payments import process_webhook_signal  # <--- Import kiya

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def payment_webhook():
    data = request.json
    email = data.get('email')
    amount = data.get('amount')

    # Bas ye function call kar do, baaki kaam payments.py sambhal lega
    status = process_webhook_signal(email, amount)

    return {"status": "success", "message": status}, 200

# 1. Path Fix
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 2. Core Imports
try:
    from config import BOT_TOKEN
    from loader import bot, app
    from clone_engine.worker import start_worker_loop
    print("✅ Core Modules Loaded...")
except ImportError as e:
    print(f"❌ CORE ERROR: {e}")
    exit()

# 3. LOAD ALL HANDLERS (Correct Order)
# 🔥 RULE: Specific Commands (/admin, /settings) Sabse Upar!
try:
    print("⏳ Loading Handlers...")

    # --- VIP HANDLERS (Priority High) ---
    import handlers.admin          # ✅ Sabse Pehle Load Hoga
    import handlers.my_clones      # ✅ Phir Settings Load Hoga

    # --- FEATURE HANDLERS ---
    import handlers.clone_maker    # Clone Create Logic
    import handlers.clone_settings # Clone Manage Logic
    import handlers.payments       # Payments
    import handlers.support        # Support
    import handlers.users          # User Info

    # --- FALLBACK HANDLER (Priority Low) ---
    import handlers.start          # ✅ Sabse Last Me (Safe)

    print("✅ All Handlers Loaded Successfully!")

except ImportError as e:
    print(f"\n❌ HANDLER ERROR: {e}")
    print("💡 Hint: Check karo ki 'handlers' folder me __init__.py aur baaki files hain ya nahi.\n")

# 4. BACKGROUND TASKS
def run_flask_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

def run_clone_worker():
    start_worker_loop()

# Threads
threading.Thread(target=run_flask_server, daemon=True).start()
threading.Thread(target=run_clone_worker, daemon=True).start()

# 5. MAIN BOT LOOP
if __name__ == "__main__":
    print("\n🚀 MANAGER BOT IS ONLINE!")
    print(f"👉 Telegram par jakar check karein.")

    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=10, long_polling_timeout=5)

        except Exception as e:
            print(f"❌ Main Bot Crash: {e}")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)
