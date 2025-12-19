"""
Authentication utilities for NORTH API
Handles Supabase JWT verification and user management
"""

import os
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import jwt
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Security scheme for JWT Bearer tokens
security = HTTPBearer(auto_error=False)

# Supabase client
def get_supabase_client() -> Optional[Client]:
    """
    Get Supabase client for authentication operations.

    Uses service role key to perform administrative auth operations
    (user creation, password resets, etc.) on the backend.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        logger.warning("Supabase not configured (SUPABASE_URL/SUPABASE_*_KEY missing)")
        return None
    return create_client(url, key)

class AuthHandler:
    """Handle authentication and authorization"""
    
    def __init__(self):
        self.supabase: Optional[Client] = get_supabase_client()
        self.jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")

    def _require_supabase(self) -> Client:
        """Return Supabase client or raise a configuration error."""
        if not self.supabase:
            raise HTTPException(status_code=500, detail="Supabase not configured")
        return self.supabase
        
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify Supabase JWT token with proper signature validation.

        In production, this validates tokens against the SUPABASE_JWT_SECRET.
        For local development without Supabase, set DISABLE_AUTH_VERIFICATION=true
        in your .env file (not recommended for production).
        """
        try:
            # Check if we should bypass verification (local dev only)
            disable_verification = os.getenv("DISABLE_AUTH_VERIFICATION", "false").lower() == "true"
            environment = os.getenv("ENVIRONMENT", "production").lower()

            # Guardrail: never allow verification to be disabled outside development
            if disable_verification and environment != "development":
                logger.error("JWT verification disabled outside development; refusing request")
                raise HTTPException(
                    status_code=500,
                    detail="Authentication misconfigured: verification disabled outside development"
                )

            if disable_verification:
                logger.warning("JWT signature verification is DISABLED - only use for local development")
                payload = jwt.decode(token, options={"verify_signature": False})
            elif self.jwt_secret:
                # Production: Verify with Supabase JWT secret
                payload = jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_signature": True}
                )
            else:
                # No secret configured - fail securely
                logger.error("SUPABASE_JWT_SECRET not configured and verification not disabled")
                raise HTTPException(
                    status_code=500,
                    detail="Authentication service not properly configured"
                )

            return payload
        except jwt.ExpiredSignatureError:
            # Must be caught before InvalidTokenError (it's a subclass)
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
    
    def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[Dict]:
        """Get current user from JWT token"""
        if not credentials:
            return None  # Allow anonymous access for some endpoints
        
        try:
            token = credentials.credentials
            payload = self.verify_token(token)
            
            # Extract user info
            user = {
                "id": payload.get("sub"),  # User ID from Supabase
                "email": payload.get("email"),
                "role": payload.get("role", "authenticated")
            }
            
            return user
        except HTTPException as e:
            # Don't hide server-side misconfiguration as "anonymous user"
            if e.status_code >= 500:
                raise
            logger.warning(f"Auth rejected: {e.detail}")
            return None
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return None
    
    def require_auth(self, credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
        """Require authentication - raises exception if not authenticated"""
        if not credentials:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user = self.get_current_user(credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        return user
    
    async def sign_up(self, email: str, password: str, full_name: str = None) -> Dict:
        """Sign up a new user"""
        try:
            supabase = self._require_supabase()
            # Determine the redirect URL based on environment
            # Can be overridden with APP_URL environment variable
            redirect_url = os.getenv("APP_URL", "https://example-ai.com")
            if os.getenv("ENVIRONMENT", "production") == "development" and not os.getenv("APP_URL"):
                redirect_url = "http://localhost:3000"
            
            logger.info(f"Using redirect URL for email verification: {redirect_url}")
            
            # Create user in Supabase Auth
            response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "email_redirect_to": redirect_url,
                    "data": {
                        "full_name": full_name or email.split('@')[0]
                    }
                }
            })
            
            # Check if we got a valid response
            if not response:
                raise HTTPException(status_code=400, detail="No response from authentication service")
            
            # Return the response even if session is None (email verification might be required)
            return {
                "user": response.user if hasattr(response, 'user') else None,
                "session": response.session if hasattr(response, 'session') else None
            }
                
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.error(f"Signup error: {e}")
            # Provide more helpful error messages
            error_msg = str(e)
            if "already registered" in error_msg.lower():
                raise HTTPException(status_code=400, detail="This email is already registered")
            elif "invalid" in error_msg.lower() and "email" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Please provide a valid email address")
            elif "weak" in error_msg.lower() and "password" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Password is too weak. Please use at least 6 characters")
            else:
                raise HTTPException(status_code=400, detail=f"Signup failed: {error_msg}")
    
    async def sign_in(self, email: str, password: str) -> Dict:
        """Sign in an existing user"""
        try:
            supabase = self._require_supabase()
            logger.info(f"Attempting signin for: {email}")
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user and response.session:
                logger.info(f"Signin successful for: {email}")
                return {
                    "user": {
                        "id": response.user.id,
                        "email": response.user.email
                    },
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token
                }
            else:
                logger.error(f"No user/session returned for: {email}")
                raise HTTPException(status_code=401, detail="Invalid credentials")
                
        except Exception as e:
            logger.error(f"Signin error for {email}: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
    
    async def sign_out(self, token: str) -> bool:
        """Sign out user"""
        try:
            supabase = self._require_supabase()
            supabase.auth.sign_out()
            return True
        except Exception as e:
            logger.error(f"Signout error: {e}")
            return False
    
    async def reset_password(self, email: str) -> Dict:
        """Send password reset email"""
        try:
            supabase = self._require_supabase()
            # Determine the redirect URL for password reset
            redirect_url = os.getenv("APP_URL", "https://example-ai.com")
            if os.getenv("ENVIRONMENT", "production") == "development" and not os.getenv("APP_URL"):
                redirect_url = "http://localhost:3000"
            
            # Add reset path to redirect URL
            redirect_url = f"{redirect_url}/reset-password"
            
            logger.info(f"Sending password reset to {email} with redirect to {redirect_url}")
            
            # Send password reset email
            response = supabase.auth.reset_password_email(
                email,
                {"redirect_to": redirect_url}
            )
            
            return {
                "success": True,
                "message": "Password reset email sent. Please check your inbox."
            }
        except Exception as e:
            logger.error(f"Password reset error for {email}: {str(e)}")
            # Check if user exists
            if "not found" in str(e).lower() or "no user" in str(e).lower():
                # Don't reveal if user exists for security
                return {
                    "success": True,
                    "message": "If an account exists with this email, a password reset link has been sent."
                }
            raise HTTPException(status_code=400, detail="Failed to send reset email")
    
    async def update_password(self, access_token: str, new_password: str) -> Dict:
        """Update user password with recovery token"""
        try:
            supabase = self._require_supabase()
            # Set the session with the recovery token first
            supabase.auth.set_session(access_token, "")
            
            # Now update the password
            response = supabase.auth.update_user(
                {"password": new_password}
            )
            
            if response and response.user:
                logger.info(f"Password updated for user: {response.user.email}")
                return {
                    "success": True,
                    "message": "Password updated successfully"
                }
            else:
                raise HTTPException(status_code=400, detail="Failed to update password")
                
        except Exception as e:
            logger.error(f"Password update error: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to update password: {str(e)}")
    
    async def get_session(self, token: str) -> Optional[Dict]:
        """Get current session from token"""
        try:
            supabase = self._require_supabase()
            # Set the session in Supabase client
            supabase.auth.set_session(token, "")
            session = supabase.auth.get_session()
            
            if session:
                return {
                    "user": session.user,
                    "expires_at": session.expires_at
                }
            return None
        except Exception as e:
            logger.error(f"Session error: {e}")
            return None

# Create singleton instance
auth_handler = AuthHandler()
