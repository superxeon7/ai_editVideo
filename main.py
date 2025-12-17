#!/usr/bin/env python3
"""
AI Auto Video Editor - Main Entry Point
Automatically adds visual elements to videos based on spoken content
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from colorama import Fore, Style, init as colorama_init

# Import services
from services.transcriber import transcribe, get_transcript_summary
from services.llm import analyze, get_decisions_summary
from services.asset_fetcher import fetch_assets_for_decisions
from services.renderer import render_with_retry

# Import utilities
from utils.audio import extract_audio
from utils.video import validate_video, get_video_info, create_thumbnail
from utils.validators import check_system_requirements, ensure_directory

# Initialize colorama for colored output
colorama_init(autoreset=True)

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/video_editor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print application banner"""
    banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🎬 AI AUTO VIDEO EDITOR 🎬                     ║
║                                                           ║
║   Automatically enhance videos with AI-powered visuals   ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)


def print_step(step_num: int, total_steps: int, description: str):
    """Print processing step"""
    print(f"\n{Fore.YELLOW}[{step_num}/{total_steps}] {description}{Style.RESET_ALL}")


def print_success(message: str):
    """Print success message"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Print error message"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Print info message"""
    print(f"{Fore.CYAN}ℹ {message}{Style.RESET_ALL}")


def main():
    """Main execution function"""
    print_banner()
    
    # Check system requirements
    print_step(0, 6, "Checking system requirements...")
    requirements = check_system_requirements()
    
    if not requirements['ffmpeg_installed']:
        print_error("FFmpeg is not installed. Please install FFmpeg first.")
        print_info("Install guide: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    if not requirements['sufficient_disk_space']:
        print_warning(f"Low disk space: {requirements['disk_space_gb']}GB free")
    
    print_success("System requirements OK")
    
    # Load configuration
    try:
        with open("config.yml", 'r') as f:
            config = yaml.safe_load(f)
        print_success("Configuration loaded")
    except Exception as e:
        print_error(f"Failed to load config.yml: {str(e)}")
        sys.exit(1)
    
    # Setup directories
    ensure_directory("temp")
    ensure_directory("output")
    ensure_directory("logs")
    ensure_directory("assets/placeholders")
    
    # Get input video path
    input_video = "input/raw_video.mp4"
    
    if not os.path.exists(input_video):
        print_error(f"Input video not found: {input_video}")
        print_info("Place your video in the 'input' directory as 'raw_video.mp4'")
        sys.exit(1)
    
    # Validate video
    print_step(1, 6, "Validating input video...")
    validation = validate_video(input_video, config['video'])
    
    if not validation['valid']:
        print_error(f"Video validation failed: {validation['error']}")
        sys.exit(1)
    
    video_info = validation['info']
    print_success(f"Video validated: {video_info['width']}x{video_info['height']}, "
                 f"{video_info['duration']:.1f}s, {video_info['file_size_mb']}MB")
    
    aspect_ratio = video_info['aspect_ratio']
    print_info(f"Detected aspect ratio: {aspect_ratio}")
    
    # Step 1: Extract audio
    print_step(2, 6, "Extracting audio from video...")
    try:
        audio_path = extract_audio(input_video, "temp/audio.wav")
        print_success(f"Audio extracted: {audio_path}")
    except Exception as e:
        print_error(f"Audio extraction failed: {str(e)}")
        sys.exit(1)
    
    # Step 2: Transcribe audio
    print_step(3, 6, "Transcribing audio with Whisper AI...")
    try:
        transcript = transcribe(
            audio_path,
            model_size=config['ai']['transcription_model'],
            language=config['ai']['language']
        )
        
        summary = get_transcript_summary(transcript)
        print_success(f"Transcription complete: {summary['total_words']} words, "
                     f"{summary['total_segments']} segments")
        print_info(f"Language: {summary['language']}, "
                  f"Speaking rate: {summary['words_per_minute']} words/min")
    except Exception as e:
        print_error(f"Transcription failed: {str(e)}")
        sys.exit(1)
    
    # Step 3: Analyze with LLM
    print_step(4, 6, "Analyzing content with Claude AI...")
    try:
        decisions = analyze(
            transcript=transcript,
            prompt_path="prompt/visual_mapper.txt",
            threshold=config['ai']['confidence_threshold'],
            aspect_ratio=aspect_ratio
        )
        
        summary = get_decisions_summary(decisions)
        print_success(f"AI analysis complete: {summary['total_insertions']} insertions planned")
        
        if summary['total_insertions'] > 0:
            print_info(f"Average confidence: {summary['avg_confidence']}")
            print_info(f"Entity types: {', '.join(summary['entity_types'].keys())}")
        else:
            print_warning("No suitable insertion points found")
            print_info("The video will be returned unchanged")
    except Exception as e:
        print_error(f"AI analysis failed: {str(e)}")
        sys.exit(1)
    
    # If no insertions, copy original video
    if not decisions.insertions:
        import shutil
        output_path = "output/final.mp4"
        shutil.copy2(input_video, output_path)
        print_success(f"Original video copied to: {output_path}")
        sys.exit(0)
    
    # Step 4: Fetch visual assets
    print_step(5, 6, "Fetching visual assets...")
    try:
        pexels_key = os.getenv('PEXELS_API_KEY')
        if not pexels_key:
            print_error("PEXELS_API_KEY not found in environment")
            print_info("Get your free API key at: https://www.pexels.com/api/")
            sys.exit(1)
        
        decisions_with_assets = fetch_assets_for_decisions(
            decisions=decisions.insertions,
            output_dir="temp/assets",
            pexels_api_key=pexels_key,
            aspect_ratio=aspect_ratio
        )
        
        print_success(f"Assets fetched: {len(decisions_with_assets)}/{len(decisions.insertions)} successful")
        
        if not decisions_with_assets:
            print_warning("No assets could be downloaded")
            print_info("Returning original video")
            import shutil
            output_path = "output/final.mp4"
            shutil.copy2(input_video, output_path)
            print_success(f"Original video copied to: {output_path}")
            sys.exit(0)
    except Exception as e:
        print_error(f"Asset fetching failed: {str(e)}")
        sys.exit(1)
    
    # Step 5: Render final video
    print_step(6, 6, "Rendering final video with FFmpeg...")
    print_info("This may take several minutes...")
    
    try:
        output_path = "output/final.mp4"
        
        result = render_with_retry(
            video=input_video,
            decisions=decisions_with_assets,
            output=output_path,
            aspect_ratio=aspect_ratio,
            config=config['rendering']
        )
        
        # Get output info
        output_info = get_video_info(result)
        
        print_success(f"Video rendering complete!")
        print_info(f"Output: {result}")
        print_info(f"Size: {output_info['file_size_mb']}MB")
        print_info(f"Duration: {output_info['duration']:.1f}s")
        
        # Create thumbnail
        try:
            thumbnail = create_thumbnail(result, "output/thumbnail.jpg")
            print_success(f"Thumbnail created: {thumbnail}")
        except Exception as e:
            print_warning(f"Could not create thumbnail: {str(e)}")
        
    except Exception as e:
        print_error(f"Rendering failed: {str(e)}")
        logger.exception("Rendering error details:")
        sys.exit(1)
    
    # Final summary
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"  🎉 VIDEO EDITING COMPLETE! 🎉")
    print(f"{'='*60}{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}📁 Output file: {Fore.WHITE}{output_path}")
    print(f"{Fore.CYAN}🎬 Insertions applied: {Fore.WHITE}{len(decisions_with_assets)}")
    print(f"{Fore.CYAN}⏱️  Original duration: {Fore.WHITE}{video_info['duration']:.1f}s")
    print(f"{Fore.CYAN}📊 Output size: {Fore.WHITE}{output_info['file_size_mb']}MB{Style.RESET_ALL}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Process interrupted by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        logger.exception("Fatal error:")
        sys.exit(1)