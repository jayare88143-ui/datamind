import React from 'react';

const DataTable = ({ dataset }) => {
  const data = dataset.data || [];
  const numericColumns = dataset.numeric_columns || [];
  const labelColumns = dataset.label_columns || [];
  const allColumns = [...labelColumns, ...numericColumns];

  return (
    <div className="glass-card p-6 rounded-xl">
      <h2 className="text-xl font-bold text-white mb-6">Raw Data</h2>
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full" data-testid="data-table">
          <thead>
            <tr className="border-b" style={{ borderColor: '#1e1e2e' }}>
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
            {data.map((row, idx) => (
              <tr
                key={idx}
                data-testid={`data-row-${idx}`}
                className="border-b hover:bg-[#12121f] transition-colors"
                style={{ borderColor: '#1e1e2e' }}
              >
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
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DataTable;
