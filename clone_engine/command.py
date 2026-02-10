from telebot import types, TeleBot
from telebot.util import extract_argument
from loader import bot # This 'bot' should be the clone bot instance
from database.mongo import clones_col, db
from bson.objectid import ObjectId
import datetime
import re
import os
import time
import requests
import threading

# Collections
clone_files_col = db.clone_files
clone_pending_payments_col = db.clone_pending_payments
clone_users_col = db.clone_users # Stores all users, premium status, and ban status
clone_broadcast_logs = db.clone_broadcast_logs # To track message IDs for deletion

# --- Helpers ---

def get_clone_bot_settings():
    try:
        current_bot_token = bot.token
        if not current_bot_token: return None, None, None
        clone_data = clones_col.find_one({"token": current_bot_token})
        if clone_data:
            return clone_data.get("settings", {}), clone_data.get("owner_id"), clone_data
        return None, None, None
    except: return None, None, None

def is_banned(user_id, clone_bot_id):
    user = clone_users_col.find_one({"user_id": user_id, "clone_bot_id": clone_bot_id})
    return user.get("is_banned", False) if user else False

def send_log(settings, message_text):
    log_channel = settings.get("log_channel")
    if log_channel:
        try:
            bot.send_message(log_channel, f"📝 *Log:* {message_text}", parse_mode="Markdown")
        except: pass

def is_user_member(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except:
        return False

def shorten_link(url, api_key):
    if not api_key: return url
    if api_key.startswith("http"):
        req_url = f"{api_key}&url={url}" if "?" in api_key else f"{api_key}?url={url}"
        try:
            resp = requests.get(req_url).json()
            return resp.get("shortenedUrl") or resp.get("link") or resp.get("url") or url
        except: return url
    return url

OFFICIAL_BOT_USERNAME = "OfficialBotUsernamePlaceholder"
TELEGRAM_LINK_REGEX = re.compile(r"https://t\.me/(?:c/)?([^/]+)/(\d+)")

def parse_telegram_message_link(link):
    match = TELEGRAM_LINK_REGEX.match(link)
    if match:
        chat_identifier = match.group(1)
        message_id = int(match.group(2))
        if chat_identifier.isdigit() and len(chat_identifier) > 9:
            chat_id = -1000000000000 + int(chat_identifier)
        else:
            chat_id = f"@{chat_identifier}"
        return chat_id, message_id
    return None, None

# --- State ---
user_batch_data = {}
user_access_tokens = {}
user_payment_data = {}

# --- Security & Active Check Decorator ---
def clone_bot_access_check(func):
    def wrapper(message, *args, **kwargs):
        settings, owner_id, clone_data = get_clone_bot_settings()
        if not settings: return

        uid = message.from_user.id
        # Ban Check
        if is_banned(uid, clone_data["_id"]):
            bot.send_message(message.chat.id, "🚫 You are banned from using this bot.")
            return

        # Sleep Mode Check
        if not clone_data.get("active", True) and uid != owner_id:
            bot.send_message(message.chat.id, "💤 Bot is currently sleeping/under maintenance.")
            return
        
        return func(message, settings, owner_id, clone_data, *args, **kwargs)
    return wrapper

def check_cancel_next_step(message):
    if message.text and message.text.startswith("/"):
        bot.clear_step_handler_by_chat_id(message.chat.id)
        if message.text == "/start":
            clone_start_command(message) # Note: Decorated, but called internally
            return True
        elif message.text == "/cancel":
            cancel_command(message)
            return True
        else:
            bot.send_message(message.chat.id, "🚫 Action Cancelled.")
            return True
    return False

# --- Handlers ---

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_batch_data.pop(message.from_user.id, None)
    user_payment_data.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "✅ Operation cancelled.")

@bot.message_handler(commands=['start'])
def clone_start_command(message):
    settings, owner_id, clone_data = get_clone_bot_settings()
    if not settings: return
    
    uid = message.from_user.id
    # Register/Update User
    clone_users_col.update_one(
        {"user_id": uid, "clone_bot_id": clone_data["_id"]},
        {"$set": {"username": message.from_user.username, "last_active": datetime.datetime.now()}, "$setOnInsert": {"is_banned": False}},
        upsert=True
    )

    if is_banned(uid, clone_data["_id"]):
        bot.send_message(message.chat.id, "🚫 You are banned.")
        return

    if message.text and len(message.text.split()) > 1:
        handle_deep_link_start(message)
        return

    if not clone_data.get("active", True) and uid != owner_id:
        bot.send_message(message.chat.id, "💤 Bot is sleeping.")
        return

    start_text = settings.get("start_text", f"Hello! I am @{clone_data.get('bot_username', 'bot')}.")
    start_pic = settings.get("start_pic")
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("💰 Buy Premium", callback_data="buy_premium_clone"))
    kb.add(types.InlineKeyboardButton(f"🤖 Clone Your Bot", url=f"https://t.me/{OFFICIAL_BOT_USERNAME}"))
    kb.add(types.InlineKeyboardButton("ℹ️ About", callback_data="about_clone_bot"))
    for btn in settings.get("custom_btns", []):
        if btn.get("name") and btn.get("url"):
            kb.add(types.InlineKeyboardButton(btn["name"], url=btn["url"]))
    
    try:
        if start_pic: bot.send_photo(message.chat.id, start_pic, caption=start_text, reply_markup=kb, parse_mode="Markdown")
        else: bot.send_message(message.chat.id, start_text, reply_markup=kb, parse_mode="Markdown")
    except: bot.send_message(message.chat.id, start_text, reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(commands=['shortlink'])
@clone_bot_access_check
def shortlink_command(message, settings, owner_id, clone_data):
    msg = bot.send_message(message.chat.id, "📤 Send file for Short-Link (Bypasses Token Verify). /cancel to abort.")
    bot.register_next_step_handler(msg, process_shortlink_file, settings, clone_data)

def process_shortlink_file(message, settings, clone_data):
    if check_cancel_next_step(message): return
    # Reuse genlink logic but with bypass flag
    process_genlink_file(message, settings, clone_data, bypass=True)

@bot.message_handler(commands=['genlink'])
@clone_bot_access_check
def genlink_command(message, settings, owner_id, clone_data):
    msg = bot.send_message(message.chat.id, "📤 Send file for link. /cancel to abort.")
    bot.register_next_step_handler(msg, process_genlink_file, settings, clone_data)

def process_genlink_file(message, settings, clone_data, bypass=False):
    if check_cancel_next_step(message): return
    user_id = message.from_user.id
    file_info = {}
    file_type = "unknown"

    if message.text: file_info, file_type = {"content": message.text}, "text"
    elif message.photo: file_info, file_type = {"file_id": message.photo[-1].file_id, "caption": message.caption}, "photo"
    elif message.video: file_info, file_type = {"file_id": message.video.file_id, "caption": message.caption}, "video"
    elif message.document: file_info, file_type = {"file_id": message.document.file_id, "caption": message.caption}, "document"
    elif message.audio: file_info, file_type = {"file_id": message.audio.file_id, "caption": message.caption}, "audio"
    elif message.sticker: file_info, file_type = {"file_id": message.sticker.file_id}, "sticker"
    elif message.animation: file_info, file_type = {"file_id": message.animation.file_id, "caption": message.caption}, "animation"
    else: return bot.send_message(message.chat.id, "⚠️ Unsupported.")

    obj_id = ObjectId()
    clone_files_col.insert_one({
        "_id": obj_id, "clone_bot_id": clone_data["_id"], "owner_id": clone_data["owner_id"],
        "user_id": user_id, "file_type": file_type, "file_info": file_info,
        "created_at": datetime.datetime.now(), "auto_delete_time": settings.get("auto_delete", "Off"),
        "bypass_verify": bypass
    })
    
    raw_link = f"https://t.me/{clone_data.get('bot_username')}?start=file_{obj_id}"
    final_link = shorten_link(raw_link, settings.get("shortener")) if bypass else raw_link
    
    bot.send_message(message.chat.id, f"✅ {'Short-Link' if bypass else 'Link'} Ready:\n`{final_link}`", parse_mode="Markdown")
    send_log(settings, f"New Link ({'Short' if bypass else 'Normal'}): {user_id}")

@bot.message_handler(commands=['batch'])
@clone_bot_access_check
def batch_command(message, settings, owner_id, clone_data):
    if not settings.get("premium_features", False) and message.from_user.id != owner_id:
         return bot.send_message(message.chat.id, "🔒 Premium Feature.")

    msg = bot.send_message(message.chat.id, "🔗 Send First Link. /cancel to abort.")
    bot.register_next_step_handler(msg, process_batch_first_link, settings, clone_data)

def process_batch_first_link(message, settings, clone_data):
    if check_cancel_next_step(message): return
    res = parse_telegram_message_link(message.text)
    if not res[0]: return bot.send_message(message.chat.id, "❌ Invalid.")
    user_batch_data[message.from_user.id] = {"source": res[0], "start": res[1], "settings": settings, "clone": clone_data}
    msg = bot.send_message(message.chat.id, "🔗 Send Last Link.")
    bot.register_next_step_handler(msg, process_batch_second_link)

def process_batch_second_link(message):
    if check_cancel_next_step(message): return
    data = user_batch_data.pop(message.from_user.id, None)
    if not data: return
    res = parse_telegram_message_link(message.text)
    if not res[1] or res[1] <= data["start"]: return bot.send_message(message.chat.id, "❌ Invalid.")

    bid = ObjectId()
    clone_files_col.insert_one({
        "_id": bid, "clone_bot_id": data["clone"]["_id"], "owner_id": data["clone"]["owner_id"],
        "user_id": message.from_user.id, "file_type": "batch", "created_at": datetime.datetime.now(),
        "batched_file_ids": [{"file_id": f"dummy_{data['source']}_{i}"} for i in range(data["start"], res[1]+1)],
        "auto_delete_time": data["settings"].get("auto_delete", "Off")
    })
    bot.send_message(message.chat.id, f"✅ Batch Ready:\n`https://t.me/{data['clone'].get('bot_username')}?start=batch_{bid}`")

def handle_deep_link_start(message):
    arg = extract_argument(message.text)
    settings, owner_id, clone_data = get_clone_bot_settings()
    if not settings: return

    # Force Join
    not_joined = [ch for ch in settings.get("fsub", []) if not is_user_member(message.from_user.id, ch['id'])]
    if not_joined:
        kb = types.InlineKeyboardMarkup()
        for ch in not_joined: kb.add(types.InlineKeyboardButton(f"Join {ch['name']}", url=f"https://t.me/{str(ch['id']).replace('-100', '')}"))
        kb.add(types.InlineKeyboardButton("🔄 Verify", url=f"https://t.me/{clone_data.get('bot_username')}?start={arg}"))
        return bot.send_message(message.chat.id, "📢 Join first:", reply_markup=kb)

    try:
        l_type = arg.split("_")[0]
        oid = arg.split(f"{l_type}_")[1]
        file_data = clone_files_col.find_one({"_id": ObjectId(oid)})
        if not file_data: return bot.send_message(message.chat.id, "❌ Not found.")

        # Token Verify (unless bypass)
        if settings.get("verify", {}).get("status") and not file_data.get("bypass_verify"):
            uid = message.from_user.id
            if arg.startswith("token_"):
                h = int(settings["verify"].get("time", "0").split()[0])
                user_access_tokens[uid] = datetime.datetime.now() + datetime.timedelta(hours=h)
                return bot.send_message(uid, "✅ Verified!")
            
            exp = user_access_tokens.get(uid)
            if not exp or datetime.datetime.now() > exp:
                v_url = f"{settings['verify'].get('api')}?url=https://t.me/{clone_data.get('bot_username')}?start=token_VERIFIED"
                kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔑 Verify", url=v_url))
                return bot.send_message(message.chat.id, "🔒 Verify required.", reply_markup=kb)

        send_stored_file(message.chat.id, file_data)
    except: bot.send_message(message.chat.id, "❌ Error.")

def send_stored_file(chat_id, file_data):
    ft, fi, bf = file_data.get("file_type"), file_data.get("file_info"), file_data.get("batched_file_ids")
    ad = file_data.get("auto_delete_time", "Off")
    nt = f"\n\n⚠️ *Auto-Delete: {ad}*" if ad != "Off" else ""
    cap = (fi.get("caption") or "") + nt if fi else nt

    try:
        if ft == "text": bot.send_message(chat_id, (fi.get("content", "") + nt), parse_mode="Markdown")
        elif ft == "batch":
            bot.send_message(chat_id, f"Batch Incoming...{nt}")
            for item in bf: bot.send_document(chat_id, item["file_id"])
        elif ft == "photo": bot.send_photo(chat_id, fi["file_id"], caption=cap, parse_mode="Markdown")
        elif ft == "video": bot.send_video(chat_id, fi["file_id"], caption=cap, parse_mode="Markdown")
        elif ft == "document": bot.send_document(chat_id, fi["file_id"], caption=cap, parse_mode="Markdown")
        else: bot.send_message(chat_id, "⚠️ Content Error.")
    except: bot.send_message(chat_id, "❌ Send Error.")

# --- Broadcast, Ban, Owner Logic ---

@bot.message_handler(commands=['broadcast'])
@clone_bot_access_check
def broadcast_command(message, settings, owner_id, clone_data):
    if message.from_user.id != owner_id: return
    
    if message.reply_to_message:
        users = list(clone_users_col.find({"clone_bot_id": clone_data["_id"]}))
        sent, fail = 0, 0
        bot.send_message(message.chat.id, f"🚀 Broadcasting to {len(users)} users...")
        for u in users:
            try:
                m = bot.copy_message(u["user_id"], message.chat.id, message.reply_to_message.message_id)
                clone_broadcast_logs.insert_one({"user_id": u["user_id"], "msg_id": m.message_id, "time": datetime.datetime.now(), "clone_bot_id": clone_data["_id"]})
                sent += 1
                time.sleep(0.05)
            except: fail += 1
        bot.send_message(message.chat.id, f"✅ Done!\nSent: {sent}\nFailed: {fail}")
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗑 Delete Last 6h", callback_data="bc_del|6"),
               types.InlineKeyboardButton("🗑 Delete Last 12h", callback_data="bc_del|12"))
        kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_bc"))
        bot.send_message(message.chat.id, "📢 Broadcast Menu:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc_del|"))
def delete_broadcast(call):
    settings, owner_id, clone_data = get_clone_bot_settings()
    if call.from_user.id != owner_id: return
    
    h = int(call.data.split("|")[1])
    limit = datetime.datetime.now() - datetime.timedelta(hours=h)
    logs = list(clone_broadcast_logs.find({"clone_bot_id": clone_data["_id"], "time": {"$gte": limit}}))
    
    bot.answer_callback_query(call.id, f"Deleting {len(logs)} messages...")
    for l in logs:
        try: bot.delete_message(l["user_id"], l["msg_id"])
        except: pass
    clone_broadcast_logs.delete_many({"clone_bot_id": clone_data["_id"], "time": {"$gte": limit}})
    bot.edit_message_text(f"✅ Deleted {len(logs)} broadcast messages from the last {h}h.", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['ban'])
@clone_bot_access_check
def ban_user(message, settings, owner_id, clone_data):
    if message.from_user.id != owner_id: return
    args = extract_argument(message.text)
    if not args: return bot.send_message(message.chat.id, "Send ID: `/ban 12345`", parse_mode="Markdown")
    clone_users_col.update_one({"user_id": int(args), "clone_bot_id": clone_data["_id"]}, {"$set": {"is_banned": True}}, upsert=True)
    bot.send_message(message.chat.id, f"✅ User {args} Banned.")

@bot.message_handler(commands=['unban'])
@clone_bot_access_check
def unban_user(message, settings, owner_id, clone_data):
    if message.from_user.id != owner_id: return
    args = extract_argument(message.text)
    if not args: return bot.send_message(message.chat.id, "Send ID: `/unban 12345`", parse_mode="Markdown")
    clone_users_col.update_one({"user_id": int(args), "clone_bot_id": clone_data["_id"]}, {"$set": {"is_banned": False}})
    bot.send_message(message.chat.id, f"✅ User {args} Unbanned.")

@bot.message_handler(commands=['owner'])
@clone_bot_access_check
def owner_command(message, settings, owner_id, clone_data):
    if message.from_user.id != owner_id: return
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("💰 Pending", callback_data="owner_show_pending"),
           types.InlineKeyboardButton("💳 Set Payment", callback_data="owner_set_pay_menu"))
    bot.send_message(message.chat.id, "👑 Owner Menu", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "owner_set_pay_menu")
def owner_set_pay_menu(call):
    settings, owner_id, _ = get_clone_bot_settings()
    if call.from_user.id != owner_id: return
    
    upi = settings.get("upi_id", "Not Set")
    text = f"💳 *Payment Settings*\n\nCurrent UPI/Link: `{upi}`"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 Set UPI/Link", callback_data="owner_set_upi"),
           types.InlineKeyboardButton("🗑 Delete", callback_data="owner_del_upi"))
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="owner_back_to_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "owner_back_to_main")
def owner_back_to_main(call):
    settings, owner_id, _ = get_clone_bot_settings()
    if call.from_user.id != owner_id: return
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("💰 Pending", callback_data="owner_show_pending"),
           types.InlineKeyboardButton("💳 Set Payment", callback_data="owner_set_pay_menu"))
    bot.edit_message_text("👑 Owner Menu", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "owner_set_upi")
def owner_set_upi_call(call):
    settings, owner_id, _ = get_clone_bot_settings()
    if call.from_user.id != owner_id: return
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="owner_set_pay_menu"))
    msg = bot.edit_message_text("📥 *Send your UPI ID or Payment Link:*", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_owner_upi)

def save_owner_upi(message):
    if check_cancel_next_step(message): return
    settings, owner_id, clone_data = get_clone_bot_settings()
    if message.from_user.id != owner_id: return
    
    upi_val = message.text.strip()
    clones_col.update_one({"_id": clone_data["_id"]}, {"$set": {"settings.upi_id": upi_val}})
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="owner_set_pay_menu"))
    bot.send_message(message.chat.id, f"✅ *Payment method updated!*\nNew UPI: `{upi_val}`", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "owner_del_upi")
def owner_del_upi_call(call):
    settings, owner_id, clone_data = get_clone_bot_settings()
    if call.from_user.id != owner_id: return
    
    clones_col.update_one({"_id": clone_data["_id"]}, {"$unset": {"settings.upi_id": ""}})
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="owner_set_pay_menu"))
    bot.edit_message_text("🗑 *Payment method deleted successfully!*", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

# ... (Previous About/Payment handlers remain similar but should use access check if needed) ...