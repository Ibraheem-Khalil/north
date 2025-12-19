"""
Cryptographic utilities for secure token and data management
"""

import os
import base64
import hashlib
from typing import Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class SecureTokenManager:
    """Handles encryption/decryption of sensitive tokens and data"""
    
    def __init__(self, master_key: Optional[str] = None):
        """Initialize with master key from environment or generate one"""
        if master_key:
            self.master_key = master_key.encode()
        else:
            # Try to get from environment
            env_key = os.getenv("NORTH_MASTER_KEY")
            if env_key:
                self.master_key = env_key.encode()
            else:
                # Generate a new key and warn user
                self.master_key = self._generate_master_key()
                print("WARNING: Generated new master key. Set NORTH_MASTER_KEY environment variable.")

        # Allow configurable salt to avoid fixed salt in production
        salt_env = os.getenv("NORTH_KDF_SALT")
        if salt_env:
            self._salt = salt_env.encode()
        else:
            self._salt = b'north_ai_salt_2024'
            logger.warning("Using default static salt; set NORTH_KDF_SALT for stronger security")
        
        # Derive encryption key from master key
        self._cipher = self._create_cipher(self.master_key, self._salt)
    
    def _generate_master_key(self) -> bytes:
        """Generate a cryptographically secure master key"""
        return os.urandom(32)
    
    def _create_cipher(self, master_key: bytes, salt: bytes) -> Fernet:
        """Create Fernet cipher from master key"""
        # Use PBKDF2 to derive a proper Fernet key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key))
        return Fernet(key)
    
    def encrypt(self, data: Union[str, bytes]) -> str:
        """Encrypt data and return base64 encoded string"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        encrypted = self._cipher.encrypt(data)
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt base64 encoded encrypted data"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to decrypt data: {e}")
    
    def hash_data(self, data: str) -> str:
        """Create SHA-256 hash of data for verification"""
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
    
    def verify_hash(self, data: str, expected_hash: str) -> bool:
        """Verify data against expected hash"""
        return self.hash_data(data) == expected_hash


def get_secure_token_manager() -> SecureTokenManager:
    """Get singleton instance of secure token manager"""
    if not hasattr(get_secure_token_manager, '_instance'):
        get_secure_token_manager._instance = SecureTokenManager()
    return get_secure_token_manager._instance


def secure_getenv(key: str, default: Optional[str] = None) -> Optional[str]:
    """Securely get environment variable with validation"""
    value = os.getenv(key, default)
    
    # Validate sensitive environment variables
    if key in ['DROPBOX_ACCESS_TOKEN', 'DROPBOX_REFRESH_TOKEN', 'DROPBOX_APP_SECRET']:
        if not value:
            raise ValueError(f"Required secure environment variable {key} is not set")
        
        # Check for suspicious patterns (allow shorter values for some vars)
        min_length = 5 if key == 'DROPBOX_APP_SECRET' else 10
        if len(value) < min_length:
            raise ValueError(f"Environment variable {key} appears to be too short")
        
        # Don't log or expose sensitive values
        return value
    
    return value


def validate_dropbox_config() -> dict:
    """Validate all required Dropbox configuration is present and secure"""
    # Ensure .env is loaded
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = [
        'DROPBOX_APP_KEY',
        'DROPBOX_APP_SECRET', 
        'DROPBOX_REFRESH_TOKEN',
        'DROPBOX_TEAM_MEMBER_ID',
        'DROPBOX_NAMESPACE_ID'
    ]
    
    config = {}
    missing = []
    
    for var in required_vars:
        # Use regular os.getenv for most vars, secure_getenv only for sensitive ones
        if var in ['DROPBOX_APP_SECRET', 'DROPBOX_REFRESH_TOKEN']:
            try:
                value = secure_getenv(var)
                if value:
                    config[var] = value
                else:
                    missing.append(var)
            except ValueError as e:
                missing.append(f"{var} (invalid)")
        else:
            # For non-sensitive vars, just check they exist
            value = os.getenv(var)
            if value:
                config[var] = value
            else:
                missing.append(var)
    
    if missing:
        raise ValueError(f"Missing or invalid Dropbox configuration: {', '.join(missing)}")
    
    return config
