"""Главный файл приложения"""

import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from textual.app import App
from src.screens import AuthScreen, ChatScreen

load_dotenv()

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if not api_id or not api_hash:
    raise ValueError(
        "API_ID и API_HASH не найдены в .env файле. "
        "Пожалуйста, скопируйте .env.example в .env и заполните свои ключи."
    )

api_id = int(api_id)

class TelegramTUI(App):
    """Класс приложения"""

    CSS_PATH = "style.tcss"

    async def on_mount(self) -> None:
        self.telegram_client = TelegramClient("user", api_id, api_hash)
        await self.telegram_client.connect()

        chat_screen = ChatScreen(telegram_client=self.telegram_client)
        self.install_screen(chat_screen, name="chats")

        if not await self.telegram_client.is_user_authorized():
            auth_screen = AuthScreen(telegram_client=self.telegram_client)
            self.install_screen(auth_screen, name="auth")
            self.push_screen("auth")
        else:
            self.push_screen("chats")

    async def on_exit_app(self):
        await self.telegram_client.disconnect()
        return super()._on_exit_app()
