import asyncio

import aiohttp
import discord
from discord.ext import commands

from eddy_bot.services.chatgpt import get_chatgpt_response

MESSAGE_LIMIT = 10


class Chat(commands.Cog, name="chat"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """The code in this event is executed every time someone sends a
        message, with or without the prefix.

        :param message: The message that was sent.
        """
        if message.author == self.bot.user or message.author.bot:
            return

        # check if the message tags the bot with @bot
        if not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            response = await self.build_response(self.bot, message)
        await message.channel.send(response)

    @staticmethod
    async def build_response(bot, message: discord.Message) -> str:
        """Build a response from the chatgpt model."""
        message_list = await Chat.construct_chat_history(bot, message.channel)
        bot.logger.debug(message_list)
        response = await get_chatgpt_response(
            bot=bot,
            message_list=message_list,
        )
        bot.logger.info(f"Response: {response}")
        return response

    @staticmethod
    async def fetch_channel_history(
        channel: discord.TextChannel,
        limit: int = None,
        after: discord.Message = None,
        retries: int = 3,
        delay: int = 5,
    ) -> list:
        """Fetch channel history with optional retries on failure."""

        for i in range(retries):
            try:
                return [m async for m in channel.history(limit=limit, after=after)]
            except aiohttp.client_exceptions.ClientConnectorError:
                if i < retries - 1:
                    await asyncio.sleep(delay)
                    continue
                raise

    @staticmethod
    async def construct_chat_history(bot, channel: discord.TextChannel) -> tuple:
        """Construct a list of message history and mentions."""
        message_list = await Chat.fetch_channel_history(channel, limit=MESSAGE_LIMIT)
        message_list.sort(key=lambda m: m.created_at)

        clear_indices = [i for i, m in enumerate(message_list) if m.content == "/clear"]
        if clear_indices:
            last_clear_idx = clear_indices[-1]
            message_list = message_list[last_clear_idx + 1 :]

        message_json = [
            {"role": "assistant", "content": m.content}
            if m.author == bot.user
            else {
                "role": "user",
                "content": f"@{m.author.display_name}: {m.content}",
            }
            for m in message_list
        ]

        return message_json


async def setup(bot) -> None:
    await bot.add_cog(Chat(bot))
