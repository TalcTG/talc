"""Файл с кастомными виджетами приложения"""

from textual.containers import Horizontal, Vertical, Container, VerticalScroll
from textual.widget import Widget
from textual.reactive import Reactive
from textual.widgets import Input, Button, Label, Static, ContentSwitcher
from textual.app import ComposeResult, RenderResult
from telethon import TelegramClient, events, utils
import datetime

class Chat(Widget):
    """Класс виджета чата для панели чатов"""

    username: Reactive[str] = Reactive(" ", recompose=True)
    msg: Reactive[str] = Reactive(" ", recompose=True)
    peer_id: Reactive[int] = Reactive(0)

    def __init__(
            self, 
            name: str | None = None, 
            id: str | None = None, 
            classes: str | None = None, 
            disabled: bool = False
    ) -> None:
        super().__init__(
            name=str(name), 
            id=id, 
            classes=classes, 
            disabled=disabled
        )
        
    def on_mount(self) -> None:
        self.switcher = self.screen.query_one(Horizontal).query_one("#dialog_switcher", ContentSwitcher)
    
    def on_click(self) -> None:
        dialog_id = f"dialog-{str(self.peer_id)}"
        print("click 1")
        try:
            self.switcher.mount(Dialog(
                telegram_client=self.app.telegram_client, 
                chat_id=self.peer_id, 
                id=dialog_id
            ))
            print("click 1.1")
        except:
            print("click 1.2")
        print("click 2")
        self.switcher.current = dialog_id
        self.switcher.recompose()
        print("click 3")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(f"┌───┐\n│ {self.username[:1]:1} │\n└───┘")
            with Vertical():
                yield Label(self.username, id="name")
                yield Label(self.msg, id="last_msg")

class Dialog(Widget):
    """Класс окна диалога"""
    
    def __init__(
            self, 
            id=None, 
            classes=None, 
            disabled=None, 
            telegram_client: TelegramClient | None = None,
            chat_id = None
        ) -> None:
        super().__init__(id=id, classes=classes, disabled=disabled)
        self.telegram_client = telegram_client
        self.chat_id = chat_id
        self.is_msg_update_blocked = False

    async def on_mount(self) -> None:
        self.limit = 10

        self.msg_input = self.query_one("#msg_input")
        self.dialog = self.query_one(Vertical).query_one("#dialog")

        self.me = await self.telegram_client.get_me()

        self.dialog.scroll_end(animate=False)
        await self.update_dialog()

        for event in (
            events.NewMessage, 
            events.MessageDeleted, 
            events.MessageEdited
        ):
            self.telegram_client.on(
                event(chats=(self.chat_id))
            )(self.update_dialog)

    def mount_messages(self, limit: int) -> None:
        print("Загрузка виджетов сообщений...")

        msg_amount = len(self.dialog.query(Message))

        if limit > msg_amount:
            for i in range(limit - msg_amount):
                self.dialog.mount(
                    Message(id=f"msg-{i + msg_amount + 1}"), 
                    before=0
                )
        elif limit < msg_amount:
            for i in range(msg_amount - limit):
                self.dialog.query(Message).last().remove()

    async def update_dialog(self, event = None) -> None:
        print("Запрос обновления сообщений")

        if not self.is_msg_update_blocked:
            self.is_msg_update_blocked = True

            messages = await self.telegram_client.get_messages(
                entity=self.chat_id, limit=self.limit
            )
            print("Получены сообщения")

            limit = len(messages)
            self.mount_messages(limit)

            for i in range(limit):
                msg = self.dialog.query_one(f"#msg-{i + 1}")
                msg.message = ""
                if str(messages[i].message):
                    msg.message = str(messages[i].message)
                
                #TODO: завести это:
                try:
                    is_me = messages[i].from_id.user_id == self.me.id
                except:
                    is_me = False
                
                msg.is_me = is_me
                msg.username = utils.get_display_name(messages[i].sender)
                msg.send_time = messages[i]\
                    .date\
                    .astimezone(datetime.timezone.utc)\
                    .strftime("%H:%M")

            self.is_msg_update_blocked = False
            print("Сообщения обновлены")
        else:
            print("Обновление сообщений невозможно: уже выполняется")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield VerticalScroll(id="dialog")
            with Horizontal(id="input_place"):
                yield Input(placeholder="Сообщение", id="msg_input")
                yield Button(label="➤", id="send", variant="primary")

    async def on_button_pressed(self, event = None) -> None:
        await self.send_message()
    
    async def on_input_submitted(self, event = None) -> None:
        await self.send_message()

    async def send_message(self) -> None:
        try:
            await self.telegram_client.send_message(
                self.chat_id, 
                str(self.msg_input.value)
            )
        except ValueError:
            self.app.notify("Ошибка отправки")
        self.msg_input.value = ""
        await self.update_dialog()

class Message(Widget):
    """Класс виджета сообщений для окна диалога"""

    message: Reactive[str] = Reactive("", recompose=True)
    is_me: Reactive[bool] = Reactive(False, recompose=True)
    username: Reactive[str] = Reactive("", recompose=True)
    send_time: Reactive[str] = Reactive("", recompose=True)
    
    def __init__(
            self, 
            name=None, 
            id=None, 
            classes=None, 
            disabled=False
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)

    def on_mount(self) -> None:
        pass

    def compose(self) -> ComposeResult:
        static = Static(self.message)
        static.border_title = self.username * (not self.is_me)
        static.border_subtitle = self.send_time
        
        with Container():
            yield static
        
        if self.is_me:
            self.classes = "is_me_true"
        else:
            self.classes = "is_me_false"
