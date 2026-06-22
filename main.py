import os
import re
import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from google import genai
from google.genai import types

# Çevresel Değişkenler (Railway'den çekilecek)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("Lütfen Railway Variables kısmına TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID ekleyin.")

# Kılavuz Görsel Linkleri
IMAGE_URL_1 = "https://example.com/adim1_bildirimler.jpg"
IMAGE_URL_2 = "https://example.com/adim2_ses_degisimi.jpg"

# Gemini Ayarları (Yeni SDK)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

system_instruction_text = (
    "Kullanıcının sorusunu maksimum 100 kelime olacak şekilde yanıtla. 100 kelimeden kısa olabilirse daha da kısa yanıtla. "
    "Her paragrafın en başına mutlaka uygun bir emoji koy. "
    "KESİNLİKLE hiçbir metinde '*' (yıldız) simgesini kullanma, metinleri kalın veya italik yapmaya çalışma."
)

# Konuşma Durumları (State)
WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2

async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sadece özel mesajda çalışan kullanım kılavuzu ve görsel gönderimi (/start ve /yardim için)."""
    if update.message.chat.type != "private":
        return

    guide = (
        "Merhaba! Bu bot size gruplarda sorularınızı yanıtlamak ve "
        "özel mesajlarda görevlerinizi hatırlatmak için tasarlandı.\n\n"
        "KULLANIM KILAVUZU\n\n"
        "Grup İçinde:\n"
        "/soru [metin] - Yapay zekaya kısa bir soru sorar.\n\n"
        "Özel Mesajda Hatırlatıcı Kurmak:\n"
        "İki farklı yöntemle hatırlatıcı kurabilirsiniz:\n\n"
        "1. Yöntem (Tek seferde hızlı kurulum):\n"
        "/hatirlat [hatırlatılacak şey] [saat]\n"
        "Örnek: /hatirlat toplantıya katıl 15:40\n\n"
        "2. Yöntem (Adım adım kurulum):\n"
        "/hatirlat [hatırlatılacak şey]\n"
        "Örnek: /hatirlat toplantıya katıl\n"
        "(Bunu yazdıktan sonra bot size saati soracaktır.)\n\n"
        "Not: İki yöntemin sonunda da bot size bildirimin önem derecesini soracaktır. "
        "Ankete cevap verdiğinizde hatırlatıcınız başarıyla kurulur.\n\n"
        "/yardim veya /start - Bu kılavuzu tekrar gösterir."
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
        await update.message.reply_text("Kılavuz görselleri yüklenirken bir hata oluştu, lütfen bot sahibinin linkleri güncellemesini bekleyin.")

async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sadece belirli grupta çalışan yapay zeka cevaplayıcısı."""
    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    question_text = " ".join(context.args)
    if not question_text:
        await update.message.reply_text("Lütfen bir soru girin. Örnek: /soru hava durumu nasıl?")
        return

    try:
        response = gemini_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=question_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction_text,
                temperature=0.7,
                max_output_tokens=150,
            )
        )
        clean_response = response.text.replace("*", "")
        await update.message.reply_text(clean_response)
    except Exception as e:
        print(f"Gemini Hatası: {e}")
        await update.message.reply_text("Cevap üretilirken bir hata oluştu.")

async def hatirlat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Özel mesajda hatırlatıcı başlatır ve formatı analiz eder."""
    if update.message.chat.type != "private":
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text("Lütfen hatırlatılacak metni yazın. Örnek: /hatirlat toplantıya katıl 15:40")
        return ConversationHandler.END

    possible_time = args[-1]
    
    if re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", possible_time):
        time_text = possible_time
        reminder_text = " ".join(args[:-1])
        
        if not reminder_text:
            await update.message.reply_text("Lütfen hatırlatılacak metni de girin. Örnek: /hatirlat toplantı 15:40")
            return ConversationHandler.END
            
        context.user_data["reminder_text"] = reminder_text
        context.user_data["reminder_time"] = time_text
        
        keyboard = [
            [InlineKeyboardButton("Çok Önemli", callback_data="imp_high")],
            [InlineKeyboardButton("Normal", callback_data="imp_normal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Saat {time_text} için '{reminder_text}' hatırlatıcısının önem derecesi nedir?", reply_markup=reply_markup)
        
        return WAITING_FOR_IMPORTANCE
    else:
        reminder_text = " ".join(args)
        context.user_data["reminder_text"] = reminder_text
        await update.message.reply_text("Lütfen hatırlatma saatini HH:MM formatında girin (Örneğin 15:40):")
        return WAITING_FOR_TIME

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcıdan adım adım kurulumda saati alır."""
    time_text = update.message.text.strip()
    
    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_text):
        await update.message.reply_text("Hatalı format. Lütfen saati 15:40 formatında girin:")
        return WAITING_FOR_TIME

    context.user_data["reminder_time"] = time_text

    keyboard = [
        [InlineKeyboardButton("Çok Önemli", callback_data="imp_high")],
        [InlineKeyboardButton("Normal", callback_data="imp_normal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bu hatırlatıcının önem derecesi nedir?", reply_markup=reply_markup)
    return WAITING_FOR_IMPORTANCE

async def receive_importance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anket cevabını alır ve zamanlayıcıyı kurar."""
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
    if target_time < now:
        target_time += datetime.timedelta(days=1)
        
    delay_seconds = (target_time - now).total_seconds()

    job_data = {
        "chat_id": chat_id,
        "text": final_reminder_text, 
        "importance": importance,
        "count": 0
    }
    
    context.job_queue.run_once(
        trigger_reminder, 
        delay_seconds, 
        data=job_data, 
        name=f"rem_{chat_id}_{target_time.timestamp()}"
    )

    await query.edit_message_text(f"Hatırlatıcı başarıyla kuruldu! Saat {time_text} geldiğinde bildirim alacaksınız.")
    return ConversationHandler.END

async def trigger_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    importance = data["importance"]
    
    if importance == "high":
        context.job_queue.run_repeating(
            send_high_importance_alert, 
            interval=180, 
            first=0, 
            data=data,
            name=f"high_loop_{chat_id}_{job.name}"
        )
    else:
        context.job_queue.run_repeating(
            send_normal_importance_alert, 
            interval=300, 
            first=0, 
            data=data,
            name=f"normal_loop_{chat_id}_{job.name}"
        )

async def send_high_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    
    if data["count"] >= 10:
        job.schedule_removal()
        return

    data["count"] += 1
    
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id, 
        text=f"Hatırlatma: {data['text']}", 
        reply_markup=reply_markup
    )

async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    
    if data["count"] >= 4:
        job.schedule_removal()
        return

    data["count"] += 1
    await context.bot.send_message(chat_id=chat_id, text=f"/hatirlat {data['text']}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("read_"):
        job_name = query.data.split("read_", 1)[1]
        
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            
        await query.edit_message_text(f"Hatırlatıcı tamamlandı.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İşlem iptal edildi.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hatirlat", hatirlat_start)],
        states={
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
            WAITING_FOR_IMPORTANCE: [CallbackQueryHandler(receive_importance, pattern="^imp_")],
        },
        fallbacks=[CommandHandler("iptal", cancel)]
    )

    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    
    app.add_handler(CommandHandler("soru", soru))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
