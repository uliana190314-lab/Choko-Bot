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

# --- БАЗЫ ДАННЫХ ---
balances = {}
warns = {}
custom_nicks = {}
marriages = {}
clans = {}
user_clan = {}
boss_hp = 10000
boss_reward = 5000
last_work = {}
last_daily = {}
awaiting_password = set()
has_premium = set()
moderators = {} # user_id: уровень (1-5)

SHOP_ITEMS = {
    "вип": {"name": "👑 VIP-статус", "price": 500},
    "размут": {"name": "🔓 Размут", "price": 1000},
    "шоколадка": {"name": "🍫 Шоколадка", "price": 50},
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_balance(uid): return balances.get(uid, 0)
def add_balance(uid, amount): balances[uid] = max(0, get_balance(uid) + amount)
def get_name(uid, default_name): return custom_nicks.get(uid, default_name)

# Проверка прав: Админ чата ИЛИ Модер уровня
async def check_power(msg: Message, required_level: int):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        if member.status in ["administrator", "creator"]:
            return True
    except: pass
    level = moderators.get(msg.from_user.id, 0)
    if level >= required_level:
        return True
    await msg.reply(f"❌ Недостаточно прав. Нужен уровень модератора: {required_level}.")
    return False

def is_cmd(text, cmd):
    t = text.lower()
    return t.startswith(f"!{cmd}") or t.startswith(f"/{cmd}")

# --- СТАРТ ---
@router.message(F.text.lower().in_({"/start", "!start", "!помощь", "!help", "/help"}))
async def start_cmd(msg: Message):
    await msg.reply(
        f"Привет {msg.from_user.first_name} 🍫\n"
        "Я твой помощник, но команды узнай в меню лень болтать 🙊"
    )

# --- КРАСИВЫЙ ПРОФИЛЬ (КАК В ИРИСЕ) ---
@router.message(F.text.lower() == "!профиль" | F.text.lower() == "/profile")
async def profile_cmd(msg: Message):
    uid = msg.from_user.id
    name = get_name(uid, msg.from_user.first_name)
    
    # Статусы
    status = "👑 Premium" if uid in has_premium else "👤 Юзер"
    mod_level = moderators.get(uid, 0)
    mod_status = f" 🛡 Модер {mod_level}" if mod_level > 0 else ""
    
    # Отношения и клан
    partner = marriages.get(uid)
    partner_name = get_name(partner, "Никто") if partner else "Нет"
    clan_name = user_clan.get(uid, "Нет")
    
    # Экономика
    bal = get_balance(uid)
    w = warns.get(uid, 0)
    
    # Рамка профиля
    text = (
        "╔══════════════════════╗\n"
        f"   👤 **{name}** {status}{mod_status}\n"
        "╠══════════════════════╣\n"
        f"   🍫 Шоколадки: **{bal}** 🍫\n"
        f"   💍 Брак: **{partner_name}**\n"
        f"   🏰 Клан: **{clan_name}**\n"
        f"   ⚠️ Варны: **{w}/3**\n"
        "╚══════════════════════╝"
    )
    await msg.reply(text, parse_mode="Markdown")

# --- СИСТЕМА МОДЕРАТОРОВ (Выдача) ---
@router.message(F.text.lower().startswith("!модер"))
async def set_moder_cmd(msg: Message):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        if member.status not in ["administrator", "creator"] and msg.from_user.id not in has_premium:
            return await msg.reply("❌ Только админы чата могут выдавать модерку.")
    except: return

    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение того, кому даешь модерку: !модер 1")
    try: level = int(msg.text.split()[1])
    except: return await msg.reply("Укажи уровень от 1 до 5: !модер 1")
    
    if level < 1 or level > 5: return await msg.reply("Уровень должен быть от 1 до 5.")
    
    target = msg.reply_to_message.from_user.id
    moderators[target] = level
    await msg.reply(f"🛡 Пользователь {msg.reply_to_message.from_user.first_name} назначен Модером {level} уровня!")

@router.message(F.text.lower().startswith("!снять_модер"))
async def remove_moder_cmd(msg: Message):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        if member.status not in ["administrator", "creator"] and msg.from_user.id not in has_premium: return
    except: return
    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение.")
    
    target = msg.reply_to_message.from_user.id
    if target in moderators:
        del moderators[target]
        await msg.reply(f"✅ С пользователя {msg.reply_to_message.from_user.first_name} сняты права модератора.")

# --- МОДЕРАЦИЯ (С УРОВНЯМИ) ---

# Варн: Уровень 1
@router.message(F.text.lower().startswith("!варн") | F.text.lower().startswith("/warn"))
async def warn_cmd(msg: Message):
    if not await check_power(msg, 1) or not msg.reply_to_message: return
    uid = msg.reply_to_message.from_user.id
    warns[uid] = warns.get(uid, 0) + 1
    await msg.reply(f"⚠️ Варн {warns[uid]}/3")
    if warns[uid] >= 3:
        try: await msg.bot.ban_chat_member(msg.chat.id, uid)
        except: pass

# Мут: Уровень 2
@router.message(F.text.lower().startswith("!мут") | F.text.lower().startswith("/mute"))
async def mute_cmd(msg: Message):
    if not await check_power(msg, 2) or not msg.reply_to_message: return
    try: mins = int(msg.text.split()[1])
    except: return await msg.reply("!мут 10")
    try:
        await msg.bot.restrict_chat_member(msg.chat.id, msg.reply_to_message.from_user.id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=mins))
        await msg.reply(f"🤐 Замучен на {mins} мин.")
    except: pass

# Кик: Уровень 3
@router.message(F.text.lower().startswith("!кик") | F.text.lower().startswith("/kick"))
async def kick_cmd(msg: Message):
    if not await check_power(msg, 3) or not msg.reply_to_message: return
    try:
        await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
        await msg.bot.unban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
        await msg.reply("👢 Кикнут.")
    except: pass

# Бан: Уровень 4
@router.message(F.text.lower().startswith("!бан") | F.text.lower().startswith("/ban"))
async def ban_cmd(msg: Message):
    if not await check_power(msg, 4) or not msg.reply_to_message: return
    try:
        await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
        await msg.reply("🚫 Забанен.")
    except: pass

# Амнистия: Уровень 5
@router.message(F.text.lower() == "!амнистия" | F.text.lower() == "/amnesty")
async def amnesty_cmd(msg: Message):
    if not await check_power(msg, 5): return
    warns.clear()
    await msg.reply("✅ Варны сброшены.")

# --- ИГРЫ И ЭКОНОМИКА ---
@router.message(F.text.lower() == "!баланс" | F.text.lower() == "/balance")
async def balance_cmd(msg: Message): await msg.reply(f"🍫 Твой баланс: {get_balance(msg.from_user.id)}")

@router.message(F.text.lower() == "!работа" | F.text.lower() == "/work")
async def work_cmd(msg: Message):
    if time.time() - last_work.get(msg.from_user.id, 0) < 3600: return await msg.reply("⏳ Отдохни.")
    earned = random.randint(10, 50)
    add_balance(msg.from_user.id, earned)
    last_work[msg.from_user.id] = time.time()
    await msg.reply(f"💼 +{earned} 🍫!")

@router.message(F.text.lower() == "!дейли" | F.text.lower() == "/daily")
async def daily_cmd(msg: Message):
    if time.time() - last_daily.get(msg.from_user.id, 0) < 86400: return await msg.reply("⏳ Уже получал.")
    bonus = random.randint(50, 150)
    add_balance(msg.from_user.id, bonus)
    last_daily[msg.from_user.id] = time.time()
    await msg.reply(f"🎁 +{bonus} 🍫!")

@router.message(F.text.lower().startswith("!кто") | F.text.lower().startswith("/who"))
async def who_cmd(msg: Message):
    try:
        members = await msg.bot.get_chat_administrators(msg.chat.id)
        random_member = random.choice(members).user
        action = msg.text[4:].strip()
        await msg.reply(f"🎲 {random_member.mention} — {action}!" if action else f"🎲 Случайный: {random_member.mention}")
    except: pass

@router.message(F.text.lower() == "!кость" | F.text.lower() == "/dice")
async def dice_cmd(msg: Message): await msg.reply(f"🎲 Выпало: {random.randint(1, 6)}")

@router.message(F.text.lower() == "!монетка" | F.text.lower() == "/coin")
async def coin_cmd(msg: Message): await msg.reply(f"🪙 {random.choice(['Орел', 'Решка'])}!")

@router.message(F.text.lower() == "!босс" | F.text.lower() == "/boss")
async def boss_cmd(msg: Message):
    global boss_hp
    if boss_hp <= 0: return await msg.reply("Босс мертв.")
    boss_hp -= random.randint(50, 300)
    if boss_hp <= 0:
        add_balance(msg.from_user.id, boss_reward)
        await msg.reply(f"💀 **БОСС ПОВЕРЖЕН!** {msg.from_user.mention} забрал {boss_reward} 🍫!")
        boss_hp = 10000
    else:
        await msg.reply(f"⚔️ Удар! Осталось HP: {boss_hp}")

# --- ПАНЕЛЬ РАЗРАБОТЧИКА ---
@router.message(F.text.lower() == "!разраб")
async def dev_panel_cmd(msg: Message):
    if msg.chat.type != "private": return await msg.reply("Пароль вводи только в личке!")
    awaiting_password.add(msg.from_user.id)
    await msg.reply("🔐 Введи пароль разработчика:")

@router.message(F.text == DEV_PASSWORD)
async def check_dev_password(msg: Message):
    if msg.from_user.id not in awaiting_password: return
    awaiting_password.remove(msg.from_user.id)
    add_balance(msg.from_user.id, 999999)
    has_premium.add(msg.from_user.id)
    moderators[msg.from_user.id] = 5 # Даем макс уровень модера
    await msg.reply("👑 **Доступ разрешен!** Ты получил 999999 🍫, Premium и Модера 5 уровня.")

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
