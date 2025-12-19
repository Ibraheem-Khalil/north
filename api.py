"""
NORTH API Server
FastAPI backend for the NORTH chatbot web interface
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import asyncio
import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Security, File, UploadFile, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Add src to path
sys.path.append(str(Path(__file__).parent))

# Import NORTH
from src.core.north_orchestrator import NORTH
from src.core.file_processor import FileProcessor

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
north_instance = None
supabase_client = None
MAX_USER_CONTEXTS = 200  # prevent unbounded growth
MAX_UPLOAD_FILES = 5
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

# Per-user context storage (prevents context leakage between users)
# Key: user_id (str), Value: ContextManager instance
user_contexts = {}

# Import lifespan manager
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting NORTH API Server...")
    
    # Pre-initialize NORTH
    try:
        get_north()
        logger.info("NORTH initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize NORTH: {e}")
    
    # Test Supabase connection
    if get_supabase():
        logger.info("Supabase connected")
    else:
        logger.info("Running without Supabase")
    
    yield
    
    # Shutdown
    logger.info("Shutting down NORTH API Server...")
    
    # Cleanup NORTH
    global north_instance
    if north_instance:
        try:
            north_instance.cleanup()
        except Exception as e:
            logger.warning(f"Error during NORTH cleanup: {e}", exc_info=True)

# Initialize FastAPI with lifespan
app = FastAPI(
    title="NORTH AI API",
    description="API backend for NORTH AI Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# App configuration
APP_URL = os.getenv("APP_URL", "https://example-ai.com")
if os.getenv("ENVIRONMENT", "production") == "development":
    APP_URL = os.getenv("APP_URL", "http://localhost:3000")

# CORS configuration (env-driven)
def get_allowed_origins() -> List[str]:
    env = os.getenv("ENVIRONMENT", "production").lower()
    # Preferred: comma-separated ALLOWED_ORIGINS
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    # Fallbacks for convenience
    app_url = os.getenv("APP_URL")
    if app_url:
        origins.append(app_url.rstrip("/"))

    # Local dev defaults
    if env == "development":
        origins.extend([
            "http://localhost:3000",
            "http://localhost:5173",
        ])

    # Deduplicate
    return sorted(set(origins))

origins = get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

def get_north():
    """Get or create NORTH instance (singleton)"""
    global north_instance
    if north_instance is None:
        try:
            north_instance = NORTH()
            logger.info("NORTH instance initialized")
        except Exception as e:
            logger.error(f"Failed to initialize NORTH: {e}")
            raise
    return north_instance

def get_supabase():
    """
    Get Supabase client for server-side database operations.

    Uses service role key for trusted backend operations since this is a private
    backend API (not publicly exposed). User authentication is enforced at the
    API endpoint level via JWT validation.

    Architecture note: RLS policies are defined in Supabase but enforcement
    happens via application-layer authentication on API endpoints.
    """
    global supabase_client
    if supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if url and key:
            try:
                from supabase import create_client
                supabase_client = create_client(url, key)
                logger.info("Supabase client initialized with service role")
            except Exception as e:
                logger.warning(f"Supabase init failed: {e}")
    return supabase_client

def get_user_context(user_id: str):
    """
    Get or create a ContextManager for a specific user.
    Prevents context leakage between users by isolating conversation history.

    Args:
        user_id: Unique user identifier (typically from JWT sub claim)

    Returns:
        ContextManager instance for this user
    """
    from src.core.context_manager import ContextManager

    global user_contexts

    # Simple LRU-ish cap to avoid unbounded growth
    if len(user_contexts) >= MAX_USER_CONTEXTS and user_id not in user_contexts:
        # Drop oldest inserted context
        oldest_key = next(iter(user_contexts.keys()))
        user_contexts.pop(oldest_key, None)

    if user_id not in user_contexts:
        user_contexts[user_id] = ContextManager(history_size=4)
        logger.info(f"Created new context for user: {user_id}")

    return user_contexts[user_id]

# --- Request/Response Models ---

class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

class SystemStatus(BaseModel):
    status: str
    agents: List[str]
    weaviate_connected: bool
    supabase_connected: bool
    version: str = "1.0.0"

class SignUpRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

class SignInRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    user: Dict[str, Any]

# --- Import auth handler ---
from src.api.auth import auth_handler

# Security scheme for JWT Bearer tokens
security = HTTPBearer(auto_error=False)

# --- API Routes ---

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "NORTH AI API",
        "status": "online",
        "version": "1.0.0",
        "docs": "/docs"
    }

# --- Authentication Routes ---

@app.post("/api/auth/check-email")
async def check_email_authorization(email: str):
    """Check if an email is authorized to sign up"""
    whitelist_path = Path(__file__).parent / "config" / "authorized_users.json"
    try:
        with open(whitelist_path, 'r') as f:
            whitelist_config = json.load(f)
    except FileNotFoundError:
        return {"authorized": False, "message": "Server configuration error"}
    
    email_lower = email.lower()
    authorized_emails = [e.lower() for e in whitelist_config["authorized_emails"]]
    
    if email_lower in authorized_emails:
        return {"authorized": True}
    else:
        return {
            "authorized": False, 
            "message": whitelist_config.get("whitelist_message", "Access restricted")
        }

@app.post("/api/auth/signup", response_model=AuthResponse)
async def sign_up(request: SignUpRequest):
    """Create a new user account - restricted to whitelist"""
    # Load authorized users whitelist
    whitelist_path = Path(__file__).parent / "config" / "authorized_users.json"
    try:
        with open(whitelist_path, 'r') as f:
            whitelist_config = json.load(f)
    except FileNotFoundError:
        logger.error("Authorized users config not found")
        raise HTTPException(status_code=500, detail="Server configuration error")
    
    # Check if email is authorized (case-insensitive)
    email_lower = request.email.lower()
    authorized_emails = [email.lower() for email in whitelist_config["authorized_emails"]]
    
    if email_lower not in authorized_emails:
        logger.warning(f"Unauthorized signup attempt from: {request.email}")
        raise HTTPException(
            status_code=403, 
            detail=whitelist_config.get("whitelist_message", "Access restricted to authorized personnel only")
        )
    
    # Proceed with signup if authorized
    try:
        result = await auth_handler.sign_up(
            email=request.email,
            password=request.password,
            full_name=request.full_name
        )
        
        logger.info(f"Authorized user signed up: {request.email}")
        
        # Check if session exists (might be None if email verification is required)
        if result.get("session") and result["session"]:
            return AuthResponse(
                access_token=result["session"].access_token,
                refresh_token=result["session"].refresh_token,
                user={
                    "id": result["user"].id,
                    "email": result["user"].email
                }
            )
        else:
            # No session means email verification is required
            return AuthResponse(
                access_token="",  # Empty token indicates verification needed
                refresh_token="",
                user={
                    "id": result["user"].id if result.get("user") else "",
                    "email": result["user"].email if result.get("user") else request.email,
                    "message": "Please check your email to verify your account"
                }
            )
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/signin", response_model=AuthResponse)
async def sign_in(request: SignInRequest):
    """Sign in with email and password"""
    try:
        result = await auth_handler.sign_in(
            email=request.email,
            password=request.password
        )
        
        return AuthResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            user=result["user"]
        )
    except Exception as e:
        logger.error(f"Signin error: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/auth/signout")
async def sign_out(user: Dict = Depends(auth_handler.get_current_user)):
    """Sign out current user"""
    if user:
        await auth_handler.sign_out("")
    return {"message": "Signed out successfully"}

class PasswordResetRequest(BaseModel):
    email: str

class UpdatePasswordRequest(BaseModel):
    password: str

@app.post("/api/auth/reset-password")
async def reset_password(request: PasswordResetRequest):
    """Send password reset email"""
    try:
        result = await auth_handler.reset_password(request.email)
        return result
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        # Always return success for security (don't reveal if email exists)
        return {"success": True, "message": "If an account exists with this email, a password reset link has been sent."}

@app.post("/api/auth/update-password")
async def update_password(
    request: UpdatePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """Update password with recovery token"""
    if not credentials:
        raise HTTPException(status_code=401, detail="No access token provided")
    
    try:
        result = await auth_handler.update_password(
            access_token=credentials.credentials,
            new_password=request.password
        )
        return result
    except Exception as e:
        logger.error(f"Password update error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/me")
async def get_current_user(user: Dict = Depends(auth_handler.require_auth)):
    """Get current user information"""
    # Also get user preferences
    supabase = get_supabase()
    if supabase and user:
        try:
            prefs_result = supabase.table("user_preferences")\
                .select("*")\
                .eq("user_id", user["id"])\
                .execute()
            
            if prefs_result.data and len(prefs_result.data) > 0:
                preferences = prefs_result.data[0].get("preferences", {})
                user["preferred_name"] = preferences.get("preferred_name")
        except Exception as e:
            logger.warning(f"Failed to fetch user preferences: {e}")
    
    return {"user": user}

@app.get("/api/user/preferences")
async def get_user_preferences(user: Dict = Depends(auth_handler.require_auth)):
    """Get user preferences"""
    supabase = get_supabase()
    if not supabase:
        return {"preferences": {}}
    
    try:
        result = supabase.table("user_preferences")\
            .select("*")\
            .eq("user_id", user["id"])\
            .execute()
        
        if result.data and len(result.data) > 0:
            return {"preferences": result.data[0].get("preferences", {})}
        return {"preferences": {}}
    except Exception as e:
        logger.error(f"Failed to fetch preferences: {e}")
        return {"preferences": {}}

@app.post("/api/user/preferences")
async def update_user_preferences(
    preferences: Dict[str, Any],
    user: Dict = Depends(auth_handler.require_auth)
):
    """Update user preferences"""
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured")
    
    try:
        # Check if preferences exist
        existing = supabase.table("user_preferences")\
            .select("*")\
            .eq("user_id", user["id"])\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            # Update existing
            result = supabase.table("user_preferences")\
                .update({"preferences": preferences})\
                .eq("user_id", user["id"])\
                .execute()
        else:
            # Create new
            result = supabase.table("user_preferences")\
                .insert({
                    "user_id": user["id"],
                    "preferences": preferences
                })\
                .execute()
        
        return {"success": True, "preferences": preferences}
    except Exception as e:
        logger.error(f"Failed to update preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    """System status check"""
    try:
        north = get_north()
        supabase = get_supabase()
        
        return SystemStatus(
            status="online",
            agents=list(north.agents.keys()) if north.agents else [],
            weaviate_connected=north._test_weaviate_connection(),
            supabase_connected=(supabase is not None)
        )
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return SystemStatus(
            status="error",
            agents=[],
            weaviate_connected=False,
            supabase_connected=False
        )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    message: ChatMessage,
    current_user: Dict = Depends(auth_handler.require_auth)
):
    """Main chat endpoint (authentication required)"""
    try:
        north = get_north()

        # Get user-specific context (prevents context leakage between users)
        user_id = current_user["id"]
        user_context = get_user_context(user_id)

        # Process the message with user-specific context without blocking the event loop
        response = await asyncio.to_thread(
            north.process_query, message.message, user_context
        )

        # Generate conversation ID if needed
        conv_id = message.conversation_id or f"conv_{int(datetime.now().timestamp())}"

        # Store in Supabase if authenticated
        supabase = get_supabase()
        if supabase:
            try:
                # Use authenticated user ID
                user_id = current_user["id"]

                # Store conversation
                supabase.table("conversations").insert({
                    "user_id": user_id,
                    "conversation_id": conv_id,
                    "message": message.message,
                    "response": response,
                    "created_at": datetime.now().isoformat()
                }).execute()
                
                logger.info(f"Conversation stored for user {current_user['email']}")
            except Exception as e:
                logger.warning(f"Failed to store conversation: {e}")
        
        return ChatResponse(
            response=response,
            conversation_id=conv_id,
            timestamp=datetime.now().isoformat(),
            metadata={
                "agents_used": list(north.agents.keys()) if north.agents else []
            }
        )
        
    except Exception as e:
        logger.error(f"Chat processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/with-files", response_model=ChatResponse)
async def chat_with_files(
    message: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    current_user: Dict = Depends(auth_handler.require_auth)
):
    """Chat endpoint with file attachment support (authentication required)"""
    try:
        north = get_north()

        # Get user-specific context (prevents context leakage between users)
        user_id = current_user["id"]
        user_context = get_user_context(user_id)

        # Process attached files
        processed_files = []
        if files:
            if len(files) > MAX_UPLOAD_FILES:
                raise HTTPException(status_code=400, detail=f"Too many files (max {MAX_UPLOAD_FILES})")
            for file in files:
                # Read file content
                content = await file.read()

                if len(content) > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{file.filename} is too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)"
                    )

                # Process the file
                processed = FileProcessor.process_file(
                    content,
                    file.filename,
                    file.content_type
                )
                processed_files.append(processed)

                logger.info(f"Processed file: {file.filename} ({file.content_type})")

        # Process the message with files and user-specific context
        if processed_files:
            response = await asyncio.to_thread(
                north.process_query_with_files, message, processed_files, user_context
            )
        else:
            response = await asyncio.to_thread(
                north.process_query, message, user_context
            )
        
        # Generate conversation ID if needed
        conv_id = conversation_id or f"conv_{int(datetime.now().timestamp())}"
        
        # Store in Supabase if authenticated
        supabase = get_supabase()
        if supabase:
            try:
                # Store conversation with file metadata
                conversation_data = {
                    "user_id": current_user["id"],
                    "conversation_id": conv_id,
                    "message": message,
                    "response": response,
                    "created_at": datetime.now().isoformat()
                }
                
                # Add file metadata if present
                if processed_files:
                    conversation_data["metadata"] = {
                        "files": [
                            {
                                "filename": f.get("filename"),
                                "type": f.get("type"),
                                "mime_type": f.get("mime_type"),
                                "size": f.get("size")
                            }
                            for f in processed_files
                        ]
                    }
                
                supabase.table("conversations").insert(conversation_data).execute()
                logger.info(f"Conversation with {len(processed_files)} files stored")
                
            except Exception as e:
                logger.warning(f"Failed to store conversation: {e}")
        
        return ChatResponse(
            response=response,
            conversation_id=conv_id,
            timestamp=datetime.now().isoformat(),
            metadata={
                "agents_used": list(north.agents.keys()) if north.agents else [],
                "files_processed": len(processed_files)
            }
        )
        
    except Exception as e:
        logger.error(f"Chat with files processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/stream")
async def chat_stream(
    message: ChatMessage,
    current_user: Dict = Depends(auth_handler.require_auth),
):
    """Streaming chat endpoint (simulated word-chunk streaming for demos; authentication required)"""
    user_id = current_user["id"]
    user_context = get_user_context(user_id)

    async def generate():
        try:
            north = get_north()
            
            # Process query
            response = await asyncio.to_thread(
                north.process_query, message.message, user_context
            )
            
            # Stream response in chunks
            words = response.split()
            buffer = []
            
            for i, word in enumerate(words):
                buffer.append(word)
                
                # Send every 3 words or on punctuation
                if len(buffer) >= 3 or word.endswith(('.', '!', '?', ':')):
                    chunk = ' '.join(buffer)
                    yield f"data: {json.dumps({'text': chunk + ' '})}\n\n"
                    buffer = []
                    await asyncio.sleep(0.05)
            
            # Send remaining words
            if buffer:
                yield f"data: {json.dumps({'text': ' '.join(buffer)})}\n\n"
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket endpoint for real-time chat with progress updates.

    Authentication:
    - In production, expects 'token' query parameter with valid JWT
    - For local dev, set DISABLE_AUTH_VERIFICATION=true to bypass

    Example: ws://localhost:8000/ws/chat?token=your_jwt_token
    """
    # Check if authentication is required (always required outside development)
    is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"
    disable_auth_flag = os.getenv("DISABLE_AUTH_VERIFICATION", "false").lower() == "true"
    require_auth = (not is_dev) or (not disable_auth_flag)

    if require_auth:
        if not token:
            logger.warning("WebSocket connection rejected: missing token")
            await websocket.close(code=1008, reason="Authentication required")
            return

        # Validate token
        try:
            payload = auth_handler.verify_token(token)
            user_id = payload.get("sub")
            logger.info(f"WebSocket authenticated for user: {user_id}")
        except HTTPException as e:
            logger.warning(f"WebSocket auth failed: {e.detail}")
            await websocket.close(code=1008, reason="Invalid token")
            return
    else:
        logger.info("WebSocket connected (auth disabled for local dev)")
        user_id = None

    await websocket.accept()
    north = get_north()

    # Get user-specific context (prevents context leakage between users)
    user_context = get_user_context(user_id) if user_id else None

    async def send_progress(stage: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        try:
            payload: Dict[str, Any] = {
                "type": "search_progress",
                "stage": stage,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
            if details is not None:
                payload["details"] = details
            await websocket.send_json(payload)
        except Exception:
            # Progress updates should never take down the chat loop.
            return

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")

            if not message:
                continue

            await send_progress("thinking", "Thinking...")
            await send_progress("processing", "Generating response...")

            # Process through NORTH with user-specific context
            response = await asyncio.to_thread(
                north.process_query, message, user_context
            )

            await send_progress("complete", "Done")

            # Send final response
            await websocket.send_json({
                "type": "response",
                "text": response,
                "timestamp": datetime.now().isoformat()
            })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "WebSocket error",
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass
        await websocket.close()

@app.get("/api/conversations/{user_id}")
async def get_conversations(
    user_id: str,
    limit: int = 50,
    current_user: Dict = Depends(auth_handler.require_auth)
):
    """Get user's conversation history (auth required; user must match token)"""
    if not current_user or current_user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    supabase = get_supabase()
    if not supabase:
        return {"conversations": [], "message": "Database not configured"}
    
    try:
        result = supabase.table("conversations")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        return {"conversations": result.data}
    except Exception as e:
        logger.error(f"Failed to fetch conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/{user_id}/{conversation_id}")
async def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    current_user: Dict = Depends(auth_handler.require_auth)
):
    """Get all messages for a specific conversation (auth required; user must match token)"""
    if not current_user or current_user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    supabase = get_supabase()
    if not supabase:
        return {"conversations": [], "message": "Database not configured"}
    
    try:
        result = supabase.table("conversations")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("conversation_id", conversation_id)\
            .order("created_at")\
            .execute()
        
        return {"conversations": result.data}
    except Exception as e:
        logger.error(f"Failed to fetch conversation messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/conversations/{user_id}/{conversation_id}")
async def delete_conversation(
    user_id: str, 
    conversation_id: str,
    current_user: Dict = Depends(auth_handler.get_current_user)
):
    """Delete all messages in a conversation"""
    # Verify the user owns this conversation
    if not current_user or current_user["id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    supabase = get_supabase()
    if not supabase:
        return {"success": False, "message": "Database not configured"}
    
    try:
        # Delete all messages with this conversation_id
        result = supabase.table("conversations")\
            .delete()\
            .eq("user_id", user_id)\
            .eq("conversation_id", conversation_id)\
            .execute()
        
        return {"success": True, "deleted_count": len(result.data)}
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clear-context")
async def clear_context(current_user: Optional[Dict] = Depends(auth_handler.get_current_user)):
    """
    Clear NORTH's conversation context.

    This endpoint clears the conversation history maintained by NORTH.
    Requires authentication when DISABLE_AUTH_VERIFICATION is false (production mode).
    """
    # Enforce authentication unless explicitly disabled for local dev.
    # Guardrail: never allow auth bypass outside development.
    environment = os.getenv("ENVIRONMENT", "production").lower()
    disable_auth_flag = os.getenv("DISABLE_AUTH_VERIFICATION", "false").lower() == "true"
    if disable_auth_flag and environment != "development":
        logger.error("DISABLE_AUTH_VERIFICATION is true outside development; refusing request")
        raise HTTPException(
            status_code=500,
            detail="Authentication misconfigured: verification disabled outside development",
        )

    require_auth = not disable_auth_flag

    if require_auth and not current_user:
        logger.warning("Unauthorized attempt to clear context")
        raise HTTPException(
            status_code=401,
            detail="Authentication required to clear context"
        )

    # Log who is clearing context for audit trail
    if current_user:
        user_id = current_user.get('id')
        logger.info(f"Context cleared by user: {current_user.get('email', 'unknown')}")
    else:
        user_id = None
        logger.warning("Context cleared by unauthenticated request (local dev mode only)")

    try:
        # Clear user-specific context (prevents clearing other users' context)
        if user_id:
            user_context = get_user_context(user_id)
            user_context.clear()
            logger.info(f"Cleared context for user: {user_id}")
        else:
            # In local dev mode without auth, clear the default context
            north = get_north()
            north.context_manager.clear()
            logger.info("Cleared default context (local dev mode)")

        return {"status": "success", "message": "Context cleared"}
    except Exception as e:
        logger.error(f"Failed to clear context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# --- Main ---

if __name__ == "__main__":
    import uvicorn
    
    # Parse any command line args
    import argparse
    parser = argparse.ArgumentParser(description="NORTH API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    # Start server
    logger.info(f"Starting NORTH API on http://{args.host}:{args.port}")
    logger.info(f"API documentation: http://localhost:{args.port}/docs")
    
    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
