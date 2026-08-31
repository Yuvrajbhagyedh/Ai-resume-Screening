const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Calls POST /api/screen. Only appends optional fields when they actually
 * have a value -- an empty string sent for a numeric form field would fail
 * validation server-side, so we simply omit unset fields entirely.
 */
export async function screenCandidates({
  resumeFiles,
  jobDescriptionText,
  jobDescriptionFile,
  requiredSkills,
  preferredSkills,
  minimumExperienceYears,
  scorer,
}) {
  const formData = new FormData();
  for (const file of resumeFiles) {
    formData.append("resumes", file);
  }
  if (jobDescriptionText && jobDescriptionText.trim()) {
    formData.append("job_description_text", jobDescriptionText.trim());
  }
  if (jobDescriptionFile) {
    formData.append("job_description_file", jobDescriptionFile);
  }
  if (requiredSkills && requiredSkills.trim()) {
    formData.append("required_skills", requiredSkills.trim());
  }
  if (preferredSkills && preferredSkills.trim()) {
    formData.append("preferred_skills", preferredSkills.trim());
  }
  if (minimumExperienceYears !== "" && minimumExperienceYears !== null && minimumExperienceYears !== undefined) {
    formData.append("minimum_experience_years", String(minimumExperienceYears));
  }
  formData.append("scorer", scorer || "deterministic");

  const response = await fetch(`${API_BASE_URL}/api/screen`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response body wasn't JSON -- keep the generic message
    }
    throw new Error(detail);
  }

  return response.json();
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) throw new Error("Health check failed");
  return response.json();
}
