from telebot import TeleBot
from flask import Flask
from config import BOT_TOKEN, MONGO_URI
from pymongo import MongoClient

# 1. FLASK APP (Server)
app = Flask(__name__)

# 2. MONGODB CONNECTION
try:
    # Connect to Database
    client = MongoClient(MONGO_URI)
    db = client['ManagerBotDB']
    print("✅ Database Connected in Loader!")
except Exception as e:
    print(f"❌ Database Error in Loader: {e}")

# 3. TELEGRAM BOT
# Parse mode HTML rakha hai taaki errors kam aayein
bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==========================================
# 👇 YE HAI WO MISSING CODE (YAHAN ADD KAREIN)
# ==========================================
@app.route('/')
def home():
    return "Bot is Running!", 200
