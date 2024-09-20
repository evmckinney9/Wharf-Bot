import io
from random import choice

from discord import FFmpegPCMAudio
from elevenlabs import generate, set_api_key, voices
from elevenlabs.api import VoiceSettings
from tenacity import retry, stop_after_attempt, wait_exponential


# Define the retry parameters
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def robust_voices():
    return voices()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def robust_generate(text, voice, model, stream):
    return generate(text=text, voice=voice, model=model, stream=stream)


class ElevenLabsAPIError(Exception):
    """Custom exception for ElevenLabs API errors."""

    pass


async def get_elevenlabs_audio(bot, message: str):
    bot.logger.info("Generating audio stream...")
    try:
        set_api_key(bot.config["elevenlabs_api_key"])

        # get voice ID, or a random voice if none (or on failure)
        voice_list = robust_voices()
        voice = next((v for v in voice_list if v.name == bot.NAME), None)
        if not voice:
            voice = choice(voice_list)
        # voice = choice(voice_list)

        # configure voice settings
        voice.settings = VoiceSettings(
            stability=0.3,
            similarity_boost=0.85,
            style=0.5,
            use_speaker_boost=False,
        )
        audio_stream = robust_generate(
            text=message,
            voice=voice,
            model="eleven_monolingual_v1",
            stream=True,
        )
        audio = b""
        for chunk in audio_stream:
            if chunk is not None:
                audio += chunk

        # Convert bytes to AudioSource using FFmpegPCMAudio
        audio_source = FFmpegPCMAudio(
            executable="ffmpeg", source=io.BytesIO(audio), pipe=True
        )

        return audio_source

    except Exception as e:
        # Raise a custom exception.
        raise ElevenLabsAPIError from e
