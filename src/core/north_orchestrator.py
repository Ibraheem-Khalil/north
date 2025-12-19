"""
NORTH Orchestrator - Main AI system orchestration logic
"""

import os
import logging
import time
from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import Tool

# LangChain agent APIs moved in recent releases; fall back gracefully.
try:
    from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore
except ImportError:
    AgentExecutor = None
    create_tool_calling_agent = None

# Import context manager for conversational continuity
from src.core.context_manager import ContextManager
# Import file processor for multimodal support
from src.core.file_processor import FileProcessor

logger = logging.getLogger(__name__)


class NORTH:
    """Main orchestrator for NORTH AI system - unified conversational AI"""
    
    def __init__(self):
        self._cleanup_called = False
        logger.info("Initializing NORTH AI System...")
        
        # Validate environment variables
        if not self._validate_environment():
            logger.error("Environment validation failed. Please check your .env file.")
            raise RuntimeError("Missing required environment variables")
            
        self.agents: Dict[str, Any] = {}
        self._initialize_agents()
        
        # Initialize context manager for conversational continuity
        self.context_manager = ContextManager(history_size=4)
        logger.info("Context manager initialized for conversational continuity")
        
        # Initialize NORTH's main LLM - she IS the assistant, not a router
        self.llm = ChatOpenAI(
            model="gpt-4o",  # GPT-4o for best context understanding
            temperature=0.7,  # Natural conversation
            timeout=30
        )
        
        # Create tools from available agents
        self.tools = self._create_tools()
        
        # NORTH's personality and capabilities
        # Store as instance variable for reuse in multimodal queries
        self.system_prompt = """You are NORTH, an intelligent AI assistant for Example Construction Co. - a construction and real estate company specializing in residential and commercial projects.

Your personality: Professional yet friendly, knowledgeable about construction, and always helpful. You understand the construction industry's terminology and challenges.

Your capabilities:
- Access to company knowledge base (contractors, projects, contact info) via search_knowledge_base
- Access to documents (contracts, invoices, insurance, W9s) via search_dropbox_files
- Process and analyze images, PDFs, spreadsheets, and other files shared in conversation
- Maintain context across conversations for seamless interactions

Available tools:
{tools}

INTERACTION APPROACH:
1. Understand the user's intent - they might ask about contractors, documents, projects, or need general help
2. If information is in the knowledge base or documents, use the appropriate tool
3. For attached files (images, PDFs, etc.), analyze them directly and provide insights
4. Combine information from multiple sources when helpful
5. Be conversational and helpful, not just a data retriever

GUIDELINES:
- Respond naturally and conversationally
- When users share construction photos, invoices, or documents, analyze them thoroughly
- Proactively suggest relevant contractors or documents based on context
- If something isn't in the database, acknowledge it gracefully and offer alternatives
- Remember you're helping busy construction professionals - be clear and actionable

Common scenarios you handle:
- "Who did the concrete work on Regency?" → Search knowledge base
- "Find the contract with ABC Electric" → Search Dropbox documents
- "Look at this damage photo" → Analyze image and suggest relevant contractors
- "What's the total on this invoice?" → Process PDF/image and extract information

You are the primary interface for Example Construction Co.'s information systems - be helpful, accurate, and efficient."""

        # Create the prompt template with proper message handling
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Create the agent if we have tools
        if self.tools and AgentExecutor and create_tool_calling_agent:
            # Use create_tool_calling_agent for compatibility with both OpenAI and Anthropic
            self.agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
            self.agent_executor = AgentExecutor(
                agent=self.agent,
                tools=self.tools,
                verbose=False,  # Set to False for cleaner output
                max_iterations=3,
                handle_parsing_errors=True
            )
            logger.info(f"NORTH initialized with {len(self.tools)} tools")
        else:
            self.agent_executor = None
            logger.warning("NORTH initialized without tools - limited capabilities")
        
    def _validate_environment(self) -> bool:
        """Validate required environment variables"""
        required_vars = ['OPENAI_API_KEY']
        optional_vars = ['OBSIDIAN_VAULT_PATH', 'WEAVIATE_API_KEY', 'WEAVIATE_URL']
        
        missing_required = []
        for var in required_vars:
            if not os.getenv(var):
                missing_required.append(var)
                
        if missing_required:
            logger.error(f"Missing required environment variables: {', '.join(missing_required)}")
            return False
            
        # Log optional variables that are missing
        for var in optional_vars:
            if not os.getenv(var):
                if var == 'WEAVIATE_URL':
                    logger.info(f"WEAVIATE_URL not set, using default: http://localhost:8080")
                else:
                    logger.warning(f"Optional environment variable not set: {var}")
                
        return True

    def _get_north_prompt(self) -> str:
        """
        Get NORTH's system prompt for multimodal queries.

        Returns a simplified version without tool placeholders since
        multimodal queries bypass the agent executor.
        """
        # Remove the {tools} placeholder for direct LLM invocation
        prompt = self.system_prompt.replace("{tools}", "search_knowledge_base, search_dropbox_files")
        return prompt

    def _test_weaviate_connection(self) -> bool:
        """Test if Weaviate is accessible"""
        try:
            import weaviate
            import requests
            
            weaviate_url = os.getenv('WEAVIATE_URL', 'http://localhost:8080')
            
            # Add API key to headers if available
            headers = {}
            api_key = os.getenv('WEAVIATE_API_KEY')
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            
            # Add Cloudflare Access headers if using HTTPS
            if weaviate_url.startswith('https://'):
                cf_client_id = os.getenv('CF_ACCESS_CLIENT_ID')
                cf_client_secret = os.getenv('CF_ACCESS_CLIENT_SECRET')
                if cf_client_id and cf_client_secret:
                    headers['CF-Access-Client-Id'] = cf_client_id
                    headers['CF-Access-Client-Secret'] = cf_client_secret
                    logger.info("Using Cloudflare Access credentials for connection test")
            
            # First try a simple HTTP request
            response = requests.get(
                f"{weaviate_url}/v1/.well-known/ready",
                timeout=10,
                headers=headers
            )
            if response.status_code != 200:
                logger.error(f"Weaviate not ready. Status: {response.status_code}")
                return False
                
            # Try to create a client connection (v4 API)
            try:
                if weaviate_url.startswith('https://') and api_key:
                    # Weaviate Cloud connection
                    import weaviate.auth as wvauth
                    
                    # Add Voyage API key to headers if available
                    headers_dict = {}
                    voyage_key = os.getenv('VOYAGE_API_KEY')
                    if voyage_key:
                        headers_dict['X-VoyageAI-Api-Key'] = voyage_key
                    
                    client = weaviate.connect_to_weaviate_cloud(
                        cluster_url=weaviate_url,
                        auth_credentials=wvauth.AuthApiKey(api_key),
                        headers=headers_dict if headers_dict else None
                    )
                else:
                    # Local connection (Docker)
                    from urllib.parse import urlparse
                    parsed = urlparse(weaviate_url)
                    host = parsed.hostname or 'localhost'
                    port = parsed.port or 8080
                    
                    client = weaviate.connect_to_local(
                        host=host,
                        port=port,
                        grpc_port=50051
                    )
                
                # Test the connection
                client.collections.list_all()
                client.close()
            except Exception as e:
                logger.error(f"Weaviate v4 connection failed: {e}")
                raise
            
            logger.info("Weaviate connection successful")
            return True
            
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Weaviate. Is it running?")
            return False
        except requests.exceptions.Timeout:
            logger.error("Weaviate connection timed out")
            return False
        except Exception as e:
            logger.error(f"Weaviate connection test failed: {e}")
            return False
        
    def _initialize_agents(self):
        """Initialize all available agents with proper error handling"""
        logger.info("Starting agent initialization...")
        
        # Initialize Document Agent (Vector Search)
        try:
            # First check if we can import the module
            try:
                from src.agents.obsidian.atomic_document_agent import AtomicDocumentAgent
            except ImportError as e:
                logger.error(f"Cannot import AtomicDocumentAgent: {e}")
                logger.info("Please ensure atomic_document_agent.py exists and dependencies are installed")
                
            else:
                # Test Weaviate connection before initializing
                if not self._test_weaviate_connection():
                    logger.warning("Skipping Document Agent initialization due to Weaviate connection failure")
                    logger.info("You can still use NORTH for other features")
                else:
                    # Initialize the agent
                    agent = AtomicDocumentAgent()
                    self.agents['document'] = agent
                    logger.info("Atomic Document Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Document Agent initialization failed: {e}", exc_info=True)
            logger.info("NORTH will continue without document search capabilities")
        
        # Initialize Dropbox Integration (V2 Weaviate-based implementation)
        try:
            from src.agents.dropbox_v2 import get_dropbox_integration
            
            # Initialize the V2 Dropbox-Weaviate integration
            dropbox_integration = get_dropbox_integration()
            if dropbox_integration.initialized:
                self.agents['dropbox'] = dropbox_integration
                logger.info("Dropbox-Weaviate Integration initialized successfully")
            else:
                logger.warning("Dropbox integration failed to initialize - check configuration")
            
        except ImportError as e:
            logger.error(f"Cannot import Dropbox integration: {e}")
            logger.info("Please ensure Weaviate client is installed")
        except Exception as e:
            logger.error(f"Dropbox integration initialization failed: {e}", exc_info=True)
            logger.info("NORTH will continue without Dropbox capabilities")
            
        # Log summary of available agents
        if self.agents:
            logger.info(f"Available agents: {', '.join(self.agents.keys())}")
        else:
            logger.warning("No agents were successfully initialized")
    
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools from available agents - one tool per agent for simplicity"""
        tools = []
        
        if 'document' in self.agents:
            # Single tool for all Obsidian/Weaviate operations
            def search_knowledge_base(query: str) -> str:
                """Search the Obsidian knowledge base for company information.
                Use this for:
                - Company or contractor details
                - Phone numbers or emails  
                - Project information
                - Work history or costs
                - Any information from notes/documents
                """
                agent = self.agents['document']
                # Return raw results to let NORTH format the response once
                if hasattr(agent, 'search'):
                    return agent.search(query, raw_results=True)
                elif hasattr(agent, 'query'):
                    return agent.query(query)
                else:
                    return agent.search(query)
            
            tools.append(Tool(
                name="search_knowledge_base",
                func=search_knowledge_base,
                description="Search Obsidian notes for company info, contractors, projects, contacts"
            ))
        else:
            # Add placeholder tool that explains Obsidian is unavailable
            def obsidian_unavailable(query: str) -> str:
                """Handle requests for Obsidian/company information when the system is unavailable."""
                return "I'm sorry, but my Obsidian knowledge base is currently unavailable. This is likely because Weaviate (the database service) isn't running. Please start Docker Desktop and Weaviate to enable access to company information, contractor details, and project data. If you need help with this, contact my creator Abe."
            
            tools.append(Tool(
                name="search_knowledge_base", 
                func=obsidian_unavailable,
                description="Explains that Obsidian search is currently unavailable"
            ))
        
        if 'dropbox' in self.agents:
            # Single tool for intelligent Dropbox operations
            def search_dropbox_files(request: str) -> str:
                """Search or browse Dropbox files using natural language.
                The Dropbox agent understands:
                - Document types (invoices, contracts, W9s, insurance, change orders)
                - Contractor and project names
                - Company folder structure
                - Complex queries like "find all signed contracts from officially hired contractors"
                
                Just describe what you're looking for in plain English.
                """
                dropbox_agent = self.agents['dropbox']
                return dropbox_agent.handle_request(request)
            
            tools.append(Tool(
                name="search_dropbox_files",
                func=search_dropbox_files,
                description="Search Dropbox using natural language - understands all document types, contractors, projects"
            ))
            
        return tools
    
    def process_query(self, query: str, context_manager: Optional[ContextManager] = None) -> str:
        """
        Process user query and return response - NORTH responds naturally

        Args:
            query: User's query string
            context_manager: Optional ContextManager for this session (enables per-user context)

        Returns:
            Response string
        """
        # Use provided context manager or fall back to instance default
        ctx = context_manager if context_manager is not None else self.context_manager

        try:
            # Check if we can answer from cached context first
            cached_answer = ctx.can_answer_from_context(query)
            if cached_answer:
                logger.info(f"Answering from context cache: {cached_answer}")
                return cached_answer

            # Get conversation history for context
            history = self._format_chat_history(ctx)

            # Get available tools description
            tools_description = ""
            if self.tools:
                tools_description = "\n".join([f"- {t.name}: {t.description}" for t in self.tools])
            else:
                tools_description = "No tools currently available"

            # Let NORTH respond naturally with tool access
            if self.agent_executor:
                start_time = time.time()

                # NORTH processes the query naturally
                response = self.agent_executor.invoke({
                    "input": query,
                    "chat_history": history,
                    "tools": tools_description,
                    "conversation_history": ctx.get_context_for_llm()
                })

                response_text = response.get("output", "I'm not sure how to help with that.")

                logger.info(f"NORTH response time: {time.time() - start_time:.2f}s")
            else:
                # Fallback if no tools available - still respond naturally
                response_text = self._respond_without_tools(query)

            # Add exchange to context for future reference
            ctx.add_exchange(query, response_text)

            # Cache the response
            ctx.cache_result(query, response_text)

            return response_text

        except Exception as e:
            logger.error(f"Error processing query '{query}': {e}", exc_info=True)
            return "I encountered an issue processing your request. Could you please try rephrasing it?"

    def process_query_with_metadata(self, query: str, context_manager: Optional[ContextManager] = None) -> Dict[str, Any]:
        """
        Process query and return response WITH metadata about tool usage.
        Useful for evaluation and debugging.

        Args:
            query: User's query string
            context_manager: Optional ContextManager for this session

        Returns:
            Dict with:
                - response: The response text
                - tools_used: List of tool names that were invoked
                - latency_ms: Response time in milliseconds
                - from_cache: Whether response came from cache
        """
        # Use provided context manager or fall back to instance default
        ctx = context_manager if context_manager is not None else self.context_manager

        try:
            # Check if we can answer from cached context first
            cached_answer = ctx.can_answer_from_context(query)
            if cached_answer:
                logger.info(f"Answering from context cache: {cached_answer}")
                return {
                    "response": cached_answer,
                    "tools_used": [],
                    "latency_ms": 0,
                    "from_cache": True
                }

            # Get conversation history for context
            history = self._format_chat_history(ctx)

            # Get available tools description
            tools_description = ""
            if self.tools:
                tools_description = "\n".join([f"- {t.name}: {t.description}" for t in self.tools])
            else:
                tools_description = "No tools currently available"

            # Let NORTH respond naturally with tool access
            tools_used = []
            if self.agent_executor:
                start_time = time.time()

                # NORTH processes the query naturally
                response = self.agent_executor.invoke({
                    "input": query,
                    "chat_history": history,
                    "tools": tools_description,
                    "conversation_history": ctx.get_context_for_llm()
                })

                response_text = response.get("output", "I'm not sure how to help with that.")
                latency_ms = (time.time() - start_time) * 1000

                # Extract actual tool usage from intermediate_steps
                if "intermediate_steps" in response:
                    for step in response["intermediate_steps"]:
                        # step is (AgentAction, observation)
                        if hasattr(step[0], 'tool'):
                            tools_used.append(step[0].tool)

                logger.info(f"NORTH response time: {latency_ms:.0f}ms | Tools used: {tools_used}")
            else:
                # Fallback if no tools available
                response_text = self._respond_without_tools(query)
                latency_ms = 0

            # Add exchange to context for future reference
            ctx.add_exchange(query, response_text)

            # Cache the response
            ctx.cache_result(query, response_text)

            return {
                "response": response_text,
                "tools_used": tools_used,
                "latency_ms": latency_ms,
                "from_cache": False
            }

        except Exception as e:
            logger.error(f"Error processing query '{query}': {e}", exc_info=True)
            return {
                "response": "I encountered an issue processing your request. Could you please try rephrasing it?",
                "tools_used": [],
                "latency_ms": 0,
                "from_cache": False
            }
    
    def _format_chat_history(self, context_manager: Optional[ContextManager] = None) -> List:
        """Format conversation history for the agent"""
        ctx = context_manager if context_manager is not None else self.context_manager
        messages = []
        raw_messages = ctx.get_messages()

        for msg in raw_messages:
            if msg.get('role') == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg.get('role') == 'assistant':
                messages.append(AIMessage(content=msg['content']))

        return messages
    
    def _respond_without_tools(self, query: str) -> str:
        """Respond when no tools are available - still be NORTH"""
        # Use the LLM to generate a natural response even without tools
        simple_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are NORTH, an AI assistant for construction and project management.
            You currently don't have access to your database, but you can still have a helpful conversation.
            Be friendly, professional, and let the user know if you need your tools back online to answer specific questions."""),
            ("human", "{query}")
        ])
        
        chain = simple_prompt | self.llm
        response = chain.invoke({"query": query})
        return response.content
    
    def process_query_with_files(self, query: str, files: List[Dict[str, Any]], context_manager: Optional[ContextManager] = None) -> str:
        """
        Process a query with attached files (images, PDFs, etc.)
        Uses GPT-4o's vision capabilities for comprehensive understanding

        Args:
            query: User's query string
            files: List of processed file dictionaries
            context_manager: Optional ContextManager for this session (enables per-user context)

        Returns:
            Response string
        """
        # Use provided context manager or fall back to instance default
        ctx = context_manager if context_manager is not None else self.context_manager

        try:
            # Prepare content blocks for vision API
            content_blocks = []

            # Add the user's text query
            content_blocks.append({
                "type": "text",
                "text": query
            })

            # Add processed files
            file_blocks = FileProcessor.prepare_for_vision_api(files)
            content_blocks.extend(file_blocks)

            # Log what we're processing
            logger.info(f"Processing query with {len(files)} files")
            for file in files:
                if 'error' not in file:
                    logger.info(f"  - {file.get('filename')}: {file.get('type')} ({file.get('mime_type')})")
                else:
                    logger.warning(f"  - {file.get('filename')}: {file.get('error')}")

            # Build the conversation with context
            messages = []

            # Add context from previous conversation if available
            # get_messages() returns list of dicts with 'role' and 'content'
            context_messages = ctx.get_messages()
            if context_messages:
                # Convert to LangChain message objects
                for msg in context_messages:
                    if msg['role'] == 'user':
                        messages.append(HumanMessage(content=msg['content']))
                    elif msg['role'] == 'assistant':
                        messages.append(AIMessage(content=msg['content']))
            
            # Add the multimodal message
            messages.append(HumanMessage(content=content_blocks))
            
            # Get NORTH's prompt
            north_prompt = self._get_north_prompt()
            
            # Create the full prompt with system message
            full_messages = [
                SystemMessage(content=north_prompt),
                *messages
            ]
            
            # Process with vision-capable model
            response = self.llm.invoke(full_messages)
            
            # Extract text content from response
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Update context for next query (use per-user context)
            ctx.add_exchange(
                query=f"{query} [with {len(files)} attached files]",
                response=response_text
            )
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error processing query with files: {e}", exc_info=True)
            
            # Fallback to text-only processing if vision fails
            fallback_query = query
            if files:
                # Add file information to query
                file_info = []
                for file in files:
                    if file.get('type') == 'text' or file.get('type') == 'document':
                        # Include text content if available
                        if 'content' in file:
                            file_info.append(f"File {file['filename']}:\n{file['content'][:500]}...")
                    else:
                        file_info.append(f"[Attached file: {file.get('filename', 'unknown')}]")
                
                if file_info:
                    fallback_query = f"{query}\n\nAttached files:\n" + "\n".join(file_info)
            
            # Process as regular text query
            return self.process_query(fallback_query)
    
    def cleanup(self):
        """Clean up all agents properly"""
        if self._cleanup_called:
            return
        self._cleanup_called = True
        
        logger.info("Cleaning up agents...")
        for name, agent in self.agents.items():
            try:
                if hasattr(agent, 'close'):
                    agent.close()
                    logger.info(f"Closed {name} agent")
                elif hasattr(agent, 'cleanup'):
                    agent.cleanup()
                    logger.info(f"Cleaned up {name} agent")
                # Special handling for dropbox agent's Weaviate client
                if name == 'dropbox' and hasattr(agent, 'agent'):
                    if hasattr(agent.agent, 'close'):
                        agent.agent.close()
                        logger.info(f"Closed Dropbox Weaviate client")
            except Exception as e:
                logger.error(f"Error cleaning up {name} agent: {e}")
        
        # Close main Weaviate client if it exists
        if hasattr(self, 'weaviate_client') and self.weaviate_client:
            try:
                self.weaviate_client.close()
                logger.info("Closed main Weaviate client")
            except Exception as e:
                logger.error(f"Error closing main Weaviate client: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup happens"""
        try:
            self.cleanup()
        except Exception:
            # Destructors shouldn't raise
            return
