#!/usr/bin/env python3
"""
Automated Weaviate backup script
Backs up all collections to JSON files with timestamps
Can be scheduled via cron or Windows Task Scheduler
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
import weaviate
from weaviate import WeaviateClient
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def connect_to_weaviate() -> WeaviateClient:
    """Connect to Weaviate with authentication"""
    weaviate_url = os.getenv('WEAVIATE_URL', 'http://localhost:8080')
    api_key = os.getenv('WEAVIATE_API_KEY')
    
    if api_key:
        # Parse URL to get host
        from urllib.parse import urlparse
        parsed = urlparse(weaviate_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 8080
        
        logger.info(f"Connecting to Weaviate at {host}:{port} with API key")
        
        # Use custom connection for API key auth
        import weaviate.auth as wvauth
        client = weaviate.connect_to_custom(
            http_host=host,
            http_port=port,
            http_secure=False,
            grpc_host=host,
            grpc_port=50051,
            grpc_secure=False,
            auth_credentials=wvauth.AuthApiKey(api_key)
        )
    else:
        logger.info("Connecting to local Weaviate without authentication")
        client = weaviate.connect_to_local()
    
    return client

def backup_collection(client: WeaviateClient, collection_name: str, backup_dir: Path) -> int:
    """Backup a single collection to JSON"""
    logger.info(f"Backing up collection: {collection_name}")
    
    try:
        collection = client.collections.get(collection_name)
        
        # Get all objects
        objects = []
        for item in collection.iterator():
            obj_data = {
                'uuid': str(item.uuid),
                'properties': item.properties,
                'vector': item.vector if hasattr(item, 'vector') else None
            }
            objects.append(obj_data)
        
        # Save to file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{collection_name}_{timestamp}.json"
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump({
                'collection': collection_name,
                'timestamp': timestamp,
                'count': len(objects),
                'objects': objects
            }, f, indent=2, default=str)
        
        logger.info(f"Backed up {len(objects)} objects to {backup_file}")
        return len(objects)
        
    except Exception as e:
        logger.error(f"Failed to backup {collection_name}: {e}")
        return 0

def cleanup_old_backups(backup_dir: Path, keep_days: int = 30):
    """Remove backups older than specified days"""
    from datetime import timedelta
    
    cutoff_date = datetime.now() - timedelta(days=keep_days)
    
    for backup_file in backup_dir.glob("*.json"):
        file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
        if file_time < cutoff_date:
            logger.info(f"Removing old backup: {backup_file}")
            backup_file.unlink()

def main():
    """Main backup process"""
    # Create backup directory
    backup_dir = Path(__file__).parent.parent / "backups" / "weaviate"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting Weaviate backup to {backup_dir}")
    
    try:
        # Connect to Weaviate
        client = connect_to_weaviate()
        
        # Get all collections
        collections = client.collections.list_all()
        logger.info(f"Found {len(collections)} collections to backup")
        
        # Backup each collection
        total_objects = 0
        for collection_name in collections:
            count = backup_collection(client, collection_name, backup_dir)
            total_objects += count
        
        # Clean up old backups
        cleanup_old_backups(backup_dir)
        
        # Create summary file
        summary = {
            'timestamp': datetime.now().isoformat(),
            'collections': list(collections),
            'total_objects': total_objects,
            'backup_dir': str(backup_dir)
        }
        
        summary_file = backup_dir / f"backup_summary_{datetime.now().strftime('%Y%m%d')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Backup complete! {len(collections)} collections, {total_objects} total objects")
        
        # Close connection
        client.close()
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise

if __name__ == "__main__":
    main()