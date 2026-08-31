import { useState } from "react";
import UploadSection from "./components/UploadSection.jsx";
import JobDescriptionSection from "./components/JobDescriptionSection.jsx";
import RequirementsSection from "./components/RequirementsSection.jsx";
import ScorerSelector from "./components/ScorerSelector.jsx";
import ResultsSummary from "./components/ResultsSummary.jsx";
import CandidateCard from "./components/CandidateCard.jsx";
import IneligibleSection from "./components/IneligibleSection.jsx";
import { screenCandidates } from "./api.js";

export default function App() {
  const [resumeFiles, setResumeFiles] = useState([]);
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [jobDescriptionFile, setJobDescriptionFile] = useState(null);
  const [requiredSkills, setRequiredSkills] = useState("");
  const [preferredSkills, setPreferredSkills] = useState("");
  const [minimumExperienceYears, setMinimumExperienceYears] = useState("");
  const [scorer, setScorer] = useState("deterministic");

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleSubmit() {
    if (resumeFiles.length === 0) {
      setError("Please add at least one resume before screening.");
      return;
    }
    setError("");
    setIsLoading(true);
    try {
      const response = await screenCandidates({
        resumeFiles,
        jobDescriptionText,
        jobDescriptionFile,
        requiredSkills,
        preferredSkills,
        minimumExperienceYears,
        scorer,
      });
      setResult(response);
    } catch (err) {
      setError(err.message || "Something went wrong while screening candidates.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleStartOver() {
    setResult(null);
    setError("");
  }

  if (result) {
    return (
      <div className="page">
        <header className="app-header">
          <h1>AI Resume Screening</h1>
          <button type="button" className="secondary-button" onClick={handleStartOver}>
            &larr; Screen more candidates
          </button>
        </header>

        <ResultsSummary result={result} />

        <div className="section">
          <h2>Ranked Candidates</h2>
          {result.ranked.length === 0 ? (
            <p className="muted">No eligible candidates in this batch.</p>
          ) : (
            <div className="candidate-list">
              {result.ranked.map((r) => (
                <CandidateCard key={r.source_file} result={r} />
              ))}
            </div>
          )}
        </div>

        <IneligibleSection ineligible={result.ineligible} failures={result.failures} />
      </div>
    );
  }

  return (
    <div className="page">
      <header className="app-header">
        <h1>AI Resume Screening</h1>
      </header>

      <UploadSection files={resumeFiles} onFilesChange={setResumeFiles} />

      <JobDescriptionSection
        text={jobDescriptionText}
        onTextChange={setJobDescriptionText}
        file={jobDescriptionFile}
        onFileChange={setJobDescriptionFile}
      />

      <RequirementsSection
        requiredSkills={requiredSkills}
        onRequiredSkillsChange={setRequiredSkills}
        preferredSkills={preferredSkills}
        onPreferredSkillsChange={setPreferredSkills}
        minimumExperienceYears={minimumExperienceYears}
        onMinimumExperienceYearsChange={setMinimumExperienceYears}
      />

      <ScorerSelector scorer={scorer} onScorerChange={setScorer} />

      {error && <p className="error-text">{error}</p>}

      <button type="button" className="primary-button" onClick={handleSubmit} disabled={isLoading}>
        {isLoading ? "Screening..." : "Screen Candidates"}
      </button>
    </div>
  );
}
