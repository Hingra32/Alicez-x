from loader import bot, db
from telebot import types
from database.mongo import clones_col, users_col, settings_col
from utils.helpers import is_premium
import datetime
import re
from handlers.start import start_command # Import for re-routing /start

# Note: Ab humein 'maker_states' dictionary ki zaroorat nahi hai.# Hum direct Next Step Handler use karenge.

print("✅ Clone Maker Handler Loaded!")

# ==========================================
# 1. START CREATION (BUTTON CLICK)
# ==========================================
@bot.callback_query_handler(func=lambda c: c.data == "make_clone")
def initiate_clone(call):
    uid = call.from_user.id
    print(f"🕵️ DEBUG: User {uid} clicked 'Create Clone'")

    # --- Premium Check ---
    try:
        config = settings_col.find_one({"_id": "config"})
        prem_mode = config.get("premium_mode", True) if config else True
    except:
        prem_mode = True

    if prem_mode and not is_premium(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💎 Buy Premium", callback_data="buy_sub_menu"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="home"))

        bot.edit_message_text(
            "🔒 *Premium Required*\n\nAdmin has restricted clone creation to Premium users only.", 
            uid, call.message.message_id, reply_markup=kb, parse_mode="Markdown"
        )
        return

    # --- UI Setup ---
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✖️ CANCEL ✖️", callback_data="cancel_clone"))

    text = (
        "🤖 *Create New Clone*\n\n"
        "1. Go to @BotFather\n"
        "2. Create a new bot with `/newbot`.\n"
        "3. **Send the API Token here.**\n\n"
        "📝 *You can Forward the message OR Copy-Paste the token directly.*"
    )

    # --- MESSAGE EDIT & REGISTER NEXT STEP ---
    try:
        # Message Edit karo
        msg = bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

        # 🔥 MAGIC LINE: Agla message seedha 'process_token' me jayega
        # Chahe koi bhi handler beech me aaye, ye usse override karega.
        bot.register_next_step_handler(msg, process_token)

        print(f"🕵️ DEBUG: Waiting for token from {uid} (Next Step Registered)")

    except Exception as e:
        # Agar edit fail ho jaye (e.g. Purana msg photo tha), naya bhejo
        msg = bot.send_message(uid, text, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_token)


# ==========================================
# 2. CANCEL BUTTON
# ==========================================
@bot.callback_query_handler(func=lambda c: c.data == "cancel_clone")
def cancel_process(call):
    try:
        # Step handler clear karo taaki bot token ka wait karna chhod de
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)

        bot.answer_callback_query(call.id, "❌ Cancelled")
        bot.edit_message_text("❌ Process Cancelled.", call.from_user.id, call.message.message_id)
        print(f"🕵️ DEBUG: User {call.from_user.id} Cancelled process")
    except:
        pass


# ==========================================
# 3. PROCESS TOKEN (NO DECORATOR NEEDED)
# ==========================================
# Note: Yahan ab '@bot.message_handler' ki zaroorat nahi hai
# Kyunki 'initiate_clone' function khud isse call karega.

def process_token(message):
    uid = message.from_user.id

    # Agar user ne Text ki jagah command (/start) bhej diya to cancel karo
    if message.text and message.text.startswith("/"):
        bot.clear_step_handler_by_chat_id(uid) # Clear any active step handler
        if message.text == "/start":
            bot.send_message(uid, "🚫 Process Cancelled. Redirecting to start.")
            start_command(message) # Call the start command handler
        else:
            bot.send_message(uid, "❌ Process Cancelled (Command Detected).")
        return # Always return after handling a command in this context

    text = message.text.strip()
    print(f"🕵️ DEBUG: Token received from {uid}: {text[:10]}...")

    # 1. Clean User Message (Optional)
    try: bot.delete_message(uid, message.message_id)
    except: pass

    token = None

    # LOGIC A: Forwarded Message (BotFather style)
    match_forward = re.search(r"HTTP API:\s*([a-zA-Z0-9:_]+)", text)
    if match_forward:
        token = match_forward.group(1).strip()
        print("🕵️ DEBUG: Token Found via Forward Regex")

    # LOGIC B: Direct Token Paste
    else:
        match_direct = re.match(r"^\d+:[a-zA-Z0-9_-]+$", text)
        if match_direct:
            token = text
            print("🕵️ DEBUG: Token Found via Direct Regex")
        else:
            print("🕵️ DEBUG: Invalid Token Format")
            send_error(uid, "❌ **Invalid Token Format!**\n\nPlease send a valid API Token.\nExample: `123456:ABC-DEF1234ghIkl-zyx`")
            return

    # 2. DUPLICATE CHECK
    print(f"🕵️ DEBUG: Checking DB for token: {token}")
    existing_bot = clones_col.find_one({"token": token})

    if existing_bot:
        if existing_bot.get("owner_id") == uid:
            send_error(uid, "⚠️ **You already added this bot!**\nCheck your /settings.")
        else:
            send_error(uid, "⚠️ **Bot Already Registered!**\n\nThis bot token is already being used by someone else.")
        return

    # 3. SAVE TO DB
    new_bot = {
        "owner_id": uid,
        "token": token,
        "bot_username": "Loading...",
        "active": True,
        "created_at": datetime.datetime.now(),
        "settings": {
            "auto_delete": "Off",
            "start_text": "Hello! I am a clone bot."
        }
    }

    try:
        clones_col.insert_one(new_bot)
        print("🕵️ DEBUG: Inserted into MongoDB Successfully")

        # Success Message
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⚙️ Manage Bot", callback_data="open_clone_list"))
        bot.send_message(uid, "✅ **Clone Created Successfully!**\n\nYour bot is being started in the background...", reply_markup=kb, parse_mode="Markdown")

    except Exception as e:
        print(f"🕵️ DEBUG: Database Insert Error: {e}")
        send_error(uid, f"❌ Database Error: {e}")

# Helper to retry
def send_error(uid, text):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✖️ Cancel", callback_data="cancel_clone"))

    msg = bot.send_message(uid, text, reply_markup=kb, parse_mode="Markdown")
    # 🔥 ERROR KE BAAD BHI LISTENING ON RAKHO
    bot.register_next_step_handler(msg, process_token)
