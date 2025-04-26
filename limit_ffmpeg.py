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

def main():
    parser = argparse.ArgumentParser(description='Monitor and limit the number of ffmpeg processes')
    parser.add_argument('--max-processes', type=int, default=3, 
                        help='Maximum number of ffmpeg processes to allow (default: 3)')
    parser.add_argument('--check-interval', type=int, default=5,
                        help='How often to check for excess processes in seconds (default: 5)')
    
    args = parser.parse_args()
    
    monitor_ffmpeg_processes(
        max_processes=args.max_processes,
        check_interval=args.check_interval
    )

if __name__ == '__main__':
    main()
