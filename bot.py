import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message

BOT_TOKEN = "9058436955:AAETqBO7xt9w_KSufObjlpzHnTExiiZT9Zw"

logging.basicConfig(level=logging.INFO)
router = Router()

balances = {}
warns = {}

@router.message(F.text == "/start")
async def start_cmd(msg: Message):
    await msg.reply("Привет! Я бот с шоколадками. 🍫\n\n"
                    "!баланс - узнать баланс\n"
                    "!шоколадки - получить 10 шоколадок\n"
                    "!перевод - перевести шоколадки (ответом на сообщение)")

@router.message(F.text == "!баланс")
async def balance_cmd(msg: Message):
    await msg.reply(f"🍫 Твой баланс: {balances.get(msg.from_user.id, 0)}")

@router.message(F.text == "!шоколадки")
async def daily_cmd(msg: Message):
    balances[msg.from_user.id] = balances.get(msg.from_user.id, 0) + 10
    await msg.reply("🍫 Ты получил 10 шоколадок!")

@router.message(F.text.startswith("!перевод"))
async def transfer_cmd(msg: Message):
    if not msg.reply_to_message:
        return await msg.reply("Ответь на сообщение того, кому хочешь перевести.")
    try:
        amount = int(msg.text.split()[1])
    except:
        return await msg.reply("Укажи сумму: !перевод 10")
    
    sender = msg.from_user.id
    receiver = msg.reply_to_message.from_user.id
    
    if sender == receiver:
        return await msg.reply("Себе нельзя.")
    if balances.get(sender, 0) < amount:
        return await msg.reply("Мало шоколадок.")
        
    balances[sender] -= amount
    balances[receiver] = balances.get(receiver, 0) + amount
    await msg.reply(f"✅ Переведено {amount} 🍫 пользователю {msg.reply_to_message.from_user.first_name}.")

@router.message(F.text.startswith("!варн"))
async def warn_cmd(msg: Message):
    if not msg.reply_to_message:
        return await msg.reply("Ответь на сообщение нарушителя.")
    
    user_id = msg.reply_to_message.from_user.id
    warns[user_id] = warns.get(user_id, 0) + 1
    await msg.reply(f"⚠️ Варн. Всего: {warns[user_id]}/3")

    if warns[user_id] >= 3:
        try:
            await msg.bot.ban_chat_member(msg.chat.id, user_id)
            await msg.reply("🚫 Забанен.")
        except:
            await msg.reply("Не удалось забанить. Проверь права.")

# --- Веб-сервер для Render ---
async def handle_ping(request):
    return web.Response(text="OK")

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
