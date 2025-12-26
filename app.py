from __future__ import annotations

import logging
from uuid import uuid4

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from config import load_config
from storage import build_storage, FileRecord
from links import make_token, parse_token
from fsub import is_user_joined_all, build_join_keyboard

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger("fsub-modern")

CFG = load_config()
STORE = build_storage(CFG.storage_backend, CFG.mongo_uri, CFG.mongo_db)

CB_DONE = "fsub_done"

def _mention_html(user) -> str:
    name = (user.first_name or "bro").replace("<", "").replace(">", "")
    return f"<a href='tg://user?id={user.id}'>{name}</a>"

def _admin_only(user_id: int) -> bool:
    return user_id in CFG.admins

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u or not update.message:
        return
    text = CFG.start_message.format(mention=_mention_html(u))
    await update.message.reply_html(text, disable_web_page_preview=True)

async def gate_or_send(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str) -> None:
    msg = update.effective_message
    u = update.effective_user
    if not msg or not u:
        return

    ok = await is_user_joined_all(context, u.id, CFG.force_sub_targets)
    if not ok:
        kb = build_join_keyboard(
            CFG.force_sub_targets,
            CFG.buttons_per_row,
            CFG.join_text,
            done_callback_data=f"{CB_DONE}:{token}"
        )
        await msg.reply_html(CFG.force_sub_message, reply_markup=kb, disable_web_page_preview=True)
        return

    file_id = parse_token(CFG.secret_key, token)
    if not file_id:
        await msg.reply_text("Token link invalid atau sudah rusak.")
        return

    rec = STORE.get(file_id)
    if not rec:
        await msg.reply_text("File tidak ditemukan / sudah dihapus dari database channel.")
        return

    # forward / copy dari channel database
    try:
        await context.bot.copy_message(
            chat_id=msg.chat_id,
            from_chat_id=rec.db_chat_id,
            message_id=rec.db_message_id,
        )
    except Exception as e:
        log.exception("copy_message failed: %s", e)
        await msg.reply_text("Gagal ambil file dari channel database. Pastikan bot admin + izin post & read.")

async def deep_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /start <payload>
    if not update.message or not update.effective_user:
        return

    args = context.args
    if not args:
        await start_cmd(update, context)
        return

    token = args[0].strip()
    await gate_or_send(update, context, token)

async def done_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.from_user:
        return
    await q.answer()

    data = (q.data or "")
    if not data.startswith(f"{CB_DONE}:"):
        return
    token = data.split(":", 1)[1].strip()

    # re-check after click
    ok = await is_user_joined_all(context, q.from_user.id, CFG.force_sub_targets)
    if not ok:
        await q.answer("Masih belum join semua ya.", show_alert=True)
        return

    # delete gate message (optional)
    try:
        await q.message.delete()
    except Exception:
        pass

    # send file
    fake_update = Update(update.update_id, message=q.message)
    await gate_or_send(fake_update, context, token)

async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    u = update.effective_user
    if not msg or not u:
        return

    # cuma admin/owner yang boleh "input" ke database
    if not _admin_only(u.id):
        return

    kind = None
    if msg.document:
        kind = "document"
    elif msg.video:
        kind = "video"
    elif msg.photo:
        kind = "photo"
    elif msg.audio:
        kind = "audio"
    elif msg.voice:
        kind = "voice"
    else:
        return

    # copy ke channel database
    try:
        copied = await context.bot.copy_message(
            chat_id=CFG.channel_id,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
    except Exception as e:
        log.exception("copy to db channel failed: %s", e)
        await msg.reply_text("Gagal simpan ke channel database. Pastikan bot admin di channel itu + izin post.")
        return

    file_id = str(uuid4())
    STORE.upsert(FileRecord(
        file_id=file_id,
        db_chat_id=CFG.channel_id,
        db_message_id=copied.message_id,
        kind=kind,
        caption=msg.caption_html if msg.caption_html else None,
    ))

    token = make_token(CFG.secret_key, file_id)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start={token}"

    await msg.reply_html(
        f"<b>Saved.</b>\n\nLink:\n<code>{link}</code>",
        disable_web_page_preview=True
    )

def main() -> None:
    app: Application = ApplicationBuilder().token(CFG.bot_token).build()

    app.add_handler(CommandHandler("start", deep_link_start))
    app.add_handler(CallbackQueryHandler(done_cb, pattern=r"^fsub_done:"))
    # save file dari admin/owner
    app.add_handler(MessageHandler(
        filters.ALL & (filters.Document.ALL | filters.VIDEO | filters.PHOTO | filters.AUDIO | filters.VOICE),
        save_file
    ))

    log.info("Bot running...")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
