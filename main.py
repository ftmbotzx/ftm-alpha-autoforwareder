# main.py
import threading
import os
from fastapi import FastAPI
import uvicorn
from bot import Application, BOT_TOKEN, post_init, load_config, start_userbot, start_command, button_handler, CommandHandler

# --- FASTAPI ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status":"FTM Alpha Forwarder Bot Running"}

def start_web():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- MAIN ---
def main():
    load_config()
    # Start web server thread
    threading.Thread(target=start_web, daemon=True).start()
    
    # Telegram bot
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("settings", start_command))
    # Add other handlers from bot.py like button_handler, conversation handlers
    
    # Start bot
    application.run_polling()

if __name__ == "__main__":
    main()
