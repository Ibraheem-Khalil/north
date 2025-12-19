import React, { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { userApi } from '../services/api';
import toast from 'react-hot-toast';

interface NameModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNameSaved: (name: string) => void;
}

export const NameModal: React.FC<NameModalProps> = ({ isOpen, onClose, onNameSaved }) => {
  const [name, setName] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setIsLoading(true);
    try {
      await userApi.updatePreferences({ preferred_name: name.trim() });
      
      // Update local storage
      const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
      currentUser.preferred_name = name.trim();
      localStorage.setItem('user', JSON.stringify(currentUser));
      
      toast.success(`Nice to meet you, ${name.trim()}!`);
      onNameSaved(name.trim());
      onClose();
    } catch (error) {
      toast.error('Failed to save your name. Please try again.');
      console.error('Save name error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      
      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 transform transition-all">
        {/* Decorative Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center">
            <Sparkles className="w-8 h-8 text-white" />
          </div>
        </div>

        {/* Content */}
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Welcome to NORTH AI
          </h2>
          <p className="text-gray-600">
            To make our conversations more personal, what would you like me to call you?
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Enter your preferred name"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-center text-lg"
            autoFocus
            required
          />
          
          <button
            type="submit"
            disabled={!name.trim() || isLoading}
            className="w-full py-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white font-medium rounded-lg hover:from-blue-600 hover:to-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Saving...' : 'Continue'}
          </button>

          {/* Skip option - hidden but functional */}
          <button
            type="button"
            onClick={() => {
              onClose();
              toast('You can set your name later in Settings', { icon: '💡' });
            }}
            className="w-full text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Skip for now
          </button>
        </form>
      </div>
    </div>
  );
};