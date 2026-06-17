import os
import logging
import tempfile
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detect_language(text: str) -> str:
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return 'zh' if chinese_chars > len(text) * 0.2 else 'ru'

async def translate_text(text: str, source_lang: str) -> str:
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

async def transcribe_voice(file_path: str) -> str:
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        # Try to convert ogg to wav using pydub
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(file_path)
            wav_path = file_path + '.wav'
            audio.export(wav_path, format='wav')
        except:
            wav_path = file_path

        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        try:
            return recognizer.recognize_google(audio, language='ru-RU')
        except:
            try:
                return recognizer.recognize_google(audio, language='zh-CN')
            except:
                return ""
    except Exception as e:
        logger.error(f"Voice error: {e}")
        return ""

async def ocr_image(file_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang='chi_sim+rus+eng')
        return text.strip()
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    source_lang = detect_language(text)
    await update.message.chat.send_action('typing')
    translated = await translate_text(text, source_lang)
    flag = "рџ‡·рџ‡є" if source_lang == 'zh' else "рџ‡Ёрџ‡і"
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
    try:
        os.remove(tmp_path)
    except:
        pass
    if not recognized:
        await update.message.reply_text("вќЊ РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃРїРѕР·РЅР°С‚СЊ СЂРµС‡СЊ. Р“РѕРІРѕСЂРёС‚Рµ С‡С‘С‚С‡Рµ.")
        return
    source_lang = detect_language(recognized)
    translated = await translate_text(recognized, source_lang)
    flag_orig = "рџ‡Ёрџ‡і" if source_lang == 'zh' else "рџ‡·рџ‡є"
    flag_trans = "рџ‡·рџ‡є" if source_lang == 'zh' else "рџ‡Ёрџ‡і"
    await update.message.reply_text(f"{flag_orig} {recognized}\n\n{flag_trans} {translated}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action('typing')
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document
    if photo:
        file = await context.bot.get_file(photo.file_id)
    elif doc and doc.mime_type and doc.mime_type.startswith('image/'):
        file = await context.bot.get_file(doc.file_id)
    else:
        await update.message.reply_text("вќЊ РџСЂРёС€Р»РёС‚Рµ С„РѕС‚Рѕ.")
        return
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        tmp_path = tmp.name
    await file.download_to_drive(tmp_path)
    recognized = await ocr_image(tmp_path)
    try:
        os.remove(tmp_path)
    except:
        pass
    if not recognized:
        await update.message.reply_text("вќЊ РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃРїРѕР·РЅР°С‚СЊ С‚РµРєСЃС‚ РЅР° С„РѕС‚Рѕ.")
        return
    source_lang = detect_language(recognized)
    translated = await translate_text(recognized, source_lang)
    flag_orig = "рџ‡Ёрџ‡і" if source_lang == 'zh' else "рџ‡·рџ‡є"
    flag_trans = "рџ‡·рџ‡є" if source_lang == 'zh' else "рџ‡Ёрџ‡і"
    await update.message.reply_text(
        f"{flag_orig} Р Р°СЃРїРѕР·РЅР°РЅРѕ:\n{recognized}\n\n{flag_trans} РџРµСЂРµРІРѕРґ:\n{translated}"
    )

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bridge Translator: ZH <-> RU\n\n"
        "Send me:\n"
        "- Text: I will translate\n"
        "- Voice: I will recognize and translate\n"
        "- Photo with text: I will read and translate\n\n"
        "Language is detected automatically!"
    )

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
