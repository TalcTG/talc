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
from PIL import Image
import io
import hashlib
import json
import shutil
from pathlib import Path

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

def image_to_ascii(image_data, max_width=80, max_height=24):
    """Конвертирует изображение в ASCII-арт"""
    try:
        # Открываем изображение из байтов
        image = Image.open(io.BytesIO(image_data))
        
        # Конвертируем в оттенки серого
        image = image.convert('L')
        
        # Определяем новые размеры с сохранением пропорций
        width, height = image.size
        aspect_ratio = height/width
        new_width = min(max_width, width)
        new_height = int(new_width * aspect_ratio * 0.5)  # * 0.5 потому что символы в терминале выше, чем шире
        
        if new_height > max_height:
            new_height = max_height
            new_width = int(new_height / aspect_ratio * 2)
        
        # Изменяем размер
        image = image.resize((new_width, new_height))
        
        # Символы от темного к светлому
        ascii_chars = '@%#*+=-:. '
        
        # Конвертируем пиксели в ASCII
        pixels = image.getdata()
        ascii_str = ''
        for i, pixel in enumerate(pixels):
            ascii_str += ascii_chars[pixel//32]  # 256//32 = 8 уровней
            if (i + 1) % new_width == 0:
                ascii_str += '\n'
        
        # Добавляем рамку вокруг ASCII-арта для стабильности
        lines = ascii_str.split('\n')
        if lines and lines[-1] == '':
            lines = lines[:-1]  # Удаляем последнюю пустую строку
        
        max_line_length = max(len(line) for line in lines)
        border_top = '┌' + '─' * max_line_length + '┐\n'
        border_bottom = '└' + '─' * max_line_length + '┘'
        
        framed_ascii = border_top
        for line in lines:
            padding = ' ' * (max_line_length - len(line))
            framed_ascii += '│' + line + padding + '│\n'
        framed_ascii += border_bottom
        
        return framed_ascii
    except Exception as e:
        print(f"Ошибка конвертации изображения: {e}")
        return "[Ошибка конвертации изображения]"

class AsciiArtCache:
    """Класс для кэширования ASCII-артов"""
    def __init__(self, cache_dir='pics'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.index_file = os.path.join(cache_dir, 'index.json')
        self.load_index()

    def load_index(self):
        """Загружает индекс кэшированных изображений"""
        try:
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.index = {}
            self.save_index()

    def save_index(self):
        """Сохраняет индекс кэшированных изображений"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f)

    def get_cache_key(self, image_data):
        """Генерирует ключ кэша для изображения"""
        return hashlib.md5(image_data).hexdigest()

    def get_cached_art(self, image_data):
        """Получает ASCII-арт из кэша или создает новый"""
        cache_key = self.get_cache_key(image_data)
        
        # Проверяем наличие в индексе
        if cache_key in self.index:
            try:
                with open(os.path.join(self.cache_dir, cache_key + '.txt'), 'r') as f:
                    return f.read()
            except FileNotFoundError:
                pass

        # Если нет в кэше, создаем новый
        ascii_art = image_to_ascii(image_data)
        
        # Сохраняем в кэш
        with open(os.path.join(self.cache_dir, cache_key + '.txt'), 'w') as f:
            f.write(ascii_art)
        
        # Обновляем индекс
        self.index[cache_key] = {
            'created_at': datetime.datetime.now().isoformat(),
            'size': len(image_data)
        }
        self.save_index()
        
        return ascii_art

class MediaCache:
    """Класс для кэширования медиафайлов"""
    def __init__(self, cache_dir='cache', max_size_mb=1000):
        self.cache_dir = Path(cache_dir)
        self.files_dir = self.cache_dir / 'files'
        self.index_file = self.cache_dir / 'index.json'
        self.max_size = max_size_mb * 1024 * 1024  # Конвертируем в байты
        self.current_size = 0
        
        # Создаем директории
        self.files_dir.mkdir(parents=True, exist_ok=True)
        
        # Загружаем индекс
        self.load_index()
    
    def load_index(self):
        """Загружает индекс кэшированных файлов"""
        try:
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
            # Подсчитываем текущий размер кэша
            self.current_size = sum(item['size'] for item in self.index.values())
        except (FileNotFoundError, json.JSONDecodeError):
            self.index = {}
            self.current_size = 0
            self.save_index()
    
    def save_index(self):
        """Сохраняет индекс кэшированных файлов"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f)
    
    def get_cache_key(self, data):
        """Генерирует ключ кэша"""
        return hashlib.md5(data).hexdigest()
    
    def cleanup(self, needed_space=0):
        """Очищает старые файлы для освобождения места"""
        if self.current_size + needed_space <= self.max_size:
            return True
        
        # Сортируем файлы по времени последнего доступа
        files = [(k, v) for k, v in self.index.items()]
        files.sort(key=lambda x: x[1]['last_access'])
        
        # Удаляем старые файлы, пока не освободится достаточно места
        for key, info in files:
            file_path = self.files_dir / f"{key}{info['ext']}"
            try:
                file_path.unlink()
                self.current_size -= info['size']
                del self.index[key]
                if self.current_size + needed_space <= self.max_size:
                    self.save_index()
                    return True
            except Exception as e:
                print(f"Ошибка при удалении файла {file_path}: {e}")
        
        return False
    
    def get_cached_file(self, file_data, file_type):
        """Получает файл из кэша или сохраняет новый"""
        cache_key = self.get_cache_key(file_data)
        
        # Проверяем наличие в кэше
        if cache_key in self.index:
            info = self.index[cache_key]
            file_path = self.files_dir / f"{cache_key}{info['ext']}"
            if file_path.exists():
                # Обновляем время последнего доступа
                info['last_access'] = datetime.datetime.now().isoformat()
                self.save_index()
                return file_path
        
        # Определяем расширение файла
        ext = self.get_extension_for_type(file_type)
        
        # Проверяем и освобождаем место если нужно
        if not self.cleanup(len(file_data)):
            print("Недостаточно места в кэше")
            return None
        
        # Сохраняем файл
        file_path = self.files_dir / f"{cache_key}{ext}"
        try:
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # Обновляем индекс
            self.index[cache_key] = {
                'type': file_type,
                'ext': ext,
                'size': len(file_data),
                'created_at': datetime.datetime.now().isoformat(),
                'last_access': datetime.datetime.now().isoformat()
            }
            self.current_size += len(file_data)
            self.save_index()
            
            return file_path
        except Exception as e:
            print(f"Ошибка сохранения файла: {e}")
            return None
    
    def get_extension_for_type(self, file_type):
        """Возвращает расширение файла для типа медиа"""
        extensions = {
            'photo': '.jpg',
            'video': '.mp4',
            'audio': '.ogg',
            'voice': '.ogg',
            'document': '',  # Будет использовано оригинальное расширение
            'sticker': '.webp',
            'gif': '.gif'
        }
        return extensions.get(file_type, '')

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
    
    def __init__(self, message_id, text="", username="", is_me=False, send_time="", status="", is_selected=False, media_data=None):
        self.message_id = message_id
        self.text = normalize_text(text)
        self.username = normalize_text(username)
        self.is_me = is_me
        self.send_time = send_time
        self.status = status
        self.is_selected = is_selected
        self._media_data = None
        self._cached_content = None
        self.set_media_data(media_data)
        
        # Создаем содержимое виджета
        self.update_widget()
        super().__init__(self.widget)
    
    def set_media_data(self, media_data):
        """Устанавливает медиа-данные и обновляет кэш"""
        if self._media_data != media_data:
            self._media_data = media_data
            self._cached_content = None
    
    def get_content(self):
        """Получает содержимое сообщения с кэшированием"""
        if self._cached_content is None:
            text = self.text if self.text else "Пустое сообщение"
            if self._media_data:
                text = self._media_data + "\n" + text
            self._cached_content = text
        return self._cached_content
    
    def update_widget(self):
        """Обновляет внешний вид виджета"""
        # Подготавливаем текст
        username = self.username if self.username else "Неизвестный"
        
        # Добавляем статус к времени для исходящих сообщений
        time_text = self.send_time
        if self.is_me and self.status:
            time_text = f"{self.send_time} {self.status}"
        
        # Создаем заголовок
        header = urwid.Columns([
            urwid.Text(username),
            ('fixed', 10 if self.is_me else 5, urwid.Text(time_text, align='right'))
        ])
        
        # Определяем стиль
        style = 'message_selected' if self.is_selected else ('message_me' if self.is_me else 'message_other')
        
        # Создаем виджет с фиксированной шириной для ASCII-арта
        content = urwid.Text(self.get_content())
        if self._media_data:
            content = urwid.BoxAdapter(urwid.Filler(content), len(self._media_data.split('\n')))
        
        # Создаем виджет
        self.widget = urwid.AttrMap(
            urwid.Pile([
                urwid.AttrMap(header, 'chat_name'),
                content
            ]),
            style
        )
    
    def selectable(self):
        return True
    
    def keypress(self, size, key):
        if key == 'ctrl r':
            return 'reply'
        return key

class SearchEdit(urwid.Edit):
    """Виджет поиска с отложенным обновлением"""
    def __init__(self, *args, **kwargs):
        self.search_callback = kwargs.pop('search_callback', None)
        self.search_delay = 0.5  # Задержка поиска в секундах
        self.last_search = 0
        self.pending_search = None
        super().__init__(*args, **kwargs)
    
    def keypress(self, size, key):
        if key in ('up', 'down', 'esc', 'enter', 'tab'):
            return key
        
        result = super().keypress(size, key)
        
        # Отменяем предыдущий отложенный поиск
        if self.pending_search:
            self.pending_search.cancel()
        
        # Создаем новый отложенный поиск
        if self.search_callback and result is None:
            async def delayed_search():
                try:
                    await asyncio.sleep(self.search_delay)
                    await self.search_callback()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Ошибка отложенного поиска: {e}")
            
            self.pending_search = asyncio.create_task(delayed_search())
        
        return result

    async def update_chat_list(self):
        """Обновляет список чатов"""
        try:
            # Сохраняем текущий фокус и ID выбранного чата
            current_focus = self.chat_list.focus_position if self.chat_walker else 0
            current_chat_id = self.current_chat_id
            
            # Получаем диалоги
            try:
                dialogs = await self.telegram_client.get_dialogs(
                    limit=50,
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
                        # Получаем имя
                        name = ""
                        if hasattr(dialog.entity, 'title') and dialog.entity.title:
                            name = dialog.entity.title
                        elif hasattr(dialog.entity, 'first_name'):
                            name = dialog.entity.first_name
                            if hasattr(dialog.entity, 'last_name') and dialog.entity.last_name:
                                name += f" {dialog.entity.last_name}"
                        name = normalize_text(name).lower()
                        
                        # Получаем последнее сообщение
                        last_message = ""
                        if dialog.message and hasattr(dialog.message, 'message'):
                            last_message = normalize_text(dialog.message.message).lower()
                        
                        # Проверяем совпадение
                        if search_query in name or search_query in last_message:
                            filtered_dialogs.append(dialog)
                            
                            # Ограничиваем количество результатов для производительности
                            if len(filtered_dialogs) >= 20:
                                break
                    except Exception as e:
                        print(f"Ошибка фильтрации диалога: {e}")
                
                dialogs = filtered_dialogs
            
            # Очищаем список
            self.chat_walker[:] = []
            
            # Добавляем чаты
            restored_focus = False
            for i, dialog in enumerate(dialogs):
                try:
                    # Получаем имя чата
                    name = ""
                    if hasattr(dialog.entity, 'title') and dialog.entity.title:
                        name = dialog.entity.title
                    elif hasattr(dialog.entity, 'first_name'):
                        name = dialog.entity.first_name
                        if hasattr(dialog.entity, 'last_name') and dialog.entity.last_name:
                            name += f" {dialog.entity.last_name}"
                    else:
                        name = "Без названия"
                    
                    # Получаем последнее сообщение
                    message = ""
                    if dialog.message and hasattr(dialog.message, 'message'):
                        message = dialog.message.message
                    
                    # Создаем виджет чата
                    chat = ChatWidget(
                        chat_id=dialog.id,
                        name=name,
                        message=message,
                        is_selected=(dialog.id == current_chat_id),
                        folder=1 if self.current_folder else 0
                    )
                    
                    self.chat_walker.append(chat)
                    
                    # Восстанавливаем фокус если это текущий чат
                    if dialog.id == current_chat_id and not restored_focus:
                        current_focus = i
                        restored_focus = True
                    
                except Exception as e:
                    print(f"Ошибка создания виджета чата: {e}")
            
            # Восстанавливаем фокус
            if self.chat_walker:
                if current_focus >= len(self.chat_walker):
                    current_focus = len(self.chat_walker) - 1
                self.chat_list.set_focus(max(0, current_focus))
                self.selected_chat_index = current_focus
                self.update_selected_chat()
            
        except Exception as e:
            print(f"Ошибка обновления чатов: {e}")
            # В случае ошибки очищаем список
            self.chat_walker[:] = []

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
        ('message_selected', 'black', 'light gray'),
        ('input_disabled', 'dark gray', 'black'),
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
                ('pack', urwid.Text(('help', "Tab - переключение фокуса, ↑↓ - выбор чата, Enter - открыть чат, Esc - назад, / - поиск, [] - папки"), align='center')),
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
        
        # Добавляем отслеживание отправляемых сообщений
        self.pending_messages = {}  # message_id -> widget
        
        # Добавляем обработчик обновления сообщений
        @telegram_client.on(events.MessageEdited())
        async def handle_edit(event):
            try:
                if event.message.out:
                    await self.update_message_status(event.message)
            except Exception as e:
                print(f"Ошибка обработки редактирования: {e}")
        
        @telegram_client.on(events.NewMessage())
        async def handle_new(event):
            try:
                if event.message.out:
                    await self.update_message_status(event.message)
                elif event.message.chat_id == self.current_chat_id:
                    # Обновляем сообщения если это текущий чат
                    self.last_message_update_time = 0
            except Exception as e:
                print(f"Ошибка обработки нового сообщения: {e}")
        
        # Добавляем состояния для ответов
        self.selected_message = None
        self.replying_to = None
        self.can_send_messages = False
        
        self.ascii_cache = AsciiArtCache()
        self.media_cache = MediaCache(max_size_mb=1000)  # 1GB по умолчанию
    
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
            # Сохраняем текущий фокус и ID выбранного чата
            current_focus = self.chat_list.focus_position if self.chat_walker else 0
            current_chat_id = self.current_chat_id
            
            # Получаем папки
            if not self.folders:
                try:
                    folders = await self.telegram_client.get_dialogs(folder=1)
                    if folders:
                        self.folders = [0, 1]
                    else:
                        self.folders = [0]
                    print(f"Доступные папки: {self.folders}")
                except Exception as e:
                    print(f"Ошибка получения папок: {e}")
                    self.folders = [0]
            
            # Получаем диалоги
            try:
                dialogs = await self.telegram_client.get_dialogs(
                    limit=50,  # Уменьшаем лимит для стабильности
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
                        name = ""
                        if hasattr(dialog.entity, 'title') and dialog.entity.title:
                            name = dialog.entity.title
                        elif hasattr(dialog.entity, 'first_name'):
                            name = dialog.entity.first_name
                            if hasattr(dialog.entity, 'last_name') and dialog.entity.last_name:
                                name += f" {dialog.entity.last_name}"
                        
                        last_message = ""
                        if dialog.message and hasattr(dialog.message, 'message'):
                            last_message = dialog.message.message
                        
                        if (search_query in normalize_text(name).lower() or 
                            search_query in normalize_text(last_message).lower()):
                            filtered_dialogs.append(dialog)
                    except Exception as e:
                        print(f"Ошибка фильтрации диалога: {e}")
                
                dialogs = filtered_dialogs
            
            # Сохраняем старые чаты для сравнения
            old_chats = {chat.chat_id: chat for chat in self.chat_walker}
            
            # Очищаем список
            self.chat_walker[:] = []
            
            # Добавляем чаты
            restored_focus = False
            for i, dialog in enumerate(dialogs):
                try:
                    entity = dialog.entity
                    
                    if hasattr(entity, 'title') and entity.title:
                        name = entity.title
                    elif hasattr(entity, 'first_name'):
                        name = entity.first_name
                        if hasattr(entity, 'last_name') and entity.last_name:
                            name += f" {entity.last_name}"
                    else:
                        name = "Без названия"
                    
                    if dialog.message:
                        message = dialog.message.message if hasattr(dialog.message, 'message') else ""
                    else:
                        message = ""
                    
                    # Проверяем, был ли этот чат раньше
                    old_chat = old_chats.get(dialog.id)
                    is_selected = (dialog.id == current_chat_id)
                    
                    chat = ChatWidget(
                        chat_id=dialog.id,
                        name=name,
                        message=message,
                        is_selected=is_selected,
                        folder=1 if self.current_folder else 0
                    )
                    
                    self.chat_walker.append(chat)
                    
                    # Восстанавливаем фокус если это текущий чат
                    if dialog.id == current_chat_id and not restored_focus:
                        current_focus = i
                        restored_focus = True
                        
                except Exception as e:
                    print(f"Ошибка создания виджета чата: {e}")
            
            # Восстанавливаем фокус
            if self.chat_walker:
                if current_focus >= len(self.chat_walker):
                    current_focus = len(self.chat_walker) - 1
                self.chat_list.set_focus(max(0, current_focus))
                self.selected_chat_index = current_focus
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
    
    async def process_media(self, message):
        """Обрабатывает медиа в сообщении"""
        try:
            media_type = None
            media_data = None
            
            if message.photo:
                media_type = 'photo'
            elif message.video:
                media_type = 'video'
            elif message.audio:
                media_type = 'audio'
            elif message.voice:
                media_type = 'voice'
            elif message.document:
                media_type = 'document'
            elif message.sticker:
                media_type = 'sticker'
            elif getattr(message, 'gif', None):
                media_type = 'gif'
            
            if media_type:
                # Загружаем медиа
                media_data = await self.telegram_client.download_media(message.media, bytes)
                if media_data:
                    # Сохраняем в кэш
                    cached_path = self.media_cache.get_cached_file(media_data, media_type)
                    if cached_path:
                        if media_type == 'photo':
                            # Для фото создаем ASCII-арт
                            with open(cached_path, 'rb') as f:
                                return self.ascii_cache.get_cached_art(f.read())
                        else:
                            # Для других типов возвращаем описание
                            size_mb = len(media_data) / (1024 * 1024)
                            return f"[{media_type.upper()}: {size_mb:.1f}MB - {cached_path.name}]"
            
            return None
        except Exception as e:
            print(f"Ошибка обработки медиа: {e}")
            return f"[Ошибка обработки {media_type if media_type else 'медиа'}]"

    async def update_message_list(self, chat_id):
        """Обновляет список сообщений"""
        try:
            if not chat_id:
                self.message_walker[:] = []
                return

            # Сохраняем текущий фокус
            current_focus = self.message_list.focus_position if self.message_walker else None
            
            # Получаем сообщения
            messages = await self.telegram_client.get_messages(
                entity=chat_id,
                limit=30  # Уменьшаем лимит для стабильности
            )
            
            # Получаем информацию о себе
            me = await self.telegram_client.get_me()
            
            # Сохраняем отслеживаемые сообщения
            tracked_messages = {
                msg_id: widget
                for msg_id, widget in self.pending_messages.items()
            }
            
            # Сохраняем старые сообщения для сравнения
            old_messages = {msg.message_id: msg for msg in self.message_walker}
            
            # Очищаем список
            self.message_walker[:] = []
            
            # Добавляем сообщения
            for msg in reversed(messages):
                try:
                    # Проверяем, было ли это сообщение раньше
                    old_message = old_messages.get(msg.id)
                    if old_message and not msg.photo:
                        # Переиспользуем существующий виджет для не-фото сообщений
                        self.message_walker.append(old_message)
                        continue
                    
                    is_me = False
                    if hasattr(msg, 'from_id') and msg.from_id:
                        if hasattr(msg.from_id, 'user_id'):
                            is_me = msg.from_id.user_id == me.id
                    
                    text = msg.message if hasattr(msg, 'message') else ""
                    media_data = None
                    
                    # Обрабатываем все типы медиа
                    media_data = await self.process_media(msg)
                    if media_data:
                        if not text:
                            text = media_data
                        else:
                            text = media_data + "\n" + text
                    
                    username = ""
                    if hasattr(msg, 'sender') and msg.sender:
                        if hasattr(msg.sender, 'first_name'):
                            username = msg.sender.first_name
                            if hasattr(msg.sender, 'last_name') and msg.sender.last_name:
                                username += f" {msg.sender.last_name}"
                        elif hasattr(msg.sender, 'title'):
                            username = msg.sender.title
                    
                    if not username:
                        username = "Я" if is_me else "Неизвестный"
                    
                    status = ""
                    if is_me:
                        if msg.id in tracked_messages:
                            status = tracked_messages[msg.id].status
                        else:
                            status = "✓✓"
                    
                    message = MessageWidget(
                        message_id=msg.id,
                        text=text,
                        username=username,
                        is_me=is_me,
                        send_time=msg.date.strftime("%H:%M"),
                        status=status,
                        is_selected=(msg.id == self.selected_message),
                        media_data=media_data
                    )
                    
                    if msg.id in tracked_messages:
                        self.pending_messages[msg.id] = message
                    
                    self.message_walker.append(message)
                except Exception as e:
                    print(f"Ошибка создания виджета сообщения: {e}")
            
            # Восстанавливаем фокус
            if current_focus is not None and current_focus < len(self.message_walker):
                self.message_list.set_focus(current_focus)
            elif self.message_walker:
                self.message_list.set_focus(len(self.message_walker) - 1)
            
        except Exception as e:
            print(f"Ошибка обновления сообщений: {e}")
            self.message_walker[:] = []
    
    async def update_message_status(self, message):
        """Обновляет статус сообщения"""
        try:
            if message.id in self.pending_messages:
                widget = self.pending_messages[message.id]
                # Определяем статус
                if getattr(message, 'from_id', None):
                    widget.status = "vv"  # Доставлено
                else:
                    widget.status = "v"  # Отправлено
                widget.update_widget()
                # Если сообщение доставлено, удаляем из отслеживания
                if widget.status == "vv":
                    del self.pending_messages[message.id]
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
    
    async def check_chat_permissions(self, chat_id):
        """Проверяет права на отправку сообщений в чате"""
        try:
            # Получаем информацию о чате
            chat = await self.telegram_client.get_entity(chat_id)
            
            # Проверяем, является ли чат каналом
            if hasattr(chat, 'broadcast') and chat.broadcast:
                # Для каналов проверяем права администратора
                participant = await self.telegram_client.get_permissions(chat)
                self.can_send_messages = participant.is_admin
            else:
                # Для всех остальных чатов разрешаем отправку
                self.can_send_messages = True
            
            # Обновляем видимость поля ввода
            self.update_input_visibility()
            
        except Exception as e:
            print(f"Ошибка проверки прав: {e}")
            # В случае ошибки разрешаем отправку для не-каналов
            self.can_send_messages = not (hasattr(chat, 'broadcast') and chat.broadcast)
            self.update_input_visibility()
    
    def update_input_visibility(self):
        """Обновляет видимость поля ввода"""
        if self.can_send_messages:
            if self.replying_to:
                self.input_edit = InputEdit(('header', f"Ответ на '{self.replying_to[:30]}...': "))
            else:
                self.input_edit = InputEdit(('header', "Сообщение: "))
        else:
            self.input_edit = InputEdit(('input_disabled', "Отправка сообщений недоступна"))
            self.input_edit.set_edit_text("")
        
        # Обновляем правую панель
        if len(self.right_panel.original_widget.widget_list) > 1:
            self.right_panel.original_widget.widget_list[-1] = self.input_edit
    
    async def handle_chat_input(self, key):
        """Обработка ввода в экране чатов"""
        try:
            if key == 'reply' and self.focused_element == "messages":
                # Получаем выбранное сообщение
                if self.message_walker and self.message_list.focus is not None:
                    msg_widget = self.message_walker[self.message_list.focus_position]
                    self.selected_message = msg_widget.message_id
                    self.replying_to = msg_widget.text
                    self.update_input_visibility()
                    # Переключаемся на ввод
                    self.focused_element = "input"
                    self.right_panel.original_widget.focus_position = 1
                return
                
            elif key == 'esc':
                if self.replying_to:
                    # Отменяем ответ
                    self.selected_message = None
                    self.replying_to = None
                    self.update_input_visibility()
                    return
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
            
            elif key == 'enter':
                if self.focused_element == "chat_list" and self.chat_walker:
                    try:
                        focused = self.chat_walker[self.chat_list.focus_position]
                        if focused.chat_id != self.current_chat_id:
                            self.current_chat_id = focused.chat_id
                            self.selected_chat_index = self.chat_list.focus_position
                            
                            # Проверяем права при открытии чата
                            await self.check_chat_permissions(focused.chat_id)
                            
                            await self.update_message_list(focused.chat_id)
                            self.focused_element = "input"
                            self.chat_widget.focus_position = 1
                            self.right_panel.original_widget.focus_position = 1
                            self.last_message_update_time = 0
                    except Exception as e:
                        print(f"Ошибка при открытии чата: {e}")
                        
                elif self.focused_element == "input" and self.current_chat_id and self.can_send_messages:
                    message = self.input_edit.get_edit_text()
                    if message.strip():
                        try:
                            # Приостанавливаем автообновление на время отправки
                            self.last_update_time = datetime.datetime.now().timestamp()
                            self.last_message_update_time = self.last_update_time
                            
                            # Создаем виджет сообщения до отправки
                            now = datetime.datetime.now()
                            msg_widget = MessageWidget(
                                message_id=0,  # Временный ID
                                text=message,
                                username="Я",
                                is_me=True,
                                send_time=now.strftime("%H:%M"),
                                status="⋯"  # Отправляется
                            )
                            
                            # Отправляем сообщение
                            sent_message = await self.telegram_client.send_message(
                                self.current_chat_id,
                                message,
                                reply_to=self.selected_message
                            )
                            
                            # Обновляем ID сообщения и добавляем в отслеживание
                            msg_widget.message_id = sent_message.id
                            self.pending_messages[sent_message.id] = msg_widget
                            
                            # Добавляем сообщение в список
                            self.message_walker.append(msg_widget)
                            self.message_list.set_focus(len(self.message_walker) - 1)
                            
                            # Очищаем поле ввода и сбрасываем ответ
                            self.input_edit.set_edit_text("")
                            self.selected_message = None
                            self.replying_to = None
                            self.update_input_visibility()
                            
                        except Exception as e:
                            print(f"Ошибка отправки сообщения: {e}")
            
            elif key == 'tab':
                if self.focused_element == "search":
                    self.focused_element = "chat_list"
                    self.left_panel.original_widget.focus_position = 2
                elif self.focused_element == "chat_list":
                    if self.current_chat_id:
                        self.focused_element = "messages"
                        self.chat_widget.focus_position = 1
                        self.right_panel.original_widget.focus_position = 0
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
                        if self.current_chat_id != focused.chat_id:
                            self.current_chat_id = focused.chat_id
                            await self.update_message_list(focused.chat_id)
                
                elif self.focused_element == "messages" and self.message_walker:
                    if key == 'up':
                        if self.message_list.focus_position > 0:
                            self.message_list.focus_position -= 1
                    else:
                        if self.message_list.focus_position < len(self.message_walker) - 1:
                            self.message_list.focus_position += 1
        
        except Exception as e:
            print(f"Ошибка обработки ввода: {e}")
            # Восстанавливаем состояние в случае ошибки
            self.focused_element = "chat_list"
            self.chat_widget.focus_position = 0
    
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
                    # Обновляем только если не в процессе отправки сообщения
                    if not self.pending_messages:
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
                    if self.current_chat_id and not self.pending_messages:
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