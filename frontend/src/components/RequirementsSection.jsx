export default function RequirementsSection({
  requiredSkills,
  onRequiredSkillsChange,
  preferredSkills,
  onPreferredSkillsChange,
  minimumExperienceYears,
  onMinimumExperienceYearsChange,
}) {
  return (
    <div className="section">
      <h2>Custom Requirements (optional)</h2>
      <p className="section-hint">
        These don't change eligibility or scoring -- they add a simple match indicator to each
        candidate's results.
      </p>
      <div className="field-grid">
        <label className="field">
          <span>Required skills</span>
          <input
            type="text"
            placeholder="e.g. Python, FastAPI, LangChain"
            value={requiredSkills}
            onChange={(e) => onRequiredSkillsChange(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Preferred skills</span>
          <input
            type="text"
            placeholder="e.g. AWS, Docker"
            value={preferredSkills}
            onChange={(e) => onPreferredSkillsChange(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Minimum experience (years)</span>
          <input
            type="number"
            min="0"
            step="0.5"
            placeholder="e.g. 2"
            value={minimumExperienceYears}
            onChange={(e) => onMinimumExperienceYearsChange(e.target.value)}
          />
        </label>
      </div>
    </div>
  );
}
