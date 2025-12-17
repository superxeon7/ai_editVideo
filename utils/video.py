import os
import subprocess
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_video_info(video_path: str) -> dict:
    """
    Get comprehensive video information
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with video metadata
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    try:
        command = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,r_frame_rate,codec_name',
            '-show_entries', 'format=duration,size,bit_rate',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        data = json.loads(result.stdout)
        
        stream = data.get('streams', [{}])[0]
        format_info = data.get('format', {})
        
        width = int(stream.get('width', 0))
        height = int(stream.get('height', 0))
        
        # Calculate aspect ratio
        aspect_ratio = detect_aspect_ratio(width, height)
        
        # Parse frame rate
        frame_rate_str = stream.get('r_frame_rate', '30/1')
        num, den = map(int, frame_rate_str.split('/'))
        frame_rate = num / den if den != 0 else 30
        
        duration = float(format_info.get('duration', 0))
        file_size = int(format_info.get('size', 0))
        
        return {
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "frame_rate": round(frame_rate, 2),
            "codec": stream.get('codec_name', 'unknown'),
            "bit_rate": int(format_info.get('bit_rate', 0))
        }
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFprobe failed: {e.stderr}")
        raise RuntimeError(f"Failed to get video info: {e.stderr}")
    except Exception as e:
        logger.error(f"Failed to parse video info: {str(e)}")
        raise


def detect_aspect_ratio(width: int, height: int) -> str:
    """
    Detect aspect ratio from dimensions
    
    Args:
        width: Video width
        height: Video height
        
    Returns:
        Aspect ratio string (e.g., "9:16" or "16:9")
    """
    ratio = width / height if height > 0 else 1
    
    # Common aspect ratios
    if 0.5 <= ratio <= 0.6:  # Portrait (9:16, 9:19.5)
        return "9:16"
    elif 1.7 <= ratio <= 1.8:  # Landscape (16:9)
        return "16:9"
    elif 0.9 <= ratio <= 1.1:  # Square
        return "1:1"
    elif ratio < 0.5:
        return "9:16"  # Very tall, treat as portrait
    else:
        return "16:9"  # Default to landscape


def validate_video(video_path: str, config: dict) -> dict:
    """
    Validate video against configuration constraints
    
    Args:
        video_path: Path to video file
        config: Configuration dictionary
        
    Returns:
        Validation result with success status and error message
    """
    try:
        info = get_video_info(video_path)
        
        # Check file size
        max_size_mb = config.get('max_file_size_mb', 500)
        if info['file_size_mb'] > max_size_mb:
            return {
                "valid": False,
                "error": f"File size ({info['file_size_mb']}MB) exceeds limit ({max_size_mb}MB)"
            }
        
        # Check duration
        max_duration = config.get('max_duration_seconds', 300)
        if info['duration'] > max_duration:
            return {
                "valid": False,
                "error": f"Duration ({info['duration']}s) exceeds limit ({max_duration}s)"
            }
        
        # Check aspect ratio
        supported_ratios = config.get('supported_aspect_ratios', ['9:16', '16:9'])
        if info['aspect_ratio'] not in supported_ratios:
            return {
                "valid": False,
                "error": f"Aspect ratio {info['aspect_ratio']} not supported. Use: {', '.join(supported_ratios)}"
            }
        
        return {
            "valid": True,
            "info": info,
            "error": None
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


def create_thumbnail(video_path: str, output_path: str = None, timestamp: float = 3.0) -> str:
    """
    Create thumbnail from video at specified timestamp
    
    Args:
        video_path: Path to video file
        output_path: Path for output thumbnail
        timestamp: Timestamp in seconds
        
    Returns:
        Path to thumbnail file
    """
    if output_path is None:
        base_name = Path(video_path).stem
        output_path = f"temp/{base_name}_thumbnail.jpg"
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        command = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(timestamp),
            '-vframes', '1',
            '-vf', 'scale=480:-1',
            '-q:v', '2',
            '-y',
            output_path
        ]
        
        subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        
        logger.info(f"Thumbnail created: {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create thumbnail: {e.stderr}")
        raise RuntimeError(f"Thumbnail creation failed: {e.stderr}")