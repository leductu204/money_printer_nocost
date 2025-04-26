@echo off
echo Starting ffmpeg process monitor...
echo This will limit the number of ffmpeg processes to 3
echo Press Ctrl+C to stop monitoring
python limit_ffmpeg.py --max-processes 3 --check-interval 5
pause
