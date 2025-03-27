"""Файл с кастомными виджетами приложения"""

from textual.containers import Horizontal, Vertical, Container, VerticalScroll
from textual.widget import Widget
from textual.reactive import Reactive
from textual.widgets import Input, Button, Label, Static, ContentSwitcher
from textual.app import ComposeResult, RenderResult
from textual.keys import Keys
from telethon import TelegramClient, events, utils
import datetime
import unicodedata
import re
import emoji
import os
import tempfile
from PIL import Image
import pywhatkit as kit
from textual import log

def remove_emoji(text: str) -> str:
    """Удаляет эмодзи из текста"""
    if not text:
        return ""
    return emoji.replace_emoji(text, '')

def normalize_text(text: str) -> str:
    """Нормализует текст для корректного отображения"""
    if not text:
        return ""
    # Удаляем эмодзи
    text = remove_emoji(text)
    # Удаляем все управляющие символы
    text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C')
    # Нормализуем Unicode
    text = unicodedata.normalize('NFKC', text)
    # Заменяем специальные символы на их ASCII-эквиваленты
    text = text.replace('—', '-').replace('–', '-').replace('…', '...')
    # Удаляем все непечатаемые символы
    text = ''.join(char for char in text if char.isprintable())
    return text

def safe_ascii(text: str) -> str:
    """Преобразует текст в безопасный ASCII-формат"""
    if not text:
        return ""
    # Удаляем эмодзи
    text = remove_emoji(text)
    # Оставляем только ASCII символы и пробелы
    return ''.join(char for char in text if ord(char) < 128 or char.isspace())

def convert_image_to_ascii(image_path: str, width: int = 50) -> str:
    """Конвертирует изображение в ASCII-арт"""
    try:
        # Открываем изображение
        img = Image.open(image_path)
        
        # Конвертируем в RGB если нужно
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Изменяем размер, сохраняя пропорции
        aspect_ratio = img.height / img.width
        height = int(width * aspect_ratio * 0.5)  # * 0.5 потому что символы выше чем шире
        img = img.resize((width, height))
        
        # Конвертируем в ASCII
        ascii_str = kit.image_to_ascii_art(image_path, output_file=None)
        
        # Очищаем временный файл
        os.remove(image_path)
        
        return ascii_str
    except Exception as e:
        log(f"Ошибка конвертации изображения: {e}")
        return "Ошибка загрузки изображения"

class Chat(Static):
    """Класс виджета чата для панели чатов"""

    DEFAULT_CSS = """
    Chat {
        width: 100%;
        height: auto;
        min-height: 3;
        padding: 1 2;
        border: solid $accent;
        margin: 1 0;
        background: $surface;
    }
    Chat:hover {
        background: $accent 20%;
    }
    Chat.-selected {
        background: $accent 30%;
    }
    Chat:focus {
        background: $accent 40%;
        border: double $accent;
    }
    .chat-avatar {
        width: 3;
        height: 3;
        content-align: center middle;
        border: solid $accent;
        margin-right: 1;
    }
    .chat-content {
        width: 100%;
    }
    .chat-name {
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }
    .chat-message {
        color: $text-muted;
    }
    """

    def __init__(
            self, 
            name: str | None = None, 
            id: str | None = None, 
            classes: str | None = None, 
            disabled: bool = False
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.can_focus = True
        self._username = ""
        self._msg = ""
        self._peer_id = 0
        self._is_selected = False
        self._folder = 0

    def on_mount(self) -> None:
        self.switcher = self.screen.query_one("#dialog_switcher", ContentSwitcher)

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        self._username = value
        self.refresh()

    @property
    def msg(self) -> str:
        return self._msg

    @msg.setter
    def msg(self, value: str) -> None:
        self._msg = value
        self.refresh()

    @property
    def peer_id(self) -> int:
        return self._peer_id

    @peer_id.setter
    def peer_id(self, value: int) -> None:
        self._peer_id = value

    @property
    def is_selected(self) -> bool:
        return self._is_selected

    @is_selected.setter
    def is_selected(self, value: bool) -> None:
        self._is_selected = value
        self.set_class(value, "-selected")

    @property
    def folder(self) -> int:
        return self._folder

    @folder.setter
    def folder(self, value: int) -> None:
        self._folder = value
        self.refresh()

    def on_focus(self) -> None:
        # Снимаем выделение со всех чатов
        for chat in self.screen.query(Chat):
            chat.is_selected = False
        
        # Выделяем текущий чат
        self.is_selected = True
        
        # Прокручиваем к этому чату
        self.screen.chat_container.scroll_to(self, animate=False)

    def on_click(self) -> None:
        self.focus()
        
        dialog_id = f"dialog-{str(self.peer_id)}"
        try:
            self.switcher.mount(Dialog(
                telegram_client=self.app.telegram_client, 
                chat_id=self.peer_id, 
                id=dialog_id
            ))
        except Exception as e:
            log(f"Ошибка открытия диалога: {e}")
            return
            
        self.switcher.current = dialog_id

    def on_key(self, event: Keys) -> None:
        if event.key == "enter":
            self.on_click()
        elif event.key == "up" and self.id != "chat-1":
            # Фокусируемся на предыдущем чате
            prev_chat = self.screen.chat_container.query_one(f"#chat-{int(self.id.split('-')[1]) - 1}")
            if prev_chat:
                prev_chat.focus()
        elif event.key == "down":
            # Фокусируемся на следующем чате
            next_chat = self.screen.chat_container.query_one(f"#chat-{int(self.id.split('-')[1]) + 1}")
            if next_chat:
                next_chat.focus()

    def compose(self) -> ComposeResult:
        """Компонуем виджет чата"""
        with Horizontal():
            # Аватар (первая буква имени)
            first_letter = normalize_text(self._username[:1].upper()) or "?"
            yield Static(first_letter, classes="chat-avatar")
            
            # Контент (имя и сообщение)
            with Vertical(classes="chat-content"):
                name = normalize_text(self._username) or "Без названия"
                msg = normalize_text(self._msg) or "Нет сообщений"
                msg = msg[:50] + "..." if len(msg) > 50 else msg
                
                # Добавляем метку папки если нужно
                folder_label = " [Архив]" if self._folder == 1 else ""
                
                yield Static(f"{name}{folder_label}", classes="chat-name")
                yield Static(msg, classes="chat-message")

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
        self.messages_loaded = 0
        self.is_loading = False

    async def on_mount(self) -> None:
        self.limit = 50  # Увеличиваем начальное количество сообщений
        self.messages_loaded = self.limit

        self.msg_input = self.query_one("#msg_input")
        self.dialog = self.query_one(Vertical).query_one("#dialog")
        self.load_more_btn = self.query_one("#load_more")

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
        log("Запрос обновления сообщений")

        if not self.is_msg_update_blocked:
            self.is_msg_update_blocked = True

            messages = await self.telegram_client.get_messages(
                entity=self.chat_id, limit=self.limit
            )
            log("Получены сообщения")

            limit = len(messages)
            self.mount_messages(limit)

            for i in range(limit):
                msg = self.dialog.query_one(f"#msg-{i + 1}")
                msg.message = ""
                
                # Обрабатываем изображения
                if messages[i].media:
                    try:
                        # Скачиваем изображение
                        image_data = await self.telegram_client.download_media(
                            messages[i].media, 
                            bytes
                        )
                        if image_data:
                            await msg.set_image(image_data)
                    except Exception as e:
                        log(f"Ошибка загрузки изображения: {e}")
                
                # Обрабатываем текст
                if str(messages[i].message):
                    msg.message = normalize_text(str(messages[i].message))
                
                try:
                    is_me = messages[i].from_id.user_id == self.me.id
                except:
                    is_me = False
                
                msg.is_me = is_me
                msg.username = normalize_text(utils.get_display_name(messages[i].sender))
                msg.send_time = messages[i]\
                    .date\
                    .astimezone(datetime.timezone.utc)\
                    .strftime("%H:%M")

            self.is_msg_update_blocked = False
            log("Сообщения обновлены")
        else:
            log("Обновление сообщений невозможно: уже выполняется")

    async def load_more_messages(self) -> None:
        if not self.is_loading:
            self.is_loading = True
            self.load_more_btn.disabled = True
            self.load_more_btn.label = "Загрузка..."
            
            try:
                messages = await self.telegram_client.get_messages(
                    entity=self.chat_id,
                    limit=self.limit,
                    offset_id=self.messages_loaded
                )
                
                if messages:
                    self.messages_loaded += len(messages)
                    self.mount_messages(self.messages_loaded)
                    await self.update_dialog()
            finally:
                self.is_loading = False
                self.load_more_btn.disabled = False
                self.load_more_btn.label = "Загрузить еще"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Button("Загрузить еще", id="load_more", variant="default")
            yield VerticalScroll(id="dialog")
            with Horizontal(id="input_place"):
                yield Input(placeholder="Сообщение", id="msg_input")
                yield Button(label=">", id="send", variant="primary")

    async def on_button_pressed(self, event) -> None:
        if event.button.id == "load_more":
            await self.load_more_messages()
        else:
            await self.send_message()
    
    async def on_input_submitted(self, event = None) -> None:
        await self.send_message()

    async def send_message(self) -> None:
        try:
            await self.telegram_client.send_message(
                self.chat_id, 
                normalize_text(str(self.msg_input.value))
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
        static = Static(normalize_text(self.message))
        static.border_title = normalize_text(self.username) * (not self.is_me)
        static.border_subtitle = self.send_time
        
        with Container():
            yield static
        
        if self.is_me:
            self.classes = "is_me_true"
        else:
            self.classes = "is_me_false"
