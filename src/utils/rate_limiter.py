"""
Rate limiting utilities for API calls
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Optional


class RateLimiter:
    """Thread-safe rate limiter using token bucket algorithm"""
    
    def __init__(self, max_calls: int = 100, time_window: int = 60):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum number of calls allowed
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self._calls: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
    
    def is_allowed(self, identifier: str = "default") -> bool:
        """
        Check if a call is allowed for the given identifier
        
        Args:
            identifier: Unique identifier for the rate limit bucket
            
        Returns:
            True if call is allowed, False otherwise
        """
        with self._lock:
            now = time.time()
            calls = self._calls[identifier]
            
            # Remove old calls outside the time window
            while calls and calls[0] <= now - self.time_window:
                calls.popleft()
            
            # Check if we're under the limit
            if len(calls) < self.max_calls:
                calls.append(now)
                return True
            
            return False
    
    def wait_if_needed(self, identifier: str = "default") -> None:
        """
        Block until a call is allowed
        
        Args:
            identifier: Unique identifier for the rate limit bucket
        """
        while not self.is_allowed(identifier):
            time.sleep(0.1)  # Wait 100ms before retrying
    
    def get_wait_time(self, identifier: str = "default") -> float:
        """
        Get the time to wait before the next call is allowed
        
        Args:
            identifier: Unique identifier for the rate limit bucket
            
        Returns:
            Time to wait in seconds, 0 if call is immediately allowed
        """
        with self._lock:
            now = time.time()
            calls = self._calls[identifier]
            
            # Remove old calls outside the time window
            while calls and calls[0] <= now - self.time_window:
                calls.popleft()
            
            if len(calls) < self.max_calls:
                return 0
            
            # Return time until the oldest call expires
            return max(0, calls[0] + self.time_window - now)


# Global rate limiters for different services
_dropbox_limiter = RateLimiter(max_calls=1000, time_window=3600)  # 1000 calls per hour
_general_limiter = RateLimiter(max_calls=100, time_window=60)     # 100 calls per minute


def get_dropbox_rate_limiter() -> RateLimiter:
    """Get the Dropbox API rate limiter"""
    return _dropbox_limiter


def get_general_rate_limiter() -> RateLimiter:
    """Get the general purpose rate limiter"""
    return _general_limiter


def rate_limited_request(func, identifier: str = "default", limiter: Optional[RateLimiter] = None):
    """
    Decorator for rate limiting API requests
    
    Args:
        func: Function to rate limit
        identifier: Rate limit bucket identifier
        limiter: Custom rate limiter, uses general limiter if None
    """
    if limiter is None:
        limiter = get_general_rate_limiter()
    
    def wrapper(*args, **kwargs):
        limiter.wait_if_needed(identifier)
        return func(*args, **kwargs)
    
    return wrapper