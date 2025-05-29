"""Файл с кастомными виджетами приложения"""

from textual.containers import Horizontal, Vertical, Container, VerticalScroll
from textual.widget import Widget
from textual.reactive import reactive
from textual.widgets import Input, Button, Label, Static, ContentSwitcher
from textual.app import ComposeResult, RenderResult
from textual.content import Content
from textual.style import Style
from telethon import TelegramClient, events, utils, types

class Chat(Widget):
    """Класс виджета чата для панели чатов"""

    username: reactive[str] = reactive(" ", recompose=True)
    peername: reactive[str] = reactive(" ", recompose=True)
    msg: reactive[str] = reactive(" ", recompose=True)
    is_group: reactive[bool] = reactive(False, recompose=True)
    is_channel: reactive[bool] = reactive(False)
    peer_id: reactive[int] = reactive(0)

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
        self.switcher = self.screen.query_one(Horizontal)\
            .query_one("#dialog_switcher", ContentSwitcher)
        
        if int(self.id[5:]) % 2 != 0:
            self.add_class("odd")
        else:
            self.add_class("even")
    
    def on_click(self) -> None:
        # Получение ID диалога и создание DOM-ID на его основе
        dialog_id = f"dialog-{str(self.peer_id)}"

        # Маунт диалога
        try:
            self.switcher.mount(Dialog(
                telegram_client=self.app.telegram_client, 
                chat_id=self.peer_id, 
                id=dialog_id,
                is_channel=self.is_channel and not self.is_group
            ))
        except:
            # Диалог уже есть: ничего не делаем
            pass

        self.switcher.current = dialog_id
        self.switcher.recompose()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(self.peername[:1], classes="avatar")
            with Vertical():
                yield Label(self.peername, id="peername", markup=False)
                if self.is_group:
                    yield Label(self.username, id="name", markup=False)
                yield Label(self.msg, id="last_msg", markup=False)

class Dialog(Widget):
    """Класс окна диалога"""
    
    def __init__(
            self, 
            id=None, 
            classes=None, 
            disabled=None, 
            telegram_client: TelegramClient | None = None,
            chat_id: int | None = None,
            is_channel: bool | None = None
    ) -> None:
        super().__init__(id=id, classes=classes, disabled=disabled)
        self.telegram_client = telegram_client
        self.chat_id = chat_id
        self.is_msg_update_blocked = False
        self.timezone = self.app.timezone
        self.is_channel = is_channel

    async def on_mount(self) -> None:
        self.limit = int(self.app.MESSAGES_LIMIT)

        if not self.is_channel:
            self.msg_input = self.query_one("#msg_input")
        self.dialog = self.query_one(Vertical).query_one("#dialog")
        self.top_bar = self.query_one(Vertical).query_one(TopBar)
        self.switcher = self.screen.query_one(Horizontal)\
            .query_one("#dialog_switcher", ContentSwitcher)

        self.me = await self.telegram_client.get_me()

        await self.update_dialog()

        #self.dialog.scroll_down(animate=False, immediate=True)

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

        if not self.is_msg_update_blocked and self.switcher.current == self.id:
            self.is_msg_update_blocked = True

            messages = await self.telegram_client.get_messages(
                entity=self.chat_id, limit=self.limit
            )
            print("Получены сообщения")

            limit = len(messages)
            self.mount_messages(limit)

            for i in range(limit):
                msg = self.dialog.query_one(f"#msg-{i + 1}")
                message = Content(str(messages[i].message))
                if str(messages[i].message):
                    entities = messages[i].entities
                    if entities:
                        for entity in entities:
                            match type(entity):
                                case types.MessageEntityBold:
                                    message = message.stylize(
                                        "bold", 
                                        entity.offset, 
                                        entity.offset + entity.length
                                    )
                                case types.MessageEntityUnderline:
                                    message = message.stylize(
                                        "underline", 
                                        entity.offset, 
                                        entity.offset + entity.length
                                    )
                                case types.MessageEntityItalic:
                                    message = message.stylize(
                                        "italic", 
                                        entity.offset, 
                                        entity.offset + entity.length
                                    )
                                case types.MessageEntityStrike:
                                    message = message.stylize(
                                        "strike", 
                                        entity.offset, 
                                        entity.offset + entity.length
                                    )

                if messages[i].media and str(message):
                    msg.message = Content(f"[{self.app.locale["media"]}] ")\
                        .stylize("link", 0, 6) + message
                elif messages[i].media:
                    msg.message = Content(f"[{self.app.locale["media"]}]")\
                        .stylize("link", 0, 6)
                else:
                    msg.message = message
                
                try:
                    is_me = messages[i].from_id.user_id == self.me.id
                except:
                    is_me = False
                
                msg.is_me = is_me
                msg.username = utils.get_display_name(messages[i].sender)
                msg.info = messages[i]\
                    .date\
                    .astimezone(self.timezone)\
                    .strftime("%H:%M")
                
            self.top_bar.peername = utils.get_display_name(
                await self.telegram_client.get_entity(self.chat_id)
            )

            self.is_msg_update_blocked = False
            print("Сообщения обновлены")
        else:
            print("Обновление сообщений невозможно: уже выполняется")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield TopBar()
            yield VerticalScroll(id="dialog")
            if not self.is_channel:
                with Horizontal(id="input_place"):
                    yield Input(
                        placeholder=self.app.locale["message"], 
                        id="msg_input"
                    )
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
            print("Ошибка отправки")
        self.msg_input.value = ""
        await self.update_dialog()

class Message(Widget):
    """Класс виджета сообщений для окна диалога"""

    message: reactive[Content] = reactive("", recompose=True)
    is_me: reactive[bool] = reactive(False, recompose=True)
    username: reactive[str] = reactive("", recompose=True)
    info: reactive[str] = reactive("", recompose=True)
    
    def __init__(self, id=None) -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        label = Label(self.message, markup=False)
        label.border_title = self.username * (not self.is_me)
        label.border_subtitle = self.info
        
        with Container():
            yield label
        
        if self.is_me:
            self.classes = "is_me_true"
        else:
            self.classes = "is_me_false"

class TopBar(Widget):
    """Класс виджета верхней панели для окна диалога"""

    peername: reactive[str] = reactive(" ", recompose=True)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(self.peername[:1], classes="avatar")
            yield Label(self.peername, classes="peername_top_bar")
