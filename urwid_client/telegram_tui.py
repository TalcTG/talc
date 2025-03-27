#!/usr/bin/env python3
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
        
        # Создаем виджеты
        avatar = urwid.AttrMap(
            urwid.Text(f" {first_letter} ", align='center'),
            'chat' if not self.is_selected else 'chat_selected'
        )
        
        content = urwid.Pile([
            urwid.AttrMap(
                urwid.Text(name),
                'chat_name' if not self.is_selected else 'chat_selected'
            ),
            urwid.AttrMap(
                urwid.Text(msg),
                'chat_message' if not self.is_selected else 'chat_selected'
            )
        ])
        
        self.widget = urwid.AttrMap(
            urwid.Columns([
                ('fixed', 3, avatar),
                content
            ]),
            'chat' if not self.is_selected else 'chat_selected'
        )
    
    def selectable(self):
        return True
    
    def keypress(self, size, key):
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
        self.search_edit = urwid.Edit(('header', "Поиск: "))
        self.chat_list = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.message_list = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.input_edit = urwid.Edit(('header', "Сообщение: "))
        
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
        
        self.chat_widget = urwid.Columns([
            ('weight', 30, urwid.Pile([
                ('pack', urwid.Text(('help', "Tab - переключение фокуса, ↑↓ - выбор чата, Enter - открыть чат, Esc - назад, / - поиск, [] - папки"), align='center')),
                ('pack', self.search_edit),
                self.chat_list
            ])),
            ('weight', 70, urwid.Pile([
                self.message_list,
                ('pack', self.input_edit)
            ]))
        ])
        
        # Создаем основной виджет
        self.main_widget = urwid.Frame(
            self.auth_widget,
            header=urwid.AttrMap(
                urwid.Text(' Telegram TUI', align='center'),
                'header'
            ),
            footer=urwid.AttrMap(
                urwid.Text(' Q: Выход | Tab: Переключение фокуса | Enter: Выбор', align='center'),
                'footer'
            )
        )
        
        # Состояние чатов
        self.current_folder = None
        self.folders = []
        self.chats = []
        self.selected_chat_index = 0
        self.focused_element = "chat_list"  # chat_list, search
    
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
            # Получаем диалоги
            dialogs = await self.telegram_client.get_dialogs(
                limit=100,
                archived=False,
                folder=self.current_folder
            )
            
            # Фильтруем по поисковому запросу
            search_query = normalize_text(self.search_edit.get_edit_text().lower())
            if search_query:
                dialogs = [
                    d for d in dialogs 
                    if search_query in normalize_text(str(d.name)).lower()
                ]
            
            # Очищаем список
            self.chat_list.body.clear()
            
            # Добавляем чаты
            for i, dialog in enumerate(dialogs):
                chat = ChatWidget(
                    chat_id=dialog.id,
                    name=str(dialog.name),
                    message=str(dialog.message.message if dialog.message else ""),
                    is_selected=(i == self.selected_chat_index),
                    folder=1 if self.current_folder else 0
                )
                self.chat_list.body.append(chat)
            
        except Exception as e:
            print(f"Ошибка обновления чатов: {e}")
    
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
            self.message_list.body.clear()
            
            # Добавляем сообщения
            for msg in reversed(messages):
                try:
                    is_me = msg.from_id.user_id == me.id
                except:
                    is_me = False
                
                message = MessageWidget(
                    text=str(msg.message),
                    username=str(msg.sender.first_name if msg.sender else "Неизвестный"),
                    is_me=is_me,
                    send_time=msg.date.strftime("%H:%M")
                )
                self.message_list.body.append(message)
            
            # Прокручиваем к последнему сообщению
            self.message_list.set_focus(len(self.message_list.body) - 1)
            
        except Exception as e:
            print(f"Ошибка обновления сообщений: {e}")
    
    async def handle_chat_input(self, key):
        """Обработка ввода в экране чатов"""
        if key == 'tab':
            # Переключаем фокус
            if self.focused_element == "chat_list":
                self.focused_element = "search"
                self.chat_widget.set_focus_column(0)
                self.chat_widget.contents[0][0].set_focus(1)  # Фокус на поиск
            else:
                self.focused_element = "chat_list"
                self.chat_widget.set_focus_column(0)
                self.chat_widget.contents[0][0].set_focus(2)  # Фокус на список чатов
        
        elif key == '/':
            # Фокус на поиск
            self.focused_element = "search"
            self.chat_widget.set_focus_column(0)
            self.chat_widget.contents[0][0].set_focus(1)
        
        elif key == '[':
            # Переход в предыдущую папку
            if self.current_folder is not None:
                self.current_folder = None
                self.selected_chat_index = 0
                await self.update_chat_list()
        
        elif key == ']':
            # Переход в следующую папку
            if self.current_folder is None and self.folders:
                self.current_folder = 1  # Архив
                self.selected_chat_index = 0
                await self.update_chat_list()
        
        elif key == 'enter' and self.focused_element == "chat_list":
            # Открываем выбранный чат
            focused = self.chat_list.get_focus()[0]
            if focused:
                await self.update_message_list(focused.chat_id)
                self.chat_widget.set_focus_column(1)  # Переключаемся на сообщения
        
        elif key == 'esc':
            # Возвращаемся к списку чатов
            self.chat_widget.set_focus_column(0)
            self.focused_element = "chat_list"
    
    def unhandled_input(self, key):
        """Обработка необработанных нажатий клавиш"""
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        
        # Создаем задачу для асинхронной обработки
        if self.current_screen == 'auth':
            asyncio.create_task(self.handle_auth(key))
        else:
            asyncio.create_task(self.handle_chat_input(key))
    
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
    
    # Если сессия существует и заблокирована, удаляем её
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            print("Старая сессия удалена")
        except Exception as e:
            print(f"Ошибка удаления сессии: {e}")
    
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