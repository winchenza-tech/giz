import os
import re
import datetime
import pytz
import asyncio
import json
import random
from collections import OrderedDict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
    PollAnswerHandler, MessageReactionHandler
)
from google import genai
from google.genai import types

# ==================== ENV & AYARLAR ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")
if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("Lütfen Railway Variables kısmına TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID ekleyin.")

IMAGE_URL_1 = "https://i.ibb.co/S4yWQrHg/MG-0345.jpg"
IMAGE_URL_2 = "https://i.ibb.co/Y748qgsP/MG-0346.jpg"
SORU_IMAGE_URL = "https://i.ibb.co/5Xcrbv87/MG-0398.jpg"
RULE_IMAGE_URL = "https://i.ibb.co/r2s2dYhb/MG-0987.png"

GEMINI_MODEL = "gemini-2.5-flash"
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2

ALLOWED_DUYURU_USERS = ["6781642262", "8639720888", "7094870780", "8150494686", "8242824985"]
ALLOWED_KONTROL_USERS = ALLOWED_DUYURU_USERS
DUYURU_GROUP_ID = "-1003297262036"
KONTROL_BILDIRIM_GROUP_ID = 6781642262

RULES = [
    """📌Kişisel verilerin ifşası uyarılmaksızın ban sebebi dir.
“İnsanın mahremiyeti, özgürlüğünün temelidir.” — John Stuart Mill""",
    """📌Şahısa küfür yasaktır. Onun haricinde küfür serbesttir. Karşılıklı atışmalarda küfür kullanımında her iki taraf da uyarılacaktır.
“Kaba söz, zayıf düşüncenin sesidir.” — Arthur Schopenhauer""",
    """📌Tartışma yaşadığınız kişiye sizinle muhatap olmamasını söyledikten sonra chatte ya da seste laf atması ve herhangi bir gönderinizi yanıtlaması ve mesajınıza emoji bırakması yasaktır. İhlali durumunda şikayet gerekmeksizin kuralı ihlal eden kişi yönetici olsa dahi uyarı yapılır.
“Sessizlik, tartışmayı bitirmenin en zarif yoludur.” — Friedrich Nietzsche""",
    """📌Gruba yeni katılan üyelerle henüz gerekli samimiyet oluşmadan; isimleri, kullanıcı adları (nick), profil fotoğrafları veya yaşları gibi kişisel unsurlar üzerinden mizah yapılması, rapor edilmesine gerek duyulmaksızın doğrudan uyarı sebebi dir. Bu kural yöneticiler dahil tüm üyeler için istisnasız geçerlidir.
"Yabancıya karşı saygı, kişinin kendi evine duyduğu saygının bir aynasıdır." — Stefan Zweig""",
    """📌Yöneticilere bildirmek istediğiniz bir mesajı alıntılayarak /Report ya da @admin komutunu yazabilirsiniz. Gereksiz kullananlar uyarılacaktır.
“Sessizlik kötülüğün en sadık müttefikidir” — Paulo Freire""",
    """📌İftira, milli ve kutsal değerlere hakaret yasaktır. Sohbet akışını bozacak şekilde kişisel tartışmaları devam ettirmek yasaktır.
“İftira, ahlaksızlığın en sinsi biçimidir.” — Jean-Jacques Rousseau""",
    """📌Herhangi bir terör örgütünü, illegal oluşumu vs. övmek uyarılmaksızın ban sebebi dir.
“Şiddeti savunan, aklı terk etmiştir.” — Albert Camus""",
    """📌Pornografik ve ileri şiddet içeren görsel içerikler kesinlikle yasaktır.
“İnsanı bozan şey özgürlük değil, ölçüsüzlüktür.” — Montesquieu""",
    """📌Çıkmadan önce geçerli bir neden belirtmeksizin gruptan ayrılan üyeler 15 günden önce gruba tekrar dahil olamazlar.
“Zevk, tekrarlandıkça değil, tazeyken değerlidir; geciken tat damakta kalmaz.” — Montaigne""",
    """📌Grup üyesi olmayan yanınızdaki arkadaşlarınızın grup seslisindeki sohbete katılması yasaktır.
“Misafirlik davetle olur.” — Türk atasözü""",
    """📌Başka grubun reklamını yapmak ve reklam olabilecek şekilde başka grupla ilgili konuşmak ban sebebi dir.
“Her topluluk, saygı ve sınır bilinciyle ayakta kalır.” — Alexis de Tocqueville""",
]

RULES_SENT_FILE = "rules_sent.json"
KONTROL_FILE = "kontrol_listesi.json"

RECENT_MESSAGE_AUTHORS = OrderedDict()
MAX_CACHE_SIZE = 1500


def update_message_cache(message):
    if message and message.from_user:
        RECENT_MESSAGE_AUTHORS[message.message_id] = message.from_user.id
        if len(RECENT_MESSAGE_AUTHORS) > MAX_CACHE_SIZE:
            RECENT_MESSAGE_AUTHORS.popitem(last=False)


# ==================== CACHE FONKSİYONU (EKSİK OLAN) ====================
async def cache_message_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        update_message_cache(update.message)
    if update.edited_message:
        update_message_cache(update.edited_message)


def load_rules_sent():
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    if os.path.exists(RULES_SENT_FILE):
        try:
            with open(RULES_SENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today_str:
                return set(data.get("sent", []))
        except Exception as e:
            print(f"Rules sent dosyası okunamadı: {e}")
    return set()


def save_rules_sent(sent_indices):
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    data = {"date": today_str, "sent": list(sent_indices)}
    try:
        with open(RULES_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Rules sent dosyası kaydedilemedi: {e}")


def load_kontrol_listesi():
    if os.path.exists(KONTROL_FILE):
        try:
            with open(KONTROL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"pairs": [], "next_pair_id": 1}


def save_kontrol_listesi(data):
    try:
        with open(KONTROL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Kontrol listesi kaydedilemedi: {e}")


async def post_random_rule(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    if not (now.hour >= 8 or now.hour < 1):
        return
    sent = load_rules_sent()
    available = [i for i in range(len(RULES)) if i not in sent]
    if not available:
        return
    idx = random.choice(available)
    rule_text = RULES[idx]
    sent.add(idx)
    save_rules_sent(sent)
    try:
        await context.bot.send_photo(chat_id=ALLOWED_GROUP_ID, photo=RULE_IMAGE_URL, caption=rule_text)
    except Exception as e:
        print(f"Kural gönderme hatası: {e}")


# ==================== İLETİŞİM KONTROL SİSTEMİ ====================
async def kontrolet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.message.chat.type
    if chat_type not in ["private", "group", "supergroup"]:
        return
    if chat_type != "private" and str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return

    text = update.message.text or ""
    mentioned = []
    for entity in (update.message.entities or []):
        if entity.type == "text_mention":
            u = entity.user
            mentioned.append({"id": u.id, "name": u.first_name or u.username or str(u.id), "username": u.username})
        elif entity.type == "mention":
            username_part = text[entity.offset:entity.offset + entity.length].lstrip("@")
            mentioned.append({"id": None, "name": username_part, "username": username_part})

    if len(mentioned) < 2:
        await update.message.reply_text("İki üyeyi etiketle işte. Örnek: /kontrolet @Tayyip @Özgür")
        return

    u1, u2 = mentioned[0], mentioned[1]
    data = load_kontrol_listesi()
    new_pair = {"pair_id": data["next_pair_id"], "user1": u1, "user2": u2}
    data["pairs"].append(new_pair)
    data["next_pair_id"] += 1
    save_kontrol_listesi(data)
    await update.message.reply_text(f"✅ İletişim yasağı eklendi! #{new_pair['pair_id']}")


async def kontrolliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    data = load_kontrol_listesi()
    if not data.get("pairs"):
        await update.message.reply_text("İletişim kontrol listesi boş.")
        return
    lines = [f"{p['pair_id']}- {p['user1']['name']} ve {p['user2']['name']}" for p in data["pairs"]]
    await update.message.reply_text("📋 Muhatap olmayanlar Listesi:\n\n" + "\n".join(lines), parse_mode="Markdown")


async def kontrolsil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Kullanım: /kontrolsil 2")
        return
    pid = int(context.args[0])
    data = load_kontrol_listesi()
    data["pairs"] = [p for p in data["pairs"] if p["pair_id"] != pid]
    save_kontrol_listesi(data)
    await update.message.reply_text(f"✅ #{pid} silindi.")


def get_user_mention(user):
    return f"@{user.username}" if user.username else (user.first_name or "Kullanıcı")


async def kontrol_ihlal_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat.id) != ALLOWED_GROUP_ID or not update.message.reply_to_message:
        return
    sender = update.message.from_user
    replied = update.message.reply_to_message.from_user
    if not sender or not replied:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue
        if (sender.id == u1_id and replied.id == u2_id) or (sender.id == u2_id and replied.id == u1_id):
            mention = get_user_mention(sender)
            warn_text = f"/warn {mention} Hoop iletişim yasağı ihlali (Reply)"
            try:
                await update.message.reply_text(warn_text)
            except:
                await context.bot.send_message(chat_id=update.message.chat_id, text=warn_text)
            await send_kontrol_bildirim(context, "Reply", warn_text, update.message.chat_id)
            break


async def kontrol_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction or str(reaction.chat.id) != ALLOWED_GROUP_ID or not reaction.new_reaction:
        return
    reactor = reaction.user
    if not reactor:
        return
    original_author_id = RECENT_MESSAGE_AUTHORS.get(reaction.message_id)
    if not original_author_id:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue
        if (reactor.id == u1_id and original_author_id == u2_id) or (reactor.id == u2_id and original_author_id == u1_id):
            mention = get_user_mention(reactor)
            warn_text = f"/warn {mention} Hooop iletişim yasağı ihlali (Emoji Tepki)"
            try:
                await context.bot.send_message(
                    chat_id=reaction.chat.id,
                    text=warn_text,
                    reply_to_message_id=reaction.message_id
                )
            except:
                await context.bot.send_message(chat_id=reaction.chat.id, text=warn_text)
            await send_kontrol_bildirim(context, "Emoji Tepki", warn_text, reaction.chat.id)
            break


async def send_kontrol_bildirim(context, ihlal_tipi, warn_text, chat_id):
    try:
        await context.bot.send_message(
            chat_id=KONTROL_BILDIRIM_GROUP_ID,
            text=f"🚨 Bunlar duramadı :D İletişim Yasağı İhlali ({ihlal_tipi})\n\n{warn_text}\n\nGrup: {chat_id}"
        )
    except Exception as e:
        print(f"Yönetim grubuna bildirim hatası: {e}")


# ==================== DİĞER FONKSİYONLAR ====================
async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    guide = (
        "Es Justo Grup İçinde:\n"
        "/soru [metin] - Yapay zekaya kısa bir soru sorar.\n\n"
        "Özel Mesajda Hatırlatıcı Kurmak:\n"
        "/hatirlat [hatırlatılacak şey] [saat]\n"
        "Örnek: /hatirlat toplantıya katıl 15:40\n\n"
        "Özel Mesajda Duyuru:\n"
        "/duyuru [metin] - Gruba duyuru gönderir ve sabitler.\n\n"
        "/yardim veya /start - Bu kılavuzu tekrar gösterir.\n\n"
        "Bu botun bildirim sesini normal mesaj bildirim sesinden farklı yapmanız önerilir."
    )
    await update.message.reply_text(guide)
    try:
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_1, caption="BİLDİRİM SESLERİNİ DEĞİŞTİRME\nAdım 1: Bildirim Menüsü")
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_2, caption="Adım 2: Özel Ses Seçimi")
    except:
        await update.message.reply_text("Kılavuzu yükleyemedim tüh.")


async def copy_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.copy_message(chat_id="-5199865415", from_chat_id=update.channel_post.chat_id, message_id=update.channel_post.message_id)
    except Exception as e:
        print(f"Kanal kopyalama hatası: {e}")


async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return
    # ... (senin mevcut soru fonksiyonun aynen kalsın)
    pass


async def duyuru_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (senin mevcut duyuru fonksiyonun aynen kalsın)
    pass


async def duyuru_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (senin mevcut fonksiyonun aynen kalsın)
    pass


# Hatırlatıcı fonksiyonları da senin kodundaki gibi kalsın
async def hatirlat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (senin kodun)
    pass


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


async def receive_importance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


async def send_high_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    pass


async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    pass


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


async def anti_spam_octopus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (senin kodun)
    pass


# ==================== ANA FONKSİYON ====================
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

    # Cache handler (emoji reaction için)
    app.add_handler(
        MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)), cache_message_author),
        group=-2
    )

    app.add_handler(MessageHandler(filters.ALL, anti_spam_octopus), group=-1)

    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))
    app.add_handler(MessageHandler(filters.Regex(r'(?i)^/soru'), soru))
    app.add_handler(CommandHandler("duyuru", duyuru_start))
    app.add_handler(PollAnswerHandler(duyuru_poll_answer))
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003613910089) & filters.UpdateType.CHANNEL_POST, copy_channel_post))

    app.add_handler(CommandHandler("kontrolet", kontrolet))
    app.add_handler(CommandHandler("kontrolliste", kontrolliste))
    app.add_handler(CommandHandler("kontrolsil", kontrolsil))

    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY, kontrol_ihlal_kontrol))
    app.add_handler(MessageReactionHandler(kontrol_reaction))

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    if app.job_queue:
        app.job_queue.run_repeating(post_random_rule, interval=155 * 60, first=60, name="random_rule_poster")

    print("Bot başlatılıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
