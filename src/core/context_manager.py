"""
Dirt simple context management - let the LLM do the work
"""
from collections import deque
from typing import Dict, Any, List, Optional

class ContextManager:
    def __init__(self, history_size: int = 10):
        self.history = deque(maxlen=history_size)  # Last 10 messages (5 exchanges)
        self.cache = {}  # Simple cache for repeated queries
        
    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        
    def add_exchange(self, query: str, response: str, entities: Optional[Dict[str, Any]] = None):
        # Compatibility method - entities ignored since LLM handles context
        self.add_message("user", query)
        self.add_message("assistant", response)
        
    def get_messages(self) -> List[Dict[str, str]]:
        return list(self.history)
        
    def get_context_for_llm(self) -> str:
        # Format history as string for LLM context
        if not self.history:
            return ""
        context_parts = []
        for msg in self.history:
            role_label = "User" if msg["role"] == "user" else "NORTH"
            context_parts.append(f"{role_label}: {msg['content']}")
        return "\n\n".join(context_parts)
    
    def resolve_pronouns(self, user_text: str) -> str:
        # No longer needed - LLM handles this naturally
        return user_text
    
    def can_answer_from_context(self, query: str) -> Optional[str]:
        # Simple cache check for repeated queries
        return self.cache.get(query.lower())
        
    def cache_result(self, key: str, value: Any):
        self.cache[key] = value
        if isinstance(key, str) and isinstance(value, str):
            self.cache[key.lower()] = value
        
    def clear(self):
        self.history.clear()
        self.cache.clear()
        
    def get_context_for_search(self) -> Dict[str, Any]:
        # No longer needed - LLM provides complete queries
        return {}