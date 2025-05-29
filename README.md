# Тальк

Тальк — клиент Telegram с текстовым пользовательским интерфейсом, написанный на Python, Telethon и Textual.

Будьте добры, по-русски | [In English, please](readme/README-en.md)

## Требования

- Python 3.12
- pyenv (рекомендуется для управления версиями Python)

## Установка

1. Установите Python 3.12 с помощью pyenv:
```bash
pyenv install 3.12
pyenv local 3.12
```

2. Создайте и активируйте виртуальное окружение:
```bash
python -m venv .venv
source .venv/bin/activate  # для Linux/macOS
# или
.venv\Scripts\activate  # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте переменные окружения:
```bash
cp .env.example .env
# Настройте .env файл и добавьте свои API ключи
# Получите ключи на https://my.telegram.org/apps
```

## Запуск

```bash
./main.py
```
