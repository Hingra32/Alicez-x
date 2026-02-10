from telebot.apihelper import ApiTelegramException # Import for handling API errors
from loader import bot # Re-inserting the bot import
from telebot import types # Added missing import for types
from config import PLANS, PLAN_DAYS, ADMIN_ID
from database.mongo import users_col, unclaimed_payments_col, pending_payments_col, settings_col
from datetime import datetime, timedelta
from handlers.start import start_command # Import for re-routing /start
# ... (rest of the imports) ...

# ... (rest of the imports) ...

@bot.callback_query_handler(func=lambda c: c.data == "buy_sub_menu")
def show_plans(call):
    # ... (Plan show karne ka wahi purana code) ...
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    for name, price in PLANS.items():
        kb.add(types.InlineKeyboardButton(f"💎 {name} - ₹{price}", callback_data=f"pay_sel|{name}|{price}"))
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="home"))

    try:
        bot.edit_message_text("👇 Select a Plan:", uid, call.message.message_id, reply_markup=kb)
    except ApiTelegramException as e:
        if "message to edit" in str(e): # Specific check for the "no text in the message to edit" error
            bot.send_message(uid, "👇 Select a Plan:", reply_markup=kb)
        else:
            raise e # Re-raise other API exceptions


@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_sel|"))
def pay_gateway(call):
    _, plan, price = call.data.split("|")
    # Link DB se nikalo
    db_conf = settings_col.find_one({"_id": "config"})
    pay_link = db_conf.get("payment_link", "https://t.me/admin") if db_conf else "https://t.me/admin"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Pay Now", url=pay_link))
    kb.add(types.InlineKeyboardButton("✅ I Have Paid", callback_data=f"pay_confirm|{plan}|{price}"))
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="buy_sub_menu"))

    bot.edit_message_text(f"💰 *Pay ₹{price}*\n\nLink par pay karein aur fir 'I Have Paid' dabayein.", call.from_user.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

# --- Step 2 & 3: User Email Input ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_confirm|"))
def ask_email_step(call):
    _, plan, price = call.data.split("|")
    msg = bot.edit_message_text("📧 *Apna Email ID bhejein:*\n(Jis email se payment kiya hai)", call.from_user.id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(msg, verify_user_email, plan, price)

def verify_user_email(message, plan_name, plan_price):
    uid = message.from_user.id

    # Check for commands first
    if message.text and message.text.startswith("/"):
        bot.clear_step_handler_by_chat_id(uid) # Clear any active step handler
        if message.text == "/start":
            bot.send_message(uid, "🚫 Action Cancelled. Redirecting to start.")
            start_command(message) # Call the start command handler
        else:
            bot.send_message(uid, "❌ Action Cancelled (Command Detected).")
        return # Stop further processing in this next_step_handler

    email = message.text.strip().lower()
    amount = float(plan_price)

    if "@" not in email:
        bot.send_message(uid, "❌ Invalid Email.")
        return

    # LOGIC: Check UNCLAIMED (Kya Webhook ka signal pehle aa chuka hai?)
    signal = unclaimed_payments_col.find_one({"email": email, "amount": amount})

    if signal:
        # ✅ MATCH FOUND (Signal wait kar raha tha)
        activate_plan(uid, plan_name)
        unclaimed_payments_col.delete_one({"_id": signal["_id"]}) # Signal Used
        bot.send_message(uid, f"🎉 *Plan Activated!*\nPayment verified automatically.")
    else:
        # ❌ NO SIGNAL (User pehle aaya hai) -> Save to PENDING
        pending_payments_col.insert_one({
            "user_id": uid, "email": email, "plan": plan_name, "amount": amount,
            "status": "pending", "date": datetime.now()
        })
        bot.send_message(uid, f"✅ *Details Saved!*\nJaise hi payment confirm hogi, plan chalu ho jayega.")


# ==========================================
# PART 2: WEBHOOK SIDE LOGIC (Ye Function Webhook Call Karega)
# ==========================================

def process_webhook_signal(email, amount):
    """
    Ye function tumhara Flask/Webhook route call karega jab nayi payment aaye.
    """
    email = email.strip().lower()
    amount = float(amount)

    # LOGIC: Check PENDING (Kya User pehle se wait kar raha hai?)
    pending_user = pending_payments_col.find_one({"email": email, "amount": amount})

    if pending_user:
        # ✅ USER FOUND (User wait kar raha tha)
        user_id = pending_user['user_id']
        plan_name = pending_user['plan']

        # 1. Plan Activate
        activate_plan(user_id, plan_name)

        # 2. Pending se hatao
        pending_payments_col.delete_one({"_id": pending_user["_id"]})

        # 3. User ko batao
        try: bot.send_message(user_id, f"🎉 *Payment Verified!*\nSignal received. Plan `{plan_name}` activated.")
        except: pass

        return "Matched with Pending User"

    else:
        # ❌ NO USER (Signal pehle aaya hai) -> Save to UNCLAIMED
        unclaimed_payments_col.insert_one({
            "email": email, "amount": amount, "created_at": datetime.now()
        })
        return "Saved to Unclaimed DB"


# --- Helper Function ---
def activate_plan(user_id, plan_name):
    days = PLAN_DAYS.get(plan_name, 30)
    new_expiry = datetime.now() + timedelta(days=days)
    users_col.update_one({"_id": user_id}, {"$set": {"premium_expiry": new_expiry}})
