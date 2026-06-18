import os
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import urllib.request
import urllib.parse
import json

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)   # ← добавить сюда

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

def detect_language(text):
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return 'zh' if chinese_chars > len(text) * 0.2 else 'ru'

def translate_sync(text, source_lang):
    target = 'ru' if source_lang == 'zh' else 'zh-CN'
    src = 'zh-CN' if source_lang == 'zh' else 'ru'
    q = urllib.parse.quote(text)

    # Попытка 1-2: Google Translate с повторными попытками
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={target}&dt=t&q={q}"
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data and data[0]:
                    result = "".join(chunk[0] for chunk in data[0] if chunk[0])
                    return result.strip()
        except Exception as e:
            logger.warning(f"Google Translate attempt {attempt+1} failed: {e}")
            time.sleep(1.5)

    # Запасной вариант: MyMemory API
    try:
        target_short = 'ru' if source_lang == 'zh' else 'zh-CN'
        src_short = 'zh-CN' if source_lang == 'zh' else 'ru'
        backup_url = f"https://api.mymemory.translated.net/get?q={q}&langpair={src_short}|{target_short}"
        req = urllib.request.Request(backup_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data["responseData"]["translatedText"].strip()
    except Exception as e:
        logger.error(f"Backup translation also failed: {e}")
        return "Translation error"

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bridge Translator ZH <-> RU\n\n"
        "Send text in Russian or Chinese - I translate automatically!"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    await update.message.chat.send_action('typing')
    source_lang = detect_language(text)
    translated = translate_sync(text, source_lang)
    flag = "RU:" if source_lang == 'zh' else "ZH:"
    await update.message.reply_text(f"{flag} {translated}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Voice: coming soon. Send text.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photo OCR: coming soon. Send text.")

async def main():
    # Start health server in background thread
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    logger.info(f"Health server on port {PORT}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/start'), handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))

    logger.info("Bot polling...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

