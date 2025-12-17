import os
import subprocess
import logging
import re
from typing import List, Dict
from models.timeline import Timeline, TimelineInsertion
from utils.video import get_video_info

logger = logging.getLogger(__name__)


class RenderingError(Exception):
    """Custom exception for rendering errors"""
    pass


def render(
    video: str,
    decisions: list,
    output: str,
    aspect_ratio: str = "9:16",
    config: Dict = None
) -> str:
    """
    Render final video with visual insertions
    
    Args:
        video: Path to input video
        decisions: List of VisualInsertion with asset_path populated
        output: Path for output video
        aspect_ratio: Video aspect ratio
        config: Rendering configuration
        
    Returns:
        Path to rendered video
        
    Raises:
        RenderingError: If rendering fails
    """
    if config is None:
        config = {
            "default_scale": 0.4,
            "default_opacity": 0.85,
            "fade_in": 0.3,
            "fade_out": 0.3,
            "preset": "medium",
            "crf": 23
        }
    
    logger.info(f"Starting video rendering: {video} -> {output}")
    
    # Build timeline
    timeline = Timeline.from_decisions(
        base_video=video,
        aspect_ratio=aspect_ratio,
        decisions=decisions,
        config=config
    )
    
    if not timeline.insertions:
        logger.warning("No insertions in timeline, copying original video")
        import shutil
        os.makedirs(os.path.dirname(output), exist_ok=True)
        shutil.copy2(video, output)
        return output
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output), exist_ok=True)
    
    # Build and execute FFmpeg command
    try:
        logger.info(f"Building FFmpeg filter complex for {len(timeline.insertions)} insertions")
        
        filter_complex = build_filter_complex(timeline)
        command = build_ffmpeg_command(
            timeline=timeline,
            output_path=output,
            filter_complex=filter_complex,
            config=config
        )
        
        logger.info("Executing FFmpeg rendering")
        execute_ffmpeg(command)
        
        # Validate output
        if not os.path.exists(output):
            raise RenderingError("Output file was not created")
        
        output_size = os.path.getsize(output) / (1024 * 1024)
        logger.info(f"Rendering complete: {output} ({output_size:.2f}MB)")
        
        return output
    
    except Exception as e:
        logger.error(f"Rendering failed: {str(e)}")
        raise RenderingError(f"Failed to render video: {str(e)}")


def build_filter_complex(timeline: Timeline) -> str:
    """
    Build FFmpeg filter_complex for all insertions
    
    Args:
        timeline: Timeline object
        
    Returns:
        FFmpeg filter_complex string
    """
    filters = []
    overlay_chain = '[0:v]'
    
    # Get video dimensions
    video_info = get_video_info(timeline.base_video)
    scale_width = video_info['width']
    scale_height = video_info['height']
    
    for idx, insertion in enumerate(timeline.insertions):
        input_index = idx + 1  # Input [0] is base video
        
        # Calculate scaled dimensions
        scaled_width = int(insertion.scale * scale_width)
        scaled_height = int(insertion.scale * scale_height)
        
        if insertion.asset_type == 'video':
            # Video asset: scale, fade, trim, set timing
            filter_parts = [
                f"[{input_index}:v]",
                f"scale={scaled_width}:{scaled_height}",
                f"fade=in:st=0:d={insertion.transition.fade_in}:alpha=1",
                f"fade=out:st={insertion.duration - insertion.transition.fade_out}:d={insertion.transition.fade_out}:alpha=1",
                f"trim=duration={insertion.duration}",
                "setpts=PTS-STARTPTS",
                f"format=rgba,colorchannelmixer=aa={insertion.opacity}[overlay{idx}]"
            ]
        else:
            # Image asset: scale, fade, loop
            filter_parts = [
                f"[{input_index}:v]",
                f"scale={scaled_width}:{scaled_height}",
                f"fade=in:st=0:d={insertion.transition.fade_in}:alpha=1",
                f"fade=out:st={insertion.duration - insertion.transition.fade_out}:d={insertion.transition.fade_out}:alpha=1",
                "format=rgba",
                f"colorchannelmixer=aa={insertion.opacity}",
                "loop=loop=-1:size=1:start=0[overlay{idx}]"
            ]
        
        filters.append(",".join(filter_parts).replace("[overlay{idx}]", f"[overlay{idx}]"))
        
        # Build overlay command
        enable_condition = f"between(t,{insertion.timestamp},{insertion.timestamp + insertion.duration})"
        
        next_chain = '[outv]' if idx == len(timeline.insertions) - 1 else f'[tmp{idx}]'
        
        overlay_filter = (
            f"{overlay_chain}[overlay{idx}]overlay="
            f"x={insertion.position.x}:y={insertion.position.y}:"
            f"enable='{enable_condition}'"
            f"{next_chain}"
        )
        
        filters.append(overlay_filter)
        overlay_chain = next_chain
    
    return ";".join(filters)


def build_ffmpeg_command(
    timeline: Timeline,
    output_path: str,
    filter_complex: str,
    config: Dict
) -> List[str]:
    """
    Build complete FFmpeg command
    
    Args:
        timeline: Timeline object
        output_path: Output file path
        filter_complex: Filter complex string
        config: Rendering configuration
        
    Returns:
        FFmpeg command as list of arguments
    """
    command = ['ffmpeg', '-y']  # -y to overwrite
    
    # Add input files
    command.extend(['-i', timeline.base_video])
    
    for insertion in timeline.insertions:
        command.extend(['-i', insertion.asset_path])
    
    # Add filter complex
    command.extend(['-filter_complex', filter_complex])
    
    # Map output video and audio
    command.extend([
        '-map', '[outv]',
        '-map', '0:a?',  # Copy audio from base video (? makes it optional)
    ])
    
    # Video encoding settings
    command.extend([
        '-c:v', 'libx264',
        '-preset', config.get('preset', 'medium'),
        '-crf', str(config.get('crf', 23)),
        '-pix_fmt', 'yuv420p',
    ])
    
    # Audio encoding settings
    command.extend([
        '-c:a', 'aac',
        '-b:a', '192k',
    ])
    
    # Web optimization
    command.extend(['-movflags', '+faststart'])
    
    # Output file
    command.append(output_path)
    
    return command


def execute_ffmpeg(command: List[str], progress_callback=None) -> None:
    """
    Execute FFmpeg command with progress tracking
    
    Args:
        command: FFmpeg command as list
        progress_callback: Optional callback function for progress updates
        
    Raises:
        RenderingError: If FFmpeg fails
    """
    logger.debug(f"FFmpeg command: {' '.join(command)}")
    
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        duration = None
        
        # Parse FFmpeg output for progress
        while True:
            line = process.stderr.readline()
            if not line:
                break
            
            # Extract total duration
            if not duration:
                duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                if duration_match:
                    h, m, s = map(float, duration_match.groups())
                    duration = h * 3600 + m * 60 + s
                    logger.debug(f"Video duration: {duration:.2f}s")
            
            # Extract current time
            time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
            if time_match and duration:
                h, m, s = map(float, time_match.groups())
                current_time = h * 3600 + m * 60 + s
                percentage = min(100, int((current_time / duration) * 100))
                
                if progress_callback:
                    progress_callback(percentage)
                
                if percentage % 10 == 0:  # Log every 10%
                    logger.info(f"Rendering progress: {percentage}%")
        
        # Wait for process to complete
        return_code = process.wait()
        
        if return_code != 0:
            stderr_output = process.stderr.read() if process.stderr else ""
            raise RenderingError(f"FFmpeg exited with code {return_code}: {stderr_output}")
        
        logger.info("FFmpeg rendering completed successfully")
    
    except subprocess.SubprocessError as e:
        logger.error(f"FFmpeg process error: {str(e)}")
        raise RenderingError(f"FFmpeg execution failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during rendering: {str(e)}")
        raise RenderingError(f"Rendering error: {str(e)}")


def render_with_retry(
    video: str,
    decisions: list,
    output: str,
    aspect_ratio: str = "9:16",
    config: Dict = None,
    max_retries: int = 2
) -> str:
    """
    Render with retry logic and complexity reduction on failure
    
    Args:
        video: Path to input video
        decisions: List of VisualInsertion objects
        output: Output path
        aspect_ratio: Video aspect ratio
        config: Rendering configuration
        max_retries: Maximum retry attempts
        
    Returns:
        Path to rendered video
    """
    attempt = 0
    current_decisions = decisions.copy()
    
    while attempt <= max_retries:
        try:
            return render(video, current_decisions, output, aspect_ratio, config)
        
        except RenderingError as e:
            attempt += 1
            
            if attempt > max_retries:
                logger.error("All rendering attempts failed, returning original video")
                import shutil
                shutil.copy2(video, output)
                return output
            
            # Reduce complexity for retry
            if attempt == 1:
                # First retry: Keep top 50% by confidence
                current_decisions = sorted(
                    current_decisions, 
                    key=lambda x: x.confidence, 
                    reverse=True
                )[:len(current_decisions)//2]
                logger.warning(f"Retry {attempt}: Reduced to {len(current_decisions)} insertions")
            else:
                # Second retry: Keep only highest confidence
                current_decisions = [max(current_decisions, key=lambda x: x.confidence)]
                logger.warning(f"Retry {attempt}: Reduced to 1 insertion")
    
    return output