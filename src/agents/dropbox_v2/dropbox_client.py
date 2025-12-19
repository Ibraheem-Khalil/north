"""
Clean Dropbox API Client Wrapper
Handles authentication, API calls, and cursor management
No business logic - pure API interface
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Generator
from datetime import datetime
from pathlib import Path
import dropbox
from dropbox.files import FileMetadata, FolderMetadata, DeletedMetadata
from dropbox.common import PathRoot
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log
)

load_dotenv()
logger = logging.getLogger(__name__)


class DropboxClient:
    """
    Clean wrapper around Dropbox API
    Handles auth, cursors, and API calls
    No hardcoded paths or business logic
    """
    
    def __init__(self):
        """Initialize Dropbox client with token management"""
        self.access_token = self._get_valid_token()
        
        # Initialize client for team space access
        if self.access_token:
            team_member_id = os.getenv("DROPBOX_TEAM_MEMBER_ID")
            namespace_id = os.getenv("DROPBOX_NAMESPACE_ID")
            
            if team_member_id and namespace_id:
                # Use DropboxTeam for Business accounts with namespace
                team = dropbox.DropboxTeam(self.access_token)
                # Set user context for team member
                client = team.as_user(team_member_id)
                
                # Set namespace path root to access team folders
                # This is critical for accessing team space instead of personal space
                path_root = PathRoot.namespace_id(namespace_id)
                self.client = client.with_path_root(path_root)
                
                logger.info(f"Dropbox client initialized for team space (member: {team_member_id}, namespace: {namespace_id})")
            else:
                # Fallback to regular personal account
                self.client = dropbox.Dropbox(self.access_token)
                logger.info("Dropbox client initialized (personal account)")
        else:
            self.client = None
            
        self.cursor_file = Path("dropbox_cursor_state.json")
        self.cursors = self._load_cursors()
        
        if not self.client:
            logger.error("Failed to initialize Dropbox client - no valid token")
    
    def _get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token using the token manager
        Handles encryption/decryption and auto-refresh
        """
        # Check environment variable first (local development)
        # This allows simple configuration via .env file
        token = os.getenv("DROPBOX_ACCESS_TOKEN")
        if token:
            return token

        # Use token manager for encrypted storage and auto-refresh (production)
        try:
            from src.agents.dropbox_v2.dropbox_token_manager import DropboxTokenManager
            token_manager = DropboxTokenManager()
            
            # Get fresh token (will auto-refresh if needed)
            token = token_manager.get_valid_token()
            if token:
                logger.info("Got valid token from token manager")
                return token
        except Exception as e:
            logger.error(f"Failed to get token from manager: {e}")
        
        return None
    
    def _load_cursors(self) -> Dict[str, str]:
        """Load saved cursors for incremental sync"""
        if self.cursor_file.exists():
            try:
                with open(self.cursor_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cursors: {e}")
        return {}
    
    def _save_cursors(self) -> None:
        """Save cursors for next incremental sync"""
        try:
            with open(self.cursor_file, 'w') as f:
                json.dump(self.cursors, f, indent=2)
            logger.debug("Saved cursors for incremental sync")
        except Exception as e:
            logger.error(f"Failed to save cursors: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        before=before_log(logger, logging.DEBUG),
        after=after_log(logger, logging.DEBUG)
    )
    def _list_folder_with_retry(self, path: str, recursive: bool, include_deleted: bool):
        """List folder with retry logic for rate limiting"""
        return self.client.files_list_folder(
            path=path,
            recursive=recursive,
            include_deleted=include_deleted
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        before=before_log(logger, logging.DEBUG),
        after=after_log(logger, logging.DEBUG)
    )
    def _list_folder_continue_with_retry(self, cursor: str):
        """Continue listing folder with retry logic"""
        return self.client.files_list_folder_continue(cursor)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        before=before_log(logger, logging.DEBUG),
        after=after_log(logger, logging.DEBUG)
    )
    def _download_with_retry(self, path: str):
        """Download file with retry logic"""
        return self.client.files_download(path)
    
    def list_folder(self, path: str = "", recursive: bool = True, 
                   include_deleted: bool = False) -> Generator[Dict, None, None]:
        """
        List all files in a folder
        Yields file metadata as dictionaries
        
        Args:
            path: Folder path to list (empty string for root)
            recursive: Whether to list recursively
            include_deleted: Whether to include deleted files
            
        Yields:
            File metadata dictionaries
        """
        if not self.client:
            logger.error("No Dropbox client available")
            return
        
        try:
            # Initial folder listing with retry logic
            result = self._list_folder_with_retry(
                path=path,
                recursive=recursive,
                include_deleted=include_deleted
            )
            
            # Process initial batch
            for entry in result.entries:
                yield self._entry_to_dict(entry)
            
            # Continue if there are more results
            while result.has_more:
                result = self._list_folder_continue_with_retry(result.cursor)
                for entry in result.entries:
                    yield self._entry_to_dict(entry)
            
            # Save cursor for this path for incremental sync
            self.cursors[path or "root"] = result.cursor
            self._save_cursors()
            
        except Exception as e:
            logger.error(f"Failed to list folder {path}: {e}")
    
    def list_folder_changes(self, path: str = "") -> Generator[Dict, None, None]:
        """
        List only changes since last sync using cursor
        This is the key to incremental indexing
        
        Args:
            path: Folder path to check for changes
            
        Yields:
            Changed file metadata
        """
        if not self.client:
            logger.error("No Dropbox client available")
            return
        
        cursor = self.cursors.get(path or "root")
        
        if not cursor:
            logger.info(f"No cursor for {path}, doing full listing")
            # No cursor means we need to do initial sync
            yield from self.list_folder(path)
            return
        
        try:
            # Get changes since cursor with retry logic
            result = self._list_folder_continue_with_retry(cursor)
            
            has_changes = False
            for entry in result.entries:
                has_changes = True
                change_data = self._entry_to_dict(entry)
                change_data['change_type'] = self._determine_change_type(entry)
                yield change_data
            
            # Continue if there are more changes
            while result.has_more:
                result = self._list_folder_continue_with_retry(result.cursor)
                for entry in result.entries:
                    has_changes = True
                    change_data = self._entry_to_dict(entry)
                    change_data['change_type'] = self._determine_change_type(entry)
                    yield change_data
            
            # Update cursor
            self.cursors[path or "root"] = result.cursor
            self._save_cursors()
            
            if not has_changes:
                logger.info(f"No changes detected for {path}")
            
        except dropbox.exceptions.ApiError as e:
            if e.error.is_reset():
                logger.warning(f"Cursor expired for {path}, doing full resync")
                # Cursor expired, need full resync
                del self.cursors[path or "root"]
                yield from self.list_folder(path)
            else:
                logger.error(f"API error checking changes: {e}")
    
    def _entry_to_dict(self, entry) -> Dict[str, Any]:
        """Convert Dropbox entry to dictionary"""
        data = {
            'name': entry.name,
            'path_lower': entry.path_lower,
            'path_display': entry.path_display,
            'id': entry.id
        }
        
        if isinstance(entry, FileMetadata):
            data.update({
                'type': 'file',
                'size': entry.size,
                'server_modified': entry.server_modified.isoformat() if entry.server_modified else None,
                'client_modified': entry.client_modified.isoformat() if entry.client_modified else None,
                'rev': entry.rev,
                'content_hash': entry.content_hash
            })
        elif isinstance(entry, FolderMetadata):
            data.update({
                'type': 'folder'
            })
        elif isinstance(entry, DeletedMetadata):
            data.update({
                'type': 'deleted'
            })
        
        return data
    
    def _determine_change_type(self, entry) -> str:
        """Determine what kind of change this is"""
        if isinstance(entry, DeletedMetadata):
            return 'deleted'
        elif isinstance(entry, FileMetadata):
            # Could check if file exists in our index to determine if new or modified
            # For now, mark as 'added_or_modified'
            return 'added_or_modified'
        elif isinstance(entry, FolderMetadata):
            return 'folder_change'
        return 'unknown'
    
    def download_file(self, path: str) -> Optional[bytes]:
        """
        Download file content
        
        Args:
            path: File path in Dropbox
            
        Returns:
            File content as bytes
        """
        if not self.client:
            return None
        
        try:
            metadata, response = self._download_with_retry(path)
            content = response.content
            logger.debug(f"Downloaded {len(content)} bytes from {path}")
            return content
        except Exception as e:
            logger.error(f"Failed to download {path}: {e}")
            return None
    
    def get_temporary_link(self, path: str) -> Optional[str]:
        """
        Get temporary download link for a file
        Useful for large files or streaming
        
        Args:
            path: File path in Dropbox
            
        Returns:
            Temporary download URL
        """
        if not self.client:
            return None
        
        try:
            link_result = self.client.files_get_temporary_link(path)
            return link_result.link
        except Exception as e:
            logger.error(f"Failed to get temporary link for {path}: {e}")
            return None
    
    def search_files(self, query: str, path: str = "", 
                    max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Search files using Dropbox search API
        This is a fallback - primary search should be through Weaviate
        
        Args:
            query: Search query
            path: Path to search in (empty for all)
            max_results: Maximum results to return
            
        Returns:
            List of matching files
        """
        if not self.client:
            return []
        
        try:
            # Configure search options
            options = dropbox.files.SearchOptions(
                path=path if path else None,
                max_results=min(max_results, 100),  # API limit
                file_status=dropbox.files.FileStatus.active,
                filename_only=False  # Search content too if available
            )
            
            # Execute search
            result = self.client.files_search_v2(query, options=options)
            
            matches = []
            for match in result.matches:
                if hasattr(match, 'metadata') and hasattr(match.metadata, 'metadata'):
                    file_data = self._entry_to_dict(match.metadata.metadata)
                    # Add search-specific metadata
                    if hasattr(match, 'match_type'):
                        file_data['match_type'] = str(match.match_type)
                    matches.append(file_data)
            
            logger.info(f"Dropbox search for '{query}' found {len(matches)} results")
            return matches
            
        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}")
            return []
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the connected Dropbox account"""
        if not self.client:
            return None
        
        try:
            account = self.client.users_get_current_account()
            return {
                'account_id': account.account_id,
                'email': account.email,
                'name': account.name.display_name,
                'account_type': str(account.account_type)
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test if the Dropbox connection is working"""
        return self.get_account_info() is not None