export default function ResultsSummary({ result }) {
  return (
    <div className="summary-grid">
      <div className="summary-card">
        <span className="summary-number">{result.total_files_discovered}</span>
        <span className="summary-label">Total resumes</span>
      </div>
      <div className="summary-card summary-eligible">
        <span className="summary-number">{result.eligible_count}</span>
        <span className="summary-label">Eligible</span>
      </div>
      <div className="summary-card summary-ineligible">
        <span className="summary-number">{result.ineligible_count}</span>
        <span className="summary-label">Ineligible</span>
      </div>
      <div className="summary-card summary-failed">
        <span className="summary-number">{result.failed_count}</span>
        <span className="summary-label">Failed</span>
      </div>
    </div>
  );
}
