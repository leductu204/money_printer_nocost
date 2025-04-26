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

def get_ffmpeg_command_with_limits(input_file, output_file, options=None):
    """
    Create an ffmpeg command with thread limits based on config
    
    Args:
        input_file: Input file path
        output_file: Output file path
        options: Additional ffmpeg options (dict)
        
    Returns:
        List of command arguments for subprocess
    """
    settings = get_ffmpeg_settings()
    ffmpeg_path = settings["ffmpeg_path"] or "ffmpeg"
    threads = settings["threads_per_process"]
    
    # Base command
    cmd = [
        ffmpeg_path,
        '-i', input_file,
        '-threads', str(threads)
    ]
    
    # Add additional options if provided
    if options:
        for key, value in options.items():
            if value is not None:
                cmd.extend([key, str(value)])
    
    # Add output file
    cmd.append(output_file)
    
    return cmd

def run_ffmpeg_with_limits(input_file, output_file, options=None, wait_for_slot=True):
    """
    Run ffmpeg with process and thread limits
    
    Args:
        input_file: Input file path
        output_file: Output file path
        options: Additional ffmpeg options (dict)
        wait_for_slot: Whether to wait for a slot to become available
        
    Returns:
        Subprocess result object
    """
    if wait_for_slot:
        wait_for_ffmpeg_slot()
    
    cmd = get_ffmpeg_command_with_limits(input_file, output_file, options)
    logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result
