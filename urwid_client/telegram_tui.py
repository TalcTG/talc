#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram TUI Client
Консольный клиент Telegram на базе urwid
"""

import urwid
import asyncio
import os
import nest_asyncio
import unicodedata
import emoji
from telethon import TelegramClient, events, utils
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv
import datetime

# Разрешаем вложенные event loops
nest_asyncio.apply()

def normalize_text(text: str) -> str:
    """Нормализует текст для корректного отображения"""
    if not text:
        return ""
    
    try:
        # Преобразуем в строку, если это не строка
        text = str(text)
        
        # Удаляем эмодзи
        text = emoji.replace_emoji(text, '')
        
        # Нормализуем Unicode
        text = unicodedata.normalize('NFKC', text)
        
        # Заменяем специальные символы на их ASCII-эквиваленты
        text = text.replace('—', '-').replace('–', '-').replace('…', '...')
        
        # Удаляем все управляющие символы, кроме новой строки и табуляции
        text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' 
                      or char in ('\n', '\t'))
        
        # Удаляем множественные пробелы
        text = ' '.join(text.split())
        
        return text
    except Exception as e:
        print(f"Ошибка нормализации текста: {e}")
        return "Ошибка отображения"

class ChatWidget(urwid.WidgetWrap):
    """Виджет чата"""
    
    def __init__(self, chat_id, name, message="", is_selected=False, folder=0):
        self.chat_id = chat_id
        self.name = normalize_text(name)
        self.message = normalize_text(message)
        self.is_selected = is_selected
        self.folder = folder
        self.has_focus = False
        
        # Создаем содержимое виджета
        self.update_widget()
        super().__init__(self.widget)
    
    def update_widget(self):
        """Обновляет внешний вид виджета"""
        # Подготавливаем данные
        name = self.name if self.name else "Без названия"
        msg = self.message if self.message else "Нет сообщений"
        
        if len(msg) > 50:
            msg = msg[:47] + "..."
        
        # Добавляем метку папки если нужно
        if self.folder == 1:
            name += " [Архив]"
        
        # Получаем первую букву для аватара
        first_letter = next((c for c in name if c.isprintable()), "?")
        
        # Определяем стиль
        if self.has_focus:
            style = 'selected'
        elif self.is_selected:
            style = 'chat_selected'
        else:
            style = 'chat'
        
        # Создаем виджеты
        avatar = urwid.AttrMap(
            urwid.Text(f" {first_letter} ", align='center'),
            style
        )
        
        content = urwid.Pile([
            urwid.AttrMap(
                urwid.Text(name),
                style
            ),
            urwid.AttrMap(
                urwid.Text(msg),
                style
            )
        ])
        
        self.widget = urwid.AttrMap(
            urwid.Columns([
                ('fixed', 3, avatar),
                content
            ]),
            None
        )
    
    def selectable(self):
        return True
    
    def render(self, size, focus=False):
        if self.has_focus != focus:
            self.has_focus = focus
            self.update_widget()
        return super().render(size, focus)
    
    def keypress(self, size, key):
        if key == 'enter':
            return key
        elif key == 'tab':
            return key
        elif key in ('up', 'down'):
            return key
        return key

class MessageWidget(urwid.WidgetWrap):
    """Виджет сообщения"""
    
    def __init__(self, text="", username="", is_me=False, send_time=""):
        self.text = normalize_text(text)
        self.username = normalize_text(username)
        self.is_me = is_me
        self.send_time = send_time
        
        # Создаем содержимое виджета
        self.update_widget()
        super().__init__(self.widget)
    
    def update_widget(self):
        """Обновляет внешний вид виджета"""
        # Подготавливаем текст
        text = self.text if self.text else "Пустое сообщение"
        username = self.username if self.username else "Неизвестный"
        
        # Создаем заголовок
        header = urwid.Columns([
            urwid.Text(username),
            ('fixed', 5, urwid.Text(self.send_time, align='right'))
        ])
        
        # Создаем виджет
        self.widget = urwid.AttrMap(
            urwid.Pile([
                urwid.AttrMap(header, 'chat_name'),
                urwid.Text(text)
            ]),
            'message_me' if self.is_me else 'message_other'
        )
    
    def selectable(self):
        return False

class SearchEdit(urwid.Edit):
    def __init__(self, *args, **kwargs):
        self.search_callback = kwargs.pop('search_callback', None)
        super().__init__(*args, **kwargs)
    
    def keypress(self, size, key):
        if key in ('up', 'down', 'esc', 'enter'):
            return key
        
        result = super().keypress(size, key)
        # Вызываем поиск при каждом изменении текста
        if self.search_callback and result is None:
            asyncio.create_task(self.search_callback())
        return result

class InputEdit(urwid.Edit):
    def keypress(self, size, key):
        if key in ('esc', 'up', 'down'):
            return key
        return super().keypress(size, key)

class TelegramTUI:
    """Основной класс приложения"""
    
    palette = [
        ('header', 'white', 'dark blue', 'bold'),
        ('footer', 'white', 'dark blue', 'bold'),
        ('bg', 'white', 'black'),
        ('selected', 'black', 'light gray'),
        ('chat', 'white', 'black'),
        ('chat_selected', 'black', 'light gray'),
        ('chat_name', 'light cyan', 'black', 'bold'),
        ('chat_message', 'light gray', 'black'),
        ('message_me', 'light green', 'black'),
        ('message_other', 'white', 'black'),
        ('help', 'yellow', 'black'),
        ('error', 'light red', 'black'),
    ]

    def __init__(self, telegram_client: TelegramClient):
        self.telegram_client = telegram_client
        self.current_screen = 'auth'  # auth или chats
        self.phone = None
        self.code = None
        self.password = None
        self.auth_step = 'phone'  # phone, code или password
        
        # Создаем виджеты авторизации
        self.phone_edit = urwid.Edit(('header', "Номер телефона: "))
        self.code_edit = urwid.Edit(('header', "Код: "))
        self.password_edit = urwid.Edit(('header', "Пароль: "), mask='*')
        self.error_text = urwid.Text(('error', ""))
        
        # Создаем виджеты чатов
        self.search_edit = SearchEdit(
            ('header', "Поиск: "),
            search_callback=self.update_chat_list
        )
        self.chat_walker = urwid.SimpleFocusListWalker([])
        self.chat_list = urwid.ListBox(self.chat_walker)
        self.message_walker = urwid.SimpleFocusListWalker([])
        self.message_list = urwid.ListBox(self.message_walker)
        self.input_edit = InputEdit(('header', "Сообщение: "))
        
        # Создаем экраны
        self.auth_widget = urwid.Filler(
            urwid.Pile([
                urwid.Text(('header', "\nДобро пожаловать в Telegram TUI\n"), align='center'),
                urwid.Divider(),
                self.phone_edit,
                self.code_edit,
                self.password_edit,
                urwid.Divider(),
                self.error_text,
                urwid.Text(('help', "Нажмите Enter для подтверждения"), align='center')
            ])
        )
        
        # Создаем левую панель (чаты)
        self.left_panel = urwid.LineBox(
            urwid.Pile([
                ('pack', urwid.Text(('help', "Tab - переключение фокуса, ↑↓ - выбор чата, Enter - открыть чат, Esc - назад, / - поиск"), align='center')),
                ('pack', self.search_edit),
                urwid.BoxAdapter(self.chat_list, 30)  # Фиксированная высота для списка чатов
            ])
        )
        
        # Создаем правую панель (сообщения)
        self.right_panel = urwid.LineBox(
            urwid.Pile([
                self.message_list,
                ('pack', self.input_edit)
            ])
        )
        
        # Создаем основной виджет чатов
        self.chat_widget = urwid.Columns([
            ('weight', 30, self.left_panel),
            ('weight', 70, self.right_panel)
        ])
        
        # Создаем основной виджет
        self.main_widget = urwid.Frame(
            self.auth_widget,
            header=urwid.AttrMap(
                urwid.Text(' Telegram TUI', align='center'),
                'header'
            ),
            footer=urwid.AttrMap(
                urwid.Text(' Q: Выход | Tab: Переключение фокуса | Enter: Выбор/Отправка | Esc: Назад', align='center'),
                'footer'
            )
        )
        
        # Состояние чатов
        self.current_folder = None
        self.folders = []
        self.chats = []
        self.selected_chat_index = 0
        self.focused_element = "chat_list"  # chat_list, search, messages, input
        self.current_chat_id = None
        
        # Добавляем таймеры обновления
        self.chat_update_task = None
        self.message_update_task = None
        self.last_update_time = 0
        self.update_interval = 3  # секунды для чатов
        self.message_update_interval = 1  # секунда для сообщений
        self.last_message_update_time = 0
    
    def switch_screen(self, screen_name: str):
        """Переключение между экранами"""
        self.current_screen = screen_name
        if screen_name == 'auth':
            self.main_widget.body = self.auth_widget
        elif screen_name == 'chats':
            self.main_widget.body = self.chat_widget
    
    async def handle_auth(self, key):
        """Обработка авторизации"""
        if key != 'enter':
            return
        
        try:
            if self.auth_step == 'phone':
                phone = normalize_text(self.phone_edit.get_edit_text())
                if phone:
                    self.phone = phone
                    await self.telegram_client.send_code_request(phone=phone)
                    self.auth_step = 'code'
                    self.error_text.set_text(('help', "Код отправлен"))
            
            elif self.auth_step == 'code':
                code = normalize_text(self.code_edit.get_edit_text())
                if code:
                    try:
                        await self.telegram_client.sign_in(phone=self.phone, code=code)
                        self.switch_screen('chats')
                        await self.update_chat_list()
                    except SessionPasswordNeededError:
                        self.auth_step = 'password'
                        self.error_text.set_text(('help', "Требуется пароль"))
            
            elif self.auth_step == 'password':
                password = self.password_edit.get_edit_text()
                if password:
                    await self.telegram_client.sign_in(password=password)
                    self.switch_screen('chats')
                    await self.update_chat_list()
        
        except Exception as e:
            self.error_text.set_text(('error', str(e)))
    
    async def update_chat_list(self):
        """Обновляет список чатов"""
        try:
            # Получаем папки
            if not self.folders:
                try:
                    # Проверяем наличие архива
                    self.folders = [1] if await self.telegram_client.get_dialogs(limit=1, folder=1) else []
                except Exception as e:
                    print(f"Ошибка получения папок: {e}")
                    self.folders = []
            
            # Получаем диалоги
            try:
                dialogs = await self.telegram_client.get_dialogs(
                    limit=100,
                    folder=self.current_folder
                )
            except Exception as e:
                print(f"Ошибка получения диалогов: {e}")
                dialogs = []
            
            # Фильтруем по поисковому запросу
            search_query = normalize_text(self.search_edit.get_edit_text().lower())
            if search_query:
                filtered_dialogs = []
                for dialog in dialogs:
                    try:
                        # Поиск по имени
                        name = ""
                        if hasattr(dialog.entity, 'title') and dialog.entity.title:
                            name = dialog.entity.title
                        elif hasattr(dialog.entity, 'first_name'):
                            name = dialog.entity.first_name
                            if hasattr(dialog.entity, 'last_name') and dialog.entity.last_name:
                                name += f" {dialog.entity.last_name}"
                        
                        # Поиск по последнему сообщению
                        last_message = ""
                        if dialog.message and hasattr(dialog.message, 'message'):
                            last_message = dialog.message.message
                        
                        # Если есть совпадение, добавляем диалог
                        if (search_query in normalize_text(name).lower() or 
                            search_query in normalize_text(last_message).lower()):
                            filtered_dialogs.append(dialog)
                    except Exception as e:
                        print(f"Ошибка фильтрации диалога: {e}")
                
                dialogs = filtered_dialogs
            
            # Очищаем список
            self.chat_walker[:] = []
            
            # Добавляем чаты
            for i, dialog in enumerate(dialogs):
                try:
                    # Получаем имя и сообщение
                    entity = dialog.entity
                    
                    # Определяем имя чата
                    if hasattr(entity, 'title') and entity.title:
                        name = entity.title
                    elif hasattr(entity, 'first_name'):
                        name = entity.first_name
                        if hasattr(entity, 'last_name') and entity.last_name:
                            name += f" {entity.last_name}"
                    else:
                        name = "Без названия"
                    
                    # Получаем последнее сообщение
                    if dialog.message:
                        message = dialog.message.message if hasattr(dialog.message, 'message') else ""
                    else:
                        message = ""
                    
                    chat = ChatWidget(
                        chat_id=dialog.id,
                        name=name,
                        message=message,
                        is_selected=(i == self.selected_chat_index),
                        folder=1 if self.current_folder else 0
                    )
                    self.chat_walker.append(chat)
                except Exception as e:
                    print(f"Ошибка создания виджета чата: {e}")
            
            # Обновляем фокус
            if self.chat_walker:
                self.selected_chat_index = min(self.selected_chat_index, len(self.chat_walker) - 1)
                self.chat_list.set_focus(self.selected_chat_index)
                self.update_selected_chat()
            
        except Exception as e:
            print(f"Ошибка обновления чатов: {e}")
    
    def update_selected_chat(self):
        """Обновляет выделение выбранного чата"""
        try:
            for i, chat in enumerate(self.chat_walker):
                was_selected = chat.is_selected
                chat.is_selected = (i == self.selected_chat_index)
                if was_selected != chat.is_selected:
                    chat.update_widget()
        except Exception as e:
            print(f"Ошибка обновления выделения: {e}")
    
    async def update_message_list(self, chat_id):
        """Обновляет список сообщений"""
        try:
            # Получаем сообщения
            messages = await self.telegram_client.get_messages(
                entity=chat_id,
                limit=50
            )
            
            # Получаем информацию о себе
            me = await self.telegram_client.get_me()
            
            # Очищаем список
            self.message_walker[:] = []
            
            # Добавляем сообщения
            for msg in reversed(messages):
                try:
                    # Определяем, отправлено ли сообщение нами
                    is_me = False
                    if hasattr(msg, 'from_id') and msg.from_id:
                        if hasattr(msg.from_id, 'user_id'):
                            is_me = msg.from_id.user_id == me.id
                    
                    # Получаем текст сообщения
                    text = msg.message if hasattr(msg, 'message') else "Медиа"
                    
                    # Получаем имя отправителя
                    username = ""
                    if hasattr(msg, 'sender') and msg.sender:
                        if hasattr(msg.sender, 'first_name'):
                            username = msg.sender.first_name
                            if hasattr(msg.sender, 'last_name') and msg.sender.last_name:
                                username += f" {msg.sender.last_name}"
                        elif hasattr(msg.sender, 'title'):
                            username = msg.sender.title
                    
                    # Если не удалось получить имя, используем Me/Другой
                    if not username:
                        username = "Я" if is_me else "Неизвестный"
                    
                    message = MessageWidget(
                        text=text,
                        username=username,
                        is_me=is_me,
                        send_time=msg.date.strftime("%H:%M")
                    )
                    self.message_walker.append(message)
                except Exception as e:
                    print(f"Ошибка создания виджета сообщения: {e}")
            
            # Прокручиваем к последнему сообщению
            if self.message_walker:
                self.message_list.set_focus(len(self.message_walker) - 1)
            
        except Exception as e:
            print(f"Ошибка обновления сообщений: {e}")
    
    async def handle_chat_input(self, key):
        """Обработка ввода в экране чатов"""
        if key == 'tab':
            if self.focused_element == "search":
                self.focused_element = "chat_list"
                self.left_panel.original_widget.focus_position = 2
                # Обновляем список при переключении на чаты
                await self.update_chat_list()
            elif self.focused_element == "chat_list":
                if self.current_chat_id:
                    self.focused_element = "messages"
                    self.chat_widget.focus_position = 1
                    self.right_panel.original_widget.focus_position = 0
                    # Обновляем сообщения при переключении на них
                    await self.update_message_list(self.current_chat_id)
                else:
                    self.focused_element = "search"
                    self.left_panel.original_widget.focus_position = 1
            elif self.focused_element == "messages":
                self.focused_element = "input"
                self.right_panel.original_widget.focus_position = 1
            elif self.focused_element == "input":
                self.focused_element = "search"
                self.chat_widget.focus_position = 0
                self.left_panel.original_widget.focus_position = 1
                # Обновляем поиск при переключении на него
                await self.update_chat_list()
        
        elif key in ('up', 'down'):
            if self.focused_element == "chat_list" and self.chat_walker:
                if key == 'up':
                    if self.chat_list.focus_position > 0:
                        self.chat_list.focus_position -= 1
                else:
                    if self.chat_list.focus_position < len(self.chat_walker) - 1:
                        self.chat_list.focus_position += 1
                
                # Обновляем выделение
                self.selected_chat_index = self.chat_list.focus_position
                self.update_selected_chat()
                
                # Если чат открыт, обновляем его содержимое
                if self.current_chat_id:
                    focused = self.chat_walker[self.selected_chat_index]
                    self.current_chat_id = focused.chat_id
                    await self.update_message_list(focused.chat_id)
            
            elif self.focused_element == "messages" and self.message_walker:
                if key == 'up':
                    if self.message_list.focus_position > 0:
                        self.message_list.focus_position -= 1
                else:
                    if self.message_list.focus_position < len(self.message_walker) - 1:
                        self.message_list.focus_position += 1
        
        elif key == 'enter':
            if self.focused_element == "search":
                await self.update_chat_list()
                self.focused_element = "chat_list"
                self.left_panel.original_widget.focus_position = 2
            elif self.focused_element == "chat_list" and self.chat_walker:
                try:
                    focused = self.chat_walker[self.chat_list.focus_position]
                    self.current_chat_id = focused.chat_id
                    self.selected_chat_index = self.chat_list.focus_position
                    await self.update_message_list(focused.chat_id)
                    self.focused_element = "input"
                    self.chat_widget.focus_position = 1
                    self.right_panel.original_widget.focus_position = 1
                    # Сбрасываем время последнего обновления сообщений
                    self.last_message_update_time = 0
                except Exception as e:
                    print(f"Ошибка при открытии чата: {e}")
            elif self.focused_element == "input" and self.current_chat_id:
                message = self.input_edit.get_edit_text()
                if message.strip():
                    try:
                        await self.telegram_client.send_message(self.current_chat_id, message)
                        self.input_edit.set_edit_text("")
                        # Сразу обновляем сообщения после отправки
                        self.last_message_update_time = 0
                        await self.update_message_list(self.current_chat_id)
                    except Exception as e:
                        print(f"Ошибка отправки сообщения: {e}")
        
        elif key == 'esc':
            if self.focused_element in ("input", "messages"):
                # Закрываем текущий чат
                self.current_chat_id = None
                self.message_walker[:] = []
                self.input_edit.set_edit_text("")
                self.focused_element = "chat_list"
                self.chat_widget.focus_position = 0
                self.left_panel.original_widget.focus_position = 2
            elif self.focused_element == "search":
                self.search_edit.set_edit_text("")
                await self.update_chat_list()
                self.focused_element = "chat_list"
                self.left_panel.original_widget.focus_position = 2
    
    def unhandled_input(self, key):
        """Обработка необработанных нажатий клавиш"""
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        
        # Создаем задачу для асинхронной обработки
        if self.current_screen == 'auth':
            asyncio.create_task(self.handle_auth(key))
        else:
            asyncio.create_task(self.handle_chat_input(key))
    
    async def start_auto_updates(self):
        """Запускает автоматическое обновление чатов и сообщений"""
        if self.chat_update_task:
            self.chat_update_task.cancel()
        if self.message_update_task:
            self.message_update_task.cancel()
            
        async def chat_update_loop():
            while True:
                try:
                    current_time = datetime.datetime.now().timestamp()
                    if current_time - self.last_update_time >= self.update_interval:
                        await self.update_chat_list()
                        self.last_update_time = current_time
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Ошибка в цикле обновления чатов: {e}")
                    await asyncio.sleep(1)
        
        async def message_update_loop():
            while True:
                try:
                    if self.current_chat_id:
                        current_time = datetime.datetime.now().timestamp()
                        if current_time - self.last_message_update_time >= self.message_update_interval:
                            await self.update_message_list(self.current_chat_id)
                            self.last_message_update_time = current_time
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Ошибка в цикле обновления сообщений: {e}")
                    await asyncio.sleep(0.5)
        
        self.chat_update_task = asyncio.create_task(chat_update_loop())
        self.message_update_task = asyncio.create_task(message_update_loop())

    async def stop_auto_updates(self):
        """Останавливает автоматическое обновление"""
        if self.chat_update_task:
            self.chat_update_task.cancel()
            self.chat_update_task = None
        if self.message_update_task:
            self.message_update_task.cancel()
            self.message_update_task = None

    async def run(self):
        """Запуск приложения"""
        try:
            # Подключаемся к Telegram
            await self.telegram_client.connect()
            print("Подключено к Telegram")
            
            # Проверяем авторизацию
            if await self.telegram_client.is_user_authorized():
                self.switch_screen('chats')
                await self.update_chat_list()
                # Запускаем автообновление
                await self.start_auto_updates()
            else:
                self.switch_screen('auth')
            
            # Создаем event loop для urwid
            event_loop = urwid.AsyncioEventLoop(loop=asyncio.get_event_loop())
            
            # Запускаем интерфейс
            urwid.MainLoop(
                self.main_widget,
                self.palette,
                event_loop=event_loop,
                unhandled_input=self.unhandled_input
            ).run()
            
        except Exception as e:
            print(f"Ошибка при запуске приложения: {e}")
        finally:
            # Останавливаем автообновление
            await self.stop_auto_updates()
            if self.telegram_client and self.telegram_client.is_connected():
                await self.telegram_client.disconnect()
                print("Отключено от Telegram")

async def main():
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем наличие API ключей
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    
    if not api_id or not api_hash:
        print("API_ID и API_HASH не найдены в .env файле.")
        print("Пожалуйста, скопируйте .env.example в .env и заполните свои ключи.")
        return
    
    # Преобразуем API_ID в число
    api_id = int(api_id)
    
    # Инициализируем клиент Telegram
    session_file = "talc.session"
    
    # Создаем клиент
    client = TelegramClient(
        session_file,
        api_id=api_id,
        api_hash=api_hash,
        system_version="macOS 14.3.1",
        device_model="MacBook",
        app_version="1.0"
    )
    
    # Создаем и запускаем приложение
    app = TelegramTUI(client)
    await app.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Ошибка при запуске приложения: {e}") 