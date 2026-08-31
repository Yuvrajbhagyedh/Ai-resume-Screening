function IneligibleRow({ result }) {
  return (
    <div className="card ineligible-card">
      <div className="ineligible-header">
        <span>{result.candidate.name || result.source_file}</span>
        <span className="badge badge-rejected">Eligible: false</span>
      </div>
      <ul className="reason-list">
        {result.eligibility.rejection_reasons.map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>
      {!result.integrity.is_clean && (
        <p className="notice notice-warning">
          Integrity warning: hidden/suspicious text detected ({result.integrity.flags.join(", ")}).
        </p>
      )}
    </div>
  );
}

function FailedRow({ failure }) {
  return (
    <div className="card failed-card">
      <div className="ineligible-header">
        <span>{failure.source_file}</span>
        <span className="badge badge-failed">Processing failed</span>
      </div>
      <p className="reason-list">{failure.error}</p>
    </div>
  );
}

export default function IneligibleSection({ ineligible, failures }) {
  if (ineligible.length === 0 && failures.length === 0) return null;

  return (
    <div className="section">
      <h2>Ineligible / Failed</h2>
      {ineligible.map((result, i) => (
        <IneligibleRow key={`ineligible-${i}`} result={result} />
      ))}
      {failures.map((failure, i) => (
        <FailedRow key={`failed-${i}`} failure={failure} />
      ))}
    </div>
  );
}
