"""Файл с кастомными экранами приложения"""

from textual.screen import Screen
from textual.widgets import Label, Input, Footer, Static, ContentSwitcher
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.app import ComposeResult
from telethon.errors import SessionPasswordNeededError
from telethon import TelegramClient, events
from src.widgets import Chat
from os import system, getenv
from telethon.utils import get_display_name

class AuthScreen(Screen):
    """Класс экрана логина в аккаунт"""

    def __init__(
            self, 
            name = None, 
            id = None, 
            classes = None, 
            telegram_client: TelegramClient | None = None
    ) -> None:
        super().__init__(name, id, classes)
        self.client = telegram_client
        self.locale = self.app.locale

    def on_mount(self) -> None:
        self.ac = self.query_one("#auth_container")

    def compose(self) -> ComposeResult:
        with Vertical(id="auth_container"):
            yield Label(self.locale["auth_greeting"])
            yield Input(
                placeholder=self.locale["phone_number"], 
                id="phone"
            )
            yield Input(
                placeholder=self.locale["code"], 
                id="code", 
                disabled=True
            )
            yield Input(
                placeholder=self.locale["password"], 
                id="password", 
                password=True, 
                disabled=True
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        match event.input.id:
            case "phone":
                self.phone = event.value
                self.ac.query_one("#phone").disabled = True
                self.ac.query_one("#code").disabled = False
                await self.client.send_code_request(phone=self.phone)
            case "code":
                try:
                    self.code = event.value
                    self.ac.query_one("#code").disabled = True
                    await self.client.sign_in(phone=self.phone, code=self.code)
                    self.app.pop_screen()
                    self.app.push_screen("chats")
                except SessionPasswordNeededError:
                    self.ac.query_one("#code").disabled = True
                    self.ac.query_one("#password").disabled = False
            case "password":
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
    ) -> None:
        super().__init__(name, id, classes)
        self.telegram_client = telegram_client
        self.DO_NOTIFY = getenv("DO_NOTIFY")
        self.locale = self.app.locale

    async def on_mount(self) -> None:
        self.limit = int(self.app.CHATS_LIMIT)
        
        # Получение ID пользователя (себя)
        self.me_id = await self.telegram_client.get_peer_id("me")
        # Получение объекта контейнера чатов
        self.chat_container = self\
            .query_one("#main_container")\
            .query_one("#chats")\
            .query_one("#chat_container")
        self.switcher = self.screen.query_one(Horizontal)\
            .query_one("#dialog_switcher", ContentSwitcher)

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

        # Автообновление чатов при следующих событиях
        for event in (
            events.NewMessage, 
            events.MessageDeleted, 
            events.MessageEdited
        ):
            self.telegram_client.on(event())(self.update_chat_list)
        self.telegram_client.on(events.NewMessage)(self.notify_send)

    def mount_chats(self, limit: int) -> None:
        """Функция маунта чатов"""
        print("Загрузка виджетов чатов...")

        # Счёт текущего количества примонтированных чатов
        chats_amount = len(self.chat_container.query(Chat))

        if limit > chats_amount:
            # Маунт недостающих, если чатов меньше, чем нужно
            for i in range(limit - chats_amount):
                chat = Chat(id=f"chat-{i + chats_amount + 1}")
                self.chat_container.mount(chat)
        elif limit < chats_amount:
            # Удаление лишних, если чатов больше, чем нужно
            for i in range(chats_amount - limit):
                self.chat_container.query(Chat).last().remove()
        # Ничего, если их ровно столько же
        
        print("Виджеты чатов загружены")

    async def update_chat_list(self, event = None) -> None:
        """Функция обновления чатов (и уведомления)"""
        print("Запрос обновления чатов")

        if not self.is_chat_update_blocked:
            self.is_chat_update_blocked = True

            dialogs = await self.telegram_client.get_dialogs(
                limit=self.limit, archived=False
            )
            print("Получены диалоги")

            # Маунт виджетов чатов в панели чатов по лимиту
            limit = len(dialogs)
            self.mount_chats(limit)

            # Изменение надписей в виджетах чатов
            for i in range(limit):
                chat = self.chat_container.query_one(f"#chat-{i + 1}")

                chat.peername = str(dialogs[i].name)
                chat.is_group = dialogs[i].is_group
                chat.is_channel = dialogs[i].is_channel
                chat.peer_id = dialogs[i].id

                try:
                    is_my_msg = \
                        dialogs[i].message.from_id.user_id == self.me_id
                except:
                    is_my_msg = dialogs[i].id == self.me_id

                if dialogs[i].is_group and is_my_msg:
                    chat.username = self.locale["you"]
                    chat.msg = str(dialogs[i].message.message)
                elif dialogs[i].is_group:
                    chat.username = str(
                        get_display_name(dialogs[i].message.sender)
                    )
                    chat.msg = str(dialogs[i].message.message)
                elif is_my_msg:
                    chat.msg = f"{self.locale["you"]}: " * is_my_msg + str(
                        dialogs[i].message.message
                    )
                else:
                    chat.msg = str(dialogs[i].message.message)

                if self.switcher.current is not None:
                    current_dialog = \
                        self.switcher.query_one(f"#{self.switcher.current}")
                    if chat.peer_id == int(current_dialog.id[7:]):
                        chat.add_class("selected_chat")
                    else:
                        chat.remove_class("selected_chat")

            self.is_chat_update_blocked = False
            print("Чаты обновлены")
        else:
            print("Обновление чатов невозможно: уже выполняется")

        if self.switcher.current is not None:
            current_dialog = \
                self.switcher.query_one(f"#{self.switcher.current}")
            await current_dialog.update_dialog()

    def notify_send(self, event) -> None:
        if not event:
            return None
        if int(self.DO_NOTIFY) and not self.app.focused and event.mentioned:
            system(f"notify-send \"{self.locale["mention"]}\" Talc")

    def compose(self) -> ComposeResult:
        yield Footer() # Нижняя панель с подсказками
        with Horizontal(id="main_container"): # Основной контейнер
            with Horizontal(id="chats"):
                yield VerticalScroll(id="chat_container")
                #TODO: сделать кнопку, чтобы прогрузить больше чатов,
                # или ленивую прокрутку
            yield ContentSwitcher(id="dialog_switcher")
                # ↑ Внутри него как раз крутятся диалоги
                #yield Label(
                #    self.locale["start_converse"],
                #    id="start_converse_label"
                #) #TODO: не показывается надпись, надо будет исправить
