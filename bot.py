"""
🤖 بوت التقديم على الوظائف — Telegram
=======================================
• إعداد الحساب (إيميل + كلمة مرور التطبيقات)
• إضافة مسميات وظيفية مع موضوع + رسالة + CV
• تقديم جديد: اختر المسمى ← أدخل إيميل الشركة ← يرسل تلقائياً
"""

import os, json, smtplib, logging
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# ─── Logging ───────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
DATA_DIR  = Path("data")
CV_DIR    = DATA_DIR / "cvs"
DATA_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(exist_ok=True)
CV_DIR.mkdir(exist_ok=True)

# ─── Conversation States ───────────────────────────────────────
(
    # Setup
    SETUP_EMAIL, SETUP_PASSWORD,
    # New Job Profile
    JP_NAME, JP_SUBJECT, JP_MESSAGE, JP_CV,
    # Apply
    APPLY_PICK_PROFILE, APPLY_EMAIL,
    # Delete profile confirm
    DEL_CONFIRM,
) = range(9)


# ══════════════════════════════════════════════════════════════
#  Data Helpers
# ══════════════════════════════════════════════════════════════
def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_user(uid: str) -> dict:
    data = load_data()
    return data.get(uid, {})

def set_user(uid: str, user: dict):
    data = load_data()
    data[uid] = user
    save_data(data)

def uid(update: Update) -> str:
    return str(update.effective_user.id)


# ══════════════════════════════════════════════════════════════
#  Email Sender (Gmail App Password)
# ══════════════════════════════════════════════════════════════
def send_email(gmail: str, app_password: str, to: str, subject: str, body: str, cv_path: Path | None):
    msg = MIMEMultipart()
    msg["From"]    = gmail
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if cv_path and cv_path.exists():
        with open(cv_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=cv_path.name)
            msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail, app_password)
        server.sendmail(gmail, to, msg.as_string())


# ══════════════════════════════════════════════════════════════
#  Keyboards
# ══════════════════════════════════════════════════════════════
def main_menu_kb(user: dict) -> InlineKeyboardMarkup:
    rows = []
    if not user.get("gmail"):
        rows.append([InlineKeyboardButton("⚙️ إعداد الحساب", callback_data="setup")])
    else:
        rows.append([InlineKeyboardButton("⚙️ تعديل الحساب", callback_data="setup")])
        rows.append([InlineKeyboardButton("➕ مسمى وظيفي جديد", callback_data="new_profile")])
        if user.get("profiles"):
            rows.append([InlineKeyboardButton("🚀 تقديم جديد", callback_data="apply")])
            rows.append([InlineKeyboardButton("📋 مسمياتي الوظيفية", callback_data="list_profiles")])
    return InlineKeyboardMarkup(rows)

def profiles_kb(profiles: dict, prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"{prefix}:{name}")]
            for name in profiles]
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = get_user(uid(update))
    name = update.effective_user.first_name

    status = ""
    if user.get("gmail"):
        status = f"\n📧 حسابك: `{user['gmail']}`"
        profiles = user.get("profiles", {})
        status += f"\n📁 مسمياتك: {len(profiles)}"

    await update.message.reply_text(
        f"👋 أهلاً {name}!\n"
        f"أنا بوت التقديم على الوظائف 🤖{status}\n\n"
        "اختر من القائمة:",
        reply_markup=main_menu_kb(user),
        parse_mode="Markdown"
    )

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(uid(update))
    await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=main_menu_kb(user))
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  Setup Account
# ══════════════════════════════════════════════════════════════
async def setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚙️ *إعداد الحساب*\n\n"
        "أرسل لي *إيميل Gmail* الخاص بك:",
        parse_mode="Markdown"
    )
    return SETUP_EMAIL

async def setup_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if "@gmail.com" not in email:
        await update.message.reply_text("❌ يجب أن يكون إيميل Gmail. أعد المحاولة:")
        return SETUP_EMAIL
    context.user_data["setup_email"] = email
    await update.message.reply_text(
        "🔑 الآن أرسل *كلمة مرور التطبيقات* (App Password)\n\n"
        "📌 كيف تحصل عليها؟\n"
        "1. روح على myaccount.google.com\n"
        "2. الأمان ← التحقق بخطوتين (فعّله أولاً)\n"
        "3. كلمات مرور التطبيقات ← أنشئ واحدة\n"
        "4. انسخها هنا (16 حرف بدون مسافات)",
        parse_mode="Markdown"
    )
    return SETUP_PASSWORD

async def setup_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip().replace(" ", "")
    await update.message.delete()  # نحذف الرسالة فوراً لحماية الباسورد

    if len(password) != 16:
        await update.message.reply_text("❌ كلمة المرور يجب أن تكون 16 حرف. أعد المحاولة:")
        return SETUP_PASSWORD

    # نختبر الاتصال
    await update.message.reply_text("⏳ جارٍ التحقق...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(context.user_data["setup_email"], password)
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الاتصال: {e}\nتأكد من الإيميل وكلمة المرور.")
        return SETUP_PASSWORD

    user = get_user(uid(update))
    user["gmail"]    = context.user_data["setup_email"]
    user["password"] = password
    if "profiles" not in user:
        user["profiles"] = {}
    set_user(uid(update), user)

    await update.message.reply_text(
        "✅ تم ربط الحساب بنجاح!\n"
        f"📧 `{user['gmail']}`",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user)
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  New Job Profile
# ══════════════════════════════════════════════════════════════
async def new_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_profile"] = {}
    await query.edit_message_text(
        "➕ *مسمى وظيفي جديد*\n\n"
        "1️⃣ أرسل *اسم المسمى الوظيفي*\n"
        "مثال: Backend Developer، مصمم جرافيك",
        parse_mode="Markdown"
    )
    return JP_NAME

async def jp_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user = get_user(uid(update))
    if name in user.get("profiles", {}):
        await update.message.reply_text("⚠️ هذا الاسم موجود مسبقاً. أرسل اسم مختلف:")
        return JP_NAME
    context.user_data["new_profile"]["name"] = name
    await update.message.reply_text(
        f"✅ الاسم: *{name}*\n\n"
        "2️⃣ أرسل *موضوع الإيميل (Subject)*\n"
        "مثال: Application for Backend Developer Position",
        parse_mode="Markdown"
    )
    return JP_SUBJECT

async def jp_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_profile"]["subject"] = update.message.text.strip()
    await update.message.reply_text(
        "3️⃣ أرسل *نص الرسالة (Body)*\n\n"
        "💡 يمكنك استخدام:\n"
        "`{name}` ← اسمك\n"
        "`{role}` ← المسمى الوظيفي\n\n"
        "مثال:\nDear Hiring Manager,\nI'm {name} applying for the {role} position...",
        parse_mode="Markdown"
    )
    return JP_MESSAGE

async def jp_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_profile"]["message"] = update.message.text.strip()
    await update.message.reply_text(
        "4️⃣ أرسل ملف *CV بصيغة PDF* 📄\n\n"
        "أو أرسل /skip إذا ما تريد إرفاق CV لهذا المسمى",
        parse_mode="Markdown"
    )
    return JP_CV

async def jp_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = context.user_data["new_profile"]
    cv_filename = None

    if update.message.document:
        doc = update.message.document
        if doc.mime_type != "application/pdf":
            await update.message.reply_text("❌ يرجى إرسال ملف PDF فقط.")
            return JP_CV
        file = await doc.get_file()
        cv_filename = f"{uid(update)}_{profile['name'].replace(' ', '_')}.pdf"
        await file.download_to_drive(CV_DIR / cv_filename)

    # حفظ البروفايل
    user = get_user(uid(update))
    if "profiles" not in user:
        user["profiles"] = {}
    user["profiles"][profile["name"]] = {
        "subject": profile["subject"],
        "message": profile["message"],
        "cv":      cv_filename,
    }
    set_user(uid(update), user)

    await update.message.reply_text(
        f"✅ *تم حفظ المسمى الوظيفي!*\n\n"
        f"📌 الاسم: {profile['name']}\n"
        f"📧 الموضوع: {profile['subject']}\n"
        f"📄 CV: {'✅ مرفق' if cv_filename else '❌ بدون CV'}\n\n"
        "القائمة الرئيسية:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user)
    )
    return ConversationHandler.END

async def jp_cv_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # نفس منطق jp_cv بدون ملف
    profile = context.user_data["new_profile"]
    user = get_user(uid(update))
    if "profiles" not in user:
        user["profiles"] = {}
    user["profiles"][profile["name"]] = {
        "subject": profile["subject"],
        "message": profile["message"],
        "cv":      None,
    }
    set_user(uid(update), user)

    await update.message.reply_text(
        f"✅ *تم حفظ المسمى الوظيفي بدون CV*\n\n"
        f"📌 {profile['name']}\n\n"
        "القائمة الرئيسية:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user)
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  List / Delete Profiles
# ══════════════════════════════════════════════════════════════
async def list_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(uid(update))
    profiles = user.get("profiles", {})

    if not profiles:
        await query.edit_message_text("📭 ما عندك مسميات وظيفية بعد.", reply_markup=main_menu_kb(user))
        return

    lines = []
    for name, p in profiles.items():
        cv_icon = "📄" if p.get("cv") else "—"
        lines.append(f"• *{name}* | موضوع: {p['subject'][:30]} | CV: {cv_icon}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🗑 حذف: {n}", callback_data=f"del:{n}")]
        for n in profiles
    ] + [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

    await query.edit_message_text(
        "📋 *مسمياتك الوظيفية:*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=kb
    )

async def delete_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_name = query.data.split(":", 1)[1]
    context.user_data["del_profile"] = profile_name

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"del_confirm:{profile_name}"),
         InlineKeyboardButton("❌ لا", callback_data="list_profiles")]
    ])
    await query.edit_message_text(
        f"🗑 هل تريد حذف *{profile_name}*؟",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_name = query.data.split(":", 1)[1]
    user = get_user(uid(update))

    p = user.get("profiles", {}).pop(profile_name, None)
    if p and p.get("cv"):
        cv_file = CV_DIR / p["cv"]
        if cv_file.exists():
            cv_file.unlink()

    set_user(uid(update), user)
    await query.edit_message_text(
        f"✅ تم حذف *{profile_name}*",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user)
    )


# ══════════════════════════════════════════════════════════════
#  Apply — تقديم جديد
# ══════════════════════════════════════════════════════════════
async def apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(uid(update))
    profiles = user.get("profiles", {})

    if not profiles:
        await query.edit_message_text("❌ ما عندك مسميات وظيفية. أضف واحد أولاً.", reply_markup=main_menu_kb(user))
        return ConversationHandler.END

    await query.edit_message_text(
        "🚀 *تقديم جديد*\n\nاختر المسمى الوظيفي:",
        parse_mode="Markdown",
        reply_markup=profiles_kb(profiles, "apply_pick")
    )
    return APPLY_PICK_PROFILE

async def apply_pick_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_name = query.data.split(":", 1)[1]
    context.user_data["apply_profile"] = profile_name

    await query.edit_message_text(
        f"✅ المسمى: *{profile_name}*\n\n"
        "📧 الآن أرسل *إيميل الشركة أو HR*:",
        parse_mode="Markdown"
    )
    return APPLY_EMAIL

async def apply_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    to_email = update.message.text.strip()
    if "@" not in to_email or "." not in to_email:
        await update.message.reply_text("❌ إيميل غير صحيح. أعد الإرسال:")
        return APPLY_EMAIL

    user = get_user(uid(update))
    profile_name = context.user_data["apply_profile"]
    profile = user["profiles"][profile_name]

    # تخصيص الرسالة
    body = profile["message"].replace("{name}", user.get("gmail", "").split("@")[0])
    body = body.replace("{role}", profile_name)

    cv_path = CV_DIR / profile["cv"] if profile.get("cv") else None

    await update.message.reply_text("⏳ جارٍ الإرسال...")
    try:
        send_email(
            gmail=user["gmail"],
            app_password=user["password"],
            to=to_email,
            subject=profile["subject"],
            body=body,
            cv_path=cv_path
        )
        await update.message.reply_text(
            f"✅ *تم الإرسال بنجاح!*\n\n"
            f"📌 المسمى: {profile_name}\n"
            f"📧 إلى: {to_email}\n"
            f"📄 CV: {'مرفق ✅' if cv_path else 'بدون CV'}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user)
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ فشل الإرسال:\n`{e}`\n\nتحقق من إعدادات حسابك.",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user)
        )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  Cancel
# ══════════════════════════════════════════════════════════════
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(uid(update))
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=main_menu_kb(user))
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════
def main():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_TOKEN_HERE":
        raise SystemExit("❌ TELEGRAM_TOKEN غير موجود في البيئة")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ── Setup conversation ──
    setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_start, pattern="^setup$")],
        states={
            SETUP_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_email)],
            SETUP_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ── New Profile conversation ──
    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_profile_start, pattern="^new_profile$")],
        states={
            JP_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, jp_name)],
            JP_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, jp_subject)],
            JP_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, jp_message)],
            JP_CV: [
                MessageHandler(filters.Document.PDF, jp_cv),
                CommandHandler("skip", jp_cv_skip),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ── Apply conversation ──
    apply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_start, pattern="^apply$")],
        states={
            APPLY_PICK_PROFILE: [CallbackQueryHandler(apply_pick_profile, pattern="^apply_pick:")],
            APPLY_EMAIL:        [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ── Handlers ──
    app.add_handler(CommandHandler("start", start))
    app.add_handler(setup_conv)
    app.add_handler(profile_conv)
    app.add_handler(apply_conv)
    app.add_handler(CallbackQueryHandler(list_profiles,   pattern="^list_profiles$"))
    app.add_handler(CallbackQueryHandler(delete_profile,  pattern="^del:"))
    app.add_handler(CallbackQueryHandler(delete_confirm,  pattern="^del_confirm:"))
    app.add_handler(CallbackQueryHandler(back_main,       pattern="^back_main$"))

    log.info("🤖 البوت شغّال...")
    app.run_polling()


if __name__ == "__main__":
    main()
