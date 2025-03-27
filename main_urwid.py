#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram TUI Client
Консольный клиент Telegram на базе urwid
"""

import asyncio
import os
from urwid_client.telegram_tui import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Ошибка при запуске приложения: {e}") 