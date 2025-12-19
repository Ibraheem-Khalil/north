"""
Auto-sync Obsidian vault with Weaviate database
Can be run manually or scheduled with Task Scheduler/cron
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime
# Import from the same weaviate_tools folder
from .atomic_document_ingestion import AtomicObsidianIngestion as ObsidianIngestion
from dotenv import load_dotenv

def sync_vault(vault_path: str = None, watch: bool = False):
    """
    Sync Obsidian vault with Weaviate
    
    Args:
        vault_path: Path to Obsidian vault (uses env var if not provided)
        watch: If True, continuously watch for changes
    """
    load_dotenv()
    
    # Get vault path
    if not vault_path:
        vault_path = os.getenv('OBSIDIAN_VAULT_PATH')
        if not vault_path:
            vault_path = input("Enter path to your Obsidian vault: ").strip()
    
    if not os.path.exists(vault_path):
        print(f"❌ Vault path not found: {vault_path}")
        return
    
    print(f"📁 Syncing vault: {vault_path}")
    
    # Initialize ingestion
    ingestion = ObsidianIngestion()
    ingestion.connect()
    
    # Track file modification times
    file_times = {}
    
    while True:
        print(f"\n🔄 Syncing at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Find all .md files
        md_files = list(Path(vault_path).rglob("*.md"))
        new_or_modified = []
        
        for filepath in md_files:
            # Get file modification time
            mtime = filepath.stat().st_mtime
            
            # Check if file is new or modified
            if str(filepath) not in file_times or file_times[str(filepath)] < mtime:
                new_or_modified.append(filepath)
                file_times[str(filepath)] = mtime
        
        # Process new/modified files
        if new_or_modified:
            print(f"📝 Found {len(new_or_modified)} new/modified files")
            for filepath in new_or_modified:
                ingestion.ingest_file(filepath)
        else:
            print("✅ No changes detected")
        
        # Show current stats
        ingestion.verify_ingestion()
        
        if not watch:
            break
        
        # Wait before next sync (5 minutes)
        print("\n💤 Waiting 5 minutes before next sync...")
        print("   (Press Ctrl+C to stop)")
        try:
            time.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            print("\n👋 Stopping sync")
            break
    
    # Cleanup
    ingestion.client.close()

def main():
    import sys
    
    # Check command line args
    watch_mode = '--watch' in sys.argv
    vault_path = None
    
    for arg in sys.argv[1:]:
        if arg != '--watch':
            vault_path = arg
    
    print("🚀 NORTH Obsidian Sync Tool")
    print("=" * 40)
    
    if watch_mode:
        print("👁️  Watch mode enabled - will sync every 5 minutes")
    
    sync_vault(vault_path, watch=watch_mode)

if __name__ == "__main__":
    main()