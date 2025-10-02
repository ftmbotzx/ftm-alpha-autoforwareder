# FTM ALPHA FORWARDER BOT (Full Single-File Version)
# Built by Gemini + Extended with Phone Login and Render Webport
# Features: Inline settings menu, phone/session login, channel management, captions, status, restart

import os
import json
import logging
import asyncio
import threading
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from pyrogram import Client, filters as pyrogram_filters
from pyrogram.errors import RPCError, SessionPasswordNeeded

from fastapi import FastAPI
import uvicorn

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8348960801:AAEu91n45m5c_g5s1U75A5a0_DMHsFkCqjk")
API_ID = int(os.environ.get("API_ID", "8012239"))
API_HASH = os.environ.get("API_HASH", "171e6f1bf66ed8dcc5140fbe827b6b08")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "7744665378"))

CONFIG_FILE = "ftm_config.json"
userbot = None
config = {}

# Conversation states
(
    AWAIT_SESSION, AWAIT_PHONE, AWAIT_CODE, AWAIT_2FA, 
    AWAIT_SOURCE_ADD, AWAIT_TARGET_ADD, AWAIT_CAPTION
) = range(7)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- CONFIG MANAGEMENT ---
def load_config():
    global config
    default_config = {
        "userbot_session": None,
        "source_channels": [],
        "target_channels": [],
        "custom_caption": "",
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        for k, v in default_config.items():
            config.setdefault(k, v)
    else:
        config = default_config
    logger.info("Config loaded.")

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    logger.info("Config saved.")

# --- DECORATOR ---
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- USERBOT FUNCTIONS ---
async def start_userbot():
    global userbot
    if config.get("userbot_session"):
        try:
            userbot = Client(
                name="userbot_session",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=config["userbot_session"],
            )
            await userbot.start()
            me = await userbot.get_me()
            logger.info(f"Userbot started as {me.first_name} (@{me.username}).")
            if config.get("source_channels"):
                userbot.add_handler(
                    pyrogram.MessageHandler(forwarder_handler, pyrogram_filters.chat(config["source_channels"]))
                )
            return f"✅ Userbot logged in as {me.first_name} (@{me.username})"
        except RPCError as e:
            userbot = None
            return f"❌ RPCError: {e}"
        except Exception as e:
            userbot = None
            return f"❌ Error: {e}"
    else:
        return "⚠️ Userbot session not set. Please login."

async def stop_userbot():
    global userbot
    if userbot and userbot.is_connected:
        await userbot.stop()
        logger.info("Userbot stopped.")
        userbot = None

async def restart_userbot_logic():
    await stop_userbot()
    status_msg = await start_userbot()
    return status_msg

# --- FORWARDING LOGIC ---
async def forwarder_handler(client, message):
    if not config["target_channels"]:
        return
    final_caption = ""
    orig = message.caption or ""
    custom = config.get("custom_caption","")
    if orig and custom:
        final_caption = f"{orig}\n\n{custom}"
    elif orig:
        final_caption = orig
    elif custom:
        final_caption = custom
    for target in config["target_channels"]:
        try:
            await message.copy(chat_id=target, caption=final_caption if final_caption else None)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Forward failed to {target}: {e}")

# --- BOT MENU ---
async def show_main_menu(update, context, text="🔧 *FTM Alpha Forwarder Settings*"):
    keyboard = [
        [InlineKeyboardButton("👤 Login", callback_data="login_menu")],
        [InlineKeyboardButton("📥 Source Channels", callback_data="source_menu"), InlineKeyboardButton("📤 Target Channels", callback_data="target_menu")],
        [InlineKeyboardButton("📝 Custom Caption", callback_data="caption_menu")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("🔄 Restart Userbot", callback_data="restart_userbot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)

# --- /start ---
@admin_only
async def start_command(update, context):
    welcome = "👋 Welcome Admin!\n\nUse the menu to configure login, channels, captions and status."
    await show_main_menu(update, context, welcome)

# --- BUTTON HANDLER ---
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "main_menu":
        await show_main_menu(update, context)
    elif data == "login_menu":
        await login_menu(update, context)
    elif data == "session_login":
        await session_login_start(update, context)
    elif data == "phone_login":
        await phone_login_start(update, context)
    elif data == "verify_code":
        await code_verify_start(update, context)
    elif data == "source_menu":
        await channel_menu(update, context, "source")
    elif data == "target_menu":
        await channel_menu(update, context, "target")
    elif data.startswith("add_"):
        await channel_add_start(update, context)
    elif data.startswith("remove_"):
        await channel_remove_start(update, context)
    elif data.startswith("del_"):
        await channel_remove_selection(update, context)
    elif data == "caption_menu":
        await caption_menu(update, context)
    elif data == "set_caption":
        await caption_set_start(update, context)
    elif data == "clear_caption":
        await caption_clear(update, context)
    elif data == "status":
        await status_command(update, context)
    elif data == "restart_userbot":
        await restart_userbot_command(update, context)

# --- LOGIN MENU ---
async def login_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("🔗 Session String Login", callback_data="session_login")],
        [InlineKeyboardButton("📱 Phone Number Login", callback_data="phone_login")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await update.callback_query.edit_message_text("👤 Login Options:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- SESSION LOGIN ---
async def session_login_start(update, context):
    await update.callback_query.message.reply_text("Send me your Pyrogram session string (or /cancel).")
    return AWAIT_SESSION

async def session_login_receive(update, context):
    session_str = update.message.text.strip()
    config["userbot_session"] = session_str
    save_config()
    await update.message.reply_text("✅ Session saved. Restarting userbot...")
    status_msg = await restart_userbot_logic()
    await show_main_menu(update, context, f"⚙️ Settings Updated\n\n{status_msg}")
    return ConversationHandler.END

# --- PHONE LOGIN ---
async def phone_login_start(update, context):
    await update.callback_query.message.reply_text("Send your phone number in international format (e.g., +919876543210)")
    return AWAIT_PHONE

async def phone_receive(update, context):
    phone = update.message.text.strip()
    context.user_data["phone_number"] = phone
    client = Client("userbot_phone", api_id=API_ID, api_hash=API_HASH)
    await client.start()
    try:
        await client.send_code(phone)
        await update.message.reply_text("✅ Code sent. Use /verify <code> [2FA password if any]")
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending code: {e}")
    await client.stop()
    return ConversationHandler.END

async def verify_code_command(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /verify <code> [2FA password]")
        return
    code = args[0]
    password = args[1] if len(args) > 1 else None
    phone = context.user_data.get("phone_number")
    client = Client("userbot_phone", api_id=API_ID, api_hash=API_HASH)
    await client.start()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeeded:
        if password:
            await client.check_password(password)
        else:
            await update.message.reply_text("❌ 2FA required. Provide with /verify <code> <password>")
            await client.stop()
            return
    session_str = await client.export_session_string()
    config["userbot_session"] = session_str
    save_config()
    await update.message.reply_text("✅ Phone login successful. Session saved. Restarting userbot...")
    await client.stop()
    status_msg = await restart_userbot_logic()
    await show_main_menu(update, context, f"⚙️ Settings Updated\n\n{status_msg}")

# --- CHANNEL MENU ---
async def channel_menu(update, context, ctype):
    channels = config.get(f"{ctype}_channels", [])
    text = f"*{'Source' if ctype=='source' else 'Target'} Channels*\n\nCurrent:\n"
    text += "\n".join(f"`{c}`" for c in channels) if channels else "_None_"
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data=f"add_{ctype}")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data=f"remove_{ctype}")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=constants.ParseMode.MARKDOWN_V2)

async def channel_add_start(update, context):
    ctype = "source" if "source" in update.callback_query.data else "target"
    context.user_data["channel_type"] = ctype
    await update.callback_query.message.reply_text(f"Send the channel ID or username to add to {ctype} channels.")
    return AWAIT_SOURCE_ADD if ctype=="source" else AWAIT_TARGET_ADD

async def channel_add_receive(update, context):
    ctype = context.user_data["channel_type"]
    ch_list_key = f"{ctype}_channels"
    ch_id = update.message.text.strip()
    try:
        ch_id_int = int(ch_id)
        ch_id = ch_id_int
    except:
        pass
    if ch_id not in config[ch_list_key]:
        config[ch_list_key].append(ch_id)
        save_config()
        await update.message.reply_text(f"✅ Channel {ch_id} added to {ctype} channels.")
    else:
        await update.message.reply_text(f"⚠️ Already in {ctype} channels.")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def channel_remove_start(update, context):
    ctype = "source" if "source" in update.callback_query.data else "target"
    context.user_data["channel_type"] = ctype
    ch_list = config.get(f"{ctype}_channels", [])
    if not ch_list:
        await update.callback_query.answer("No channels to remove.", show_alert=True)
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(str(c), callback_data=f"del_{ctype}_{c}")] for c in ch_list]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"{ctype}_menu")])
    await update.callback_query.edit_message_text("Select channel to remove:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAIT_SOURCE_REMOVE if ctype=="source" else AWAIT_TARGET_REMOVE

async def channel_remove_selection(update, context):
    _, ctype, ch_id_str = update.callback_query.data.split("_",2)
    try: ch_id = int(ch_id_str)
    except: ch_id = ch_id_str
    key = f"{ctype}_channels"
    if ch_id in config[key]:
        config[key].remove(ch_id)
        save_config()
        await update.callback_query.answer(f"✅ {ch_id} removed.", show_alert=True)
    await channel_menu(update, context, ctype)
    return ConversationHandler.END

# --- CAPTION MENU ---
async def caption_menu(update, context):
    caption = config.get("custom_caption") or "_Not set_"
    text = f"📝 *Custom Caption*\n\nCurrent:\n{caption}"
    keyboard = [
        [InlineKeyboardButton("✏️ Set Caption", callback_data="set_caption")],
        [InlineKeyboardButton("🗑 Clear Caption", callback_data="clear_caption")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=constants.ParseMode.MARKDOWN_V2)

async def caption_set_start(update, context):
    await update.callback_query.message.reply_text("Send the new custom caption:")
    return AWAIT_CAPTION

async def caption_set_receive(update, context):
    config["custom_caption"] = update.message.text
    save_config()
    await update.message.reply_text("✅ Caption updated.")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def caption_clear(update, context):
    config["custom_caption"] = ""
    save_config()
    await update.callback_query.answer("✅ Caption cleared.", show_alert=True)
    await caption_menu(update, context)

# --- STATUS & RESTART ---
@admin_only
async def status_command(update, context):
    userbot_status = "🔴 Not Running"
    uname = "N/A"
    if userbot and userbot.is_connected:
        me = await userbot.get_me()
        uname = f"@{me.username}" if me.username else me.first_name
        userbot_status = f"✅ Running as {uname}"
    sources = "\n".join(f"`{s}`" for s in config["source_channels"]) or "_None_"
    targets = "\n".join(f"`{t}`" for t in config["target_channels"]) or "_None_"
    caption = config.get("custom_caption") or "_None_"
    text = f"📊 *FTM Alpha Forwarder Status*\n\n*Userbot:* {userbot_status}\n\n*Source:* {sources}\n*Target:* {targets}\n*Caption:* `{caption}`"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))
    else:
        await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def restart_userbot_command(update, context):
    await update.callback_query.answer("🔄 Restarting...")
    msg = await restart_userbot_logic()
    await update.callback_query.edit_message_text(f"🔄 Userbot restarted.\n\n{msg}", parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))

# --- CANCEL ---
async def cancel_conversation(update, context):
    await update.message.reply_text("Operation cancelled.")
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- FASTAPI FOR RENDER ---
app = FastAPI()
@app.get("/")
async def root(): return {"status":"FTM Alpha Forwarder Bot Running"}

def start_web():
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- MAIN ---
async def post_init(application):
    await start_userbot()

def main():
    load_config()
    threading.Thread(target=start_web).start()

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Conversation Handlers
    session_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, session_login_receive)],
        states={AWAIT_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, session_login_receive)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_user=True,
    )
    phone_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, phone_receive)],
        states={AWAIT_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, phone_receive)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_user=True,
    )
    add_channel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_receive)],
        states={AWAIT_SOURCE_ADD:[MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_receive)],
                AWAIT_TARGET_ADD:[MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_receive)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_user=True,
    )
    remove_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(channel_remove_start, pattern="^remove_")],
        states={AWAIT_SOURCE_REMOVE:[CallbackQueryHandler(channel_remove_selection, pattern="^del_source_")],
                AWAIT_TARGET_REMOVE:[CallbackQueryHandler(channel_remove_selection, pattern="^del_target_")]
