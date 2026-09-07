import os
import random
import sqlite3
from datetime import datetime, timedelta
import telebot
from telebot import types

# ================= CONFIGURATION =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = 8914163493  # Main Owner Telegram ID
FAMEPAY_UPI_ID = "your_famepay_upi@handle"  # Put your FamePay UPI ID here

# Referral Commission Percentages
REF_COMMISSION_L1 = 0.05  # 5% for Level 1
REF_COMMISSION_L2 = 0.02  # 2% for Level 2
REF_COMMISSION_L3 = 0.01  # 1% for Level 3

bot = telebot.TeleBot(BOT_TOKEN)

# ================= DATABASE SETUP (Values stored in Paise/Integers) =================
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users Table (Balance stored in paise, e.g., ₹150.00 = 15000 paise)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        phone TEXT,
                        balance INTEGER DEFAULT 0,
                        last_spin TEXT DEFAULT '',
                        referred_by INTEGER DEFAULT 0,
                        ref_level1 INTEGER DEFAULT 0,
                        ref_level2 INTEGER DEFAULT 0,
                        ref_level3 INTEGER DEFAULT 0)''')
                        
    # Admins / Staff Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS staff (
                        user_id INTEGER PRIMARY KEY,
                        can_approve_deposits INTEGER DEFAULT 0,
                        can_manage_stock INTEGER DEFAULT 0)''')
                        
    # Products Table (Price stored in paise)
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        duration TEXT,
                        price INTEGER)''')
                        
    # Keys/Stock Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock (
                        key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_id INTEGER,
                        key_code TEXT,
                        is_sold INTEGER DEFAULT 0)''')
                        
    # History Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        product_name TEXT,
                        key_code TEXT,
                        date TEXT)''')
                        
    # Pending Deposit Requests Table (Amount stored in paise)
    cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (
                        deposit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        amount INTEGER,
                        utr TEXT UNIQUE,
                        status TEXT DEFAULT 'PENDING',
                        date TEXT)''')
                        
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('bot_database.db', check_same_thread=False)

def is_owner(user_id):
    return user_id == OWNER_ID

def get_staff_perms(user_id):
    if is_owner(user_id):
        return {'deposit': 1, 'stock': 1}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT can_approve_deposits, can_manage_stock FROM staff WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        return {'deposit': res[0], 'stock': res[1]}
    return {'deposit': 0, 'stock': 0}

# ================= /START & REFERRAL / PHONE VERIFICATION =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = 0
    if len(args) > 1 and args[1].isdigit():
        parsed_ref = int(args[1])
        if parsed_ref != user_id:
            referrer_id = parsed_ref

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT phone, referred_by FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        actual_ref = referrer_id
        cursor.execute('INSERT INTO users (user_id, referred_by) VALUES (?, ?)', (user_id, actual_ref))
        
        # Distribute referral counts upwards (Level 1, Level 2, Level 3)
        if actual_ref:
            cursor.execute('UPDATE users SET ref_level1 = ref_level1 + 1 WHERE user_id = ?', (actual_ref,))
            cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (actual_ref,))
            l2 = cursor.fetchone()
            if l2 and l2[0]:
                cursor.execute('UPDATE users SET ref_level2 = ref_level2 + 1 WHERE user_id = ?', (l2[0],))
                cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (l2[0],))
                l3 = cursor.fetchone()
                if l3 and l3[0]:
                    cursor.execute('UPDATE users SET ref_level3 = ref_level3 + 1 WHERE user_id = ?', (l3[0],))
        conn.commit()
        user_phone = None
    else:
        user_phone = user[0]

    conn.close()

    if not user_phone:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        btn = types.KeyboardButton("📱 Share Phone Number", request_contact=True)
        markup.add(btn)
        bot.send_message(message.chat.id, "Welcome! Please share your phone number to verify your account:", reply_markup=markup)
    else:
        show_main_menu(message.chat.id)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact:
        user_id = message.from_user.id
        phone = message.contact.phone_number
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''UPDATE users SET phone = ? WHERE user_id = ?''', (phone, user_id))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, "Verification successful!", reply_markup=types.ReplyKeyboardRemove())
        show_main_menu(message.chat.id)

# ================= MAIN MENU =================
def show_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛍️ Product Store", callback_data="store"),
        types.InlineKeyboardButton("👤 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("💳 Add Balance (UPI/FamePay)", callback_data="add_balance"),
        types.InlineKeyboardButton("👥 Referral Program", callback_data="referrals"),
        types.InlineKeyboardButton("🎁 Daily Spin", callback_data="spin"),
        types.InlineKeyboardButton("📜 History", callback_data="history"),
        types.InlineKeyboardButton("💬 Support", callback_data="support")
    )
    
    perms = get_staff_perms(chat_id)
    if is_owner(chat_id) or any(perms.values()):
        markup.add(types.InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"))

    bot.send_message(chat_id, "Choose an option from below:", reply_markup=markup)

# ================= CALLBACK HANDLER =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    if call.data == "store":
        bot.answer_callback_query(call.id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT product_id, name, duration, price FROM products')
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
            bot.edit_message_text("No products available right now. Check back later!", call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
            
        markup = types.InlineKeyboardMarkup()
        for p in products:
            price_rs = p[3] / 100.0
            markup.add(types.InlineKeyboardButton(f"{p[1]} ({p[2]}) - ₹{price_rs:.2f}", callback_data=f"buy_{p[0]}"))
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text("Select a product to buy:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("buy_"):
        bot.answer_callback_query(call.id)
        product_id = int(call.data.split("_")[1])
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT name, price FROM products WHERE product_id = ?', (product_id,))
        prod = cursor.fetchone()
        
        if not prod:
            bot.answer_callback_query(call.id, "Product not found!")
            conn.close()
            return
            
        prod_name, price_paise = prod
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        user_res = cursor.fetchone()
        balance_paise = user_res[0] if user_res else 0
        
        if balance_paise < price_paise:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Add Balance", callback_data="add_balance"))
            markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
            bot.edit_message_text(f"❌ Insufficient balance! You need ₹{price_paise/100:.2f}, but you have ₹{balance_paise/100:.2f}.", call.message.chat.id, call.message.message_id, reply_markup=markup)
            conn.close()
            return
            
        cursor.execute('SELECT key_id, key_code FROM stock WHERE product_id = ? AND is_sold = 0 LIMIT 1', (product_id,))
        stock_item = cursor.fetchone()
        
        if not stock_item:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
            bot.edit_message_text("❌ Sorry, this product is currently out of stock!", call.message.chat.id, call.message.message_id, reply_markup=markup)
            conn.close()
            return
            
        key_id, key_code = stock_item
        
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (price_paise, user_id))
        cursor.execute('UPDATE stock SET is_sold = 1 WHERE key_id = ?', (key_id,))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('INSERT INTO history (user_id, product_name, key_code, date) VALUES (?, ?, ?, ?)', (user_id, prod_name, key_code, now_str))
        conn.commit()
        conn.close()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(f"✅ Purchase Successful!\n\n📦 Product: {prod_name}\n🔑 Key: `{key_code}`\n\nSave this key securely!", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "profile":
        bot.answer_callback_query(call.id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT phone, balance FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        phone = user[0] if user else "Not Verified"
        balance_rs = (user[1] if user else 0) / 100.0
        
        text = f"👤 **Your Profile**\n\n🆔 ID: `{user_id}`\n📱 Phone: `{phone}`\n💰 Balance: ₹{balance_rs:.2f}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "referrals":
        bot.answer_callback_query(call.id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT ref_level1, ref_level2, ref_level3 FROM users WHERE user_id = ?', (user_id,))
        refs = cursor.fetchone()
        conn.close()
        
        r1 = refs[0] if refs else 0
        r2 = refs[1] if refs else 0
        r3 = refs[2] if refs else 0
        
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        
        text = (
            f"👥 **3-Level Referral Program**\n\n"
            f"Earn instant commission when your referrals top up:\n"
            f"• Level 1: {int(REF_COMMISSION_L1*100)}% commission\n"
            f"• Level 2: {int(REF_COMMISSION_L2*100)}% commission\n"
            f"• Level 3: {int(REF_COMMISSION_L3*100)}% commission\n\n"
            f"• L1 Referrals: **{r1}** users\n"
            f"• L2 Referrals: **{r2}** users\n"
            f"• L3 Referrals: **{r3}** users\n\n"
            f"🔗 **Your Referral Link:**\n`{ref_link}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_balance":
        bot.answer_callback_query(call.id)
        text = (
            f"💳 **Add Balance via FamePay / UPI**\n\n"
            f"1. Send any amount (₹1 to ₹10,000) to UPI ID: `{FAMEPAY_UPI_ID}`\n"
            f"2. Click below to submit your payment details (Amount & 12-digit UTR)."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Submit Payment (Amount & UTR)", callback_data="submit_deposit"))
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "submit_deposit":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Send your payment details as:\n`Amount | 12-digit UTR`\nExample: `150 | 412345678901`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_user_deposit)

    elif call.data == "spin":
        bot.answer_callback_query(call.id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT last_spin FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        last_spin_str = res[0] if res else ""
        
        now = datetime.now()
        if last_spin_str:
            last_spin_time = datetime.strptime(last_spin_str, "%Y-%m-%d %H:%M:%S")
            if now - last_spin_time < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last_spin_time)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
                bot.edit_message_text(f"⏳ You have already spun today!\nTry again in {hours}h {minutes}m.", call.message.chat.id, call.message.message_id, reply_markup=markup)
                conn.close()
                return
                
        reward_paise = random.randint(100, 2000)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('UPDATE users SET balance = balance + ?, last_spin = ? WHERE user_id = ?', (reward_paise, now_str, user_id))
        conn.commit()
        conn.close()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(f"🎉 Congratulations! You won ₹{reward_paise/100:.2f} from your Daily Spin!", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "history":
        bot.answer_callback_query(call.id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT product_name, key_code, date FROM history WHERE user_id = ? ORDER BY order_id DESC LIMIT 5', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            text = "📜 **Your Purchase History**\n\nNo purchases yet."
        else:
            text = "📜 **Your Last Purchases:**\n\n"
            for r in rows:
                text += f"• **{r[0]}**\n  Key: `{r[1]}`\n  Date: {r[2]}\n\n"
                
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "support":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
        bot.edit_message_text("💬 Contact support for any queries.", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "main_menu":
        bot.answer_callback_query(call.id)
        show_main_menu(call.message.chat.id)

    elif call.data == "admin_panel":
        perms = get_staff_perms(user_id)
        if is_owner(user_id) or any(perms.values()):
            bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup()
            if perms['stock'] or is_owner(user_id):
                markup.add(types.InlineKeyboardButton("➕ Add Product", callback_data="admin_add_prod"))
                markup.add(types.InlineKeyboardButton("📦 Add Stock Keys", callback_data="admin_add_stock"))
            if perms['deposit'] or is_owner(user_id):
                markup.add(types.InlineKeyboardButton("👥 Pending Deposits", callback_data="admin_view_deposits"))
            if is_owner(user_id):
                markup.add(types.InlineKeyboardButton("🛠️ Manage Staff Roles", callback_data="admin_manage_staff"))
            markup.add(types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu"))
            bot.edit_message_text("⚙️ **Admin Panel**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "admin_add_prod":
        perms = get_staff_perms(user_id)
        if perms['stock'] or is_owner(user_id):
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "Send product details as:\n`Name | Duration | Price (in ₹)`\nExample: `Netflix | 1 Month | 149`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_add_product)

    elif call.data == "admin_add_stock":
        perms = get_staff_perms(user_id)
        if perms['stock'] or is_owner(user_id):
            bot.answer_callback_query(call.id)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT product_id, name FROM products')
            products = cursor.fetchall()
            conn.close()

            if not products:
                bot.send_message(call.message.chat.id, "⚠️ No products exist yet. Add a product first.")
                return

            msg = bot.send_message(
                call.message.chat.id,
                "Send stock as:\n`ProductID | Key1,Key2,Key3`\n\nAvailable products:\n" +
                "\n".join(f"`{p[0]}` - {p[1]}" for p in products),
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, process_add_stock)

    elif call.data == "admin_view_deposits":
        perms = get_staff_perms(user_id)
        if perms['deposit'] or is_owner(user_id):
            bot.answer_callback_query(call.id)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT deposit_id, user_id, amount, utr, date FROM deposits WHERE status = ?', ('PENDING',))
            deposits = cursor.fetchall()
            conn.close()

            if not deposits:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_panel"))
                bot.edit_message_text("✅ No pending deposit requests found.", call.message.chat.id, call.message.message_id, reply_markup=markup)
                return

            markup = types.InlineKeyboardMarkup()
            for d in deposits:
                amount_rs = d[2] / 100.0
                markup.add(types.InlineKeyboardButton(f"Approve ₹{amount_rs:.2f} | UTR: {d[3]}", callback_data=f"approve_dep_{d[0]}"))
            markup.add(types.InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_panel"))
            bot.edit_message_text("📋 **Pending UTR Requests:**\nClick any to approve and credit balance:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("approve_dep_"):
        perms = get_staff_perms(user_id)
        if perms['deposit'] or is_owner(user_id):
            bot.answer_callback_query(call.id)
            dep_id = int(call.data.split("_")[2])
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, amount, utr, status FROM deposits WHERE deposit_id = ?', (dep_id,))
            dep = cursor.fetchone()
            
            if not dep or dep[3] != 'PENDING':
                bot.send_message(call.message.chat.id, "❌ Deposit request already processed or not found.")
                conn.close()
                return
                
            target_user_id, amount_paise, utr_code, _ = dep
            
            cursor.execute('UPDATE deposits SET status = ? WHERE deposit_id = ? AND status = ?', ('APPROVED', dep_id, 'PENDING'))
            if cursor.rowcount == 0:
                bot.send_message(call.message.chat.id, "⚠️ Already processed.")
                conn.close()
                return
                
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount_paise, target_user_id))
            
            cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (target_user_id,))
            u_info = cursor.fetchone()
            if u_info and u_info[0]:
                l1_id = u_info[0]
                l1_comm = round(amount_paise * REF_COMMISSION_L1)
                if l1_comm > 0:
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (l1_comm, l1_id))
                    try:
                        bot.send_message(l1_id, f"🎁 You received ₹{l1_comm/100:.2f} commission from Level 1 referral deposit!")
                    except Exception:
                        pass
                    
                cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (l1_id,))
                l2_info = cursor.fetchone()
                if l2_info and l2_info[0]:
                    l2_id = l2_info[0]
                    l2_comm = round(amount_paise * REF_COMMISSION_L2)
                    if l2_comm > 0:
                        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (l2_comm, l2_id))
                        try:
                            bot.send_message(l2_id, f"🎁 You received ₹{l2_comm/100:.2f} commission from Level 2 referral deposit!")
                        except Exception:
                            pass
                        
                    cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (l2_id,))
                    l3_info = cursor.fetchone()
                    if l3_info and l3_info[0]:
                        l3_id = l3_info[0]
                        l3_comm = round(amount_paise * REF_COMMISSION_L3)
                        if l3_comm > 0:
                            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (l3_comm, l3_id))
                            try:
                                bot.send_message(l3_id, f"🎁 You received ₹{l3_comm/100:.2f} commission from Level 3 referral deposit!")
                            except Exception:
                                pass

            conn.commit()
            conn.close()
            
            bot.send_message(call.message.chat.id, f"✅ Successfully approved ₹{amount_paise/100:.2f} for UTR `{utr_code}`, credited user, and distributed referral commissions!", parse_mode="Markdown")
            try:
                bot.send_message(target_user_id, f"🎉 Your deposit of ₹{amount_paise/100:.2f} has been approved and added to your wallet!")
            except Exception:
                pass

    elif call.data == "admin_manage_staff" and is_owner(user_id):
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Send staff details as:\n`UserID | Deposit(0/1) | Stock(0/1)`\nExample: `987654321 | 1 | 1`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_manage_staff)

def process_user_deposit(message):
    user_id = message.from_user.id
    try:
        parts = message.text.split("|")
        amount_rs = float(parts[0].strip())
        utr = parts[1].strip()
        
        if not (1 <= amount_rs <= 10000):
            bot.send_message(message.chat.id, "❌ Invalid amount! Amount must be between ₹1 and ₹10,000.")
            return
            
        if not utr.isdigit() or len(utr) != 12:
            bot.send_message(message.chat.id, "❌ Invalid UTR format! A valid UPI UTR must be exactly 12 digits.")
            return
            
        amount_paise = round(amount_rs * 100)
            
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT deposit_id FROM deposits WHERE utr = ?', (utr,))
        if cursor.fetchone():
            bot.send_message(message.chat.id, "⚠️ This UTR has already been submitted!")
            conn.close()
            return
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('INSERT INTO deposits (user_id, amount, utr, date) VALUES (?, ?, ?, ?)', (user_id, amount_paise, utr, now_str))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Deposit request for ₹{amount_rs:.2f} (UTR: `{utr}`) submitted successfully! Staff will verify and credit your balance shortly.", parse_mode="Markdown")
        show_main_menu(message.chat.id)
    except Exception:
        bot.send_message(message.chat.id, "❌ Invalid format. Please use: `Amount | UTR`", parse_mode="Markdown")

def process_manage_staff(message):
    if not is_owner(message.from_user.id):
        return
    try:
        parts = message.text.split("|")
        staff_id = int(parts[0].strip())
        dep = int(parts[1].strip())
        stk = int(parts[2].strip())
        
        if dep not in (0, 1) or stk not in (0, 1):
            bot.send_message(message.chat.id, "❌ Permission flags must be strictly 0 or 1.")
            return
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO staff (user_id, can_approve_deposits, can_manage_stock) 
                          VALUES (?, ?, ?)
                          ON CONFLICT(user_id) DO UPDATE SET can_approve_deposits=excluded.can_approve_deposits, 
                          can_manage_stock=excluded.can_manage_stock''', 
                       (staff_id, dep, stk))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Staff permissions updated successfully for User ID `{staff_id}`!", parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ Error updating staff. Check format.")

def process_add_product(message):
    perms = get_staff_perms(message.from_user.id)
    if not perms['stock'] and not is_owner(message.from_user.id):
        return
    try:
        parts = message.text.split("|")
        name = parts[0].strip()
        duration = parts[1].strip()
        price_rs = float(parts[2].strip())
        price_paise = round(price_rs * 100)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO products (name, duration, price) VALUES (?, ?, ?)', (name, duration, price_paise))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Product '{name}' added successfully!")
    except Exception:
        bot.send_message(message.chat.id, "❌ Error adding product. Check format.")

def process_add_stock(message):
    perms = get_staff_perms(message.from_user.id)
    if not perms['stock'] and not is_owner(message.from_user.id):
        return
    try:
        parts = message.text.split("|")
        product_id = int(parts[0].strip())
        keys = [k.strip() for k in parts[1].split(",") if k.strip()]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM products WHERE product_id = ?', (product_id,))
        prod = cursor.fetchone()
        if not prod:
            bot.send_message(message.chat.id, "❌ Invalid product ID.")
            conn.close()
            return

        cursor.executemany(
            'INSERT INTO stock (product_id, key_code) VALUES (?, ?)',
            [(product_id, k) for k in keys]
        )
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ Added {len(keys)} key(s) to '{prod[0]}'.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Error adding stock. Check format.")

if __name__ == "__main__":
    print("Bot is running with Owner ID 8914163493 and complete setup...")
    bot.infinity_polling()
