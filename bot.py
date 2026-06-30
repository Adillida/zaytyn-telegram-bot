"""
ZAYTYN KG Telegram Bot — @Zaytyn_bot
Framework: python-telegram-bot 20.x (webhook mode)
Deploy: Render.com / Railway / any VPS with HTTPS
"""

import os
import logging
import json
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from fastapi import FastAPI, Request, Response
import uvicorn

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]          # 8738056048:AAHySdowS-PA82gHh7LHRDslKwcunJy7nYo
WEBHOOK_URL = os.environ["WEBHOOK_URL"]        # https://your-app.onrender.com/webhook
WC_URL      = os.environ.get("WC_URL", "https://zaytynkg.com/wp-json/wc/v3")
WC_KEY      = os.environ["WC_CONSUMER_KEY"]   # ck_...
WC_SECRET   = os.environ["WC_CONSUMER_SECRET"]# cs_...

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_data = {}
ORDER_STATE = {}

# ─── WOOCOMMERCE HELPERS ──────────────────────────────────────────────────────
def wc_get(endpoint: str, params: dict = None) -> dict | list:
    """GET from WooCommerce REST API."""
    url = f"{WC_URL}/{endpoint}"
    r = requests.get(url, params=params, auth=(WC_KEY, WC_SECRET), timeout=15)
    r.raise_for_status()
    return r.json()

def get_categories() -> list:
    return wc_get("products/categories", {"per_page": 50, "hide_empty": True})

def search_products(query: str, per_page: int = 5) -> list:
    return wc_get("products", {"search": query, "per_page": per_page, "status": "publish"})

def get_product(product_id: int) -> dict:
    return wc_get(f"products/{product_id}")

def format_product(p: dict) -> str:
    price = p.get("price", "—")
    stock = "✅ В наличии" if p.get("in_stock") else "❌ Нет в наличии"
    return f"*{p['name']}*\n💰 {price} сом\n{stock}\n🔗 {p.get('permalink','')}"

# ─── COMMAND HANDLERS ─────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🛍 Каталог", callback_data="catalog"),
         InlineKeyboardButton("🔍 Поиск", callback_data="search_prompt")],
        [InlineKeyboardButton("🛒 Заказ", callback_data="order_info"),
         InlineKeyboardButton("📦 Опт", callback_data="wholesale_info")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
    ]
    await update.message.reply_text(
        "👋 Добро пожаловать в ZAYTYN KG!\n\n"
        "🌿 Натуральные товары для здоровья и восстановления.\n\n"
        "Выберите раздел:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    try:
        cats = get_categories()
        if not cats:
            await msg.reply_text("Категории не найдены. Попробуйте позже.")
            return
        kb = []
        for cat in cats[:12]:
            kb.append([InlineKeyboardButton(
                f"{cat['name']} ({cat['count']})",
                callback_data=f"cat_{cat['id']}"
            )])
        await msg.reply_text(
            "📂 *Каталог товаров:*",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"catalog error: {e}")
        await msg.reply_text("⚠️ Не удалось загрузить каталог. Попробуйте позже.")

async def search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        query = " ".join(ctx.args)
        await _do_search(update.message, query)
    else:
        ctx.user_data["awaiting_search"] = True
        await update.message.reply_text("🔍 Введите название товара для поиска:")

async def order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛒 *Как сделать заказ:*\n\n"
        "1. Выберите товар в /catalog\n"
        "2. Нажмите «Заказать»\n"
        "3. Укажите имя и адрес доставки\n"
        "4. Менеджер свяжется с вами\n\n"
        "Или напишите нам напрямую:\n"
        "📞 WhatsApp: https://wa.me/996XXXXXXXXX",
        parse_mode="Markdown"
    )

async def wholesale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📦 *Оптовые условия ZAYTYN KG:*\n\n"
        "✅ Минимальный заказ: уточняйте у менеджера\n"
        "✅ Скидки от объёма\n"
        "✅ Доставка по Кыргызстану\n"
        "✅ Договор и накладные\n\n"
        "📩 Для оптовых заявок:\n"
        "Email: info@zaytynkg.com\n"
        "Сайт: https://zaytynkg.com",
        parse_mode="Markdown"
    )

async def support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 *Поддержка ZAYTYN KG*\n\n"
        "Мы рады помочь!\n\n"
        "🌐 Сайт: https://zaytynkg.com\n"
        "📧 Email: info@zaytynkg.com\n"
        "⏰ Режим работы: Пн-Сб, 9:00–18:00\n\n"
        "Опишите вашу проблему, и мы ответим в ближайшее время.",
        parse_mode="Markdown"
    )

# ─── CALLBACK QUERY HANDLER ──────────────────────────────────────────────────
async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "catalog":
        await catalog(update, ctx)

    elif data == "search_prompt":
        ctx.user_data["awaiting_search"] = True
        await q.message.reply_text("🔍 Введите название товара:")

    elif data == "order_info":
    kb = [
        [InlineKeyboardButton("🚚 Today Express", callback_data="delivery_today")],
        [InlineKeyboardButton("🚛 YLDAM Express", callback_data="delivery_yldam")],
        [InlineKeyboardButton("🚕 Чолпон-Ата / Иссык-Куль", callback_data="delivery_local")],
        [InlineKeyboardButton("📍 Самовывоз Бостери", callback_data="delivery_pickup")]
    ]

    await q.message.reply_text(
        "Выберите способ доставки:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

    elif data == "wholesale_info":
        await q.message.reply_text(
            "📦 Оптовые условия: напишите на info@zaytynkg.com\n"
            "Или посетите: https://zaytynkg.com/оптовые-продажи/
        )

    elif data == "support":
        await q.message.reply_text(
            "💬 Поддержка: info@zaytynkg.com\nСайт: https://zaytynkg.com"
        )

    elif data.startswith("cat_"):
        cat_id = data[4:]
        try:
            products = wc_get("products", {
                "category": cat_id, "per_page": 8, "status": "publish"
            })
            if not products:
                await q.message.reply_text("В этой категории нет товаров.")
                return
            kb = []
            for p in products:
                kb.append([InlineKeyboardButton(
                    f"{p['name']} — {p.get('price','?')} сом",
                    callback_data=f"prod_{p['id']}"
                )])
            await q.message.reply_text(
                "🛍 *Товары в категории:*",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"cat products error: {e}")
            await q.message.reply_text("⚠️ Ошибка загрузки товаров.")

    elif data.startswith("prod_"):
        prod_id = int(data[5:])
        try:
            p = get_product(prod_id)
            text = format_product(p)
            kb = [[
                InlineKeyboardButton("🛒 Заказать", callback_data=f"order_{prod_id}"),
                InlineKeyboardButton("🔙 Назад", callback_data="catalog")
            ]]
            await q.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"product detail error: {e}")
            await q.message.reply_text("⚠️ Не удалось загрузить товар.")

    elif data.startswith("order_"):
        prod_id = data[6:]
        ctx.user_data["ordering_product"] = prod_id
        await q.message.reply_text(
            "✏️ Чтобы оформить заказ, напишите ваше имя и номер телефона.\n\n"
            "Пример: Айгуль, +996 555 123456"
        )
        ctx.user_data["awaiting_order"] = True

# ─── TEXT MESSAGE HANDLER ─────────────────────────────────────────────────────
async def text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if ctx.user_data.get("awaiting_search"):
        ctx.user_data.pop("awaiting_search")
        await _do_search(update.message, text)

    elif ctx.user_data.get("awaiting_order"):
        ctx.user_data.pop("awaiting_order")
        prod_id = ctx.user_data.get("ordering_product", "—")
        await update.message.reply_text(
            f"✅ Заявка принята!\n\n"
            f"Товар ID: {prod_id}\n"
            f"Контакт: {text}\n\n"
            f"Менеджер свяжется с вами в ближайшее время.\n"
            f"Или оформите на сайте: https://zaytynkg.com"
        )
    else:
        await update.message.reply_text(
            "Используйте команды:\n"
            "/catalog — каталог товаров\n"
            "/search — поиск товара\n"
            "/order — как заказать\n"
            "/wholesale — оптовые условия\n"
            "/support — поддержка"
        )

async def _do_search(msg, query: str):
    try:
        await msg.reply_text(f"🔍 Ищу «{query}»...")
        products = search_products(query)
        if not products:
            await msg.reply_text(f"❌ По запросу «{query}» ничего не найдено.")
            return
        kb = []
        for p in products:
            kb.append([InlineKeyboardButton(
                f"{p['name']} — {p.get('price','?')} сом",
                callback_data=f"prod_{p['id']}"
            )])
        await msg.reply_text(
            f"✅ Найдено {len(products)} товаров:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        logger.error(f"search error: {e}")
        await msg.reply_text("⚠️ Ошибка поиска. Попробуйте позже.")

# ─── FASTAPI + WEBHOOK SETUP ──────────────────────────────────────────────────
app_fastapi = FastAPI()
ptb_app: Application = None

@app_fastapi.on_event("startup")
async def startup():
    global ptb_app
    ptb_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .updater(None)          # webhook mode — no polling
        .build()
    )
    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("catalog", catalog))
    ptb_app.add_handler(CommandHandler("search", search))
    ptb_app.add_handler(CommandHandler("order", order))
    ptb_app.add_handler(CommandHandler("wholesale", wholesale))
    ptb_app.add_handler(CommandHandler("support", support))
    ptb_app.add_handler(CallbackQueryHandler(button))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))

    await ptb_app.initialize()
    await ptb_app.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook",
        allowed_updates=["message", "callback_query"]
    )
    await ptb_app.start()
    logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")

@app_fastapi.on_event("shutdown")
async def shutdown():
    await ptb_app.stop()

@app_fastapi.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return Response(status_code=200)

@app_fastapi.get("/")
def health():
    return {"status": "ok", "bot": "@Zaytyn_bot"}

if __name__ == "__main__":
    uvicorn.run(app_fastapi, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
