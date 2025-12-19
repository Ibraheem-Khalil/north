"""
Dropbox Token Manager - Handles automatic token refresh for Dropbox API with encryption
"""

import os
import json
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv, set_key
from src.utils.crypto_utils import get_secure_token_manager, secure_getenv, validate_dropbox_config

load_dotenv()
logger = logging.getLogger(__name__)

class DropboxTokenManager:
    """Manages Dropbox OAuth2 tokens with automatic refresh"""
    
    def __init__(self):
        """Initialize token manager with secure configuration"""
        # Validate configuration first
        try:
            config = validate_dropbox_config()
            self.app_key = config["DROPBOX_APP_KEY"]
            self.app_secret = config["DROPBOX_APP_SECRET"] 
            self.refresh_token = config["DROPBOX_REFRESH_TOKEN"]
        except ValueError as e:
            logger.error(f"Invalid Dropbox configuration: {e}")
            raise
        
        # Initialize encryption manager
        self.crypto_manager = get_secure_token_manager()
        
        # Token cache file
        self.token_cache_file = Path("dropbox_token_cache.json")
        self.env_file = Path(".env")
        
        # Current access token and expiry
        self.access_token = None
        self.token_expiry = None
        
        # Load cached token if available
        self._load_cached_token()
        
        # If no valid token, try to refresh
        if not self._is_token_valid():
            self.refresh_access_token()
    
    def _load_cached_token(self):
        """Load and decrypt token from cache file if it exists"""
        if self.token_cache_file.exists():
            try:
                with open(self.token_cache_file, 'r') as f:
                    cache = json.load(f)
                    
                    # Decrypt token if present
                    encrypted_token = cache.get('encrypted_access_token')
                    if encrypted_token:
                        self.access_token = self.crypto_manager.decrypt(encrypted_token)
                    
                    expiry_str = cache.get('expiry')
                    if expiry_str:
                        self.token_expiry = datetime.fromisoformat(expiry_str)
                    
                    logger.info("Loaded and decrypted cached Dropbox token")
            except Exception as e:
                logger.error(f"Failed to load token cache: {e}")
                # Clear corrupted cache
                self._clear_cache()
        else:
            # Try to use the token from .env (might be expired) - migrate to encrypted
            env_token = secure_getenv("DROPBOX_ACCESS_TOKEN")
            if env_token:
                self.access_token = env_token
                logger.warning("Using unencrypted token from .env - will encrypt on next save")
    
    def _save_token_cache(self):
        """Save current token to cache file with encryption"""
        try:
            # Encrypt the access token
            encrypted_token = self.crypto_manager.encrypt(self.access_token)
            
            cache = {
                'encrypted_access_token': encrypted_token,
                'expiry': self.token_expiry.isoformat() if self.token_expiry else None,
                'updated_at': datetime.now().isoformat(),
                'token_hash': self.crypto_manager.hash_data(self.access_token)  # For integrity verification
            }
            
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
            
            # Update .env file with encrypted token for other processes
            if self.env_file.exists():
                set_key(str(self.env_file), "DROPBOX_ACCESS_TOKEN_ENCRYPTED", encrypted_token)
                # Remove old unencrypted token if it exists
                set_key(str(self.env_file), "DROPBOX_ACCESS_TOKEN", "")
            
            logger.info("Saved encrypted token to cache and .env")
        except Exception as e:
            logger.error(f"Failed to save token cache: {e}")
    
    def _clear_cache(self):
        """Clear corrupted cache file"""
        try:
            if self.token_cache_file.exists():
                self.token_cache_file.unlink()
                logger.info("Cleared corrupted token cache")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def _is_token_valid(self):
        """Check if current token is still valid"""
        if not self.access_token:
            return False
        
        # If we don't know expiry, assume it's expired
        if not self.token_expiry:
            return False
        
        # Check if token expires in next 5 minutes (buffer time)
        buffer_time = timedelta(minutes=5)
        return datetime.now() < (self.token_expiry - buffer_time)
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            logger.error("No refresh token available. Need to re-authenticate.")
            raise ValueError("No refresh token available")
        
        if not self.app_key or not self.app_secret:
            logger.error("App key and secret required for token refresh")
            raise ValueError("Missing app credentials")
        
        try:
            logger.info("Refreshing Dropbox access token...")
            
            # Make refresh request with timeout to prevent hanging
            response = requests.post(
                "https://api.dropboxapi.com/oauth2/token",
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id': self.app_key,
                    'client_secret': self.app_secret
                },
                timeout=30  # Prevent hanging on network issues
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data['access_token']
                
                # Calculate expiry (Dropbox tokens typically last 4 hours)
                expires_in = data.get('expires_in', 14400)  # Default 4 hours
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                
                # Save to cache
                self._save_token_cache()
                
                logger.info(f"Token refreshed successfully, expires at {self.token_expiry}")
                return self.access_token
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                raise Exception(f"Token refresh failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise
    
    def get_valid_token(self):
        """Get a valid access token, refreshing if necessary"""
        if not self._is_token_valid():
            self.refresh_access_token()
        return self.access_token
    
    def get_headers(self, team_member_id=None, namespace_id=None):
        """Get headers with valid token for Dropbox API requests"""
        token = self.get_valid_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        if team_member_id:
            headers["Dropbox-API-Select-User"] = team_member_id
        
        if namespace_id:
            headers["Dropbox-API-Path-Root"] = json.dumps({
                ".tag": "namespace_id",
                "namespace_id": namespace_id
            })
        
        return headers
    
    def test_connection(self):
        """Test if current token works"""
        try:
            token = self.get_valid_token()
            
            # For business accounts, we need the team member ID
            headers = {"Authorization": f"Bearer {token}"}
            team_member_id = os.getenv("DROPBOX_TEAM_MEMBER_ID")
            if team_member_id:
                headers["Dropbox-API-Select-User"] = team_member_id
            
            response = requests.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers=headers,
                timeout=30  # Add timeout for consistency
            )
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Token valid for user: {user_data.get('email')}")
                return True
            else:
                logger.error(f"Token test failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


# Singleton instance
_token_manager = None

def get_token_manager():
    """Get or create the singleton token manager"""
    global _token_manager
    if _token_manager is None:
        _token_manager = DropboxTokenManager()
    return _token_manager
