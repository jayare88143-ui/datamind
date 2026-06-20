import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Database } from 'lucide-react';

const PAGE_SIZE = 50;

const DataTable = ({ dataset }) => {
  const data = dataset.data || [];
  const numericColumns = dataset.numeric_columns || [];
  const labelColumns = dataset.label_columns || [];
  const allColumns = [...labelColumns, ...numericColumns];

  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(data.length / PAGE_SIZE));
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, data.length);

  const paginatedData = useMemo(
    () => data.slice(startIdx, endIdx),
    [data, startIdx, endIdx]
  );

  const goToPage = (p) => {
    setPage(Math.max(1, Math.min(totalPages, p)));
  };

  return (
    <div className="glass-card p-6 rounded-xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5" style={{ color: '#6366f1' }} />
          <h2 className="text-xl font-bold text-white">Raw Data</h2>
          <span className="text-sm text-gray-400 monospace">
            {data.length.toLocaleString()} rows
          </span>
        </div>
        <div className="text-sm text-gray-400">
          Showing <span className="monospace text-white">{(startIdx + 1).toLocaleString()}</span>
          {' – '}
          <span className="monospace text-white">{endIdx.toLocaleString()}</span>
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
                  className={`px-4 py-3 text-left text-sm font-semibold ${
                    numericColumns.includes(col) ? 'text-[#6366f1]' : 'text-white'
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row, idx) => {
              const actualIdx = startIdx + idx;
              return (
                <tr
                  key={actualIdx}
                  data-testid={`data-row-${actualIdx}`}
                  className="border-b hover:bg-[#12121f] transition-colors"
                  style={{ borderColor: '#1e1e2e' }}
                >
                  <td className="px-4 py-3 text-xs text-gray-500 monospace">{actualIdx + 1}</td>
                  {allColumns.map((col) => (
                    <td
                      key={col}
                      className={`px-4 py-3 text-sm ${
                        numericColumns.includes(col)
                          ? 'text-gray-300 monospace font-medium'
                          : 'text-gray-400'
                      }`}
                    >
                      {row[col] !== undefined && row[col] !== null ? row[col].toString() : '-'}
                    </td>
                  ))}
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
            <span className="monospace text-white">{totalPages}</span>
          </span>
          <div className="flex items-center gap-2">
            <button
              data-testid="page-prev-button"
              onClick={() => goToPage(page - 1)}
              disabled={page === 1}
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
              onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
              className="w-16 px-2 py-2 rounded-lg bg-[#12121f] border border-[#1e1e2e] text-white text-sm text-center focus:outline-none focus:border-[#6366f1] monospace"
            />
            <button
              data-testid="page-next-button"
              onClick={() => goToPage(page + 1)}
              disabled={page === totalPages}
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
