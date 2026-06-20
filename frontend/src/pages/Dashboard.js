import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Upload, TrendingUp, TrendingDown, Minus, AlertTriangle, MessageSquare, Database, FileText, LogOut } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import UploadCSV from '../components/UploadCSV';
import DataQuality from '../components/DataQuality';
import AIChat from '../components/AIChat';
import DataTable from '../components/DataTable';
import MetricDetail from '../components/MetricDetail';
import DatasetSelector from '../components/DatasetSelector';
import { jsPDF } from 'jspdf';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Dashboard = () => {
  const { user, token, logout } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [datasets, setDatasets] = useState([]);
  const [currentDataset, setCurrentDataset] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [qualityData, setQualityData] = useState(null);
  const [selectedMetric, setSelectedMetric] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDatasets();
  }, []);

  const fetchDatasets = async () => {
    try {
      const response = await axios.get(`${API_BASE}/datasets`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setDatasets(response.data);
      if (response.data.length > 0) {
        setCurrentDataset(response.data[0]);
      }
    } catch (error) {
      console.error('Failed to fetch datasets:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadComplete = (quality) => {
    setQualityData(quality);
    setShowUpload(false);
    setShowQuality(true);
  };

  const handleSaveDataset = async (name, updatedQualityData) => {
    const dataToSave = updatedQualityData || qualityData;
    try {
      const response = await axios.post(
        `${API_BASE}/datasets/save`,
        {
          name: name,
          cleaned_data: dataToSave.cleaned_data,
          original_data: dataToSave.original_data,
          numeric_columns: dataToSave.numeric_columns,
          label_columns: dataToSave.label_columns,
          quality_score: dataToSave.score
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const newDataset = response.data;
      // Add the new dataset to the local list (newest first) and select it
      setDatasets((prev) => [newDataset, ...prev.filter(d => d.id !== newDataset.id)]);
      setCurrentDataset(newDataset);
      setShowQuality(false);
      setQualityData(null);
      setActiveTab('dashboard');
    } catch (error) {
      console.error('Failed to save dataset:', error);
      alert('Failed to save dataset: ' + (error.response?.data?.detail || error.message));
    }
  };

  const loadSampleData = async () => {
    try {
      const response = await axios.get(`${API_BASE}/datasets/sample/data`);
      const sampleData = response.data;
      
      // Process sample data as if uploaded
      const quality = {
        score: 100,
        issues: [
          { type: 'success', message: 'No empty rows found' },
          { type: 'success', message: 'No duplicate rows found' },
          { type: 'success', message: 'All 4 numeric columns valid' }
        ],
        rows_removed: 0,
        duplicates_found: 0,
        cleaned_data: sampleData,
        original_data: sampleData,
        numeric_columns: ['revenue', 'orders', 'cac', 'churn'],
        label_columns: ['month']
      };
      
      setQualityData(quality);
      setShowQuality(true);
    } catch (error) {
      console.error('Failed to load sample data:', error);
    }
  };

  const exportPDF = () => {
    if (!currentDataset) return;

    const doc = new jsPDF();
    
    // Title
    doc.setFontSize(20);
    doc.setTextColor(99, 102, 241);
    doc.text('DataMind Analytics Report', 20, 20);
    
    // Dataset name
    doc.setFontSize(12);
    doc.setTextColor(0, 0, 0);
    doc.text(`Dataset: ${currentDataset.name}`, 20, 35);
    doc.text(`Generated: ${new Date().toLocaleDateString()}`, 20, 42);
    
    // Metrics Summary
    doc.setFontSize(14);
    doc.text('Key Metrics', 20, 55);
    doc.setFontSize(10);
    
    let y = 65;
    currentDataset.metrics.forEach((metric) => {
      doc.text(`${metric.name}: ${metric.latest_value.toFixed(2)}`, 25, y);
      doc.text(`Trend: ${metric.trend} (${metric.trend_percent.toFixed(1)}%)`, 25, y + 5);
      y += 15;
    });
    
    // Anomalies
    if (currentDataset.anomalies.length > 0) {
      doc.addPage();
      doc.setFontSize(14);
      doc.text('Detected Anomalies', 20, 20);
      doc.setFontSize(10);
      
      y = 30;
      currentDataset.anomalies.slice(0, 10).forEach((anomaly) => {
        doc.setTextColor(anomaly.severity === 'Critical' ? 239 : 245, anomaly.severity === 'Critical' ? 68 : 158, anomaly.severity === 'Critical' ? 68 : 11);
        doc.text(`${anomaly.severity}: ${anomaly.metric} = ${anomaly.value}`, 25, y);
        doc.setTextColor(0, 0, 0);
        doc.text(`At ${anomaly.label} (z-score: ${anomaly.z_score.toFixed(2)})`, 25, y + 5);
        y += 15;
        if (y > 270) {
          doc.addPage();
          y = 20;
        }
      });
    }
    
    doc.save(`DataMind_Report_${currentDataset.name}.pdf`);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0a0a12' }}>
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-[#6366f1] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (showUpload) {
    return <UploadCSV onComplete={handleUploadComplete} onCancel={() => setShowUpload(false)} />;
  }

  if (showQuality && qualityData) {
    return (
      <DataQuality
        data={qualityData}
        onSave={handleSaveDataset}
        onCancel={() => {
          setShowQuality(false);
          setQualityData(null);
        }}
      />
    );
  }

  if (!currentDataset) {
    return (
      <div className="min-h-screen" style={{ background: '#0a0a12' }}>
        {/* Header */}
        <div className="border-b" style={{ borderColor: '#1e1e2e', background: '#0d0d1f' }}>
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)' }}>
                <TrendingUp className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-xl font-bold text-white">DataMind</h1>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-gray-400 text-sm">Welcome, {user?.name}</span>
              <button
                data-testid="logout-button"
                onClick={logout}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#12121f] transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </div>
        </div>

        {/* Empty State */}
        <div className="flex items-center justify-center" style={{ minHeight: 'calc(100vh - 73px)' }}>
          <div className="text-center max-w-md px-4">
            <div className="w-24 h-24 rounded-2xl mx-auto mb-6 flex items-center justify-center" style={{ background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(168, 85, 247, 0.1) 100%)' }}>
              <Database className="w-12 h-12" style={{ color: '#6366f1' }} />
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">No Data Yet</h2>
            <p className="text-gray-400 mb-8">Upload your business data to get instant AI-powered insights and anomaly detection</p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                data-testid="upload-csv-button"
                onClick={() => setShowUpload(true)}
                className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white font-medium transition-all transform hover:scale-105"
              >
                <Upload className="w-5 h-5" />
                Upload CSV
              </button>
              <button
                data-testid="try-sample-button"
                onClick={loadSampleData}
                className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg border border-[#6366f1] text-[#6366f1] hover:bg-[#6366f1] hover:text-white font-medium transition-all"
              >
                Try Sample Data
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: '#0a0a12' }}>
      {/* Header */}
      <div className="border-b" style={{ borderColor: '#1e1e2e', background: '#0d0d1f' }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)' }}>
                <TrendingUp className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-xl font-bold text-white">DataMind</h1>
            </div>
            <div className="h-8 w-px" style={{ background: '#1e1e2e' }}></div>
            <DatasetSelector
              datasets={datasets}
              currentDataset={currentDataset}
              onSelect={(ds) => setCurrentDataset(ds)}
              onRename={(id, newName) => {
                setDatasets(prev => prev.map(d => d.id === id ? { ...d, name: newName } : d));
                if (currentDataset.id === id) {
                  setCurrentDataset(prev => ({ ...prev, name: newName }));
                }
              }}
              onDelete={(id) => {
                const remaining = datasets.filter(d => d.id !== id);
                setDatasets(remaining);
                if (currentDataset.id === id) {
                  setCurrentDataset(remaining.length > 0 ? remaining[0] : null);
                }
              }}
              token={token}
            />
            <div className="flex items-center gap-1 px-2 py-1 rounded-full" style={{ background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#10b981' }}></div>
              <span className="text-xs text-gray-300">Private to you</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              data-testid="export-pdf-button"
              onClick={exportPDF}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#12121f] hover:bg-[#1a1a2e] text-white transition-colors"
            >
              <FileText className="w-4 h-4" />
              Export PDF
            </button>
            <button
              data-testid="new-upload-button"
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white transition-colors"
            >
              <Upload className="w-4 h-4" />
              Upload New
            </button>
            <button
              data-testid="logout-button-main"
              onClick={logout}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#12121f] transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6 border-b" style={{ borderColor: '#1e1e2e' }}>
            <button
              data-testid="tab-dashboard"
              onClick={() => setActiveTab('dashboard')}
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                activeTab === 'dashboard'
                  ? 'text-[#6366f1] border-[#6366f1]'
                  : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              Dashboard
            </button>
            <button
              data-testid="tab-chat"
              onClick={() => setActiveTab('chat')}
              className={`px-4 py-3 font-medium transition-colors border-b-2 flex items-center gap-2 ${
                activeTab === 'chat'
                  ? 'text-[#6366f1] border-[#6366f1]'
                  : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              Ask AI
            </button>
            <button
              data-testid="tab-data"
              onClick={() => setActiveTab('data')}
              className={`px-4 py-3 font-medium transition-colors border-b-2 flex items-center gap-2 ${
                activeTab === 'data'
                  ? 'text-[#6366f1] border-[#6366f1]'
                  : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <Database className="w-4 h-4" />
              Data
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        {activeTab === 'dashboard' && (
          <DashboardView dataset={currentDataset} onMetricClick={setSelectedMetric} />
        )}
        {activeTab === 'chat' && <AIChat dataset={currentDataset} />}
        {activeTab === 'data' && <DataTable dataset={currentDataset} />}
      </div>

      {/* Metric Detail Modal */}
      {selectedMetric && (
        <MetricDetail
          metric={selectedMetric}
          datasetId={currentDataset.id}
          onClose={() => setSelectedMetric(null)}
        />
      )}
    </div>
  );
};

const DashboardView = ({ dataset, onMetricClick }) => {
  return (
    <div className="space-y-6">
      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {dataset.metrics.map((metric) => {
          const hasAnomaly = metric.anomalies && metric.anomalies.length > 0;
          const momChange = metric.mom_change;
          const isPositive = momChange !== null && momChange > 0;
          const isNegative = momChange !== null && momChange < 0;

          return (
            <div
              key={metric.name}
              data-testid={`kpi-card-${metric.name}`}
              className="kpi-card rounded-xl p-5"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-sm text-gray-400 mb-1">{metric.name}</p>
                  <p className="text-2xl font-bold text-white monospace">{metric.latest_value.toFixed(2)}</p>
                </div>
                {hasAnomaly && (
                  <div className="anomaly-pulse" data-testid={`anomaly-indicator-${metric.name}`}>
                    <div className="w-2 h-2 rounded-full" style={{ background: '#ef4444' }}></div>
                  </div>
                )}
              </div>
              {momChange !== null && (
                <div className={`flex items-center gap-1 text-sm ${
                  isPositive ? 'trend-up' : isNegative ? 'trend-down' : 'trend-flat'
                }`}>
                  {isPositive ? <TrendingUp className="w-4 h-4" /> : isNegative ? <TrendingDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
                  <span className="font-medium">{Math.abs(momChange).toFixed(1)}%</span>
                  <span className="text-gray-500 text-xs">vs last</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {dataset.metrics.map((metric) => {
          const chartData = metric.labels.map((label, idx) => ({
            label,
            value: metric.values[idx]
          }));

          const isUp = metric.trend === 'up';
          const isDown = metric.trend === 'down';

          return (
            <div
              key={metric.name}
              data-testid={`metric-card-${metric.name}`}
              onClick={() => onMetricClick(metric)}
              className="metric-card glass-card p-6 cursor-pointer hover:border-[#6366f1] transition-all"
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-white mb-1">{metric.name}</h3>
                  <div className={`flex items-center gap-2 text-sm ${
                    isUp ? 'trend-up' : isDown ? 'trend-down' : 'trend-flat'
                  }`}>
                    {isUp ? <TrendingUp className="w-4 h-4" /> : isDown ? <TrendingDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
                    <span className="font-medium">{Math.abs(metric.trend_percent).toFixed(1)}% per period</span>
                  </div>
                </div>
                {metric.anomalies && metric.anomalies.length > 0 && (
                  <div className="flex items-center gap-1 px-2 py-1 rounded-full" style={{ background: 'rgba(239, 68, 68, 0.1)' }}>
                    <div className="w-2 h-2 rounded-full" style={{ background: '#ef4444' }}></div>
                    <span className="text-xs font-medium" style={{ color: '#ef4444' }}>{metric.anomalies.length}</span>
                  </div>
                )}
              </div>

              <div className="h-20 mb-2" style={{ minWidth: 0 }}>
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <LineChart data={chartData}>
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#6366f1"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="text-xs text-gray-500">
                Click for AI analysis
              </div>
            </div>
          );
        })}
      </div>

      {/* Anomaly Feed */}
      {dataset.anomalies && dataset.anomalies.length > 0 && (
        <div className="glass-card p-6 rounded-xl">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5" style={{ color: '#f59e0b' }} />
            <h2 className="text-xl font-bold text-white">Anomaly Feed</h2>
          </div>
          <div className="space-y-3" data-testid="anomaly-feed">
            {dataset.anomalies.slice(0, 10).map((anomaly, idx) => (
              <div
                key={`${anomaly.metric}-${idx}`}
                data-testid={`anomaly-item-${idx}`}
                className="flex items-start gap-4 p-4 rounded-lg" style={{ background: '#12121f' }}
              >
                <div className={`px-2 py-1 rounded text-xs font-bold ${
                  anomaly.severity === 'Critical'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-yellow-500/20 text-yellow-400'
                }`}>
                  {anomaly.severity}
                </div>
                <div className="flex-1">
                  <p className="text-white font-medium mb-1">
                    {anomaly.metric} = <span className="monospace">{anomaly.value}</span>
                  </p>
                  <p className="text-sm text-gray-400">
                    At {anomaly.label} • Expected: {anomaly.expected_range} • z-score: {anomaly.z_score.toFixed(2)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
