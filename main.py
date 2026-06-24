import os
import re
import datetime
import pytz
import asyncio
import json
import io
import matplotlib
matplotlib.use('Agg') # Sunucuda hata vermeden arka planda grafik çizmek için
import matplotlib.pyplot as plt

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

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2
STATS_FILE = "stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f)

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
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_1, caption="BİLDİRİM SESLERİNİ DEĞİŞTİRME\nAdım 1: Bildirim Menüsü")
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_2, caption="Adım 2: Özel Ses Seçimi")
    except Exception as e:
        await update.message.reply_text("Kılavuzu yükleyemedim tüh.")

async def copy_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Belirli kanaldan gelen mesajları diğer gruba kopyalar."""
    try:
        await context.bot.copy_message(
            chat_id="-5199865415",
            from_chat_id=update.channel_post.chat_id,
            message_id=update.channel_post.message_id
        )
    except Exception as e:
        print(f"Kanal mesajı kopyalama hatası: {e}")

async def score_bot_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message Score Bot'un mesajını okuyup grafikli rapor gönderir."""
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    
    # Sadece 00:00 ile 00:25 arasında çalışsın
    if not (now.hour == 0 and 0 <= now.minute <= 25):
        return

    text = update.message.text or update.message.caption
    if not text:
        return

    # İstatistikleri Gemini'ye çektiriyoruz
    extract_prompt = f"Aşağıdaki mesaj istatistiği metninden 'toplam mesaj sayısını' ve 'kullanıcı (çeşitliliği) sayısını' bul. Sadece şu formatta geçerli bir JSON döndür: {{\"msg_count\": 100, \"user_count\": 10}}. Metin: {text}"
    
    try:
        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=extract_prompt
        )
        json_str = response.text.strip().strip('`').replace('json\n', '')
        data = json.loads(json_str)
        msg_count = data.get("msg_count", 0)
        user_count = data.get("user_count", 0)
    except Exception as e:
        print(f"Veri çekilemedi: {e}")
        return

    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    last_week_str = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    stats = load_stats()
    stats[today_str] = {"msg_count": msg_count, "user_count": user_count}
    save_stats(stats)

    labels = ['Geçen Hafta', 'Dün', 'Bugün']
    m_counts = [stats.get(last_week_str, {}).get("msg_count", 0), stats.get(yesterday_str, {}).get("msg_count", 0), msg_count]
    u_counts = [stats.get(last_week_str, {}).get("user_count", 0), stats.get(yesterday_str, {}).get("user_count", 0), user_count]

    # Grafiği Çiziyoruz
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(labels))
    width = 0.35

    ax.bar([i - width/2 for i in x], m_counts, width, label='Mesaj Sayısı', color='#4A90E2')
    ax.bar([i + width/2 for i in x], u_counts, width, label='Kişi Sayısı', color='#F5A623')

    ax.set_ylabel('Adet')
    ax.set_title('Grup Günlük Aktiflik Kıyaslaması')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    # Raporlama için yapay zekaya gönder
    report_prompt = (
        f"Bugün grupta {msg_count} mesaj atıldı ve {user_count} kişi konuştu. Dün {m_counts[1]} mesaj, {u_counts[1]} kişi vardı. "
        f"Geçen hafta ise {m_counts[0]} mesaj, {u_counts[0]} kişi vardı. Bu verileri kıyaslayarak gruba özel, samimi, "
        f"ansiklopedik olmayan en fazla 100 kelimelik motive edici veya tatlı tatlı sitem eden bir günlük özet raporu yaz."
    )
    try:
        report_response = await gemini_client.aio.models.generate_content(model=GEMINI_MODEL, contents=report_prompt)
        report_text = report_response.text
    except:
        report_text = "Bugünkü günlük grubumuzun raporu ektedir!"

    try:
        await context.bot.send_photo(
            chat_id="-5199865415",
            photo=buf,
            caption=report_text
        )
    except Exception as e:
        print(f"Rapor gönderilirken hata oluştu: {e}")


async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        print(f"Gelen Grup ID: {update.message.chat.id} | Beklenen ID: {ALLOWED_GROUP_ID}")

    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    # Soru metni belirleme (Doğrudan mesaj veya caption)
    text = update.message.text or update.message.caption or ""
    question_text = re.sub(r'^/soru\s*', '', text, flags=re.IGNORECASE).strip()

    # Eğer metin yoksa alıntılanan mesajdaki metne bak
    if not question_text and update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        question_text = reply_text.strip()

    # Görsel kontrolü (Mesajın kendisinde veya alıntılanan mesajda)
    photo_obj = None
    if update.message.photo:
        photo_obj = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo_obj = update.message.reply_to_message.photo[-1]

    image_data = None
    if photo_obj:
        file = await context.bot.get_file(photo_obj.file_id)
        image_bytes = await file.download_as_bytearray()
        image_data = types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')

    if not question_text and not image_data:
        await update.message.reply_photo(
            photo=SORU_IMAGE_URL,
            caption="Bir soru girsene bu ne böyle şimdi? Örnek: /soru hava durumu nasıl?"
        )
        return

    # Dinamik Samimi Üslup Ayarı
    user_id = str(update.message.from_user.id)
    dynamic_instruction = (
        "Kullanıcının sorusunu maksimum 100 kelime olacak şekilde yanıtla. "
        "Yanıtın en az 5 kelimeden oluşmalı. "
        "Her paragrafın en başına mutlaka uygun bir emoji koy. "
        "Genel olarak ansiklopedik, kaba veya robotik konuşma, samimi ve günlük bir dil kullan. "
        "Uzun cevaplarda paragrafa ayırabilirsin. "
    )

    if user_id == "8639720888":
        dynamic_instruction += "Lütfen kullanıcıya 'ablam' diye hitap et. Çok saygılı, kız kardeşi gibi sıcak, ablamlı bir dil kullan. "
    elif question_text.endswith("?"):
        dynamic_instruction += "Lütfen kullanıcıya 'güzelim' diye hitap et. Çok samimi, sıcak, sevimli ve flörtöz olmayan tatlı bir üslup kullan. "

    status_msg = await update.message.reply_text("☕ Gizem zihnini açmak için kahvesini yudumluyor...")
    
    async def loading_animation():
        frames = ["📖 Gizem cevabı düşünüyor...", "✍️ Gizem soruya cevap yazıyor..."]
        try:
            for frame in frames:
                await asyncio.sleep(3)
                await status_msg.edit_text(frame)
        except: pass
            
    animation_task = asyncio.create_task(loading_animation())

    try:
        contents = [question_text] if question_text else []
        if image_data: contents.append(image_data)

        # BURASI GÜNCELLENDİ: max_output_tokens 150'den 800'e çıkarıldı.
        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=dynamic_instruction,
                temperature=0.7,
                max_output_tokens=800, 
            )
        )
        
        animation_task.cancel()
        try: await status_msg.delete()
        except: pass

        if response and response.text:
            clean_response = response.text
            if len(clean_response) <= 1024:
                await update.message.reply_photo(photo=SORU_IMAGE_URL, caption=clean_response)
            else:
                await update.message.reply_photo(photo=SORU_IMAGE_URL)
                await update.message.reply_text(clean_response)
        else:
            await update.message.reply_text("Bu saçma soruyu cevaplayamam.")
            
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
        await update.message.reply_text("Şu anda aktif 3 adet hatırlatıcın bulunuyor. Daha fazla ekleyebilmek için mevcut olanlardan birinin tamamlanmasını bekl veya /iptal komutu ile hepsini silebilirsin.")
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
    
    # Kanal dinleyicisi (Otomatik mesaj kopyalama)
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003613910089) & filters.UpdateType.CHANNEL_POST, copy_channel_post))
    
    # Message Score Bot Dinleyicisi
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003297262036) & filters.User(user_id=5933486341), score_bot_listener))

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))
    
    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
