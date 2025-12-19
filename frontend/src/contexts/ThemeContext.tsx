import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { userApi } from '../services/api';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>('light');

  useEffect(() => {
    // Load theme from localStorage or user preferences
    const loadTheme = async () => {
      // First check localStorage for immediate loading
      const savedTheme = localStorage.getItem('theme') as Theme;
      if (savedTheme) {
        setThemeState(savedTheme);
        applyTheme(savedTheme);
      }

      // Then check user preferences from API
      try {
        const { preferences } = await userApi.getPreferences();
        if (preferences.theme) {
          setThemeState(preferences.theme);
          applyTheme(preferences.theme);
          localStorage.setItem('theme', preferences.theme);
        }
      } catch (error) {
        // If not logged in or error, use localStorage or default
      }
    };

    loadTheme();
  }, []);

  const applyTheme = (newTheme: Theme) => {
    if (newTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  const setTheme = async (newTheme: Theme) => {
    setThemeState(newTheme);
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);

    // Save to user preferences if logged in
    try {
      const { preferences } = await userApi.getPreferences();
      await userApi.updatePreferences({ ...preferences, theme: newTheme });
    } catch (error) {
      // User might not be logged in, that's ok
    }
  };

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};