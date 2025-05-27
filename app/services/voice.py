import asyncio
import os
import re
import time
import wave
from datetime import datetime
from typing import Union
from xml.sax.saxutils import unescape

import edge_tts
from edge_tts import SubMaker, submaker
from loguru import logger
from moviepy.video.tools import subtitles
from openai import OpenAI
import requests
from google import genai
from google.genai import types

from app.config import config
from app.utils import utils


def mktimestamp(time_in_seconds: float) -> str:
    """Convert time in seconds to SRT timestamp format"""
    hours = int(time_in_seconds // 3600)
    minutes = int((time_in_seconds % 3600) // 60)
    seconds = int(time_in_seconds % 60)
    milliseconds = int((time_in_seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def get_all_voices() -> list[str]:
    """Get all available TTS voices (OpenAI, OpenAI FM, and Gemini)"""
    voices = []

    # Add OpenAI voices
    voices.extend([
        "openai-alloy-Male",
        "openai-echo-Male",
        "openai-fable-Female",
        "openai-onyx-Male",
        "openai-nova-Female",
        "openai-shimmer-Female",
        "openai_fm-alloy-Unisex",
        "openai_fm-ash-Unisex",
        "openai_fm-ballad-Unisex",
        "openai_fm-coral-Unisex",
        "openai_fm-echo-Unisex",
        "openai_fm-fable-Unisex",
        "openai_fm-onyx-Unisex",
        "openai_fm-nova-Unisex",
        "openai_fm-sage-Unisex",
        "openai_fm-shimmer-Unisex",
        "openai_fm-verse-Unisex"
    ])

    # Add Gemini voices - based on actual API supported voices
    voices.extend([
        "gemini-achernar-Unisex",
        "gemini-achird-Unisex",
        "gemini-algenib-Unisex",
        "gemini-algieba-Unisex",
        "gemini-alnilam-Unisex",
        "gemini-aoede-Unisex",
        "gemini-autonoe-Unisex",
        "gemini-callirrhoe-Unisex",
        "gemini-charon-Unisex",
        "gemini-despina-Unisex",
        "gemini-enceladus-Unisex",
        "gemini-erinome-Unisex",
        "gemini-fenrir-Unisex",
        "gemini-gacrux-Unisex",
        "gemini-iapetus-Unisex",
        "gemini-kore-Unisex",
        "gemini-laomedeia-Unisex",
        "gemini-leda-Unisex",
        "gemini-orus-Unisex",
        "gemini-puck-Unisex",
        "gemini-pulcherrima-Unisex",
        "gemini-rasalgethi-Unisex",
        "gemini-sadachbia-Unisex",
        "gemini-sadaltager-Unisex",
        "gemini-schedar-Unisex",
        "gemini-sulafat-Unisex",
        "gemini-umbriel-Unisex",
        "gemini-vindemiatrix-Unisex",
        "gemini-zephyr-Unisex",
        "gemini-zubenelgenubi-Unisex"
    ])

    return voices


# Keep for backward compatibility
def get_all_azure_voices(filter_locals=None) -> list[str]:
    """Backward compatibility function - now returns all voices"""
    return get_all_voices()


def parse_voice_name(name: str):
    # zh-CN-XiaoyiNeural-Female
    # zh-CN-YunxiNeural-Male
    # zh-CN-XiaoxiaoMultilingualNeural-V2-Female
    name = name.replace("-Female", "").replace("-Male", "").strip()
    return name


def is_azure_v2_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""


def is_openai_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.startswith("openai-"):
        return voice_name.replace("openai-", "").strip()
    return ""


def is_openai_fm_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.startswith("openai_fm-"):
        return voice_name.replace("openai_fm-", "").strip()
    return ""


def is_gemini_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.startswith("gemini-"):
        # Extract just the voice name (e.g., "Zubenelgenubi" from "gemini-Zubenelgenubi-Unisex")
        voice_part = voice_name.replace("gemini-", "").strip()
        # Remove gender suffix if present
        if "-" in voice_part:
            voice_part = voice_part.split("-")[0]
        return voice_part.lower()  # Gemini API expects lowercase
    return ""


def tts(
    text: str, voice_name: str, voice_rate: float, voice_file: str
) -> Union[SubMaker, None]:
    # Check if voice name explicitly indicates a provider
    openai_voice = is_openai_voice(voice_name)
    gemini_voice = is_gemini_voice(voice_name)

    if openai_voice:
        return openai_tts(text, openai_voice, voice_rate, voice_file)
    elif is_openai_fm_voice(voice_name):
        return openai_fm_tts(text, voice_name, voice_rate, voice_file)
    elif gemini_voice:
        return gemini_tts(text, voice_name, voice_rate, voice_file)

    # If no provider is indicated in the voice name, use the configured provider
    tts_provider = config.app.get("tts_provider", "gemini").lower()
    if tts_provider == "openai" and not openai_voice:
        # For OpenAI, use the voice name as is (alloy, echo, etc.)
        # If it's an Azure voice, extract just the name part
        if "-" in voice_name:
            # This is likely an Azure voice, so we'll use a default OpenAI voice
            logger.warning(f"Using default OpenAI voice 'alloy' instead of Azure voice {voice_name}")
            return openai_tts(text, "alloy", voice_rate, voice_file)
        else:
            return openai_tts(text, voice_name, voice_rate, voice_file)
    elif tts_provider == "openai_fm":
        return openai_fm_tts(text, voice_name, voice_rate, voice_file)
    elif tts_provider == "gemini":
        return gemini_tts(text, voice_name, voice_rate, voice_file)

    # Default to Gemini TTS
    return gemini_tts(text, voice_name, voice_rate, voice_file)


def convert_rate_to_percent(rate: float) -> str:
    if rate == 1.0:
        return "+0%"
    percent = round((rate - 1.0) * 100)
    if percent > 0:
        return f"+{percent}%"
    else:
        return f"{percent}%"


def openai_tts(text: str, voice_name: str, voice_rate: float, voice_file: str) -> Union[SubMaker, None]:
    text = text.strip()

    # Extract the actual voice name from the format "openai-voice-Gender"
    if voice_name.startswith("openai-"):
        parts = voice_name.split("-")
        if len(parts) >= 2:
            voice_name = parts[1]  # Get the actual voice name (alloy, echo, etc.)

    for i in range(3):
        try:
            logger.info(f"start OpenAI TTS, voice name: {voice_name}, try: {i + 1}")

            # Get OpenAI API key from config
            api_key = config.app.get("openai_api_key", "")
            base_url = config.app.get("openai_base_url", "")

            if not api_key:
                logger.error("OpenAI API key not found in config")
                return None

            # Create OpenAI client
            client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)

            # Create SubMaker for subtitle generation
            sub_maker = SubMaker()

            # Adjust speed based on voice_rate
            speed = voice_rate

            # Get TTS model from config or use default
            tts_model = config.app.get("openai_tts_model", "tts-1")

            # Call OpenAI TTS API with streaming response
            with client.audio.speech.with_streaming_response.create(
                model=tts_model,  # tts-1 or tts-1-hd for higher quality
                voice=voice_name,  # alloy, echo, fable, onyx, nova, or shimmer
                input=text,
                speed=speed
            ) as response:
                # Save the audio file
                with open(voice_file, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

            # Since OpenAI TTS doesn't provide word boundaries, we need to estimate them
            # This is a simple approach - for better results, you might need to use a speech recognition service
            words = text.split()
            total_chars = len(text)

            # Get file size to estimate duration
            file_size = os.path.getsize(voice_file)
            # Rough estimate: ~10KB per second for MP3
            estimated_duration_ms = (file_size / 10000) * 1000

            # Create approximate word boundaries
            offset = 0
            for word in words:
                # Estimate word duration based on its length relative to total text
                word_duration = (len(word) / total_chars) * estimated_duration_ms
                # Create subtitle entry with timestamp tuple (start_time, end_time)
                start_time = offset / 1000  # Convert to seconds
                end_time = (offset + word_duration) / 1000  # Convert to seconds
                sub_maker.create_sub((start_time, end_time), word)
                offset += word_duration

            logger.info(f"completed, output file: {voice_file}")
            return sub_maker

        except Exception as e:
            logger.error(f"OpenAI TTS failed, error: {str(e)}")

    return None


def openai_fm_tts(text: str, voice_name: str, voice_rate: float, voice_file: str) -> Union[SubMaker, None]:
    voice_name = is_openai_fm_voice(voice_name)
    if not voice_name:
        logger.error(f"invalid OpenAI FM voice name: {voice_name}")
        raise ValueError(f"invalid OpenAI FM voice name: {voice_name}")
    text = text.strip()

    for i in range(3):
        try:
            logger.info(f"start OpenAI FM TTS, voice name: {voice_name}, try: {i + 1}")

            # Prepare headers from the provided demo_openai_api.py
            headers = {
                "accept": "*/*",
                "accept-language": "vi-VN,vi;q=0.9,zh-CN;q=0.8,zh;q=0.7,fr-FR;q=0.6,fr;q=0.5,en-US;q=0.4,en;q=0.3",
                "origin": "https://www.openai.fm",
                "priority": "u=1, i",
                "referer": "https://www.openai.fm/worker-444eae9e2e1bdd6edd8969f319655e70.js",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
                "Cookie": "_ga=GA1.1.600869161.1743481050; _ga_NME7NXL4L0=GS1.1.1745957564.11.1.1745958401.0.0.0"
            }

            # Get tone from config
            tone = config.app.get("openai_fm_tone", "Calm, encouraging, and articulate")

            # Prepare prompt based on the selected tone
            if tone == "Calm, encouraging, and articulate":
                prompt = "Accent/Affect: Warm, refined, and gently instructive, reminiscent of a friendly art instructor. Tone: Calm, encouraging, and articulate, clearly describing each step with patience. Pacing: Slow and deliberate, pausing often to allow the listener to follow instructions comfortably. Emotion: Cheerful, supportive, and pleasantly enthusiastic; convey genuine enjoyment and appreciation of art. Pronunciation: Clearly articulate artistic terminology (e.g., 'brushstrokes,' 'landscape,' 'palette') with gentle emphasis. Personality Affect: Friendly and approachable with a hint of sophistication; speak confidently and reassuringly, guiding users through each painting step patiently and warmly."
            elif tone == "Friendly, clear, and reassuring":
                prompt = "Affect/personality: A cheerful guide. Tone: Friendly, clear, and reassuring, creating a calm atmosphere and making the listener feel confident and comfortable. Pronunciation: Clear, articulate, and steady, ensuring each instruction is easily understood while maintaining a natural, conversational flow. Pause: Brief, purposeful pauses after key instructions (e.g., 'cross the street' and 'turn right') to allow time for the listener to process the information and follow along. Emotion: Warm and supportive, conveying empathy and care, ensuring the listener feels guided and safe throughout the journey."
            else:  # Neutral and informative
                prompt = "Voice: Clear, authoritative, and composed, projecting confidence and professionalism. Tone: Neutral and informative, maintaining a balance between formality and approachability. Punctuation: Structured with commas and pauses for clarity, ensuring information is digestible and well-paced. Delivery: Steady and measured, with slight emphasis on key figures and deadlines to highlight critical points."

            # Prepare payload as dictionary per the demo_openai_api.py
            payload = {
                "input": text,
                "prompt": prompt,
                "voice": voice_name.split('-')[0].strip(),
                "vibe": "null"
            }

            # Make request to OpenAI FM API
            response = requests.post(
                "https://www.openai.fm/api/generate",
                headers=headers,
                data=payload,
                timeout=(30, 60)
            )

            if response.status_code != 200:
                logger.error(f"OpenAI FM TTS request failed with status code: {response.status_code}, response: {response.text}")
                continue

            # Create SubMaker for subtitle generation
            sub_maker = SubMaker()

            # Save the audio file from response content
            with open(voice_file, 'wb') as f:
                f.write(response.content)

            logger.info(f"Audio file saved successfully at: {voice_file}")

            # Since OpenAI FM TTS might not provide word boundaries, we need to estimate them
            words = text.split()
            total_chars = len(text)

            # Get file size to estimate duration
            file_size = os.path.getsize(voice_file)
            # Rough estimate: ~10KB per second for MP3
            estimated_duration_ms = (file_size / 10000) * 1000

            # Create approximate word boundaries
            offset = 0
            for word in words:
                # Estimate word duration based on its length relative to total text
                word_duration = (len(word) / total_chars) * estimated_duration_ms
                # Create subtitle entry with timestamp tuple (start_time, end_time)
                start_time = offset / 1000  # Convert to seconds
                end_time = (offset + word_duration) / 1000  # Convert to seconds
                sub_maker.create_sub((start_time, end_time), word)
                offset += word_duration

            logger.info(f"completed, output file: {voice_file}")
            return sub_maker

        except Exception as e:
            logger.error(f"OpenAI FM TTS failed, error: {str(e)}")

    return None


def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    """Helper function to save wave file for Gemini TTS"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def gemini_tts(text: str, voice_name: str, voice_rate: float, voice_file: str) -> Union[SubMaker, None]:
    voice_name = is_gemini_voice(voice_name)
    if not voice_name:
        logger.error(f"invalid Gemini voice name: {voice_name}")
        raise ValueError(f"invalid Gemini voice name: {voice_name}")
    text = text.strip()

    for i in range(3):
        try:
            logger.info(f"start Gemini TTS, voice name: {voice_name}, try: {i + 1}")

            # Get Gemini API key from config
            api_key = config.app.get("gemini_api_key", "")
            if not api_key:
                logger.error("Gemini API key not found in config")
                return None

            # Create Gemini client
            client = genai.Client(api_key=api_key)

            # Create SubMaker for subtitle generation
            sub_maker = SubMaker()

            # Call Gemini TTS API
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                )
            )

            # Extract audio data
            data = response.candidates[0].content.parts[0].inline_data.data

            # Save the audio file as WAV first, then convert if needed
            temp_wav_file = voice_file.replace('.mp3', '_temp.wav')
            wave_file(temp_wav_file, data)

            # Convert WAV to MP3 if needed
            if voice_file.endswith('.mp3'):
                # Use ffmpeg to convert WAV to MP3
                import subprocess
                ffmpeg_path = config.app.get("ffmpeg_path", "ffmpeg")
                try:
                    subprocess.run([
                        ffmpeg_path, "-i", temp_wav_file, "-acodec", "mp3",
                        "-y", voice_file
                    ], check=True, capture_output=True)
                    os.remove(temp_wav_file)  # Remove temp WAV file
                except subprocess.CalledProcessError as e:
                    logger.error(f"FFmpeg conversion failed: {e}")
                    # If conversion fails, just rename the WAV file
                    os.rename(temp_wav_file, voice_file.replace('.mp3', '.wav'))
                    voice_file = voice_file.replace('.mp3', '.wav')
            else:
                # If output is already WAV, just rename
                os.rename(temp_wav_file, voice_file)

            # Since Gemini TTS doesn't provide word boundaries, we need to estimate them
            words = text.split()
            total_chars = len(text)

            # Get file size to estimate duration
            file_size = os.path.getsize(voice_file)
            # Rough estimate based on file format
            if voice_file.endswith('.wav'):
                # WAV files are larger, roughly 176KB per second for 44.1kHz 16-bit stereo
                estimated_duration_ms = (file_size / 176000) * 1000
            else:
                # MP3 estimate: ~10KB per second
                estimated_duration_ms = (file_size / 10000) * 1000

            # Create approximate word boundaries
            offset = 0
            for word in words:
                # Estimate word duration based on its length relative to total text
                word_duration = (len(word) / total_chars) * estimated_duration_ms
                # Create subtitle entry with timestamp tuple (start_time, end_time)
                start_time = offset / 1000  # Convert to seconds
                end_time = (offset + word_duration) / 1000  # Convert to seconds
                sub_maker.create_sub((start_time, end_time), word)
                offset += word_duration

            logger.info(f"completed, output file: {voice_file}")
            return sub_maker

        except Exception as e:
            logger.error(f"Gemini TTS failed, error: {str(e)}")

    return None