"""Tests for Telegram bot."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axela.infrastructure.telegram.bot import DigestBot


class TestDigestBot:
    """Tests for DigestBot."""

    @pytest.fixture
    def bot(self) -> DigestBot:
        """Return DigestBot instance."""
        return DigestBot(token="test-token-123")

    @pytest.fixture
    def mock_update(self) -> MagicMock:
        """Return mock Telegram Update."""
        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        return update

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Return mock Telegram context."""
        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()
        return context

    def test_init(self, bot: DigestBot) -> None:
        """Test bot initialization."""
        assert bot._token == "test-token-123"
        assert bot._app is None
        assert bot._chat_id is None
        assert bot._digest_trigger is None
        assert bot._status_func is None

    def test_set_chat_id(self, bot: DigestBot) -> None:
        """Test set_chat_id method."""
        bot.set_chat_id(12345)
        assert bot._chat_id == 12345

        bot.set_chat_id(None)
        assert bot._chat_id is None

    def test_set_digest_trigger(self, bot: DigestBot) -> None:
        """Test set_digest_trigger method."""

        async def trigger() -> str:
            return "digest content"

        bot.set_digest_trigger(trigger)
        assert bot._digest_trigger == trigger

    def test_set_status_func(self, bot: DigestBot) -> None:
        """Test set_status_func method."""

        async def status() -> str:
            return "status text"

        bot.set_status_func(status)
        assert bot._status_func == status

    def test_is_running_false_when_not_started(self, bot: DigestBot) -> None:
        """Test is_running returns False when bot not started."""
        assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_start_creates_application(self, bot: DigestBot) -> None:
        """Test start method creates application."""
        with patch("axela.infrastructure.telegram.bot.Application") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.updater = AsyncMock()
            mock_app.add_handler = MagicMock()
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app

            await bot.start()

            assert bot._app is not None
            assert bot.is_running is True
            mock_app.initialize.assert_called_once()
            mock_app.start.assert_called_once()
            mock_app.updater.start_polling.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_does_nothing_if_already_started(self, bot: DigestBot) -> None:
        """Test start method does nothing if bot already running."""
        bot._app = MagicMock()  # Simulate already started

        await bot.start()

        # Should not create new app
        assert bot._app is not None

    @pytest.mark.asyncio
    async def test_stop_shuts_down_application(self, bot: DigestBot) -> None:
        """Test stop method shuts down application."""
        mock_app = AsyncMock()
        mock_app.updater = AsyncMock()
        bot._app = mock_app

        await bot.stop()

        mock_app.updater.stop.assert_called_once()
        mock_app.stop.assert_called_once()
        mock_app.shutdown.assert_called_once()
        assert bot._app is None
        assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_started(self, bot: DigestBot) -> None:
        """Test stop method does nothing if bot not started."""
        await bot.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_send_message_returns_none_if_not_started(self, bot: DigestBot) -> None:
        """Test send_message returns None if bot not started."""
        result = await bot.send_message("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_returns_none_if_no_chat_id(self, bot: DigestBot) -> None:
        """Test send_message returns None if chat_id not configured."""
        bot._app = MagicMock()

        result = await bot.send_message("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_success(self, bot: DigestBot) -> None:
        """Test send_message sends message and returns message ID."""
        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        bot._app = MagicMock()
        bot._app.bot = mock_bot
        bot._chat_id = 99999

        result = await bot.send_message("Hello!", parse_mode="HTML")

        assert result == 12345
        mock_bot.send_message.assert_called_once_with(chat_id=99999, text="Hello!", parse_mode="HTML")

    @pytest.mark.asyncio
    async def test_send_message_handles_exception(self, bot: DigestBot) -> None:
        """Test send_message returns None on exception."""
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("Network error"))

        bot._app = MagicMock()
        bot._app.bot = mock_bot
        bot._chat_id = 99999

        result = await bot.send_message("Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_error(self, bot: DigestBot) -> None:
        """Test send_error formats error message correctly."""
        mock_message = MagicMock()
        mock_message.message_id = 1

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        bot._app = MagicMock()
        bot._app.bot = mock_bot
        bot._chat_id = 99999

        await bot.send_error("Something went wrong")

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert "Error" in call_args.kwargs["text"]
        assert "Something went wrong" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_start_sends_welcome_message(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_start sends welcome message with chat ID."""
        await bot._handle_start(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 12345
        assert "Welcome to Axela" in call_args.kwargs["text"]
        assert "12345" in call_args.kwargs["text"]  # chat ID shown

    @pytest.mark.asyncio
    async def test_handle_start_returns_if_no_effective_chat(
        self,
        bot: DigestBot,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_start returns early if no effective_chat."""
        update = MagicMock()
        update.effective_chat = None

        await bot._handle_start(update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_now_unauthorized_user(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_now rejects unauthorized user."""
        bot._chat_id = 99999  # Different from mock_update's 12345

        await bot._handle_now(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "not authorized" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_now_no_digest_trigger(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_now rejects when no digest trigger configured."""
        bot._chat_id = 12345  # Matches mock_update
        bot._digest_trigger = None

        await bot._handle_now(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "not configured" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_now_success(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_now triggers digest and sends result."""
        bot._chat_id = 12345

        async def trigger() -> str:
            return "<b>Morning Digest</b>\n\nNo updates"

        bot._digest_trigger = trigger

        await bot._handle_now(mock_update, mock_context)

        # Should have 2 calls: "Collecting updates..." and the digest
        assert mock_context.bot.send_message.call_count == 2

        # Check second call has digest content
        last_call = mock_context.bot.send_message.call_args_list[1]
        assert "Morning Digest" in last_call.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_now_handles_error(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_now handles digest trigger errors."""
        bot._chat_id = 12345

        async def failing_trigger() -> str:
            raise ValueError("Database connection failed")

        bot._digest_trigger = failing_trigger

        await bot._handle_now(mock_update, mock_context)

        # Should have 2 calls: "Collecting..." and error message
        assert mock_context.bot.send_message.call_count == 2

        last_call = mock_context.bot.send_message.call_args_list[1]
        assert "Failed to generate digest" in last_call.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_status_unauthorized_user(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_status rejects unauthorized user."""
        bot._chat_id = 99999  # Different from mock_update's 12345

        await bot._handle_status(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "not authorized" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_status_default_status(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_status returns default status when no status_func."""
        bot._chat_id = 12345
        bot._status_func = None

        await bot._handle_status(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "Axela Status" in call_args.kwargs["text"]
        assert "Bot is running" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_status_custom_status(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_status uses custom status function."""
        bot._chat_id = 12345

        async def status_func() -> str:
            return "<b>Custom Status</b>\n\n5 sources active"

        bot._status_func = status_func

        await bot._handle_status(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "Custom Status" in call_args.kwargs["text"]
        assert "5 sources active" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_status_handles_error(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_status handles status function errors."""
        bot._chat_id = 12345

        async def failing_status() -> str:
            raise RuntimeError("Status unavailable")

        bot._status_func = failing_status

        await bot._handle_status(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "Failed to get status" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handle_help(
        self,
        bot: DigestBot,
        mock_update: MagicMock,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_help sends help message."""
        await bot._handle_help(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "Available Commands" in text
        assert "/now" in text
        assert "/status" in text
        assert "/help" in text

    @pytest.mark.asyncio
    async def test_handle_help_returns_if_no_effective_chat(
        self,
        bot: DigestBot,
        mock_context: MagicMock,
    ) -> None:
        """Test _handle_help returns early if no effective_chat."""
        update = MagicMock()
        update.effective_chat = None

        await bot._handle_help(update, mock_context)

        mock_context.bot.send_message.assert_not_called()
