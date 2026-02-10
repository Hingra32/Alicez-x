from loader import bot
from telebot import types
from database.mongo import users_col, clones_col
from utils.helpers import is_premium
from datetime import datetime

# ==========================================
# 1. USER PROFILE COMMAND (/me or /profile)
# ==========================================
@bot.message_handler(commands=['me', 'profile'])
def my_profile(message):
    uid = message.from_user.id

    # Database se user fetch karein
    user = users_col.find_one({"_id": uid})

    if not user:
        # Agar user DB me nahi hai (Rare case), to add kar do
        users_col.insert_one({
            "_id": uid, 
            "name": message.from_user.first_name,
            "joined_at": datetime.now()
        })
        user = users_col.find_one({"_id": uid})

    # Stats Calculate karein
    clone_count = clones_col.count_documents({"owner_id": uid})
    status = "💎 Premium Member" if is_premium(uid) else "👤 Free User"

    # Date formatting fix
    try:
        join_date = user.get("joined_at", datetime.now()).strftime("%d-%B-%Y")
    except:
        join_date = "Unknown"

    # Message Text
    text = (
        f"👤 *User Profile*\n\n"
        f"🆔 **ID:** `{uid}`\n"
        f"📛 **Name:** {message.from_user.first_name}\n"
        f"📅 **Joined:** {join_date}\n\n"
        f"🤖 **Total Clones:** `{clone_count}`\n"
        f"🔰 **Account Status:** {status}"
    )

    # Profile Photo ke sath bhejein
    try:
        photos = bot.get_user_profile_photos(uid)
        if photos.total_count > 0:
            bot.send_photo(message.chat.id, photos.photos[0][-1].file_id, caption=text, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ==========================================
# 2. SIMPLE ID COMMAND (/id)
# ==========================================
@bot.message_handler(commands=['id'])
def show_id(message):
    # Reply me user ID aur Chat ID dono batayega
    bot.reply_to(message, f"🆔 **User ID:** `{message.from_user.id}`\n💬 **Chat ID:** `{message.chat.id}`", parse_mode="Markdown")

# ==========================================
# 3. AUTO UPDATE USERNAME (Background Logic)
# ==========================================
# 🔥 FIX: Ye ab commands ko nahi rokega
@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"), content_types=['text'])
def update_user_info(message):
    try:
        uid = message.from_user.id
        first_name = message.from_user.first_name

        # Chupchap DB update karo (Upsert=True matlab naya hai to bana do)
        users_col.update_one(
            {"_id": uid}, 
            {"$set": {"name": first_name}}, 
            upsert=True
        )
    except Exception:
        pass 

    # NOTE: Yahan 'return' ya 'reply' mat lagana, 
    # taaki ye background me chale aur user ko disturb na kare.
