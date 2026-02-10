from loader import bot
from telebot import types
from database.mongo import clones_col
from bson.objectid import ObjectId
import datetime
import re
from handlers.start import start_command # Import for re-routing /start

# ==========================================
# 1. MAIN CLONE SETTINGS PANEL
# ==========================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("c_set_panel|"))
def clone_settings_panel(call):
    try:
        cid = call.data.split("|")[1]
        data = clones_col.find_one({"_id": ObjectId(cid)})

        if not data:
            bot.answer_callback_query(call.id, "❌ Bot not found!", show_alert=True)
            return

        # Settings Defaults
        sett = data.get("settings", {})
        is_active = data.get("active", True)

        # Icons
        act_icon = "🟢" if is_active else "🔴"
        prem_icon = "✅" if sett.get("premium_features") else "❌"

        kb = types.InlineKeyboardMarkup(row_width=2)

        # Row 1: Start/Stop
        btn_txt = "🛑 Stop Bot" if is_active else "🟢 Start Bot"
        kb.add(types.InlineKeyboardButton(btn_txt, callback_data=f"cs_toggle_act|{cid}"))

        # Row 2: Transfer & Premium
        kb.add(types.InlineKeyboardButton("🔀 Transfer DB", callback_data=f"cs_trans_db|{cid}"),
               types.InlineKeyboardButton(f"💎 Premium: {prem_icon}", callback_data=f"cs_prem_tog|{cid}"))

        # Row 3: Token & Start Msg
        kb.add(types.InlineKeyboardButton("🔐 Token Verify", callback_data=f"cs_ver_menu|{cid}"),
               types.InlineKeyboardButton("📝 Start Msg", callback_data=f"cs_start_menu|{cid}"))

        # Row 4: Force Join & Custom Btn
        kb.add(types.InlineKeyboardButton("📢 Force Join", callback_data=f"cs_fsub_menu|{cid}"),
               types.InlineKeyboardButton("🔘 Custom Btn", callback_data=f"cs_btn_menu|{cid}"))

        # Row 5: Time & Plans
        kb.add(types.InlineKeyboardButton("⏱ Auto Delete", callback_data=f"cs_time_menu|{cid}"),
               types.InlineKeyboardButton("💳 Edit Plans", callback_data=f"cs_plans_menu|{cid}"))

        # Row 6: Shortener & Logs
        kb.add(types.InlineKeyboardButton("🔗 Shortener", callback_data=f"cs_short_menu|{cid}"),
               types.InlineKeyboardButton("📝 Log Channel", callback_data=f"cs_log_menu|{cid}"))

        # Row 7: Delete & Sleep
        kb.add(types.InlineKeyboardButton("🗑 Delete Bot", callback_data=f"cs_del_ask|{cid}"),
               types.InlineKeyboardButton("💤 Sleep Mode", callback_data=f"cs_sleep_tog|{cid}"))

        kb.add(types.InlineKeyboardButton("🔙 Back to List", callback_data="open_clone_list"))

        caption = (f"⚙️ *Clone Settings: @{data.get('bot_username', 'Loading...')}*\n"
                   f"🆔 ID: `{cid}`\n"
                   f"📊 Status: {act_icon}\n"
                   f"🔑 Token: `{data['token'][:15]}...`")

        bot.edit_message_text(caption, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

    except Exception as e:
        print(f"Panel Error: {e}")
        bot.answer_callback_query(call.id, "Error opening panel.")

# ==========================================
# 2. FEATURE HANDLERS
# ==========================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("cs_"))
def setting_actions(call):
    cid = call.data.split("|")[1]
    action = call.data.split("|")[0]
    uid = call.from_user.id
    mid = call.message.message_id
    chat_id = call.message.chat.id

    # --- TOGGLES ---
    if action == "cs_toggle_act":
        curr = clones_col.find_one({"_id": ObjectId(cid)}).get("active", True)
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"active": not curr}})
        clone_settings_panel(call) # Refresh

    elif action == "cs_prem_tog":
        curr_sett = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {})
        new_val = not curr_sett.get("premium_features", False)
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.premium_features": new_val}})
        clone_settings_panel(call)

    elif action == "cs_sleep_tog":
        curr = clones_col.find_one({"_id": ObjectId(cid)}).get("active", True)
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"active": not curr}})
        status = "Sleep Mode 💤" if curr else "Active ✅"
        bot.answer_callback_query(call.id, f"Bot is now {status}")
        clone_settings_panel(call)

    # --- TRANSFER DB ---
    elif action == "cs_trans_db":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        msg = bot.edit_message_text("🔀 *Transfer Database*\n\nSend the new MongoDB URI to transfer data:", chat_id, mid, reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_transfer_db, cid, mid)

    # --- TOKEN VERIFY ---
    elif action == "cs_ver_menu":
        sett = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("verify", {})
        status = "✅ On" if sett.get("status") else "❌ Off"

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("✏️ Set API", callback_data=f"cs_ver_set|{cid}"),
               types.InlineKeyboardButton("⏱ Set Time", callback_data=f"cs_ver_time|{cid}"))
        kb.add(types.InlineKeyboardButton(f"Toggle: {status}", callback_data=f"cs_ver_tog|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))

        info = f"🔐 *Token Verification*\nAPI: `{sett.get('api', 'None')}`\nDomain: `{sett.get('domain', 'None')}`\nTime: `{sett.get('time', 'None')}`"
        bot.edit_message_text(info, chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_ver_set":
        msg = bot.edit_message_text("✏️ Send format: `API_KEY, DOMAIN`\nExample: `xyz123, short.com`", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_ver_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_verify_api, cid, mid)

    elif action == "cs_ver_time":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("3 Hours", callback_data=f"cs_vt_set|{cid}|3"),
               types.InlineKeyboardButton("6 Hours", callback_data=f"cs_vt_set|{cid}|6"),
               types.InlineKeyboardButton("12 Hours", callback_data=f"cs_vt_set|{cid}|12"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_ver_menu|{cid}"))
        bot.edit_message_text("⏱ Select Verify Expiry Time:", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_vt_set":
        time_val = call.data.split("|")[2]
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.verify.time": f"{time_val} Hours"}})
        call.data = f"cs_ver_menu|{cid}"
        setting_actions(call)

    elif action == "cs_ver_tog":
        curr = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("verify", {}).get("status", False)
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.verify.status": not curr}})
        call.data = f"cs_ver_menu|{cid}"
        setting_actions(call)

    # --- START MESSAGE ---
    elif action == "cs_start_menu":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Set Text", callback_data=f"cs_st_text|{cid}"),
               types.InlineKeyboardButton("🗑 Del Text", callback_data=f"cs_st_del|{cid}"))
        kb.add(types.InlineKeyboardButton("🖼 Set Pic", callback_data=f"cs_st_pic|{cid}"),
               types.InlineKeyboardButton("🗑 Del Pic", callback_data=f"cs_st_del_pic|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text("📝 *Start Message Settings*", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_st_text":
        msg = bot.edit_message_text("📝 Send new start message.\nUse `{mention}` for name.", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_start_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_start_text, cid, mid)

    elif action == "cs_st_del":
        clones_col.update_one({"_id": ObjectId(cid)}, {"$unset": {"settings.start_text": ""}})
        bot.answer_callback_query(call.id, "🗑 Text Deleted")
        call.data = f"cs_start_menu|{cid}"
        setting_actions(call)

    # --- START PIC (CROSS BOT LOGIC) ---
    elif action == "cs_st_pic":
        c_data = clones_col.find_one({"_id": ObjectId(cid)})
        bot_user = c_data.get("bot_username", "YourBot")
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.waiting_for_pic": True}})

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("↗️ Go to Bot & Send Photo", url=f"https://t.me/{bot_user}"))
        kb.add(types.InlineKeyboardButton("🔄 I Have Sent", callback_data=f"cs_check_pic|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_start_menu|{cid}"))

        text = (f"📸 *Setup Start Picture*\n\n1. Open your bot.\n2. Send the photo.\n3. Click 'I Have Sent'.")
        bot.edit_message_text(text, chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_check_pic":
        c_data = clones_col.find_one({"_id": ObjectId(cid)})
        pic_id = c_data.get("settings", {}).get("start_pic")
        waiting = c_data.get("settings", {}).get("waiting_for_pic")

        if pic_id and not waiting:
            bot.answer_callback_query(call.id, "✅ Verified!", show_alert=True)
            call.data = f"cs_start_menu|{cid}"
            setting_actions(call)
        else:
            bot.answer_callback_query(call.id, "❌ Photo not received yet!", show_alert=True)

    elif action == "cs_st_del_pic":
        clones_col.update_one({"_id": ObjectId(cid)}, {"$unset": {"settings.start_pic": ""}})
        bot.answer_callback_query(call.id, "🗑 Photo Removed")
        call.data = f"cs_start_menu|{cid}"
        setting_actions(call)

    # --- FORCE JOIN ---
    elif action == "cs_fsub_menu":
        fsub = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("fsub", [])
        kb = types.InlineKeyboardMarkup(row_width=2)
        for idx, ch in enumerate(fsub):
            kb.add(types.InlineKeyboardButton(f"❌ {ch['name']}", callback_data=f"cs_fs_del|{cid}|{idx}"))
        if len(fsub) < 4:
            kb.add(types.InlineKeyboardButton("➕ Add Channel", callback_data=f"cs_fs_add|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text(f"📢 *Force Join Channels* ({len(fsub)}/4)", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_fs_add":
        msg = bot.edit_message_text("🔄 *Forward a message* from the channel to add:", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_fsub_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_fsub_channel, cid, mid)

    elif action == "cs_fs_del":
        idx = int(call.data.split("|")[2])
        fsub = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("fsub", [])
        if 0 <= idx < len(fsub):
            del fsub[idx]
            clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.fsub": fsub}})
        call.data = f"cs_fsub_menu|{cid}"
        setting_actions(call)

    # --- CUSTOM BUTTONS ---
    elif action == "cs_btn_menu":
        btns = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("custom_btns", [])
        kb = types.InlineKeyboardMarkup(row_width=2)
        for idx, b in enumerate(btns):
            kb.add(types.InlineKeyboardButton(f"❌ {b['name']}", callback_data=f"cs_btn_del|{cid}|{idx}"))
        if len(btns) < 4:
            kb.add(types.InlineKeyboardButton("➕ ADD", callback_data=f"cs_btn_add|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text(f"🔘 *Custom Buttons* ({len(btns)}/4)", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_btn_add":
        txt = "➕ Send format:\n`{Name}{Url}`\nExample: `{Support}{https://t.me/help}`"
        msg = bot.edit_message_text(txt, chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_btn_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_custom_btn, cid, mid)

    elif action == "cs_btn_del":
        idx = int(call.data.split("|")[2])
        btns = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("custom_btns", [])
        if 0 <= idx < len(btns):
            del btns[idx]
            clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.custom_btns": btns}})
        call.data = f"cs_btn_menu|{cid}"
        setting_actions(call)

    # --- AUTO DELETE TIME ---
    elif action == "cs_time_menu":
        kb = types.InlineKeyboardMarkup(row_width=2)
        times = ["30 Mins", "2 Hours", "6 Hours", "Off"]
        for t in times: kb.add(types.InlineKeyboardButton(t, callback_data=f"cs_set_time|{cid}|{t}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        curr = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("auto_delete", "Off")
        bot.edit_message_text(f"⏱ *Auto Delete Time*\nCurrent: {curr}", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_set_time":
        t = call.data.split("|")[2]
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.auto_delete": t}})
        bot.answer_callback_query(call.id, f"Set to {t}")
        call.data = f"cs_time_menu|{cid}"
        setting_actions(call)

    # --- SHORTENER ---
    elif action == "cs_short_menu":
        api = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("shortener", "None")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✏️ Set API", callback_data=f"cs_short_set|{cid}"),
               types.InlineKeyboardButton("🗑 Delete", callback_data=f"cs_short_del|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text(f"🔗 *Shortener API*\nCurrent: `{api}`", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_short_set":
        msg = bot.edit_message_text("🔗 Send your Shortener API Key:", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_short_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_shortener, cid, mid)

    elif action == "cs_short_del":
        clones_col.update_one({"_id": ObjectId(cid)}, {"$unset": {"settings.shortener": ""}})
        bot.answer_callback_query(call.id, "🗑 Deleted")
        call.data = f"cs_short_menu|{cid}"
        setting_actions(call)

    # --- LOG CHANNEL ---
    elif action == "cs_log_menu":
        log = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {}).get("log_channel", "None")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Set Channel", callback_data=f"cs_log_set|{cid}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text(f"📝 *Log Channel ID*\nCurrent: `{log}`", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_log_set":
        msg = bot.edit_message_text("🔄 Forward a message from Log Channel:", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_log_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_log_channel, cid, mid)

    # --- DELETE BOT ---
    elif action == "cs_del_ask":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⚠️ YES, DELETE", callback_data=f"cs_del_conf|{cid}"))
        kb.add(types.InlineKeyboardButton("❌ No", callback_data=f"c_set_panel|{cid}"))
        bot.edit_message_text("⚠️ *Are you sure?*\nAction is irreversible!", chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_del_conf":
        clones_col.delete_one({"_id": ObjectId(cid)})
        bot.edit_message_text("🗑 Bot Deleted. Go to /settings.", chat_id, mid)


    # --- PLANS ---
    elif action == "cs_plans_menu":
        sett = clones_col.find_one({"_id": ObjectId(cid)}).get("settings", {})
        plans = sett.get("plans", {})
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name, price in plans.items():
            kb.add(types.InlineKeyboardButton(f"❌ {name} - ₹{price}", callback_data=f"cs_plan_del|{cid}|{name}"))
        
        if len(plans) < 6:
            kb.add(types.InlineKeyboardButton("➕ Add Plan", callback_data=f"cs_plan_add|{cid}"))
        
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"c_set_panel|{cid}"))
        
        text = "💳 *Edit Plans*\n\nClick on a plan to delete it, or add a new one."
        bot.edit_message_text(text, chat_id, mid, reply_markup=kb, parse_mode="Markdown")

    elif action == "cs_plan_add":
        msg = bot.edit_message_text("📝 *Send Plan Name:*\n(Example: `1 Month`)", chat_id, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cs_plans_menu|{cid}")), parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_plan_name, cid, mid)

    elif action == "cs_plan_del":
        plan_name = call.data.split("|")[2]
        clones_col.update_one({"_id": ObjectId(cid)}, {"$unset": {f"settings.plans.{plan_name}": ""}})
        bot.answer_callback_query(call.id, f"🗑 Plan '{plan_name}' Deleted")
        call.data = f"cs_plans_menu|{cid}"
        setting_actions(call)

# ==========================================
# 3. SAFE INPUT HANDLERS (Next Step)
# ==========================================

def check_cancel(message, cid):
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

def save_plan_name(message, cid, mid):
    if check_cancel(message, cid): return
    plan_name = message.text.strip()
    msg = bot.send_message(message.chat.id, f"💰 *Send Price for '{plan_name}':*\n(Numbers only, e.g., `150`)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_plan_price, cid, plan_name)

def save_plan_price(message, cid, plan_name):
    if check_cancel(message, cid): return
    try:
        price = float(message.text.strip())
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {f"settings.plans.{plan_name}": price}})
        bot.send_message(message.chat.id, f"✅ Plan '{plan_name}' added with price ₹{price}!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid Price! Please use numbers only.")

def save_transfer_db(message, cid, mid):
    if check_cancel(message, cid): return
    # Only saving URI to settings for now
    clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.mongo_db": message.text.strip()}})
    bot.send_message(message.chat.id, "✅ Database URI Saved!")

def save_verify_api(message, cid, mid):
    if check_cancel(message, cid): return
    try:
        api, domain = message.text.split(",")
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.verify.api": api.strip(), "settings.verify.domain": domain.strip(), "settings.verify.status": True}})
        bot.send_message(message.chat.id, "✅ Verify API Saved!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid Format! Use: API, DOMAIN")

def save_start_text(message, cid, mid):
    if check_cancel(message, cid): return
    clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.start_text": message.text}})
    bot.send_message(message.chat.id, "✅ Start Text Updated!")

def save_fsub_channel(message, cid, mid):
    if message.forward_from_chat:
        ch_id = message.forward_from_chat.id
        ch_name = message.forward_from_chat.title or "Channel"
        clones_col.update_one({"_id": ObjectId(cid)}, {"$push": {"settings.fsub": {"id": ch_id, "name": ch_name}}})
        bot.send_message(message.chat.id, "✅ Channel Added!")
    else:
        bot.send_message(message.chat.id, "❌ Not a Forwarded Message!")

def save_custom_btn(message, cid, mid):
    if check_cancel(message, cid): return
    match = re.search(r"\{(.*?)\}\{(.*?)\}", message.text)
    if match:
        name, url = match.groups()
        clones_col.update_one({"_id": ObjectId(cid)}, {"$push": {"settings.custom_btns": {"name": name, "url": url}}})
        bot.send_message(message.chat.id, "✅ Button Added!")
    else:
        bot.send_message(message.chat.id, "❌ Invalid Format! Use: {Name}{Url}")

def save_shortener(message, cid, mid):
    if check_cancel(message, cid): return
    clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.shortener": message.text.strip()}})
    bot.send_message(message.chat.id, "✅ Shortener API Saved!")

def save_log_channel(message, cid, mid):
    if message.forward_from_chat:
        clones_col.update_one({"_id": ObjectId(cid)}, {"$set": {"settings.log_channel": message.forward_from_chat.id}})
        bot.send_message(message.chat.id, "✅ Log Channel Set!")
    else:
        bot.send_message(message.chat.id, "❌ Not a Forward!")
