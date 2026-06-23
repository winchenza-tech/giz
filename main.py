import os
import re
import datetime
import pytz
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from google import genai
from google.genai import types

# Çevresel Değişkenler
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("Lütfen Railway Variables kısmına TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID ekleyin.")

# Kılavuz ve Soru Görsel Linkleri
IMAGE_URL_1 = "https://i.ibb.co/S4yWQrHg/MG-0345.jpg"
IMAGE_URL_2 = "https://i.ibb.co/Y748qgsP/MG-0346.jpg"
SORU_IMAGE_URL = "https://i.ibb.co/5Xcrbv87/MG-0398.jpg"

# Kullanılacak Gemini Modeli
GEMINI_MODEL = "gemini-2.5-flash"

# Gemini Ayarları
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Talimatlar, metnin düz ve sade olması ve ek açıklama yapılmaması için güncellendi.
system_instruction_text = (
    "Sadece sorunun doğrudan cevabını ver. Yanıtına düşünme sürecini, notları, sistem talimatlarını veya meta açıklamaları asla ekleme. "
    "Cevabın mutlaka en az 5 kelimeden oluşsun. "
    "Her paragrafın en başına mutlaka uygun bir emoji koy. "
    "Yazı tipini veya kalınlığını değiştirme, tüm metni düz ve sade bir formatta yaz. "
    "Markdown formatlama işaretlerini (yıldız, alt çizgi vb.) kesinlikle kullanma. "
    "Uzun cevaplarda paragrafa ayırabilirsin."
)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2

async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    guide = (
        "Es Justo Grup İçinde:\n"
        "/soru [metin] - Yapay zekaya kısa bir soru sorar.\n\n"
        "Özel Mesajda Hatırlatıcı Kurmak:\n"
        "/hatirlat [hatırlatılacak şey] [saat]\n"
        "Örnek: /hatirlat toplantıya katıl 15:40\n\n"
        "/yardim veya /start - Bu kılavuzu tekrar gösterir.\n\n"
        "Bu botun bildirim sesini normal mesaj bildirim sesinden farklı yapmanız önerilir."
    )
    
    await update.message.reply_text(guide)

    try:
        await context.bot.send_photo(
            chat_id=update.message.chat_id, 
            photo=IMAGE_URL_1, 
            caption="BİLDİRİM SESLERİNİ DEĞİŞTİRME\nAdım 1: Bildirim Menüsü"
        )
        await context.bot.send_photo(
            chat_id=update.message.chat_id, 
            photo=IMAGE_URL_2, 
            caption="Adım 2: Özel Ses Seçimi"
        )
    except Exception as e:
        await update.message.reply_text("Kılavuzu yükleyemedim tüh.")

async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        print(f"Gelen Grup ID: {update.message.chat.id} | Beklenen ID: {ALLOWED_GROUP_ID}")

    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    question_text = " ".join(context.args)
    if not question_text and update.message.reply_to_message:
        question_text = update.message.reply_to_message.text or update.message.reply_to_message.caption

    image_data = None
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        file = await context.bot.get_file(update.message.reply_to_message.photo[-1].file_id)
        image_bytes = await file.download_as_bytearray()
        image_data = types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')

    if not question_text and not image_data:
        await update.message.reply_photo(
            photo=SORU_IMAGE_URL,
            caption="Bir soru girsene bu ne böyle şimdi? Örnek: /soru hava durumu nasıl?"
        )
        return

    status_msg = await update.message.reply_text("📖 Gizem soruyu okuyor...")
    
    async def loading_animation():
        frames = [
            "☕ Gizem zihnini açmak için kahvesini yudumluyor...",
            "✍️ Gizem soruya cevap yazıyor..."
        ]
        try:
            for frame in frames:
                await asyncio.sleep(3)
                await status_msg.edit_text(frame)
        except: pass
            
    animation_task = asyncio.create_task(loading_animation())

    try:
        contents = [question_text] if question_text else []
        if image_data: contents.append(image_data)

        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction_text,
                temperature=0.7,
                max_output_tokens=150,
            )
        )
        
        animation_task.cancel()
        try: await status_msg.delete()
        except: pass

        if response and response.text:
            # Yıldızları yine de temizliyoruz ki model yine de hata yaparsa düzeltelim
            clean_response = response.text.replace("*", "")
            if len(clean_response) <= 1024:
                await update.message.reply_photo(photo=SORU_IMAGE_URL, caption=clean_response)
            else:
                await update.message.reply_photo(photo=SORU_IMAGE_URL)
                await update.message.reply_text(clean_response)
        else:
            await update.message.reply_text("Cevap üretilirken bir hata oluştu.")
            
    except Exception as e:
        animation_task.cancel()
        try: await status_msg.delete()
        except: pass
        print(f"Gemini Hatası: {e}")
        await update.message.reply_text("Cevap üretilirken bir hata oluştu.")

async def hatirlat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return ConversationHandler.END

    chat_id = update.message.chat_id
    active_reminders = 0
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name and f"_{chat_id}_" in job.name:
                active_reminders += 1

    if active_reminders >= 3:
        await update.message.reply_text("Şu anda aktif 3 adet hatırlatıcın bulunuyor. Daha fazla ekleyebilmek için mevcut olanlardan birinin tamamlanmasını bekleme veya /iptal komutu ile hepsini silebilirsin.")
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text("Hatırlatılacak o çok önemli şeyi yaz. Örnek: /hatirlat toplantıya katıl 15:40")
        return ConversationHandler.END

    possible_time = args[-1]
    
    if re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", possible_time):
        time_text = possible_time
        reminder_text = " ".join(args[:-1])
        if not reminder_text:
            await update.message.reply_text("Hatırlatılacak o dünya önemlisi şeyi de söyle. Örnek: /hatirlat toplantı 15:40")
            return ConversationHandler.END
        context.user_data["reminder_text"] = reminder_text
        context.user_data["reminder_time"] = time_text
        keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")], [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Saat {time_text} için '{reminder_text}' hatırlatıcısının önem derecesi nedir?", reply_markup=reply_markup)
        return WAITING_FOR_IMPORTANCE
    else:
        reminder_text = " ".join(args)
        context.user_data["reminder_text"] = reminder_text
        await update.message.reply_text("Hatırlatma saatini SS:DD formatında gir (Örneğin 15:40):")
        return WAITING_FOR_TIME

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_text):
        await update.message.reply_text("Hatalı format. Bunu çocuk bile becerebilir de neyse saati 15:40 formatında gir:")
        return WAITING_FOR_TIME
    context.user_data["reminder_time"] = time_text
    keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")], [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bu hatırlatıcının önem derecesi nedir?", reply_markup=reply_markup)
    return WAITING_FOR_IMPORTANCE

async def receive_importance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    importance = "high" if query.data == "imp_high" else "normal"
    reminder_text = context.user_data.get("reminder_text")
    time_text = context.user_data.get("reminder_time")
    chat_id = query.message.chat_id
    final_reminder_text = f"{reminder_text} ({time_text})"
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    hour, minute = map(int, time_text.split(":"))
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_time < now: target_time += datetime.timedelta(days=1)
    delay_seconds = (target_time - now).total_seconds()
    job_data = {"chat_id": chat_id, "text": final_reminder_text, "count": 0}
    job_id = f"rem_{chat_id}_{target_time.timestamp()}"
    if importance == "high":
        context.job_queue.run_repeating(send_high_importance_alert, interval=120, first=delay_seconds, data=job_data, name=f"high_loop_{job_id}")
    else:
        context.job_queue.run_repeating(send_normal_importance_alert, interval=300, first=delay_seconds, data=job_data, name=f"normal_loop_{job_id}")
    await query.edit_message_text(f"Hatırlatıcı kuruldu! Saat {time_text} geldiğinde bildirim alacaksın.")
    return ConversationHandler.END

async def send_high_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    if data["count"] >= 5: job.schedule_removal(); return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=f"Hatırlatma: {data['text']}", reply_markup=reply_markup)

async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    if data["count"] >= 4: job.schedule_removal(); return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=f"Hatırlatma: {data['text']}", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("read_"):
        job_name = query.data.split("read_", 1)[1]
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs: job.schedule_removal()
        await query.edit_message_text(f"Görev tamamlandı.")

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    removed_count = 0
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name and f"_{chat_id}_" in job.name:
                job.schedule_removal()
                removed_count += 1
    if removed_count > 0: await update.message.reply_text(f"İşlem iptal edildi ve sana ait aktif {removed_count} hatırlatıcı tamamen silindi.")
    else: await update.message.reply_text("İşlem iptal edildi. (Zaten aktif bir hatırlatıcın bulunmuyordu.)")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hatirlat", hatirlat_start)],
        states={
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
            WAITING_FOR_IMPORTANCE: [CallbackQueryHandler(receive_importance, pattern="^imp_")],
        },
        fallbacks=[CommandHandler("iptal", cancel_all)],
        allow_reentry=True
    )
    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))
    app.add_handler(CommandHandler("soru", soru))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))
    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
