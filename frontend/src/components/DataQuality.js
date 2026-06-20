import React, { useState } from 'react';
import { CheckCircle, AlertTriangle, XCircle, X, Trash2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DataQuality = ({ data: initialData, onSave, onCancel }) => {
  const { token } = useAuth();
  const [data, setData] = useState(initialData);
  const [datasetName, setDatasetName] = useState('My Dataset');
  const [removingDuplicates, setRemovingDuplicates] = useState(false);

  const getScoreColor = (score) => {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#f59e0b';
    return '#ef4444';
  };

  const getScoreLabel = (score) => {
    if (score >= 80) return 'Excellent';
    if (score >= 60) return 'Good';
    return 'Needs Attention';
  };

  const handleRemoveDuplicates = async () => {
    setRemovingDuplicates(true);
    try {
      const response = await axios.post(
        `${API_BASE}/datasets/remove-duplicates`,
        { cleaned_data: data.cleaned_data },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      // Update local data with deduplicated rows, bump score, and rewrite the duplicate issue
      const newIssues = data.issues
        .filter(i => !i.message.toLowerCase().includes('duplicate'))
        .concat([{ type: 'success', message: `Removed ${response.data.removed} duplicate rows` }]);
      setData({
        ...data,
        cleaned_data: response.data.cleaned_data,
        duplicates_found: 0,
        score: Math.min(100, data.score + 10),
        issues: newIssues
      });
    } catch (err) {
      console.error('Remove duplicates failed:', err);
    } finally {
      setRemovingDuplicates(false);
    }
  };

  const hasDuplicates = data.duplicates_found > 0;

  return (
    <div className="min-h-screen p-6" style={{ background: '#0a0a12' }}>
      <div className="max-w-4xl mx-auto">
        <div className="glass-card p-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-white">Data Quality Report</h2>
            <button
              data-testid="close-quality-button"
              onClick={onCancel}
              className="p-2 rounded-lg hover:bg-[#12121f] text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Score */}
          <div className="mb-8 text-center">
            <div className="inline-flex flex-col items-center justify-center w-32 h-32 rounded-full mb-4" style={{
              background: `conic-gradient(${getScoreColor(data.score)} ${data.score * 3.6}deg, rgba(99, 102, 241, 0.1) 0deg)`
            }}>
              <div className="w-28 h-28 rounded-full flex flex-col items-center justify-center" style={{ background: '#0d0d1f' }}>
                <span className="text-4xl font-bold" style={{ color: getScoreColor(data.score) }}>{data.score}</span>
                <span className="text-xs text-gray-400">/ 100</span>
              </div>
            </div>
            <p className="text-xl font-semibold" style={{ color: getScoreColor(data.score) }}>
              {getScoreLabel(data.score)}
            </p>
          </div>

          {/* Issues */}
          <div className="space-y-3 mb-8" data-testid="quality-issues">
            {data.issues.map((issue, idx) => {
              const Icon = issue.type === 'success' ? CheckCircle : issue.type === 'warning' ? AlertTriangle : XCircle;
              const color = issue.type === 'success' ? '#10b981' : issue.type === 'warning' ? '#f59e0b' : '#ef4444';
              const bgColor = issue.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : issue.type === 'warning' ? 'rgba(245, 158, 11, 0.1)' : 'rgba(239, 68, 68, 0.1)';

              return (
                <div
                  key={idx}
                  data-testid={`quality-issue-${idx}`}
                  className="flex items-start gap-3 p-4 rounded-lg"
                  style={{ background: bgColor }}
                >
                  <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color }} />
                  <p className="text-white text-sm">{issue.message}</p>
                </div>
              );
            })}
          </div>

          {/* Summary */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="p-4 rounded-lg" style={{ background: '#12121f' }}>
              <p className="text-gray-400 text-sm mb-1">Numeric Columns</p>
              <p className="text-2xl font-bold text-white">{data.numeric_columns.length}</p>
              <p className="text-xs text-gray-500 mt-1">{data.numeric_columns.join(', ')}</p>
            </div>
            <div className="p-4 rounded-lg" style={{ background: '#12121f' }}>
              <p className="text-gray-400 text-sm mb-1">Label Columns</p>
              <p className="text-2xl font-bold text-white">{data.label_columns.length}</p>
              <p className="text-xs text-gray-500 mt-1">{data.label_columns.join(', ')}</p>
            </div>
          </div>

          {/* Remove Duplicates Action (only when duplicates exist) */}
          {hasDuplicates && (
            <div className="mb-6 p-4 rounded-lg flex items-center justify-between" style={{ background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5" style={{ color: '#f59e0b' }} />
                <div>
                  <p className="text-white font-medium text-sm">{data.duplicates_found} duplicate row{data.duplicates_found !== 1 ? 's' : ''} found</p>
                  <p className="text-gray-400 text-xs">Remove them in one click before analysis</p>
                </div>
              </div>
              <button
                data-testid="remove-duplicates-button"
                onClick={handleRemoveDuplicates}
                disabled={removingDuplicates}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#f59e0b] hover:bg-[#d97706] text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                {removingDuplicates ? 'Removing...' : 'Remove Duplicates'}
              </button>
            </div>
          )}

          {/* Dataset Name */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">Dataset Name</label>
            <input
              data-testid="dataset-name-input"
              type="text"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              className="w-full px-4 py-3 rounded-lg bg-[#12121f] border border-[#1e1e2e] text-white focus:outline-none focus:border-[#6366f1] transition-colors"
              placeholder="Enter dataset name"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button
              data-testid="proceed-button"
              onClick={() => onSave(datasetName, data)}
              className="flex-1 py-3 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white font-medium transition-all transform hover:scale-[1.02]"
            >
              Proceed to Dashboard
            </button>
            <button
              data-testid="fix-first-button"
              onClick={onCancel}
              className="px-6 py-3 rounded-lg border border-[#1e1e2e] text-gray-400 hover:text-white hover:border-gray-600 font-medium transition-colors"
            >
              Let me fix it first
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataQuality;
