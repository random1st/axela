"""Telegram bot for digest delivery and commands."""

from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = structlog.get_logger()

# Type alias for digest trigger function
DigestTriggerFunc = Callable[[], Coroutine[Any, Any, str]]

# Type alias for Application with all type parameters (BT, CCT, UD, CD, BD, JQ)
ApplicationType = Application[Any, Any, Any, Any, Any, Any]


class DigestBot:
    """Telegram bot for sending digests and handling commands."""

    def __init__(self, token: str) -> None:
        """Initialize the bot.

        Args:
            token: Telegram bot token from @BotFather

        """
        self._token = token
        self._app: ApplicationType | None = None
        self._chat_id: int | None = None
        self._digest_trigger: DigestTriggerFunc | None = None
        self._status_func: Callable[[], Coroutine[Any, Any, str]] | None = None

    def set_chat_id(self, chat_id: int | None) -> None:
        """Set the chat ID to send messages to.

        Args:
            chat_id: Telegram chat ID

        """
        self._chat_id = chat_id

    def set_digest_trigger(self, func: DigestTriggerFunc) -> None:
        """Set the function to trigger an on-demand digest.

        Args:
            func: Async function that triggers digest and returns formatted content

        """
        self._digest_trigger = func

    def set_status_func(self, func: Callable[[], Coroutine[Any, Any, str]]) -> None:
        """Set the function to get bot status.

        Args:
            func: Async function that returns status string

        """
        self._status_func = func

    async def start(self) -> None:
        """Start the bot."""
        if self._app is not None:
            logger.warning("Bot already started")
            return

        self._app = Application.builder().token(self._token).build()

        # Register command handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("now", self._handle_now))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("help", self._handle_help))

        await self._app.initialize()
        await self._app.start()
        if self._app.updater is not None:
            await self._app.updater.start_polling()

        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Stop the bot."""
        if self._app is None:
            return

        if self._app.updater is not None:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None

        logger.info("Telegram bot stopped")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> int | None:
        """Send a message to the configured chat.

        Args:
            text: Message text
            parse_mode: Telegram parse mode (HTML, Markdown, etc.)

        Returns:
            Message ID if sent successfully, None otherwise

        """
        if self._app is None:
            logger.error("Bot not started")
            return None

        if self._chat_id is None:
            logger.error("Chat ID not configured")
            return None

        try:
            message = await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return int(message.message_id)
        except Exception as e:
            logger.exception("Failed to send message", error=str(e))
            return None

    async def send_error(self, error_message: str) -> None:
        """Send an error alert to the configured chat.

        Args:
            error_message: Error description

        """
        text = f"⚠️ <b>Error</b>\n\n{error_message}"
        await self.send_message(text)

    async def _handle_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /start command."""
        if update.effective_chat is None:
            return

        chat_id = update.effective_chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "👋 <b>Welcome to Axela!</b>\n\n"
                "I aggregate updates from your work tools and send you digests.\n\n"
                f"Your chat ID is: <code>{chat_id}</code>\n\n"
                "Use /help to see available commands."
            ),
            parse_mode="HTML",
        )
        logger.info("Start command received", chat_id=chat_id)

    async def _handle_now(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /now command - trigger immediate digest."""
        if update.effective_chat is None:
            return

        chat_id = update.effective_chat.id

        if self._chat_id is not None and chat_id != self._chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ You are not authorized to use this bot.",
            )
            return

        if self._digest_trigger is None:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Digest service not configured.",
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Collecting updates...",
        )

        try:
            content = await self._digest_trigger()
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("Failed to generate digest", error=str(e))
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Failed to generate digest: {e}",
            )

    async def _handle_status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /status command - show bot status."""
        if update.effective_chat is None:
            return

        chat_id = update.effective_chat.id

        if self._chat_id is not None and chat_id != self._chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ You are not authorized to use this bot.",
            )
            return

        if self._status_func is None:
            status_text = (
                "📊 <b>Axela Status</b>\n\n"
                "✅ Bot is running\n"
                f"💬 Chat ID: <code>{self._chat_id or 'Not configured'}</code>"
            )
        else:
            try:
                status_text = await self._status_func()
            except Exception as e:
                status_text = f"❌ Failed to get status: {e}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=status_text,
            parse_mode="HTML",
        )

    async def _handle_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /help command."""
        if update.effective_chat is None:
            return

        help_text = (
            "📖 <b>Available Commands</b>\n\n"
            "/now - Get an immediate digest of all updates\n"
            "/status - Show bot status and configuration\n"
            "/help - Show this help message"
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=help_text,
            parse_mode="HTML",
        )

    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._app is not None
