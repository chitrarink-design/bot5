"""Recipe (pocket sous-chef) bot.

/random → a surprise recipe with photo, category and full steps.
/chicken, /pasta, any /<ingredient> or plain text → dish ideas as buttons;
tap one for the full recipe. Data from TheMealDB (free, no key).

Run with:  python bot.py
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import sys

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import config

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("recipe-bot")

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


# ── TheMealDB ────────────────────────────────────────────────────────────
async def mealdb(endpoint: str, **params: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{config.MEALDB_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json().get("meals") or []


async def find_dishes(query: str) -> list[dict]:
    """Try ingredient, then category, then dish name."""
    q = query.strip().lower().replace(" ", "_")
    meals = await mealdb("filter.php", i=q)
    if not meals:
        meals = await mealdb("filter.php", c=query.strip().title())
    if not meals:
        meals = await mealdb("search.php", s=query.strip())
    return meals


async def get_meal(meal_id: str) -> dict | None:
    meals = await mealdb("lookup.php", i=meal_id)
    return meals[0] if meals else None


async def random_meal() -> dict | None:
    meals = await mealdb("random.php")
    return meals[0] if meals else None


# ── Formatting ───────────────────────────────────────────────────────────
def _e(text: str | None) -> str:
    return html.escape((text or "").strip())


def recipe_caption(meal: dict) -> str:
    lines = [f"🍽 <b>{_e(meal.get('strMeal'))}</b>", ""]
    if meal.get("strCategory"):
        lines.append(f"📂 Category: {_e(meal['strCategory'])}")
    if meal.get("strArea"):
        lines.append(f"🌍 Cuisine: {_e(meal['strArea'])}")
    lines += ["", "🥕 <b>Ingredients</b>"]
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        if not ing:
            continue
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        lines.append(f"• {_e(measure) + ' ' if measure else ''}{_e(ing)}")
    text = "\n".join(lines)
    if len(text) > CAPTION_LIMIT:
        text = text[: CAPTION_LIMIT - 1].rsplit("\n", 1)[0] + "\n…"
    return text


def recipe_steps(meal: dict) -> list[str]:
    """Numbered instructions, split into Telegram-sized messages."""
    raw = meal.get("strInstructions") or ""
    steps = [s.strip() for s in re.split(r"\r?\n+", raw) if s.strip()]
    # Drop source "STEP 1" style headings; we number the steps ourselves.
    steps = [s for s in steps if not re.fullmatch(r"(?i)step\s*\d+[.:]?", s)]
    steps = [re.sub(r"^(?:step\s*)?\d+[.):]\s*", "", s, flags=re.I) for s in steps]
    lines = ["👩‍🍳 <b>Cooking steps</b>", ""]
    lines += [f"<b>{n}.</b> {_e(s)}" for n, s in enumerate(steps, 1)]

    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 2 > MESSAGE_LIMIT:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def recipe_buttons(meal: dict) -> InlineKeyboardMarkup:
    rows = []
    if meal.get("strYoutube"):
        rows.append([InlineKeyboardButton(config.BTN_VIDEO, url=meal["strYoutube"])])
    rows.append([InlineKeyboardButton(config.BTN_ANOTHER, callback_data="random")])
    return InlineKeyboardMarkup(rows)


# ── Sending ──────────────────────────────────────────────────────────────
async def send_recipe(chat, meal: dict) -> None:
    caption = recipe_caption(meal)
    try:
        await chat.send_action(ChatAction.UPLOAD_PHOTO)
        await chat.send_photo(meal["strMealThumb"], caption=caption, parse_mode=ParseMode.HTML)
    except (TelegramError, KeyError) as exc:
        log.warning("Photo send failed (%s); sending text.", exc)
        await chat.send_message(caption, parse_mode=ParseMode.HTML)

    chunks = recipe_steps(meal)
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        await chat.send_message(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=recipe_buttons(meal) if last else None,
            disable_web_page_preview=True,
        )


async def send_random(chat) -> None:
    await chat.send_action(ChatAction.TYPING)
    try:
        meal = await random_meal()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("MealDB error: %s", exc)
        await chat.send_message(config.API_ERROR)
        return
    if meal:
        await send_recipe(chat, meal)
    else:
        await chat.send_message(config.API_ERROR)


async def send_ideas(update: Update, query: str) -> None:
    chat = update.effective_chat
    await chat.send_action(ChatAction.TYPING)
    try:
        meals = await find_dishes(query)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("MealDB error: %s", exc)
        await chat.send_message(config.API_ERROR)
        return

    safe = html.escape(query)
    if not meals:
        await chat.send_message(
            config.NOTHING_FOUND.format(query=safe), parse_mode=ParseMode.HTML
        )
        return
    buttons = [
        [InlineKeyboardButton(f"🍴 {m['strMeal']}", callback_data=f"meal:{m['idMeal']}")]
        for m in meals[: config.MAX_IDEAS]
    ]
    await chat.send_message(
        config.IDEAS_TITLE.format(query=safe),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ── Handlers ─────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.info("/start from %s (%s)", user.id, user.full_name)
    await update.effective_message.reply_html(config.WELCOME_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(config.HELP_TEXT)


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_random(update.effective_chat)


async def ingredient_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any other /command is treated as an ingredient: /chicken, /salmon, …"""
    word = update.effective_message.text.split()[0][1:].split("@")[0]
    await send_ideas(update, word.replace("_", " "))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text.strip()
    if len(text) > 50:
        await update.effective_message.reply_html(config.HELP_TEXT)
        return
    await send_ideas(update, text)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat = update.effective_chat
    if query.data == "random":
        await send_random(chat)
        return
    if query.data.startswith("meal:"):
        await chat.send_action(ChatAction.TYPING)
        try:
            meal = await get_meal(query.data.split(":", 1)[1])
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("MealDB error: %s", exc)
            meal = None
        if meal:
            await send_recipe(chat, meal)
        else:
            await chat.send_message(config.API_ERROR)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Brief internet/Telegram hiccups are retried automatically — no traceback.
    if isinstance(context.error, NetworkError):
        log.warning("Network problem, retrying: %s", context.error)
        return
    log.error("Handler error", exc_info=context.error)


async def post_init(application: Application) -> None:
    bot = application.bot
    await bot.set_my_commands(config.BOT_COMMANDS)
    try:
        await bot.set_my_description(config.BOT_DESCRIPTION)
        await bot.set_my_short_description(config.BOT_SHORT_DESCRIPTION)
    except TelegramError as exc:
        log.warning("Could not set description: %s", exc)
    me = await bot.get_me()
    log.info("Running as @%s (id %s)", me.username, me.id)


def make_request(pool_size: int) -> HTTPXRequest:
    """HTTP client with generous timeouts so short network blips don't fail."""
    return HTTPXRequest(
        connection_pool_size=pool_size,
        connect_timeout=20.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        proxy=config.PROXY_URL or None,
    )


def main() -> None:
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .request(make_request(pool_size=8))
        .get_updates_request(make_request(pool_size=1))
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(MessageHandler(filters.COMMAND, ingredient_command))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(on_error)

    # Python 3.14+ no longer creates an event loop automatically, which
    # run_polling() relies on — so create one explicitly.
    asyncio.set_event_loop(asyncio.new_event_loop())
    log.info("Bot starting (long polling)…")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,  # keep retrying if the network is down at startup
    )


if __name__ == "__main__":
    main()
