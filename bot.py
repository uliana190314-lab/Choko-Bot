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
DEV_PASSWORD = "1903145"
# ==============================

logging.basicConfig(level=logging.INFO)
router = Router()

# --- БАЗЫ ДАННЫХ (в памяти) ---
balances = {}       # user_id: шоколадки
warns = {}          # user_id: варны
inventory = {}      # user_id: инвентарь
custom_nicks = {}   # user_id: кастомный ник
premium_users = set() # ID тех, у кого есть премиум
last_work = {}
last_daily = {}
awaiting_password = set()

SHOP_ITEMS = {
    "вип": {"name": "👑 VIP-статус", "price": 500},
    "размут": {"name": "🔓 Размут", "price": 1000},
    "шоколадка": {"name": "🍫 Шоколадка", "price": 50},
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_balance(uid): return balances.get(uid, 0)
def add_balance(uid, amount): balances[uid] = get_balance(uid) + amount
def get_name(uid, default_name): return custom_nicks.get(uid, default_name)

async def is_admin(msg: Message):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

# Универсальная проверка: начинается ли текст с команды (игнорируя регистр, ! или /)
def is_cmd(text, cmd):
    t = text.lower()
    return t.startswith(f"!{cmd}") or t.startswith(f"/{cmd}")

# --- ПРИВЕТСТВИЕ НОВЫХ УЧАСТНИКОВ ---
@router.message(F.new_chat_members)
async def welcome_new_member(msg: Message):
    for member in msg.new_chat_members:
        if member.is_bot: continue
        await msg.reply(f"👋 Привет, {member.first_name}!\nНе забудь заработать свои первые 🍫 командой `!работа`.")

# --- СТАРТ (ТВОЙ ТЕКСТ) ---
@router.message(F.text.lower().in_({"/start", "!start", "!помощь", "!help", "/help"}))
async def start_cmd(msg: Message):
    text = (
        f"Привет {msg.from_user.first_name} 🍫\n"
        "Я твой помощник, но команды узнай в меню лень болтать 🙊"
    )
    await msg.reply(text)

# --- ПАНЕЛЬ РАЗРАБОТЧИКА ---
@router.message(F.text.lower() == "!разраб")
async def dev_panel_cmd(msg: Message):
    if msg.chat.type != "private": return await msg.reply("Пароль вводи только в личке со мной!")
    awaiting_password.add(msg.from_user.id)
    await msg.reply("🔐 Введи пароль разработчика:")

@router.message(F.text == DEV_PASSWORD)
async def check_dev_password(msg: Message):
    if msg.from_user.id not in awaiting_password: return
    awaiting_password.remove(msg.from_user.id)
    add_balance(msg.from_user.id, 999999)
    premium_users.add(msg.from_user.id)
    await msg.reply("👑 **Доступ разрешен!**\nТы получил 999999 🍫 и статус Premium.\n\n!выдать [id] [сумма] — выдать шоколадки\n!выдать_прем [id] — выдать премиум")

@router.message(F.text.lower().startswith("!выдать_прем"))
async def admin_give_prem_cmd(msg: Message):
    if msg.from_user.id not in premium_users: return
    try:
        target_id = int(msg.text.split()[1])
        premium_users.add(target_id)
        await msg.reply(f"✅ Пользователь {target_id} получил Premium!")
    except: await msg.reply("Формат: !выдать_прем 123456789")

@router.message(F.text.lower().startswith("!выдать"))
async def admin_give_cmd(msg: Message):
    if msg.from_user.id not in premium_users: return
    try:
        parts = msg.text.split()
        target_id = int(parts[1])
        amount = int(parts[2])
        add_balance(target_id, amount)
        await msg.reply(f"✅ Выдано {amount} 🍫 пользователю {target_id}")
    except: await msg.reply("Формат: !выдать 123456789 100")

# --- СИСТЕМА НИКОВ ---
@router.message(F.text.lower().startswith("+ник"))
async def set_nick_cmd(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2: return await msg.reply("Напиши: +ник НовоеИмя")
    new_nick = parts[1].strip()
    if len(new_nick) > 20: return await msg.reply("Ник слишком длинный.")
    custom_nicks[msg.from_user.id] = new_nick
    await msg.reply(f"✅ Твой ник изменен на: {new_nick}")

# --- УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК КОМАНД ---
@router.message(F.text)
async def universal_handler(msg: Message):
    t = msg.text.lower()
    
    # Профиль и Баланс
    if t in ["!профиль", "/profile", "/профиль"]:
        name = get_name(msg.from_user.id, msg.from_user.first_name)
        await msg.reply(f"👤 **{name}**\n🍫 Баланс: {get_balance(msg.from_user.id)}\n⚠️ Варны: {warns.get(msg.from_user.id, 0)}/3")
    elif t in ["!баланс", "/balance", "/баланс"]:
        await msg.reply(f"🍫 Твой баланс: {get_balance(msg.from_user.id)}")
    elif t == "!топ" or t == "/top":
        top = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:5]
        text = "🏆 **Топ богачей:**\n"
        for i, (uid, bal) in enumerate(top, 1):
            text += f"{i}. {get_name(uid, 'Неизвестный')} — {bal} 🍫\n"
        await msg.reply(text if text != "🏆 **Топ богачей:**\n" else "Пусто.")
    
    # Игры
    elif is_cmd(t, "кто") or is_cmd(t, "who"):
        try:
            members = await msg.bot.get_chat_administrators(msg.chat.id)
            random_member = random.choice(members).user
            action = msg.text[4:].strip()
            await msg.reply(f"🎲 {random_member.mention} — {action}!" if action else f"🎲 Случайный: {random_member.mention}")
        except: await msg.reply("Не удалось.")
    elif is_cmd(t, "дуэль") or is_cmd(t, "duel"):
        if not msg.reply_to_message: return await msg.reply("Ответь на сообщение: !дуэль 50")
        try: bet = int(msg.text.split()[1])
        except: return await msg.reply("Укажи ставку: !дуэль 50")
        if get_balance(msg.from_user.id) < bet or get_balance(msg.reply_to_message.from_user.id) < bet: return await msg.reply("У кого-то не хватает шоколадок.")
        r1, r2 = random.randint(1, 100), random.randint(1, 100)
        if r1 > r2:
            add_balance(msg.from_user.id, bet); add_balance(msg.reply_to_message.from_user.id, -bet)
            await msg.reply(f"⚔️ Ты победил! ({r1} vs {r2}) Забрал {bet} 🍫")
        elif r2 > r1:
            add_balance(msg.from_user.id, -bet); add_balance(msg.reply_to_message.from_user.id, bet)
            await msg.reply(f"⚔️ Ты проиграл! ({r1} vs {r2}) Потерял {bet} 🍫")
        else: await msg.reply("🤝 Ничья!")
    elif t == "!кость" or t == "/dice":
        await msg.reply(f"🎲 Выпало: {random.randint(1, 6)}")
    elif t == "!монетка" or t == "/coin":
        await msg.reply(f"🪙 {random.choice(['Орел', 'Решка'])}!")
    elif is_cmd(t, "шар") or is_cmd(t, "ball"):
        await msg.reply(f"🎱 {random.choice(['Да', 'Нет', 'Возможно', 'Спроси позже'])}")
    
    # Экономика
    elif t == "!работа" or t == "/work":
        if time.time() - last_work.get(msg.from_user.id, 0) < 3600: return await msg.reply("⏳ Отдохни.")
        earned = random.randint(10, 50)
        add_balance(msg.from_user.id, earned)
        last_work[msg.from_user.id] = time.time()
        await msg.reply(f"💼 +{earned} 🍫!")
    elif t == "!дейли" or t == "/daily":
        if time.time() - last_daily.get(msg.from_user.id, 0) < 86400: return await msg.reply("⏳ Уже получал.")
        bonus = random.randint(50, 150)
        add_balance(msg.from_user.id, bonus)
        last_daily[msg.from_user.id] = time.time()
        await msg.reply(f"🎁 +{bonus} 🍫!")
    elif is_cmd(t, "перевод") or is_cmd(t, "transfer"):
        if not msg.reply_to_message: return await msg.reply("Ответь на сообщение: !перевод 10")
        try: amount = int(msg.text.split()[1])
        except: return await msg.reply("!перевод 10")
        if get_balance(msg.from_user.id) < amount: return await msg.reply("Мало.")
        add_balance(msg.from_user.id, -amount); add_balance(msg.reply_to_message.from_user.id, amount)
        await msg.reply("✅ Переведено.")
    elif is_cmd(t, "казино") or is_cmd(t, "casino"):
        try: bet = int(msg.text.split()[1])
        except: return await msg.reply("Пример: !казино 10")
        if get_balance(msg.from_user.id) < bet: return await msg.reply("Мало шоколадок.")
        if random.choice([True, False]): add_balance(msg.from_user.id, bet); await msg.reply(f"🎰 Выиграл {bet} 🍫!")
        else: add_balance(msg.from_user.id, -bet); await msg.reply(f"💸 Проиграл {bet} 🍫.")
    
    # Магазин
    elif t == "!магазин" or t == "/shop":
        text = "🛒 **Магазин:**\n"
        for k, v in SHOP_ITEMS.items(): text += f"{v['name']} — {v['price']} 🍫 (!купить {k})\n"
        await msg.reply(text)
    elif is_cmd(t, "купить") or is_cmd(t, "buy"):
        try: key = msg.text.split()[1].lower()
        except: return await msg.reply("!магазин")
        if key not in SHOP_ITEMS: return await msg.reply("Нет такого.")
        if get_balance(msg.from_user.id) < SHOP_ITEMS[key]["price"]: return await msg.reply("Мало шоколадок.")
        add_balance(msg.from_user.id, -SHOP_ITEMS[key]["price"])
        inventory.setdefault(msg.from_user.id, []).append(key)
        await msg.reply(f"✅ Куплено: {SHOP_ITEMS[key]['name']}")
    
    # Модерация
    elif is_cmd(t, "бан") or is_cmd(t, "ban"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        try:
            await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
            await msg.reply("🚫 Забанен.")
        except: await msg.reply("Ошибка прав.")
    elif is_cmd(t, "кик") or is_cmd(t, "kick"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        try:
            await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
            await msg.bot.unban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
            await msg.reply("👢 Кикнут.")
        except: await msg.reply("Ошибка.")
    elif is_cmd(t, "мут") or is_cmd(t, "mute"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        try: mins = int(msg.text.split()[1])
        except: return await msg.reply("!мут 10")
        try:
            await msg.bot.restrict_chat_member(msg.chat.id, msg.reply_to_message.from_user.id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=mins))
            await msg.reply(f"🤐 Замучен на {mins} мин.")
        except: pass
    elif is_cmd(t, "варн") or is_cmd(t, "warn"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        uid = msg.reply_to_message.from_user.id
        warns[uid] = warns.get(uid, 0) + 1
        await msg.reply(f"⚠️ Варн {warns[uid]}/3")
        if warns[uid] >= 3:
            try: await msg.bot.ban_chat_member(msg.chat.id, uid)
            except: pass
    elif t == "!амнистия" or t == "/amnesty":
        if not await is_admin(msg): return
        warns.clear()
        await msg.reply("✅ Варны сброшены.")

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
