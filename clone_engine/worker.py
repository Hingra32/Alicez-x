import time
import threading
from telebot import TeleBot
from database.mongo import clones_col
from clone_engine.bot_instance import register_bot_handlers # Iska code niche hai

# Memory me Bots ko store karne ke liye
running_bots = {}

def start_worker_loop():
    print("🏭 Worker Engine Started...")

    while True:
        try:
            # 1. Database se saare Active bots uthao
            active_clones = clones_col.find({"active": True})

            current_tokens = []

            for clone in active_clones:
                token = clone['token']
                bot_id = str(clone['_id'])
                current_tokens.append(bot_id)

                # 2. Agar ye bot pehle se nahi chal raha, to Start karo
                if bot_id not in running_bots:
                    try:
                        # Naya TeleBot Instance
                        new_bot = TeleBot(token)

                        # Is bot par commands set karo (Start, etc.)
                        register_bot_handlers(new_bot, clone)

                        # Polling alag thread me start karo
                        # 'threaded=True' zaroori hai taaki ek bot dusre ko na roke
                        t = threading.Thread(target=new_bot.infinity_polling, kwargs={'timeout': 10, 'long_polling_timeout': 5})
                        t.daemon = True
                        t.start()

                        # Memory me save karo
                        running_bots[bot_id] = {"bot": new_bot, "thread": t}
                        print(f"✅ Clone Started: {clone.get('bot_username', bot_id)}")

                        # Username Update (Agar DB me nahi hai)
                        if clone.get("bot_username") == "Loading...":
                            me = new_bot.get_me()
                            clones_col.update_one({"_id": clone['_id']}, {"$set": {"bot_username": me.username}})

                    except Exception as e:
                        print(f"❌ Error starting clone {bot_id}: {e}")

            # 3. Stop Logic (Agar DB me active False ho gaya)
            # (Note: TeleBot thread kill karna mushkil hota hai, 
            # safe tarika hai bot.stop_polling() call karna)
            active_ids = set(current_tokens)
            running_ids = set(running_bots.keys())

            bots_to_stop = running_ids - active_ids

            for bid in bots_to_stop:
                try:
                    running_bots[bid]["bot"].stop_bot() # Polling roko
                    del running_bots[bid]
                    print(f"🛑 Clone Stopped: {bid}")
                except:
                    pass

        except Exception as e:
            print(f"⚠️ Worker Loop Error: {e}")

        # Har 10 second baad check karo
        time.sleep(10)
