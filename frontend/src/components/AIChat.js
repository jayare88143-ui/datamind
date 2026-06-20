import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Send, Sparkles, Trash2 } from 'lucide-react';
import axios from 'axios';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const AIChat = ({ dataset }) => {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const messagesEndRef = useRef(null);

  const suggestedQuestions = [
    "What's the biggest anomaly?",
    "Summarize all trends",
    "Which metric needs urgent attention?",
    "Best and worst month overall?"
  ];

  // Load chat history when dataset changes
  useEffect(() => {
    const loadHistory = async () => {
      setHistoryLoaded(false);
      setMessages([]);
      try {
        const response = await axios.get(
          `${API_BASE}/chat/history/${dataset.id}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        const history = response.data.map(m => ({ role: m.role, content: m.content }));
        setMessages(history);
      } catch (err) {
        console.error('Failed to load chat history:', err);
      } finally {
        setHistoryLoaded(true);
      }
    };
    if (dataset?.id) loadHistory();
  }, [dataset?.id, token]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const saveMessage = async (role, content) => {
    try {
      await axios.post(
        `${API_BASE}/chat/save`,
        { dataset_id: dataset.id, role, content },
        { headers: { Authorization: `Bearer ${token}` } }
      );
    } catch (err) {
      console.error('Failed to save message:', err);
    }
  };

  const clearHistory = async () => {
    if (!window.confirm('Clear all chat history for this dataset?')) return;
    try {
      await axios.delete(`${API_BASE}/chat/history/${dataset.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setMessages([]);
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  const sendMessage = async (text) => {
    if (!text.trim() || isStreaming) return;

    const userMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);

    // Save user message
    saveMessage('user', text);

    const assistantMessage = { role: 'assistant', content: '' };
    setMessages((prev) => [...prev, assistantMessage]);

    let fullResponse = '';

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: text,
          dataset_id: dataset.id
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        // Keep the last (possibly incomplete) line in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                fullResponse += data.content;
                setMessages((prev) => {
                  const newMessages = [...prev];
                  newMessages[newMessages.length - 1].content += data.content;
                  return newMessages;
                });
              }
              if (data.done) break;
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }
      // Save assistant message after streaming completes
      if (fullResponse) {
        saveMessage('assistant', fullResponse);
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1].content = 'Sorry, I encountered an error. Please try again.';
        return newMessages;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const formatContent = (content) => {
    // Convert **text** to bold
    const parts = content.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, idx) => {
      if (idx % 2 === 1) {
        return <strong key={idx} style={{ color: '#6366f1' }}>{part}</strong>;
      }
      return part;
    });
  };

  return (
    <div className="flex flex-col h-[calc(100vh-200px)]">
      {/* Header with Clear button */}
      {messages.length > 0 && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4" style={{ color: '#6366f1' }} />
            <span className="text-sm text-gray-400">{messages.length} message{messages.length !== 1 ? 's' : ''}</span>
          </div>
          <button
            data-testid="clear-chat-history"
            onClick={clearHistory}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-[#ef4444] hover:bg-[#ef4444]/10 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear History
          </button>
        </div>
      )}

      {/* Suggested Questions */}
      {messages.length === 0 && historyLoaded && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-5 h-5" style={{ color: '#6366f1' }} />
            <h3 className="text-lg font-semibold text-white">Ask me anything about your data</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {suggestedQuestions.map((question, idx) => (
              <button
                key={idx}
                data-testid={`suggested-question-${idx}`}
                onClick={() => sendMessage(question)}
                className="p-4 rounded-lg text-left text-sm text-gray-300 hover:text-white hover:border-[#6366f1] transition-all" style={{ background: '#12121f', border: '1px solid #1e1e2e' }}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-4 mb-4" data-testid="chat-messages">
        {messages.map((message, idx) => (
          <div
            key={idx}
            data-testid={`chat-message-${idx}`}
            className={`chat-message flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] p-4 rounded-lg ${
                message.role === 'user'
                  ? 'bg-[#6366f1] text-white'
                  : 'glass-card text-white'
              }`}
            >
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {message.role === 'assistant' ? formatContent(message.content) : message.content}
              </div>
            </div>
          </div>
        ))}
        {isStreaming && messages[messages.length - 1]?.content === '' && (
          <div className="flex items-center gap-2 text-gray-400">
            <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse"></div>
            <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse" style={{ animationDelay: '0.2s' }}></div>
            <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse" style={{ animationDelay: '0.4s' }}></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          data-testid="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your metrics, trends, or anomalies..."
          disabled={isStreaming}
          className="flex-1 px-4 py-3 rounded-lg bg-[#12121f] border border-[#1e1e2e] text-white focus:outline-none focus:border-[#6366f1] transition-colors disabled:opacity-50"
        />
        <button
          data-testid="chat-send-button"
          type="submit"
          disabled={!input.trim() || isStreaming}
          className="px-6 py-3 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};

export default AIChat;
