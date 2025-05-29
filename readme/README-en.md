# Talc

Talc is a Telegram client with TUI, written in Python, Telethon and Textual.

[Будьте добры, по-русски](../README.md) | In English, please

## Requirements

- Python 3.12
- pyenv (recommended for managing Python versions)

## Installation

1. Install Python 3.12 via pyenv:
```bash
pyenv install 3.12
pyenv local 3.12
```

2. Create and activate virtual enviroment:
```bash
python -m venv .venv
source .venv/bin/activate # for Linux/macOS
# or
.venv\Scripts\activate    # for Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure enviroment variables:
```bash
cp .env.example .env
# Configure .env file and add your API-keys
# Get keys on https://my.telegram.org/apps
```

## Run

```bash
./main.py
```
