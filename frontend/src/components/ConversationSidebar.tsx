import React, { useEffect, useState } from 'react';
import { Plus, MessageSquare, Calendar, Trash2, AlertCircle } from 'lucide-react';
import { chatApi, Conversation } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { format, isToday, isYesterday } from 'date-fns';
import toast from 'react-hot-toast';

interface ConversationSidebarProps {
  isOpen: boolean;
  onNewChat: () => void;
  currentConversationId?: string;
  onSelectConversation: (conversation: Conversation) => void;
  refreshTrigger?: number;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({ 
  isOpen, 
  onNewChat,
  currentConversationId,
  onSelectConversation,
  refreshTrigger 
}) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hoveredConv, setHoveredConv] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const { user } = useAuth();

  useEffect(() => {
    if (user) {
      loadConversations();
    }
  }, [user, refreshTrigger]);

  const handleDeleteConversation = async (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    
    if (deleteConfirm !== conv.conversation_id) {
      setDeleteConfirm(conv.conversation_id);
      // Auto-cancel after 3 seconds
      setTimeout(() => setDeleteConfirm(null), 3000);
      return;
    }
    
    try {
      await chatApi.deleteConversation(user!.id, conv.conversation_id);
      toast.success('Conversation deleted');
      
      // If we deleted the current conversation, start a new chat
      if (conv.conversation_id === currentConversationId) {
        onNewChat();
      }
      
      // Reload conversations
      loadConversations();
      setDeleteConfirm(null);
    } catch (error) {
      toast.error('Failed to delete conversation');
      console.error('Delete error:', error);
    }
  };

  const loadConversations = async () => {
    if (!user) return;
    
    setIsLoading(true);
    try {
      const { conversations } = await chatApi.getConversations(user.id);
      
      // Group conversations by conversation_id and take the latest from each
      const groupedConvs = conversations.reduce((acc, conv) => {
        if (!acc[conv.conversation_id] || new Date(conv.created_at) > new Date(acc[conv.conversation_id].created_at)) {
          acc[conv.conversation_id] = conv;
        }
        return acc;
      }, {} as Record<string, Conversation>);
      
      const uniqueConversations = Object.values(groupedConvs).sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      
      setConversations(uniqueConversations);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const formatConversationDate = (dateString: string) => {
    const date = new Date(dateString);
    
    if (isToday(date)) {
      return 'Today';
    } else if (isYesterday(date)) {
      return 'Yesterday';
    } else {
      return format(date, 'MMM d');
    }
  };

  const groupConversationsByDate = () => {
    const groups: { [key: string]: Conversation[] } = {};
    
    conversations.forEach((conv) => {
      const dateKey = formatConversationDate(conv.created_at);
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(conv);
    });
    
    return groups;
  };

  if (!isOpen) return null;

  const groupedConversations = groupConversationsByDate();

  return (
    <div className="w-64 bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-white flex flex-col h-full transition-colors border-r border-gray-200 dark:border-gray-700">
      {/* Header - matching main header height */}
      <div className="h-[61px] flex items-center px-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center space-x-2 bg-gray-800 dark:bg-white/10 hover:bg-gray-700 dark:hover:bg-white/20 text-white font-medium py-2 px-4 rounded-lg transition-colors"
        >
          <Plus className="w-5 h-5" />
          <span>New Chat</span>
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-center text-gray-400">
            Loading conversations...
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-4 text-center text-gray-400">
            <MessageSquare className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No conversations yet</p>
            <p className="text-xs mt-1">Start a new chat to begin</p>
          </div>
        ) : (
          <div className="p-2">
            {Object.entries(groupedConversations).map(([date, convs]) => (
              <div key={date} className="mb-4">
                <div className="flex items-center space-x-2 px-2 py-1">
                  <Calendar className="w-3 h-3 text-gray-600 dark:text-gray-500" />
                  <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                    {date}
                  </h3>
                </div>
                
                {convs.map((conv) => (
                  <div
                    key={conv.id}
                    className="relative group mb-1"
                    onMouseEnter={() => setHoveredConv(conv.conversation_id)}
                    onMouseLeave={() => setHoveredConv(null)}
                  >
                    <button
                      onClick={() => onSelectConversation(conv)}
                      className={`w-full text-left p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-white/10 transition-colors ${
                        conv.conversation_id === currentConversationId ? 'bg-gray-200 dark:bg-white/10' : ''
                      }`}
                    >
                      <div className="flex items-start space-x-2">
                        <MessageSquare className="w-4 h-4 text-gray-500 dark:text-gray-400 mt-0.5 flex-shrink-0" />
                        <div className="flex-1 min-w-0 pr-6">
                          <p className="text-sm text-gray-800 dark:text-white truncate">
                            {conv.message}
                          </p>
                          <p className="text-xs text-gray-600 dark:text-gray-500 truncate mt-1">
                            {conv.response.substring(0, 50)}...
                          </p>
                        </div>
                      </div>
                    </button>
                    
                    {/* Delete button */}
                    {(hoveredConv === conv.conversation_id || deleteConfirm === conv.conversation_id) && (
                      <button
                        onClick={(e) => handleDeleteConversation(e, conv)}
                        className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded transition-all ${
                          deleteConfirm === conv.conversation_id
                            ? 'bg-red-600 hover:bg-red-700'
                            : 'hover:bg-gray-300 dark:hover:bg-white/20'
                        }`}
                        title={deleteConfirm === conv.conversation_id ? 'Click again to confirm' : 'Delete conversation'}
                      >
                        {deleteConfirm === conv.conversation_id ? (
                          <AlertCircle className="w-4 h-4 text-white" />
                        ) : (
                          <Trash2 className="w-4 h-4 text-gray-500 dark:text-gray-400 hover:text-red-400 dark:hover:text-red-400" />
                        )}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* User Info - matching input area height */}
      <div className="h-[88px] border-t border-gray-200 dark:border-gray-700 px-4 flex items-center">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg flex items-center justify-center">
            <span className="text-white font-medium text-sm">
              {user?.email?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate text-gray-800 dark:text-white">{user?.full_name || user?.email}</p>
            <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{user?.email}</p>
          </div>
        </div>
      </div>
    </div>
  );
};