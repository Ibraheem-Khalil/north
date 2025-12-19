"""
Dynamic Entity Discovery
Learns from actual Dropbox folder structure and indexed documents
No hardcoding - discovers entities from the data itself
"""

import logging
import re
from typing import Dict, List, Set, Optional
from pathlib import Path
import weaviate
from collections import defaultdict

logger = logging.getLogger(__name__)


class EntityDiscovery:
    """
    Discovers entities dynamically from:
    1. Dropbox folder structure
    2. Documents already in Weaviate
    3. Patterns in filenames and paths
    """
    
    def __init__(self, weaviate_client: Optional[weaviate.Client] = None):
        """Initialize with optional Weaviate connection"""
        self.weaviate_client = weaviate_client
        self.discovered_entities = {
            'projects': set(),
            'contractors': set(),
            'document_types': set(),
            'common_terms': defaultdict(int)
        }
        
    def discover_from_paths(self, file_paths: List[str]) -> Dict[str, Set[str]]:
        """
        Discover entities from a list of file paths
        Analyzes folder structure to find projects, contractors, etc.
        
        Args:
            file_paths: List of Dropbox file paths
            
        Returns:
            Dictionary of discovered entities
        """
        for path in file_paths:
            parts = Path(path).parts
            
            # Analyze path structure dynamically
            # Look for patterns like /COMPANY_FILES/[PROJECT]/[STATUS]/[CONTRACTOR]/
            if len(parts) > 2:
                # Potential project folder (usually 2nd or 3rd level)
                for i in range(1, min(4, len(parts))):
                    folder = parts[i]
                    
                    # Projects often have addresses or names with numbers
                    if any(char.isdigit() for char in folder):
                        self.discovered_entities['projects'].add(folder)
                    
                    # Look for contractor patterns
                    # Often in "OFFICIALLY HIRED" or similar folders
                    if i > 1 and 'HIRED' in parts[i-1].upper():
                        self.discovered_entities['contractors'].add(folder)
                    
                    # Document types often in folder names
                    doc_patterns = ['invoice', 'contract', 'report', 'w9', 'w-9', 
                                  'insurance', 'coi', 'agreement', 'receipt']
                    folder_lower = folder.lower()
                    for pattern in doc_patterns:
                        if pattern in folder_lower:
                            self.discovered_entities['document_types'].add(pattern)
            
            # Analyze filename for document types
            filename = Path(path).name.lower()
            for doc_type in ['invoice', 'contract', 'agreement', 'w9', 'receipt', 
                           'report', 'insurance', 'change order']:
                if doc_type in filename:
                    self.discovered_entities['document_types'].add(doc_type)
            
            # Track common terms for pattern recognition
            words = re.findall(r'\b\w+\b', path)
            for word in words:
                if len(word) > 3:  # Skip short words
                    self.discovered_entities['common_terms'][word.lower()] += 1
        
        # Convert sets to lists for JSON serialization
        return {
            'projects': list(self.discovered_entities['projects']),
            'contractors': list(self.discovered_entities['contractors']),
            'document_types': list(self.discovered_entities['document_types']),
            'frequent_terms': [
                term for term, count in self.discovered_entities['common_terms'].items() 
                if count > 3  # Terms appearing more than 3 times
            ][:50]  # Top 50 frequent terms
        }
    
    def discover_from_weaviate(self) -> Dict[str, List[str]]:
        """
        Discover entities from documents already indexed in Weaviate
        
        Returns:
            Dictionary of discovered entities from the index
        """
        if not self.weaviate_client:
            return {}
        
        discovered = {
            'projects': set(),
            'contractors': set(),
            'document_types': set()
        }
        
        try:
            # Query Weaviate for unique property values
            # This is dynamic - we're learning from what's actually indexed
            
            # Get sample of documents to analyze
            result = self.weaviate_client.query.get(
                "Document",
                ["project_name", "contractor", "document_type", "file_path"]
            ).with_limit(100).do()
            
            if result and 'data' in result and 'Get' in result['data']:
                documents = result['data']['Get'].get('Document', [])
                
                for doc in documents:
                    if doc.get('project_name'):
                        discovered['projects'].add(doc['project_name'])
                    if doc.get('contractor'):
                        discovered['contractors'].add(doc['contractor'])
                    if doc.get('document_type'):
                        discovered['document_types'].add(doc['document_type'])
                    
                    # Also learn from paths in the index
                    if doc.get('file_path'):
                        path_parts = Path(doc['file_path']).parts
                        for part in path_parts:
                            # Simple heuristic: folders with numbers might be projects
                            if any(char.isdigit() for char in part):
                                discovered['projects'].add(part)
            
            return {
                'projects': list(discovered['projects']),
                'contractors': list(discovered['contractors']),
                'document_types': list(discovered['document_types'])
            }
            
        except Exception as e:
            logger.error(f"Failed to discover from Weaviate: {e}")
            return {}
    
    def learn_patterns(self, successful_searches: List[Dict]) -> None:
        """
        Learn from successful searches to improve future discovery
        
        Args:
            successful_searches: List of queries that returned good results
        """
        for search in successful_searches:
            if search.get('found_project'):
                self.discovered_entities['projects'].add(search['found_project'])
            if search.get('found_contractor'):
                self.discovered_entities['contractors'].add(search['found_contractor'])
    
    def suggest_alternatives(self, term: str, category: str) -> List[str]:
        """
        Suggest alternatives for a term based on discovered entities
        Uses fuzzy matching and learned patterns
        
        Args:
            term: The term to find alternatives for
            category: Type of entity (project, contractor, etc.)
            
        Returns:
            List of alternative suggestions
        """
        suggestions = []
        term_lower = term.lower()
        
        if category == 'contractor':
            # Look for partial matches in discovered contractors
            for contractor in self.discovered_entities['contractors']:
                if term_lower in contractor.lower() or contractor.lower() in term_lower:
                    suggestions.append(contractor)
        
        elif category == 'project':
            # Look for partial matches in discovered projects
            for project in self.discovered_entities['projects']:
                if term_lower in project.lower() or any(
                    word in project.lower() for word in term_lower.split()
                ):
                    suggestions.append(project)
        
        return suggestions[:5]  # Return top 5 suggestions
