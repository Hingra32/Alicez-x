import threading
import time
from telebot import types
from loader import bot
from config import ADMIN_ID, PLANS
from database.mongo import users_col, settings_col, clones_col, tickets_col
import re
from bson.objectid import ObjectId
from handlers.start import start_command # Import for re-routing /start

# --- STATE MANAGEMENT ---
# Dictionary to store Admin's current action
admin_states = {} 

# --- HELPER FUNCTIONS ---
def get_db_setting(key, default):
    data = settings_col.find_one({"_id": "config"})
    if data and key in data: return data[key]
    return default

def update_db_setting(key, value):
    settings_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# Helper for Back Button
def back_btn(cb_data):
    return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=cb_data))

# ======================================================
# 1. MAIN ADMIN PANEL (/admin)
# ======================================================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    # Security Check
    if str(message.from_user.id) != str(ADMIN_ID): return

    # Purana koi step atka ho to clear karo
    bot.clear_step_handler_by_chat_id(message.chat.id)

    # Send Panel
    send_admin_home(message.chat.id, message.message_id, trigger="command")

def send_admin_home(chat_id, message_id=None, trigger="call"):
    # Stats Calculation
    total_users = users_col.count_documents({})
    total_clones = clones_col.count_documents({})
    active_prem = users_col.count_documents({"premium_expiry": {"$ne": None}})

    text = (f"👮‍♂️ *Admin Dashboard*\n\n"
            f"👥 Users: `{total_users}`\n"
            f"🤖 Clones: `{total_clones}`\n"
            f"💎 Premium: `{active_prem}`\n\n"
            f"Select an option:")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
           types.InlineKeyboardButton("🚫 Ban/Unban", callback_data="adm_ban_menu"))
    kb.add(types.InlineKeyboardButton("📝 Start Msg", callback_data="adm_start_menu"),
           types.InlineKeyboardButton("🔘 Custom Btn", callback_data="adm_cust_btn"))
    kb.add(types.InlineKeyboardButton("💰 Payment Link", callback_data="adm_pay_link"),
           types.InlineKeyboardButton("📊 Reports/Tix", callback_data="adm_reports"))
    kb.add(types.InlineKeyboardButton("💳 Edit Plans", callback_data="adm_plans"),
           types.InlineKeyboardButton("➕ Manual Add", callback_data="adm_manual"))

    # Premium Mode Toggle Status
    prem_mode = get_db_setting("premium_mode", True)
    mode_icon = "🟢 On" if prem_mode else "🔴 Off"
    kb.add(types.InlineKeyboardButton(f"💎 Prem Mode: {mode_icon}", callback_data="adm_toggle_prem"))

    kb.add(types.InlineKeyboardButton("📝 Log Channel", callback_data="adm_log_channel"))
    kb.add(types.InlineKeyboardButton("❌ Close", callback_data="close_menu"))

    try:
        if trigger == "command":
            bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
        else:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=kb, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

# ======================================================
# 🔄 CALLBACK HANDLER (THE BRAIN)
# ======================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_") or c.data == "admin_home" or c.data == "close_menu" or c.data.startswith("st_") or c.data.startswith("bc_") or c.data.startswith("edt_") or c.data.startswith("rep_") or c.data.startswith("done_") or c.data.startswith("del_") or c.data.startswith("add_") or c.data.startswith("set_"))
def admin_callbacks(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    uid = call.from_user.id
    mid = call.message.message_id
    cid = call.message.chat.id
    data = call.data

    # 🔥 CRITICAL FIX: Koi bhi button dbane par purana "Step Handler" cancel karo
    bot.clear_step_handler_by_chat_id(cid)

    # Loading animation roko
    try: bot.answer_callback_query(call.id)
    except: pass

    # ------------------------------------
    # 0. HOME & CLOSE
    # ------------------------------------
    if data == "admin_home":
        admin_states[uid] = None
        send_admin_home(cid, mid)
        return

    elif data == "close_menu":
        try:
            bot.delete_message(cid, mid)
            # Optional: Command message bhi delete kar sakte ho agar store kiya ho
        except: pass
        return

    # ------------------------------------
    # 1. BROADCAST SYSTEM
    # ------------------------------------
    if data == "adm_broadcast":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("👥 All Users", callback_data="bc_target|all"),
               types.InlineKeyboardButton("💎 Premium Only", callback_data="bc_target|prem"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text("📢 *Broadcast Step 1*\nSelect Target Audience:", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("bc_target|"):
        target = data.split("|")[1]
        admin_states[uid] = {"action": "broadcast", "target": target}

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📌 Pin Message", callback_data="bc_opt|pin"),
               types.InlineKeyboardButton("No Pin", callback_data="bc_opt|nopin"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_broadcast"))
        bot.edit_message_text("📢 *Broadcast Step 2*\nPin Message in user chat?", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("bc_opt|"):
        pin = True if "pin" == data.split("|")[1] else False
        if uid not in admin_states: admin_states[uid] = {} # Safety check
        admin_states[uid]["pin"] = pin

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("❌ No Delete", callback_data="bc_time|0"),
               types.InlineKeyboardButton("1 Hour", callback_data="bc_time|1"),
               types.InlineKeyboardButton("24 Hours", callback_data="bc_time|24"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_broadcast"))
        bot.edit_message_text("📢 *Broadcast Step 3*\nAuto-Delete Time?", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("bc_time|"):
        hrs = int(data.split("|")[1])
        if uid not in admin_states: admin_states[uid] = {}
        admin_states[uid]["del_time"] = hrs

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_broadcast"))
        msg = bot.edit_message_text("📢 *Final Step*\n\nSend the message (Text/Photo/Video) you want to broadcast:", cid, mid, reply_markup=kb, parse_mode="Markdown")

        bot.register_next_step_handler(msg, process_broadcast_msg)

    # ------------------------------------
    # 2. BAN / UNBAN
    # ------------------------------------
    elif data == "adm_ban_menu":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        msg = bot.edit_message_text("🚫 *Ban/Unban User*\n\nSend User ID to toggle Ban status:", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ban_user)

    # ------------------------------------
    # 3. START MESSAGE & PIC
    # ------------------------------------
    elif data == "adm_start_menu":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Set Text", callback_data="st_text_menu"),
               types.InlineKeyboardButton("🖼 Set Pic", callback_data="st_pic_menu"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text("📝 *Start Settings*\nChoose what to edit:", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data == "st_text_menu":
        curr = get_db_setting("start_text", "Welcome {mention}")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✏️ Edit Text", callback_data="st_edit_text"),
               types.InlineKeyboardButton("🗑 Reset Default", callback_data="st_reset_text"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_start_menu"))
        bot.edit_message_text(f"📄 *Current Text:*\n`{curr}`\n\nFormat: `{{mention}}` for name.", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data == "st_edit_text":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="st_text_menu"))
        msg = bot.edit_message_text("⌨️ *Send New Start Message:*", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_start_text)

    elif data == "st_reset_text":
        update_db_setting("start_text", "Welcome {mention}")
        bot.answer_callback_query(call.id, "✅ Reset to Default")
        # Go back to menu
        call.data = "st_text_menu"
        admin_callbacks(call)

    elif data == "st_pic_menu":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🖼 Set Photo", callback_data="st_set_pic"),
               types.InlineKeyboardButton("🗑 Remove Photo", callback_data="st_del_pic"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_start_menu"))
        bot.edit_message_text("🖼 *Start Picture Manager*", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data == "st_set_pic":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="st_pic_menu"))
        msg = bot.edit_message_text("📸 *Send the Photo now:*", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_start_pic)

    elif data == "st_del_pic":
        update_db_setting("start_pic", None)
        bot.answer_callback_query(call.id, "🗑 Photo Removed!")
        call.data = "st_pic_menu"
        admin_callbacks(call)

    # ------------------------------------
    # 4. CUSTOM BUTTONS
    # ------------------------------------
    elif data == "adm_cust_btn":
        btns = get_db_setting("custom_btns", []) 

        kb = types.InlineKeyboardMarkup(row_width=2)
        for i, b in enumerate(btns):
            kb.add(types.InlineKeyboardButton(f"❌ {b['text']}", callback_data=f"del_btn|{i}"))

        kb.add(types.InlineKeyboardButton("➕ ADD BUTTON", callback_data="add_cust_btn"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))

        msg_txt = ("🔘 *Custom Buttons*\n\n"
               "**Formats to Copy:**\n"
               "Broadcast: `{name}{buttonurl}{broadcast}`\n"
               "Start Cmd: `{name}{buttonurl}{start}`\n\n"
               "👇 *Click to Remove Button:*")
        bot.edit_message_text(msg_txt, cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data == "add_cust_btn":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_cust_btn"))
        msg = bot.edit_message_text("➕ *Add Button*\n\nSend in this format:\n`Button Name - https://link.com`", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_cust_btn)

    elif data.startswith("del_btn|"):
        idx = int(data.split("|")[1])
        btns = get_db_setting("custom_btns", [])
        if 0 <= idx < len(btns):
            del btns[idx]
            update_db_setting("custom_btns", btns)
        call.data = "adm_cust_btn"
        admin_callbacks(call)

    # ------------------------------------
    # 5. PAYMENT LINK
    # ------------------------------------
    elif data == "adm_pay_link":
        curr = get_db_setting("payment_link", "Not Set")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✏️ Edit Link", callback_data="edt_pay_lnk"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text(f"💰 *Current Payment Link:*\n{curr}", cid, mid, reply_markup=kb, disable_web_page_preview=True, parse_mode="Markdown")

    elif data == "edt_pay_lnk":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_pay_link"))
        msg = bot.edit_message_text("🔗 *Send New Payment Link:*", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_pay_link)

    # ------------------------------------
    # 6. REPORTS (STATS + TICKETS)
    # ------------------------------------
    elif data == "adm_reports":
        tix = list(tickets_col.find({"status": "open"}))

        text = f"📊 *Reports Center*\nOpen Tickets: {len(tix)}\n\n"
        kb = types.InlineKeyboardMarkup()

        if tix:
            t = tix[0] 
            text += f"👤 User: `{t['user_id']}`\n📝 Msg: {t['text']}" # Changed 'query' to 'text' standard
            kb.add(types.InlineKeyboardButton("↩️ Reply", callback_data=f"rep_tix|{t['_id']}"),
                   types.InlineKeyboardButton("✅ Done", callback_data=f"done_tix|{t['_id']}"))
        else:
            text += "✅ No pending reports."

        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text(text, cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("rep_tix|"):
        tid = data.split("|")[1]
        ticket = tickets_col.find_one({"_id": ObjectId(tid)})
        if ticket:
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_reports"))
            msg = bot.edit_message_text(f"✍️ *Reply to {ticket['user_id']}:*", cid, mid, reply_markup=kb, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_reply_ticket, ticket['user_id'], tid)

    elif data.startswith("done_tix|"):
        try: tickets_col.update_one({"_id": ObjectId(data.split("|")[1])}, {"$set": {"status": "closed"}})
        except: pass
        call.data = "adm_reports"
        admin_callbacks(call)

    # ------------------------------------
    # 7. EDIT PLANS
    # ------------------------------------
    elif data == "adm_plans":
        plans = get_db_setting("plans", PLANS) 
        kb = types.InlineKeyboardMarkup(row_width=2)
        for name, price in plans.items():
            kb.add(types.InlineKeyboardButton(f"{name} - ₹{price}", callback_data=f"edt_pln|{name}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text("💳 *Edit Plan Prices*\nSelect a plan to change price:", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("edt_pln|"):
        pname = data.split("|")[1]
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_plans"))
        msg = bot.edit_message_text(f"💰 *Edit {pname}*\nSend new price (Number only):", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_plan_price, pname)

    # ------------------------------------
    # 8. MANUAL ADD (PREMIUM)
    # ------------------------------------
    elif data == "adm_manual":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        msg = bot.edit_message_text("➕ *Manual Premium*\n\nFormat: `UserID{Days}`\nExample: `123456789{30}`", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_manual_add)

    # ------------------------------------
    # 9. PREMIUM MODE TOGGLE
    # ------------------------------------
    elif data == "adm_toggle_prem":
        curr = get_db_setting("premium_mode", True)
        update_db_setting("premium_mode", not curr)
        send_admin_home(cid, mid)

    # ------------------------------------
    # 10. LOG CHANNEL
    # ------------------------------------
    elif data == "adm_log_channel":
        curr = get_db_setting("log_channel", "Not Set")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Set Log Channel", callback_data="set_log_ch"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text(f"📝 *Log Channel*\nCurrent ID: `{curr}`\n\nTo set: Make bot admin in channel & Forward a message.", cid, mid, reply_markup=kb, parse_mode="Markdown")

    elif data == "set_log_ch":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_log_channel"))
        msg = bot.edit_message_text("🔄 *Forward a message from your Channel now:*", cid, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_log_channel)


# ======================================================
# 🚀 SAFE INPUT HANDLERS (Next Step Handlers)
# ======================================================

def check_cancel(message):
    if message.text and message.text.startswith("/"):
        bot.clear_step_handler_by_chat_id(message.chat.id) # Clear any active step handler
        if message.text == "/start":
            bot.send_message(message.chat.id, "🚫 Action Cancelled. Redirecting to start.")
            start_command(message) # Call the start command handler
            return True # Command handled, stop further processing
        else:
            bot.send_message(message.chat.id, "🚫 Action Cancelled (Command Detected).")
            return True # For other commands, just cancel the current flow
    return False

def process_broadcast_msg(message):
    if check_cancel(message): return
    uid = message.from_user.id
    state = admin_states.get(uid, {})

    threading.Thread(target=run_broadcast, args=(message, state)).start()
    bot.send_message(message.chat.id, "🚀 Broadcast Started in Background!", reply_markup=back_btn("adm_broadcast"))
    admin_states[uid] = None

def process_ban_user(message):
    if check_cancel(message): return
    try:
        target_id = int(message.text)
        u = users_col.find_one({"_id": target_id})
        if u:
            new_ban = not u.get("is_banned", False)
            users_col.update_one({"_id": target_id}, {"$set": {"is_banned": new_ban}})
            status = "🚫 Banned" if new_ban else "✅ Unbanned"
            # FIX: Reply_to nahi use kiya, taki tag na fase
            bot.send_message(message.chat.id, f"User {target_id} is now {status}", reply_markup=back_btn("adm_ban_menu"))
        else:
            bot.send_message(message.chat.id, "❌ User not found in DB.", reply_markup=back_btn("adm_ban_menu"))
    except:
        bot.send_message(message.chat.id, "❌ Invalid ID (Numbers Only)", reply_markup=back_btn("adm_ban_menu"))

def process_start_text(message):
    if check_cancel(message): return
    update_db_setting("start_text", message.text)
    bot.send_message(message.chat.id, "✅ Start Text Updated!", reply_markup=back_btn("st_text_menu"))

def process_start_pic(message):
    if message.text and message.text.startswith("/"): return
    if message.photo:
        fid = message.photo[-1].file_id
        update_db_setting("start_pic", fid)
        bot.send_message(message.chat.id, "✅ Start Pic Updated!", reply_markup=back_btn("st_pic_menu"))
    else:
        bot.send_message(message.chat.id, "❌ Please send a photo.")

def process_cust_btn(message):
    if check_cancel(message): return
    try:
        parts = re.split(r'[-\|]', message.text, 1)
        if len(parts) == 2:
            name, url = parts
            btns = get_db_setting("custom_btns", [])
            btns.append({"text": name.strip(), "url": url.strip()})
            update_db_setting("custom_btns", btns)
            bot.send_message(message.chat.id, "✅ Button Added!", reply_markup=back_btn("adm_cust_btn"))
        else:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ Invalid Format. Use: Name - Link")

def process_pay_link(message):
    if check_cancel(message): return
    update_db_setting("payment_link", message.text)
    bot.send_message(message.chat.id, "✅ Payment Link Updated!", reply_markup=back_btn("adm_pay_link"))

def process_plan_price(message, pname):
    if check_cancel(message): return
    try:
        price = int(message.text)
        plans = get_db_setting("plans", PLANS)
        plans[pname] = price
        update_db_setting("plans", plans)
        bot.send_message(message.chat.id, f"✅ {pname} price set to ₹{price}", reply_markup=back_btn("adm_plans"))
    except:
        bot.send_message(message.chat.id, "❌ Numbers only!")

def process_manual_add(message):
    if check_cancel(message): return
    import re
    from datetime import datetime, timedelta
    match = re.search(r"(\d+)\{(\d+)\}", message.text)
    if match:
        tid = int(match.group(1))
        days = int(match.group(2))
        expiry = datetime.now() + timedelta(days=days)
        users_col.update_one({"_id": tid}, {"$set": {"premium_expiry": expiry}}, upsert=True)
        bot.send_message(message.chat.id, f"✅ Premium Added to {tid} for {days} days.", reply_markup=back_btn("admin_home"))
    else:
        bot.send_message(message.chat.id, "❌ Invalid Format. Use: ID{Days}")

def process_log_channel(message):
    if message.forward_from_chat:
        cid = message.forward_from_chat.id
        update_db_setting("log_channel", cid)
        bot.send_message(message.chat.id, f"✅ Log Channel Set: {cid}", reply_markup=back_btn("adm_log_channel"))
    else:
        bot.send_message(message.chat.id, "❌ Please forward from the channel.")

def process_reply_ticket(message, uid, tid):
    if check_cancel(message): return
    try:
        bot.send_message(uid, f"👨‍💻 *Admin Reply:*\n\n{message.text}", parse_mode="Markdown")
        tickets_col.update_one({"_id": ObjectId(tid)}, {"$set": {"status": "closed"}})
        bot.send_message(message.chat.id, "✅ Reply Sent!", reply_markup=back_btn("adm_reports"))
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")

# --- BROADCAST RUNNER ---
def run_broadcast(message, options):
    target = options['target'] 
    pin = options['pin']
    del_time = options['del_time']

    query = {}
    if target == 'prem': query = {"premium_expiry": {"$ne": None}}

    users = users_col.find(query)
    count = 0
    msg_ids = [] 

    for u in users:
        try:
            m = bot.copy_message(u['_id'], message.chat.id, message.message_id)
            if pin: 
                try: bot.pin_chat_message(u['_id'], m.message_id)
                except: pass

            if del_time > 0:
                msg_ids.append((u['_id'], m.message_id))

            count += 1
            time.sleep(0.05) 
        except: pass

    bot.send_message(ADMIN_ID, f"✅ Broadcast Complete. Sent to {count} users.")

    if del_time > 0 and msg_ids:
        def deleter():
            time.sleep(del_time * 3600)
            for cid, mid in msg_ids:
                try: bot.delete_message(cid, mid)
                except: pass
        threading.Thread(target=deleter).start()
