from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


def _split_target(raw: str) -> tuple[str, str]:
    """
    Accept:
      - "@public" -> (check_chat="@public", join_url="https://t.me/public")
      - "-100id|https://t.me/+invite" -> (check_chat="-100id", join_url="https://t.me/+invite")
      - "-100id" -> (check_chat="-100id", join_url="https://t.me/")  # not recommended
      - "https://t.me/+invite" -> (check_chat="https://t.me/+invite", join_url="https://t.me/+invite") # check will fail
    """
    s = str(raw).strip()
    if "|" in s:
        a, b = s.split("|", 1)
        return a.strip(), b.strip()

    if s.startswith("@"):
        return s, f"https://t.me/{s.lstrip('@')}"

    if s.startswith("https://t.me/") or s.startswith("http://t.me/"):
        return s, s  # join ok, but check_chat is invalid -> will fail member check

    return s, "https://t.me/"


async def is_user_joined_all(context: ContextTypes.DEFAULT_TYPE, user_id: int, targets: list[str]) -> bool:
    if not targets:
        return True

    for raw in targets:
        check_chat, _join_url = _split_target(raw)

        try:
            member = await context.bot.get_chat_member(chat_id=check_chat, user_id=user_id)
            status = getattr(member, "status", None)
            if status in ("left", "kicked"):
                return False
        except Exception:
            # kalau check_chat itu invite link / bot tidak punya akses -> dianggap belum join
            return False

    return True


def build_join_keyboard(
    targets: list[str],
    buttons_per_row: int,
    join_text: str,
    done_callback_data: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []

    for idx, raw in enumerate(targets, start=1):
        _check_chat, join_url = _split_target(raw)

        buf.append(InlineKeyboardButton(f"{join_text} {idx}", url=join_url))
        if len(buf) >= buttons_per_row:
            rows.append(buf)
            buf = []

    if buf:
        rows.append(buf)

    rows.append([InlineKeyboardButton("✅ Sudah Join", callback_data=done_callback_data)])
    return InlineKeyboardMarkup(rows)
