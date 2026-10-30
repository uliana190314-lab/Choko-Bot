import asyncio
import logging
import os
import random
import time
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message
from datetime import datetime, timedelta

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "9058436955:AAETqBO7xt9w_KSufObjlpzHnTExiiZT9Zw"
DEV_PASSWORD = "1903145" # Твой пароль разработчика
# ==============================

logging.basicConfig(level=logging.INFO)
router = Router()

# --- БАЗЫ ДАННЫХ ---
balances = {}       # user_id: шоколадки
warns = {}          # user_id: варны
inventory = {}      # user_id: инвентарь
custom_nicks = {}   # user_id: кастомный ник (для команды +ник)
premium_users = set() # ID тех, у кого есть премиум
last_work = {}
last_daily = {}

# --- СОСТОЯНИЯ (Для запроса пароля) ---
awaiting_password = set()

SHOP_ITEMS = {
    "вип": {"name": "👑 VIP-статус", "price": 500},
    "размут": {"name": "🔓 Размут", "price": 1000},
    "шоколадка": {"name": "🍫 Шоколадка", "price": 50},
}

# --- ФУНКЦИИ ---
def get_balance(uid): return balances.get(uid, 0)
def add_balance(uid, amount): balances[uid] = get_balance(uid) + amount
def get_name(uid, default_name): return custom_nicks.get(uid, default_name)

async def is_admin(msg: Message):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

# --- ПРИВЕТСТВИЕ ---
@router.message(F.new_chat_members)
async def welcome_new_member(msg: Message):
    for member in msg.new_chat_members:
        if member.is_bot: continue
        await msg.reply(f"👋 Привет, {member.first_name}!\nНе забудь заработать свои первые 🍫 командой `!работа`.")

# --- СТАРТ ---
@router.message(F.text == "/start")
async def start_cmd(msg: Message):
    await msg.reply(
        "🎮 **Игры:** !кто, !дуэль, !рулетка, !шар, !кость, !монетка\n"
        "🍫 **Эко:** !профиль, !топ, !работа, !дейли, !магазин, !инвентарь, !перевод\n"
        "🛡 **Модерация:** !бан, !кик, !мут, !разбан, !амнистия, !варн\n"
        "👤 **Профиль:** +ник [новое_имя] — сменить ник\n"
        "И многое другое!"
    )

# --- СИСТЕМА НИКОВ ---
@router.message(F.text.startswith("+ник"))
async def set_nick_cmd(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        return await msg.reply("Напиши: +ник НовоеИмя")
    
    new_nick = parts[1].strip()
    if len(new_nick) > 20:
        return await msg.reply("Ник слишком длинный.")
        
    custom_nicks[msg.from_user.id] = new_nick
    await msg.reply(f"✅ Твой ник изменен на: {new_nick}")

# --- ПАНЕЛЬ РАЗРАБОТЧИКА ---
@router.message(F.text == "!Разраб")
async def dev_panel_cmd(msg: Message):
    # Эта команда работает только в личке (чтобы никто не спалил пароль в группе)
    if msg.chat.type != "private":
        return await msg.reply("Пароль вводи только в личке со мной!")
    
    awaiting_password.add(msg.from_user.id)
    await msg.reply("🔐 Введи пароль разработчика:")

# Ловим пароль от разраба
@router.message(F.text == DEV_PASSWORD)
async def check_dev_password(msg: Message):
    if msg.from_user.id not in awaiting_password:
        return # Если пароль случайно написали в чате, игнорим
    
    awaiting_password.remove(msg.from_user.id)
    
    # Даем безлимит шоколадок (или много) и премиум
    add_balance(msg.from_user.id, 999999)
    premium_users.add(msg.from_user.id)
    
    await msg.reply(
        "👑 **Доступ разрешен!**\n"
        "Ты получил 999999 🍫 и статус Premium.\n"
        "Новые команды:\n"
        "!выдать [id] [сумма] — выдать шоколадки\n"
        "!выдать_прем [id] — выдать премиум юзеру"
    )

@router.message(F.text.startswith("!выдать"))
async def admin_give_cmd(msg: Message):
    if msg.from_user.id not in premium_users: return
    try:
        parts = msg.text.split()
        target_id = int(parts[1])
        amount = int(parts[2])
        add_balance(target_id, amount)
        await msg.reply(f"✅ Выдано {amount} 🍫 пользователю {target_id}")
    except: await msg.reply("Формат: !выдать 123456789 100")

@router.message(F.text.startswith("!выдать_прем"))
async def admin_give_prem_cmd(msg: Message):
    if msg.from_user.id not in premium_users: return
    try:
        target_id = int(msg.text.split()[1])
        premium_users.add(target_id)
        await msg.reply(f"✅ Пользователь {target_id} получил Premium!")
    except: await msg.reply("Формат: !выдать_прем 123456789")

# --- ИГРЫ ---
@router.message(F.text.startswith("!кто"))
async def who_is_cmd(msg: Message):
    try:
        members = await msg.bot.get_chat_administrators(msg.chat.id)
        random_member = random.choice(members).user
        action = msg.text[len("!кто"):].strip()
        await msg.reply(f"🎲 {random_member.mention} — {action}!" if action else f"🎲 Случайный: {random_member.mention}")
    except: await msg.reply("Не удалось.")

@router.message(F.text.startswith("!дуэль"))
async def duel_cmd(msg: Message):
    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение: !дуэль 50")
    try: bet = int(msg.text.split()[1])
    except: return await msg.reply("Укажи ставку: !дуэль 50")
    if get_balance(msg.from_user.id) < bet or get_balance(msg.reply_to_message.from_user.id) < bet:
        return await msg.reply("У кого-то не хватает шоколадок.")
    
    r1, r2 = random.randint(1, 100), random.randint(1, 100)
    if r1 > r2:
        add_balance(msg.from_user.id, bet); add_balance(msg.reply_to_message.from_user.id, -bet)
        await msg.reply(f"⚔️ Ты победил! ({r1} vs {r2}) Забрал {bet} 🍫")
    elif r2 > r1:
        add_balance(msg.from_user.id, -bet); add_balance(msg.reply_to_message.from_user.id, bet)
        await msg.reply(f"⚔️ Ты проиграл! ({r1} vs {r2}) Потерял {bet} 🍫")
    else: await msg.reply("🤝 Ничья!")

@router.message(F.text == "!кость")
async def dice_cmd(msg: Message):
    await msg.reply(f"🎲 Выпало число: {random.randint(1, 6)}")

@router.message(F.text == "!монетка")
async def coin_cmd(msg: Message):
    await msg.reply(f"🪙 {random.choice(['Орел', 'Решка'])}!")

@router.message(F.text.startswith("!шар"))
async def ball_cmd(msg: Message):
    await msg.reply(f"🎱 {random.choice(['Да', 'Нет', 'Возможно', 'Спроси позже'])}")

# --- ЭКОНОМИКА ---
@router.message(F.text == "!профиль")
async def profile_cmd(msg: Message):
    name = get_name(msg.from_user.id, msg.from_user.first_name)
    status = "👑 Premium" if msg.from_user.id in premium_users else "👤 Юзер"
    await msg.reply(f"👤 **{name}**\n{status}\n🍫 Шоколадки: {get_balance(msg.from_user.id)}\n⚠️ Варны: {warns.get(msg.from_user.id, 0)}/3")

@router.message(F.text == "!топ")
async def top_cmd(msg: Message):
    top = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:5]
    text = "🏆 **Топ богачей:**\n"
    for i, (uid, bal) in enumerate(top, 1):
        text += f"{i}. {get_name(uid, 'Неизвестный')} — {bal} 🍫\n"
    await msg.reply(text if text != "🏆 **Топ богачей:**\n" else "Пусто.")

@router.message(F.text == "!работа")
async def work_cmd(msg: Message):
    if time.time() - last_work.get(msg.from_user.id, 0) < 3600: return await msg.reply("⏳ Отдохни.")
    earned = random.randint(10, 50)
    add_balance(msg.from_user.id, earned)
    last_work[msg.from_user.id] = time.time()
    await msg.reply(f"💼 +{earned} 🍫!")

@router.message(F.text == "!дейли")
async def daily_cmd(msg: Message):
    if time.time() - last_daily.get(msg.from_user.id, 0) < 86400: return await msg.reply("⏳ Уже получал.")
    bonus = random.randint(50, 150)
    add_balance(msg.from_user.id, bonus)
    last_daily[msg.from_user.id] = time.time()
    await msg.reply(f"🎁 +{bonus} 🍫!")

@router.message(F.text.startswith("!перевод"))
async def transfer_cmd(msg: Message):
    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение: !перевод 10")
    try: amount = int(msg.text.split()[1])
    except: return await msg.reply("!перевод 10")
    if get_balance(msg.from_user.id) < amount: return await msg.reply("Мало.")
    add_balance(msg.from_user.id, -amount); add_balance(msg.reply_to_message.from_user.id, amount)
    await msg.reply("✅ Переведено.")

# --- МАГАЗИН ---
@router.message(F.text == "!магазин")
async def shop_cmd(msg: Message):
    text = "🛒 **Магазин:**\n"
    for k, v in SHOP_ITEMS.items(): text += f"{v['name']} — {v['price']} 🍫 (!купить {k})\n"
    await msg.reply(text)

@router.message(F.text.startswith("!купить"))
async def buy_cmd(msg: Message):
    try: key = msg.text.split()[1].lower()
    except: return await msg.reply("!магазин")
    if get_balance(msg.from_user.id) < SHOP_ITEMS[key]["price"]: return await msg.reply("Мало.")
    add_balance(msg.from_user.id, -SHOP_ITEMS[key]["price"])
    await msg.reply(f"✅ Куплено: {SHOP_ITEMS[key]['name']}")

# --- МОДЕРАЦИЯ ---
@router.message(F.text.startswith("!бан"))
async def ban_cmd(msg: Message):
    if not await is_admin(msg) or not msg.reply_to_message: return
    try:
        await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
        await msg.reply("🚫 Забанен.")
    except: await msg.reply("Ошибка.")

@router.message(F.text.startswith("!мут"))
async def mute_cmd(msg: Message):
    if not await is_admin(msg) or not msg.reply_to_message: return
    try: mins = int(msg.text.split()[1])
    except: return await msg.reply("!мут 10")
    try:
        await msg.bot.restrict_chat_member(msg.chat.id, msg.reply_to_message.from_user.id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=mins))
        await msg.reply(f"🤐 Замучен на {mins} мин.")
    except: pass

@router.message(F.text == "!амнистия")
async def amnesty_cmd(msg: Message):
    if not await is_admin(msg): return
    warns.clear()
    await msg.reply("✅ Варны сброшены.")

@router.message(F.text.startswith("!варн"))
async def warn_cmd(msg: Message):
    if not await is_admin(msg) or not msg.reply_to_message: return
    uid = msg.reply_to_message.from_user.id
    warns[uid] = warns.get(uid, 0) + 1
    await msg.reply(f"⚠️ Варн {warns[uid]}/3")
    if warns[uid] >= 3:
        try: await msg.bot.ban_chat_member(msg.chat.id, uid)
        except: pass

# --- ВЕБ-СЕРВЕР ---
async def handle_ping(request): return web.Response(text="OK")
async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    asyncio.create_task(start_web_server())
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
