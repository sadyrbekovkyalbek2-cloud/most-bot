# -*- coding: utf-8 -*-
import os
import logging
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple HTTP server to keep Render happy
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def detect_language(text):
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return 'zh' if chinese_chars > len(text) * 0.2 else 'ru'

async def translate_text(text, source_lang):
    target_lang = 'ru' if source_lang == 'zh' else 'zh-CN'
    src = 'zh-CN' if source_lang == 'zh' else 'ru'
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": src, "tl": target_lang, "dt": "t", "q": text},
            timeout=15
        )
        data = resp.json()
        result = ""
        if data and data[0]:
            for chunk in data[0]:
                if chunk[0]:
                    result += chunk[0]
        return result.strip()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    source_lang = detect_language(text)
    await update.message.chat.send_action('typing')
    translated = await translate_text(text, source_lang)
    flag = "RU:" if source_lang == 'zh' else "ZH:"
    await update.message.reply_text(f"{flag} {translated}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Voice recognition coming soon. Send text for now.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photo OCR coming soon. Send text for now.")

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bridge Translator ZH <-> RU\n\n"
        "Send me any text in Russian or Chinese - I will translate automatically!"
    )

def main():
    # Start health server in background thread
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    logger.info("Health server started")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/start'), handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
