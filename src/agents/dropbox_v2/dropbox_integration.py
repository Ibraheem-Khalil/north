"""
Main Dropbox Integration for NORTH AI
Production-grade implementation with dynamic entity extraction and search orchestration
Dynamic, non-hardcoded, intelligent search system
"""

import logging
from typing import Optional, Dict, Any
from .search_orchestrator import DropboxSearchOrchestrator
from .incremental_sync import IncrementalSync

logger = logging.getLogger(__name__)


class DropboxIntegration:
    """
    Main integration class for NORTH
    Provides clean interface for Dropbox search and sync
    """
    
    def __init__(self):
        """Initialize the Dropbox integration"""
        try:
            # Initialize search orchestrator
            self.search = DropboxSearchOrchestrator()
            
            # Initialize sync manager
            self.sync = IncrementalSync()
            
            self.initialized = True
            logger.info("DropboxIntegration V2 initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Dropbox integration: {e}")
            self.search = None
            self.sync = None
            self.initialized = False
    
    def handle_request(self, request: str, context: Optional[Dict] = None) -> str:
        """
        Main entry point from NORTH
        Handles natural language requests about Dropbox documents
        
        Args:
            request: Natural language query from user
            context: Optional context from previous interactions
            
        Returns:
            Formatted response string
        """
        if not self.initialized:
            return "Dropbox integration is not available. Please check configuration and ensure Weaviate is running."
        
        try:
            # Perform search with context if available
            if context and self.search:
                results = self.search.search_with_context(request)
            else:
                results = self.search.search(request)
            
            # Format response
            return self._format_response(request, results)
            
        except Exception as e:
            logger.error(f"Error handling Dropbox request: {e}")
            return f"I encountered an error searching Dropbox: {str(e)}"
    
    def _format_response(self, query: str, results: Dict[str, Any]) -> str:
        """
        Format search results into a user-friendly response
        
        Args:
            query: Original user query
            results: Search results from orchestrator
            
        Returns:
            Formatted response string
        """
        if not results.get('success'):
            if results.get('error'):
                return f"I couldn't search Dropbox due to an error: {results['error']}"
            return "I couldn't find any documents matching your search."
        
        documents = results.get('results', [])
        
        if not documents:
            # Provide helpful response even when no results
            entities = results.get('entities_extracted', {})
            response = "I couldn't find any documents matching your search.\n\n"
            response += "I was looking for:\n"
            
            if entities.get('project'):
                response += f"• Project: {entities['project']}\n"
            if entities.get('contractor'):
                response += f"• Contractor: {entities['contractor']}\n"
            if entities.get('document_type'):
                response += f"• Document type: {entities['document_type']}\n"
            
            response += "\nTry rephrasing your search or checking if the document exists with a different name."
            return response
        
        # Build response with found documents
        response = f"I found {len(documents)} document{'s' if len(documents) > 1 else ''} matching your search:\n\n"
        
        for i, doc in enumerate(documents[:5], 1):  # Show top 5
            response += f"**{i}. {doc.get('name', 'Unknown')}**\n"
            
            # Add metadata if available
            if doc.get('project_name'):
                response += f"   Project: {doc['project_name']}\n"
            if doc.get('contractor'):
                response += f"   Contractor: {doc['contractor']}\n"
            elif doc.get('vendor_name'):
                response += f"   Vendor: {doc['vendor_name']}\n"
            if doc.get('document_type'):
                response += f"   Type: {doc['document_type']}\n"
            
            # Add document-specific details
            if doc.get('invoice_number'):
                response += f"   Invoice #: {doc['invoice_number']}\n"
            if doc.get('invoice_amount'):
                response += f"   Amount: ${doc['invoice_amount']:,.2f}\n"
            
            # Add path
            response += f"   Path: {doc.get('file_path', 'Unknown')}\n"
            
            # Add modified date
            if doc.get('modified_date'):
                # Handle both datetime objects and strings
                modified = doc['modified_date']
                if hasattr(modified, 'strftime'):
                    # It's a datetime object
                    response += f"   Modified: {modified.strftime('%Y-%m-%d')}\n"
                else:
                    # It's a string - take first 10 chars
                    response += f"   Modified: {str(modified)[:10]}\n"
            
            response += "\n"
        
        if len(documents) > 5:
            response += f"... and {len(documents) - 5} more document{'s' if len(documents) > 6 else ''}.\n"
        
        # Add search intelligence info
        if results.get('strategies_tried', 0) > 1:
            response += f"\nNote: I tried {results['strategies_tried']} different search strategies to find these results."
        
        return response
    
    def search_documents(self, query: str) -> Dict[str, Any]:
        """
        Direct search interface for documents
        
        Args:
            query: Search query
            
        Returns:
            Raw search results
        """
        if not self.initialized or not self.search:
            return {
                'success': False,
                'error': 'Dropbox integration not initialized',
                'results': []
            }
        
        return self.search.search(query)
    
    def run_sync(self, force_full: bool = False) -> Dict[str, Any]:
        """
        Run document sync (for manual or scheduled execution)
        
        Args:
            force_full: Force full sync instead of incremental
            
        Returns:
            Sync statistics
        """
        if not self.initialized or not self.sync:
            return {
                'success': False,
                'error': 'Dropbox integration not initialized'
            }
        
        try:
            if force_full:
                return self.sync.perform_initial_sync()
            else:
                return self.sync.run_daily_sync()
                
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status of the Dropbox integration
        
        Returns:
            Status information
        """
        status = {
            'initialized': self.initialized,
            'search_available': self.search is not None,
            'sync_available': self.sync is not None
        }
        
        if self.sync:
            try:
                sync_status = self.sync.get_sync_status()
                status['sync'] = sync_status
            except Exception as e:
                status['sync_error'] = str(e)
        
        if self.search and self.search.weaviate_client:
            try:
                # Get some index stats
                from .weaviate_indexer import WeaviateIndexer
                indexer = WeaviateIndexer()
                stats = indexer.get_index_stats()
                status['index'] = stats
            except Exception as e:
                status['index_error'] = str(e)
        
        return status


# Global instance for easy access
_dropbox_integration = None


def get_dropbox_integration() -> DropboxIntegration:
    """
    Get or create the global Dropbox integration instance
    
    Returns:
        DropboxIntegration instance
    """
    global _dropbox_integration
    if _dropbox_integration is None:
        _dropbox_integration = DropboxIntegration()
    return _dropbox_integration


def close_dropbox_integration() -> None:
    """Close and cleanup the global Dropbox integration"""
    global _dropbox_integration
    if _dropbox_integration:
        # Cleanup if needed
        _dropbox_integration = None
        logger.info("Dropbox integration closed")
