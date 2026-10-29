/**
 * Interview Preparation JavaScript
 */
document.addEventListener("DOMContentLoaded", () => {
  const updateTitleBtn = document.getElementById("updateTitleBtn");
  const editJobTitle = document.getElementById("editJobTitle");
  const retryPlanBtn = document.getElementById("retryPlanBtn");
  const finalizeFromPrepBtn = document.getElementById("finalizeFromPrepBtn");
  const voiceEngineRadios = document.querySelectorAll('input[name="voice_engine_select"]');
  const savingBadge = document.getElementById("voiceEngineSavingBadge");

  // Handle Voice Engine switching
  voiceEngineRadios.forEach(radio => {
    radio.addEventListener("change", async () => {
      const selectedEngine = radio.value;

      // Update UI card borders
      document.querySelectorAll(".voice-engine-card").forEach(card => {
        card.style.borderColor = "var(--border-color)";
      });
      const parentLabel = radio.closest(".voice-engine-card");
      if (parentLabel) {
        parentLabel.style.borderColor = "var(--primary)";
      }

      if (savingBadge) {
        savingBadge.textContent = "Saving...";
        savingBadge.style.display = "inline-block";
      }

      try {
        const response = await fetch(`/api/interviews/${interviewId}/voice-engine`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({ voice_engine: selectedEngine })
        });

        const data = await response.json();
        if (response.ok && data.success) {
          if (savingBadge) {
            savingBadge.textContent = "Saved ✓";
            setTimeout(() => {
              savingBadge.style.display = "none";
            }, 1800);
          }

          // Update cached session
          const cached = sessionStorage.getItem("interview_" + interviewId);
          if (cached) {
            try {
              const obj = JSON.parse(cached);
              obj.voice_engine = selectedEngine;
              sessionStorage.setItem("interview_" + interviewId, JSON.stringify(obj));
              sessionStorage.setItem("current_interview", JSON.stringify(obj));
            } catch (_) {}
          }
        } else {
          alert(data.error || "Failed to update voice engine.");
          if (savingBadge) savingBadge.style.display = "none";
        }
      } catch (err) {
        console.error("Error updating voice engine:", err);
        if (savingBadge) savingBadge.style.display = "none";
      }
    });
  });

  if (updateTitleBtn && editJobTitle) {
    updateTitleBtn.addEventListener("click", async () => {
      const newTitle = editJobTitle.value.trim();
      if (!newTitle) {
        alert("Job title cannot be empty.");
        return;
      }

      updateTitleBtn.disabled = true;
      updateTitleBtn.textContent = "Saving...";

      try {
        const response = await fetch(`/api/interviews/${interviewId}/update-title`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({ job_title: newTitle })
        });

        const data = await response.json();
        if (response.ok && data.success) {
          updateTitleBtn.textContent = "Saved ✓";
          setTimeout(() => {
            updateTitleBtn.textContent = "Save Title Change";
            updateTitleBtn.disabled = false;
          }, 1500);
        } else {
          alert(data.error || "Failed to update job title.");
          updateTitleBtn.disabled = false;
          updateTitleBtn.textContent = "Save Title Change";
        }
      } catch (err) {
        alert("Error updating title: " + err.message);
        updateTitleBtn.disabled = false;
        updateTitleBtn.textContent = "Save Title Change";
      }
    });
  }

  if (finalizeFromPrepBtn) {
    finalizeFromPrepBtn.addEventListener("click", async () => {
      finalizeFromPrepBtn.disabled = true;
      finalizeFromPrepBtn.textContent = "Synthesizing Evaluation Report...";

      try {
        const response = await fetch(`/api/interviews/${interviewId}/finalize`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({})
        });

        const data = await response.json();
        if (response.ok && data.success) {
          window.location.href = data.report_url || `/reports/${interviewId}`;
        } else {
          alert(data.error || "Failed to finalize evaluation.");
          finalizeFromPrepBtn.disabled = false;
          finalizeFromPrepBtn.textContent = "⚡ Generate Evaluation Report Now";
        }
      } catch (err) {
        alert("Evaluation request failed: " + err.message);
        finalizeFromPrepBtn.disabled = false;
        finalizeFromPrepBtn.textContent = "⚡ Generate Evaluation Report Now";
      }
    });
  }

  if (retryPlanBtn) {
    retryPlanBtn.addEventListener("click", async () => {
      retryPlanBtn.disabled = true;
      retryPlanBtn.textContent = "Generating Plan...";

      try {
        const response = await fetch(`/api/interviews/${interviewId}/prepare`, {
          method: "POST",
          headers: { "Accept": "application/json" }
        });

        const data = await response.json();
        if (response.ok && data.success) {
          if (data.interview) {
            sessionStorage.setItem("interview_" + interviewId, JSON.stringify(data.interview));
            sessionStorage.setItem("current_interview", JSON.stringify(data.interview));
          }
          window.location.reload();
        } else {
          alert(data.error || "Failed to generate interview plan.");
          retryPlanBtn.disabled = false;
          retryPlanBtn.textContent = "⚡ Generate Interview Plan";
        }
      } catch (err) {
        alert("Network error: " + err.message);
        retryPlanBtn.disabled = false;
        retryPlanBtn.textContent = "⚡ Generate Interview Plan";
      }
    });
  }
});
