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
marriages = {}      # user_id: partner_id
clans = {}          # clan_name: {"leader": id, "members": []}
user_clan = {}      # user_id: clan_name
boss_hp = 10000
boss_reward = 5000
last_work = {}
last_daily = {}
awaiting_password = set()
has_premium = set()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_balance(uid): return balances.get(uid, 0)
def add_balance(uid, amount): balances[uid] = max(0, get_balance(uid) + amount)
def get_name(uid, default_name): return custom_nicks.get(uid, default_name)

async def is_admin(msg: Message):
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, msg.from_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

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

# --- БРАКИ ---
@router.message(F.text.lower().startswith("!брак") | F.text.lower().startswith("/marry"))
async def marriage_cmd(msg: Message):
    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение того, с кем хочешь вступить в брак.")
    target_id = msg.reply_to_message.from_user.id
    if target_id == msg.from_user.id: return await msg.reply("Нельзя жениться на себе.")
    if msg.from_user.id in marriages: return await msg.reply("Ты уже в браке. Сначала !развод.")
    
    marriages[msg.from_user.id] = target_id
    marriages[target_id] = msg.from_user.id
    await msg.reply(f"💍 Поздравляем! {msg.from_user.mention} и {msg.reply_to_message.from_user.mention} теперь в браке!")

@router.message(F.text.lower() == "!развод" or F.text.lower() == "/divorce")
async def divorce_cmd(msg: Message):
    if msg.from_user.id not in marriages: return await msg.reply("Ты не в браке.")
    partner = marriages[msg.from_user.id]
    del marriages[msg.from_user.id]
    if partner in marriages: del marriages[partner]
    await msg.reply("💔 Брак расторгнут.")

# --- КЛАНЫ ---
@router.message(F.text.lower().startswith("!клан создать") | F.text.lower().startswith("/clan create"))
async def create_clan_cmd(msg: Message):
    try: clan_name = msg.text.split(maxsplit=2)[2]
    except: return await msg.reply("Напиши: !клан создать [Название]")
    if msg.from_user.id in user_clan: return await msg.reply("Ты уже в клане.")
    if clan_name in clans: return await msg.reply("Такой клан уже есть.")
    
    clans[clan_name] = {"leader": msg.from_user.id, "members": [msg.from_user.id]}
    user_clan[msg.from_user.id] = clan_name
    await msg.reply(f"🏰 Клан **{clan_name}** создан! Лидер: {msg.from_user.mention}")

@router.message(F.text.lower().startswith("!клан вступить") | F.text.lower().startswith("/clan join"))
async def join_clan_cmd(msg: Message):
    try: clan_name = msg.text.split(maxsplit=2)[2]
    except: return await msg.reply("Напиши: !клан вступить [Название]")
    if msg.from_user.id in user_clan: return await msg.reply("Ты уже в клане.")
    if clan_name not in clans: return await msg.reply("Клана не существует.")
    
    clans[clan_name]["members"].append(msg.from_user.id)
    user_clan[msg.from_user.id] = clan_name
    await msg.reply(f"✅ Ты вступил в клан **{clan_name}**!")

@router.message(F.text.lower() == "!клан топ" or F.text.lower() == "/clan top")
async def top_clans_cmd(msg: Message):
    if not clans: return await msg.reply("Кланов пока нет.")
    sorted_clans = sorted(clans.items(), key=lambda x: len(x[1]["members"]), reverse=True)[:5]
    text = "🏰 **Топ кланов:**\n"
    for i, (name, data) in enumerate(sorted_clans, 1):
        text += f"{i}. {name} — {len(data['members'])} чел.\n"
    await msg.reply(text)

# --- БОСС ---
@router.message(F.text.lower() == "!босс" or F.text.lower() == "/boss")
async def boss_cmd(msg: Message):
    global boss_hp
    if boss_hp <= 0: return await msg.reply("Босс уже мертв. Скоро появится новый!")
    
    dmg = random.randint(50, 300)
    boss_hp -= dmg
    
    if boss_hp <= 0:
        add_balance(msg.from_user.id, boss_reward)
        await msg.reply(f"💀 **БОСС ПОВЕРЖЕН!** {msg.from_user.mention} забрал {boss_reward} 🍫!")
        boss_hp = 10000
    else:
        await msg.reply(f"⚔️ Ты ударил босса на {dmg} урона! Осталось HP: {boss_hp}")

# --- КЕЙСЫ ---
@router.message(F.text.lower() == "!кейс" or F.text.lower() == "/case")
async def case_cmd(msg: Message):
    cost = 100
    if get_balance(msg.from_user.id) < cost: return await msg.reply(f"Кейс стоит {cost} 🍫. Мало шоколадок.")
    
    add_balance(msg.from_user.id, -cost)
    prizes = [(10, "🥉 Маленький", 50), (30, "🥈 Средний", 150), (50, "🥇 Большой", 300), (9, "💎 Мега", 1000), (1, "👑 ДЖЕКПОТ", 5000)]
    total_weight = sum(p[0] for p in prizes)
    r = random.randint(1, total_weight)
    current = 0
    for weight, name, reward in prizes:
        current += weight
        if r <= current:
            add_balance(msg.from_user.id, reward)
            await msg.reply(f"🎁 Ты открыл кейс и получил: **{name}** (+{reward} 🍫)!")
            break

# --- БИТВА ---
@router.message(F.text.lower().startswith("!битва") | F.text.lower().startswith("/battle"))
async def battle_cmd(msg: Message):
    if not msg.reply_to_message: return await msg.reply("Ответь на сообщение противника: !битва")
    if msg.reply_to_message.from_user.id == msg.from_user.id: return await msg.reply("Сам с собой?")
    
    my_power = get_balance(msg.from_user.id) // 10 + random.randint(1, 50)
    enemy_power = get_balance(msg.reply_to_message.from_user.id) // 10 + random.randint(1, 50)
    
    if my_power > enemy_power:
        win_amount = random.randint(10, 100)
        add_balance(msg.reply_to_message.from_user.id, -win_amount)
        add_balance(msg.from_user.id, win_amount)
        await msg.reply(f"⚔️ {msg.from_user.mention} победил {msg.reply_to_message.from_user.mention} и забрал {win_amount} 🍫!")
    else:
        win_amount = random.randint(10, 100)
        add_balance(msg.from_user.id, -win_amount)
        add_balance(msg.reply_to_message.from_user.id, win_amount)
        await msg.reply(f"⚔️ {msg.reply_to_message.from_user.mention} победил {msg.from_user.mention} и забрал {win_amount} 🍫!")

# --- ПРОФИЛЬ ---
@router.message(F.text.lower() == "!профиль" or F.text.lower() == "/profile")
async def profile_cmd(msg: Message):
    uid = msg.from_user.id
    name = get_name(uid, msg.from_user.first_name)
    status = "👑 Premium" if uid in has_premium else "👤 Юзер"
    partner = marriages.get(uid)
    partner_name = get_name(partner, "Никто") if partner else "Никто"
    clan_name = user_clan.get(uid, "Нет")
    
    await msg.reply(
        f"👤 **{name}** [{status}]\n"
        f"🍫 Шоколадки: {get_balance(uid)}\n"
        f"💍 Брак: {partner_name}\n"
        f"🏰 Клан: {clan_name}\n"
        f"⚠️ Варны: {warns.get(uid, 0)}/3"
    )

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
    await msg.reply("👑 **Доступ разрешен!** Ты получил 999999 🍫 и Premium.")

@router.message(F.text.lower().startswith("!выдать_прем"))
async def admin_give_prem_cmd(msg: Message):
    if msg.from_user.id not in has_premium: return
    try:
        target_id = int(msg.text.split()[1])
        has_premium.add(target_id)
        await msg.reply(f"✅ Пользователь {target_id} получил Premium!")
    except: await msg.reply("Формат: !выдать_прем 123456789")

@router.message(F.text.lower().startswith("!выдать"))
async def admin_give_cmd(msg: Message):
    if msg.from_user.id not in has_premium: return
    try:
        parts = msg.text.split()
        target_id = int(parts[1])
        amount = int(parts[2])
        add_balance(target_id, amount)
        await msg.reply(f"✅ Выдано {amount} 🍫 пользователю {target_id}")
    except: await msg.reply("Формат: !выдать 123456789 100")

# --- УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ОСТАЛЬНЫХ КОМАНД ---
@router.message(F.text)
async def universal_handler(msg: Message):
    t = msg.text.lower()
    
    if t in ["!баланс", "/balance"]:
        await msg.reply(f"🍫 Твой баланс: {get_balance(msg.from_user.id)}")
    elif t == "!топ" or t == "/top":
        top = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:5]
        text = "🏆 **Топ богачей:**\n"
        for i, (uid, bal) in enumerate(top, 1):
            text += f"{i}. {get_name(uid, 'Неизвестный')} — {bal} 🍫\n"
        await msg.reply(text if text != "🏆 **Топ богачей:**\n" else "Пусто.")
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
    elif is_cmd(t, "бан") or is_cmd(t, "ban"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        try:
            await msg.bot.ban_chat_member(msg.chat.id, msg.reply_to_message.from_user.id)
            await msg.reply("🚫 Забанен.")
        except: pass
    elif is_cmd(t, "мут") or is_cmd(t, "mute"):
        if not await is_admin(msg) or not msg.reply_to_message: return
        try: mins = int(msg.text.split()[1])
        except: return await msg.reply("!мут 10")
        try:
            await msg.bot.restrict_chat_member(msg.chat.id, msg.reply_to_message.from_user.id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=mins))
            await msg.reply(f"🤐 Замучен на {mins} мин.")
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
