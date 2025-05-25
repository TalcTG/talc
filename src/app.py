"""Главный файл приложения"""

from os import getenv
from dotenv import load_dotenv
from telethon import TelegramClient
from textual.app import App
from src.screens import AuthScreen, ChatScreen
import src.locales

load_dotenv()
API_ID = getenv("API_ID")
API_HASH = getenv("API_HASH")

if not API_ID or not API_HASH:
    raise ValueError(
        "API_ID и API_HASH не найдены в .env файле. "
        "Пожалуйста, скопируйте .env.example в .env и заполните свои ключи."
    )

API_ID = int(API_ID)

#locale = locales.

class Talc(App):
    """Класс приложения"""

    CSS_PATH = "style.tcss"

    async def on_mount(self) -> None:
        self.telegram_client = TelegramClient(getenv("CURRENT_USER"), API_ID, API_HASH)
        await self.telegram_client.connect()

        chat_screen = ChatScreen(telegram_client=self.telegram_client)
        self.install_screen(chat_screen, name="chats")

        if not await self.telegram_client.is_user_authorized():
            auth_screen = AuthScreen(telegram_client=self.telegram_client)
            self.install_screen(auth_screen, name="auth")
            self.push_screen("auth")
        else:
            self.push_screen("chats")

        self.scroll_sensitivity_y = 1.0

    async def on_exit_app(self):
        await self.telegram_client.disconnect()
        return super()._on_exit_app()
