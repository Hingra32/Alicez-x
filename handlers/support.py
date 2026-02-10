from loader import bot
from telebot import types
from database.mongo import tickets_col, users_col
from config import ADMIN_ID
from datetime import datetime

support_states = {}

# --- 1. SUPPORT MENU ---
@bot.callback_query_handler(func=lambda c: c.data == "help_supp")
def open_support(call):
    uid = call.from_user.id

    # RATE LIMIT LOGIC
    user = users_col.find_one({"_id": uid})
    today = datetime.now().strftime("%Y-%m-%d")

    # Default values fetch karo
    last_date = user.get("supp_date", "")
    count = user.get("supp_count", 0)

    # Agar date badal gayi, to reset karo
    if last_date != today:
        users_col.update_one({"_id": uid}, {"$set": {"supp_date": today, "supp_count": 0}})
        count = 0

    # Check Count
    if count >= 3:
        bot.answer_callback_query(call.id, "❌ Daily Limit Reached (3/3)\nTry again tomorrow.", show_alert=True)
        return

    # Allow
    support_states[uid] = "WAIT_QUERY"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="home"))

    bot.edit_message_text(
        f"🆘 *Support Center* (Used: {count}/3)\n\nApni samasya likh kar bhejein:",
        uid, call.message.message_id, reply_markup=kb, parse_mode="Markdown"
    )

# --- 2. RECEIVE QUERY ---
@bot.message_handler(func=lambda m: support_states.get(m.from_user.id) == "WAIT_QUERY")
def send_to_admin(message):
    uid = message.from_user.id
    text = message.text

    # Update Count
    users_col.update_one({"_id": uid}, {"$inc": {"supp_count": 1}})

    # Save Ticket
    ticket_id = tickets_col.insert_one({
        "user_id": uid, "query": text, "status": "open", "date": datetime.now()
    }).inserted_id

    # Send to Admin (Reports Format)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Reply", callback_data=f"rep_tix|{ticket_id}"))

    admin_msg = f"📩 *New Support Ticket*\n👤 User: `{uid}`\n📝 Query: {text}"
    try:
        bot.send_message(ADMIN_ID, admin_msg, reply_markup=kb, parse_mode="Markdown")
        bot.send_message(uid, "✅ *Message Sent!* Admin will reply soon.", parse_mode="Markdown")
    except:
        bot.send_message(uid, "❌ Error sending to admin.")

    support_states[uid] = None
