/**
 * Dashboard JavaScript handlers
 * Viraya Company's Interview AI Bot
 */
async function deleteInterview(interviewId) {
  if (!confirm("Are you sure you want to delete this interview record? This action cannot be undone.")) {
    return;
  }

  try {
    const response = await fetch(`/api/interviews/${interviewId}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' }
    });

    const data = await response.json();
    if (response.ok && data.success) {
      const row = document.getElementById(`interview-row-${interviewId}`);
      if (row) {
        row.style.transition = 'opacity 0.25s ease';
        row.style.opacity = '0';
        setTimeout(() => row.remove(), 250);
      } else {
        window.location.reload();
      }
    } else {
      alert(data.error || "Failed to delete interview.");
    }
  } catch (err) {
    alert("Network error: " + err.message);
  }
}
