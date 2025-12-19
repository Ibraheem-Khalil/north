import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Brain, Search, CheckCircle, Loader } from 'lucide-react';

interface SearchProgressProps {
  progress: Array<{
    stage: 'thinking' | 'searching' | 'verifying' | 'processing' | 'complete';
    message: string;
    timestamp: string;
    details?: any;
  }>;
  isSearching: boolean;
}

export const SearchProgress: React.FC<SearchProgressProps> = ({ progress, isSearching }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (progress.length === 0 && !isSearching) {
    return null;
  }

  // Check if we've reached completion
  const isComplete = progress.some(p => p.stage === 'complete');
  
  // Get the latest stage for icon determination
  const getStageIcon = (stage: string, index: number) => {
    // Determine if this is the current active stage
    const isCurrentStage = index === progress.length - 1 && isSearching && !isComplete;
    switch (stage) {
      case 'thinking':
        return <Brain className="w-4 h-4 text-purple-500" />;
      case 'searching':
        return <Search className="w-4 h-4 text-blue-500" />;
      case 'verifying':
        return isCurrentStage ? 
          <Loader className="w-4 h-4 text-yellow-500 animate-spin" /> :
          <CheckCircle className="w-4 h-4 text-yellow-500" />;
      case 'processing':
        return isCurrentStage ?
          <Loader className="w-4 h-4 text-orange-500 animate-spin" /> :
          <CheckCircle className="w-4 h-4 text-orange-500" />;
      case 'linking':
        return isCurrentStage ?
          <Loader className="w-4 h-4 text-indigo-500 animate-spin" /> :
          <CheckCircle className="w-4 h-4 text-indigo-500" />;
      case 'formatting':
        return isCurrentStage ?
          <Loader className="w-4 h-4 text-pink-500 animate-spin" /> :
          <CheckCircle className="w-4 h-4 text-pink-500" />;
      case 'complete':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      default:
        return isCurrentStage ?
          <Loader className="w-4 h-4 text-gray-500 animate-spin" /> :
          <CheckCircle className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStageColor = (stage: string) => {
    switch (stage) {
      case 'thinking':
        return 'bg-purple-50 border-purple-200';
      case 'searching':
        return 'bg-blue-50 border-blue-200';
      case 'verifying':
        return 'bg-yellow-50 border-yellow-200';
      case 'processing':
        return 'bg-orange-50 border-orange-200';
      case 'linking':
        return 'bg-indigo-50 border-indigo-200';
      case 'formatting':
        return 'bg-pink-50 border-pink-200';
      case 'complete':
        return 'bg-green-50 border-green-200';
      default:
        return 'bg-gray-50 border-gray-200';
    }
  };

  // Get the latest thinking message for preview
  const latestThinking = progress
    .filter(p => p.stage === 'thinking')
    .slice(-1)[0];

  return (
    <div className="mb-4">
      {/* Collapsed view - shows latest thinking */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full text-left bg-gray-50 hover:bg-gray-100 rounded-lg p-3 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {isSearching ? (
              <Loader className="w-4 h-4 text-blue-500 animate-spin" />
            ) : (
              <Brain className="w-4 h-4 text-gray-500" />
            )}
            <span className="text-sm font-medium text-gray-700">
              {isSearching ? 'Searching Dropbox...' : 'Search Process'}
            </span>
            {latestThinking && !isExpanded && (
              <span className="text-sm text-gray-500 truncate max-w-md">
                - {latestThinking.message}
              </span>
            )}
          </div>
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded view - shows all progress */}
      {isExpanded && (
        <div className="mt-2 bg-white border border-gray-200 rounded-lg p-4 space-y-2 max-h-96 overflow-y-auto">
          {progress.map((step, index) => (
            <div
              key={index}
              className={`flex items-start space-x-3 p-3 rounded-lg border ${getStageColor(step.stage)}`}
            >
              <div className="flex-shrink-0 mt-0.5">
                {getStageIcon(step.stage, index)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-900">
                  {step.message}
                </div>
                {step.details && (
                  <div className="mt-1 text-xs text-gray-500">
                    {step.details.planned_queries && (
                      <div>
                        Planned searches: {step.details.planned_queries.join(', ')}
                      </div>
                    )}
                    {step.details.iteration && (
                      <div>
                        Attempt {step.details.iteration} of {step.details.max_iterations}
                      </div>
                    )}
                    {step.details.file && (
                      <div>
                        Verifying: {step.details.file}
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0">
                <span className="text-xs text-gray-400">
                  {new Date(step.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
          
          {isSearching && (
            <div className="flex items-center justify-center py-2">
              <Loader className="w-5 h-5 text-blue-500 animate-spin" />
              <span className="ml-2 text-sm text-gray-500">Processing...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};