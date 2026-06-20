import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MetricDetail = ({ metric, datasetId, onClose }) => {
  const { token } = useAuth();
  const [analysis, setAnalysis] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalysis();
  }, []);

  const fetchAnalysis = async () => {
    try {
      const metricKey = metric.column || metric.name;
      const response = await fetch(
        `${API_BASE}/metrics/${encodeURIComponent(metricKey)}/analyze?dataset_id=${datasetId}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                setAnalysis((prev) => prev + data.content);
              }
              if (data.done) {
                setLoading(false);
                break;
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }
    } catch (error) {
      console.error('Analysis error:', error);
      setAnalysis('Failed to load analysis. Please try again.');
      setLoading(false);
    }
  };

  const formatContent = (content) => {
    const parts = content.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, idx) => {
      if (idx % 2 === 1) {
        return <strong key={idx} style={{ color: '#6366f1' }}>{part}</strong>;
      }
      return part;
    });
  };

  const isUp = metric.trend === 'up';
  const isDown = metric.trend === 'down';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0, 0, 0, 0.8)' }}>
      <div className="glass-card p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto scrollbar-thin" data-testid="metric-detail-modal">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">{metric.name} Analysis</h2>
            <div className={`flex items-center gap-2 text-sm ${
              isUp ? 'trend-up' : isDown ? 'trend-down' : 'trend-flat'
            }`}>
              {isUp ? <TrendingUp className="w-4 h-4" /> : isDown ? <TrendingDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
              <span className="font-medium">{Math.abs(metric.trend_percent).toFixed(1)}% per period</span>
            </div>
          </div>
          <button
            data-testid="close-metric-detail"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[#12121f] text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="p-4 rounded-lg" style={{ background: '#12121f' }}>
            <p className="text-gray-400 text-xs mb-1">Latest Value</p>
            <p className="text-xl font-bold text-white monospace">{metric.latest_value.toFixed(2)}</p>
          </div>
          <div className="p-4 rounded-lg" style={{ background: '#12121f' }}>
            <p className="text-gray-400 text-xs mb-1">Mean</p>
            <p className="text-xl font-bold text-white monospace">{metric.mean.toFixed(2)}</p>
          </div>
          <div className="p-4 rounded-lg" style={{ background: '#12121f' }}>
            <p className="text-gray-400 text-xs mb-1">Std Dev</p>
            <p className="text-xl font-bold text-white monospace">{metric.std_dev.toFixed(2)}</p>
          </div>
        </div>

        {metric.anomalies && metric.anomalies.length > 0 && (
          <div className="mb-6 p-4 rounded-lg" style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
            <p className="text-red-400 font-medium mb-2">{metric.anomalies.length} Anomal{metric.anomalies.length === 1 ? 'y' : 'ies'} Detected</p>
            <div className="space-y-2">
              {metric.anomalies.slice(0, 3).map((anomaly, idx) => (
                <p key={idx} className="text-sm text-gray-300">
                  • {anomaly.value} at {anomaly.label} (z-score: {anomaly.z_score.toFixed(2)})
                </p>
              ))}
            </div>
          </div>
        )}

        <div className="prose prose-invert max-w-none">
          {loading && analysis === '' ? (
            <div className="flex items-center gap-2 text-gray-400">
              <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse"></div>
              <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse" style={{ animationDelay: '0.2s' }}></div>
              <div className="w-2 h-2 rounded-full bg-[#6366f1] animate-pulse" style={{ animationDelay: '0.4s' }}></div>
              <span className="ml-2">AI is analyzing...</span>
            </div>
          ) : (
            <div data-testid="ai-analysis" className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">
              {formatContent(analysis)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MetricDetail;
