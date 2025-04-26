import os
import subprocess
import shutil
import concurrent.futures
import psutil
from loguru import logger

# Setup logging
logger.add("video_fix.log", rotation="10 MB")

# Determine optimal number of threads based on CPU cores
def get_optimal_threads():
    cpu_count = psutil.cpu_count(logical=False)  # Physical cores
    if cpu_count is None:
        cpu_count = psutil.cpu_count(logical=True)  # Logical cores as fallback
    if cpu_count is None:
        return 2  # Default if detection fails
    
    # Use 75% of available cores, minimum 2, maximum 5
    optimal = max(2, min(5, int(cpu_count * 0.75)))
    logger.info(f"Detected {cpu_count} CPU cores, using {optimal} threads for conversion")
    return optimal

def get_ffmpeg_path():
    """Get ffmpeg path from environment or use default"""
    # Default ffmpeg path in the project
    default_path = "C:/Users/leduc/AppData/Local/Programs/Python/ffmpeg/bin/ffmpeg.exe"
    if os.path.exists(default_path):
        return default_path
        
    return 'ffmpeg'  # Fall back to system PATH

def fix_video(input_path, output_dir):
    """Fix a video file by re-encoding it with compatible settings"""
    if not os.path.exists(input_path):
        logger.error(f"Input file does not exist: {input_path}")
        return False
        
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Get ffmpeg path
    ffmpeg_path = get_ffmpeg_path()
    logger.info(f"Using ffmpeg from: {ffmpeg_path}")
    
    # Create temporary output path
    filename = os.path.basename(input_path)
    base_name = os.path.splitext(filename)[0]
    temp_output_path = os.path.join(output_dir, f"{base_name}_fixed.mp4")
    
    # Convert using ffmpeg with compatible settings
    cmd = [
        ffmpeg_path,
        '-i', input_path,  # Input file
        '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',  # Maintain aspect ratio
        '-c:v', 'libx264',  # Use H.264 codec for video
        '-preset', 'fast',  # Faster encoding preset
        '-crf', '23',  # Constant Rate Factor (lower = better quality, 18-28 is good)
        '-c:a', 'aac',  # Use AAC codec for audio
        '-b:a', '128k',  # Audio bitrate
        '-pix_fmt', 'yuv420p',  # Pixel format for better compatibility
        '-metadata:s:v:0', 'rotate=0',  # Remove rotation metadata
        '-movflags', '+faststart',  # Optimize for web streaming
        '-threads', '2',  # Limit threads per process to avoid overloading
        '-max_muxing_queue_size', '9999',  # Prevent muxing errors
        '-y',  # Overwrite output file if exists
        temp_output_path
    ]
    
    logger.info(f"Converting {filename}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.success(f"Successfully converted {filename}")
            return temp_output_path
        else:
            logger.error(f"Error converting {filename}: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error processing {filename}: {str(e)}")
        return False

def process_video_task(video_file, input_dir, temp_dir):
    """Process a single video file (for parallel processing)"""
    input_path = os.path.join(input_dir, video_file)
    
    # Fix the video
    fixed_path = fix_video(input_path, temp_dir)
    
    if fixed_path and os.path.exists(fixed_path):
        try:
            # Replace original with fixed version
            shutil.copy2(fixed_path, input_path)
            logger.success(f"Replaced {video_file} with fixed version")
            
            # Delete the temporary fixed file to save space
            os.remove(fixed_path)
            logger.info(f"Deleted temporary file: {fixed_path}")
            
            return True
        except Exception as e:
            logger.error(f"Error replacing file {video_file}: {str(e)}")
            return False
    return False

def process_all_videos(input_dir, temp_dir):
    """Process all video files in the input directory using multiple threads"""
    if not os.path.exists(input_dir):
        logger.error(f"Input directory does not exist: {input_dir}")
        return
        
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # Get all video files in the directory
    video_files = [f for f in os.listdir(input_dir) 
                  if os.path.isfile(os.path.join(input_dir, f)) and 
                  f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
    
    if not video_files:
        logger.warning(f"No video files found in directory: {input_dir}")
        return
    
    logger.info(f"Found {len(video_files)} video files to process")
    
    # Determine number of threads to use
    num_threads = get_optimal_threads()
    
    # Process videos in parallel
    success_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit all tasks
        future_to_video = {executor.submit(process_video_task, video_file, input_dir, temp_dir): video_file 
                          for video_file in video_files}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_video):
            video_file = future_to_video[future]
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                logger.error(f"Error processing {video_file}: {str(e)}")
    
    logger.info(f"Successfully processed {success_count} out of {len(video_files)} files")

def kill_ffmpeg_processes():
    """Kill any running ffmpeg processes"""
    try:
        # Since we're on Windows (based on the paths), use taskkill
        subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True)
        logger.info("Killed all remaining ffmpeg processes")
    except Exception as e:
        logger.error(f"Error killing ffmpeg processes: {str(e)}")

if __name__ == "__main__":
    try:
        # Define directories
        videos_dir = r"E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\local_videos"
        temp_dir = r"E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\temp_fix"
        
        print("Starting video fix process...")
        print("This will convert all videos in the local_videos directory to a compatible format.")
        print("Original files will be directly replaced with the converted versions.")
        print("Press Ctrl+C at any time to cancel.")
        
        logger.info("Starting video fix process...")
        process_all_videos(videos_dir, temp_dir)
        logger.info("Video fix process completed")
        
        print("\nVideo fix process completed!")
        print("All videos have been converted to a compatible format.")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        logger.warning("Process interrupted by user")
    except Exception as e:
        print(f"\nError in main process: {str(e)}")
        logger.error(f"Error in main process: {str(e)}")
    finally:
        kill_ffmpeg_processes()
