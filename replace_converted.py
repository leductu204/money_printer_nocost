import os
import shutil
from loguru import logger

# Setup logging
logger.add("replace_converted.log", rotation="10 MB")

def replace_converted_files(input_dir):
    """Replace original MP4 files with converted ones"""
    if not os.path.exists(input_dir):
        logger.error(f"Directory does not exist: {input_dir}")
        return
    
    # Get all converted files in the directory
    converted_files = [f for f in os.listdir(input_dir) 
                      if f.lower().endswith('_converted.mp4')]
    
    if not converted_files:
        logger.warning(f"No converted files found in directory: {input_dir}")
        return
    
    logger.info(f"Found {len(converted_files)} converted files to replace")
    
    success_count = 0
    for converted_file in converted_files:
        try:
            # Get original file name
            original_file = converted_file.replace('_converted.mp4', '.mp4')
            original_path = os.path.join(input_dir, original_file)
            converted_path = os.path.join(input_dir, converted_file)
            
            # Check if original file exists
            if not os.path.exists(original_path):
                logger.warning(f"Original file not found: {original_file}")
                continue
            
            # Replace original with converted
            shutil.copy2(converted_path, original_path)
            logger.success(f"Replaced {original_file} with {converted_file}")
            
            # Delete converted file
            os.remove(converted_path)
            logger.info(f"Deleted temporary file: {converted_file}")
            
            success_count += 1
        except Exception as e:
            logger.error(f"Error replacing file {converted_file}: {str(e)}")
    
    logger.info(f"Successfully replaced {success_count} out of {len(converted_files)} files")

if __name__ == "__main__":
    # Define directory
    videos_dir = r"E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\local_videos"
    
    print("Starting file replacement process...")
    print("This will replace original MP4 files with converted ones.")
    
    replace_converted_files(videos_dir)
    
    print("\nReplacement process completed!")
    print(f"Successfully replaced files with converted versions.")
