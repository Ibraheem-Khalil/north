import { useState, useEffect, useRef, useCallback } from 'react';

interface SearchProgress {
  stage: 'thinking' | 'searching' | 'verifying' | 'processing' | 'complete';
  message: string;
  timestamp: string;
  details?: any;
}

interface WebSocketMessage {
  type: 'response' | 'search_progress' | 'error';
  text?: string;
  stage?: string;
  message?: string;
  timestamp: string;
  search_history?: SearchProgress[];
  details?: any;
}

export const useWebSocketChat = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [searchProgress, setSearchProgress] = useState<SearchProgress[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const responseCallbackRef = useRef<((response: string) => void) | null>(null);

  useEffect(() => {
    // Get API base URL from environment (fallback to localhost for dev)
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = apiUrl.replace(/^https?:\/\//, '');

    // Get auth token from localStorage if available
    // Token is stored as 'auth_token' by AuthContext
    let token = localStorage.getItem('auth_token') || '';

    // Fallback: check old 'auth' format for backwards compatibility
    if (!token) {
      const authData = localStorage.getItem('auth');
      if (authData) {
        try {
          const parsed = JSON.parse(authData);
          token = parsed.access_token || '';
        } catch (e) {
          console.warn('Failed to parse legacy auth data:', e);
        }
      }
    }

    // Build WebSocket URL with optional token parameter
    let wsUrl = `${wsProtocol}://${wsHost}/ws/chat`;
    if (token) {
      wsUrl += `?token=${encodeURIComponent(token)}`;
    }

    console.log('Connecting to WebSocket:', wsUrl.replace(/token=[^&]+/, 'token=***'));
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        
        if (data.type === 'search_progress') {
          // Add to progress history
          const progress: SearchProgress = {
            stage: data.stage as SearchProgress['stage'],
            message: data.message || '',
            timestamp: data.timestamp,
            details: data.details
          };
          
          setSearchProgress(prev => [...prev, progress]);
          
          // Update searching state
          if (data.stage === 'thinking' || data.stage === 'searching' || data.stage === 'verifying') {
            setIsSearching(true);
          } else if (data.stage === 'complete') {
            setIsSearching(false);
          }
        } else if (data.type === 'response') {
          // Final response received
          setIsSearching(false);
          
          // Add search history if provided
          if (data.search_history) {
            setSearchProgress(data.search_history);
          }
          
          // Call the response callback
          if (responseCallbackRef.current && data.text) {
            responseCallbackRef.current(data.text);
            responseCallbackRef.current = null;
          }
        } else if (data.type === 'error') {
          console.error('WebSocket error:', data.message);
          setIsSearching(false);
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    wsRef.current = ws;

    // Cleanup on unmount
    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, []);

  const sendMessage = useCallback((message: string, onResponse: (response: string) => void) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected');
      onResponse('Error: Not connected to server');
      return;
    }

    // Clear previous progress
    setSearchProgress([]);
    setIsSearching(true);
    
    // Store the callback
    responseCallbackRef.current = onResponse;

    // Send message via WebSocket
    wsRef.current.send(JSON.stringify({ message }));
  }, []);

  const clearProgress = useCallback(() => {
    setSearchProgress([]);
  }, []);

  return {
    isConnected,
    isSearching,
    searchProgress,
    sendMessage,
    clearProgress
  };
};