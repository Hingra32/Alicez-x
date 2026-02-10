from loader import bot
from telebot import types
from database.mongo import users_col, settings_col
from utils.helpers import is_premium, get_custom_markup
from datetime import datetime

# --- 1. START COMMAND ---
@bot.message_handler(commands=["start"])
def start_command(message):
    uid = message.from_user.id
    chat_id = message.chat.id

    # 1. Save User to DB if new
    if not users_col.find_one({"_id": uid}):
        users_col.insert_one({
            "_id": uid, 
            "joined_at": datetime.now(), 
            "premium_expiry": None, 
            "is_banned": False
        })

    # 2. Fetch from DB using your EXACT keys ("config", "start_text", "start_pic")
    db_conf = settings_col.find_one({"_id": "config"})

    # Default values agar DB fetch fail ho jaye
    raw_text = "Hello {mention} welcome to official bot"
    pic = None
    premium_mode = True # Default

    if db_conf:
        # Aapke JSON fields ke mutabik data uthana
        raw_text = db_conf.get("start_text", raw_text)
        pic = db_conf.get("start_pic", None)
        premium_mode = db_conf.get("premium_mode", True)

    # 3. Text Formatting
    text = raw_text.replace("{mention}", message.from_user.first_name)
    user_is_premium = is_premium(uid)
    status = "💎 Premium" if user_is_premium else "👤 Free"
    full_text = f"{text}\n\n<b>Status:</b> {status}"

    # 4. Buttons Build
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🤖 Create Clone", callback_data="make_clone"),
        types.InlineKeyboardButton("🆘 Support", callback_data="help_supp")
    )

    # Premium button logic
    if premium_mode and not user_is_premium:
        kb.add(types.InlineKeyboardButton("💎 Buy Premium", callback_data="buy_sub_menu"))

    # Custom Buttons
    cust = get_custom_markup()
    if cust: 
        for btn in cust: kb.add(btn)

    # 5. Send Message Logic
    try:
        # String "None" ya khali string ko check karna
        if pic and str(pic).strip().lower() not in ["none", "null", ""]:
            bot.send_photo(chat_id, pic.strip(), caption=full_text, reply_markup=kb, parse_mode="HTML")
        else:
            bot.send_message(chat_id, full_text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        # Agar photo ID invalid ho (e.g. kisi aur bot ki ID ho) toh text bhej dega
        print(f"❌ Photo Error: {e}")
        bot.send_message(chat_id, full_text, reply_markup=kb, parse_mode="HTML")

# --- 2. CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda c: c.data == "home")
def back_home(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    start_command(call.message)
