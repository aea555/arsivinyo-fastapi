import ffmpeg
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def update_creation_time(file_path: str, timestamp: Optional[datetime] = None) -> str:
    """Updates the creation_time metadata of a media file using FFmpeg stream copy."""
    if timestamp is None:
        timestamp = datetime.now()
    
    formatted_time = timestamp.strftime('%Y-%m-%dT%H:%M:%S')
    
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    output_path = os.path.join(dir_name, f"fixed_{base_name}")

    try:
        # Use -c copy for instant metadata update without re-encoding
        (
            ffmpeg
            .input(file_path)
            .output(output_path, metadata=f'creation_time={formatted_time}', c='copy')
            .overwrite_output()
            .run(quiet=True)
        )
        
        # Replace original with the updated file
        os.replace(output_path, file_path)
        logger.info(f"Updated metadata for {file_path} to {formatted_time}")
        return file_path
    except Exception as e:
        logger.error(f"FFmpeg error for {file_path}: {e}")
        # If anything fails, cleanup output and raise
        if os.path.exists(output_path):
            os.remove(output_path)
        raise
