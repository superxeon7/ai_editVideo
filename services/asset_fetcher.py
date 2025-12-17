import os
import logging
import requests
from typing import Optional, Dict
from pathlib import Path
from models.decision import VisualInsertion
from utils.validators import sanitize_filename

logger = logging.getLogger(__name__)


class AssetFetchError(Exception):
    """Custom exception for asset fetching errors"""
    pass


def fetch_assets_for_decisions(
    decisions: list,
    output_dir: str,
    pexels_api_key: str,
    aspect_ratio: str = "9:16"
) -> list:
    """
    Fetch visual assets for all insertion decisions
    
    Args:
        decisions: List of VisualInsertion objects
        output_dir: Directory to save downloaded assets
        pexels_api_key: Pexels API key
        aspect_ratio: Video aspect ratio for orientation filtering
        
    Returns:
        List of decisions with asset_path populated
    """
    os.makedirs(output_dir, exist_ok=True)
    
    successful_downloads = []
    
    for idx, decision in enumerate(decisions):
        try:
            logger.info(
                f"Fetching asset {idx+1}/{len(decisions)}: "
                f"'{decision.search_query}' for word '{decision.word}'"
            )
            
            asset_info = search_pexels(
                query=decision.search_query,
                api_key=pexels_api_key,
                orientation="portrait" if aspect_ratio == "9:16" else "landscape",
                media_type="videos"  # Prefer videos over images
            )
            
            if not asset_info:
                # Fallback: try with just entity type
                logger.warning(f"No results for '{decision.search_query}', trying '{decision.entity_type}'")
                asset_info = search_pexels(
                    query=decision.entity_type,
                    api_key=pexels_api_key,
                    orientation="portrait" if aspect_ratio == "9:16" else "landscape",
                    media_type="videos"
                )
            
            if asset_info:
                # Download asset
                asset_path = download_asset(
                    url=asset_info['url'],
                    output_dir=output_dir,
                    filename=f"{sanitize_filename(decision.word)}_{idx}.{asset_info['extension']}"
                )
                
                decision.asset_path = asset_path
                decision.asset_type = asset_info['type']
                successful_downloads.append(decision)
                
                logger.info(f"Asset downloaded successfully: {asset_path}")
            else:
                logger.warning(
                    f"No asset found for '{decision.word}' - "
                    f"insertion will be skipped"
                )
        
        except Exception as e:
            logger.error(f"Failed to fetch asset for '{decision.word}': {str(e)}")
            continue
    
    logger.info(
        f"Asset fetching complete: {len(successful_downloads)}/{len(decisions)} successful"
    )
    
    return successful_downloads


def search_pexels(
    query: str,
    api_key: str,
    orientation: str = "portrait",
    media_type: str = "videos",
    per_page: int = 1
) -> Optional[Dict]:
    """
    Search Pexels for media
    
    Args:
        query: Search query
        api_key: Pexels API key
        orientation: 'portrait' or 'landscape'
        media_type: 'videos' or 'photos'
        per_page: Number of results
        
    Returns:
        Dictionary with asset info or None
    """
    try:
        if media_type == "videos":
            url = "https://api.pexels.com/videos/search"
        else:
            url = "https://api.pexels.com/v1/search"
        
        headers = {
            "Authorization": api_key
        }
        
        params = {
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
            "size": "medium"  # medium quality for faster downloads
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if media_type == "videos":
            videos = data.get('videos', [])
            if not videos:
                return None
            
            video = videos[0]
            video_files = video.get('video_files', [])
            
            # Find suitable video file (prefer HD but not 4K)
            suitable_file = None
            for vf in video_files:
                if vf.get('quality') in ['hd', 'sd']:
                    suitable_file = vf
                    break
            
            if not suitable_file and video_files:
                suitable_file = video_files[0]
            
            if not suitable_file:
                return None
            
            return {
                'url': suitable_file['link'],
                'type': 'video',
                'extension': 'mp4',
                'width': suitable_file.get('width', 0),
                'height': suitable_file.get('height', 0)
            }
        
        else:  # photos
            photos = data.get('photos', [])
            if not photos:
                return None
            
            photo = photos[0]
            src = photo.get('src', {})
            
            return {
                'url': src.get('large', src.get('original')),
                'type': 'image',
                'extension': 'jpg',
                'width': photo.get('width', 0),
                'height': photo.get('height', 0)
            }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Pexels API request failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error searching Pexels: {str(e)}")
        return None


def download_asset(url: str, output_dir: str, filename: str, timeout: int = 30) -> str:
    """
    Download asset from URL
    
    Args:
        url: Asset URL
        output_dir: Output directory
        filename: Output filename
        timeout: Download timeout in seconds
        
    Returns:
        Path to downloaded file
        
    Raises:
        AssetFetchError: If download fails
    """
    output_path = os.path.join(output_dir, filename)
    
    try:
        logger.debug(f"Downloading asset from: {url}")
        
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                chunk_size = 8192
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
        
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.debug(f"Downloaded {file_size_mb:.2f}MB to {output_path}")
        
        return output_path
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download asset: {str(e)}")
        raise AssetFetchError(f"Download failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error downloading asset: {str(e)}")
        raise AssetFetchError(f"Download error: {str(e)}")


def get_placeholder_asset(placeholder_dir: str = "assets/placeholders") -> str:
    """
    Get path to placeholder asset
    
    Args:
        placeholder_dir: Directory containing placeholder assets
        
    Returns:
        Path to placeholder file
    """
    placeholder_path = os.path.join(placeholder_dir, "generic.jpg")
    
    if os.path.exists(placeholder_path):
        return placeholder_path
    
    # Create a simple placeholder if it doesn't exist
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        os.makedirs(placeholder_dir, exist_ok=True)
        
        # Create 1080x1920 placeholder for vertical video
        img = Image.new('RGB', (1080, 1920), color=(50, 50, 50))
        draw = ImageDraw.Draw(img)
        
        # Add text
        text = "Visual Asset"
        bbox = draw.textbbox((0, 0), text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        position = ((1080 - text_width) // 2, (1920 - text_height) // 2)
        draw.text(position, text, fill=(200, 200, 200))
        
        img.save(placeholder_path, 'JPEG')
        logger.info(f"Created placeholder asset: {placeholder_path}")
        
        return placeholder_path
    
    except Exception as e:
        logger.error(f"Failed to create placeholder: {str(e)}")
        raise AssetFetchError("No placeholder available")