function ScoreBar({ label, value, max }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="score-bar-row">
      <div className="score-bar-label">
        <span>{label}</span>
        <span>
          {value.toFixed(1)} / {max}
        </span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function CandidateCard({ result }) {
  const { candidate, score, github, integrity, eligibility, requirements_match: match, scoring_error } = result;

  return (
    <div className="card candidate-card">
      <div className="candidate-header">
        <div>
          <span className="rank-badge">#{result.rank}</span>
          <h3>{candidate.name || "(name not detected)"}</h3>
          <p className="candidate-email">{candidate.email || "no email detected"}</p>
        </div>
        {score && (
          <div className="total-score">
            <span className="total-score-number">{score.total.toFixed(1)}</span>
            <span className="total-score-label">/ 100</span>
          </div>
        )}
      </div>

      <span className="badge badge-eligible">Eligible</span>

      {scoring_error && (
        <div className="notice notice-warning">
          Scoring unavailable for this candidate: {scoring_error}
        </div>
      )}

      {score && (
        <div className="score-breakdown">
          <ScoreBar label="AI / Agentic / RAG" value={score.ai_agentic_rag_depth} max={40} />
          <ScoreBar label="Python & Backend" value={score.python_backend_engineering} max={30} />
          <ScoreBar label="Cloud / Deployment / Full Stack" value={score.cloud_deployment_fullstack} max={15} />
          <ScoreBar label="GitHub" value={score.github_activity} max={10} />
          <ScoreBar label="Engineering Depth" value={score.engineering_depth} max={5} />

          {score.penalties.length > 0 && (
            <div className="penalties">
              {score.penalties.map((p, i) => (
                <p key={i} className="penalty-line">
                  {p.points.toFixed(1)} pts &mdash; {p.reason}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {score && score.evidence.length > 0 && (
        <details className="evidence-details">
          <summary>Evidence ({score.evidence.length})</summary>
          <ul>
            {score.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}

      {github.status !== "disabled" && github.status !== "no_url" && (
        <div className="github-info">
          <strong>GitHub:</strong>{" "}
          {github.status === "ok" ? (
            <span>
              @{github.username} &middot; {github.public_repos} public repos &middot; {github.followers}{" "}
              followers
            </span>
          ) : (
            <span className="muted">unavailable ({github.status})</span>
          )}
        </div>
      )}

      {!integrity.is_clean && (
        <div className="notice notice-warning">
          Integrity warning: hidden/suspicious text detected in this PDF ({integrity.flags.join(", ")}).
          That text was excluded from scoring.
        </div>
      )}

      {match && (
        <div className="requirements-match">
          <strong>Requirements match:</strong>
          {match.required_skills_matched.length > 0 && (
            <p className="match-line match-good">Required matched: {match.required_skills_matched.join(", ")}</p>
          )}
          {match.required_skills_missing.length > 0 && (
            <p className="match-line match-bad">Required missing: {match.required_skills_missing.join(", ")}</p>
          )}
          {match.preferred_skills_matched.length > 0 && (
            <p className="match-line match-good">Preferred matched: {match.preferred_skills_matched.join(", ")}</p>
          )}
          {match.minimum_experience_years !== null && (
            <p className="match-line">
              Experience:{" "}
              {match.experience_years_detected !== null
                ? `${match.experience_years_detected} yrs detected`
                : "not detected in resume text"}{" "}
              (minimum required: {match.minimum_experience_years} yrs)
              {match.meets_minimum_experience === true && " ✓"}
              {match.meets_minimum_experience === false && " ✗"}
            </p>
          )}
        </div>
      )}

      <details className="evidence-details">
        <summary>Skills & projects</summary>
        <p>
          <strong>Skills:</strong> {candidate.skills.join(", ") || "none extracted"}
        </p>
        {candidate.projects.map((p, i) => (
          <div key={i} className="project-block">
            <strong>{p.name}</strong>
            <p>{p.description}</p>
          </div>
        ))}
      </details>
    </div>
  );
}
