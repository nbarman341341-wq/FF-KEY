import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import firebase_admin
from firebase_admin import credentials, firestore

# --- FIREBASE INITIALIZATION ---
cred = credentials.Certificate("max-store-bot-firebase-adminsdk-fbsvc-eb734b87bd.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- CONFIGURATION ---
BOT_TOKEN = "8857888643:AAHWFTfcv9IoQHK-5p2NQRg2t0XoI6Bx4Gg"
ADMIN_ID = 8914163493  # आपकी एडमिन आईडी
UPI_ID = "yourname@oksbi"  # यहाँ बाद में अपनी असली UPI ID डाल सकते हैं

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("🛍️ Browse Hacks / Products", callback_data="browse_products")],
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("➕ Add Product", callback_data="add_product_prompt")])
        keyboard.append([InlineKeyboardButton("🔑 Add Stock Keys (Unlimited)", callback_data="add_key_prompt")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to Key Store! Choose an option below:",
        reply_markup=reply_markup
    )

# --- BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "browse_products":
        products_ref = db.collection('products').stream()
        products = list(products_ref)
        
        if not products:
            await query.edit_message_text("No hacks/products available right now!")
            return
            
        for doc in products:
            p_data = doc.to_dict()
            p_id = doc.id
            text = f"<b>{p_data.get('name')}</b>\nPrice: ₹{p_data.get('price')}\n{p_data.get('description')}"
            
            keyboard = [[InlineKeyboardButton("🛒 Buy & Pay via UPI", callback_data=f"buy_{p_id}")]]
            if user_id == ADMIN_ID:
                keyboard.append([InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{p_id}")])
                
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "add_product_prompt" and user_id == ADMIN_ID:
        context.user_data['action'] = 'add_product'
        await query.edit_message_text(
            "Send product details in this format:\n\n"
            "Name | Price | Description\n\n"
            "Example: Free Fire VIP Hack | 299 | 30 Days Mod Menu"
        )

    elif query.data == "add_key_prompt" and user_id == ADMIN_ID:
        context.user_data['action'] = 'add_key'
        await query.edit_message_text(
            "Send keys stock in this format (You can add unlimited one by one):\n\n"
            "ProductName | KeyValue\n\n"
            "Example: Free Fire VIP Hack | FF-KEY-9999"
        )

    elif query.data.startswith("buy_"):
        p_id = query.data.split("_")[1]
        p_ref = db.collection('products').document(p_id).get()
        if p_ref.exists:
            p_data = p_ref.to_dict()
            price = p_data.get('price')
            name = p_data.get('name')
            
            payment_text = (
                f"💳 **Payment for {name}**\n"
                f"Amount: **₹{price}**\n\n"
                f"Pay to UPI ID: `{UPI_ID}`\n\n"
                f"After payment, click the button below to notify Admin."
            )
            keyboard = [[InlineKeyboardButton("✅ I Have Paid (Notify Admin)", callback_data=f"paid_{p_id}_{user_id}")]]
            await query.message.reply_text(payment_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("paid_"):
        _, p_id, buyer_id = query.data.split("_")
        p_ref = db.collection('products').document(p_id).get()
        p_name = p_ref.to_dict().get('name') if p_ref.exists else "Product"
        
        await query.edit_message_text("⏳ Payment notification sent to Admin! Please wait for approval and your key.")
        
        admin_text = (
            f"🔔 **New Payment Verification Request!**\n"
            f"Buyer ID: `{buyer_id}`\n"
            f"Product: {p_name}\n\n"
            f"Check your UPI app. If money received, click Approve below to dispatch the key automatically."
        )
        admin_keyboard = [[InlineKeyboardButton("✅ Approve & Send Key", callback_data=f"approve_{p_id}_{buyer_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(admin_keyboard))

    elif query.data.startswith("approve_") and user_id == ADMIN_ID:
        _, p_id, buyer_id = query.data.split("_")
        p_ref = db.collection('products').document(p_id).get()
        p_name = p_ref.to_dict().get('name') if p_ref.exists else "Product"
        
        keys_ref = db.collection('keys').where('product_name', '==', p_name).where('used', '==', False).limit(1).stream()
        keys_list = list(keys_ref)
        
        if not keys_list:
            await query.edit_message_text("❌ Error: No stock keys left for this product! Please add more keys first.")
            return
            
        key_doc = keys_list[0]
        key_value = key_doc.to_dict().get('key_value')
        
        db.collection('keys').document(key_doc.id).update({'used': True})
        
        try:
            await context.bot.send_message(
                chat_id=int(buyer_id),
                text=f"🎉 **Payment Approved by Admin!**\nHere is your key for **{p_name}**:\n\n`{key_value}`",
                parse_mode="Markdown"
            )
            await query.edit_message_text(f"✅ Approved successfully! Key sent to buyer: `{key_value}`")
        except Exception as e:
            await query.edit_message_text(f"⚠️ Approved, but failed to message buyer. Error: {e}")

    elif query.data.startswith("del_") and user_id == ADMIN_ID:
        p_id = query.data.split("_")[1]
        db.collection('products').document(p_id).delete()
        await query.edit_message_text("Product deleted successfully!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        action = context.user_data.get('action')
        text = update.message.text
        
        if action == 'add_product':
            try:
                name, price, desc = [x.strip() for x in text.split("|")]
                db.collection('products').add({
                    "name": name,
                    "price": float(price),
                    "description": desc
                })
                context.user_data['action'] = None
                await update.message.reply_text("✅ Product added successfully!")
            except Exception as e:
                await update.message.reply_text(f"❌ Format error. Use: Name | Price | Description. Error: {e}")
                
        elif action == 'add_key':
            try:
                p_name, key_val = [x.strip() for x in text.split("|")]
                db.collection('keys').add({
                    "product_name": p_name,
                    "key_value": key_val,
                    "used": False
                })
                await update.message.reply_text(f"✅ Key added for '{p_name}'! You can send another key or do /start.")
            except Exception as e:
                await update.message.reply_text(f"❌ Format error. Use: ProductName | KeyValue. Error: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
