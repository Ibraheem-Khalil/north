import React from 'react';
import { User, Bot, FileText, File, Image } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { format } from 'date-fns';

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

interface ChatMessageProps {
  message: Message;
}

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B';
  else if (bytes < 1048576) return Math.round(bytes / 1024) + ' KB';
  else return Math.round(bytes / 1048576) + ' MB';
};

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  return (
    <div className={`flex ${message.isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[80%] ${message.isUser ? 'flex-row-reverse' : 'flex-row'} space-x-2`}>
        {/* Avatar */}
        <div className={`flex-shrink-0 ${message.isUser ? 'ml-2' : 'mr-2'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
            message.isUser 
              ? 'bg-gradient-to-br from-green-500 to-emerald-600' 
              : 'bg-gradient-to-br from-blue-500 to-indigo-600'
          }`}>
            {message.isUser ? (
              <User className="w-5 h-5 text-white" />
            ) : (
              <Bot className="w-5 h-5 text-white" />
            )}
          </div>
        </div>

        {/* Message Content */}
        <div className="flex flex-col">
          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className={`flex flex-wrap gap-2 mb-2 ${message.isUser ? 'justify-end' : 'justify-start'}`}>
              {message.attachments.map((attachment, index) => (
                <div 
                  key={index} 
                  className="flex items-center space-x-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-700 rounded-lg border border-gray-300 dark:border-gray-600"
                >
                  {attachment.type.startsWith('image/') ? (
                    <Image className="w-4 h-4 text-blue-500" />
                  ) : attachment.type.includes('pdf') ? (
                    <FileText className="w-4 h-4 text-red-500" />
                  ) : (
                    <File className="w-4 h-4 text-gray-500" />
                  )}
                  <span className="text-xs text-gray-600 dark:text-gray-400 truncate max-w-[150px]">
                    {attachment.name}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-500">
                    ({formatFileSize(attachment.size)})
                  </span>
                </div>
              ))}
            </div>
          )}
          
          {/* Message text */}
          <div className={`px-4 py-2 rounded-lg ${
            message.isUser 
              ? 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white' 
              : 'bg-white border border-gray-200 text-gray-900'
          }`}>
            {message.isUser ? (
              <p className="whitespace-pre-wrap break-words">{message.content}</p>
            ) : (
              <div className="prose prose-sm max-w-none break-words overflow-hidden">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
          </div>
          
          {/* Timestamp */}
          <span className={`text-xs text-gray-500 mt-1 ${
            message.isUser ? 'text-right' : 'text-left'
          }`}>
            {format(message.timestamp, 'h:mm a')}
          </span>
        </div>
      </div>
    </div>
  );
};