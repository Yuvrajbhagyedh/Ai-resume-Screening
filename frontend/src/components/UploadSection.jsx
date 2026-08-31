import { useRef, useState } from "react";

const MAX_FILES = 50;
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];

function hasAcceptedExtension(file) {
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function UploadSection({ files, onFilesChange }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [warning, setWarning] = useState("");

  function addFiles(newFiles) {
    const incoming = Array.from(newFiles);
    const accepted = incoming.filter(hasAcceptedExtension);
    const rejectedCount = incoming.length - accepted.length;

    const existingKeys = new Set(files.map((f) => `${f.name}-${f.size}`));
    const deduped = accepted.filter((f) => !existingKeys.has(`${f.name}-${f.size}`));

    const combined = [...files, ...deduped];
    const overflow = combined.length - MAX_FILES;
    const finalFiles = overflow > 0 ? combined.slice(0, MAX_FILES) : combined;

    const messages = [];
    if (rejectedCount > 0) {
      messages.push(`${rejectedCount} file(s) skipped -- only .pdf, .docx, .txt are accepted.`);
    }
    if (overflow > 0) {
      messages.push(`Only the first ${MAX_FILES} files were kept (limit reached).`);
    }
    setWarning(messages.join(" "));
    onFilesChange(finalFiles);
  }

  function handleInputChange(e) {
    if (e.target.files?.length) addFiles(e.target.files);
    e.target.value = "";
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  }

  function removeFile(index) {
    setWarning("");
    onFilesChange(files.filter((_, i) => i !== index));
  }

  function clearAll() {
    setWarning("");
    onFilesChange([]);
  }

  return (
    <div className="section">
      <h2>Resumes</h2>
      <div
        className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
      >
        <p>Drag and drop resumes here, or click to browse</p>
        <p className="dropzone-hint">PDF required &middot; DOCX/TXT optional &middot; up to {MAX_FILES} files</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          multiple
          hidden
          onChange={handleInputChange}
        />
      </div>

      {warning && <p className="warning-text">{warning}</p>}

      <div className="file-list-header">
        <span>
          {files.length} / {MAX_FILES} resumes
        </span>
        {files.length > 0 && (
          <button type="button" className="link-button" onClick={clearAll}>
            Clear all
          </button>
        )}
      </div>

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.size}-${index}`} className="file-list-item">
              <span className="file-name">{file.name}</span>
              <button
                type="button"
                className="remove-button"
                onClick={() => removeFile(index)}
                aria-label={`Remove ${file.name}`}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
