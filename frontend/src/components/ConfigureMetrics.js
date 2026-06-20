import React, { useMemo, useState } from 'react';
import { ChevronLeft, Sparkles, X, TrendingUp } from 'lucide-react';

const CALCULATION_OPTIONS = [
  { value: 'latest', label: 'Latest value', hint: 'show the most recent period' },
  { value: 'sum', label: 'Sum', hint: 'total across all rows' },
  { value: 'mean', label: 'Average', hint: 'mean across all rows' },
  { value: 'min', label: 'Minimum', hint: 'lowest value seen' },
  { value: 'max', label: 'Maximum', hint: 'highest value seen' },
  { value: 'count', label: 'Count', hint: 'number of non-empty rows' },
  { value: 'growth', label: 'Growth %', hint: 'percent change first → last' },
];

const calcLabel = (v) => CALCULATION_OPTIONS.find(o => o.value === v)?.label || v;

const ConfigureMetrics = ({ qualityData, onBack, onSave }) => {
  const suggestions = qualityData.suggested_metric_configs || [];

  const initialConfigs = useMemo(() => {
    // Prefer server suggestions; fall back to a default config per numeric column
    if (suggestions.length > 0) {
      return suggestions.map(s => ({
        column: s.column,
        display_name: s.suggested_display_name,
        calculation: s.suggested_calculation,
        enabled: true,
        rationale: s.rationale,
      }));
    }
    return (qualityData.numeric_columns || []).map(col => ({
      column: col,
      display_name: col,
      calculation: 'latest',
      enabled: true,
      rationale: '',
    }));
  }, [suggestions, qualityData.numeric_columns]);

  const [configs, setConfigs] = useState(initialConfigs);
  const [datasetName, setDatasetName] = useState('My Dataset');
  const [saving, setSaving] = useState(false);

  const updateConfig = (idx, patch) => {
    setConfigs(prev => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  };

  const enabledCount = configs.filter(c => c.enabled).length;

  const handleSave = async () => {
    const trimmed = datasetName.trim();
    if (!trimmed) return;
    if (enabledCount === 0) return;
    setSaving(true);
    try {
      // Strip frontend-only `rationale` before sending
      const cleanConfigs = configs
        .filter(c => c.enabled)
        .map(({ column, display_name, calculation }) => ({
          column,
          display_name: display_name?.trim() || column,
          calculation,
          enabled: true,
        }));
      await onSave(trimmed, cleanConfigs);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen p-6" style={{ background: '#0a0a12' }}>
      <div className="max-w-4xl mx-auto">
        <div className="glass-card p-8">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <button
                data-testid="configure-back-button"
                onClick={onBack}
                className="p-2 rounded-lg hover:bg-[#12121f] text-gray-400 hover:text-white transition-colors"
                aria-label="Back to data quality"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <div>
                <h2 className="text-2xl font-bold text-white">Configure Metrics</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Pick what to monitor and how it should be calculated. We've pre-filled smart defaults.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full" style={{ background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
              <Sparkles className="w-3.5 h-3.5" style={{ color: '#6366f1' }} />
              <span className="text-xs font-medium" style={{ color: '#a5b4fc' }}>AI-suggested defaults</span>
            </div>
          </div>

          {/* Dataset name */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">Dataset name</label>
            <input
              data-testid="configure-dataset-name"
              type="text"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              className="w-full px-4 py-3 rounded-lg bg-[#12121f] border border-[#1e1e2e] text-white focus:outline-none focus:border-[#6366f1] transition-colors"
              placeholder="e.g. Q4 customer metrics"
            />
          </div>

          {/* Metric cards */}
          {configs.length === 0 ? (
            <div className="p-8 rounded-lg text-center text-gray-400" style={{ background: '#12121f' }}>
              No numeric columns detected in your data. You can still proceed without metrics, but the dashboard will be empty.
            </div>
          ) : (
            <div className="space-y-3 mb-6">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">
                  {enabledCount} of {configs.length} metric{configs.length === 1 ? '' : 's'} selected
                </span>
                <div className="flex gap-3">
                  <button
                    data-testid="select-all-metrics"
                    onClick={() => setConfigs(prev => prev.map(c => ({ ...c, enabled: true })))}
                    className="text-xs text-[#6366f1] hover:text-white transition-colors"
                  >
                    Select all
                  </button>
                  <button
                    data-testid="deselect-all-metrics"
                    onClick={() => setConfigs(prev => prev.map(c => ({ ...c, enabled: false })))}
                    className="text-xs text-gray-400 hover:text-white transition-colors"
                  >
                    Clear
                  </button>
                </div>
              </div>

              {configs.map((config, idx) => (
                <div
                  key={config.column}
                  data-testid={`metric-config-${config.column}`}
                  className={`p-4 rounded-lg border transition-all ${
                    config.enabled
                      ? 'border-[#6366f1]/30'
                      : 'border-[#1e1e2e] opacity-50'
                  }`}
                  style={{ background: '#12121f' }}
                >
                  <div className="flex items-start gap-4">
                    {/* Include toggle */}
                    <label className="flex items-center gap-2 mt-2 cursor-pointer">
                      <input
                        data-testid={`metric-enabled-${config.column}`}
                        type="checkbox"
                        checked={config.enabled}
                        onChange={(e) => updateConfig(idx, { enabled: e.target.checked })}
                        className="w-5 h-5 rounded accent-[#6366f1] cursor-pointer"
                      />
                    </label>

                    <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Display name */}
                      <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1.5">
                          Display name
                          <span className="ml-2 text-gray-600 font-mono">{config.column}</span>
                        </label>
                        <input
                          data-testid={`metric-name-${config.column}`}
                          type="text"
                          value={config.display_name}
                          disabled={!config.enabled}
                          onChange={(e) => updateConfig(idx, { display_name: e.target.value })}
                          className="w-full px-3 py-2 rounded-lg bg-[#0a0a12] border border-[#1e1e2e] text-white text-sm focus:outline-none focus:border-[#6366f1] transition-colors disabled:cursor-not-allowed"
                          placeholder={config.column}
                        />
                      </div>

                      {/* Calculation */}
                      <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1.5">
                          Calculation
                          {config.rationale && (
                            <span className="ml-2 inline-flex items-center gap-1 text-[10px]" style={{ color: '#a5b4fc' }}>
                              <Sparkles className="w-2.5 h-2.5" />
                              {config.rationale}
                            </span>
                          )}
                        </label>
                        <select
                          data-testid={`metric-calc-${config.column}`}
                          value={config.calculation}
                          disabled={!config.enabled}
                          onChange={(e) => updateConfig(idx, { calculation: e.target.value })}
                          className="w-full px-3 py-2 rounded-lg bg-[#0a0a12] border border-[#1e1e2e] text-white text-sm focus:outline-none focus:border-[#6366f1] transition-colors disabled:cursor-not-allowed"
                        >
                          {CALCULATION_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label} — {opt.hint}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Footer with current selection summary */}
                  {config.enabled && (
                    <div className="mt-3 pl-9 flex items-center gap-2 text-xs text-gray-500">
                      <TrendingUp className="w-3 h-3" />
                      Headline value will be the&nbsp;
                      <span className="text-white font-medium">{calcLabel(config.calculation).toLowerCase()}</span>
                      &nbsp;of <span className="font-mono text-gray-400">{config.column}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-4 pt-4 border-t" style={{ borderColor: '#1e1e2e' }}>
            <button
              data-testid="configure-save-button"
              onClick={handleSave}
              disabled={saving || !datasetName.trim() || enabledCount === 0}
              className="flex-1 py-3 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white font-medium transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {saving ? 'Saving…' : `Save & View Dashboard (${enabledCount} metric${enabledCount === 1 ? '' : 's'})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigureMetrics;
