import os
import asyncio
import logging
import threading
import subprocess
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
logging.getLogger("httpx").setLevel(logging.WARNING)

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

    try:
        mm_url = f"https://api.mymemory.translated.net/get?q={q}&langpair={src}|{target}"
        req = urllib.request.Request(mm_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = data["responseData"]["translatedText"]
            if result and "MYMEMORY WARNING" not in result:
                return result.strip()
    except Exception as e:
        logger.warning(f"MyMemory failed: {e}")

    try:
        g_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={target}&dt=t&q={q}"
        req = urllib.request.Request(g_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data and data[0]:
                result = "".join(chunk[0] for chunk in data[0] if chunk[0])
                return result.strip()
    except Exception as e:
        logger.error(f"Google Translate also failed: {e}")

    return "Translation error"

def recognize_speech_sync(ogg_path, wav_path):
    """Convert ogg->wav using ffmpeg, then recognize with SpeechRecognition."""
    import speech_recognition as sr

    subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, timeout=30
    )

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)

    for lang_code in ["ru-RU", "zh-CN"]:
        try:
            text = recognizer.recognize_google(audio_data, language=lang_code)
            if text:
                return text
        except sr.UnknownValueError:
            continue
        except Exception as e:
            logger.warning(f"Recognition error ({lang_code}): {e}")
            continue
    return None

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bridge Translator ZH <-> RU\n\n"
        "Send text, voice, or photo with text - I translate automatically!"
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
    await update.message.chat.send_action('typing')
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"/tmp/{voice.file_id}.ogg"
    wav_path = f"/tmp/{voice.file_id}.wav"
    await file.download_to_drive(ogg_path)

    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, recognize_speech_sync, ogg_path, wav_path)

        if not text:
            await update.message.reply_text("Could not recognize speech. Please try again, speaking clearly.")
            return

        source_lang = detect_language(text)
        translated = translate_sync(text, source_lang)
        flag = "RU:" if source_lang == 'zh' else "ZH:"
        await update.message.reply_text(f"рџЋ¤ {text}\n{flag} {translated}")
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await update.message.reply_text("Error processing voice message.")
    finally:
        for p in (ogg_path, wav_path):
            if os.path.exists(p):
                os.remove(p)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photo OCR: coming soon. Please send text or voice for now.")

async def main():
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
