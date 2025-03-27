# Telegram TUI Client

Консольный клиент Telegram на базе urwid с поддержкой:
- Просмотра чатов и сообщений
- Поиска по чатам
- Навигации с помощью клавиатуры
- Поддержки папок (Архив)
- Корректного отображения эмодзи и Unicode

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/talc.git
cd talc
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Скопируйте `.env.example` в `.env`:
```bash
cp .env.example .env
```

5. Получите API ключи на https://my.telegram.org/apps и добавьте их в `.env`

## Запуск

```bash
python main_urwid.py
```

## Управление

- Tab: Переключение фокуса между поиском и списком чатов
- ↑↓: Выбор чата
- Enter: Открыть выбранный чат
- Esc: Вернуться к списку чатов
- /: Быстрый доступ к поиску
- []: Переключение между основными чатами и архивом
- Q: Выход

## Структура проекта

```
talc/
├── main_urwid.py          # Основной файл запуска
├── requirements.txt       # Зависимости проекта
├── .env.example          # Пример конфигурации
├── .env                  # Конфигурация (не включена в git)
└── urwid_client/        # Основной код приложения
    ├── __init__.py
    └── telegram_tui.py  # Реализация клиента
```

## Лицензия

MIT
