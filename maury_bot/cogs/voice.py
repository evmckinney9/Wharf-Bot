import asyncio
import time
from collections import deque

from discord.ext import commands
from discord.ext.commands import Context

from maury_bot.services.chatgpt import get_chatgpt_reddit_message, get_chatgpt_response
from maury_bot.services.elevenlabs import ElevenLabsAPIError, get_elevenlabs_audio
from maury_bot.services.reddit import get_reddit_comments


class Voice(commands.Cog, name="voice"):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.queue = deque()
        self.lock = asyncio.Lock()
        self.last_voice_command_time = None
        self.cooldown_period = 10  # 10 seconds
        self.disconnect_task = None

    async def play_audio(self, ctx, audio_source) -> None:
        """Joins voice channel, plays audio, and then starts a disconnect cooldown."""
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel to use this command.")
            return

        # Check if the bot is already connected to the voice channel
        voice_client = ctx.guild.voice_client
        if not voice_client:
            voice_client = await ctx.author.voice.channel.connect()

        voice_client.play(audio_source)

        while voice_client.is_playing():
            await asyncio.sleep(1)

        if self.disconnect_task is None:
            self.disconnect_task = asyncio.create_task(self.wait_and_disconnect(ctx))

    async def wait_and_disconnect(self, ctx):
        """Wait for the cooldown period and then disconnect if no new commands were received."""
        await asyncio.sleep(self.cooldown_period)

        # Check if cooldown has expired
        if time.time() - self.last_voice_command_time > self.cooldown_period:
            voice_client = ctx.guild.voice_client
            if voice_client and not voice_client.is_playing():
                await voice_client.disconnect()
            self.disconnect_task = None

    async def handle_speak(self, ctx, audio_task):
        """Processes and plays the requested speech."""
        self.last_voice_command_time = time.time()  # Refresh the last command time

        async with self.lock:
            audio_source = await audio_task
            await self.play_audio(ctx, audio_source)

        await self.check_queue(ctx)

    async def check_queue(self, ctx):
        """Processes the next message in the queue."""
        if self.queue:
            await self.handle_speak(ctx, self.queue.popleft())

    async def add_to_queue_or_speak(self, ctx, audio_task):
        """Determines whether to queue the message or process immediately."""
        # Check if there's any voice client playing audio
        is_voice_active = any(vc.is_playing() for vc in self.bot.voice_clients)

        if is_voice_active:
            self.queue.append(audio_task)
        else:
            await self.handle_speak(ctx, audio_task)

    @commands.hybrid_command(
        name="speak",
        description="Bot joins voice call and speaks the model response.",
    )
    async def speak(self, ctx: Context, *, message: str) -> None:
        try:
            await ctx.defer(ephemeral=False)

            message = await get_chatgpt_response(
                self.bot, [{"role": "user", "content": message}]
            )

            # replace newline characters with <break time="0.5s"/>
            voice_message = message.replace("\n\n", '<break time="0.75s"/>')
            self.bot.logger.debug(f"Response from model: {message}")

            audio_task = asyncio.create_task(
                get_elevenlabs_audio(self.bot, voice_message)
            )
            await self.add_to_queue_or_speak(ctx, audio_task)
            await ctx.send(message)
        except ElevenLabsAPIError as e:
            self.bot.logger.error(f"Error in speak command: {repr(e)}")
            await ctx.send("Sorry, there was an error processing your request.")

    @commands.hybrid_command(
        name="recite",
        description="Bot joins voice call and recites provided text.",
    )
    async def recite(self, ctx: Context, *, message: str) -> None:
        try:
            await ctx.defer(ephemeral=False)

            audio_task = asyncio.create_task(get_elevenlabs_audio(self.bot, message))
            await self.add_to_queue_or_speak(ctx, audio_task)
            await ctx.send(message)
        except ElevenLabsAPIError as e:
            self.bot.logger.error(f"Error in recite command: {repr(e)}")
            await ctx.send("Sorry, there was an error processing your request.")

    @commands.hybrid_command(
            name="smark",
            description="Bot joins voice call and speaks the model response from a Reddit thread.",
        )
    async def smark(self, ctx: Context, thread_url: str) -> None:
        try:
            await ctx.defer(ephemeral=False)

            # Fetch comments from the Reddit thread
            comments = await get_reddit_comments(thread_url)

            # Generate response using ChatGPT
            message = await get_chatgpt_reddit_message(self.bot, comments)

            # Synthesize audio from the response
            audio_task = asyncio.create_task(
                get_elevenlabs_audio(self.bot, message)
            )

            # Speak the synthesized audio in the voice channel
            await self.add_to_queue_or_speak(ctx, audio_task)

            # Send the original message as a text response
            await ctx.send(message)
        except Exception as e:
            self.bot.logger.error(f"Error in reddit command: {repr(e)}")
            await ctx.send("Sorry, there was an error processing your request.")



async def setup(bot) -> None:
    """Adds the Voice cog to the bot."""
    await bot.add_cog(Voice(bot))
