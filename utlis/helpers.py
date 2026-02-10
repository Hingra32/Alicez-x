from database.mongo import users_col, settings_col
from datetime import datetime
from telebot import types

# ==========================================
# 1. CHECK PREMIUM STATUS
# ==========================================
def is_premium(user_id):
    """Checks if a user has an active premium plan."""
    user = users_col.find_one({"_id": user_id})
    if not user or not user.get("premium_expiry"):
        return False
    # Check if expiry date is in the future
    return user["premium_expiry"] > datetime.now()

# ==========================================
# 2. GET DATABASE SETTING
# ==========================================
def get_setting(key, default=None):
    """Fetches a specific setting from the config collection."""
    data = settings_col.find_one({"_id": "config"})
    if data and key in data:
        return data[key]
    return default

# ==========================================
# 3. GET CUSTOM BUTTONS (Ye Missing Tha)
# ==========================================
def get_custom_markup():
    """Fetches custom buttons list for Start Menu."""
    btns = get_setting("custom_btns", [])

    keyboard_buttons = []
    for b in btns:
        # Sirf tab add karo agar text aur url dono hon
        if "text" in b and "url" in b:
            keyboard_buttons.append(types.InlineKeyboardButton(text=b["text"], url=b["url"]))

    return keyboard_buttons
