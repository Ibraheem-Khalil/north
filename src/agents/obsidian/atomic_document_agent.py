"""
Atomic Document Agent v4 - Clean implementation following strict requirements
Uses Weaviate v4 best practices with proper filter syntax
"""

import os
import json
import logging
from typing import List, Dict, Optional, Any
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

import weaviate
import weaviate.classes as wvc
from weaviate.classes.query import Filter, MetadataQuery
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import voyageai

logger = logging.getLogger(__name__)

class QueryType(Enum):
    """Types of queries we handle"""
    LIST_ALL = "list_all"        # "list all X suppliers"
    FIND_BY_PROJECT = "find_by_project"  # "who is the X for project Y"
    GET_CONTACT = "get_contact"  # "phone number for X"
    GENERAL = "general"          # everything else

class AtomicDocumentAgent:
    """Document agent with clean 3-stage architecture"""
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using Voyage AI"""
        if not hasattr(self, 'voyage_client') or not self.voyage_client:
            return None
        try:
            response = self.voyage_client.embed(
                [text],
                model="voyage-3-large",
                input_type="query"  # Use query type for search
            )
            return response.embeddings[0]
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None
    
    def __init__(self):
        load_dotenv()
        
        # Connect to Weaviate 
        try:
            weaviate_url = os.getenv("WEAVIATE_URL")
            weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
            
            if weaviate_url and weaviate_api_key:
                # Production: Weaviate Cloud
                logger.info(f"Connecting to Weaviate Cloud: {weaviate_url}")
                voyage_key = os.getenv("VOYAGE_API_KEY")
                headers = {"X-VoyageAI-Api-Key": voyage_key} if voyage_key else None
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=weaviate_url,
                    auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key),
                    headers=headers,
                    additional_config=wvc.init.AdditionalConfig(
                        timeout=wvc.init.Timeout(init=30, query=60, insert=120)
                    )
                )
            else:
                # Local development: Connect to Docker instance
                logger.info("Connecting to local Weaviate (Docker)")
                self.client = weaviate.connect_to_local(
                    host="localhost",
                    port=8080,
                    grpc_port=50051,
                    headers=None
                )
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise
        
        # Get collections
        self.company = self.client.collections.get("Company")
        self.worklog = self.client.collections.get("WorkLog")
        
        # Initialize LLM for query expansion and response (use gpt-4o-mini for better quality)
        self.llm = ChatOpenAI(temperature=0.2, model="gpt-4o-mini")
        
        # Initialize Voyage AI for reranking if available
        voyage_api_key = os.getenv('VOYAGE_API_KEY')
        if voyage_api_key:
            self.voyage_client = voyageai.Client(api_key=voyage_api_key)
            self.rerank_model = "rerank-2.5"
            logger.info("Voyage reranking enabled")
        else:
            self.voyage_client = None
            logger.info("Voyage reranking not available")
        
        # Load service tags for intelligent mapping
        self.service_tags = self._load_service_tags()
        
        # Response formatter
        self.response_template = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful assistant that answers based on the provided context.
    
    IMPORTANT: When asked about performance notes, look for the "Performance Notes:" section in the context.
    Performance notes may appear as a list of observations about a company's work quality.
    
    Instructions:
    1. Answer ONLY based on the provided context
    2. For performance notes specifically, look for and quote the "Performance Notes:" section
    3. If performance notes exist in the context, present them clearly
    4. When asked about specific types of contractors, identify companies based on Services/Scope fields
    5. Pay attention to relevance scores - higher scores mean more relevant results
    6. Be direct and concise
    7. If information is not in the context, say so clearly
    
    Context structure includes: Company, Services, Phone, Email, Project, Scope, Cost, Status, Performance Notes, and Knowledge Gained fields."""),
            ("human", "Context:\n{context}\n\nQuestion: {question}")
        ])
        self.response_chain = self.response_template | self.llm | StrOutputParser()
        
        logger.info("Atomic Document Agent v4 initialized")
    
    def _load_service_tags(self) -> List[str]:
        """Load service tags from JSON file"""
        tags_file = Path(__file__).parent / 'service_tags.json'
        if tags_file.exists():
            try:
                with open(tags_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {data['total_count']} service tags")
                    return data['services']
            except Exception as e:
                logger.warning(f"Failed to load service tags: {e}")
        return []
    
    def rerank_results(self, query: str, results: List[Dict], top_k: int = 5) -> List[Dict]:
        """Rerank search results using Voyage AI if available"""
        if not self.voyage_client or not results:
            return results[:top_k]
        
        try:
            # Format documents for reranking
            documents = []
            for result in results:
                # Create text representation based on result type
                if 'services' in result:  # Company result
                    doc_text = f"Company: {result.get('company', '')}\n"
                    doc_text += f"Services: {', '.join(result.get('services', []))}\n"
                    doc_text += f"Contact: {result.get('point_of_contact', '')}\n"
                    doc_text += f"Phone: {result.get('phone', '')}"
                elif 'project' in result:  # WorkLog result
                    doc_text = f"Company: {result.get('company', '')}\n"
                    doc_text += f"Project: {result.get('project', '')}\n"
                    doc_text += f"Scope: {', '.join(result.get('scope', []))}\n"
                    doc_text += f"Status: {result.get('status', '')}"
                else:
                    doc_text = str(result)
                
                documents.append(doc_text)
            
            # Rerank with Voyage
            rerank_response = self.voyage_client.rerank(
                query=query,
                documents=documents,
                model=self.rerank_model,
                top_k=min(top_k, len(documents))
            )
            
            # Return reranked results
            reranked = []
            for item in rerank_response.results:
                original_result = results[item.index]
                original_result['relevance_score'] = item.relevance_score
                reranked.append(original_result)
            
            logger.info(f"[RERANK] Reranked {len(results)} results to top {len(reranked)}")
            return reranked
            
        except Exception as e:
            logger.warning(f"[RERANK] Failed to rerank: {e}")
            return results[:top_k]
    
    def extract_service_tags(self, query: str) -> List[str]:
        """Use LLM to map user query to exact service tags"""
        if not self.service_tags:
            return []
        
        prompt = f"""Map this user query to the exact service tags from the list below.
User Query: "{query}"

Available Service Tags:
{', '.join(self.service_tags)}

Instructions:
1. Return ONLY exact matches from the available tags
2. Return multiple tags if the query matches multiple services
3. Handle variations (e.g., "concrete work" → "concrete labor")
4. If no exact match exists, return empty list

Return as JSON array of exact tags only. Examples:
- "I need concrete work" → ["concrete labor", "concrete supplier"]
- "electrical and plumbing" → ["Electric", "plumbing"]
- "conrete labor" (typo) → ["concrete labor"]

Tags:"""
        
        try:
            response = self.llm.invoke(prompt)
            # Parse the response to get tags
            import re
            # Extract JSON array from response
            match = re.search(r'\[.*?\]', response.content, re.DOTALL)
            if match:
                tags = json.loads(match.group())
                # Filter to ensure only valid tags
                valid_tags = [tag for tag in tags if tag in self.service_tags]
                logger.info(f"Mapped '{query}' to tags: {valid_tags}")
                return valid_tags
        except Exception as e:
            logger.warning(f"Failed to extract service tags: {e}")
        
        return []
    
    # Stage 1: Query Classification
    def classify_query(self, query: str) -> tuple[QueryType, Dict[str, Any]]:
        """Classify query type and extract parameters"""
        logger.info(f"[QUERY CLASSIFICATION] Analyzing: '{query}'")
        query_lower = query.lower()
        params = {}
        
        # Pattern 1: "list all" type queries - use LLM for flexible extraction
        # Check for "list all" patterns OR queries ending with "suppliers" or "contractors"
        if (any(phrase in query_lower for phrase in ["list all", "show all", "all suppliers", "all contractors", "companies that provide"]) or
            query_lower.endswith("suppliers") or query_lower.endswith("contractors") or 
            "suppliers" in query_lower.split() or "contractors" in query_lower.split()):
            logger.info("[QUERY CLASSIFICATION] Detected LIST_ALL pattern")
            
            # Use simple LLM prompt to extract service type
            extraction_prompt = f"""Extract the service/trade type from this query. Return ONLY the core service word.
Query: {query}
Examples: door, plumbing, glass, electrical, concrete
Service:"""
            
            try:
                # Quick LLM extraction using the existing self.llm
                response = self.llm.invoke(extraction_prompt)
                service = response.content.strip().lower()
                
                # Clean up common words that aren't services
                if service and service not in ["companies", "all", "that", "provide", "services", "none", ""]:
                    params["service"] = service
                    logger.info(f"[QUERY CLASSIFICATION] LLM extracted service: '{service}'")
            except Exception as e:
                logger.warning(f"[QUERY CLASSIFICATION] LLM extraction failed, using fallback: {e}")
                # Simple fallback - look for word before supplier/contractor
                words = query_lower.split()
                for i, word in enumerate(words):
                    if word in ["supplier", "suppliers", "contractor", "contractors", "services"]:
                        if i > 0 and words[i-1] not in ["that", "provide", "all"]:
                            params["service"] = words[i-1]
                            logger.info(f"[QUERY CLASSIFICATION] Fallback extracted: '{params['service']}'")
                        break
            
            logger.info(f"[QUERY CLASSIFICATION] Result: LIST_ALL with params: {params}")
            return QueryType.LIST_ALL, params
        
        # Pattern 2: "who is the X for project Y" or "who provided X for Y"
        project_keywords = ["regency", "mitchell", "emerald", "park place"]
        for keyword in project_keywords:
            if keyword in query_lower:
                logger.info(f"[QUERY CLASSIFICATION] Detected FIND_BY_PROJECT pattern with project: '{keyword}'")
                params["project"] = keyword
                # Don't extract service here - let search_worklogs_by_project handle it semantically
                # This allows semantic search to understand "foundation" -> concrete work, etc.
                logger.info(f"[QUERY CLASSIFICATION] Result: FIND_BY_PROJECT with params: {params}")
                return QueryType.FIND_BY_PROJECT, params
        
        # Pattern 3: "phone number for X" or "contact for X"
        if any(word in query_lower for word in ["phone", "number", "email", "contact"]):
            logger.info("[QUERY CLASSIFICATION] Detected GET_CONTACT pattern")
            logger.info(f"[QUERY CLASSIFICATION] Result: GET_CONTACT with params: {params}")
            return QueryType.GET_CONTACT, params
        
        logger.info("[QUERY CLASSIFICATION] No specific pattern detected - using GENERAL")
        return QueryType.GENERAL, params
    
    # Stage 2: Search Execution
    def search_companies_by_exact_tags(self, tags: List[str]) -> List[Dict]:
        """Search for companies with exact service tag matches"""
        logger.info(f"[EXACT TAG SEARCH] Searching for tags: {tags}")
        
        all_results = []
        seen_companies = set()
        
        for tag in tags:
            try:
                # Get ALL companies with this exact tag
                response = self.company.query.fetch_objects(
                    limit=200,  # Get all matches
                    return_properties=["company", "services", "office_phone", "mobile_phone", 
                                     "email", "phone_e164", "email_lower", "entity_uid", "hired"]
                )
                
                for obj in response.objects:
                    company_name = obj.properties.get("company", "")
                    services = obj.properties.get("services", [])
                    
                    # Check for exact match
                    if tag in services and company_name not in seen_companies:
                        seen_companies.add(company_name)
                        
                        result = {
                            "company": company_name,
                            "services": services,
                            "phone": obj.properties.get("office_phone", "") or obj.properties.get("mobile_phone", ""),
                            "phone_e164": obj.properties.get("phone_e164", ""),
                            "email": obj.properties.get("email", []),
                            "email_lower": obj.properties.get("email_lower", []),
                            "entity_uid": obj.properties.get("entity_uid", ""),
                            "hired": obj.properties.get("hired", False),
                            "matched_tag": tag  # Track which tag matched
                        }
                        all_results.append(result)
                        
            except Exception as e:
                logger.error(f"[EXACT TAG SEARCH] Error searching for '{tag}': {e}")
        
        # Sort by hired status (hired companies first)
        all_results.sort(key=lambda x: x.get("hired", False), reverse=True)
        
        logger.info(f"[EXACT TAG SEARCH] Found {len(all_results)} companies for tags: {tags}")
        return all_results
    
    def search_companies_with_filter(self, service: str, limit: int = 1000) -> List[Dict]:
        """Search companies by service using deterministic filters for COMPLETE results"""
        logger.info(f"[FILTER SEARCH - Company] Searching for service: '{service}' in Company collection")
        
        # Build list of variations to search for
        search_terms = [service.lower()]
        
        # Add common variations
        if service.lower() in ['electrical', 'electric']:
            search_terms.extend(['electrical', 'electric', 'electrician'])
        elif service.lower() in ['concrete', 'foundation']:
            search_terms.extend(['concrete', 'foundation', 'concrete & foundation'])
        elif service.lower() in ['glass', 'windows', 'glazing']:
            search_terms.extend(['glass', 'windows', 'glazing', 'windows labor', 'mirrors'])
        elif service.lower() in ['roofing', 'roof']:
            search_terms.extend(['roofing', 'roof', 'roof labor', 'roof material'])
        
        # Remove duplicates
        search_terms = list(set(search_terms))
        logger.info(f"[FILTER SEARCH - Company] Searching for variations: {search_terms}")
        
        all_results = []
        seen_companies = set()
        
        for term in search_terms:
            try:
                # Try case-insensitive contains for each term
                # This ensures we get ALL companies with the service
                response = self.company.query.fetch_objects(
                    limit=limit,
                    return_properties=["company", "services", "office_phone", "mobile_phone", 
                                     "email", "phone_e164", "email_lower", "entity_uid", "hired"]
                )
                
                # Filter results that contain the service term
                for obj in response.objects:
                    company_name = obj.properties.get("company", "")
                    services = obj.properties.get("services", [])
                    
                    # Check if any service matches our search term (case-insensitive)
                    service_match = any(term.lower() in str(svc).lower() for svc in services)
                    
                    if service_match and company_name not in seen_companies:
                        seen_companies.add(company_name)
                        
                        # Include normalized fields for integrations
                        result = {
                            "company": company_name,
                            "services": services,
                            "phone": obj.properties.get("office_phone", "") or obj.properties.get("mobile_phone", ""),
                            "phone_e164": obj.properties.get("phone_e164", ""),
                            "email": obj.properties.get("email", []),
                            "email_lower": obj.properties.get("email_lower", []),
                            "entity_uid": obj.properties.get("entity_uid", ""),
                            "hired": obj.properties.get("hired", False)
                        }
                        all_results.append(result)
                        
            except Exception as e:
                logger.error(f"[FILTER SEARCH - Company] Error searching for '{term}': {e}")
        
        # Sort by hired status (hired companies first)
        all_results.sort(key=lambda x: x.get("hired", False), reverse=True)
        
        logger.info(f"[FILTER SEARCH - Company] Found {len(all_results)} total companies")
        if all_results:
            logger.info(f"[FILTER SEARCH - Company] Sample companies: {[r['company'] for r in all_results[:5]]}")
        
        return all_results
    
    def search_worklogs_by_project(self, project: str, query_text: Optional[str] = None) -> List[Dict]:
        """Search worklogs for a specific project"""
        logger.info(f"[WORKLOG SEARCH] Searching for project: '{project}'")
        try:
            # Map project keywords to full names
            project_map = {
                "regency": "305 Regency Parkway Mansfield, Texas 76063",
                "mitchell": "220 Mitchell",
                "emerald": "Emerald Bay",
                "park place": "Park Place"
            }
            full_project = project_map.get(project.lower(), project)
            logger.info(f"[WORKLOG SEARCH] Mapped project '{project}' to '{full_project}'")
            
            if query_text:
                logger.info(f"[WORKLOG SEARCH] Using HYBRID search with query: '{query_text}'")
                logger.info(f"[WORKLOG SEARCH] Alpha=0.7 (semantic-leaning) for language flexibility")
                # Use hybrid search to semantically understand the query
                # This handles semantic variations like:
                # - "foundation" -> matches "Foundation" in scope
                # - "concrete" -> matches concrete-related work
                # - "electrical" -> matches "Electrical" work
                # No hardcoded service list needed - let semantic search handle it
                # Generate vector for hybrid search since we use custom vectors
                vector = self.generate_embedding(query_text)
                if vector:
                    response = self.worklog.query.hybrid(
                        query=query_text,
                        vector=vector,  # Provide the vector explicitly
                        alpha=0.7,  # Lean semantic to understand variations
                        filters=Filter.by_property("project").equal(full_project),
                        limit=50,
                        return_properties=["company", "project", "scope", "tags", "cost", "status", "rehire", "performance_notes", "knowledge_gained"],
                        return_metadata=MetadataQuery(score=True)
                    )
                else:
                    # Fallback to filter-only if embedding fails
                    logger.warning("[WORKLOG SEARCH] Failed to generate embedding, using filter-only search")
                    response = self.worklog.query.fetch_objects(
                        filters=Filter.by_property("project").equal(full_project),
                        limit=100,
                        return_properties=["company", "project", "scope", "tags", "cost", "status", "rehire", "performance_notes", "knowledge_gained"]
                    )
            else:
                logger.info(f"[WORKLOG SEARCH] Using FILTER-ONLY search (no query text)")
                # Use filter for all contractors on project
                response = self.worklog.query.fetch_objects(
                    filters=Filter.by_property("project").equal(full_project),
                    limit=100,
                    return_properties=["company", "project", "scope", "tags", "cost", "status", "rehire", "performance_notes", "knowledge_gained"]
                )
            
            results = []
            for obj in response.objects:
                result = {
                    "company": obj.properties.get("company", ""),
                    "project": obj.properties.get("project", ""),
                    "scope": obj.properties.get("scope", []),
                    "tags": obj.properties.get("tags", []),
                    "cost": obj.properties.get("cost", ""),
                    "status": obj.properties.get("status", ""),
                    "rehire": obj.properties.get("rehire", ""),
                    "performance_notes": obj.properties.get("performance_notes", []),
                    "knowledge_gained": obj.properties.get("knowledge_gained", "")
                }
                # Add score if available (from hybrid search)
                if hasattr(obj, 'metadata') and hasattr(obj.metadata, 'score'):
                    result["score"] = obj.metadata.score
                results.append(result)
            
            logger.info(f"[WORKLOG SEARCH] Found {len(results)} worklog entries")
            if results and "score" in results[0]:
                scores = [r.get("score", 0) for r in results[:5]]
                logger.info(f"[WORKLOG SEARCH] Top 5 scores: {scores}")
            if results:
                logger.info(f"[WORKLOG SEARCH] Companies found: {[r['company'] for r in results[:3]]}")
            
            return results
        except Exception as e:
            logger.error(f"[WORKLOG SEARCH] FAILED: {e}")
            return []
    
    def search_company_exact(self, company_name: str) -> Optional[Dict]:
        """Find exact company match"""
        logger.info(f"[EXACT SEARCH - Company] Looking for exact match: '{company_name}'")
        try:
            where = Filter.by_property("company").equal(company_name)
            
            response = self.company.query.fetch_objects(
                filters=where,
                limit=1,
                return_properties=["company", "office_phone", "mobile_phone", "email", "services"]
            )
            
            if response.objects:
                obj = response.objects[0]
                result = {
                    "company": obj.properties.get("company", ""),
                    "phone": obj.properties.get("office_phone", "") or obj.properties.get("mobile_phone", ""),
                    "email": obj.properties.get("email", []),
                    "services": obj.properties.get("services", [])
                }
                logger.info(f"[EXACT SEARCH - Company] Found exact match: '{result['company']}'")
                return result
            logger.info(f"[EXACT SEARCH - Company] No exact match found for '{company_name}'")
            return None
        except Exception as e:
            logger.error(f"[EXACT SEARCH - Company] FAILED: {e}")
            return None
    
    def search_hybrid(self, query: str, limit: int = 10) -> List[Dict]:
        """Hybrid search across BOTH Company and WorkLog collections for general queries"""
        # If query looks like a service search, prioritize keyword matches
        # Service queries often contain "labor", "supplier", "contractor", etc.
        service_keywords = ['labor', 'supplier', 'contractor', 'service']
        is_service_query = any(keyword in query.lower() for keyword in service_keywords)
        
        # Use higher alpha (more keyword weight) for service searches
        alpha = 0.7 if is_service_query else 0.3
        
        logger.info(f"[HYBRID SEARCH] Query: '{query}' with alpha={alpha} ({'keyword-focused' if is_service_query else 'balanced'})")
        logger.info(f"[HYBRID SEARCH] Searching both Company and WorkLog collections")
        
        all_results = []
        
        # Search Company collection
        try:
            logger.info(f"[HYBRID SEARCH - Company] Limit: {limit}")
            # Generate vector for hybrid search
            vector = self.generate_embedding(query)
            if vector:
                response = self.company.query.hybrid(
                    query=query,
                    vector=vector,  # Provide the vector explicitly
                    alpha=alpha,  # Use dynamic alpha based on query type
                    limit=limit,
                    return_properties=["company", "services", "office_phone", "mobile_phone", "email"],
                    return_metadata=MetadataQuery(score=True)
                )
            else:
                # Fallback to keyword search if embedding fails
                logger.warning("[COMPANY SEARCH] Failed to generate embedding, using BM25 search")
                response = self.company.query.bm25(
                    query=query,
                    limit=limit,
                    return_properties=["company", "services", "office_phone", "mobile_phone", "email"],
                    return_metadata=MetadataQuery(score=True)
                )
            
            for obj in response.objects:
                result = {
                    "company": obj.properties.get("company", ""),
                    "services": obj.properties.get("services", []),
                    "phone": obj.properties.get("office_phone", "") or obj.properties.get("mobile_phone", ""),
                    "email": obj.properties.get("email", []),
                    "score": obj.metadata.score,
                    "_source": "Company"
                }
                all_results.append(result)
            
            logger.info(f"[HYBRID SEARCH - Company] Found {len(all_results)} results")
        except Exception as e:
            logger.error(f"[HYBRID SEARCH - Company] Error: {e}")
        
        # Also search WorkLog collection for performance notes and project data
        try:
            logger.info(f"[HYBRID SEARCH - WorkLog] Limit: {limit}")
            # Generate vector for hybrid search
            vector = self.generate_embedding(query)
            if vector:
                response = self.worklog.query.hybrid(
                    query=query,
                    vector=vector,  # Provide the vector explicitly
                    alpha=alpha,  # Use dynamic alpha based on query type
                    limit=limit,
                    return_properties=["company", "project", "scope", "tags", "cost", "status", "rehire", "performance_notes", "knowledge_gained"],
                    return_metadata=MetadataQuery(score=True)
                )
            else:
                # Fallback to BM25 if embedding fails
                logger.warning("[WORKLOG SEARCH] Failed to generate embedding, using BM25 search")
                response = self.worklog.query.bm25(
                    query=query,
                    limit=limit,
                    return_properties=["company", "project", "scope", "tags", "cost", "status", "rehire", "performance_notes", "knowledge_gained"],
                    return_metadata=MetadataQuery(score=True)
                )
            
            for obj in response.objects:
                result = {
                    "company": obj.properties.get("company", ""),
                    "project": obj.properties.get("project", ""),
                    "scope": obj.properties.get("scope", []),
                    "cost": obj.properties.get("cost", ""),
                    "status": obj.properties.get("status", ""),
                    "rehire": obj.properties.get("rehire", ""),
                    "performance_notes": obj.properties.get("performance_notes", []),
                    "knowledge_gained": obj.properties.get("knowledge_gained", ""),
                    "score": obj.metadata.score,
                    "_source": "WorkLog"
                }
                
                all_results.append(result)
            
            logger.info(f"[HYBRID SEARCH - WorkLog] Found {len([r for r in all_results if r['_source'] == 'WorkLog'])} results")
        except Exception as e:
            logger.error(f"[HYBRID SEARCH - WorkLog] Error: {e}")
        
        # Merge and deduplicate results, combining data from both sources
        merged_results = {}
        for result in all_results:
            company = result.get("company", "")
            if not company:
                continue
                
            if company not in merged_results:
                merged_results[company] = result
            else:
                # Merge data from both sources - combine fields rather than replacing
                existing = merged_results[company]
                
                # Keep the higher score
                if result["score"] > existing["score"]:
                    existing["score"] = result["score"]
                
                # Merge fields - prefer non-empty values
                for field in ["phone", "email", "services", "project", "scope", "cost", 
                             "status", "rehire", "performance_notes", "knowledge_gained"]:
                    if field in result and result[field]:
                        # If existing doesn't have this field or it's empty, use the new value
                        if field not in existing or not existing[field]:
                            existing[field] = result[field]
                        # For performance_notes, combine them if both exist
                        elif field == "performance_notes" and existing[field] and result[field]:
                            # Combine lists
                            if isinstance(existing[field], list) and isinstance(result[field], list):
                                existing[field] = existing[field] + result[field]
                
                # Track that this has data from multiple sources
                if existing.get("_source") != result.get("_source"):
                    existing["_source"] = "Combined"
        
        # Convert back to list and sort by score
        results = list(merged_results.values())
        results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)[:limit]
        
        logger.info(f"[HYBRID SEARCH] Total merged results: {len(results)}")
        if results:
            scores = [r["score"] for r in results[:3]]
            companies = [r["company"] for r in results[:3]]
            logger.info(f"[HYBRID SEARCH] Top 3 scores: {scores}")
            logger.info(f"[HYBRID SEARCH] Top 3 companies: {companies}")
        
        return results
    
    # Stage 3: Result Validation & Formatting
    def filter_by_score_threshold(self, results: List[Dict], min_score: float = 0.0) -> List[Dict]:
        """Filter results by minimum relevance score"""
        if not results or "score" not in results[0]:
            logger.info("[SCORE FILTER] No scores available - returning all results")
            return results
        
        logger.info(f"[SCORE FILTER] Filtering with minimum score threshold: {min_score}")
        original_count = len(results)
        filtered = [r for r in results if r.get("score", 0) >= min_score]
        
        if len(filtered) < len(results):
            removed_count = original_count - len(filtered)
            logger.info(f"[SCORE FILTER] Removed {removed_count} results below threshold")
            logger.info(f"[SCORE FILTER] Kept {len(filtered)}/{original_count} results")
        else:
            logger.info(f"[SCORE FILTER] All {original_count} results meet threshold")
        
        return filtered
    
    def format_context(self, results: List[Dict], query_type: QueryType) -> str:
        """Format results for LLM response"""
        if not results:
            return "No results found."
        
        # Check for search notes (e.g., when exact match not found)
        search_note = None
        if results and '_search_note' in results[0]:
            search_note = results[0]['_search_note']
            # Remove the note from results before formatting
            for r in results:
                r.pop('_search_note', None)
        
        # Sort by score if available (ensures most relevant first)
        if results and any('score' in r for r in results):
            results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
        
        parts = []
        if search_note:
            parts.append(search_note)
            parts.append("---")
        
        for r in results:
            part = f"Company: {r.get('company', 'Unknown')}"
            
            if r.get('services'):
                part += f"\nServices: {', '.join(r['services'])}"
            
            if r.get('phone'):
                part += f"\nPhone: {r['phone']}"
                # Include normalized phone for integrations if available
                if r.get('phone_e164'):
                    part += f" (Normalized: {r['phone_e164']})"
            
            if r.get('email'):
                emails = r['email'] if isinstance(r['email'], list) else [r['email']]
                part += f"\nEmail: {', '.join(emails)}"
            
            if r.get('project'):
                part += f"\nProject: {r['project']}"
            
            if r.get('scope'):
                part += f"\nScope: {', '.join(r['scope'])}"
            
            if r.get('cost'):
                # Format cost as currency if it's a number
                cost_val = r['cost']
                if isinstance(cost_val, (int, float)):
                    part += f"\nCost: ${cost_val:,.2f}"
                else:
                    part += f"\nCost: ${cost_val}"
            
            if r.get('status'):
                part += f"\nStatus: {r['status']}"
            
            if r.get('rehire'):
                part += f"\nWould rehire: {r['rehire']}"
            
            # Include performance notes if available - more robust handling
            if 'performance_notes' in r and r['performance_notes']:
                notes = r['performance_notes']
                # Handle both list and string formats
                if isinstance(notes, list):
                    # Filter out None and empty strings, but keep all valid notes
                    valid_notes = [str(n).strip() for n in notes if n and str(n).strip()]
                    if valid_notes:
                        part += f"\nPerformance Notes:"
                        for note in valid_notes:
                            part += f"\n  - {note}"
                elif isinstance(notes, str) and notes.strip():
                    part += f"\nPerformance Notes: {notes.strip()}"
            
            # Include knowledge gained if available
            if r.get('knowledge_gained'):
                part += f"\nKnowledge Gained: {r['knowledge_gained']}"
            
            # Always include score if available so LLM can use it for ranking
            if r.get('score'):
                part += f"\n[Relevance Score: {r['score']:.4f}]"
            
            parts.append(part)
        
        return "\n\n---\n\n".join(parts)
    
    # Main search method
    def search(self, query: str, min_score: float = 0.0, max_results: Optional[int] = None, raw_results: bool = False) -> str:
        """Main search orchestrator following 3-stage architecture"""
        logger.info("=" * 60)
        logger.info("=== NEW SEARCH SESSION ===")
        logger.info("=" * 60)
        logger.info(f"[SEARCH] Query: '{query}'")
        logger.info(f"[SEARCH] Parameters: min_score={min_score}, max_results={max_results}")
        
        # Stage 1: Classify and expand
        logger.info("[SEARCH] === STAGE 1: Query Analysis ===")
        query_type, params = self.classify_query(query)
        
        # Stage 2: Execute search based on type
        logger.info("[SEARCH] === STAGE 2: Search Execution ===")
        results = []
        
        if query_type == QueryType.LIST_ALL:
            logger.info("[SEARCH] Executing LIST_ALL strategy with DETERMINISTIC FILTERS")
            service = params.get("service", "")
            if service:
                logger.info(f"[SEARCH] Service term extracted: '{service}'")
                
                # Use deterministic filter search - this returns ALL matching companies
                results = self.search_companies_with_filter(service)
                
                if not results:
                    logger.warning(f"[SEARCH] No companies found with service '{service}'")
                    # Try removing 'supplier' or 'contractor' suffixes
                    if 'supplier' in service.lower():
                        service = service.lower().replace('supplier', '').strip()
                        logger.info(f"[SEARCH] Retrying with cleaned term: '{service}'")
                        results = self.search_companies_with_filter(service)
                    elif 'contractor' in service.lower():
                        service = service.lower().replace('contractor', '').strip()
                        logger.info(f"[SEARCH] Retrying with cleaned term: '{service}'")
                        results = self.search_companies_with_filter(service)
                
                logger.info(f"[SEARCH] COMPLETE results: {len(results)} companies found")
                if results:
                    hired_count = sum(1 for r in results if r.get('hired'))
                    logger.info(f"[SEARCH] Breakdown: {hired_count} hired, {len(results) - hired_count} not hired")
            else:
                logger.warning("[SEARCH] LIST_ALL query but no service term found")
                results = []
        
        elif query_type == QueryType.FIND_BY_PROJECT:
            logger.info("[SEARCH] Executing FIND_BY_PROJECT strategy")
            project = params.get("project")
            
            if project:
                logger.info(f"[SEARCH] Project: '{project}'")
                
                # Search worklogs - pass the full query for semantic understanding
                logger.info("[SEARCH] Step 1: Searching WorkLog collection")
                worklog_results = self.search_worklogs_by_project(project, query)
                
                # Only proceed if we found relevant worklogs
                if worklog_results:
                    logger.info(f"[SEARCH] Found {len(worklog_results)} worklog entries")
                    
                    # Sort WorkLog results by relevance score (highest first)
                    worklog_results = sorted(worklog_results, key=lambda x: x.get("score", 0), reverse=True)
                    logger.info("[SEARCH] Sorted results by relevance score")
                    
                    # Process companies in relevance order (not all companies)
                    logger.info("[SEARCH] Step 2: Enriching with Company collection data")
                    seen_companies = set()
                    for wl_result in worklog_results:
                        company = wl_result.get("company")
                        if company and company not in seen_companies:
                            seen_companies.add(company)
                            logger.info(f"[SEARCH] Looking up company: '{company}'")
                            company_info = self.search_company_exact(company)
                            if company_info:
                                logger.info(f"[SEARCH] ✓ Found company info for '{company}'")
                                # Add scope information from worklog and preserve relevance score
                                company_info["scope"] = wl_result.get("scope", [])
                                company_info["project"] = wl_result.get("project", "")
                                company_info["cost"] = wl_result.get("cost", "")
                                company_info["status"] = wl_result.get("status", "")
                                company_info["rehire"] = wl_result.get("rehire", "")
                                company_info["performance_notes"] = wl_result.get("performance_notes", [])
                                company_info["knowledge_gained"] = wl_result.get("knowledge_gained", "")
                                if "score" in wl_result:
                                    company_info["score"] = wl_result["score"]
                                results.append(company_info)
                            else:
                                # Fallback: Company exists in WorkLog but not in Company collection
                                # This handles cases like "Porter & Bier Concrete" that may only be in WorkLog
                                logger.warning(f"[SEARCH] ⚠️ FALLBACK: Company '{company}' found in WorkLog but not in Company collection")
                                logger.info("[SEARCH] Using WorkLog data only (contact info unavailable)")
                                
                                # No exact match - create result from WorkLog data only with score
                                results.append({
                                    "company": company,
                                    "scope": wl_result.get("scope", []),
                                    "project": wl_result.get("project", ""),
                                    "services": wl_result.get("scope", []),  # Use scope as services fallback
                                    "phone": "(Contact information not available in WorkLog)",
                                    "email": [],
                                    "cost": wl_result.get("cost", ""),
                                    "status": wl_result.get("status", ""),
                                    "rehire": wl_result.get("rehire", ""),
                                    "performance_notes": wl_result.get("performance_notes", []),
                                    "knowledge_gained": wl_result.get("knowledge_gained", ""),
                                    "score": wl_result.get("score", 0)
                                })
                    
                    logger.info(f"[SEARCH] Enrichment complete: {len(results)} final results")
                else:
                    logger.warning(f"[SEARCH] No worklog entries found for project '{project}'")
        
        elif query_type == QueryType.GET_CONTACT:
            logger.info("[SEARCH] Executing GET_CONTACT strategy")
            
            # Check if multiple companies are mentioned (e.g., listing several companies)
            # Look for patterns like "Company1, Company2, Company3" or multiple "&" signs
            company_count = query.count(',') + query.count(' & ') + 1
            if company_count > 3:
                # Adjust limit for multiple companies
                search_limit = min(company_count + 2, 20)  # Cap at 20 for performance
                logger.info(f"[SEARCH] Detected {company_count} possible companies, using limit={search_limit}")
            else:
                search_limit = 3
                
            logger.info("[SEARCH] Using hybrid search to find company")
            results = self.search_hybrid(query, limit=search_limit)
            logger.info(f"[SEARCH] Contact search returned {len(results)} results")
        
        else:  # GENERAL
            logger.info("[SEARCH] Executing GENERAL strategy")
            
            # Try to extract service tags first
            service_tags = self.extract_service_tags(query)
            
            if service_tags:
                logger.info(f"[SEARCH] Extracted service tags: {service_tags}")
                logger.info("[SEARCH] Using exact tag search for complete results")
                results = self.search_companies_by_exact_tags(service_tags)
                logger.info(f"[SEARCH] Exact tag search returned ALL {len(results)} matching companies")
            else:
                # Fallback to hybrid search for non-service queries
                logger.info("[SEARCH] No service tags found, using hybrid search for general query")
                results = self.search_hybrid(query, limit=10)
        
        # Stage 3: Validate and format
        logger.info("[SEARCH] === STAGE 3: Result Validation & Formatting ===")
        
        if not results:
            logger.warning("[SEARCH] NO RESULTS FOUND")
            logger.info("[SEARCH] Returning: 'I couldn't find any relevant information'")
            return "I couldn't find any relevant information for your query."
        
        logger.info(f"[SEARCH] Processing {len(results)} results")
        
        # Apply reranking if available (except for LIST_ALL which should return all)
        if self.voyage_client and results and query_type != QueryType.LIST_ALL:
            logger.info("[SEARCH] === RERANKING WITH VOYAGE AI ===")
            original_count = len(results)
            # Get more results for reranking, then take top
            rerank_k = max_results if max_results else 5
            results = self.rerank_results(query, results, top_k=min(rerank_k * 2, len(results)))
            logger.info(f"[SEARCH] Reranked {original_count} results to top {len(results)}")
        
        # Simple validation for LIST_ALL queries
        if query_type == QueryType.LIST_ALL and len(results) < 2:
            logger.warning(f"[VALIDATION] LIST_ALL query returned only {len(results)} results")
        
        # Apply score filtering if requested
        if min_score > 0:
            logger.info(f"[SEARCH] Applying score filter (min_score={min_score})")
            results = self.filter_by_score_threshold(results, min_score)
            if not results:
                logger.warning("[SEARCH] All results filtered out by score threshold")
                return "No results met the minimum relevance score threshold."
        
        # Limit results if requested - but NEVER for LIST_ALL queries
        if query_type != QueryType.LIST_ALL and max_results and len(results) > max_results:
            logger.info(f"[SEARCH] Limiting results to top {max_results}")
            # Sort by score first if available
            if results and any('score' in r for r in results):
                results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
                logger.info("[SEARCH] Sorted by relevance score before limiting")
            results = results[:max_results]
            logger.info(f"[SEARCH] Limited to {len(results)} results")
        elif query_type == QueryType.LIST_ALL:
            logger.info(f"[SEARCH] LIST_ALL query - returning ALL {len(results)} results without limit")
        
        # Log score information for debugging
        if results and any('score' in r for r in results):
            scores = [r.get("score", 0) for r in results]
            logger.info(f"[SEARCH] === FINAL SCORE SUMMARY ===")
            logger.info(f"[SEARCH] Top score: {scores[0]:.4f}")
            logger.info(f"[SEARCH] Min score: {min(scores):.4f}")
            logger.info(f"[SEARCH] Avg score: {sum(scores)/len(scores):.4f}")
            logger.info(f"[SEARCH] Score distribution: {scores[:5] if len(scores) > 5 else scores}")
        
        # Format context and generate response
        logger.info("[SEARCH] Formatting context for LLM response")
        context = self.format_context(results, query_type)
        
        logger.info("[SEARCH] === SEARCH COMPLETE ===")
        logger.info(f"[SEARCH] Final result count: {len(results)}")
        logger.info(f"[SEARCH] Query type: {query_type.value}")
        
        # If raw_results is True, return formatted context without LLM processing
        if raw_results:
            logger.info("[SEARCH] Returning raw formatted context (no LLM processing)")
            logger.info("=" * 60)
            return context
        
        logger.info("[SEARCH] Generating natural language response...")
        response = self.response_chain.invoke({"context": context, "question": query})
        
        logger.info("[SEARCH] Response generated successfully")
        logger.info("=" * 60)
        
        return response
    
    def __del__(self):
        """Clean up Weaviate connection"""
        if hasattr(self, 'client'):
            self.client.close()