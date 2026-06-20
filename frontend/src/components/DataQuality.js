import React, { useState } from 'react';
import { CheckCircle, AlertTriangle, XCircle, X } from 'lucide-react';

const DataQuality = ({ data, onSave, onCancel }) => {
  const [datasetName, setDatasetName] = useState('My Dataset');

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
              onClick={() => onSave(datasetName)}
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
