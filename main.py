#!/usr/bin/python
"""Файл инициализации приложения"""

from src.app import TelegramTUI

if __name__ == "__main__":
    tg = TelegramTUI()
    tg.run()
