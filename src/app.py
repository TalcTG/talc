"""Файл с основным классом приложения"""

from textual.app import App
from textual.binding import Binding
from telethon import TelegramClient
import os
import asyncio
from src.screens import AuthScreen, ChatScreen
from textual import log
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Проверяем наличие API ключей
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if not api_id or not api_hash:
    raise ValueError(
        "API_ID и API_HASH не найдены в .env файле. "
        "Пожалуйста, скопируйте .env.example в .env и заполните свои ключи."
    )

# Преобразуем API_ID в число
api_id = int(api_id)

class TelegramTUI(App):
    """Класс основного приложения"""

    BINDINGS = [
        Binding("ctrl+c,ctrl+q", "quit", "Выход", show=True),
    ]

    CSS_PATH = "style.tcss"
    TITLE = "Telegram TUI"

    def __init__(
            self,
            driver_class=None,
            css_path=None,
            watch_css=False
    ):
        super().__init__(
            driver_class=driver_class,
            css_path=css_path,
            watch_css=watch_css
        )
        
        # Инициализируем клиент Telegram
        session_file = "talc.session"
        
        # Если сессия существует и заблокирована, удаляем её
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                log("Старая сессия удалена")
            except Exception as e:
                log(f"Ошибка удаления сессии: {e}")
        
        self.telegram_client = TelegramClient(
            session_file,
            api_id=api_id,
            api_hash=api_hash,
            system_version="macOS 14.3.1",
            device_model="MacBook",
            app_version="1.0"
        )

    async def on_mount(self) -> None:
        """Действия при запуске приложения"""
        try:
            # Подключаемся к Telegram
            await self.telegram_client.connect()
            log("Подключено к Telegram")
            
            # Устанавливаем экраны
            chat_screen = ChatScreen(telegram_client=self.telegram_client)
            self.install_screen(chat_screen, name="chats")
            
            auth_screen = AuthScreen(telegram_client=self.telegram_client)
            self.install_screen(auth_screen, name="auth")
            
            # Проверяем авторизацию и показываем нужный экран
            if await self.telegram_client.is_user_authorized():
                await self.push_screen("chats")
            else:
                await self.push_screen("auth")
                
        except Exception as e:
            log(f"Ошибка при запуске: {e}")
            self.exit()

    async def on_unmount(self) -> None:
        """Действия при закрытии приложения"""
        try:
            if self.telegram_client and self.telegram_client.is_connected():
                await self.telegram_client.disconnect()
                log("Отключено от Telegram")
        except Exception as e:
            log(f"Ошибка при закрытии: {e}")

    async def action_quit(self) -> None:
        """Действие при выходе из приложения"""
        try:
            if self.telegram_client and self.telegram_client.is_connected():
                await self.telegram_client.disconnect()
                log("Отключено от Telegram")
        except Exception as e:
            log(f"Ошибка при выходе: {e}")
        self.exit()
