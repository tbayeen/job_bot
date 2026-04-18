"""
🤖 بوت التقديم على الوظائف — Telegram + SendGrid
=================================================
• إعداد الحساب (إيميلك + SendGrid API Key)
• إضافة مسميات وظيفية مع موضوع + رسالة + CV
• تقديم جديد: اختر المسمى ← أدخل إيميل الشركة ← يرسل تلقائياً
"""

import os, json, logging, base64
from pathlib import Path

import sendgrid
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition
)
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# ─── Logging ───────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DATA_DIR  = Path("data")
CV_DIR    = DATA_DIR / "cvs"
DATA_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(exist_ok=True)
CV_DIR.mkdir(exist_ok=True)

# ─── Conversation States ───────────────────────────────────────
(
    SETUP_EMAIL, SETUP_APIKEY,
    JP_NAME, JP_SUBJECT, JP_MESSAGE, JP_CV,
    APPLY_PICK_PROFILE, APPLY_EMAIL,
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

def get_user(u: str) -> dict:
    return load_data().get(u, {})

def set_user(u: str, user: dict):
    data = load_data()
    data[u] = user
    save_data(data)

def uid(update: Update) -> str:
    return str(update.effective_user.id)


# ══════════════════════════════════════════════════════════════
#  SendGrid Email Sender
# ══════════════════════════════════════════════════════════════
def send_email(from_email: str, api_key: str, to: str, subject: str, body: str, cv_path):
    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    message = Mail(
        from_email=from_email,
        to_emails=to,
        subject=subject,
        plain_text_content=body
    )
    if cv_path and Path(cv_path).exists():
        with open(cv_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(Path(cv_path).name),
            FileType("application/pdf"),
            Disposition("attachment")
        )
        message.attachment = attachment
    response = sg.send(message)
    if response.status_code not in (200, 202):
        raise Exception(f"SendGrid error: {response.status_code}")


# ══════════════════════════════════════════════════════════════
#  Keyboards
# ══════════════════════════════════════════════════════════════
def main_menu_kb(user: dict) -> InlineKeyboardMarkup:
    rows = []
    if not user.get("email"):
        rows.append([InlineKeyboardButton("⚙️ إعداد الحساب", callback_data="setup")])
    else:
        rows.append([InlineKeyboardButton("⚙️ تعديل الحساب", callback_data="setup")])
        rows.append([InlineKeyboardButton("➕ مسمى وظيفي جديد", callback_data="new_profile")])
        if user.get("profiles"):
            rows.append([InlineKeyboardButton("🚀 تقديم جديد", callback_data="apply")])
            rows.append([InlineKeyboardButton("📋 مسمياتي الوظيفية", callback_data="list_profiles")])
    return InlineKeyboardMarkup(rows)

def profiles_kb(profiles: dict, prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"{prefix}:{name}")] for name in profiles]
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
    if user.get("email"):
        status = f"\n📧 حسابك: `{user['email']}`"
        status += f"\n📁 مسمياتك: {len(user.get('profiles', {}))}"
    await update.message.reply_text(
        f"👋 أهلاً {name}!\nأنا بوت التقديم على الوظائف 🤖{status}\n\nاختر من القائمة:",
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
        "⚙️ *إعداد الحساب*\n\nأرسل لي *إيميلك* (اللي سيُرسل منه):",
        parse_mode="Markdown"
    )
    return SETUP_EMAIL

async def setup_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("❌ إيميل غير صحيح. أعد المحاولة:")
        return SETUP_EMAIL
    context.user_data["setup_email"] = email
    await update.message.reply_text(
        "🔑 الآن أرسل *SendGrid API Key*\n\n"
        "📌 تجده في SendGrid:\nSettings ← API Keys ← Create API Key",
        parse_mode="Markdown"
    )
    return SETUP_APIKEY

async def setup_apikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api_key = update.message.text.strip()
    await update.message.delete()
    await update.message.reply_text("⏳ جارٍ التحقق...")
    try:
        send_email(
            from_email=context.user_data["setup_email"],
            api_key=api_key,
            to=context.user_data["setup_email"],
            subject="✅ اختبار البوت",
            body="البوت يعمل بنجاح! 🎉",
            cv_path=None
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ فشل التحقق:\n`{e}`\n\nتأكد من الـ API Key وأن إيميلك مسجّل في SendGrid كـ Sender.",
            parse_mode="Markdown"
        )
        return SETUP_APIKEY

    user = get_user(uid(update))
    user["email"]   = context.user_data["setup_email"]
    user["api_key"] = api_key
    if "profiles" not in user:
        user["profiles"] = {}
    set_user(uid(update), user)

    await update.message.reply_text(
        "✅ *تم ربط الحساب بنجاح!*\n"
        f"📧 `{user['email']}`\n\n"
        "راح يوصلك إيميل اختبار ✉️",
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
        "➕ *مسمى وظيفي جديد*\n\n1️⃣ أرسل *اسم المسمى الوظيفي*\nمثال: Backend Developer",
        parse_mode="Markdown"
    )
    return JP_NAME

async def jp_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user = get_user(uid(update))
    if name in user.get("profiles", {}):
        await update.message.reply_text("⚠️ هذا الاسم موجود. أرسل اسم مختلف:")
        return JP_NAME
    context.user_data["new_profile"]["name"] = name
    await update.message.reply_text(
        f"✅ الاسم: *{name}*\n\n2️⃣ أرسل *موضوع الإيميل*\nمثال: Application for {name} Position",
        parse_mode="Markdown"
    )
    return JP_SUBJECT

async def jp_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_profile"]["subject"] = update.message.text.strip()
    await update.message.reply_text(
        "3️⃣ أرسل *نص الرسالة*\n\n"
        "💡 يمكنك استخدام:\n`{name}` ← اسمك\n`{role}` ← المسمى الوظيفي",
        parse_mode="Markdown"
    )
    return JP_MESSAGE

async def jp_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_profile"]["message"] = update.message.text.strip()
    await update.message.reply_text(
        "4️⃣ أرسل ملف *CV بصيغة PDF* 📄\n\nأو أرسل /skip بدون CV",
        parse_mode="Markdown"
    )
    return JP_CV

async def save_profile(update, context, cv_filename=None):
    profile = context.user_data["new_profile"]
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
        f"✅ *تم حفظ المسمى!*\n\n📌 {profile['name']}\n📄 CV: {'✅' if cv_filename else '❌'}",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user)
    )
    return ConversationHandler.END

async def jp_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.mime_type != "application/pdf":
        await update.message.reply_text("❌ يرجى إرسال ملف PDF فقط.")
        return JP_CV
    profile = context.user_data["new_profile"]
    file = await doc.get_file()
    cv_filename = f"{uid(update)}_{profile['name'].replace(' ', '_')}.pdf"
    await file.download_to_drive(CV_DIR / cv_filename)
    return await save_profile(update, context, cv_filename)

async def jp_cv_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await save_profile(update, context, None)


# ══════════════════════════════════════════════════════════════
#  List / Delete Profiles
# ══════════════════════════════════════════════════════════════
async def list_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(uid(update))
    profiles = user.get("profiles", {})
    if not profiles:
        await query.edit_message_text("📭 ما عندك مسميات بعد.", reply_markup=main_menu_kb(user))
        return
    lines = [f"• *{n}* | CV: {'📄' if p.get('cv') else '—'}" for n, p in profiles.items()]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🗑 حذف: {n}", callback_data=f"del:{n}")] for n in profiles
    ] + [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
    await query.edit_message_text(
        "📋 *مسمياتك:*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=kb
    )

async def delete_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.split(":", 1)[1]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم", callback_data=f"del_confirm:{name}"),
        InlineKeyboardButton("❌ لا", callback_data="list_profiles")
    ]])
    await query.edit_message_text(f"🗑 حذف *{name}*؟", parse_mode="Markdown", reply_markup=kb)

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.split(":", 1)[1]
    user = get_user(uid(update))
    p = user.get("profiles", {}).pop(name, None)
    if p and p.get("cv"):
        f = CV_DIR / p["cv"]
        if f.exists(): f.unlink()
    set_user(uid(update), user)
    await query.edit_message_text(f"✅ تم حذف *{name}*", parse_mode="Markdown", reply_markup=main_menu_kb(user))


# ══════════════════════════════════════════════════════════════
#  Apply
# ══════════════════════════════════════════════════════════════
async def apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(uid(update))
    profiles = user.get("profiles", {})
    if not profiles:
        await query.edit_message_text("❌ ما عندك مسميات. أضف واحد أولاً.", reply_markup=main_menu_kb(user))
        return ConversationHandler.END
    await query.edit_message_text(
        "🚀 *تقديم جديد*\n\nاختر المسمى:",
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
        f"✅ المسمى: *{profile_name}*\n\n📧 أرسل *إيميل الشركة أو HR*:",
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
    body = profile["message"].replace("{name}", user["email"].split("@")[0]).replace("{role}", profile_name)
    cv_path = CV_DIR / profile["cv"] if profile.get("cv") else None

    await update.message.reply_text("⏳ جارٍ الإرسال...")
    try:
        send_email(user["email"], user["api_key"], to_email, profile["subject"], body, cv_path)
        await update.message.reply_text(
            f"✅ *تم الإرسال!*\n\n📌 {profile_name}\n📧 إلى: {to_email}\n📄 CV: {'✅' if cv_path else '❌'}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل:\n`{e}`", parse_mode="Markdown", reply_markup=main_menu_kb(user))
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
    if not TELEGRAM_TOKEN:
        raise SystemExit("❌ TELEGRAM_TOKEN غير موجود")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_start, pattern="^setup$")],
        states={
            SETUP_EMAIL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_email)],
            SETUP_APIKEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_apikey)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

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

    apply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_start, pattern="^apply$")],
        states={
            APPLY_PICK_PROFILE: [CallbackQueryHandler(apply_pick_profile, pattern="^apply_pick:")],
            APPLY_EMAIL:        [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(setup_conv)
    app.add_handler(profile_conv)
    app.add_handler(apply_conv)
    app.add_handler(CallbackQueryHandler(list_profiles,  pattern="^list_profiles$"))
    app.add_handler(CallbackQueryHandler(delete_profile, pattern="^del:"))
    app.add_handler(CallbackQueryHandler(delete_confirm, pattern="^del_confirm:"))
    app.add_handler(CallbackQueryHandler(back_main,      pattern="^back_main$"))

    log.info("🤖 البوت شغّال...")
    app.run_polling()


if __name__ == "__main__":
    main()
