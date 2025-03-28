"""Главный файл приложения"""

import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient, events
from textual.app import App
from rich.console import Console
from src.screens import AuthScreen, ChatScreen

# Настройка консоли для корректной работы с Unicode
"""
console = Console(force_terminal=True, color_system="auto")
sys.stdout = console
"""
# спойлер: не помогло

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
    TITLE = "Telegram TUI"

    def __init__(self):
        super().__init__()

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

if __name__ == "__main__":
    raise Exception("Запущен не тот файл. Запустите main.py.")
