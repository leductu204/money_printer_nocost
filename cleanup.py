import os
import shutil
from loguru import logger

# Setup logging
logger.add("cleanup.log", rotation="10 MB")

def cleanup_converted_files():
    """Clean up all converted files and prepare for fresh conversion"""
    # Define directories
    videos_dir = r"E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\local_videos"
    temp_dir = r"E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\storage\temp_fix"
    backup_dir = os.path.join(videos_dir, "backup")
    
    # Check if backup directory exists
    if os.path.exists(backup_dir):
        logger.info(f"Found backup directory: {backup_dir}")
        
        # Count files in backup
        backup_files = os.listdir(backup_dir)
        logger.info(f"Found {len(backup_files)} files in backup directory")
        
        # Ask for confirmation
        print(f"Found {len(backup_files)} files in backup directory.")
        confirm = input("Do you want to restore original files from backup? (y/n): ")
        
        if confirm.lower() == 'y':
            # Restore original files from backup
            restored_count = 0
            for file in backup_files:
                backup_path = os.path.join(backup_dir, file)
                target_path = os.path.join(videos_dir, file)
                
                try:
                    shutil.copy2(backup_path, target_path)
                    restored_count += 1
                    logger.info(f"Restored original file: {file}")
                except Exception as e:
                    logger.error(f"Error restoring file {file}: {str(e)}")
            
            logger.success(f"Restored {restored_count} original files from backup")
            print(f"Restored {restored_count} original files from backup")
        
        # Ask if user wants to delete backup
        confirm = input("Do you want to delete the backup directory? (y/n): ")
        if confirm.lower() == 'y':
            try:
                shutil.rmtree(backup_dir)
                logger.info(f"Deleted backup directory: {backup_dir}")
                print(f"Deleted backup directory: {backup_dir}")
            except Exception as e:
                logger.error(f"Error deleting backup directory: {str(e)}")
    else:
        logger.info("No backup directory found")
        print("No backup directory found")
    
    # Check if temp directory exists
    if os.path.exists(temp_dir):
        # Ask if user wants to delete temp directory
        confirm = input(f"Do you want to delete the temporary directory ({temp_dir})? (y/n): ")
        if confirm.lower() == 'y':
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Deleted temporary directory: {temp_dir}")
                print(f"Deleted temporary directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error deleting temporary directory: {str(e)}")
    else:
        logger.info("No temporary directory found")
        print("No temporary directory found")
    
    print("Cleanup completed. You can now run the conversion process again.")
    logger.info("Cleanup completed")

if __name__ == "__main__":
    cleanup_converted_files()
