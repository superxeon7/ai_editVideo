import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, output_path: str = None) -> str:
    """
    Extract audio from video using FFmpeg
    
    Args:
        video_path: Path to input video
        output_path: Path for output audio (optional)
        
    Returns:
        Path to extracted audio file
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Generate output path if not provided
    if output_path is None:
        base_name = Path(video_path).stem
        output_path = f"temp/{base_name}_audio.wav"
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    logger.info(f"Extracting audio from {video_path} to {output_path}")
    
    try:
        # FFmpeg command to extract audio as WAV PCM
        command = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ar', '16000',  # 16kHz sample rate (optimal for Whisper)
            '-ac', '1',  # Mono
            '-y',  # Overwrite output
            output_path
        ]
        
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        logger.info(f"Audio extracted successfully: {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg audio extraction failed: {e.stderr}")
        raise RuntimeError(f"Failed to extract audio: {e.stderr}")
    except Exception as e:
        logger.error(f"Unexpected error during audio extraction: {str(e)}")
        raise


def get_audio_duration(audio_path: str) -> float:
    """
    Get duration of audio file in seconds
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Duration in seconds
    """
    try:
        command = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        duration = float(result.stdout.strip())
        return duration
        
    except Exception as e:
        logger.error(f"Failed to get audio duration: {str(e)}")
        return 0.0


def validate_audio_quality(audio_path: str) -> dict:
    """
    Validate audio quality for transcription
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Dictionary with validation results
    """
    try:
        command = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=sample_rate,channels,bit_rate',
            '-of', 'json',
            audio_path
        ]
        
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        import json
        data = json.loads(result.stdout)
        
        if not data.get('streams'):
            return {
                "valid": False,
                "error": "No audio stream found"
            }
        
        stream = data['streams'][0]
        sample_rate = int(stream.get('sample_rate', 0))
        channels = int(stream.get('channels', 0))
        
        # Check if audio quality is sufficient
        valid = sample_rate >= 8000 and channels > 0
        
        return {
            "valid": valid,
            "sample_rate": sample_rate,
            "channels": channels,
            "error": None if valid else "Audio quality too low for transcription"
        }
        
    except Exception as e:
        logger.error(f"Failed to validate audio: {str(e)}")
        return {
            "valid": False,
            "error": str(e)
        }