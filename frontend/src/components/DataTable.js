import React, { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Database } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;
const PAGE_SIZE = 50;

const DataTable = ({ dataset }) => {
  const { token } = useAuth();
  const numericColumns = dataset.numeric_columns || [];
  const labelColumns = dataset.label_columns || [];
  const dateColumns = dataset.date_columns || [];
  const allColumns = [...labelColumns, ...dateColumns, ...numericColumns];

  // Total row count: prefer total_rows (server-side count when chunked), fall back to data.length
  const totalRows = dataset.total_rows ?? (dataset.data || []).length;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));

  const [page, setPage] = useState(1);
  const [pageRows, setPageRows] = useState(() => (dataset.data || []).slice(0, PAGE_SIZE));
  const [loading, setLoading] = useState(false);

  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, totalRows);

  // Whether the preview embedded in the dataset already covers the current page
  const previewCovers = useMemo(() => {
    const previewLen = (dataset.data || []).length;
    return endIdx <= previewLen;
  }, [dataset.data, endIdx]);

  useEffect(() => {
    // Reset to page 1 when dataset changes
    setPage(1);
    setPageRows((dataset.data || []).slice(0, PAGE_SIZE));
  }, [dataset.id, dataset.data]);

  useEffect(() => {
    if (previewCovers) {
      setPageRows((dataset.data || []).slice(startIdx, endIdx));
      return;
    }
    // Fetch from paginated endpoint
    let cancelled = false;
    setLoading(true);
    axios
      .get(`${API_BASE}/datasets/${dataset.id}/rows`, {
        params: { skip: startIdx, limit: PAGE_SIZE },
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        if (!cancelled) setPageRows(res.data.rows || []);
      })
      .catch((err) => {
        console.error('Failed to fetch rows:', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dataset.id, startIdx, endIdx, previewCovers, dataset.data, token]);

  const goToPage = (p) => setPage(Math.max(1, Math.min(totalPages, p)));

  return (
    <div className="glass-card p-6 rounded-xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5" style={{ color: '#6366f1' }} />
          <h2 className="text-xl font-bold text-white">Raw Data</h2>
          <span className="text-sm text-gray-400 monospace">{totalRows.toLocaleString()} rows</span>
        </div>
        <div className="text-sm text-gray-400">
          Showing <span className="monospace text-white">{totalRows === 0 ? 0 : (startIdx + 1).toLocaleString()}</span>
          {' – '}
          <span className="monospace text-white">{endIdx.toLocaleString()}</span>
          {loading && <span className="ml-2 text-[#6366f1] text-xs">loading…</span>}
        </div>
      </div>

      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full" data-testid="data-table">
          <thead>
            <tr className="border-b" style={{ borderColor: '#1e1e2e' }}>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-12">#</th>
              {allColumns.map((col) => (
                <th
                  key={col}
                  className={`px-4 py-3 text-left text-sm font-semibold whitespace-nowrap ${
                    numericColumns.includes(col)
                      ? 'text-[#6366f1]'
                      : dateColumns.includes(col)
                        ? 'text-[#f59e0b]'
                        : 'text-white'
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, idx) => {
              const actualIdx = startIdx + idx;
              return (
                <tr
                  key={actualIdx}
                  data-testid={`data-row-${actualIdx}`}
                  className="border-b hover:bg-[#12121f] transition-colors"
                  style={{ borderColor: '#1e1e2e' }}
                >
                  <td className="px-4 py-3 text-xs text-gray-500 monospace">{actualIdx + 1}</td>
                  {allColumns.map((col) => {
                    const v = row[col];
                    const display = v === undefined || v === null || v === '' ? '-' : v.toString();
                    return (
                      <td
                        key={col}
                        className={`px-4 py-3 text-sm whitespace-nowrap max-w-xs truncate ${
                          numericColumns.includes(col)
                            ? 'text-gray-300 monospace font-medium'
                            : 'text-gray-400'
                        }`}
                        title={display}
                      >
                        {display}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t" style={{ borderColor: '#1e1e2e' }}>
          <span className="text-sm text-gray-400">
            Page <span className="monospace text-white">{page}</span> of{' '}
            <span className="monospace text-white">{totalPages.toLocaleString()}</span>
          </span>
          <div className="flex items-center gap-2">
            <button
              data-testid="page-prev-button"
              onClick={() => goToPage(page - 1)}
              disabled={page === 1 || loading}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-[#12121f] hover:bg-[#1a1a2e] text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm"
            >
              <ChevronLeft className="w-4 h-4" />
              Prev
            </button>
            <input
              data-testid="page-input"
              type="number"
              value={page}
              min={1}
              max={totalPages}
              onChange={(e) => goToPage(parseInt(e.target.value, 10) || 1)}
              className="w-20 px-2 py-2 rounded-lg bg-[#12121f] border border-[#1e1e2e] text-white text-sm text-center focus:outline-none focus:border-[#6366f1] monospace"
            />
            <button
              data-testid="page-next-button"
              onClick={() => goToPage(page + 1)}
              disabled={page === totalPages || loading}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-[#12121f] hover:bg-[#1a1a2e] text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataTable;
