"""Configuration and message content for the recipe (sous-chef) bot.

Edit the texts below to change wording; edit .env to change the token.
Recipes come from TheMealDB (https://www.themealdb.com), free, no key needed.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()

# Optional: route traffic through a proxy if Telegram is blocked/unstable,
# e.g. http://user:pass@host:port  (empty = direct connection)
PROXY_URL = (os.getenv("PROXY_URL") or "").strip()

MEALDB_URL = "https://www.themealdb.com/api/json/v1/1"
MAX_IDEAS = 10   # how many dish buttons to show for an ingredient

# ── Profile texts (the "What can this bot do?" card) ────────────────────
BOT_DESCRIPTION = (
    "🍳 Your pocket sous-chef! I suggest dish ideas and give you full "
    "step-by-step cooking instructions.\n"
    "\n"
    "Send an ingredient like /chicken or /pasta to get meal ideas.\n"
    "Use /random for a surprise recipe with instructions, category, and a "
    "photo.\n"
    "\n"
    "Perfect for quick dinners, meal prep, and trying new cuisines. Just ask, "
    "cook, and enjoy!"
)
BOT_SHORT_DESCRIPTION = "Your pocket sous-chef: dish ideas and step-by-step recipes."

# ── Messages (HTML) ──────────────────────────────────────────────────────
WELCOME_TEXT = (
    "👋 Welcome! I can give you dish ideas and cooking steps.\n"
    "\n"
    "Try /random for a surprise dish, or send an ingredient like /chicken."
)

HELP_TEXT = (
    "<b>How to use</b>\n"
    "\n"
    "🎲 /random — a surprise recipe with photo and steps\n"
    "🥕 Send an ingredient — e.g. /chicken, /beef, /pasta, /salmon, "
    "or just type <i>rice</i>\n"
    "🔎 Type a dish name — e.g. <i>lasagne</i>\n"
    "\n"
    "Then tap a dish to get the full recipe."
)

IDEAS_TITLE = "🍽 <b>Dish ideas with {query}</b>\n\nTap a dish to see the full recipe:"
NOTHING_FOUND = (
    "😕 I couldn't find dishes for <b>{query}</b>.\n"
    "Try another ingredient like /chicken, /beef or /pasta — or /random."
)
API_ERROR = "⚠️ The recipe service isn't answering right now. Please try again soon."

BTN_ANOTHER = "🎲 Another random dish"
BTN_VIDEO = "▶️ Watch video"

BOT_COMMANDS = [
    ("start", "Start the bot"),
    ("random", "Surprise recipe"),
    ("chicken", "Chicken dish ideas"),
    ("pasta", "Pasta dish ideas"),
    ("beef", "Beef dish ideas"),
    ("help", "How to use this bot"),
]
