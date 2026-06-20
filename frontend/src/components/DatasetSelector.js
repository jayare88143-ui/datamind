import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Database, Edit2, Trash2, Check, X } from 'lucide-react';
import axios from 'axios';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DatasetSelector = ({ datasets, currentDataset, onSelect, onRename, onDelete, token }) => {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setEditingId(null);
        setConfirmDeleteId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const startEdit = (dataset, e) => {
    e.stopPropagation();
    setEditingId(dataset.id);
    setEditName(dataset.name);
    setConfirmDeleteId(null);
  };

  const submitRename = async (datasetId, e) => {
    e.stopPropagation();
    if (!editName.trim()) return;
    try {
      await axios.patch(
        `${API_BASE}/datasets/${datasetId}/rename`,
        { name: editName.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onRename(datasetId, editName.trim());
      setEditingId(null);
    } catch (err) {
      console.error('Rename failed:', err);
    }
  };

  const cancelEdit = (e) => {
    e.stopPropagation();
    setEditingId(null);
    setEditName('');
  };

  const startDelete = (datasetId, e) => {
    e.stopPropagation();
    setConfirmDeleteId(datasetId);
    setEditingId(null);
  };

  const confirmDelete = async (datasetId, e) => {
    e.stopPropagation();
    try {
      await axios.delete(`${API_BASE}/datasets/${datasetId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      onDelete(datasetId);
      setConfirmDeleteId(null);
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  if (!currentDataset) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        data-testid="dataset-selector-button"
        onClick={() => setOpen(!open)}
        aria-label={`Current dataset: ${currentDataset.name}. Click to switch.`}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#12121f] transition-colors text-left"
      >
        <div>
          <p className="text-xs text-gray-500">Dataset</p>
          <div className="flex items-center gap-1">
            <p className="text-sm font-medium text-white max-w-[200px] truncate">{currentDataset.name}</p>
            <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
          </div>
        </div>
      </button>

      {open && (
        <div
          data-testid="dataset-dropdown"
          className="absolute top-full mt-2 left-0 w-80 rounded-lg shadow-xl z-50 overflow-hidden"
          style={{ background: '#12121f', border: '1px solid #1e1e2e' }}
        >
          <div className="px-3 py-2 border-b text-xs font-semibold text-gray-400 uppercase tracking-wider" style={{ borderColor: '#1e1e2e' }}>
            Your Datasets ({datasets.length})
          </div>
          <div className="max-h-80 overflow-y-auto scrollbar-thin">
            {datasets.map((dataset) => (
              <div
                key={dataset.id}
                data-testid={`dataset-item-${dataset.id}`}
                className={`group flex items-center justify-between px-3 py-3 hover:bg-[#1a1a2e] transition-colors cursor-pointer ${
                  currentDataset.id === dataset.id ? 'bg-[#1a1a2e]' : ''
                }`}
                onClick={() => {
                  if (editingId !== dataset.id && confirmDeleteId !== dataset.id) {
                    onSelect(dataset);
                    setOpen(false);
                  }
                }}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <Database className={`w-4 h-4 flex-shrink-0 ${currentDataset.id === dataset.id ? 'text-[#6366f1]' : 'text-gray-500'}`} />
                  {editingId === dataset.id ? (
                    <input
                      data-testid={`rename-input-${dataset.id}`}
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') submitRename(dataset.id, e);
                        if (e.key === 'Escape') cancelEdit(e);
                      }}
                      className="flex-1 px-2 py-1 rounded bg-[#0a0a12] border border-[#6366f1] text-white text-sm focus:outline-none"
                      autoFocus
                    />
                  ) : (
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{dataset.name}</p>
                      <p className="text-xs text-gray-500">{dataset.metrics?.length || 0} metrics • Quality: {dataset.quality_score}</p>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                  {editingId === dataset.id ? (
                    <>
                      <button
                        data-testid={`confirm-rename-${dataset.id}`}
                        onClick={(e) => submitRename(dataset.id, e)}
                        className="p-1.5 rounded hover:bg-[#10b981]/20 text-[#10b981] transition-colors"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        data-testid={`cancel-rename-${dataset.id}`}
                        onClick={cancelEdit}
                        className="p-1.5 rounded hover:bg-[#ef4444]/20 text-gray-400 transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </>
                  ) : confirmDeleteId === dataset.id ? (
                    <>
                      <button
                        data-testid={`confirm-delete-${dataset.id}`}
                        onClick={(e) => confirmDelete(dataset.id, e)}
                        className="px-2 py-1 rounded bg-[#ef4444] hover:bg-[#dc2626] text-white text-xs font-semibold transition-colors"
                      >
                        Delete
                      </button>
                      <button
                        data-testid={`cancel-delete-${dataset.id}`}
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                        className="p-1.5 rounded hover:bg-[#1e1e2e] text-gray-400 transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </>
                  ) : (
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                      <button
                        data-testid={`rename-dataset-${dataset.id}`}
                        onClick={(e) => startEdit(dataset, e)}
                        className="p-1.5 rounded hover:bg-[#1e1e2e] text-gray-400 hover:text-white transition-colors"
                        title="Rename"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        data-testid={`delete-dataset-${dataset.id}`}
                        onClick={(e) => startDelete(dataset.id, e)}
                        className="p-1.5 rounded hover:bg-[#ef4444]/20 text-gray-400 hover:text-[#ef4444] transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DatasetSelector;
