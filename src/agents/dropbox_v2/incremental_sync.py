"""
Incremental Sync for Dropbox Files
Implements cursor-based change detection and daily sync
Cursor-based incremental indexing for production use
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import os

from .dropbox_client import DropboxClient
from .document_processor import DocumentProcessor
from .weaviate_indexer import WeaviateIndexer

logger = logging.getLogger(__name__)


class IncrementalSync:
    """
    Handles incremental syncing of Dropbox files to Weaviate
    Uses cursors for efficient change detection
    """
    
    def __init__(self, root_path: str = None):
        """
        Initialize incremental sync
        
        Args:
            root_path: Root path in Dropbox to sync (defaults to env var)
        """
        self.root_path = root_path or os.getenv("DROPBOX_ROOT_PATH", "/COMPANY_FILES")
        self.dropbox = DropboxClient()
        self.processor = DocumentProcessor()
        self.indexer = WeaviateIndexer()
        
        # Sync state file
        self.state_file = Path("dropbox_sync_state.json")
        self.sync_state = self._load_sync_state()
        
        logger.info(f"IncrementalSync initialized for {root_path}")
    
    def _load_sync_state(self) -> Dict[str, Any]:
        """Load sync state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load sync state: {e}")
        
        return {
            'last_sync': None,
            'total_indexed': 0,
            'last_cursor': None,
            'sync_history': []
        }
    
    def _save_sync_state(self) -> None:
        """Save sync state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.sync_state, f, indent=2, default=str)
            logger.debug("Saved sync state")
        except Exception as e:
            logger.error(f"Failed to save sync state: {e}")
    
    def perform_initial_sync(self) -> Dict[str, Any]:
        """
        Perform initial full sync of all files
        This is run once to establish baseline
        
        Returns:
            Sync statistics
        """
        logger.info("Starting initial full sync...")
        stats = {
            'started_at': datetime.utcnow().isoformat(),
            'files_processed': 0,
            'files_indexed': 0,
            'files_failed': 0,
            'folders_found': 0
        }
        
        try:
            # List all files recursively
            for file_metadata in self.dropbox.list_folder(self.root_path, recursive=True):
                if file_metadata['type'] == 'folder':
                    stats['folders_found'] += 1
                    continue
                
                if file_metadata['type'] != 'file':
                    continue
                
                # Check if it's a supported file type
                file_path = file_metadata['path_display']
                if not self._should_index_file(file_path):
                    logger.debug(f"Skipping unsupported file: {file_path}")
                    continue
                
                stats['files_processed'] += 1
                
                # Download and process file
                success = self._process_and_index_file(file_metadata)
                if success:
                    stats['files_indexed'] += 1
                else:
                    stats['files_failed'] += 1
                
                # Log progress every 10 files
                if stats['files_processed'] % 10 == 0:
                    logger.info(f"Progress: {stats['files_processed']} files processed, "
                              f"{stats['files_indexed']} indexed")
            
            # Update sync state
            stats['completed_at'] = datetime.utcnow().isoformat()
            stats['duration_seconds'] = (
                datetime.fromisoformat(stats['completed_at']) - 
                datetime.fromisoformat(stats['started_at'])
            ).total_seconds()
            
            self.sync_state['last_sync'] = stats['completed_at']
            self.sync_state['total_indexed'] = stats['files_indexed']
            self.sync_state['sync_history'].append(stats)
            self._save_sync_state()
            
            logger.info(f"Initial sync completed: {stats['files_indexed']} files indexed")
            return stats
            
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")
            stats['error'] = str(e)
            return stats
    
    def perform_incremental_sync(self) -> Dict[str, Any]:
        """
        Perform incremental sync using cursors
        Only processes files that changed since last sync
        
        Returns:
            Sync statistics
        """
        logger.info("Starting incremental sync...")
        stats = {
            'started_at': datetime.utcnow().isoformat(),
            'changes_processed': 0,
            'files_added': 0,
            'files_modified': 0,
            'files_deleted': 0,
            'files_failed': 0
        }
        
        try:
            # Get changes since last sync
            changes_found = False
            for change in self.dropbox.list_folder_changes(self.root_path):
                changes_found = True
                change_type = change.get('change_type', 'unknown')
                
                if change_type == 'deleted':
                    # Remove from index
                    self._remove_from_index(change)
                    stats['files_deleted'] += 1
                    
                elif change_type == 'added_or_modified':
                    # Check if it's a supported file
                    if not self._should_index_file(change['path_display']):
                        continue
                    
                    # Process and index
                    success = self._process_and_index_file(change)
                    if success:
                        # Determine if add or modify based on existing index
                        if self._file_exists_in_index(change['id']):
                            stats['files_modified'] += 1
                        else:
                            stats['files_added'] += 1
                    else:
                        stats['files_failed'] += 1
                
                stats['changes_processed'] += 1
                
                # Log progress
                if stats['changes_processed'] % 5 == 0:
                    logger.info(f"Processed {stats['changes_processed']} changes")
            
            if not changes_found:
                logger.info("No changes detected since last sync")
            
            # Update sync state
            stats['completed_at'] = datetime.utcnow().isoformat()
            stats['duration_seconds'] = (
                datetime.fromisoformat(stats['completed_at']) - 
                datetime.fromisoformat(stats['started_at'])
            ).total_seconds()
            
            self.sync_state['last_sync'] = stats['completed_at']
            self.sync_state['sync_history'].append(stats)
            
            # Keep only last 30 days of history
            cutoff = datetime.utcnow() - timedelta(days=30)
            self.sync_state['sync_history'] = [
                h for h in self.sync_state['sync_history']
                if datetime.fromisoformat(h['started_at']) > cutoff
            ]
            
            self._save_sync_state()
            
            logger.info(f"Incremental sync completed: {stats['changes_processed']} changes, "
                       f"{stats['files_added']} added, {stats['files_modified']} modified, "
                       f"{stats['files_deleted']} deleted")
            return stats
            
        except Exception as e:
            logger.error(f"Incremental sync failed: {e}")
            stats['error'] = str(e)
            return stats
    
    def _should_index_file(self, file_path: str) -> bool:
        """Check if file should be indexed based on type"""
        supported_extensions = {'.pdf', '.txt', '.md', '.csv', '.doc', '.docx'}
        ext = Path(file_path).suffix.lower()
        return ext in supported_extensions
    
    def _process_and_index_file(self, file_metadata: Dict[str, Any]) -> bool:
        """
        Download, process, and index a single file
        
        Args:
            file_metadata: File metadata from Dropbox
            
        Returns:
            True if successful
        """
        try:
            file_path = file_metadata['path_display']
            logger.debug(f"Processing {file_path}")
            
            # Download file content
            content = self.dropbox.download_file(file_path)
            if not content:
                logger.error(f"Failed to download {file_path}")
                return False
            
            # Process document
            document = self.processor.process_document(content, file_metadata)
            if not document:
                logger.warning(f"Failed to process {file_path}")
                return False
            
            # Index in Weaviate
            success = self.indexer.index_document(document)
            if success:
                logger.debug(f"Successfully indexed {file_path}")
                return True
            else:
                logger.error(f"Failed to index {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing file {file_metadata.get('path_display')}: {e}")
            return False
    
    def _remove_from_index(self, file_metadata: Dict[str, Any]) -> bool:
        """Remove deleted file from index"""
        try:
            file_id = file_metadata.get('id')
            if file_id:
                return self.indexer.delete_document(file_id)
            return False
        except Exception as e:
            logger.error(f"Failed to remove file from index: {e}")
            return False
    
    def _file_exists_in_index(self, file_id: str) -> bool:
        """Check if file already exists in index"""
        try:
            return self.indexer.document_exists(file_id)
        except Exception:
            return False
    
    def run_daily_sync(self) -> Dict[str, Any]:
        """
        Main entry point for daily scheduled sync
        Determines whether to run initial or incremental sync
        
        Returns:
            Sync statistics
        """
        logger.info("Starting daily sync job...")
        
        # Check if we've done initial sync
        if not self.sync_state.get('last_sync'):
            logger.info("No previous sync found, running initial sync")
            return self.perform_initial_sync()
        
        # Check when last sync was
        last_sync = datetime.fromisoformat(self.sync_state['last_sync'])
        days_since_sync = (datetime.utcnow() - last_sync).days
        
        if days_since_sync > 30:
            # Cursor might be expired, do full resync
            logger.warning(f"Last sync was {days_since_sync} days ago, running full resync")
            return self.perform_initial_sync()
        
        # Run incremental sync
        return self.perform_incremental_sync()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics"""
        status = {
            'last_sync': self.sync_state.get('last_sync'),
            'total_indexed': self.sync_state.get('total_indexed', 0),
            'sync_count': len(self.sync_state.get('sync_history', [])),
        }
        
        # Add recent sync stats
        if self.sync_state.get('sync_history'):
            recent = self.sync_state['sync_history'][-1]
            status['last_sync_stats'] = {
                'duration_seconds': recent.get('duration_seconds'),
                'changes_processed': recent.get('changes_processed', 0),
                'files_added': recent.get('files_added', 0),
                'files_modified': recent.get('files_modified', 0),
                'files_deleted': recent.get('files_deleted', 0)
            }
        
        # Calculate next sync time (if daily)
        if status['last_sync']:
            last = datetime.fromisoformat(status['last_sync'])
            next_sync = last + timedelta(days=1)
            status['next_sync'] = next_sync.isoformat()
            status['next_sync_in_hours'] = max(0, (next_sync - datetime.utcnow()).total_seconds() / 3600)
        
        return status


# Command-line interface for manual sync
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    sync = IncrementalSync()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'initial':
        print("Running initial full sync...")
        stats = sync.perform_initial_sync()
    elif len(sys.argv) > 1 and sys.argv[1] == 'status':
        status = sync.get_sync_status()
        print(json.dumps(status, indent=2, default=str))
    else:
        print("Running daily sync...")
        stats = sync.run_daily_sync()
    
    print(f"Sync completed: {json.dumps(stats, indent=2, default=str)}")
