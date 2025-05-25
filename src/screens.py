"""Файл с кастомными экранами приложения"""

from textual.screen import Screen
from textual.widgets import Label, Input, Footer, Static, ContentSwitcher
from textual.containers import Vertical, Horizontal, VerticalScroll
from telethon.errors import SessionPasswordNeededError
from telethon import TelegramClient, events
from src.widgets import Dialog, Chat

class AuthScreen(Screen):
    """Класс экрана логина в аккаунт"""

    def __init__(
            self, 
            name = None, 
            id = None, 
            classes = None, 
            telegram_client: TelegramClient | None = None
    ):
        super().__init__(name, id, classes)
        self.client = telegram_client

    def on_mount(self):
        self.ac = self.query_one("#auth_container")

    def compose(self):
        with Vertical(id="auth_container"):
            yield Label("Добро пожаловать в Telegram TUI")
            yield Input(placeholder="Номер телефона", id="phone")
            yield Input(placeholder="Код", id="code", disabled=True)
            yield Input(
                placeholder="Пароль", 
                id="password", 
                password=True, 
                disabled=True
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "phone":
            self.phone = event.value
            self.ac.query_one("#phone").disabled = True
            self.ac.query_one("#code").disabled = False
            await self.client.send_code_request(phone=self.phone)
        elif event.input.id == "code":
            try:
                self.code = event.value
                self.ac.query_one("#code").disabled = True
                await self.client.sign_in(phone=self.phone, code=self.code)
                self.app.pop_screen()
                self.app.push_screen("chats")
            except SessionPasswordNeededError:
                self.ac.query_one("#code").disabled = True
                self.ac.query_one("#password").disabled = False
        elif event.input.id == "password":
            self.password = event.value
            await self.client.sign_in(password=self.password)
            await self.client.start()
            self.app.pop_screen()
            self.app.push_screen("chats")

class ChatScreen(Screen):
    """Класс экрана чатов, он же основной экран приложения"""

    def __init__(
            self, 
            name = None, 
            id = None, 
            classes = None, 
            telegram_client: TelegramClient | None = None
    ):
        super().__init__(name, id, classes)
        self.telegram_client = telegram_client

    async def on_mount(self):
        self.limit = 100

        self.chat_container = self\
            .query_one("#main_container")\
            .query_one("#chats")\
            .query_one("#chat_container")

        print("Первоначальная загрузка виджетов чатов...")
        self.mount_chats(
            len(
                await self.telegram_client.get_dialogs(
                    limit=self.limit, archived=False
                )
            )
        )
        print("Первоначальная загрузка виджетов чата завершена")

        self.is_chat_update_blocked = False
        await self.update_chat_list()

        print("Первоначальная загрузка чатов завершена")

        for event in (
            events.NewMessage, 
            events.MessageDeleted, 
            events.MessageEdited
        ):
            self.telegram_client.on(event())(self.update_chat_list)

    def mount_chats(self, limit: int):
        print("Загрузка виджетов чатов...")

        chats_amount = len(self.chat_container.query(Chat))

        if limit > chats_amount:
            for i in range(limit - chats_amount):
                chat = Chat(id=f"chat-{i + chats_amount + 1}")
                self.chat_container.mount(chat)
        elif limit < chats_amount:
            for i in range(chats_amount - limit):
                self.chat_container.query(Chat).last().remove()
        
        print("Виджеты чатов загружены")

    async def update_chat_list(self, event = None):
        print("Запрос обновления чатов")

        if not self.is_chat_update_blocked:
            self.is_chat_update_blocked = True

            dialogs = await self.telegram_client.get_dialogs(
                limit=self.limit, archived=False
            )
            print("Получены диалоги")

            limit = len(dialogs)
            self.mount_chats(limit)

            for i in range(limit):
                chat = self.chat_container.query_one(f"#chat-{i + 1}")
                chat.username = str(dialogs[i].name)
                chat.msg = str(dialogs[i].message.message)
                chat.peer_id = dialogs[i].id

            self.is_chat_update_blocked = False
            print("Чаты обновлены")
        else:
            print("Обновление чатов невозможно: уже выполняется")

    def compose(self):
        yield Footer()
        with Horizontal(id="main_container"):
            with Horizontal(id="chats"):
                yield VerticalScroll(id="chat_container")
                #TODO: сделать кнопку чтобы прогрузить больше чатов
            yield ContentSwitcher(id="dialog_switcher")
                #yield Dialog(telegram_client=self.telegram_client)
