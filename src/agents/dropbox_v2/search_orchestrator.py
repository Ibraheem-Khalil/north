"""
Search Orchestrator for Dropbox
Implements dynamic search strategies without hardcoding
Uses Weaviate hybrid search with intelligent query generation
"""

import logging
from typing import Dict, List, Optional, Any
import weaviate
from weaviate.classes.query import Filter, MetadataQuery, HybridFusion
from datetime import datetime
import os

from .entity_extractor import DropboxEntityExtractor, SearchEntities
from .entity_discovery import EntityDiscovery

logger = logging.getLogger(__name__)


class DropboxSearchOrchestrator:
    """
    Orchestrates search operations using extracted entities
    No hardcoded logic - builds queries dynamically
    """
    
    def __init__(self):
        """Initialize the search orchestrator"""
        # Entity extraction
        self.extractor = DropboxEntityExtractor()
        
        # Connect to Weaviate
        self.weaviate_client = self._connect_weaviate()
        
        # Entity discovery from actual data
        self.discovery = EntityDiscovery(self.weaviate_client)
        
        # Track search context for follow-ups
        self.search_context = {}
        
        logger.info("DropboxSearchOrchestrator initialized")
    
    def _connect_weaviate(self) -> Optional[weaviate.Client]:
        """Connect to Weaviate (production or local)"""
        try:
            if os.getenv("WEAVIATE_URL") and os.getenv("WEAVIATE_API_KEY"):
                # Production: Weaviate Cloud
                # Build headers with Voyage API key
                headers = {}
                voyage_key = os.getenv("VOYAGE_API_KEY")
                if voyage_key:
                    headers["X-VoyageAI-Api-Key"] = voyage_key
                    
                client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=os.getenv("WEAVIATE_URL"),
                    auth_credentials=weaviate.auth.AuthApiKey(os.getenv("WEAVIATE_API_KEY")),
                    headers=headers if headers else None
                )
            else:
                # Local: Docker instance
                client = weaviate.connect_to_local(host="localhost", port=8080)
            
            logger.info("Connected to Weaviate")
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            return None
    
    def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Main search method - orchestrates the entire search process
        
        Args:
            query: Natural language query from user
            max_results: Maximum number of results to return
            
        Returns:
            Search results with metadata
        """
        try:
            # Step 1: Discover entities from the system (if first run)
            discovered = self.discovery.discover_from_weaviate()
            
            # Step 2: Extract entities from the query
            entities = self.extractor.extract_with_examples(query, discovered)
            
            # Step 3: Build search strategy based on extracted entities
            search_strategies = self._build_search_strategies(entities)
            
            # Step 4: Execute searches with fallback logic
            results = []
            for strategy in search_strategies:
                strategy_results = self._execute_search(strategy)
                if strategy_results:
                    results.extend(strategy_results)
            
            # Step 5: If no results, try refinement
            if not results and entities:
                refined_entities = self.extractor.refine_with_feedback(
                    query, entities, no_results=True
                )
                refined_strategies = self._build_search_strategies(refined_entities)
                
                for strategy in refined_strategies[:2]:  # Try top 2 refined strategies
                    strategy_results = self._execute_search(strategy)
                    if strategy_results:
                        results.extend(strategy_results)
            
            # Step 6: Rank and format results
            ranked_results = self._rank_results(results, entities)
            
            # Update context for follow-up queries
            if ranked_results:
                self.search_context['last_search'] = query
                self.search_context['last_document'] = ranked_results[0].get('name')
                self.search_context['last_entities'] = entities.model_dump()
            
            return {
                'success': bool(ranked_results),
                'results': ranked_results[:max_results],
                'entities_extracted': entities.model_dump(),
                'strategies_tried': len(search_strategies),
                'total_found': len(results)
            }
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }
    
    def _build_search_strategies(self, entities: SearchEntities) -> List[Dict]:
        """
        Build multiple search strategies from extracted entities
        No hardcoding - dynamically generates queries
        
        Args:
            entities: Extracted entities from the query
            
        Returns:
            List of search strategies to try
        """
        strategies = []
        
        # Strategy 1: Hybrid search with all extracted terms
        terms = []
        if entities.project:
            terms.append(entities.project)
        if entities.contractor:
            terms.append(entities.contractor)
        if entities.document_type:
            terms.append(entities.document_type)
        terms.extend(entities.keywords)
        
        if terms:
            strategies.append({
                'type': 'hybrid',
                'query': ' '.join(terms),
                'alpha': 0.5,  # Equal weight to semantic and keyword
                'filters': self._build_filters(entities)
            })
        
        # Strategy 2: Pure semantic search if we have natural language
        if len(' '.join(terms)) > 10:  # Substantial query
            strategies.append({
                'type': 'vector',
                'query': ' '.join(terms),
                'filters': self._build_filters(entities)
            })
        
        # Strategy 3: Keyword search for specific identifiers
        if entities.specific_file or any(keyword.replace('.', '').isdigit() for keyword in entities.keywords):
            # Might be looking for invoice number or specific file
            strategies.append({
                'type': 'keyword',
                'query': entities.specific_file or ' '.join(entities.keywords),
                'filters': self._build_filters(entities)
            })
        
        # Strategy 4: Broader search without filters if needed
        if terms:
            strategies.append({
                'type': 'hybrid',
                'query': ' '.join(terms),
                'alpha': 0.7,  # More semantic weight for broader matching
                'filters': None  # No filters for broader search
            })
        
        return strategies
    
    def _build_filters(self, entities: SearchEntities) -> Optional[Filter]:
        """
        Build Weaviate v4 Filter objects from entities
        Uses LIKE operator for flexible matching
        
        Args:
            entities: Extracted entities
            
        Returns:
            Weaviate v4 Filter object or None
        """
        conditions = []
        
        if entities.project:
            # Use LIKE for partial matching (e.g., "123 Main" matches "123 Main Street")
            conditions.append(
                Filter.by_property("project_name").like(f"*{entities.project}*")
            )
        
        if entities.contractor:
            # Search in both contractor AND vendor_name fields (OR logic)
            # This ensures we find documents where the company might be in either field
            contractor_condition = Filter.by_property("contractor").like(f"*{entities.contractor}*") | \
                                 Filter.by_property("vendor_name").like(f"*{entities.contractor}*")
            conditions.append(contractor_condition)
        
        if entities.document_type:
            conditions.append(
                Filter.by_property("document_type").like(f"*{entities.document_type}*")
            )
        
        if not conditions:
            return None
        
        if len(conditions) == 1:
            return conditions[0]
        
        # Combine multiple conditions with AND
        result = conditions[0]
        for cond in conditions[1:]:
            result = result & cond
        
        return result
    
    def _execute_search(self, strategy: Dict) -> List[Dict]:
        """
        Execute a search strategy against Weaviate
        Searches both Document and DocumentChunk collections
        
        Args:
            strategy: Search strategy configuration
            
        Returns:
            List of search results
        """
        if not self.weaviate_client:
            return []
        
        try:
            # Search both collections
            documents = self._search_documents(strategy)
            chunks = self._search_chunks(strategy)
            
            # Combine and deduplicate results
            combined = self._combine_results(documents, chunks)
            return combined
            
        except Exception as e:
            logger.error(f"Search execution failed: {e}")
            return []
    
    def _search_documents(self, strategy: Dict) -> List[Dict]:
        """Search the main Document collection"""
        try:
            collection = self.weaviate_client.collections.get("Document")
            
            # Build and execute query based on strategy type
            if strategy['type'] == 'hybrid':
                # Hybrid search combining vector and keyword
                response = collection.query.hybrid(
                    query=strategy['query'],
                    alpha=strategy.get('alpha', 0.5),
                    fusion_type=HybridFusion.RELATIVE_SCORE,
                    limit=20,
                    filters=strategy.get('filters'),
                    return_properties=["name", "file_path", "project_name", "contractor", "vendor_name",
                                     "document_type", "content", "file_size", "modified_date"],
                    return_metadata=MetadataQuery(score=True)
                )
            elif strategy['type'] == 'vector':
                # Pure vector/semantic search
                response = collection.query.near_text(
                    query=strategy['query'],
                    limit=20,
                    filters=strategy.get('filters'),
                    return_properties=["name", "file_path", "project_name", "contractor", "vendor_name",
                                     "document_type", "content", "file_size", "modified_date"],
                    return_metadata=MetadataQuery(score=True)
                )
            elif strategy['type'] == 'keyword':
                # BM25 keyword search
                response = collection.query.bm25(
                    query=strategy['query'],
                    limit=20,
                    filters=strategy.get('filters'),
                    return_properties=["name", "file_path", "project_name", "contractor", "vendor_name",
                                     "document_type", "content", "file_size", "modified_date"],
                    return_metadata=MetadataQuery(score=True)
                )
            else:
                # Fallback to fetch_objects with filters
                response = collection.query.fetch_objects(
                    limit=20,
                    filters=strategy.get('filters'),
                    return_properties=[
                        "name",
                        "file_path",
                        "project_name",
                        "contractor",
                        "vendor_name",
                        "document_type",
                        "content",
                        "file_size",
                        "modified_date",
                    ]
                )
            
            # Extract results from v4 response
            documents = []
            if response and response.objects:
                for obj in response.objects:
                    doc = obj.properties
                    doc['_id'] = str(obj.uuid)
                    # Add vector score if available
                    if hasattr(obj, 'metadata') and hasattr(obj.metadata, 'score'):
                        doc['_score'] = obj.metadata.score
                    documents.append(doc)
                logger.info(f"Strategy {strategy['type']} found {len(documents)} results")
            
            return documents
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
    
    def _search_chunks(self, strategy: Dict) -> List[Dict]:
        """Search the DocumentChunk collection"""
        try:
            # Check if chunk collection exists
            collections = self.weaviate_client.collections.list_all()
            if "DocumentChunk" not in collections:
                return []
            
            collection = self.weaviate_client.collections.get("DocumentChunk")
            
            # Execute same query against chunks
            if strategy['type'] == 'hybrid':
                response = collection.query.hybrid(
                    query=strategy['query'],
                    alpha=strategy.get('alpha', 0.5),
                    fusion_type=HybridFusion.RELATIVE_SCORE,
                    limit=30,
                    filters=strategy.get('filters'),
                    return_properties=[
                        "parent_dropbox_id",
                        "parent_name",
                        "file_path",
                        "chunk_index",
                        "total_chunks",
                        "content",
                        "project_name",
                        "contractor",
                        "vendor_name",
                        "document_type",
                    ],
                    return_metadata=MetadataQuery(score=True)
                )
            elif strategy['type'] == 'vector':
                response = collection.query.near_text(
                    query=strategy['query'],
                    limit=30,
                    filters=strategy.get('filters'),
                    return_properties=[
                        "parent_dropbox_id",
                        "parent_name",
                        "file_path",
                        "chunk_index",
                        "total_chunks",
                        "content",
                        "project_name",
                        "contractor",
                        "vendor_name",
                        "document_type",
                    ],
                    return_metadata=MetadataQuery(score=True)
                )
            elif strategy['type'] == 'keyword':
                response = collection.query.bm25(
                    query=strategy['query'],
                    limit=30,
                    filters=strategy.get('filters'),
                    return_properties=[
                        "parent_dropbox_id",
                        "parent_name",
                        "file_path",
                        "chunk_index",
                        "total_chunks",
                        "content",
                        "project_name",
                        "contractor",
                        "vendor_name",
                        "document_type",
                    ],
                    return_metadata=MetadataQuery(score=True)
                )
            else:
                return []
            
            # Extract chunk results
            chunks = []
            if response and response.objects:
                for obj in response.objects:
                    chunk = obj.properties
                    chunk['_id'] = str(obj.uuid)
                    chunk['_is_chunk'] = True
                    # Add vector score if available
                    if hasattr(obj, 'metadata') and hasattr(obj.metadata, 'score'):
                        chunk['_score'] = obj.metadata.score
                    chunks.append(chunk)
                logger.debug(f"Found {len(chunks)} chunk results")
            
            return chunks
            
        except Exception as e:
            logger.error(f"Chunk search failed: {e}")
            return []
    
    def _combine_results(self, documents: List[Dict], chunks: List[Dict]) -> List[Dict]:
        """
        Combine document and chunk results
        Groups chunks by parent document and deduplicates
        
        Args:
            documents: Results from Document collection
            chunks: Results from DocumentChunk collection
            
        Returns:
            Combined and deduplicated results
        """
        # Track seen documents
        seen_ids = set()
        combined = []
        
        # Add full documents first
        for doc in documents:
            doc_id = doc.get('dropbox_id') or doc.get('_id')
            if doc_id:
                seen_ids.add(doc_id)
                combined.append(doc)
        
        # Group chunks by parent document and track best score
        chunks_by_parent = {}
        for chunk in chunks:
            parent_id = chunk.get('parent_dropbox_id')
            if parent_id:
                if parent_id not in chunks_by_parent:
                    chunks_by_parent[parent_id] = []
                chunks_by_parent[parent_id].append(chunk)
        
        # Add documents found via chunks (if not already added)
        for parent_id, chunk_list in chunks_by_parent.items():
            if parent_id not in seen_ids:
                # Sort chunks by score to get best match
                chunk_list.sort(key=lambda c: c.get('_score', 0), reverse=True)
                best_chunk = chunk_list[0]
                
                # Create a synthetic document from chunk info
                synthetic_doc = {
                    'dropbox_id': parent_id,
                    'name': best_chunk.get('parent_name'),
                    'file_path': best_chunk.get('file_path'),
                    'project_name': best_chunk.get('project_name'),
                    'contractor': best_chunk.get('contractor'),
                    'document_type': best_chunk.get('document_type'),
                    # Include best matching chunk content
                    'content': best_chunk.get('content'),
                    '_matched_chunks': len(chunk_list),
                    '_from_chunks': True,
                    # Use the best chunk's score
                    '_score': best_chunk.get('_score', 0)
                }
                combined.append(synthetic_doc)
                seen_ids.add(parent_id)
        
        logger.info(f"Combined {len(documents)} documents and {len(chunks_by_parent)} from chunks")
        return combined
    
    
    def _rank_results(self, results: List[Dict], entities: SearchEntities) -> List[Dict]:
        """
        Rank search results based on relevance
        Uses vector scores as primary ranking, with entity matching as tiebreaker
        
        Args:
            results: Raw search results
            entities: Original search entities
            
        Returns:
            Ranked and deduplicated results
        """
        # Deduplicate by file path
        seen_paths = set()
        unique_results = []
        
        for result in results:
            path = result.get('file_path', '')
            if path and path not in seen_paths:
                seen_paths.add(path)
                
                # Calculate heuristic score for entity matches (used as tiebreaker)
                heuristic_score = 0
                
                # Score based on entity matches
                if entities.project and entities.project.lower() in str(result).lower():
                    heuristic_score += 3
                
                if entities.contractor and entities.contractor.lower() in str(result).lower():
                    heuristic_score += 3
                
                if entities.document_type and entities.document_type.lower() in str(result).lower():
                    heuristic_score += 2
                
                # Score based on keyword matches
                for keyword in entities.keywords:
                    if keyword.lower() in str(result).lower():
                        heuristic_score += 1
                
                result['heuristic_score'] = heuristic_score
                unique_results.append(result)
        
        # Sort by vector score (if available) then by heuristic score
        # Higher scores are better for both
        unique_results.sort(
            key=lambda x: (
                x.get('_score', 0),  # Primary: vector score from Weaviate
                x.get('heuristic_score', 0)  # Secondary: entity matching score
            ), 
            reverse=True
        )
        
        return unique_results
    
    def search_with_context(self, query: str) -> Dict[str, Any]:
        """
        Search with context from previous searches
        Handles follow-up queries like "show me the invoice for that"
        
        Args:
            query: Follow-up query
            
        Returns:
            Search results
        """
        # Extract entities with context
        entities = self.extractor.extract(query, self.search_context)
        
        # If this is a follow-up, inherit some context
        if 'that' in query.lower() or 'it' in query.lower():
            if self.search_context.get('last_entities'):
                last = self.search_context['last_entities']
                
                # Inherit project/contractor if not specified
                if not entities.project and last.get('project'):
                    entities.project = last['project']
                if not entities.contractor and last.get('contractor'):
                    entities.contractor = last['contractor']
        
        # Continue with normal search
        return self.search(query)
