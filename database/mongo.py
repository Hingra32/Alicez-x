import pymongo
import certifi
from config import MONGO_URI

# 1. Connection Setup
# 'certifi' zaroori hai taaki SSL Certificate error na aaye (Replit/Render par)
try:
    client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client["TelegramBotDB"]
    print("✅ Database Connected Successfully!")

except Exception as e:
    print(f"❌ Database Connection Error: {e}")
    # Agar DB connect nahi hua to code aage crash na ho, isliye exit karte hain
    exit()

# ==========================================
# 2. COLLECTIONS DEFINITION
# ==========================================

# A. Manager Bot Users
# (Data: User ID, Name, Premium Status, Join Date)
users_col = db["users"]

# B. The Clones (Bots)
# (Data: Token, Owner ID, Settings {start_pic, fsub, buttons}, Active Status)
clones_col = db["clones"]

# C. Global Settings (Admin Panel)
# (Data: Payment Link, Maintenance Mode, Premium Mode Toggle)
settings_col = db["settings"]

# D. Payment System
# (Data: Email, Amount, Status for Verification)
pending_payments_col = db["pending_payments"]    # User ne request ki
unclaimed_payments_col = db["unclaimed_payments"] # Webhook se paise aaye par user nahi mila

# E. Support System
# (Data: User Query, Admin Reply, Status)
tickets_col = db["tickets"]

# F. Clone Engine Data (Future Use)
# (Data: File ID, Caption, Views) - Clone bot jo file store karega
clone_files_col = db["clone_files"] 

# (Data: User ID, Bot ID) - Clone bot ke users (Broadcast ke liye)
clone_users_col = db["clone_users"] 


# ==========================================
# 3. PERFORMANCE INDEXING (OPTIONAL BUT RECOMMENDED)
# ==========================================
# Ye bot ki speed badhane ke liye hai. Ise ek baar run hone dein.

try:
    # 1. Clones ko 'Token' aur 'Owner' se dhoondhna fast hoga
    clones_col.create_index("token", unique=True) # Token kabhi duplicate nahi ho sakta
    clones_col.create_index("owner_id")

    # 2. Users ko ID se dhoondhna
    users_col.create_index("joined_at")

    # 3. Files ko Short Code se dhoondhna (File Store ke liye)
    clone_files_col.create_index("short_code", unique=True)

    # 4. Clone Users (Taaki ek user duplicate count na ho broadcast mein)
    clone_users_col.create_index([("bot_id", 1), ("user_id", 1)], unique=True)

    print("⚡ Database Indexes Created (Performance Optimized)")

except Exception as e:
    print(f"⚠️ Indexing Note: {e}")
