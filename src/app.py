"""Главный файл приложения"""

from os import getenv
from dotenv import load_dotenv
from telethon import TelegramClient
from textual.app import App
from textual.keys import Keys, _character_to_key
from datetime import timezone, timedelta
from src.screens import AuthScreen, ChatScreen
import src.locales

load_dotenv()
API_ID = getenv("API_ID")
API_HASH = getenv("API_HASH")
LANGUAGE = getenv("LANGUAGE")
UTC_OFFSET = getenv("UTC_OFFSET")

if "" in [API_ID, API_HASH, LANGUAGE, UTC_OFFSET]:
    raise ValueError(
        "Недостаточно параметров в .env файле."
        "Скопируйте .env.example в .env и заполните свои API-ключи."
        "Not enough settings in .env file."
        "Copy .env.example into .env and fill your API-keys."
    )

API_ID = int(API_ID)
locale = dict(zip(
    getattr(src.locales, "codes"), getattr(src.locales, LANGUAGE)
))

class Talc(App):
    """Класс приложения"""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        (Keys.ControlE, "notify(\"Нажата кнопка профиля\")", locale["you"]),
        (Keys.ControlF, "notify(\"Нажата кнопка папок\")", locale["folders"]),
        (Keys.Tab, "notify(\"Нажат таб\")", locale["switch_focus"]),
        (Keys.Enter, "notify(\"Нажат энтер\")", locale["enter"]),
        (Keys.Escape, "notify(\"Нажат эскейп\")", locale["back"]),
        (_character_to_key("/"), "notify(\"Нажат слэш\")", locale["search"])
    ]

    def __init__(
        self, 
        driver_class = None, 
        css_path = None, 
        watch_css = False, 
        ansi_color = False
    ):
        super().__init__(driver_class, css_path, watch_css, ansi_color)
        self.locale = locale
        self.timezone = timezone(timedelta(hours=int(UTC_OFFSET)))

    async def on_mount(self) -> None:
        self.telegram_client = TelegramClient(
            getenv("CURRENT_USER"), 
            API_ID, 
            API_HASH
        )
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
