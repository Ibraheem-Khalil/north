"""
Atomic Document Ingestion for NORTH AI System
Handles both Company and WorkLog documents with proper YAML parsing
"""

import os
import re
import yaml
import uuid
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import weaviate
import weaviate.classes as wvc
from weaviate.classes.query import Filter
from weaviate.classes.config import Property, DataType, Configure
from weaviate.util import generate_uuid5
from dotenv import load_dotenv
import frontmatter
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AtomicObsidianIngestion:
    def __init__(self):
        load_dotenv()
        self.client = None
        self.company_collection = None
        self.worklog_collection = None
        
    def create_schema(self):
        """Create collections with proper schema if they don't exist"""
        try:
            # Check if Company collection exists
            existing_collections = self.client.collections.list_all()
            
            if "Company" not in existing_collections:
                logger.info("Creating Company collection with schema...")
                self.client.collections.create(
                    name="Company",
                    vectorizer_config=Configure.Vectorizer.text2vec_voyageai(
                        model="voyage-3-large"
                    ),
                    properties=[
                        # Entity identifiers
                        Property(name="entity_uid", data_type=DataType.TEXT),
                        Property(name="entity_id", data_type=DataType.TEXT),
                        
                        # Core fields
                        Property(name="company", data_type=DataType.TEXT),
                        Property(name="services", data_type=DataType.TEXT_ARRAY),
                        Property(name="role", data_type=DataType.TEXT_ARRAY),
                        Property(name="hired", data_type=DataType.BOOL),
                        
                        # Contact info - raw and normalized
                        Property(name="office_phone", data_type=DataType.TEXT),
                        Property(name="mobile_phone", data_type=DataType.TEXT),
                        Property(name="phone_e164", data_type=DataType.TEXT),  # Normalized phone
                        Property(name="email", data_type=DataType.TEXT_ARRAY),
                        Property(name="email_lower", data_type=DataType.TEXT_ARRAY),  # Normalized emails
                        Property(name="point_of_contact", data_type=DataType.TEXT),
                        
                        # Additional info
                        Property(name="website", data_type=DataType.TEXT),
                        Property(name="address", data_type=DataType.TEXT),
                        Property(name="locations", data_type=DataType.TEXT_ARRAY),
                        Property(name="referred_by", data_type=DataType.TEXT),
                        Property(name="notes", data_type=DataType.TEXT),
                        Property(name="tags", data_type=DataType.TEXT_ARRAY),
                        
                        # Extracted markdown sections
                        Property(name="performance_notes", data_type=DataType.TEXT_ARRAY),
                        Property(name="knowledge_gained", data_type=DataType.TEXT),
                        Property(name="references", data_type=DataType.TEXT_ARRAY),
                        
                        # Content
                        Property(name="content", data_type=DataType.TEXT),
                        Property(name="filename", data_type=DataType.TEXT)
                    ]
                )
                logger.info("Company collection created successfully")
            
            if "WorkLog" not in existing_collections:
                logger.info("Creating WorkLog collection with schema...")
                self.client.collections.create(
                    name="WorkLog",
                    vectorizer_config=Configure.Vectorizer.text2vec_voyageai(
                        model="voyage-3-large"
                    ),
                    properties=[
                        # Entity identifiers
                        Property(name="entity_uid", data_type=DataType.TEXT),
                        Property(name="worklog_uid", data_type=DataType.TEXT),
                        
                        # Project info
                        Property(name="company", data_type=DataType.TEXT),
                        Property(name="project", data_type=DataType.TEXT),
                        Property(name="project_id", data_type=DataType.TEXT),  # Normalized project ID
                        Property(name="role", data_type=DataType.TEXT),
                        Property(name="scope", data_type=DataType.TEXT_ARRAY),
                        
                        # Details - using proper data types
                        Property(name="cost", data_type=DataType.NUMBER),  # NUMBER not TEXT
                        Property(name="status", data_type=DataType.TEXT),
                        Property(name="rehire", data_type=DataType.BOOL),  # BOOLEAN not TEXT
                        
                        # Dates
                        Property(name="start_date", data_type=DataType.TEXT),
                        Property(name="end_date", data_type=DataType.TEXT),
                        Property(name="duration", data_type=DataType.TEXT),
                        
                        # Metadata
                        Property(name="tags", data_type=DataType.TEXT_ARRAY),
                        
                        # Extracted markdown sections
                        Property(name="performance_notes", data_type=DataType.TEXT_ARRAY),
                        Property(name="knowledge_gained", data_type=DataType.TEXT),
                        Property(name="references", data_type=DataType.TEXT_ARRAY),
                        
                        Property(name="content", data_type=DataType.TEXT),
                        Property(name="filename", data_type=DataType.TEXT)
                    ]
                )
                logger.info("WorkLog collection created successfully")
                
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
            # Continue anyway - collections might already exist with correct schema
        
    def connect(self):
        """Connect to Weaviate"""
        try:
            # Try cloud first
            if os.getenv("WEAVIATE_URL") and os.getenv("WEAVIATE_API_KEY"):
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=os.getenv("WEAVIATE_URL"),
                    auth_credentials=weaviate.auth.AuthApiKey(os.getenv("WEAVIATE_API_KEY")),
                    headers={"X-VoyageAI-Api-Key": os.getenv("VOYAGE_API_KEY")}  # Pass Voyage key for WCD
                )
                logger.info("Connected to Weaviate Cloud")
            else:
                raise Exception("No cloud config")
        except Exception as e:
            # Fall back to local Docker
            try:
                self.client = weaviate.connect_to_local(
                    host="localhost", 
                    port=8080,
                    grpc_port=50051,
                    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
                )
                logger.info("Connected to local Weaviate")
            except Exception as e:
                logger.error(f"Failed to connect to Weaviate: {e}")
                raise
        
        # Create schema if needed
        self.create_schema()
        
        # Get collections
        self.company_collection = self.client.collections.get("Company")
        self.worklog_collection = self.client.collections.get("WorkLog")
        return self.client
    
    def parse_obsidian_file(self, filepath: Path) -> Dict:
        """Parse Obsidian file with frontmatter"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            # Get document type from metadata
            doc_type = post.metadata.get('type', 'unknown')
            
            # Base document data
            doc_data = {
                'filename': filepath.name,
                'content': post.content,  # Full markdown content
                'type': doc_type
            }
            
            # Add all metadata
            doc_data.update(post.metadata)
            
            return doc_data
            
        except Exception as e:
            logger.error(f"Error parsing {filepath}: {e}")
            return None
    
    def _convert_to_bool(self, value: Union[str, bool, None]) -> Optional[bool]:
        """Convert yes/no strings to boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ['yes', 'true', '1']
        return None
    
    def _convert_to_number(self, value: Union[str, float, int, None]) -> Optional[float]:
        """Convert string numbers to float"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove common formatting
            cleaned = value.replace('$', '').replace(',', '').strip()
            try:
                return float(cleaned)
            except Exception:
                return None
        return None
    
    def _ensure_array(self, value: Union[str, List, None]) -> List[str]:
        """Ensure value is an array"""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [value]
        return []
    
    def _ensure_string(self, value: Union[str, List, None]) -> str:
        """Ensure value is a string, not an array"""
        if value is None:
            return ''
        if isinstance(value, list):
            # If it's an empty list, return empty string
            if not value:
                return ''
            # If list has items, join them
            return ', '.join(str(v) for v in value)
        return str(value)
    
    def generate_entity_uid(self, company_name: str) -> str:
        """Generate deterministic entity UID from company name"""
        if not company_name:
            return ""
        
        # Clean and normalize the name
        clean_name = company_name.strip().lower()
        # Remove common suffixes that might change
        clean_name = re.sub(r'\s+(llc|inc|corp|ltd|co\.?)$', '', clean_name, flags=re.IGNORECASE)
        
        # Generate deterministic UUID
        namespace = uuid.NAMESPACE_DNS
        entity_uid = str(uuid.uuid5(namespace, f"company:{clean_name}"))
        
        return entity_uid
    
    def generate_entity_id(self, company_name: str) -> str:
        """Generate human-readable slug from company name"""
        if not company_name:
            return ""
        
        # Basic slugification
        slug = company_name.lower().strip()
        # Remove special characters
        slug = re.sub(r'[^\w\s-]', '', slug)
        # Replace spaces with hyphens
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def normalize_phone(self, phone_raw: str) -> Optional[str]:
        """Normalize phone to E.164 format for integrations"""
        if not phone_raw:
            return None
        
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', str(phone_raw))
        
        # Handle US phone numbers
        if len(digits) == 10:
            # Standard US number without country code
            return f"+1{digits}"
        elif len(digits) == 11 and digits[0] == '1':
            # US number with country code
            return f"+{digits}"
        
        # Can't normalize - return None but keep raw
        logger.debug(f"Could not normalize phone: {phone_raw}")
        return None
    
    def normalize_email_list(self, emails: Union[str, List[str], None]) -> List[str]:
        """Normalize emails to lowercase for consistent lookups"""
        if not emails:
            return []
        
        # Convert to list if string
        if isinstance(emails, str):
            emails = [emails]
        
        normalized = []
        for email in emails:
            if email:
                # Basic normalization - lowercase and strip
                email = str(email).strip().lower()
                normalized.append(email)
        
        return normalized
    
    def normalize_project_id(self, project_name: str) -> str:
        """Convert project names to consistent IDs"""
        if not project_name:
            return ""

        # Common project patterns
        patterns = [
            (r'^(\d+)\s+Regency', '\\1-regency'),
            (r'^(\d+)\s+[NS]\.?\s*Mitchell', '\\1-mitchell'),
            (r'^(\d+)\s+Broadmoor', '\\1-broadmoor'),
            (r'^(\d+)\s+Newt Patterson', '\\1-newt-patterson'),
        ]
        
        for pattern, replacement in patterns:
            match = re.search(pattern, project_name, re.IGNORECASE)
            if match:
                # Extract just the pattern match and apply replacement
                return re.sub(pattern, replacement, project_name, flags=re.IGNORECASE).split()[0].lower()
        
        # Fallback: take first number and first significant word
        match = re.match(r'^(\d+)\s+([A-Za-z]+)', project_name)
        if match:
            return f"{match.group(1)}-{match.group(2).lower()}"
        
        # Last resort: slugify first 30 chars
        slug = re.sub(r'[^\w\s-]', '', project_name[:30].lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def extract_markdown_sections(self, content: str) -> Dict:
        """Extract specific sections from markdown content"""
        sections = {
            'performance_notes': [],
            'knowledge_gained': '',
            'references': []
        }
        
        if not content:
            return sections
            
        # Extract Performance Notes (bullet points after ## Performance Notes)
        if "## Performance Notes" in content or "## performance notes" in content.lower():
            try:
                # Find the section between Performance Notes and the next section
                pattern = r'##\s*Performance Notes(.*?)(?=##|\Z)'
                match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if match:
                    notes_text = match.group(1)
                    # Extract bullet points (lines starting with -)
                    notes = []
                    for line in notes_text.split('\n'):
                        line = line.strip()
                        if line.startswith('-'):
                            note = line.lstrip('-').strip()
                            if note:
                                notes.append(note)
                    sections['performance_notes'] = notes
            except Exception as e:
                logger.debug(f"Could not extract performance notes: {e}")
        
        # Extract Knowledge Gained (paragraph text after ## Knowledge Gained)
        if "## Knowledge Gained" in content or "## knowledge gained" in content.lower():
            try:
                pattern = r'##\s*Knowledge Gained(.*?)(?=##|\Z)'
                match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if match:
                    knowledge_text = match.group(1).strip()
                    # Remove any markdown formatting and clean up
                    knowledge_text = knowledge_text.replace('---', '').strip()
                    if knowledge_text:
                        sections['knowledge_gained'] = knowledge_text
            except Exception as e:
                logger.debug(f"Could not extract knowledge gained: {e}")
        
        # Extract References (links from ## Reference or ## References)
        if "## Reference" in content or "## reference" in content.lower():
            try:
                pattern = r'##\s*References?(.*?)(?=##|\Z)'
                match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if match:
                    ref_text = match.group(1)
                    # Extract URLs from markdown links [text](url) or plain URLs
                    url_pattern = r'\[.*?\]\((.*?)\)|https?://[^\s\)]+'
                    urls = re.findall(url_pattern, ref_text)
                    # Clean up URLs
                    refs = []
                    for url in urls:
                        if url:  # From markdown link format
                            refs.append(url)
                        elif url.startswith('http'):  # Plain URL
                            refs.append(url)
                    sections['references'] = refs
            except Exception as e:
                logger.debug(f"Could not extract references: {e}")
                
        return sections
    
    def prepare_company_document(self, doc_data: Dict) -> Dict:
        """Prepare company document for ingestion with normalization"""
        # Extract markdown sections from content
        content = doc_data.get('content', '')
        markdown_sections = self.extract_markdown_sections(content)
        
        # Generate entity identifiers
        company_name = doc_data.get('company', '')
        entity_uid = self.generate_entity_uid(company_name)
        entity_id = self.generate_entity_id(company_name)
        
        # Normalize phone (prefer office, fall back to mobile)
        office_phone = self._ensure_string(doc_data.get('office_phone'))
        mobile_phone = self._ensure_string(doc_data.get('mobile_phone'))
        phone_e164 = self.normalize_phone(office_phone) or self.normalize_phone(mobile_phone)
        
        # Normalize emails
        email_raw = self._ensure_array(doc_data.get('email'))
        email_lower = self.normalize_email_list(email_raw)
        
        return {
            # Entity identifiers
            'entity_uid': entity_uid,
            'entity_id': entity_id,
            
            # Core fields
            'company': company_name,
            'services': self._ensure_array(doc_data.get('services')),
            'role': self._ensure_array(doc_data.get('role')),
            'hired': self._convert_to_bool(doc_data.get('hired')),
            
            # Contact info - both raw and normalized
            'office_phone': office_phone,
            'mobile_phone': mobile_phone,
            'phone_e164': phone_e164 or '',  # Empty string if can't normalize
            'email': email_raw,
            'email_lower': email_lower,
            'point_of_contact': self._ensure_string(doc_data.get('point_of_contact')),
            
            # Additional info
            'website': self._ensure_string(doc_data.get('website')),
            'address': self._ensure_string(doc_data.get('address')),
            'locations': self._ensure_array(doc_data.get('locations')),
            'referred_by': self._ensure_string(doc_data.get('referred_by')),
            'notes': self._ensure_string(doc_data.get('notes')),
            'tags': self._ensure_array(doc_data.get('tags')),
            
            # Extracted markdown sections
            'performance_notes': markdown_sections['performance_notes'],
            'knowledge_gained': markdown_sections['knowledge_gained'],
            'references': markdown_sections['references'],
            
            # Content
            'content': content,
            'filename': doc_data.get('filename', '')
        }
    
    def prepare_worklog_document(self, doc_data: Dict) -> Dict:
        """Prepare work log document for ingestion with entity linking"""
        # Extract markdown sections from content
        content = doc_data.get('content', '')
        markdown_sections = self.extract_markdown_sections(content)
        
        # Generate entity UID from company name
        company_name = doc_data.get('company', '')
        entity_uid = self.generate_entity_uid(company_name)
        
        # Generate project ID
        project_name = doc_data.get('project', '')
        project_id = self.normalize_project_id(project_name)
        
        # Generate worklog UID
        scope = doc_data.get('scope', [])
        scope_str = scope[0] if isinstance(scope, list) and scope else str(scope)
        start_date = doc_data.get('start_date', '')
        worklog_uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 
                          f"{entity_uid}#{project_id}#{scope_str}#{start_date or 'undated'}"))
        
        
        # Handle scope field - could be string or array
        scope = doc_data.get('scope', [])
        if isinstance(scope, str):
            # Split by common delimiters
            scope = [s.strip() for s in re.split(r'[,;]|\s+and\s+', scope) if s.strip()]
        elif isinstance(scope, list):
            # Ensure all items are strings
            scope = [str(s).strip() for s in scope if s]
        else:
            scope = []
        
        # Handle duration field which might be 'duration_days' or 'duration'
        duration = doc_data.get('duration', '')
        if not duration:
            duration = doc_data.get('duration_days', '')
            
        # Convert cost to NUMBER for Weaviate
        cost_value = self._convert_to_number(doc_data.get('cost'))
            
        # Convert rehire to BOOLEAN for Weaviate  
        rehire_value = self._convert_to_bool(doc_data.get('rehire'))
            
        # Handle company field - could be empty array or string
        company = doc_data.get('company', '')
        if isinstance(company, list):
            company = company[0] if company else ''
        elif company is None:
            company = ''
        else:
            company = str(company)
            
        # Handle role field - could be empty array or string
        role = doc_data.get('role', '')
        if isinstance(role, list):
            role = role[0] if role else ''
        elif role is None:
            role = ''
        else:
            role = str(role)
            
        return {
            # Entity identifiers
            'entity_uid': entity_uid,
            'worklog_uid': worklog_uid,
            
            # Project info
            'company': company,
            'project': project_name,
            'project_id': project_id,
            'role': role,
            'scope': scope,
            
            # Details (with proper types for Weaviate schema)
            'cost': cost_value,  # NUMBER type
            'status': doc_data.get('status', ''),
            'rehire': rehire_value,  # BOOLEAN type
            
            # Dates
            'start_date': str(doc_data.get('start_date', '')) if doc_data.get('start_date') else '',
            'end_date': str(doc_data.get('end_date', '')) if doc_data.get('end_date') else '',
            'duration': str(duration),
            
            # Metadata
            'tags': self._ensure_array(doc_data.get('tags')),
            
            # Extracted markdown sections
            'performance_notes': markdown_sections['performance_notes'],
            'knowledge_gained': markdown_sections['knowledge_gained'],
            'references': markdown_sections['references'],
            
            'content': content,
            'filename': doc_data.get('filename', '')
        }
    
    def ingest_file(self, filepath: Path) -> bool:
        """Ingest a single file"""
        try:
            logger.info(f"Processing: {filepath.name}")
            
            # Parse the file
            doc_data = self.parse_obsidian_file(filepath)
            if not doc_data:
                logger.debug(f"  Failed to parse: {filepath.name}")
                return False
            
            # Route based on document type
            doc_type = doc_data.get('type', '').lower()
            logger.debug(f"  Document type: '{doc_type}' (original: '{doc_data.get('type', '')}')")
            
            if doc_type == 'company-log':
                # Prepare and ingest company document
                company_data = self.prepare_company_document(doc_data)
                
                # Use entity_uid as the document UUID for stability
                doc_uuid = company_data['entity_uid']
                
                try:
                    # Check if document already exists
                    existing = self.company_collection.data.get_by_id(doc_uuid)
                    if existing:
                        # Update existing document
                        self.company_collection.data.update(
                            uuid=doc_uuid,
                            properties=company_data
                        )
                        logger.info(f"  → Updated company: {company_data.get('company', 'Unknown')}")
                    else:
                        # Insert new document
                        self.company_collection.data.insert(
                            properties=company_data,
                            uuid=doc_uuid
                        )
                        logger.info(f"  → Ingested company: {company_data.get('company', 'Unknown')}")
                except Exception as e:
                    # If get_by_id fails, try to insert
                    try:
                        self.company_collection.data.insert(
                            properties=company_data,
                            uuid=doc_uuid
                        )
                        logger.info(f"  → Ingested company: {company_data.get('company', 'Unknown')}")
                    except Exception as insert_error:
                        if "already exists" in str(insert_error):
                            # Document exists, try to update
                            self.company_collection.data.update(
                                uuid=doc_uuid,
                                properties=company_data
                            )
                            logger.info(f"  → Updated company: {company_data.get('company', 'Unknown')}")
                        else:
                            raise insert_error
                
            elif doc_type == 'work-log':
                # Prepare and ingest work log
                worklog_data = self.prepare_worklog_document(doc_data)
                
                # Use worklog_uid as the document UUID for stability
                doc_uuid = worklog_data['worklog_uid']
                
                try:
                    # Check if document already exists
                    existing = self.worklog_collection.data.get_by_id(doc_uuid)
                    if existing:
                        # Update existing document
                        self.worklog_collection.data.update(
                            uuid=doc_uuid,
                            properties=worklog_data
                        )
                        logger.info(f"  → Updated work log: {worklog_data.get('company', 'Unknown')} - {worklog_data.get('project', 'Unknown')}")
                    else:
                        # Insert new document
                        self.worklog_collection.data.insert(
                            properties=worklog_data,
                            uuid=doc_uuid
                        )
                        logger.info(f"  → Ingested work log: {worklog_data.get('company', 'Unknown')} - {worklog_data.get('project', 'Unknown')}")
                except Exception as e:
                    # If get_by_id fails, try to insert
                    try:
                        self.worklog_collection.data.insert(
                            properties=worklog_data,
                            uuid=doc_uuid
                        )
                        logger.info(f"  → Ingested work log: {worklog_data.get('company', 'Unknown')} - {worklog_data.get('project', 'Unknown')}")
                    except Exception as insert_error:
                        if "already exists" in str(insert_error):
                            # Document exists, try to update
                            self.worklog_collection.data.update(
                                uuid=doc_uuid,
                                properties=worklog_data
                            )
                            logger.info(f"  → Updated work log: {worklog_data.get('company', 'Unknown')} - {worklog_data.get('project', 'Unknown')}")
                        else:
                            raise insert_error
                
            else:
                logger.warning(f"  ⚠ Unknown document type: {doc_type}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"  ✗ Error ingesting {filepath}: {e}")
            return False
    
    def ingest_directory(self, directory: str, filter_types: List[str] = None) -> Dict[str, int]:
        """Ingest all markdown files from a directory
        
        Args:
            directory: Path to the directory to scan
            filter_types: Optional list of document types to process (e.g., ['work-log', 'company-log'])
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise ValueError(f"Directory not found: {directory}")
        
        # Find all .md files in this directory and subdirectories
        md_files = list(dir_path.rglob("*.md"))
        logger.info(f"\nSearching in: {directory}")
        logger.info(f"Found {len(md_files)} markdown files in Index folder")
        
        # If filter_types is specified, pre-filter files
        if filter_types:
            logger.info(f"Filtering for document types: {filter_types}")
            filtered_files = []
            for filepath in md_files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        post = frontmatter.load(f)
                        doc_type = post.metadata.get('type', '')
                        if doc_type in filter_types:
                            filtered_files.append(filepath)
                except Exception:
                    pass
            md_files = filtered_files
            logger.info(f"Found {len(md_files)} files with specified types")
        
        results = {
            "total_files": len(md_files),
            "companies_ingested": 0,
            "worklogs_ingested": 0,
            "failed": 0
        }
        
        for filepath in md_files:
            success = self.ingest_file(filepath)
            if success:
                # Check which type was ingested
                with open(filepath, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                    doc_type = post.metadata.get('type', '').lower()
                    if doc_type == 'company-log':
                        results["companies_ingested"] += 1
                    elif doc_type == 'work-log':
                        results["worklogs_ingested"] += 1
            else:
                results["failed"] += 1
        
        return results
    
    def clear_collection(self, collection_name: str):
        """Clear all documents from a collection"""
        try:
            if collection_name == "WorkLog":
                collection = self.worklog_collection
            elif collection_name == "Company":
                collection = self.company_collection
            else:
                raise ValueError(f"Unknown collection: {collection_name}")
            
            # Get current count
            count_before = collection.aggregate.over_all(total_count=True).total_count
            
            # Delete all objects - v4 syntax
            # Note: delete_many with empty where clause deletes all
            result = collection.data.delete_many(
                where=Filter.by_property("filename").like("*")  # Match all files
            )
            
            # Verify deletion
            count_after = collection.aggregate.over_all(total_count=True).total_count
            logger.info(f"Cleared {collection_name}: {count_before} → {count_after} documents")
            
        except Exception as e:
            logger.error(f"Error clearing {collection_name}: {e}")
    
    def verify_ingestion(self):
        """Verify and display ingested documents"""
        # Check Company collection
        company_count = self.company_collection.aggregate.over_all(total_count=True).total_count
        logger.info(f"\nCompany collection: {company_count} documents")
        
        # Show sample companies
        if company_count > 0:
            logger.info("\nSample companies:")
            companies = self.company_collection.query.fetch_objects(limit=3)
            for company in companies.objects:
                props = company.properties
                logger.info(f"  - {props.get('company', 'Unknown')}")
                logger.info(f"    Services: {props.get('services', [])}")
                logger.info(f"    Office: {props.get('office_phone', 'N/A')}")
                logger.info(f"    Hired: {props.get('hired', 'N/A')}")
        
        # Check WorkLog collection
        worklog_count = self.worklog_collection.aggregate.over_all(total_count=True).total_count
        logger.info(f"\nWorkLog collection: {worklog_count} documents")
        
        # Show sample work logs
        if worklog_count > 0:
            logger.info("\nSample work logs:")
            worklogs = self.worklog_collection.query.fetch_objects(limit=3)
            for worklog in worklogs.objects:
                props = worklog.properties
                logger.info(f"  - {props.get('company', 'Unknown')} @ {props.get('project', 'Unknown')}")
                logger.info(f"    Scope: {props.get('scope', [])}")
                cost = props.get('cost')
                if cost is not None:
                    # Cost is already a NUMBER type
                    logger.info(f"    Cost: ${cost:,.2f}")
                else:
                    logger.info(f"    Cost: Not specified")
                rehire = props.get('rehire')
                if rehire is not None:
                    # Rehire is already a BOOLEAN type
                    logger.info(f"    Rehire: {'Yes' if rehire else 'No'}")
                else:
                    logger.info(f"    Rehire: Not specified")

def main():
    """Run atomic ingestion"""
    ingestion = AtomicObsidianIngestion()
    
    logger.info("Connecting to Weaviate...")
    ingestion.connect()
    
    # Get directory from user or use default
    import sys
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = input("Enter path to Index folder (or press Enter for default): ").strip()
        if not directory:
            # Use OBSIDIAN_VAULT_PATH from environment or prompt user
            vault_path = os.getenv('OBSIDIAN_VAULT_PATH')
            if vault_path:
                # Get index folder path from environment or use default
                # Format: "Company Name/Main Files/3 - Index" or just "3 - Index"
                index_folder = os.getenv('OBSIDIAN_INDEX_FOLDER', '3 - Index')
                directory = os.path.join(vault_path, index_folder)
            else:
                print("Error: OBSIDIAN_VAULT_PATH not set in environment")
                print("Please set OBSIDIAN_VAULT_PATH in your .env file")
                return

    # Ask if user wants to filter for specific types
    filter_types = None
    response = None  # Initialize response variable
    
    if len(sys.argv) > 2:
        if sys.argv[2] == "--work-logs":
            filter_types = ['work-log']
        elif sys.argv[2] == "--companies":
            filter_types = ['company-log']
        elif sys.argv[2] == "--all":
            filter_types = ['work-log', 'company-log']
        elif sys.argv[2] == "--clear-and-ingest":
            filter_types = ['work-log', 'company-log']
            # Automatically clear collections
            logger.info("\nClearing collections before ingestion...")
            ingestion.clear_collection("WorkLog")
            ingestion.clear_collection("Company")
    else:
        response = input("\nIngest: (1) Work logs only, (2) Companies only, (3) Both, (4) Clear & ingest both? [3]: ").strip()
        if response == '1':
            filter_types = ['work-log']
        elif response == '2':
            filter_types = ['company-log']
        elif response == '4':
            filter_types = ['work-log', 'company-log']
            # Automatically clear collections
            logger.info("\nClearing collections before ingestion...")
            ingestion.clear_collection("WorkLog")
            ingestion.clear_collection("Company")
        else:  # Default to '3' or empty
            filter_types = ['work-log', 'company-log']
    
    # Ask if user wants to clear collections first (only if not already cleared)
    if '--clear-and-ingest' not in sys.argv and response != '4':
        if filter_types and filter_types == ['work-log']:
            clear_response = input("\nClear existing work logs before ingesting? (y/N): ").strip().lower()
            if clear_response == 'y':
                ingestion.clear_collection("WorkLog")
        elif filter_types and filter_types == ['company-log']:
            clear_response = input("\nClear existing companies before ingesting? (y/N): ").strip().lower()
            if clear_response == 'y':
                ingestion.clear_collection("Company")
        elif filter_types and 'work-log' in filter_types and 'company-log' in filter_types:
            clear_response = input("\nClear existing collections before ingesting? (y/N): ").strip().lower()
            if clear_response == 'y':
                ingestion.clear_collection("WorkLog")
                ingestion.clear_collection("Company")
    
    logger.info(f"\nIngesting from: {directory}")
    if filter_types:
        logger.info(f"Filtering for types: {filter_types}")
    
    results = ingestion.ingest_directory(directory, filter_types)
    
    logger.info(f"\n=== Ingestion Summary ===")
    logger.info(f"Total files: {results['total_files']}")
    logger.info(f"Companies ingested: {results['companies_ingested']}")
    logger.info(f"Work logs ingested: {results['worklogs_ingested']}")
    logger.info(f"Failed: {results['failed']}")
    
    # Verify
    ingestion.verify_ingestion()
    
    # Close connection
    ingestion.client.close()

if __name__ == "__main__":
    main()
    
    # Auto-update service tags after ingestion
    print("\n" + "="*60)
    print("Updating service tags...")
    from update_service_tags import update_service_tags
    update_service_tags()
    print("="*60)
