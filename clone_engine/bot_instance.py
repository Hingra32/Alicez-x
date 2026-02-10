from telebot import types
from database.mongo import clones_col, clone_files_col

def register_bot_handlers(bot, clone_data):
    """
    Ye function har naye Clone Bot ke liye commands set karta hai.
    """

    # --- 1. START COMMAND ---
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        # DB se custom settings uthao
        # (Kyunki clone_data purana ho sakta hai, taza data lo)
        current_data = clones_col.find_one({"token": bot.token})
        settings = current_data.get("settings", {})

        # A. Start Text
        text = settings.get("start_text", "Hello! I am a clone bot.")
        # Replace {mention}
        text = text.replace("{mention}", f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})")

        # B. Start Pic (Agar hai)
        pic = settings.get("start_pic")

        # C. Custom Buttons (Agar hain)
        kb = types.InlineKeyboardMarkup()
        for btn in settings.get("custom_btns", []):
            kb.add(types.InlineKeyboardButton(btn['name'], url=btn['url']))

        try:
            if pic:
                # Note: File ID cross-bot issue kar sakti hai agar logic heavy na ho
                # Filhal simple rakhte hain
                bot.send_photo(message.chat.id, pic, caption=text, reply_markup=kb, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")

    # --- 2. FILE HANDLING (Photo Save Logic for Admin) ---
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        # Check karo kya Manager Bot wait kar raha hai?
        current_data = clones_col.find_one({"token": bot.token})
        waiting = current_data.get("settings", {}).get("waiting_for_pic")

        if waiting:
            # ✅ Start Pic Set karne ke liye
            fid = message.photo[-1].file_id
            clones_col.update_one(
                {"_id": current_data["_id"]}, 
                {"$set": {"settings.start_pic": fid, "settings.waiting_for_pic": False}}
            )
            bot.reply_to(message, "✅ **Photo Saved!**\nAb aap Manager Bot par jakar 'I Have Sent' button daba sakte hain.")
