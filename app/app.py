from telethon import TelegramClient, events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical, Container
from textual.widgets import Placeholder, Label, Static, Rule, Input, Button
from widgets.chat import Chat
from widgets.dialog import Dialog
from telegram.client import TelegramClientWrapper
from tokens import api_id, api_hash

class TelegramTUI(App):
    CSS_PATH = "../tcss/style.tcss"

    def __init__(self):
        super().__init__()
        self.telegram_client = TelegramClientWrapper(api_id, api_hash, self.handler)

    async def on_mount(self) -> None:
        await self.telegram_client.connect()
        await self.update_chat_list()

    async def handler(self, event):
        await self.update_chat_list()

    async def update_chat_list(self):
        dialogs = await self.telegram_client.get_dialogs(limit=10)
        chat_container = self.query_one("#main_container").query_one("#chats").query_one("#chat_container")
        chat_container.query(Chat).remove()

        for dialog in dialogs:
            name = dialog.name
            msg = dialog.message.message
            chat = Chat(name, msg, id=f"chat-{dialog.id}")
            chat_container.mount(chat)

    def compose(self) -> ComposeResult:
        with Horizontal(id="main_container"):
            with Horizontal(id="chats"):
                yield VerticalScroll(Static(id="chat_container"))
                yield Rule("vertical")
            yield Dialog()

    async def on_exit_app(self):
        await self.telegram_client.disconnect()
        return super()._on_exit_app()
