import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : '/api';

// Create axios instance with defaults
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
      // Only redirect if not on login or reset password pages
      const path = window.location.pathname;
      if (!path.includes('/login') && !path.includes('/reset-password')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export interface User {
  id: string;
  email: string;
  full_name?: string;
  preferred_name?: string;
}

export interface UserPreferences {
  preferred_name?: string;
  theme?: 'light' | 'dark';
  notifications?: boolean;
  [key: string]: any;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  user: User;
}

export interface ChatMessage {
  message: string;
  conversation_id?: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  timestamp: string;
  metadata?: any;
}

export interface Conversation {
  id: string;
  user_id: string;
  conversation_id: string;
  message: string;
  response: string;
  created_at: string;
}

// Auth API
export const authApi = {
  signUp: async (email: string, password: string, full_name?: string): Promise<AuthResponse> => {
    const response = await api.post('/auth/signup', { email, password, full_name });
    return response.data;
  },

  signIn: async (email: string, password: string): Promise<AuthResponse> => {
    const response = await api.post('/auth/signin', { email, password });
    return response.data;
  },

  signOut: async (): Promise<void> => {
    await api.post('/auth/signout');
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
  },

  getCurrentUser: async (): Promise<{ user: User }> => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  resetPassword: async (email: string): Promise<{ message: string }> => {
    const response = await api.post('/auth/reset-password', { email });
    return response.data;
  },
};

// Chat API
let currentAbortController: AbortController | null = null;

export const chatApi = {
  sendMessage: async (message: string, conversationId?: string, files?: File[]): Promise<ChatResponse> => {
    // Cancel any existing request
    if (currentAbortController) {
      currentAbortController.abort();
    }
    
    // Create new abort controller for this request
    currentAbortController = new AbortController();
    
    try {
      let response;
      
      // If files are attached, use multipart form data
      if (files && files.length > 0) {
        const formData = new FormData();
        formData.append('message', message);
        if (conversationId) {
          formData.append('conversation_id', conversationId);
        }
        
        // Append each file
        files.forEach(file => {
          formData.append('files', file);
        });
        
        response = await api.post('/chat/with-files', formData, {
          signal: currentAbortController.signal,
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });
      } else {
        // Regular text-only message
        response = await api.post('/chat', { 
          message, 
          conversation_id: conversationId 
        }, {
          signal: currentAbortController.signal
        });
      }
      
      currentAbortController = null;
      return response.data;
    } catch (error) {
      currentAbortController = null;
      throw error;
    }
  },
  
  cancelMessage: () => {
    if (currentAbortController) {
      currentAbortController.abort();
      currentAbortController = null;
    }
  },

  getConversations: async (userId: string, limit = 50): Promise<{ conversations: Conversation[] }> => {
    const response = await api.get(`/conversations/${userId}`, { 
      params: { limit } 
    });
    return response.data;
  },

  getConversationMessages: async (userId: string, conversationId: string): Promise<{ conversations: Conversation[] }> => {
    const response = await api.get(`/conversations/${userId}/${conversationId}`);
    return response.data;
  },

  deleteConversation: async (userId: string, conversationId: string): Promise<{ success: boolean; deleted_count: number }> => {
    const response = await api.delete(`/conversations/${userId}/${conversationId}`);
    return response.data;
  },

  clearContext: async (): Promise<void> => {
    await api.post('/clear-context');
  },
};

// User API
export const userApi = {
  getPreferences: async (): Promise<{ preferences: UserPreferences }> => {
    const response = await api.get('/user/preferences');
    return response.data;
  },

  updatePreferences: async (preferences: UserPreferences): Promise<{ success: boolean; preferences: UserPreferences }> => {
    const response = await api.post('/user/preferences', preferences);
    return response.data;
  },
};

// System API
export const systemApi = {
  getStatus: async () => {
    const response = await api.get('/status');
    return response.data;
  },

  healthCheck: async () => {
    const response = await api.get('/health');
    return response.data;
  },
};

export default api;