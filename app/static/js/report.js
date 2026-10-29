/**
 * Report Page JavaScript
 */
document.addEventListener("DOMContentLoaded", () => {
  const header = document.getElementById("reportTranscriptHeader");
  const panel = document.getElementById("reportTranscriptPanel");
  const toggleBtn = document.getElementById("reportTranscriptToggleBtn");

  if (header && panel && toggleBtn) {
    header.addEventListener("click", () => {
      const isVisible = panel.style.display !== "none";
      panel.style.display = isVisible ? "none" : "block";
      toggleBtn.textContent = isVisible ? "Show Transcript ▼" : "Hide Transcript ▲";
    });
  }
});
