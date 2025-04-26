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
