import os
import logging
from pathlib import Path
from typing import List
from models.decision import VisualInsertion

logger = logging.getLogger(__name__)


def validate_file_exists(file_path: str) -> bool:
    """Check if file exists"""
    return os.path.exists(file_path) and os.path.isfile(file_path)


def validate_directory_exists(dir_path: str) -> bool:
    """Check if directory exists"""
    return os.path.exists(dir_path) and os.path.isdir(dir_path)


def ensure_directory(dir_path: str) -> None:
    """Create directory if it doesn't exist"""
    os.makedirs(dir_path, exist_ok=True)


def validate_video_format(file_path: str, supported_formats: List[str]) -> bool:
    """
    Validate video file format
    
    Args:
        file_path: Path to video file
        supported_formats: List of supported extensions (e.g., ['mp4', 'mov'])
        
    Returns:
        True if format is supported
    """
    ext = Path(file_path).suffix.lower().lstrip('.')
    return ext in [fmt.lower() for fmt in supported_formats]


def validate_insertions_frequency(insertions: List[VisualInsertion], max_per_interval: int = 1, interval: float = 10.0) -> List[VisualInsertion]:
    """
    Validate and filter insertions to avoid visual spam
    
    Args:
        insertions: List of visual insertions
        max_per_interval: Maximum insertions per time interval
        interval: Time interval in seconds
        
    Returns:
        Filtered list of insertions
    """
    if not insertions:
        return []
    
    # Sort by timestamp
    sorted_insertions = sorted(insertions, key=lambda x: x.timestamp)
    
    filtered = []
    last_insertion_time = -interval  # Start with negative to allow first insertion
    
    for insertion in sorted_insertions:
        time_since_last = insertion.timestamp - last_insertion_time
        
        if time_since_last >= interval / max_per_interval:
            filtered.append(insertion)
            last_insertion_time = insertion.timestamp
        else:
            logger.debug(
                f"Skipping insertion at {insertion.timestamp}s - "
                f"too close to previous insertion ({time_since_last:.1f}s < {interval/max_per_interval:.1f}s)"
            )
    
    removed_count = len(insertions) - len(filtered)
    if removed_count > 0:
        logger.info(f"Filtered out {removed_count} insertions due to frequency constraints")
    
    return filtered


def validate_insertion_bounds(insertions: List[VisualInsertion], video_duration: float) -> List[VisualInsertion]:
    """
    Ensure insertions don't exceed video duration
    
    Args:
        insertions: List of visual insertions
        video_duration: Total video duration in seconds
        
    Returns:
        Filtered list of valid insertions
    """
    valid_insertions = []
    
    for insertion in insertions:
        insertion_end = insertion.timestamp + insertion.duration
        
        if insertion.timestamp < 0:
            logger.warning(f"Skipping insertion with negative timestamp: {insertion.timestamp}")
            continue
        
        if insertion_end > video_duration:
            # Adjust duration to fit within video
            new_duration = video_duration - insertion.timestamp
            if new_duration >= 0.5:  # Minimum 0.5s duration
                insertion.duration = new_duration
                valid_insertions.append(insertion)
                logger.info(
                    f"Adjusted insertion duration at {insertion.timestamp}s "
                    f"to {new_duration:.1f}s to fit video bounds"
                )
            else:
                logger.warning(f"Skipping insertion at {insertion.timestamp}s - exceeds video duration")
        else:
            valid_insertions.append(insertion)
    
    return valid_insertions


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to remove invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    max_length = 200
    name, ext = os.path.splitext(filename)
    if len(name) > max_length:
        name = name[:max_length]
    
    return name + ext


def validate_confidence_threshold(threshold: float) -> bool:
    """Validate confidence threshold is between 0 and 1"""
    return 0.0 <= threshold <= 1.0


def check_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and accessible"""
    import subprocess
    
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_system_requirements() -> dict:
    """
    Check if system meets requirements
    
    Returns:
        Dictionary with requirement checks
    """
    requirements = {
        "ffmpeg_installed": check_ffmpeg_installed(),
        "python_version": True,  # If running, Python is OK
    }
    
    # Check disk space
    import shutil
    try:
        stat = shutil.disk_usage('.')
        free_gb = stat.free / (1024**3)
        requirements["disk_space_gb"] = round(free_gb, 2)
        requirements["sufficient_disk_space"] = free_gb > 5  # Require 5GB free
    except:
        requirements["disk_space_gb"] = 0
        requirements["sufficient_disk_space"] = False
    
    return requirements