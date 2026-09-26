import type { QueryResult } from "@/lib/types";

type QueryResultDetailsProps = {
  query: QueryResult;
};

function formatCell(value: unknown): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat("vi-VN", {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  }
  return String(value ?? "—");
}

export function QueryResultDetails({ query }: QueryResultDetailsProps) {
  const canShowTable = query.rows.length > 0 && !(query.rows.length === 1 && query.columns.length === 1);

  return (
    <div className="query-details">
      {canShowTable && (
        <details>
          <summary>Xem dữ liệu <span>{query.row_count} hàng</span></summary>
          <div className="query-table-scroll">
            <table>
              <thead><tr>{query.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
              <tbody>
                {query.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>{query.columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {query.sql && (
        <details>
          <summary>Xem SQL</summary>
          <pre><code>{query.sql}</code></pre>
        </details>
      )}
      {query.execution_time_ms !== null && query.execution_time_ms !== undefined && (
        <p className="query-duration">Thời gian truy vấn: {query.execution_time_ms.toLocaleString("vi-VN")} ms</p>
      )}
    </div>
  );
}
