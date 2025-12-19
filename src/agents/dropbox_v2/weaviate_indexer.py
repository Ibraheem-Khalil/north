"""
Weaviate Indexer for Dropbox Documents
Manages document indexing in Weaviate vector database
Single unified collection design for predictable indexing and search
"""

import logging
import os
from typing import Dict, List, Optional, Any
import weaviate
from weaviate.classes.config import Configure, Property, DataType, StopwordsPreset
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.classes.aggregate import GroupByAggregate
from datetime import datetime, timezone
import hashlib
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class WeaviateIndexer:
    """
    Handles all Weaviate operations for document indexing
    Uses a single unified collection for all documents
    """
    
    def __init__(self):
        """Initialize Weaviate connection and schema"""
        self.client = self._connect_weaviate()
        self.collection_name = "Document"
        self.chunk_collection_name = "DocumentChunk"
        
        if self.client:
            self._ensure_schema()
            logger.info("WeaviateIndexer initialized")
        else:
            logger.error("Failed to initialize WeaviateIndexer")
    
    def _connect_weaviate(self) -> Optional[weaviate.Client]:
        """Connect to Weaviate (cloud or local)"""
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
                logger.info("Connected to Weaviate Cloud")
            else:
                # Local: Docker instance
                client = weaviate.connect_to_local(host="localhost", port=8080)
                logger.info("Connected to local Weaviate")
            
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            return None
    
    def _ensure_schema(self) -> None:
        """
        Ensure both Document and DocumentChunk collections exist
        Implements chunked indexing for better recall
        """
        if not self.client:
            return
        
        try:
            # Check if collections exist
            collections = self.client.collections.list_all()
            
            # Create main Document collection if needed
            if self.collection_name not in collections:
                self._create_document_collection()
            else:
                logger.debug(f"Collection {self.collection_name} already exists")
            
            # Create DocumentChunk collection if needed
            if self.chunk_collection_name not in collections:
                self._create_chunk_collection()
            else:
                logger.debug(f"Collection {self.chunk_collection_name} already exists")
            
            # Idempotently ensure vendor_name exists on both collections
            try:
                doc_col = self.client.collections.get(self.collection_name)
                try:
                    doc_col.config.add_property(Property(name="vendor_name", data_type=DataType.TEXT))
                    logger.info("Added missing property vendor_name to Document collection")
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Could not ensure Document.vendor_name: {e}")

            try:
                chunk_col = self.client.collections.get(self.chunk_collection_name)
                try:
                    chunk_col.config.add_property(Property(name="vendor_name", data_type=DataType.TEXT))
                    logger.info("Added missing property vendor_name to DocumentChunk collection")
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Could not ensure DocumentChunk.vendor_name: {e}")
                
        except Exception as e:
            logger.error(f"Failed to ensure schema: {e}")
    
    def _create_document_collection(self) -> None:
        """Create the main Document collection"""
        try:
            
            # Create collection with schema
            self.client.collections.create(
                name=self.collection_name,
                vectorizer_config=Configure.Vectorizer.text2vec_voyageai(
                    model="voyage-3-large"  # As specified in requirements
                ),
                properties=[
                    # Core identifiers
                    Property(name="dropbox_id", data_type=DataType.TEXT),
                    Property(name="name", data_type=DataType.TEXT),
                    Property(name="file_path", data_type=DataType.TEXT),
                    
                    # Content
                    Property(name="content", data_type=DataType.TEXT),
                    
                    # Dynamic extracted metadata (not hardcoded)
                    Property(name="project_name", data_type=DataType.TEXT),
                    Property(name="contractor", data_type=DataType.TEXT),
                    Property(name="document_type", data_type=DataType.TEXT),
                    
                    # File metadata
                    Property(name="file_size", data_type=DataType.INT),
                    Property(name="modified_date", data_type=DataType.DATE),
                    Property(name="created_date", data_type=DataType.DATE),
                    
                    # Document-specific metadata (optional fields)
                    Property(name="invoice_number", data_type=DataType.TEXT),
                    Property(name="invoice_amount", data_type=DataType.NUMBER),
                    Property(name="invoice_date", data_type=DataType.TEXT),
                    Property(name="vendor_name", data_type=DataType.TEXT),
                    
                    # Processing metadata
                    Property(name="indexed_at", data_type=DataType.DATE),
                    Property(name="text_length", data_type=DataType.INT),
                    Property(name="word_count", data_type=DataType.INT),
                    
                    # Content hash for deduplication
                    Property(name="content_hash", data_type=DataType.TEXT)
                ],
                # Enable BM25 for keyword search (hybrid capability)
                inverted_index_config=Configure.inverted_index(
                    bm25_b=0.75,
                    bm25_k1=1.2,
                    index_null_state=False,
                    index_property_length=True, 
                    index_timestamps=True,
                    stopwords_preset=StopwordsPreset.EN
                )
            )
            
            logger.info(f"Created collection {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to create Document collection: {e}")
    
    def _create_chunk_collection(self) -> None:
        """Create the DocumentChunk collection for chunked indexing"""
        try:
            self.client.collections.create(
                name=self.chunk_collection_name,
                vectorizer_config=Configure.Vectorizer.text2vec_voyageai(
                    model="voyage-3-large"
                ),
                properties=[
                    # Parent document reference
                    Property(name="parent_dropbox_id", data_type=DataType.TEXT),
                    Property(name="parent_name", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="total_chunks", data_type=DataType.INT),
                    
                    # Chunk content
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="chunk_size", data_type=DataType.INT),
                    
                    # Inherited metadata from parent
                    Property(name="file_path", data_type=DataType.TEXT),
                    Property(name="project_name", data_type=DataType.TEXT),
                    Property(name="contractor", data_type=DataType.TEXT),
                    Property(name="vendor_name", data_type=DataType.TEXT),
                    Property(name="document_type", data_type=DataType.TEXT),
                    Property(name="modified_date", data_type=DataType.DATE),
                    
                    # Processing metadata
                    Property(name="indexed_at", data_type=DataType.DATE)
                ],
                inverted_index_config=Configure.inverted_index(
                    bm25_b=0.75,
                    bm25_k1=1.2,
                    index_null_state=False,
                    index_property_length=True,
                    index_timestamps=True,
                    stopwords_preset=StopwordsPreset.EN
                )
            )
            
            logger.info(f"Created collection {self.chunk_collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to create DocumentChunk collection: {e}")
    
    def index_document(self, document: Dict[str, Any], enable_chunking: bool = True) -> bool:
        """
        Index a document in Weaviate with optional chunking
        
        Args:
            document: Document data to index
            enable_chunking: Whether to chunk the document for better recall
            
        Returns:
            True if successful
        """
        if not self.client:
            return False
        
        try:
            # Generate content hash for deduplication
            content = document.get('content', '')
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            document['content_hash'] = content_hash
            
            # Check if document already exists (by dropbox_id or content_hash)
            existing = self._find_existing_document(
                document.get('id'),
                content_hash
            )
            
            # If updating, clean up old chunks first
            if existing and enable_chunking:
                self._delete_document_chunks(document.get('id'))
            
            # Prepare document for indexing
            weaviate_doc = self._prepare_document_for_weaviate(document)
            
            collection = self.client.collections.get(self.collection_name)
            
            if existing:
                # Update existing document with retry
                self._update_document_with_retry(
                    collection,
                    existing['_additional']['id'],
                    weaviate_doc
                )
                logger.debug(f"Updated document {document.get('name')}")
            else:
                # Create new document with retry
                self._insert_document_with_retry(collection, weaviate_doc)
                logger.debug(f"Indexed new document {document.get('name')}")
            
            # Index chunks if enabled and content is substantial
            if enable_chunking and len(content) > 500:
                self._index_document_chunks(document)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to index document {document.get('name')}: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    def _insert_document_with_retry(self, collection, properties: Dict[str, Any]):
        """Insert document with retry logic"""
        return collection.data.insert(properties=properties)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    def _update_document_with_retry(self, collection, uuid: str, properties: Dict[str, Any]):
        """Update document with retry logic"""
        return collection.data.update(uuid=uuid, properties=properties)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    def _insert_chunk_with_retry(self, collection, properties: Dict[str, Any]):
        """Insert chunk with retry logic"""
        return collection.data.insert(properties=properties)
    
    def _prepare_document_for_weaviate(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare document for Weaviate indexing
        Handles type conversions and field mapping
        """
        # Map fields from processor to Weaviate schema
        weaviate_doc = {
            'dropbox_id': document.get('id'),
            'name': document.get('name'),
            'file_path': document.get('file_path'),
            'content': document.get('content', ''),
            
            # Dynamic metadata (may be None)
            'project_name': document.get('project_name'),
            'contractor': document.get('contractor'),
            'document_type': document.get('document_type'),
            
            # File metadata
            'file_size': document.get('file_size', 0),
            
            # Document metadata
            'invoice_number': document.get('invoice_number'),
            'invoice_amount': document.get('invoice_amount'),
            'invoice_date': document.get('invoice_date'),
            'vendor_name': document.get('vendor_name'),
            
            # Processing metadata
            'text_length': document.get('text_length', 0),
            'word_count': document.get('word_count', 0),
            'content_hash': document.get('content_hash')
        }
        
        # Handle dates
        if document.get('modified_date'):
            weaviate_doc['modified_date'] = self._parse_date(document['modified_date'])
        if document.get('created_date'):
            weaviate_doc['created_date'] = self._parse_date(document['created_date'])
        if document.get('indexed_at'):
            weaviate_doc['indexed_at'] = self._parse_date(document['indexed_at'])
        
        # Remove None values (Weaviate doesn't like them)
        weaviate_doc = {k: v for k, v in weaviate_doc.items() if v is not None}
        
        return weaviate_doc
    
    def _parse_date(self, date_str: str) -> str:
        """Parse date string to RFC3339 format for Weaviate"""
        try:
            # Try to parse ISO format and normalize to UTC
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Convert to UTC if it has timezone info
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            else:
                # Assume UTC if no timezone
                dt = dt.replace(tzinfo=timezone.utc)
            # Return RFC3339 format with single Z
            return dt.isoformat().replace('+00:00', 'Z')
        except Exception:
            # Return current time if parsing fails
            return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def _find_existing_document(self, dropbox_id: Optional[str], 
                               content_hash: str) -> Optional[Dict]:
        """
        Find existing document by Dropbox ID or content hash
        
        Args:
            dropbox_id: Dropbox file ID
            content_hash: SHA256 hash of content
            
        Returns:
            Existing document or None
        """
        if not self.client:
            return None
        
        try:
            # Get collection
            collection = self.client.collections.get(self.collection_name)
            
            # First try by dropbox_id (most reliable)
            if dropbox_id:
                response = collection.query.fetch_objects(
                    filters=Filter.by_property("dropbox_id").equal(dropbox_id),
                    limit=1,
                    return_properties=["dropbox_id"],
                    include_vector=False
                )
                
                if response and response.objects:
                    obj = response.objects[0]
                    return {"dropbox_id": obj.properties.get("dropbox_id"), 
                           "_additional": {"id": str(obj.uuid)}}
            
            # Fallback to content hash
            response = collection.query.fetch_objects(
                filters=Filter.by_property("content_hash").equal(content_hash),
                limit=1,
                return_properties=["content_hash"],
                include_vector=False
            )
            
            if response and response.objects:
                obj = response.objects[0]
                return {"content_hash": obj.properties.get("content_hash"),
                       "_additional": {"id": str(obj.uuid)}}
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding existing document: {e}")
            return None
    
    def delete_document(self, dropbox_id: str) -> bool:
        """
        Delete a document and all its chunks from Weaviate
        
        Args:
            dropbox_id: Dropbox file ID
            
        Returns:
            True if successful
        """
        if not self.client:
            return False
        
        try:
            # First delete all chunks for this document
            self._delete_document_chunks(dropbox_id)
            
            # Find document
            existing = self._find_existing_document(dropbox_id, "")
            if not existing:
                logger.warning(f"Document {dropbox_id} not found for deletion")
                return True  # Already gone
            
            # Delete by UUID
            collection = self.client.collections.get(self.collection_name)
            collection.data.delete_by_id(existing['_additional']['id'])
            
            logger.debug(f"Deleted document {dropbox_id} and its chunks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document {dropbox_id}: {e}")
            return False
    
    def document_exists(self, dropbox_id: str) -> bool:
        """Check if document exists in index"""
        return self._find_existing_document(dropbox_id, "") is not None
    
    def _index_document_chunks(self, document: Dict[str, Any]) -> None:
        """
        Index document chunks for better recall
        
        Args:
            document: Document with content to chunk
        """
        try:
            from .document_processor import DocumentProcessor
            
            # Create processor instance to use chunk_text method
            processor = DocumentProcessor()
            
            # Use full_text if available (for complete chunking), otherwise fall back to content
            content = document.get('full_text') or document.get('content', '')
            chunks = processor.chunk_text(content, chunk_size=1000, overlap=200)
            
            if not chunks:
                return
            
            # Get chunk collection
            chunk_collection = self.client.collections.get(self.chunk_collection_name)
            
            # Prepare metadata that's common to all chunks
            base_metadata = {
                'parent_dropbox_id': document.get('id'),
                'parent_name': document.get('name'),
                'file_path': document.get('file_path'),
                'project_name': document.get('project_name'),
                'contractor': document.get('contractor'),
                'vendor_name': document.get('vendor_name'),
                'document_type': document.get('document_type'),
                'total_chunks': len(chunks)
            }
            
            # Handle dates
            if document.get('modified_date'):
                base_metadata['modified_date'] = self._parse_date(document['modified_date'])
            
            # Index each chunk
            for idx, chunk_text in enumerate(chunks):
                chunk_data = {
                    **base_metadata,
                    'chunk_index': idx,
                    'content': chunk_text,
                    'chunk_size': len(chunk_text),
                    'indexed_at': datetime.utcnow().isoformat() + 'Z'
                }
                
                # Remove None values
                chunk_data = {k: v for k, v in chunk_data.items() if v is not None}
                
                # Insert chunk with retry
                self._insert_chunk_with_retry(chunk_collection, chunk_data)
            
            logger.debug(f"Indexed {len(chunks)} chunks for {document.get('name')}")
            
        except Exception as e:
            logger.error(f"Failed to index chunks for {document.get('name')}: {e}")
    
    def _delete_document_chunks(self, dropbox_id: str) -> None:
        """
        Delete all chunks for a document
        
        Args:
            dropbox_id: Dropbox ID of the parent document
        """
        try:
            chunk_collection = self.client.collections.get(self.chunk_collection_name)
            
            # Find and delete all chunks for this document
            response = chunk_collection.query.fetch_objects(
                filters=Filter.by_property("parent_dropbox_id").equal(dropbox_id),
                limit=1000
            )
            
            if response and response.objects:
                for obj in response.objects:
                    chunk_collection.data.delete_by_id(str(obj.uuid))
                logger.debug(f"Deleted {len(response.objects)} chunks for document {dropbox_id}")
                
        except Exception as e:
            logger.error(f"Failed to delete chunks for {dropbox_id}: {e}")
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the index"""
        if not self.client:
            return {'error': 'No client connection'}
        
        try:
            # Get collection
            collection = self.client.collections.get(self.collection_name)
            
            stats = {
                'total_documents': 0,
                'collection': self.collection_name
            }
            
            # Get document count using v4 aggregate API
            aggregate_response = collection.aggregate.over_all(
                total_count=True
            )
            
            if aggregate_response:
                stats['total_documents'] = aggregate_response.total_count or 0
            
            # Get document types breakdown using group_by
            type_aggregate = collection.aggregate.over_all(
                group_by=GroupByAggregate(prop="document_type")
            )
            
            if type_aggregate and type_aggregate.groups:
                stats['document_types'] = {}
                for group in type_aggregate.groups:
                    if group.grouped_by and group.grouped_by.get('document_type'):
                        stats['document_types'][group.grouped_by['document_type']] = group.total_count or 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {'error': str(e)}
