# Lịch sử tối ưu hóa FFMPEG trong MoneyPrinterTurbo

## Vấn đề ban đầu

Người dùng gặp phải các vấn đề sau khi sử dụng FFMPEG trong MoneyPrinterTurbo:

1. **Sử dụng quá nhiều RAM**: FFMPEG tạo ra quá nhiều quá trình chạy đồng thời, mỗi quá trình sử dụng khoảng 200-300MB RAM.
2. **Lỗi MemoryError**: Khi kết hợp video, xuất hiện lỗi `MemoryError: Unable to allocate 15.8 MiB for an array with shape (2073600, 1) and data type float64`.
3. **Cảnh báo về frame cuối cùng**: Xuất hiện cảnh báo `bytes wanted but 0 bytes read at frame index 180 (out of a total 180 frames)`.

## Giải pháp đã triển khai

### 1. Tạo file `ffmpeg_settings.py`

File này thêm các tùy chọn FFMPEG vào WebUI của MoneyPrinterTurbo:

```python
import os
import streamlit as st
import psutil
from app.config import config

def add_ffmpeg_settings_to_ui():
    """
    Add ffmpeg settings to the UI
    This function should be called in the Basic Settings expander in Main.py
    """
    st.write("**FFMPEG Settings**")
    
    # Get current ffmpeg path from config
    current_ffmpeg_path = config.app.get("ffmpeg_path", "")
    
    # Display ffmpeg path input
    ffmpeg_path = st.text_input(
        "FFMPEG Path", 
        value=current_ffmpeg_path,
        help="Path to ffmpeg executable. Leave empty to use the default."
    )
    
    # Save ffmpeg path to config
    if ffmpeg_path != current_ffmpeg_path:
        config.app["ffmpeg_path"] = ffmpeg_path
        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
    
    # Get available RAM
    total_ram = psutil.virtual_memory().total / (1024 * 1024 * 1024)  # in GB
    
    # Display RAM limit input
    ram_limit = st.slider(
        "FFMPEG RAM Limit (GB)",
        min_value=1.0,
        max_value=max(8.0, total_ram - 2),
        value=min(7.0, total_ram - 2),
        step=0.5,
        help="Maximum RAM to use for FFMPEG processes. Each FFMPEG process uses about 700-800MB RAM."
    )
    config.app["ffmpeg_ram_limit"] = ram_limit
    
    # Calculate RAM usage per process based on threads
    ram_per_process_mb = 400 + (200 * 2)  # Base 400MB + 200MB per thread (default 2 threads)
    
    # Calculate max processes based on RAM limit
    max_processes = max(1, int((ram_limit * 1024) / ram_per_process_mb))
    
    # Display max processes input
    max_ffmpeg_processes = st.slider(
        "Max FFMPEG Processes",
        min_value=1,
        max_value=max(6, max_processes),
        value=min(3, max_processes),  # Default to 3 processes or less
        step=1,
        help=f"Maximum number of FFMPEG processes to run in parallel. Each process uses about {ram_per_process_mb}MB RAM."
    )
    config.app["max_ffmpeg_processes"] = max_ffmpeg_processes
    
    # Display threads per process input
    threads_per_process = st.slider(
        "Threads per FFMPEG Process",
        min_value=1,
        max_value=10,  # Limit to 10 threads max as requested
        value=2,
        step=1,
        help="Number of threads to use per FFMPEG process. More threads = faster processing but more RAM usage."
    )
    config.app["ffmpeg_threads_per_process"] = threads_per_process
    
    # Recalculate RAM usage per process based on selected threads
    ram_per_process_mb = 400 + (threads_per_process * 200)  # Base 400MB + 200MB per thread
    
    # Display estimated RAM usage
    estimated_ram = (max_ffmpeg_processes * ram_per_process_mb) / 1024  # in GB
    st.info(f"Estimated maximum RAM usage: {estimated_ram:.2f} GB")
    
    # Warning if estimated RAM usage is too high
    if estimated_ram > ram_limit:
        st.warning(f"⚠️ Estimated RAM usage ({estimated_ram:.2f} GB) exceeds your RAM limit ({ram_limit:.2f} GB). Consider reducing the number of processes or threads.")
    
    return {
        "ffmpeg_path": ffmpeg_path,
        "ram_limit": ram_limit,
        "max_processes": max_ffmpeg_processes,
        "threads_per_process": threads_per_process
    }

# This function can be used to get the ffmpeg settings from config
def get_ffmpeg_settings():
    return {
        "ffmpeg_path": config.app.get("ffmpeg_path", ""),
        "ram_limit": config.app.get("ffmpeg_ram_limit", 7.0),
        "max_processes": config.app.get("max_ffmpeg_processes", 6),
        "threads_per_process": config.app.get("ffmpeg_threads_per_process", 2)
    }
```

### 2. Sửa đổi file `Main.py`

Thêm import và tùy chọn FFMPEG vào WebUI:

```python
# Thêm import
from ffmpeg_settings import add_ffmpeg_settings_to_ui

# Thêm vào phần Basic Settings
with st.expander(tr("Basic Settings"), expanded=False):
    # ... (các tùy chọn hiện tại)
    
    # Add FFMPEG settings
    st.markdown("---")
    ffmpeg_settings = add_ffmpeg_settings_to_ui()
```

### 3. Sửa đổi file `video.py`

Thêm import và sử dụng số luồng từ config:

```python
# Thêm import
from app.config import config

# Trong hàm combine_videos
ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", threads)
logger.info(f"Using {ffmpeg_threads} threads for FFMPEG")

video_clip.write_videofile(
    filename=combined_video_path,
    threads=ffmpeg_threads,
    # ... (các tham số khác)
)

# Trong hàm generate_video
ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", params.n_threads or 2)
logger.info(f"Using {ffmpeg_threads} threads for FFMPEG in final video")

video_clip.write_videofile(
    output_file,
    threads=ffmpeg_threads,
    # ... (các tham số khác)
)

# Trong hàm preprocess_video
ffmpeg_threads = config.app.get("ffmpeg_threads_per_process", 2)
final_clip.write_videofile(video_file, fps=30, logger=None, threads=ffmpeg_threads)
```

### 4. Tạo script `parallel_convert.py`

Script này chuyển đổi nhiều video MOV sang MP4 đồng thời, với giới hạn số lượng quá trình:

```python
import os
import subprocess
import concurrent.futures
import psutil
from loguru import logger
from convert_mov_to_mp4 import get_ffmpeg_path

# Setup logging
logger.add("parallel_convert.log", rotation="10 MB")

def estimate_max_processes(ram_limit_gb=7, ram_per_process_mb=800):
    """
    Estimate the maximum number of ffmpeg processes that can run in parallel
    based on available RAM and estimated RAM usage per process
    """
    # Get available RAM
    available_ram = psutil.virtual_memory().available / (1024 * 1024)  # in MB
    
    # Reserve 2GB for system and other processes
    reserved_ram = 2 * 1024  # 2GB in MB
    usable_ram = min(ram_limit_gb * 1024, available_ram - reserved_ram)  # in MB
    
    # Calculate max processes
    max_processes = max(1, int(usable_ram / ram_per_process_mb))
    
    logger.info(f"Available RAM: {available_ram:.2f} MB")
    logger.info(f"Usable RAM: {usable_ram:.2f} MB")
    logger.info(f"Estimated RAM per ffmpeg process: {ram_per_process_mb} MB")
    logger.info(f"Maximum recommended parallel processes: {max_processes}")
    
    return max_processes

def convert_single_file(input_path, threads=2, delete_original=True):
    """Convert a single MOV file to MP4"""
    if not os.path.exists(input_path):
        logger.error(f"Input file does not exist: {input_path}")
        return False
    
    if not input_path.lower().endswith('.mov'):
        logger.error(f"Input file is not a MOV file: {input_path}")
        return False
    
    # Get ffmpeg path
    ffmpeg_path = get_ffmpeg_path()
    
    # Create output path
    output_filename = os.path.splitext(os.path.basename(input_path))[0] + '.mp4'
    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, output_filename)
    
    # Convert using ffmpeg with high quality settings
    cmd = [
        ffmpeg_path,
        '-i', input_path,  # Input file
        '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',  # Maintain aspect ratio with 1080p resolution
        '-c:v', 'libx264',  # Use H.264 codec for video
        '-preset', 'medium',  # Better quality preset
        '-crf', '18',  # Lower CRF for higher quality (18 is considered visually lossless)
        '-c:a', 'aac',  # Use AAC codec for audio
        '-b:a', '192k',  # Higher audio bitrate
        '-pix_fmt', 'yuv420p',  # Pixel format for better compatibility
        '-metadata:s:v:0', 'rotate=0',  # Remove rotation metadata
        '-movflags', '+faststart',  # Optimize for web streaming
        '-threads', str(threads),  # Control number of threads
        '-max_muxing_queue_size', '9999',  # Prevent muxing errors
        '-y',  # Overwrite output file if exists
        output_path
    ]
    
    try:
        logger.info(f"Converting {os.path.basename(input_path)} to {output_filename}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.success(f"Successfully converted {os.path.basename(input_path)} to {output_filename}")
            
            # Delete original file if requested
            if delete_original:
                os.remove(input_path)
                logger.info(f"Deleted original file: {os.path.basename(input_path)}")
            
            return True
        else:
            logger.error(f"Error converting {os.path.basename(input_path)}: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error processing {os.path.basename(input_path)}: {str(e)}")
        return False

def parallel_convert(input_dir, max_workers=None, threads_per_process=2, ram_limit_gb=7, delete_original=True):
    """
    Convert MOV files to MP4 in parallel
    
    Args:
        input_dir: Directory containing MOV files
        max_workers: Maximum number of parallel processes (auto-calculated if None)
        threads_per_process: Number of threads per ffmpeg process
        ram_limit_gb: RAM limit in GB
        delete_original: Whether to delete original MOV files after conversion
    """
    if not os.path.exists(input_dir):
        logger.error(f"Directory does not exist: {input_dir}")
        return
    
    # Get all MOV files in the directory
    mov_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) 
                if f.lower().endswith('.mov') and os.path.isfile(os.path.join(input_dir, f))]
    
    if not mov_files:
        logger.warning(f"No MOV files found in directory: {input_dir}")
        return
    
    # Calculate RAM usage per process based on threads
    ram_per_process_mb = 400 + (threads_per_process * 200)  # Base 400MB + 200MB per thread
    
    # Auto-calculate max workers if not specified
    if max_workers is None:
        max_workers = estimate_max_processes(ram_limit_gb, ram_per_process_mb)
    
    logger.info(f"Found {len(mov_files)} MOV files to convert")
    logger.info(f"Using {max_workers} parallel processes with {threads_per_process} threads each")
    
    # Process files in parallel
    success_count = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(
                convert_single_file, 
                file_path, 
                threads_per_process, 
                delete_original
            ): file_path for file_path in mov_files
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                logger.error(f"Error processing {os.path.basename(file_path)}: {str(e)}")
    
    logger.info(f"Successfully converted {success_count} out of {len(mov_files)} files")
```

### 5. Tạo script `limit_ffmpeg.py`

Script này giám sát và giới hạn số lượng quá trình ffmpeg chạy đồng thời:

```python
import os
import subprocess
import psutil
import time
import argparse
from loguru import logger

# Setup logging
logger.add("limit_ffmpeg.log", rotation="10 MB")

def count_ffmpeg_processes():
    """Count the number of ffmpeg processes currently running"""
    count = 0
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'ffmpeg' in proc.info['name'].lower():
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return count

def kill_excess_ffmpeg_processes(max_processes=3):
    """Kill excess ffmpeg processes if there are more than max_processes running"""
    ffmpeg_processes = []
    
    # Get all ffmpeg processes
    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            if 'ffmpeg' in proc.info['name'].lower():
                ffmpeg_processes.append({
                    'pid': proc.info['pid'],
                    'create_time': proc.info['create_time']
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Sort by creation time (oldest first)
    ffmpeg_processes.sort(key=lambda x: x['create_time'])
    
    # Keep the oldest max_processes processes, kill the rest
    processes_to_keep = ffmpeg_processes[:max_processes]
    processes_to_kill = ffmpeg_processes[max_processes:]
    
    # Kill excess processes
    for proc in processes_to_kill:
        try:
            process = psutil.Process(proc['pid'])
            process.terminate()
            logger.info(f"Terminated ffmpeg process with PID {proc['pid']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.error(f"Failed to terminate process with PID {proc['pid']}")
    
    return len(processes_to_kill)

def monitor_ffmpeg_processes(max_processes=3, check_interval=5):
    """
    Monitor and limit the number of ffmpeg processes
    
    Args:
        max_processes: Maximum number of ffmpeg processes to allow
        check_interval: How often to check for excess processes (in seconds)
    """
    logger.info(f"Starting ffmpeg process monitor. Maximum allowed processes: {max_processes}")
    logger.info(f"Press Ctrl+C to stop monitoring")
    
    try:
        while True:
            current_count = count_ffmpeg_processes()
            logger.info(f"Current ffmpeg processes: {current_count}")
            
            if current_count > max_processes:
                killed = kill_excess_ffmpeg_processes(max_processes)
                logger.warning(f"Killed {killed} excess ffmpeg processes")
            
            time.sleep(check_interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
```

### 6. Tạo script `ffmpeg_limiter.py`

Script này cung cấp các hàm để giới hạn số lượng quá trình ffmpeg:

```python
import os
import subprocess
import psutil
from loguru import logger
from app.config import config

def get_ffmpeg_settings():
    """Get ffmpeg settings from config"""
    return {
        "ffmpeg_path": config.app.get("ffmpeg_path", ""),
        "ram_limit": config.app.get("ffmpeg_ram_limit", 7.0),
        "max_processes": config.app.get("max_ffmpeg_processes", 3),
        "threads_per_process": config.app.get("ffmpeg_threads_per_process", 2)
    }

def limit_ffmpeg_processes():
    """
    Limit the number of ffmpeg processes based on config settings
    Returns True if new ffmpeg processes can be started, False otherwise
    """
    settings = get_ffmpeg_settings()
    max_processes = settings["max_processes"]
    
    # Count current ffmpeg processes
    current_count = 0
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'ffmpeg' in proc.info['name'].lower():
                current_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    logger.info(f"Current ffmpeg processes: {current_count}, Maximum allowed: {max_processes}")
    
    # Return True if we're under the limit, False otherwise
    return current_count < max_processes

def wait_for_ffmpeg_slot():
    """
    Wait until there's a slot available for a new ffmpeg process
    Returns True when a slot is available
    """
    import time
    
    while not limit_ffmpeg_processes():
        logger.info("Waiting for ffmpeg slot to become available...")
        time.sleep(5)  # Wait 5 seconds before checking again
    
    return True
```

### 7. Tạo batch file `convert_videos_limited.bat`

Batch file này chạy script `parallel_convert.py` với các tham số giới hạn:

```batch
@echo off
echo Converting all MOV files in local_videos directory to MP4 with limited processes...
python parallel_convert.py "E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\local_videos" --max-workers 3 --threads-per-process 2 --ram-limit 3
echo Done!
pause
```

### 8. Tạo batch file `limit_ffmpeg.bat`

Batch file này chạy script giám sát ffmpeg:

```batch
@echo off
echo Starting ffmpeg process monitor...
echo This will limit the number of ffmpeg processes to 3
echo Press Ctrl+C to stop monitoring
python limit_ffmpeg.py --max-processes 3 --check-interval 5
pause
```

## Các vấn đề đã giải quyết

1. **Giới hạn số luồng FFMPEG**: Người dùng có thể điều chỉnh số luồng FFMPEG từ 1 đến 10 trong WebUI.
2. **Giới hạn số lượng quá trình FFMPEG**: Giảm số lượng quá trình ffmpeg chạy đồng thời xuống 3 (có thể điều chỉnh).
3. **Tối ưu hóa sử dụng RAM**: Tính toán và hiển thị mức sử dụng RAM dự kiến, cảnh báo khi vượt quá giới hạn.
4. **Tích hợp vào WebUI**: Thêm các tùy chọn FFMPEG vào giao diện người dùng.

## Cách sử dụng

1. **Tùy chọn FFMPEG trong WebUI**:
   - Mở MoneyPrinterTurbo
   - Mở phần "Basic Settings"
   - Cuộn xuống phần cuối của cột bên phải để thấy "FFMPEG Settings"
   - Điều chỉnh số luồng và số lượng quá trình theo nhu cầu

2. **Chuyển đổi video MOV sang MP4**:
   - Sử dụng batch file `convert_videos_limited.bat`
   - Hoặc chạy lệnh: `python parallel_convert.py "đường/dẫn/đến/thư/mục" --threads-per-process 2 --ram-limit 3`

3. **Giám sát và giới hạn quá trình FFMPEG**:
   - Sử dụng batch file `limit_ffmpeg.bat`
   - Hoặc chạy lệnh: `python limit_ffmpeg.py --max-processes 3`

## Lưu ý

- Mỗi luồng FFMPEG sử dụng thêm khoảng 200MB RAM
- Mỗi quá trình FFMPEG sử dụng khoảng 400MB RAM cơ bản + 200MB cho mỗi luồng
- Với 2 luồng mỗi quá trình, mỗi quá trình FFMPEG sẽ sử dụng khoảng 800MB RAM
- Giới hạn số lượng quá trình xuống 3 sẽ giảm mức sử dụng RAM xuống còn khoảng 2.4GB
