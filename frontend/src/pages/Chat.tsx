import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, MicOff, Paperclip, Menu, LogOut, Settings, Brain, RefreshCw, Download, Copy, Check, Square, X, FileText, File } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { chatApi, ChatResponse, Conversation, userApi } from '../services/api';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { ChatMessage } from '../components/ChatMessage';
import { SearchProgress } from '../components/SearchProgress';
import { NameModal } from '../components/NameModal';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useWebSocketChat } from '../hooks/useWebSocketChat';
import toast from 'react-hot-toast';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
  attachments?: Array<{
    name: string;
    type: string;
    size: number;
  }>;
}

export const Chat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [conversationId, setConversationId] = useState<string | undefined>();
  
  // WebSocket for real-time search progress
  const { isConnected, isSearching, searchProgress, sendMessage: sendWebSocketMessage, clearProgress } = useWebSocketChat();
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Speech recognition hook
  const { 
    isListening, 
    transcript, 
    isSupported, 
    toggleListening, 
    clearTranscript 
  } = useSpeechRecognition();
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [showNameModal, setShowNameModal] = useState(false);
  const [, setUserName] = useState<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Update input message when speech transcript changes
  useEffect(() => {
    if (transcript) {
      setInputMessage(prev => prev + transcript);
      clearTranscript();
    }
  }, [transcript, clearTranscript]);

  useEffect(() => {
    // Load last conversation from sessionStorage on mount
    const savedConvId = sessionStorage.getItem('currentConversationId');
    if (savedConvId) {
      setConversationId(savedConvId);
    }
    
    // Check if user has a preferred name
    const checkUserName = async () => {
      if (user && messages.length === 0 && !savedConvId) {
        const { preferences } = await userApi.getPreferences();
        
        if (!preferences.preferred_name) {
          // First time user - show modal
          setShowNameModal(true);
        } else {
          // Returning user - use their preferred name with varied greetings
          setUserName(preferences.preferred_name);
          
          const returningUserGreetings = [
            `Welcome back, ${preferences.preferred_name}! How can I help you today?`,
            `Good to see you again, ${preferences.preferred_name}! What's on the agenda?`,
            `Hey ${preferences.preferred_name}! What can I do for you?`,
            `${preferences.preferred_name}, ready to assist! What do you need?`,
            `Back again, ${preferences.preferred_name}? Let's get to work!`,
            `Hi ${preferences.preferred_name}! What project are we tackling today?`,
            `${preferences.preferred_name}! Great to have you back. How can I help?`
          ];
          
          const greeting = returningUserGreetings[Math.floor(Math.random() * returningUserGreetings.length)];
          
          setMessages([
            {
              id: 'welcome',
              content: greeting,
              isUser: false,
              timestamp: new Date(),
            },
          ]);
        }
      }
    };
    
    checkUserName();
  }, [user]);

  // Save conversation ID to sessionStorage when it changes
  useEffect(() => {
    if (conversationId) {
      sessionStorage.setItem('currentConversationId', conversationId);
    }
  }, [conversationId]);

  const handleNameSaved = (name: string) => {
    setUserName(name);
    
    const firstTimeGreetings = [
      `Welcome, ${name}! I'm NORTH, your intelligent assistant for our team. How can I help you today?`,
      `Nice to meet you, ${name}! I'm NORTH, here to help with your construction and project needs.`,
      `Hello ${name}! I'm NORTH, your AI assistant. Ready to help you find contractors, documents, or anything else you need!`,
      `${name}, welcome aboard! I'm NORTH - think of me as your digital assistant for everything we do here.`
    ];
    
    const greeting = firstTimeGreetings[Math.floor(Math.random() * firstTimeGreetings.length)];
    
    setMessages([
      {
        id: 'welcome',
        content: greeting,
        isUser: false,
        timestamp: new Date(),
      },
    ]);
  };

  const handleStopGeneration = () => {
    chatApi.cancelMessage();
    setIsLoading(false);
    toast.success('Generation stopped');
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      content: inputMessage,
      isUser: true,
      timestamp: new Date(),
      attachments: attachedFiles.map(file => ({
        name: file.name,
        type: file.type,
        size: file.size
      }))
    };

    setMessages((prev) => [...prev, userMessage]);
    const sentMessage = inputMessage; // Store for use
    setInputMessage('');
    const sentFiles = [...attachedFiles]; // Keep reference for API call
    setAttachedFiles([]); // Clear attachments after sending
    setIsLoading(true);
    
    // Clear previous search progress
    clearProgress();

    try {
      // Always use WebSocket if connected and no files are attached
      // Let NORTH decide which agent to route to
      if (isConnected && sentFiles.length === 0) {
        // Use WebSocket for real-time progress
        sendWebSocketMessage(sentMessage, (response) => {
          const northMessage: Message = {
            id: `north-${Date.now()}`,
            content: response,
            isUser: false,
            timestamp: new Date()
          };
          setMessages((prev) => [...prev, northMessage]);
          setIsLoading(false);
        });
      } else {
        // Use regular API when files are attached or WebSocket not connected
        const response: ChatResponse = await chatApi.sendMessage(
          sentMessage,
          conversationId,
          sentFiles.length > 0 ? sentFiles : undefined
        );

        if (!conversationId) {
          setConversationId(response.conversation_id);
        }
        
        const aiMessage: Message = {
          id: `ai-${Date.now()}`,
          content: response.response,
          isUser: false,
          timestamp: new Date(response.timestamp),
        };

        setMessages((prev) => [...prev, aiMessage]);
        setIsLoading(false);
        
        // Trigger sidebar refresh
        setRefreshTrigger(prev => prev + 1);
      }
    } catch (error: any) {
      // Don't show error if it was cancelled
      if (error.code !== 'ERR_CANCELED') {
        toast.error('Failed to send message. Please try again.');
        console.error('Chat error:', error);
      }
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Auto-resize textarea
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputMessage(e.target.value);
    
    // Auto-resize
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  };

  // Handle paste event for files
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) {
          files.push(file);
        }
      }
    }
    
    if (files.length > 0) {
      setAttachedFiles(prev => [...prev, ...files]);
      toast.success(`${files.length} file(s) attached!`);
    }
  };

  // Handle drag and drop
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    
    if (files.length > 0) {
      const validFiles: File[] = [];
      const errors: string[] = [];
      
      files.forEach(file => {
        // Check file size
        if (file.size > MAX_FILE_SIZE) {
          errors.push(`${file.name} is too large (max 10MB)`);
          return;
        }
        
        // Check file type
        const fileExtension = file.name.split('.').pop()?.toLowerCase();
        const allowedExtensions = ['md', 'markdown', 'txt', 'json', 'xml', 'html', 'css', 'js', 'py', 'yaml', 'yml', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'];
        
        const isAllowed = ALLOWED_FILE_TYPES.includes(file.type) || 
                         (fileExtension && allowedExtensions.includes(fileExtension));
        
        if (!isAllowed) {
          errors.push(`${file.name} is not a supported file type`);
          return;
        }
        
        validFiles.push(file);
      });
      
      if (validFiles.length > 0) {
        setAttachedFiles(prev => [...prev, ...validFiles]);
        toast.success(`${validFiles.length} file(s) attached!`);
      }
      
      if (errors.length > 0) {
        errors.forEach(error => toast.error(error));
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };
  
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  // Remove attached file
  const removeFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };
  
  // File constraints
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
  const ALLOWED_FILE_TYPES = [
    // Images (supported by vision-capable models)
    'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp',
    
    // Documents (need parsing on backend)
    'application/pdf',
    'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .doc, .docx
    
    // Spreadsheets (need pandas/openpyxl on backend)
    'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xls, .xlsx
    'text/csv',
    
    // Text files (easy to process)
    'text/plain',
    'text/markdown',
    'text/x-markdown',
    'application/json',
    'application/xml',
    'text/xml',
    'text/html',
    'text/css',
    'text/javascript',
    'application/javascript',
    'text/x-python',
    'text/x-yaml',
    'text/yaml'
  ];
  
  // Handle file selection
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const validFiles: File[] = [];
      const errors: string[] = [];
      
      Array.from(files).forEach(file => {
        // Check file size
        if (file.size > MAX_FILE_SIZE) {
          errors.push(`${file.name} is too large (max 10MB)`);
          return;
        }
        
        // Check file type
        const fileExtension = file.name.split('.').pop()?.toLowerCase();
        const allowedExtensions = ['md', 'markdown', 'txt', 'json', 'xml', 'html', 'css', 'js', 'py', 'yaml', 'yml', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'pdf'];
        
        const isAllowed = ALLOWED_FILE_TYPES.includes(file.type) || 
                         (fileExtension && allowedExtensions.includes(fileExtension));
        
        if (!isAllowed) {
          errors.push(`${file.name} is not a supported file type`);
          return;
        }
        
        validFiles.push(file);
      });
      
      if (validFiles.length > 0) {
        setAttachedFiles(prev => [...prev, ...validFiles]);
        toast.success(`${validFiles.length} file(s) attached!`);
      }
      
      if (errors.length > 0) {
        errors.forEach(error => toast.error(error));
      }
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };
  
  // Get file icon based on type
  const getFileIcon = (file: File) => {
    if (file.type.startsWith('image/')) {
      return null; // Will show image preview
    } else if (file.type.includes('pdf')) {
      return <FileText className="w-8 h-8 text-red-500" />;
    } else if (file.type.includes('word') || file.name.endsWith('.doc') || file.name.endsWith('.docx')) {
      return <FileText className="w-8 h-8 text-blue-500" />;
    } else if (file.type.includes('excel') || file.type.includes('spreadsheet') || file.name.endsWith('.xls') || file.name.endsWith('.xlsx')) {
      return <FileText className="w-8 h-8 text-green-500" />;
    } else if (file.type.includes('csv')) {
      return <FileText className="w-8 h-8 text-green-400" />;
    } else {
      return <File className="w-8 h-8 text-gray-500" />;
    }
  };
  
  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return Math.round(bytes / 1024) + ' KB';
    else return Math.round(bytes / 1048576) + ' MB';
  };

  useEffect(() => {
    // Reset textarea height when message is sent
    if (inputRef.current && !inputMessage) {
      inputRef.current.style.height = 'auto';
    }
  }, [inputMessage]);

  const handleCopyMessage = (messageId: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  const handleExportChat = () => {
    const chatContent = messages.map(m => 
      `${m.isUser ? 'You' : 'NORTH'} (${m.timestamp.toLocaleString()}):\n${m.content}\n`
    ).join('\n---\n\n');
    
    const blob = new Blob([chatContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `north-chat-${conversationId || 'new'}-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Chat exported');
  };

  const handleNewChat = () => {
    // Array of varied greetings for new chats
    const newChatGreetings = [
      "What can I help you with today?",
      "How can I assist you?",
      "What's on your mind?",
      "Ready to help! What do you need?",
      "I'm here to help. What are you working on?",
      "What would you like to know?",
      "How can I make your day easier?",
      "What project can I help you with?",
      "Need something? I'm all ears!",
      "What can NORTH do for you today?"
    ];
    
    // Pick a random greeting
    const greeting = newChatGreetings[Math.floor(Math.random() * newChatGreetings.length)];
    
    setMessages([{
      id: 'welcome-new',
      content: greeting,
      isUser: false,
      timestamp: new Date(),
    }]);
    setConversationId(undefined);
    sessionStorage.removeItem('currentConversationId');
    chatApi.clearContext();
    
    // Clear search progress when starting new chat
    clearProgress();
  };

  const handleLoadConversation = useCallback(async (conversation: Conversation) => {
    try {
      // Load all messages from this conversation
      const { conversations } = await chatApi.getConversationMessages(user!.id, conversation.conversation_id);
      
      const loadedMessages: Message[] = [];
      conversations.forEach((conv) => {
        // Add user message
        loadedMessages.push({
          id: `user-${conv.id}-${Date.now()}`,
          content: conv.message,
          isUser: true,
          timestamp: new Date(conv.created_at),
        });
        // Add AI response
        loadedMessages.push({
          id: `ai-${conv.id}-${Date.now()}`,
          content: conv.response,
          isUser: false,
          timestamp: new Date(conv.created_at),
        });
      });
      
      setMessages(loadedMessages);
      setConversationId(conversation.conversation_id);
      sessionStorage.setItem('currentConversationId', conversation.conversation_id);
      
      // Clear context and set it for this conversation
      await chatApi.clearContext();
    } catch (error) {
      toast.error('Failed to load conversation');
      console.error('Load conversation error:', error);
    }
  }, [user]);

  return (
    <>
      {/* Name Modal for first-time users */}
      <NameModal 
        isOpen={showNameModal}
        onClose={() => setShowNameModal(false)}
        onNameSaved={handleNameSaved}
      />
      
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <ConversationSidebar 
        isOpen={isSidebarOpen}
        onNewChat={handleNewChat}
        currentConversationId={conversationId}
        onSelectConversation={handleLoadConversation}
        refreshTrigger={refreshTrigger}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-[61px] bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 flex items-center">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <Menu className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
                  <Brain className="w-5 h-5 text-white" />
                </div>
                <h1 className="text-xl font-semibold text-gray-900 dark:text-white">NORTH AI</h1>
              </div>
            </div>
            
            <div className="flex items-center space-x-2">
              {messages.length > 1 && (
                <button
                  onClick={handleExportChat}
                  className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                  title="Export Chat"
                >
                  <Download className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                </button>
              )}
              <button
                onClick={() => chatApi.clearContext()}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Clear Context"
              >
                <RefreshCw className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
              <button 
                onClick={() => navigate('/settings')}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Settings"
              >
                <Settings className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
              <button
                onClick={signOut}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
            </div>
          </div>
        </header>

        {/* Messages Area with drag indicator */}
        <div 
          className={`flex-1 overflow-y-auto px-4 py-6 relative transition-all ${
            isDragging ? 'bg-blue-50 dark:bg-blue-900/20 border-2 border-dashed border-blue-400 dark:border-blue-600' : ''
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          {/* Drag indicator overlay */}
          {isDragging && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-8 border-2 border-blue-500">
                <div className="flex flex-col items-center space-y-3">
                  <Paperclip className="w-12 h-12 text-blue-500 animate-bounce" />
                  <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">Drop your files here</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Images, PDFs, documents, and more</p>
                </div>
              </div>
            </div>
          )}
          
          <div className="max-w-3xl mx-auto space-y-4">
            {/* Show search progress if there's activity */}
            {(searchProgress.length > 0 || isSearching) && (
              <SearchProgress 
                progress={searchProgress} 
                isSearching={isSearching} 
              />
            )}
            
            {messages.map((message) => (
              <div key={message.id} className="group relative">
                <ChatMessage message={message} />
                {/* Copy button for messages */}
                <button
                  onClick={() => handleCopyMessage(message.id, message.content)}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 bg-white/80 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-700 rounded shadow-sm"
                  title="Copy message"
                >
                  {copiedMessageId === message.id ? (
                    <Check className="w-4 h-4 text-green-600" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  )}
                </button>
              </div>
            ))}
            {isLoading && (
              <div className="flex items-center justify-between bg-gray-100 dark:bg-gray-800 rounded-lg p-4">
                <div className="flex items-center space-x-2 text-gray-500 dark:text-gray-400">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-sm">NORTH is thinking...</span>
                </div>
                <button
                  onClick={handleStopGeneration}
                  className="flex items-center space-x-1 px-3 py-1 bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  <Square className="w-3 h-3" />
                  <span>Stop</span>
                </button>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area - matching sidebar footer height */}
        <div className={`${attachedFiles.length > 0 ? 'min-h-[88px]' : 'h-[88px]'} bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-4 py-3 transition-all`}>
          <div className="max-w-3xl mx-auto w-full">
            {/* File previews */}
            {attachedFiles.length > 0 && (
              <div className="flex gap-2 mb-3 p-2 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
                {attachedFiles.map((file, index) => {
                  const icon = getFileIcon(file);
                  return (
                    <div key={index} className="relative group">
                      {file.type.startsWith('image/') ? (
                        <img 
                          src={URL.createObjectURL(file)} 
                          alt={file.name}
                          className="h-16 w-16 object-cover rounded-lg border border-gray-300 dark:border-gray-600"
                        />
                      ) : (
                        <div className="h-16 w-20 bg-gray-100 dark:bg-gray-700 rounded-lg border border-gray-300 dark:border-gray-600 flex flex-col items-center justify-center p-1">
                          {icon}
                          <span className="text-[10px] text-gray-600 dark:text-gray-400 truncate w-full text-center">
                            {file.name.split('.').pop()?.toUpperCase()}
                          </span>
                        </div>
                      )}
                      <button
                        onClick={() => removeFile(index)}
                        className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X className="w-3 h-3" />
                      </button>
                      {/* File info tooltip */}
                      <div className="absolute bottom-0 left-0 right-0 bg-black/75 text-white text-[10px] p-1 rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                        <p className="truncate">{file.name}</p>
                        <p>{formatFileSize(file.size)}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            
            <div className="flex items-end space-x-2">
              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.csv,.md,.json,.xml,.html,.css,.js,.py,.yaml,.yml"
              />
              
              <button 
                onClick={() => fileInputRef.current?.click()}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors self-end"
                title="Attach files"
              >
                <Paperclip className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
              
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={inputMessage}
                  onChange={handleTextareaChange}
                  onKeyDown={handleKeyPress}
                  onPaste={handlePaste}
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  placeholder={isListening ? "Listening... Speak now" : "Type a message, attach files, or drag & drop..."}
                  disabled={isLoading}
                  rows={1}
                  className={`w-full px-4 py-2 border dark:bg-gray-700 dark:text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 dark:disabled:bg-gray-800 disabled:text-gray-500 resize-none overflow-y-auto ${
                    isListening ? 'border-red-400 ring-2 ring-red-200' : 'border-gray-300 dark:border-gray-600'
                  }`}
                  style={{ minHeight: '40px', maxHeight: '120px' }}
                />
                {isListening && (
                  <div className="absolute top-2 right-2 flex items-center space-x-2">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-red-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-red-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-red-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-xs text-red-500 font-medium">Recording</span>
                  </div>
                )}
              </div>

              <button 
                onClick={toggleListening}
                disabled={!isSupported}
                className={`p-2 rounded-lg transition-all self-end ${
                  isListening 
                    ? 'bg-red-500 hover:bg-red-600 animate-pulse' 
                    : 'hover:bg-gray-100 dark:hover:bg-gray-700'
                } ${!isSupported ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={
                  !isSupported 
                    ? 'Speech recognition not supported in this browser' 
                    : isListening 
                    ? 'Stop recording' 
                    : 'Start voice input'
                }
              >
                {isListening ? (
                  <MicOff className="w-5 h-5 text-white" />
                ) : (
                  <Mic className={`w-5 h-5 ${isSupported ? 'text-gray-600 dark:text-gray-400' : 'text-gray-400'}`} />
                )}
              </button>

              <button
                onClick={handleSendMessage}
                disabled={!inputMessage.trim() || isLoading}
                className="p-2 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-lg hover:from-blue-600 hover:to-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed self-end"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    </>
  );
};
