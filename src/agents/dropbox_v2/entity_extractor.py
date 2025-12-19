"""
Entity Extractor for Dropbox Search
Uses LLM with structured output to dynamically extract entities
No hardcoding - learns from context and data
"""

import json
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class SearchEntities(BaseModel):
    """Structured output schema for entity extraction"""
    project: Optional[str] = Field(None, description="Project name or identifier")
    contractor: Optional[str] = Field(None, description="Contractor or vendor name")
    document_type: Optional[str] = Field(None, description="Type of document (invoice, contract, etc)")
    keywords: List[str] = Field(default_factory=list, description="Additional search keywords")
    date_range: Optional[Dict[str, str]] = Field(None, description="Date range if specified")
    amount_range: Optional[Dict[str, float]] = Field(None, description="Amount range if specified")
    specific_file: Optional[str] = Field(None, description="Specific filename if mentioned")


class DropboxEntityExtractor:
    """
    Extracts structured entities from natural language queries
    Uses GPT-4o-mini with structured output for consistent JSON responses
    """
    
    def __init__(self):
        """Initialize the entity extractor with structured output"""
        # Use GPT-4o-mini for cost-effective extraction
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,  # Low temperature for consistent extraction
            timeout=20
        ).with_structured_output(SearchEntities)
        
        # System prompt with construction domain context
        self.system_prompt = """You are an entity extraction specialist for a construction company's document search system.
        
Your task is to extract structured information from user queries about documents.

Important guidelines:
1. Extract entities as they appear in the query - don't assume or expand names unless obvious
2. For ambiguous terms, extract them as-is (e.g., "Geotech" stays "Geotech", not expanded)
3. Document types should be normalized to base forms (invoice, contract, report, etc.)
4. Include any specific details mentioned (dates, amounts, invoice numbers)
5. If the query references "that document" or "it", mark it as a reference to context

Examples to guide you:
- "Find the Geotech invoice for Mitchell" -> 
  {project: "Mitchell", contractor: "Geotech", document_type: "invoice"}
  
- "Show me all contracts over $50k from last month" ->
  {document_type: "contract", amount_range: {min: 50000}, date_range: {from: "last month"}}
  
- "Where is the signed painter agreement for 305 Regency?" ->
  {project: "305 Regency", contractor: "painter", document_type: "agreement", keywords: ["signed"]}

Remember: Extract what's there, don't invent or assume."""
        
        logger.info("DropboxEntityExtractor initialized with structured output")
    
    def extract(self, query: str, context: Optional[Dict] = None) -> SearchEntities:
        """
        Extract entities from a user query
        
        Args:
            query: Natural language query from user
            context: Optional context about previous searches or current document
            
        Returns:
            SearchEntities object with extracted information
        """
        try:
            # Build the messages
            messages = [SystemMessage(content=self.system_prompt)]
            
            # Add context if provided (for follow-up queries)
            if context:
                context_msg = f"\nContext from previous interaction:\n"
                if context.get('last_document'):
                    context_msg += f"Last document found: {context['last_document']}\n"
                if context.get('last_search'):
                    context_msg += f"Last search: {context['last_search']}\n"
                
                messages[0].content += context_msg
            
            # Add the user query
            messages.append(HumanMessage(content=query))
            
            # Get structured extraction
            entities = self.llm.invoke(messages)
            
            logger.info(f"Extracted entities: {entities.model_dump_json()}")
            return entities
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            # Return empty entities on failure
            return SearchEntities()
    
    def extract_with_examples(self, query: str, discovered_entities: Optional[Dict] = None) -> SearchEntities:
        """
        Enhanced extraction that can use discovered entities from the actual data
        
        Args:
            query: User query
            discovered_entities: Entities discovered from folder structure or previous searches
            
        Returns:
            SearchEntities with extraction
        """
        try:
            # Build enhanced prompt with discovered context
            enhanced_prompt = self.system_prompt
            
            if discovered_entities:
                enhanced_prompt += "\n\nDiscovered entities from the system:\n"
                
                if discovered_entities.get('projects'):
                    enhanced_prompt += f"Known projects: {', '.join(discovered_entities['projects'][:10])}\n"
                
                if discovered_entities.get('contractors'):
                    enhanced_prompt += f"Known contractors: {', '.join(discovered_entities['contractors'][:10])}\n"
                
                enhanced_prompt += "\nUse these as hints but don't force matches - extract what the user actually said."
            
            messages = [
                SystemMessage(content=enhanced_prompt),
                HumanMessage(content=query)
            ]
            
            entities = self.llm.invoke(messages)
            return entities
            
        except Exception as e:
            logger.error(f"Enhanced extraction failed: {e}")
            return SearchEntities()
    
    def refine_with_feedback(self, query: str, entities: SearchEntities, 
                            no_results: bool = False) -> SearchEntities:
        """
        Refine extraction if initial search yielded no results
        Might expand abbreviations or suggest alternatives
        
        Args:
            query: Original query
            entities: Initial extraction
            no_results: Whether the search found nothing
            
        Returns:
            Refined SearchEntities
        """
        if not no_results:
            return entities
        
        try:
            refine_prompt = """The initial search found no results. Please re-extract with these considerations:
1. Expand any abbreviations that might be too specific
2. Consider alternative phrasings or synonyms
3. Try broader terms if the initial extraction was too narrow
4. Keep the core intent but be more flexible

Original extraction: {entities}
User query: {query}

Provide a refined extraction that might yield better results."""
            
            messages = [
                SystemMessage(content=refine_prompt.format(
                    entities=entities.model_dump_json(),
                    query=query
                )),
                HumanMessage(content="Refine the extraction for better search results")
            ]
            
            refined = self.llm.invoke(messages)
            logger.info(f"Refined entities: {refined.model_dump_json()}")
            return refined
            
        except Exception as e:
            logger.error(f"Refinement failed: {e}")
            return entities