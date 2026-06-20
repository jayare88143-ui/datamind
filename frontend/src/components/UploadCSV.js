import React, { useState, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Upload, X, FileSpreadsheet } from 'lucide-react';
import axios from 'axios';
import Papa from 'papaparse';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const UploadCSV = ({ onComplete, onCancel }) => {
  const { token } = useAuth();
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleFileInput = async (e) => {
    if (e.target.files && e.target.files[0]) {
      await handleFile(e.target.files[0]);
    }
  };

  const handleFile = async (file) => {
    if (!file.name.endsWith('.csv')) {
      setError('Please upload a CSV file');
      return;
    }

    setError('');
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await axios.post(`${API_BASE}/datasets/upload`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });

      onComplete(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to upload file');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: '#0a0a12' }}>
      <div className="w-full max-w-2xl">
        <div className="glass-card p-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-white">Upload CSV File</h2>
            <button
              data-testid="cancel-upload-button"
              onClick={onCancel}
              className="p-2 rounded-lg hover:bg-[#12121f] text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div
            data-testid="file-drop-zone"
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`upload-zone ${dragActive ? 'drag-active' : ''} rounded-xl p-12 text-center`}
          >
            <div className="flex flex-col items-center">
              <div className="w-20 h-20 rounded-2xl mb-6 flex items-center justify-center" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
                {uploading ? (
                  <div className="w-8 h-8 border-4 border-[#6366f1] border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  <FileSpreadsheet className="w-10 h-10" style={{ color: '#6366f1' }} />
                )}
              </div>

              {uploading ? (
                <p className="text-white font-medium mb-2">Processing your file...</p>
              ) : (
                <>
                  <h3 className="text-white font-semibold text-lg mb-2">Drop your CSV file here</h3>
                  <p className="text-gray-400 mb-6">or click to browse</p>
                  <input
                    data-testid="file-input"
                    type="file"
                    accept=".csv"
                    onChange={handleFileInput}
                    className="hidden"
                    id="file-upload"
                  />
                  <label
                    htmlFor="file-upload"
                    className="px-6 py-3 rounded-lg bg-[#6366f1] hover:bg-[#5558e3] text-white font-medium cursor-pointer transition-colors inline-block"
                  >
                    Browse Files
                  </label>
                </>
              )}
            </div>
          </div>

          {error && (
            <div data-testid="upload-error" className="mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
              {error}
            </div>
          )}

          <div className="mt-6 p-4 rounded-lg" style={{ background: '#12121f' }}>
            <p className="text-sm text-gray-400">
              <strong className="text-white">Tips:</strong> Upload CSV files up to ~50,000 rows for best performance. The first row should contain column headers.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadCSV;
