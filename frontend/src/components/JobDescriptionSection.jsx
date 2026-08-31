export default function JobDescriptionSection({ text, onTextChange, file, onFileChange }) {
  return (
    <div className="section">
      <h2>Job Description (optional)</h2>
      <p className="section-hint">Paste the JD, upload a file, or leave this blank.</p>
      <textarea
        className="textarea"
        rows={5}
        placeholder="Paste job description here..."
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
      />
      <div className="file-input-row">
        <label className="file-input-label">
          {file ? file.name : "Upload JD file (.pdf, .docx, .txt)"}
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            hidden
            onChange={(e) => onFileChange(e.target.files?.[0] || null)}
          />
        </label>
        {file && (
          <button type="button" className="link-button" onClick={() => onFileChange(null)}>
            Remove
          </button>
        )}
      </div>
    </div>
  );
}
