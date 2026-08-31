export default function ScorerSelector({ scorer, onScorerChange }) {
  return (
    <div className="section">
      <h2>Scoring</h2>
      <div className="scorer-options">
        <label className="radio-option">
          <input
            type="radio"
            name="scorer"
            value="deterministic"
            checked={scorer === "deterministic"}
            onChange={() => onScorerChange("deterministic")}
          />
          <span>
            <strong>Deterministic</strong> -- rule-based scoring, no external API calls (default)
          </span>
        </label>
        <label className="radio-option">
          <input
            type="radio"
            name="scorer"
            value="gemini"
            checked={scorer === "gemini"}
            onChange={() => onScorerChange("gemini")}
          />
          <span>
            <strong>Gemini</strong> -- semantic evaluation of project depth via the Gemini API
            (requires a server-side API key; eligibility is always decided deterministically
            either way)
          </span>
        </label>
      </div>
    </div>
  );
}
