"""Файл с кастомными экранами приложения"""

from textual.screen import Screen
from textual.widgets import Label, Input, Footer, Static, ContentSwitcher
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.events import Key
from telethon.errors import SessionPasswordNeededError
from telethon import TelegramClient, events
from src.widgets import Dialog, Chat, normalize_text
from textual import log
from textual.keys import Keys, _character_to_key

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
            yield Label(normalize_text("Добро пожаловать в Telegram TUI"))
            yield Input(placeholder=normalize_text("Номер телефона"), id="phone")
            yield Input(placeholder=normalize_text("Код"), id="code", disabled=True)
            yield Input(
                placeholder=normalize_text("Пароль"), 
                id="password", 
                password=True, 
                disabled=True
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "phone":
            self.phone = normalize_text(event.value)
            self.ac.query_one("#phone").disabled = True
            self.ac.query_one("#code").disabled = False
            await self.client.send_code_request(phone=self.phone)
        elif event.input.id == "code":
            try:
                self.code = normalize_text(event.value)
                self.ac.query_one("#code").disabled = True
                await self.client.sign_in(phone=self.phone, code=self.code)
                self.app.pop_screen()
                self.app.push_screen("chats")
            except SessionPasswordNeededError:
                self.ac.query_one("#code").disabled = True
                self.ac.query_one("#password").disabled = False
        elif event.input.id == "password":
            self.password = normalize_text(event.value)
            await self.client.sign_in(password=self.password)
            await self.client.start()
            self.app.pop_screen()
            self.app.push_screen("chats")

class ChatScreen(Screen):
    """Класс экрана чатов, он же основной экран приложения"""
    
    BINDINGS = [
        (Keys.Tab, "log(\"Нажат таб\")", "Переключение фокуса"),
        (Keys.Enter, "log(\"Нажат энтер\")", "Открыть"),
        (Keys.Escape, "log(\"Нажат эскейп\")", "Назад"),
        (_character_to_key("/"), "log(\"Нажат слэш\")", "Поиск")
    ]

    def __init__(
            self, 
            name = None, 
            id = None, 
            classes = None, 
            telegram_client: TelegramClient | None = None
    ):
        super().__init__(name, id, classes)
        self.telegram_client = telegram_client
        self.search_query = ""
        self.selected_chat_index = 0
        self.chats = []
        self.focused_element = "search"  # search, chat_list, dialog

    async def on_mount(self):
        self.limit = 100

        self.chat_container = self\
            .query_one("#main_container")\
            .query_one("#chats")\
            .query_one("#chat_container")
        
        self.search_input = self.query_one("#search_input")

        log("Первоначальная загрузка виджетов чатов...")
        self.mount_chats(
            len(
                await self.telegram_client.get_dialogs(
                    limit=self.limit, archived=False
                )
            )
        )
        log("Первоначальная загрузка виджетов чата завершена")

        self.is_chat_update_blocked = False
        await self.update_chat_list()

        log("Первоначальная загрузка чатов завершена")

        for event in (
            events.NewMessage, 
            events.MessageDeleted, 
            events.MessageEdited
        ):
            self.telegram_client.on(event())(self.update_chat_list)

    def mount_chats(self, limit: int):
        log("Загрузка виджетов чатов...")

        chats_amount = len(self.chat_container.query(Chat))

        if limit > chats_amount:
            for i in range(limit - chats_amount):
                chat = Chat(id=f"chat-{i + chats_amount + 1}")
                self.chat_container.mount(chat)
        elif limit < chats_amount:
            for i in range(chats_amount - limit):
                self.chat_container.query(Chat).last().remove()
        
        log("Виджеты чатов загружены")

    async def update_chat_list(self, event = None):
        log("Запрос обновления чатов")

        if not self.is_chat_update_blocked:
            self.is_chat_update_blocked = True

            dialogs = await self.telegram_client.get_dialogs(
                limit=self.limit, archived=False
            )
            log("Получены диалоги")

            # Фильтруем диалоги по поисковому запросу
            if self.search_query:
                dialogs = [
                    d for d in dialogs 
                    if self.search_query.lower() in \
                        normalize_text(d.name).lower()
                ]

            limit = len(dialogs)
            self.mount_chats(limit)

            for i in range(limit):
                chat = self.chat_container.query_one(f"#chat-{i + 1}")
                chat.username = normalize_text(str(dialogs[i].name))
                chat.msg = normalize_text(str(dialogs[i].message.message))
                chat.peer_id = dialogs[i].id
                chat.is_selected = (i == self.selected_chat_index)
                chat.is_focused = (self.focused_element == "chat_list" and \
                                   i == self.selected_chat_index)

            self.is_chat_update_blocked = False
            log("Чаты обновлены")
        else:
            log("Обновление чатов невозможно: уже выполняется")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search_input":
            self.search_query = normalize_text(event.value)
            self.selected_chat_index = 0
            self.update_chat_list()

    def on_key(self, event: Key) -> None:
        if event.key == Keys.Tab:
            # Переключаем фокус между элементами
            if self.focused_element == "search":
                self.focused_element = "chat_list"
                self.search_input.blur()
                self.update_chat_list()
            elif self.focused_element == "chat_list":
                self.focused_element = "search"
                self.search_input.focus()
                self.update_chat_list()
            return

        if self.focused_element == "search":
            return

        chats = self.chat_container.query(Chat)
        if not chats:
            return

        match event.key:
            case Keys.Up:
                self.selected_chat_index = max(0, self.selected_chat_index - 1)
                for i, chat in enumerate(chats):
                    chat.is_selected = (i == self.selected_chat_index)
                    chat.is_focused = (i == self.selected_chat_index)
                # Прокручиваем к выбранному чату
                selected_chat = chats[self.selected_chat_index]
                self.chat_container.scroll_to(selected_chat, animate=False)
            case Keys.Down:
                self.selected_chat_index = min(len(chats) - 1, self.selected_chat_index + 1)
                for i, chat in enumerate(chats):
                    chat.is_selected = (i == self.selected_chat_index)
                    chat.is_focused = (i == self.selected_chat_index)
                # Прокручиваем к выбранному чату
                selected_chat = chats[self.selected_chat_index]
                self.chat_container.scroll_to(selected_chat, animate=False)
            case Keys.Enter:
                chats[self.selected_chat_index].on_click()
            case Keys.Escape:
                # Возвращаемся к списку чатов
                self.app.pop_screen()
                self.app.push_screen("chats")
            case "/": #Не работает: нужен кейкод слэша
                # Фокус на поиск
                self.focused_element = "search"
                self.search_input.focus()
                self.update_chat_list()

    def compose(self):
        yield Footer()
        with Horizontal(id="main_container"):
            with Vertical(id="chats"):
                yield Input(placeholder=normalize_text("Поиск чатов..."), id="search_input")
                yield VerticalScroll(id="chat_container")
            yield ContentSwitcher(id="dialog_switcher")
                #yield Dialog(telegram_client=self.telegram_client)

if __name__ == "__main__":
    raise Exception("Запущен не тот файл. Запустите main.py.")
