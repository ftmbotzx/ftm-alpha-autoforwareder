# bot.py
import os
import json
import logging
import asyncio
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

# --- CONFIG ---
CONFIG_FILE = "ftm_config.json"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8348960801:AAEu91n45m5c_g5s1U75A5a0_DMHsFkCqjk")
API_ID = int(os.environ.get("API_ID", "8012239"))
API_HASH = os.environ.get("API_HASH", "171e6f1bf66ed8dcc5140fbe827b6b08")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "7744665378"))

# Conversation states
(
    AWAIT_SESSION, AWAIT_PHONE, AWAIT_CODE, AWAIT_2FA,
    AWAIT_SOURCE_ADD, AWAIT_TARGET_ADD, AWAIT_CAPTION,
    AWAIT_SOURCE_REMOVE, AWAIT_TARGET_REMOVE
) = range(9)

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
userbot = None
config = {}

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
                session_string=config["userbot_session"]
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

# --- FORWARDER ---
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
        [InlineKeyboardButton("📥 Source Channels", callback_data="source_menu"),
         InlineKeyboardButton("📤 Target Channels", callback_data="target_menu")],
        [InlineKeyboardButton("📝 Custom Caption", callback_data="caption_menu")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("🔄 Restart Userbot", callback_data="restart_userbot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)

# --- START COMMAND ---
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
