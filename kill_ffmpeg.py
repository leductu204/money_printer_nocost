import os
import subprocess
from loguru import logger

def kill_ffmpeg_processes():
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True)
        else:  # Linux/Mac
            subprocess.run(['pkill', 'ffmpeg'], capture_output=True)
        logger.info("Killed all remaining ffmpeg processes")
    except Exception as e:
        logger.error(f"Error killing ffmpeg processes: {str(e)}")

if __name__ == '__main__':
    kill_ffmpeg_processes() 