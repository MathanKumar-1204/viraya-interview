/**
 * Viraya Company's Interview AI Bot - Setup Controller
 * Handles candidate resume upload, generates situational interview plan in the background,
 * and reveals the "Start Live Interview" button directly on the form page without navigation.
 */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("setupForm");
  const resumeInput = document.getElementById("resume_file");
  const resumePreview = document.getElementById("resumePreview");
  const resumeDropzone = document.getElementById("resumeDropzone");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const errorBox = document.getElementById("formErrorBox");
  const errorMessage = document.getElementById("formErrorMessage");
  const setupFormCard = document.getElementById("setupFormCard");
  const interviewReadyCard = document.getElementById("interviewReadyCard");
  const readyCandidateName = document.getElementById("readyCandidateName");
  const startLiveInterviewBtn = document.getElementById("startLiveInterviewBtn");

  function showError(msg) {
    if (errorMessage) errorMessage.textContent = msg;
    if (errorBox) {
      errorBox.style.display = "flex";
      errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function hideError() {
    if (errorBox) errorBox.style.display = "none";
  }

  // File Dropzone Interaction
  if (resumeDropzone && resumeInput) {
    resumeDropzone.addEventListener("click", () => {
      resumeInput.click();
    });

    ["dragenter", "dragover"].forEach(eventName => {
      resumeDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        resumeDropzone.style.borderColor = "var(--primary)";
        resumeDropzone.style.background = "#eef2ff";
      });
    });

    ["dragleave", "drop"].forEach(eventName => {
      resumeDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        resumeDropzone.style.borderColor = "var(--border-color)";
        resumeDropzone.style.background = "#fafafa";
      });
    });

    resumeDropzone.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        resumeInput.files = e.dataTransfer.files;
        handleFileSelection(resumeInput.files[0]);
      }
    });

    resumeInput.addEventListener("change", () => {
      if (resumeInput.files && resumeInput.files[0]) {
        handleFileSelection(resumeInput.files[0]);
      } else if (resumePreview) {
        resumePreview.style.display = "none";
      }
    });
  }

  function handleFileSelection(file) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showError(`File "${file.name}" exceeds the 10 MB limit. Please select a smaller resume.`);
      resumeInput.value = "";
      if (resumePreview) resumePreview.style.display = "none";
      return;
    }
    hideError();
    if (resumePreview) {
      resumePreview.innerHTML = `Selected: <b>${file.name}</b> (${(file.size / 1024).toFixed(1)} KB)`;
      resumePreview.style.display = "inline-flex";
    }
  }

  // Form submission
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideError();

      const candidateNameInput = document.getElementById("candidate_name");
      const candidateName = candidateNameInput ? candidateNameInput.value.trim() : "";
      const hasResume = resumeInput && resumeInput.files && resumeInput.files.length > 0;

      if (!candidateName) {
        showError("Please enter the candidate's full name.");
        return;
      }

      if (!hasResume) {
        showError("Please upload the candidate's resume (PDF or DOCX).");
        return;
      }

      const formData = new FormData(form);

      submitBtn.disabled = true;
      if (btnText) btnText.style.display = "none";
      if (btnSpinner) {
        btnSpinner.style.display = "inline";
        btnSpinner.textContent = "Uploading & Saving to MongoDB...";
      }

      try {
        // Step 1: Upload resume, save to MongoDB, and create interview
        const uploadRes = await fetch("/api/interviews", {
          method: "POST",
          body: formData,
          headers: { "Accept": "application/json" }
        });

        const uploadData = await uploadRes.json();
        if (!uploadRes.ok) {
          throw new Error(uploadData.error || "Failed to create interview record.");
        }

        const interviewId = uploadData.interview_id;
        if (uploadData.interview) {
          sessionStorage.setItem("interview_" + interviewId, JSON.stringify(uploadData.interview));
          sessionStorage.setItem("current_interview", JSON.stringify(uploadData.interview));
        }

        if (btnSpinner) {
          btnSpinner.textContent = "Generating Situational Interview Questions...";
        }

        // Step 2: Request structured interview planning in background
        const planRes = await fetch(`/api/interviews/${interviewId}/prepare`, {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json"
          }
        });

        const planData = await planRes.json();
        if (!planRes.ok) {
          throw new Error(planData.error || "Failed to generate interview plan.");
        }

        if (planData.interview) {
          sessionStorage.setItem("interview_" + interviewId, JSON.stringify(planData.interview));
          sessionStorage.setItem("current_interview", JSON.stringify(planData.interview));
        }

        // Step 3: Do NOT move to another page or reveal internal questions!
        // Instead, show the Start Live Interview button alone right on this form page.
        if (setupFormCard) setupFormCard.style.display = "none";
        if (readyCandidateName) readyCandidateName.textContent = candidateName;
        if (startLiveInterviewBtn) {
          startLiveInterviewBtn.href = `/interviews/${interviewId}/live`;
        }
        if (interviewReadyCard) {
          interviewReadyCard.style.display = "block";
          interviewReadyCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }

      } catch (err) {
        showError(err.message || "An unexpected error occurred during interview preparation.");
        submitBtn.disabled = false;
        if (btnText) btnText.style.display = "inline";
        if (btnSpinner) {
          btnSpinner.style.display = "none";
          btnSpinner.textContent = "Analyzing Resume & Preparing...";
        }
      }
    });
  }
});
