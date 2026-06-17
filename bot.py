import os
import logging
import tempfile
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8667872645:AAHrOlh-JFT9rm2Dq44Fob9HRigyGJDbLlc")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# ОПРЕДЕЛЕНИЕ ЯЗЫКА
# ============================================================
def detect_language(text: str) -> str:
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return 'zh' if chinese_chars > len(text) * 0.2 else 'ru'

# ============================================================
# ПЕРЕВОД ЧЕРЕЗ GOOGLE TRANSLATE
# ============================================================
async def translate_text(text: str, source_lang: str) -> str:
    target_lang = 'ru' if source_lang == 'zh' else 'zh-CN'
    src = 'zh-CN' if source_lang == 'zh' else 'ru'
    url = (
        f"https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={src}&tl={target_lang}&dt=t&q={httpx.URL(text)}"
    )
    # Правильный способ через params
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

# ============================================================
# РАСПОЗНАВАНИЕ РЕЧИ
# ============================================================
async def transcribe_voice(file_path: str) -> str:
    """Распознаём голосовое сообщение через Google Speech API (бесплатный endpoint)"""
    try:
        import subprocess
        # Конвертируем ogg в wav через ffmpeg
        wav_path = file_path.replace('.ogg', '.wav')
        subprocess.run(
            ['ffmpeg', '-i', file_path, '-ar', '16000', '-ac', '1', wav_path, '-y'],
            capture_output=True
        )

        # Используем SpeechRecognition с Google
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)

        # Пробуем распознать как русский, потом как китайский
        try:
            text = recognizer.recognize_google(audio, language='ru-RU')
            return text
        except:
            try:
                text = recognizer.recognize_google(audio, language='zh-CN')
                return text
            except:
                return ""
    except Exception as e:
        logger.error(f"Voice recognition error: {e}")
        return ""

# ============================================================
# OCR ДЛЯ ФОТО
# ============================================================
async def ocr_image(file_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        # Пробуем русский + китайский + английский
        text = pytesseract.image_to_string(img, lang='chi_sim+rus+eng')
        return text.strip()
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""

# ============================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    source_lang = detect_language(text)
    await update.message.chat.send_action('typing')
    translated = await translate_text(text, source_lang)
    flag = "🇷🇺" if source_lang == 'zh' else "🇨🇳"
    await update.message.reply_text(f"{flag} {translated}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action('typing')
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
        tmp_path = tmp.name

    await file.download_to_drive(tmp_path)
    recognized = await transcribe_voice(tmp_path)

    if not recognized:
        await update.message.reply_text("❌ Не удалось распознать речь. Говорите чётче.")
        return

    source_lang = detect_language(recognized)
    translated = await translate_text(recognized, source_lang)
    flag_orig = "🇨🇳" if source_lang == 'zh' else "🇷🇺"
    flag_trans = "🇷🇺" if source_lang == 'zh' else "🇨🇳"
    await update.message.reply_text(
        f"{flag_orig} {recognized}\n\n{flag_trans} {translated}"
    )

    # Очистка
    try:
        os.remove(tmp_path)
        os.remove(tmp_path.replace('.ogg', '.wav'))
    except:
        pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action('typing')
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document

    if photo:
        file = await context.bot.get_file(photo.file_id)
        suffix = '.jpg'
    elif doc and doc.mime_type and doc.mime_type.startswith('image/'):
        file = await context.bot.get_file(doc.file_id)
        suffix = '.jpg'
    else:
        await update.message.reply_text("❌ Пришлите фото или изображение документа.")
        return

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    await file.download_to_drive(tmp_path)
    recognized = await ocr_image(tmp_path)

    try:
        os.remove(tmp_path)
    except:
        pass

    if not recognized:
        await update.message.reply_text("❌ Не удалось распознать текст на фото. Попробуйте более чёткое изображение.")
        return

    source_lang = detect_language(recognized)
    translated = await translate_text(recognized, source_lang)
    flag_orig = "🇨🇳" if source_lang == 'zh' else "🇷🇺"
    flag_trans = "🇷🇺" if source_lang == 'zh' else "🇨🇳"
    await update.message.reply_text(
        f"{flag_orig} Распознано:\n{recognized}\n\n{flag_trans} Перевод:\n{translated}"
    )

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌉 Привет! Я переводчик 中文 ↔ Русский.\n\n"
        "Просто пришли мне:\n"
        "• 💬 Текст — переведу\n"
        "• 🎤 Голосовое — распознаю и переведу\n"
        "• 📷 Фото с текстом — прочитаю и переведу\n\n"
        "Язык определяю автоматически!"
    )

# ============================================================
# ЗАПУСК БОТА
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/start'), handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))

    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
