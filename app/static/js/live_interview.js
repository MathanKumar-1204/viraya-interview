/**
 * Live Spoken Interview Session Controller
 * Supports dual live voice engines:
 * 1. ElevenLabs Conversational AI Web SDK (@elevenlabs/client)
 * 2. Gemini Flash Live Voice Engine (Multimodal turn-taking with browser speech synthesis & recognition)
 */

import { Conversation } from "https://cdn.jsdelivr.net/npm/@elevenlabs/client/+esm";

let conversationInstance = null;
let timerInterval = null;
let elapsedSeconds = 0;
let isCallActive = false;
let isFinalizing = false;
let transcriptTurns = [];
let conversationId = null;

// Gemini Flash Live voice states
let isAlexSpeaking = false;
let isWaitingForAiReply = false;
let recognitionInstance = null;
let isRecognizing = false;
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

document.addEventListener("DOMContentLoaded", () => {
  const startBtn = document.getElementById("startInterviewBtn");
  const endBtn = document.getElementById("endInterviewBtn");
  const voiceOrb = document.getElementById("voiceOrb");
  const orbIcon = document.getElementById("orbIcon");
  const connectionBadge = document.getElementById("connectionBadge");
  const studioStateTitle = document.getElementById("studioStateTitle");
  const studioStateSubtitle = document.getElementById("studioStateSubtitle");
  const timerDisplay = document.getElementById("timerDisplay");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressPercent = document.getElementById("progressPercent");
  const transcriptBox = document.getElementById("transcriptBox");
  const turnCounter = document.getElementById("turnCounter");
  const emptyTranscriptMsg = document.getElementById("emptyTranscriptMsg");
  const transcriptToggleBtn = document.getElementById("transcriptToggleBtn");
  const transcriptToggleHeader = document.getElementById("transcriptToggleHeader");
  const transcriptPanelBody = document.getElementById("transcriptPanelBody");
  const finalizingModal = document.getElementById("finalizingModal");
  const audioStatusDot = document.getElementById("audioStatusDot");
  const audioStatusText = document.getElementById("audioStatusText");

  // Gemini Live speech monitor & feedback elements
  const liveVoiceMonitor = document.getElementById("liveVoiceMonitor");
  const liveMonitorStateText = document.getElementById("liveMonitorStateText");
  const liveMonitorDot = document.getElementById("liveMonitorDot");
  const liveTranscriptDisplay = document.getElementById("liveTranscriptDisplay");
  const livePauseIndicator = document.getElementById("livePauseIndicator");
  const doneSpeakingBtn = document.getElementById("doneSpeakingBtn");
  const braveSpeechNotice = document.getElementById("braveSpeechNotice");
  const voiceFallbackInput = document.getElementById("voiceFallbackInput");
  const voiceFallbackTextInput = document.getElementById("voiceFallbackTextInput");
  const voiceFallbackSendBtn = document.getElementById("voiceFallbackSendBtn");

  let currentSpokenCandidateText = "";

  // Pre-load synthesis voices
  if (typeof window !== "undefined" && window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }

  // Utility to extract clean speech string from potential JSON wrappers
  function extractCleanSpokenText(text) {
    if (!text) return "";
    let cleaned = String(text).trim();
    if (cleaned.startsWith("```")) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
    }
    if ((cleaned.startsWith("{") && cleaned.endsWith("}")) || cleaned.includes('"response"') || cleaned.includes('"message"')) {
      try {
        const parsed = JSON.parse(cleaned);
        if (parsed.response && typeof parsed.response === "string") return parsed.response.trim();
        if (parsed.message && typeof parsed.message === "string") return parsed.message.trim();
        if (parsed.text && typeof parsed.text === "string") return parsed.text.trim();
        if (parsed.content && typeof parsed.content === "string") return parsed.content.trim();
        for (const val of Object.values(parsed)) {
          if (typeof val === "string") return val.trim();
        }
      } catch (_) {
        const m = cleaned.match(/"(?:response|message|text|content)"\s*:\s*"([^"]+)"/);
        if (m && m[1]) return m[1].replace(/\\"/g, '"').trim();
      }
    }
    if ((cleaned.startsWith('"') && cleaned.endsWith('"')) || (cleaned.startsWith("'") && cleaned.endsWith("'"))) {
      cleaned = cleaned.slice(1, -1).trim();
    }
    return cleaned;
  }

  // Format seconds to MM:SS
  function formatTime(totalSecs) {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  // Update timer display & progress bar
  function tickTimer() {
    elapsedSeconds++;
    if (timerDisplay) {
      timerDisplay.textContent = formatTime(elapsedSeconds);
    }

    const totalSeconds = (targetDurationMinutes || 15) * 60;
    const pct = Math.min(100, Math.round((elapsedSeconds / totalSeconds) * 100));
    if (progressBarFill) {
      progressBarFill.style.width = `${pct}%`;
    }
    if (progressPercent) {
      progressPercent.textContent = `${pct}% Elapsed`;
    }
  }

  function startTimer() {
    if (!timerInterval) {
      timerInterval = setInterval(tickTimer, 1000);
    }
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // Set audio status pill state
  function updateAudioStatus(text, dotColor) {
    if (audioStatusText) audioStatusText.textContent = text;
    if (audioStatusDot) audioStatusDot.style.backgroundColor = dotColor;
  }

  // Reset Start Button
  function resetStartButton(message) {
    cleanupSarvamVoice();
    const isConfigured = (voiceEngine === "gemini_live") 
      ? isGeminiLiveConfigured 
      : (voiceEngine === "openai_realtime")
        ? isOpenaiRealtimeConfigured
        : (voiceEngine === "sarvam")
          ? isSarvamConfigured
          : isElevenLabsConfigured;
    const defaultMsg = voiceEngine === "gemini_live" 
      ? "▶️ Start Interview Call (Gemini Flash Live)" 
      : voiceEngine === "openai_realtime"
        ? "▶️ Start Interview Call (OpenAI Realtime WebRTC)"
        : (voiceEngine === "sarvam")
          ? "▶️ Start Interview Call (Sarvam AI Voice)"
          : "▶️ Start Interview Call (ElevenLabs AI)";
    if (startBtn) {
      startBtn.disabled = !isConfigured;
      startBtn.style.display = "inline-flex";
      startBtn.textContent = message || defaultMsg;
    }
    if (endBtn) {
      endBtn.style.display = "none";
    }
    if (connectionBadge) {
      connectionBadge.className = "badge badge-gray";
      connectionBadge.textContent = "Not Connected";
    }
    if (liveVoiceMonitor) {
      liveVoiceMonitor.style.display = "none";
    }
    if (doneSpeakingBtn) {
      doneSpeakingBtn.style.display = "none";
    }
    updateAudioStatus("Microphone & audio ready", "#94a3b8");
  }

  // Append a turn to transcript
  function appendTranscriptTurn(role, text) {
    const cleanText = extractCleanSpokenText(text);
    if (!cleanText) return;

    if (emptyTranscriptMsg) {
      emptyTranscriptMsg.style.display = "none";
    }

    const cleanRole = (role === "agent" || role === "interviewer" || role === "ai") ? "interviewer" : "candidate";
    const turn = {
      role: cleanRole,
      message: cleanText,
      time_in_call_secs: elapsedSeconds
    };
    transcriptTurns.push(turn);

    const msgEl = document.createElement("div");
    msgEl.className = `transcript-message ${cleanRole}`;

    const roleLabel = cleanRole === "interviewer" ? "Alex (AI Interviewer)" : (candidateName || "Candidate");
    msgEl.innerHTML = `
      <div class="message-role">${escapeHtml(roleLabel)} <span style="font-weight: normal; font-size: 0.7rem; color: var(--text-muted);">• ${formatTime(elapsedSeconds)}</span></div>
      <div>${escapeHtml(cleanText)}</div>
    `;

    if (transcriptBox) {
      transcriptBox.appendChild(msgEl);
      transcriptBox.scrollTop = transcriptBox.scrollHeight;
    }

    if (turnCounter) {
      turnCounter.textContent = `${transcriptTurns.length} exchange${transcriptTurns.length === 1 ? "" : "s"}`;
    }

    // Check if interviewer has asked all questions and completed the interview
    checkIfInterviewCompleted(cleanRole, cleanText);

    // Sync turns with server in background
    syncTranscriptToServer();
  }

  let autoEndTriggered = false;

  function checkIfInterviewCompleted(cleanRole, cleanText) {
    if (autoEndTriggered || isFinalizing) return;
    if (cleanRole !== "interviewer") return;

    const lower = cleanText.toLowerCase();

    // Check for closing/completion statements from the bot
    const completionPhrases = [
      "that concludes all our interview questions",
      "that concludes our interview",
      "that wraps up all our questions",
      "that wraps up our interview",
      "that wraps up all the questions",
      "that's all the questions i have",
      "that is all the questions i have",
      "all our questions for today",
      "evaluation report is now being generated",
      "report is now being generated",
      "report is being prepared",
      "evaluation report is now being prepared",
      "concludes the interview",
      "completed all our questions"
    ];

    const hasCompletionPhrase = completionPhrases.some(phrase => lower.includes(phrase));
    const candidateTurnsCount = transcriptTurns.filter(t => t.role === "candidate").length;
    const isAlexClosing = (lower.includes("conclude") || lower.includes("wrap up") || lower.includes("thank you")) &&
                          (lower.includes("report") || lower.includes("questions") || lower.includes("today"));

    if (hasCompletionPhrase || (candidateTurnsCount >= 3 && isAlexClosing)) {
      console.log("[Interview] Auto-completion triggered by interviewer wrap-up message:", cleanText);
      autoEndTriggered = true;
      triggerAutoFinalization();
    }
  }

  function triggerAutoFinalization() {
    updateAudioStatus("Interview completed. Calling off session and preparing evaluation report...", "#10b981");
    if (connectionBadge) {
      connectionBadge.className = "badge badge-success";
      connectionBadge.textContent = "Interview Completed";
    }
    if (studioStateTitle) {
      studioStateTitle.textContent = "Interview Completed";
    }
    if (studioStateSubtitle) {
      studioStateSubtitle.textContent = "Alex has asked all questions. Calling off the session and synthesizing your evaluation report...";
    }

    // Wait 3.5 seconds for final speech synthesis audio to finish playing, then finalize and redirect
    setTimeout(async () => {
      if (!isFinalizing) {
        await finalizeAndRedirect("completed");
      }
    }, 3500);
  }

  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
  }

  let syncTimeout = null;
  function syncTranscriptToServer() {
    clearTimeout(syncTimeout);
    syncTimeout = setTimeout(async () => {
      try {
        await fetch(`/api/interviews/${interviewId}/transcript`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transcript: transcriptTurns,
            conversation_id: conversationId
          })
        });
      } catch (e) {
        console.warn("Background transcript sync failed:", e);
      }
    }, 400);
  }

  // Toggle Transcript panel
  if (transcriptToggleHeader && transcriptPanelBody) {
    transcriptToggleHeader.addEventListener("click", () => {
      const isVisible = transcriptPanelBody.style.display !== "none";
      transcriptPanelBody.style.display = isVisible ? "none" : "block";
      if (transcriptToggleBtn) {
        transcriptToggleBtn.textContent = isVisible ? "Expand ▼" : "Collapse ▲";
      }
    });
  }

  // =========================================================================
  // GEMINI FLASH LIVE VOICE ENGINE IMPLEMENTATION
  // =========================================================================

  function speakGeminiTurn(text, onComplete) {
    const cleanSpeech = extractCleanSpokenText(text);
    if (!cleanSpeech) {
      if (onComplete) onComplete();
      return;
    }

    isAlexSpeaking = true;
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }

    // Stop candidate recognition while Alex speaks to prevent self-echo
    stopGeminiRecognition();

    if (voiceOrb) voiceOrb.className = "pulsing-orb speaking";
    if (orbIcon) orbIcon.textContent = "🎙️";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-indigo";
      connectionBadge.textContent = "Alex is Speaking";
    }
    updateAudioStatus("Alex is speaking aloud...", "#6366f1");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🔊 Alex is speaking aloud...";
    if (liveMonitorDot) liveMonitorDot.style.background = "#6366f1";
    if (liveTranscriptDisplay) liveTranscriptDisplay.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">(Alex is speaking...)</span>';
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    if (!window.speechSynthesis) {
      // Browser does not support speech synthesis
      isAlexSpeaking = false;
      if (onComplete) onComplete();
      return;
    }

    const utter = new SpeechSynthesisUtterance(cleanSpeech);
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => 
      v.lang.startsWith("en") && (
        v.name.includes("Google") || 
        v.name.includes("Natural") || 
        v.name.includes("Samantha") || 
        v.name.includes("David") || 
        v.name.includes("Daniel")
      )
    ) || voices.find(v => v.lang.startsWith("en"));

    if (preferredVoice) {
      utter.voice = preferredVoice;
    }
    utter.rate = 1.0;
    utter.pitch = 1.0;

    let hasEnded = false;
    const finalizeTurn = () => {
      if (hasEnded) return;
      hasEnded = true;
      isAlexSpeaking = false;
      if (!isCallActive) return;

      if (voiceOrb) voiceOrb.className = "pulsing-orb listening";
      if (orbIcon) orbIcon.textContent = "🗣️";
      if (connectionBadge) {
        connectionBadge.className = "badge badge-emerald";
        connectionBadge.textContent = "Listening to You";
      }
      updateAudioStatus("Listening • Speak into your microphone...", "#10b981");

      if (liveMonitorStateText) liveMonitorStateText.textContent = "🎙️ Listening to you... Speak into your microphone";
      if (liveMonitorDot) liveMonitorDot.style.background = "#10b981";
      if (liveTranscriptDisplay) liveTranscriptDisplay.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">(Alex is listening... Speak your answer now)</span>';
      currentSpokenCandidateText = "";

      if (onComplete) onComplete();
    };

    utter.onend = finalizeTurn;
    utter.onerror = finalizeTurn;

    // Safety timeout in case speech synthesis stalls
    const wordCount = cleanSpeech.split(" ").length;
    const estimatedDurationMs = Math.max(2500, (wordCount / 2.5) * 1000 + 1500);
    setTimeout(finalizeTurn, estimatedDurationMs);

    window.speechSynthesis.speak(utter);
  }

  function setupGeminiRecognition() {
    if (voiceEngine === "sarvam") return;
    if (!SpeechRecognition) {
      console.warn("SpeechRecognition not supported in this browser.");
      updateAudioStatus("Speech recognition unavailable. Please use Chrome, Edge, or enable speech in Brave settings.", "#ef4444");
      if (braveSpeechNotice) braveSpeechNotice.style.display = "flex";
      if (voiceFallbackInput) voiceFallbackInput.style.display = "block";
      return;
    }

    if (recognitionInstance) return;

    try {
      recognitionInstance = new SpeechRecognition();
      recognitionInstance.continuous = true;
      recognitionInstance.interimResults = true;
      recognitionInstance.lang = "en-US";

      let speechSilenceTimer = null;
      let finalAccumulated = "";

      recognitionInstance.onresult = (event) => {
        if (!isCallActive || isAlexSpeaking || isWaitingForAiReply) return;

        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalAccumulated += " " + event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }

        const candidateText = (finalAccumulated + " " + interim).trim();
        if (candidateText) {
          currentSpokenCandidateText = candidateText;
          updateAudioStatus(`🎙️ Hearing you: "${candidateText.slice(-35)}"`, "#10b981");

          if (liveMonitorStateText) liveMonitorStateText.textContent = "🗣️ Hearing you speak...";
          if (liveMonitorDot) liveMonitorDot.style.background = "#10b981";
          if (liveTranscriptDisplay) {
            liveTranscriptDisplay.textContent = `"${candidateText}"`;
          }
          if (doneSpeakingBtn) {
            doneSpeakingBtn.style.display = "inline-flex";
          }
          if (livePauseIndicator) {
            livePauseIndicator.style.display = "block";
            livePauseIndicator.textContent = "⏳ Pause detected — submitting answer to Alex...";
          }

          clearTimeout(speechSilenceTimer);
          // Automatically send turn when candidate pauses for 1.3 seconds
          speechSilenceTimer = setTimeout(() => {
            if (candidateText && isCallActive && !isAlexSpeaking && !isWaitingForAiReply) {
              const toSend = candidateText;
              finalAccumulated = "";
              currentSpokenCandidateText = "";
              sendCandidateTurnToGemini(toSend);
            }
          }, 1300);
        }
      };

      recognitionInstance.onerror = (e) => {
        if (e.error === "no-speech") return;
        console.warn("Speech recognition notice:", e.error);

        // Catch Brave or browser policy network / permission blocks
        if (e.error === "network" || e.error === "not-allowed" || e.error === "service-not-allowed") {
          if (braveSpeechNotice) braveSpeechNotice.style.display = "flex";
          if (voiceFallbackInput) voiceFallbackInput.style.display = "block";
          updateAudioStatus("Speech recognition service blocked (check Brave settings or use input below)", "#ef4444");
        }
      };

      recognitionInstance.onend = () => {
        isRecognizing = false;
        if (isCallActive && !isAlexSpeaking && !isWaitingForAiReply) {
          try {
            recognitionInstance.start();
            isRecognizing = true;
          } catch (_) {}
        }
      };

    } catch (e) {
      console.warn("Speech recognition initialization error:", e);
      if (braveSpeechNotice) braveSpeechNotice.style.display = "flex";
      if (voiceFallbackInput) voiceFallbackInput.style.display = "block";
    }
  }

  // Handle explicit "Done Speaking" button click (candidate finishes talking & sends immediately)
  if (doneSpeakingBtn) {
    doneSpeakingBtn.addEventListener("click", () => {
      if (voiceEngine === "sarvam") {
        if (sarvamMediaRecorder && sarvamMediaRecorder.state === "recording") {
          sarvamHasSpokenInTurn = true;
          stopSarvamRecordingAndSend();
        }
        return;
      }
      if (currentSpokenCandidateText && isCallActive && !isWaitingForAiReply) {
        const toSend = currentSpokenCandidateText;
        currentSpokenCandidateText = "";
        sendCandidateTurnToGemini(toSend);
      }
    });
  }

  // Handle fallback manual input if speech recognition is blocked in browser
  if (voiceFallbackSendBtn && voiceFallbackTextInput) {
    const submitFallback = () => {
      const text = voiceFallbackTextInput.value.trim();
      if (text && isCallActive && !isWaitingForAiReply) {
        voiceFallbackTextInput.value = "";
        if (voiceEngine === "sarvam") {
          sendCandidateTurnToSarvam(text);
        } else {
          sendCandidateTurnToGemini(text);
        }
      }
    };
    voiceFallbackSendBtn.addEventListener("click", submitFallback);
    voiceFallbackTextInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitFallback();
      }
    });
  }

  function startGeminiRecognition() {
    if (voiceEngine === "sarvam") return;
    if (!recognitionInstance && SpeechRecognition) {
      setupGeminiRecognition();
    }
    if (recognitionInstance && !isRecognizing) {
      try {
        recognitionInstance.start();
        isRecognizing = true;
      } catch (_) {}
    }
  }

  function stopGeminiRecognition() {
    if (recognitionInstance && isRecognizing) {
      try {
        recognitionInstance.stop();
      } catch (_) {}
      isRecognizing = false;
    }
  }

  async function sendCandidateTurnToGemini(candidateMessage) {
    if (!candidateMessage || !candidateMessage.trim() || isWaitingForAiReply) return;

    isWaitingForAiReply = true;
    stopGeminiRecognition();

    appendTranscriptTurn("candidate", candidateMessage.trim());

    if (voiceOrb) voiceOrb.className = "pulsing-orb";
    if (orbIcon) orbIcon.textContent = "🧠";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-indigo";
      connectionBadge.textContent = "Alex is Thinking...";
    }
    updateAudioStatus("Alex is formulating response...", "#6366f1");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🧠 Alex is formulating response...";
    if (liveMonitorDot) liveMonitorDot.style.background = "#6366f1";
    if (liveTranscriptDisplay) {
      liveTranscriptDisplay.innerHTML = `<span style="color: #4f46e5; font-weight: 600;">✓ Sent: "${escapeHtml(candidateMessage.trim())}"</span>`;
    }
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    try {
      const res = await fetch(`/api/interviews/${interviewId}/gemini-live/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({
          candidate_message: candidateMessage.trim(),
          history: transcriptTurns
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to process turn with Gemini.");
      }

      const aiReply = extractCleanSpokenText(data.turn.message);
      appendTranscriptTurn("interviewer", aiReply);

      speakGeminiTurn(aiReply, () => {
        isWaitingForAiReply = false;
        startGeminiRecognition();
      });

    } catch (err) {
      console.error("Gemini Live turn error:", err);
      const fallbackMsg = `Thank you for sharing that, ${candidateName}. Could you give a specific example demonstrating your approach?`;
      appendTranscriptTurn("interviewer", fallbackMsg);
      speakGeminiTurn(fallbackMsg, () => {
        isWaitingForAiReply = false;
        startGeminiRecognition();
      });
    }
  }

  // =========================================================================
  // SARVAM AI VOICE ENGINE IMPLEMENTATION
  // Direct MediaRecorder & AnalyserNode streaming (Brave-compatible & Web Speech-free)
  // =========================================================================
  let currentSarvamAudio = null;
  let sarvamMicStream = null;
  let sarvamAudioContext = null;
  let sarvamAnalyser = null;
  let sarvamMediaRecorder = null;
  let sarvamRecordedChunks = [];
  let sarvamSilenceTimer = null;
  let sarvamAnimFrame = null;
  let sarvamHasSpokenInTurn = false;
  let sarvamMimeType = "audio/webm";

  function getSupportedSarvamMimeType() {
    if (typeof MediaRecorder === "undefined") return "";
    const types = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
      "audio/wav"
    ];
    for (const t of types) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return "";
  }

  async function initSarvamMicrophone() {
    if (sarvamMicStream && sarvamMicStream.active) {
      return sarvamMicStream;
    }
    sarvamMicStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        sarvamAudioContext = new AudioCtx();
        const sourceNode = sarvamAudioContext.createMediaStreamSource(sarvamMicStream);
        sarvamAnalyser = sarvamAudioContext.createAnalyser();
        sarvamAnalyser.fftSize = 256;
        sarvamAnalyser.smoothingTimeConstant = 0.5;
        sourceNode.connect(sarvamAnalyser);
      }
    } catch (e) {
      console.warn("Could not initialize Sarvam AudioContext analyser:", e);
    }

    return sarvamMicStream;
  }

  function stopSarvamAudio() {
    if (currentSarvamAudio) {
      try {
        currentSarvamAudio.pause();
        currentSarvamAudio.currentTime = 0;
      } catch (_) {}
      currentSarvamAudio = null;
    }
  }

  function cleanupSarvamVoice() {
    stopSarvamAudio();
    clearTimeout(sarvamSilenceTimer);
    sarvamSilenceTimer = null;
    if (sarvamAnimFrame) {
      cancelAnimationFrame(sarvamAnimFrame);
      sarvamAnimFrame = null;
    }
    if (sarvamMediaRecorder && sarvamMediaRecorder.state === "recording") {
      try {
        sarvamMediaRecorder.stop();
      } catch (_) {}
    }
    sarvamMediaRecorder = null;
    if (sarvamMicStream) {
      sarvamMicStream.getTracks().forEach((track) => {
        try { track.stop(); } catch (_) {}
      });
      sarvamMicStream = null;
    }
    if (sarvamAudioContext) {
      try { sarvamAudioContext.close(); } catch (_) {}
      sarvamAudioContext = null;
    }
    sarvamAnalyser = null;
  }

  function playSarvamAudioB64(audioB64, onComplete) {
    stopSarvamAudio();
    if (!audioB64) {
      if (onComplete) onComplete();
      return;
    }

    try {
      const audio = new Audio("data:audio/mp3;base64," + audioB64);
      currentSarvamAudio = audio;

      let hasEnded = false;
      const finish = () => {
        if (hasEnded) return;
        hasEnded = true;
        currentSarvamAudio = null;
        if (onComplete) onComplete();
      };

      audio.onended = finish;
      audio.onerror = (e) => {
        console.warn("Sarvam audio playback error:", e);
        finish();
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          console.warn("Audio autoplay blocked or failed:", err);
          finish();
        });
      }
    } catch (e) {
      console.error("Failed to play Sarvam audio:", e);
      if (onComplete) onComplete();
    }
  }

  function speakSarvamTurn(text, audioB64, onComplete) {
    const cleanSpeech = extractCleanSpokenText(text);
    if (!cleanSpeech) {
      if (onComplete) onComplete();
      return;
    }

    isAlexSpeaking = true;

    if (voiceOrb) {
      voiceOrb.className = "pulsing-orb speaking";
      voiceOrb.style.transform = "";
    }
    if (orbIcon) orbIcon.textContent = "🎙️";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-indigo";
      connectionBadge.textContent = "Alex is Speaking";
    }
    updateAudioStatus("Alex is speaking aloud (Sarvam Bulbul)...", "#6366f1");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🔊 Alex is speaking (Sarvam Bulbul)...";
    if (liveMonitorDot) liveMonitorDot.style.background = "#6366f1";
    if (liveTranscriptDisplay) liveTranscriptDisplay.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">(Alex is speaking...)</span>';
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    const afterSpeech = () => {
      isAlexSpeaking = false;
      if (!isCallActive) return;

      if (voiceOrb) {
        voiceOrb.className = "pulsing-orb listening";
        voiceOrb.style.transform = "";
      }
      if (orbIcon) orbIcon.textContent = "🗣️";
      if (connectionBadge) {
        connectionBadge.className = "badge badge-emerald";
        connectionBadge.textContent = "Listening to You";
      }
      updateAudioStatus("Listening • Speak into your microphone...", "#10b981");

      if (liveMonitorStateText) liveMonitorStateText.textContent = "🎙️ Listening to you... Speak into your microphone";
      if (liveMonitorDot) liveMonitorDot.style.background = "#10b981";
      if (liveTranscriptDisplay) liveTranscriptDisplay.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">(Alex is listening... Speak your answer now)</span>';
      currentSpokenCandidateText = "";

      if (onComplete) onComplete();
    };

    if (audioB64) {
      playSarvamAudioB64(audioB64, afterSpeech);
    } else {
      if (window.speechSynthesis) {
        const utter = new SpeechSynthesisUtterance(cleanSpeech);
        utter.onend = afterSpeech;
        utter.onerror = afterSpeech;
        window.speechSynthesis.speak(utter);
      } else {
        setTimeout(afterSpeech, 2500);
      }
    }
  }

  function startSarvamListeningTurn() {
    if (!isCallActive || isWaitingForAiReply || isAlexSpeaking) return;

    sarvamHasSpokenInTurn = false;
    sarvamRecordedChunks = [];
    clearTimeout(sarvamSilenceTimer);
    sarvamSilenceTimer = null;

    if (voiceOrb) {
      voiceOrb.className = "pulsing-orb listening";
      voiceOrb.style.transform = "";
    }
    if (orbIcon) orbIcon.textContent = "🗣️";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-emerald";
      connectionBadge.textContent = "Listening to You";
    }
    updateAudioStatus("Listening • Speak into your microphone...", "#10b981");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🎙️ Listening to you... Speak into your microphone";
    if (liveMonitorDot) liveMonitorDot.style.background = "#10b981";
    if (liveTranscriptDisplay) {
      liveTranscriptDisplay.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">(Alex is listening... Speak your answer now)</span>';
    }
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    try {
      sarvamMimeType = getSupportedSarvamMimeType();
      const options = sarvamMimeType ? { mimeType: sarvamMimeType } : undefined;
      sarvamMediaRecorder = new MediaRecorder(sarvamMicStream, options);

      sarvamMediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          sarvamRecordedChunks.push(e.data);
        }
      };

      sarvamMediaRecorder.onstop = () => {
        if (sarvamAnimFrame) {
          cancelAnimationFrame(sarvamAnimFrame);
          sarvamAnimFrame = null;
        }
        if (sarvamHasSpokenInTurn && sarvamRecordedChunks.length > 0) {
          const type = sarvamMimeType || "audio/webm";
          const blob = new Blob(sarvamRecordedChunks, { type });
          sarvamRecordedChunks = [];
          sendCandidateAudioToSarvam(blob);
        } else {
          sarvamRecordedChunks = [];
          if (isCallActive && !isWaitingForAiReply && !isAlexSpeaking) {
            setTimeout(startSarvamListeningTurn, 300);
          }
        }
      };

      sarvamMediaRecorder.start(250);
    } catch (err) {
      console.error("Failed to start Sarvam MediaRecorder:", err);
      updateAudioStatus("Microphone recording error", "#ef4444");
      return;
    }

    monitorSarvamMicrophone();
  }

  function monitorSarvamMicrophone() {
    if (!isCallActive || isWaitingForAiReply || isAlexSpeaking || !sarvamAnalyser) return;

    const dataArray = new Uint8Array(sarvamAnalyser.frequencyBinCount);

    const checkVolume = () => {
      if (!isCallActive || isWaitingForAiReply || isAlexSpeaking || !sarvamMediaRecorder || sarvamMediaRecorder.state !== "recording") {
        return;
      }

      sarvamAnalyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;

      // Threshold: 12 (ambient room noise is typically < 10)
      if (avg > 12) {
        if (!sarvamHasSpokenInTurn) {
          sarvamHasSpokenInTurn = true;
          if (doneSpeakingBtn) doneSpeakingBtn.style.display = "inline-flex";
          if (liveMonitorStateText) liveMonitorStateText.textContent = "🗣️ Hearing you speak...";
          if (liveTranscriptDisplay) {
            liveTranscriptDisplay.innerHTML = '<span style="color: #10b981; font-weight: 600;">🎙️ Recording your spoken answer...</span>';
          }
        }

        // Orb pulse effect proportional to voice volume
        if (voiceOrb) {
          const scale = Math.min(1.25, 1.0 + (avg / 255) * 0.4);
          voiceOrb.style.transform = `scale(${scale})`;
        }

        if (sarvamSilenceTimer) {
          clearTimeout(sarvamSilenceTimer);
          sarvamSilenceTimer = null;
        }
        if (livePauseIndicator) livePauseIndicator.style.display = "none";

      } else {
        if (voiceOrb) {
          voiceOrb.style.transform = "";
        }

        if (sarvamHasSpokenInTurn) {
          if (!sarvamSilenceTimer) {
            if (livePauseIndicator) {
              livePauseIndicator.style.display = "block";
              livePauseIndicator.textContent = "⏳ Pause detected — submitting answer to Alex...";
            }
            sarvamSilenceTimer = setTimeout(() => {
              stopSarvamRecordingAndSend();
            }, 1400);
          }
        }
      }

      sarvamAnimFrame = requestAnimationFrame(checkVolume);
    };

    sarvamAnimFrame = requestAnimationFrame(checkVolume);
  }

  function stopSarvamRecordingAndSend() {
    clearTimeout(sarvamSilenceTimer);
    sarvamSilenceTimer = null;
    if (sarvamAnimFrame) {
      cancelAnimationFrame(sarvamAnimFrame);
      sarvamAnimFrame = null;
    }
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    if (sarvamMediaRecorder && sarvamMediaRecorder.state === "recording") {
      try {
        sarvamMediaRecorder.stop();
      } catch (e) {
        console.warn("Notice stopping Sarvam MediaRecorder:", e);
      }
    }
  }

  async function sendCandidateAudioToSarvam(audioBlob) {
    if (!audioBlob || isWaitingForAiReply) return;

    isWaitingForAiReply = true;
    stopSarvamAudio();

    if (voiceOrb) {
      voiceOrb.className = "pulsing-orb thinking";
      voiceOrb.style.transform = "";
    }
    if (orbIcon) orbIcon.textContent = "🧠";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-amber";
      connectionBadge.textContent = "Alex is Thinking...";
    }
    updateAudioStatus("Alex is formulating response (Sarvam Saaras STT)...", "#f59e0b");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🧠 Alex is transcribing & thinking...";
    if (liveMonitorDot) liveMonitorDot.style.background = "#f59e0b";
    if (liveTranscriptDisplay) {
      liveTranscriptDisplay.innerHTML = '<span style="color: #6366f1; font-style: italic;">Transcribing your voice with Sarvam Saaras AI...</span>';
    }

    try {
      const formData = new FormData();
      const ext = (sarvamMimeType && sarvamMimeType.includes("mp4")) ? "mp4" : "webm";
      formData.append("audio", audioBlob, `turn_${Date.now()}.${ext}`);
      formData.append("time_in_call_secs", elapsedSeconds);

      const res = await fetch(`/api/interviews/${interviewId}/sarvam/turn`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Sarvam turn failed.");
      }

      // If silence / no speech detected, resume listening quietly
      if (data.no_speech) {
        isWaitingForAiReply = false;
        startSarvamListeningTurn();
        return;
      }

      const candidateSpeech = data.candidate_message || "";
      if (candidateSpeech) {
        appendTranscriptTurn("candidate", candidateSpeech);
        if (liveTranscriptDisplay) {
          liveTranscriptDisplay.innerHTML = `<span style="color: #4f46e5; font-weight: 600;">✓ Heard: "${escapeHtml(candidateSpeech)}"</span>`;
        }
      }

      const alexText = data.response_text;
      const audioB64 = data.audio_base64;

      appendTranscriptTurn("interviewer", alexText);

      isWaitingForAiReply = false;
      speakSarvamTurn(alexText, audioB64, () => {
        startSarvamListeningTurn();
      });

    } catch (err) {
      console.error("Sarvam audio turn error:", err);
      isWaitingForAiReply = false;
      const fallbackMsg = "Got it. Can you walk me through your personal contribution to that project?";
      appendTranscriptTurn("interviewer", fallbackMsg);
      speakSarvamTurn(fallbackMsg, null, () => {
        startSarvamListeningTurn();
      });
    }
  }

  async function startSarvamVoiceSession(creds) {
    isCallActive = true;
    startBtn.style.display = "none";
    if (endBtn) {
      endBtn.style.display = "inline-flex";
    }
    if (liveVoiceMonitor) {
      liveVoiceMonitor.style.display = "block";
    }
    if (braveSpeechNotice) {
      braveSpeechNotice.style.display = "none";
    }

    if (studioStateTitle) {
      studioStateTitle.textContent = "Interview in Progress (Sarvam AI Voice)";
    }
    if (studioStateSubtitle) {
      studioStateSubtitle.textContent =
        "Alex is conducting your spoken interview powered by Sarvam AI. Speak naturally into your microphone.";
    }

    startTimer();

    try {
      await initSarvamMicrophone();
    } catch (micErr) {
      console.error("Failed to acquire microphone for Sarvam:", micErr);
      alert("Microphone access is required for the Sarvam AI interview. Please allow microphone access in your browser.");
      resetStartButton();
      return;
    }

    const greetingText = creds.text || `Hello ${candidateName}! Welcome to your interview for the ${jobTitle} position. I am Alex, your interviewer today. To get started, could you please explain a bit about yourself and walk me through your CV?`;
    const greetingAudio = creds.audio_base64 || null;

    appendTranscriptTurn("interviewer", greetingText);

    speakSarvamTurn(greetingText, greetingAudio, () => {
      startSarvamListeningTurn();
    });
  }

  async function sendCandidateTurnToSarvam(candidateMessage) {
    if (!candidateMessage || !candidateMessage.trim() || isWaitingForAiReply) return;

    isWaitingForAiReply = true;
    if (sarvamMediaRecorder && sarvamMediaRecorder.state === "recording") {
      try { sarvamMediaRecorder.stop(); } catch (_) {}
    }
    stopSarvamAudio();

    appendTranscriptTurn("candidate", candidateMessage.trim());

    if (voiceOrb) {
      voiceOrb.className = "pulsing-orb thinking";
      voiceOrb.style.transform = "";
    }
    if (orbIcon) orbIcon.textContent = "🧠";
    if (connectionBadge) {
      connectionBadge.className = "badge badge-amber";
      connectionBadge.textContent = "Alex is Thinking...";
    }
    updateAudioStatus("Alex is formulating response...", "#f59e0b");

    if (liveMonitorStateText) liveMonitorStateText.textContent = "🧠 Alex is formulating response...";
    if (liveMonitorDot) liveMonitorDot.style.background = "#f59e0b";
    if (liveTranscriptDisplay) {
      liveTranscriptDisplay.innerHTML = `<span style="color: #4f46e5; font-weight: 600;">✓ Sent: "${escapeHtml(candidateMessage.trim())}"</span>`;
    }
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";
    if (livePauseIndicator) livePauseIndicator.style.display = "none";

    try {
      const res = await fetch(`/api/interviews/${interviewId}/sarvam/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({
          candidate_message: candidateMessage.trim(),
          time_in_call_secs: elapsedSeconds
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Sarvam turn failed.");
      }

      const alexText = data.response_text;
      const audioB64 = data.audio_base64;

      appendTranscriptTurn("interviewer", alexText);

      isWaitingForAiReply = false;
      speakSarvamTurn(alexText, audioB64, () => {
        startSarvamListeningTurn();
      });

    } catch (err) {
      console.error("Sarvam turn error:", err);
      isWaitingForAiReply = false;
      const fallbackMsg = "Got it. Can you walk me through your personal contribution to that project?";
      appendTranscriptTurn("interviewer", fallbackMsg);
      speakSarvamTurn(fallbackMsg, null, () => {
        startSarvamListeningTurn();
      });
    }
  }

  // =========================================================================
  // OPENAI REALTIME VOICE (WEBRTC) ENGINE IMPLEMENTATION
  // =========================================================================
  let peerConnection = null;
  let dataChannel = null;
  let localAudioStream = null;
  let remoteAudioElement = null;
  let currentAiTurnAccumulator = "";

  function cleanupOpenAIRealtime() {
    if (localAudioStream) {
      localAudioStream.getTracks().forEach((track) => {
        try { track.stop(); } catch (_) {}
      });
      localAudioStream = null;
    }
    if (dataChannel) {
      try { dataChannel.close(); } catch (_) {}
      dataChannel = null;
    }
    if (peerConnection) {
      try { peerConnection.close(); } catch (_) {}
      peerConnection = null;
    }
    if (remoteAudioElement) {
      try {
        remoteAudioElement.srcObject = null;
        remoteAudioElement.remove();
      } catch (_) {}
      remoteAudioElement = null;
    }
    currentAiTurnAccumulator = "";
  }

  function handleOpenAIRealtimeEvent(event) {
    if (!event || !event.type) return;

    switch (event.type) {
      // Candidate speech detection (server VAD) & interruption/barge-in
      case "input_audio_buffer.speech_started":
        console.log("[OpenAI Realtime] Candidate speech started (Barge-in / listening)");
        if (voiceOrb) voiceOrb.className = "pulsing-orb listening";
        if (orbIcon) orbIcon.textContent = "🗣️";
        if (connectionBadge) {
          connectionBadge.className = "badge badge-emerald";
          connectionBadge.textContent = "Listening to You";
        }
        updateAudioStatus("Listening • You are speaking...", "#10b981");
        break;

      case "input_audio_buffer.speech_stopped":
        console.log("[OpenAI Realtime] Candidate speech stopped");
        if (voiceOrb) voiceOrb.className = "pulsing-orb";
        if (orbIcon) orbIcon.textContent = "🧠";
        if (connectionBadge) {
          connectionBadge.className = "badge badge-indigo";
          connectionBadge.textContent = "Alex is Listening / Formulating...";
        }
        updateAudioStatus("Alex is processing your response...", "#6366f1");
        break;

      // Candidate transcription completed by Whisper
      case "conversation.item.input_audio_transcription.completed":
        if (event.transcript && event.transcript.trim()) {
          console.log("[OpenAI Realtime] Candidate transcript:", event.transcript);
          appendTranscriptTurn("candidate", event.transcript.trim());
        }
        break;

      // Model audio response generation
      case "response.created":
      case "response.output_item.added":
        if (voiceOrb) voiceOrb.className = "pulsing-orb speaking";
        if (orbIcon) orbIcon.textContent = "🎙️";
        if (connectionBadge) {
          connectionBadge.className = "badge badge-indigo";
          connectionBadge.textContent = "Alex is Speaking";
        }
        updateAudioStatus("Alex is speaking aloud...", "#6366f1");
        currentAiTurnAccumulator = "";
        break;

      // Streaming audio transcript chunks
      case "response.audio_transcript.delta":
        if (event.delta) {
          currentAiTurnAccumulator += event.delta;
        }
        break;

      // Finalized AI audio transcript
      case "response.audio_transcript.done":
        const completedText = (event.transcript || currentAiTurnAccumulator || "").trim();
        if (completedText) {
          console.log("[OpenAI Realtime] Alex transcript:", completedText);
          appendTranscriptTurn("interviewer", completedText);
        }
        currentAiTurnAccumulator = "";
        break;

      case "response.done":
        if (isCallActive) {
          if (voiceOrb) voiceOrb.className = "pulsing-orb listening";
          if (orbIcon) orbIcon.textContent = "🗣️";
          if (connectionBadge) {
            connectionBadge.className = "badge badge-emerald";
            connectionBadge.textContent = "Listening to You";
          }
          updateAudioStatus("Listening • Speak into your microphone", "#10b981");
        }
        break;

      case "error":
        console.error("[OpenAI Realtime] Server error event:", event.error);
        const errMsg = event.error ? (event.error.message || JSON.stringify(event.error)) : "Realtime API event notice";
        updateAudioStatus(`Realtime notice: ${errMsg}`, "#f59e0b");
        break;

      default:
        break;
    }
  }

  // =========================================================================
  // START CALL HANDLER (BRANCHES FOR ELEVENLABS vs GEMINI LIVE vs OPENAI REALTIME)
  // =========================================================================

  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      const isConfigured = (voiceEngine === "gemini_live") 
        ? isGeminiLiveConfigured 
        : (voiceEngine === "openai_realtime")
          ? isOpenaiRealtimeConfigured
          : (voiceEngine === "sarvam")
            ? isSarvamConfigured
            : isElevenLabsConfigured;
      if (!isConfigured) {
        const engineName = (voiceEngine === "gemini_live") 
          ? "Gemini API Key" 
          : (voiceEngine === "openai_realtime")
            ? "OpenAI API Key"
            : (voiceEngine === "sarvam")
              ? "Sarvam API Key"
              : "ElevenLabs API Key & Agent ID";
        alert(`${engineName} is not configured in your .env file.`);
        return;
      }

      startBtn.disabled = true;
      startBtn.textContent = "Requesting Microphone Access...";
      if (connectionBadge) {
        connectionBadge.className = "badge badge-amber";
        connectionBadge.textContent = "Mic Permission";
      }
      updateAudioStatus("Requesting microphone permission...", "#f59e0b");

      try {
        // Step 1: Explicitly verify microphone permission
        let micStream;
        try {
          micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          micStream.getTracks().forEach((track) => track.stop());
        } catch (micErr) {
          console.error("Microphone permission denied or failed:", micErr);
          alert(
            "Microphone access is required for the spoken interview.\n\n" +
            "Please click the microphone/lock icon in your browser's address bar, allow microphone access, and try again."
          );
          resetStartButton();
          return;
        }

        // Step 2: Fetch secure conversation credentials
        startBtn.textContent = "Connecting to Voice Agent...";
        updateAudioStatus("Initializing voice session...", "#f59e0b");
        if (connectionBadge) {
          connectionBadge.textContent = "Securing Session";
        }

        const res = await fetch(`/api/interviews/${interviewId}/conversation-credentials`);
        const creds = await res.json();

        if (!res.ok) {
          throw new Error(creds.error || "Failed to obtain interview conversation credentials.");
        }

        // BRANCH: GEMINI FLASH LIVE VOICE ENGINE
        if (voiceEngine === "gemini_live" || creds.voice_engine === "gemini_live") {
          isCallActive = true;
          startBtn.style.display = "none";
          if (endBtn) {
            endBtn.style.display = "inline-flex";
          }
          if (liveVoiceMonitor) {
            liveVoiceMonitor.style.display = "block";
          }

          if (studioStateTitle) {
            studioStateTitle.textContent = "Interview in Progress (Gemini Flash Live)";
          }
          if (studioStateSubtitle) {
            studioStateSubtitle.textContent =
              "Alex is conducting your spoken interview powered by Gemini Flash Live. Speak your answer into your microphone.";
          }

          startTimer();
          setupGeminiRecognition();

          // Speak initial opening greeting from Gemini
          const rawGreeting = creds.greeting ? creds.greeting.message : 
            `Hello ${candidateName}! Welcome to your spoken interview for the ${jobTitle} role. I'm Alex. To get started, could you please introduce yourself and tell me what interests you most about this position?`;
          const initialGreeting = extractCleanSpokenText(rawGreeting);

          appendTranscriptTurn("interviewer", initialGreeting);
          speakGeminiTurn(initialGreeting, () => {
            startGeminiRecognition();
          });

          return;
        }

        // BRANCH: OPENAI REALTIME VOICE (WEBRTC) ENGINE
        if (voiceEngine === "openai_realtime" || creds.voice_engine === "openai_realtime") {
          updateAudioStatus("Negotiating WebRTC audio connection...", "#f59e0b");
          if (connectionBadge) {
            connectionBadge.textContent = "WebRTC Handshake";
          }

          // Step 1: Capture local microphone
          localAudioStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true
            }
          });

          // Step 2: Initialize RTCPeerConnection
          peerConnection = new RTCPeerConnection({
            iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
          });

          // Step 3: Remote audio element
          remoteAudioElement = document.createElement("audio");
          remoteAudioElement.autoplay = true;
          peerConnection.ontrack = (event) => {
            console.log("[OpenAI Realtime] Remote audio track attached");
            remoteAudioElement.srcObject = event.streams[0];
          };

          // Step 4: Add local audio track
          localAudioStream.getTracks().forEach((track) => {
            peerConnection.addTrack(track, localAudioStream);
          });

          // Step 5: Create Data Channel before offer
          dataChannel = peerConnection.createDataChannel("oai-events");

          dataChannel.onopen = () => {
            console.log("[OpenAI Realtime] Data channel opened");
            isCallActive = true;
            startTimer();

            startBtn.style.display = "none";
            if (endBtn) endBtn.style.display = "inline-flex";

            if (studioStateTitle) {
              studioStateTitle.textContent = "Interview in Progress (OpenAI Realtime)";
            }
            if (studioStateSubtitle) {
              studioStateSubtitle.textContent =
                "Alex is speaking with you live over low-latency WebRTC. Speak naturally into your microphone; Alex will listen and you can interrupt anytime.";
            }

            if (connectionBadge) {
              connectionBadge.className = "badge badge-emerald";
              connectionBadge.textContent = "Live WebRTC Connected";
            }
            updateAudioStatus("Connected • Realtime audio active", "#10b981");

            // Trigger initial opening greeting from Alex
            try {
              const triggerGreeting = {
                type: "response.create",
                response: {
                  modalities: ["audio", "text"],
                  instructions: `Greet ${candidateName} warmly for their interview for the ${jobTitle} role, introduce yourself as Alex, and ask the first opening question.`
                }
              };
              dataChannel.send(JSON.stringify(triggerGreeting));
            } catch (trigErr) {
              console.warn("[OpenAI Realtime] Initial greeting trigger error:", trigErr);
            }
          };

          dataChannel.onmessage = (e) => {
            try {
              const parsedEvent = JSON.parse(e.data);
              handleOpenAIRealtimeEvent(parsedEvent);
            } catch (err) {
              console.warn("[OpenAI Realtime] JSON parse warning:", err);
            }
          };

          dataChannel.onerror = (err) => {
            console.error("[OpenAI Realtime] Data channel error:", err);
            updateAudioStatus("Data channel error", "#ef4444");
          };

          dataChannel.onclose = () => {
            console.log("[OpenAI Realtime] Data channel closed");
          };

          // Step 6: Create SDP Offer
          const offer = await peerConnection.createOffer();
          await peerConnection.setLocalDescription(offer);

          const targetModel = creds.model || "gpt-4o-realtime-preview-2024-12-17";
          let answerSdp = null;

          // Attempt direct fetch to OpenAI Realtime endpoint using ephemeral client_secret
          if (creds.client_secret && !creds.client_secret.startsWith("ek_mock")) {
            const candidateUrls = [
              `https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(targetModel)}`,
              "https://api.openai.com/v1/realtime/calls",
              `https://api.openai.com/v1/realtime?model=${encodeURIComponent(targetModel)}`
            ];

            for (const url of candidateUrls) {
              try {
                const sdpRes = await fetch(url, {
                  method: "POST",
                  headers: {
                    "Authorization": `Bearer ${creds.client_secret}`,
                    "Content-Type": "application/sdp"
                  },
                  body: offer.sdp
                });

                if (sdpRes.ok) {
                  answerSdp = await sdpRes.text();
                  break;
                } else {
                  console.warn(`[OpenAI Realtime] Direct SDP exchange status (${url}):`, sdpRes.status);
                  if (sdpRes.status !== 404) {
                    break;
                  }
                }
              } catch (directErr) {
                console.warn(`[OpenAI Realtime] Direct SDP exchange error (${url}):`, directErr);
              }
            }
          }

          // Fallback: relay through backend endpoint
          if (!answerSdp) {
            const relayRes = await fetch(`/api/interviews/${interviewId}/openai-realtime/relay`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                sdp: offer.sdp,
                client_secret: creds.client_secret,
                model: targetModel
              })
            });

            const relayData = await relayRes.json();
            if (!relayRes.ok || !relayData.sdp) {
              throw new Error(relayData.error || "Failed to establish WebRTC connection with OpenAI Realtime.");
            }
            answerSdp = relayData.sdp;
          }

          // Step 7: Apply remote description (SDP Answer)
          await peerConnection.setRemoteDescription({
            type: "answer",
            sdp: answerSdp
          });

          return;
        }

        // BRANCH: SARVAM AI VOICE ENGINE
        if (voiceEngine === "sarvam" || creds.voice_engine === "sarvam") {
          startSarvamVoiceSession(creds);
          return;
        }

        // BRANCH: ELEVENLABS CONVERSATIONAL AI ENGINE
        updateAudioStatus("Connecting audio stream...", "#f59e0b");
        if (connectionBadge) {
          connectionBadge.textContent = "Opening Audio Stream";
        }

        const sessionConfig = {
          dynamicVariables: creds.dynamic_variables || {
            interview_id: interviewId,
            candidate_name: candidateName,
            job_title: jobTitle
          },
          onConnect: ({ conversationId: id }) => {
            console.log("Connected to ElevenLabs session:", id);
            conversationId = id;
            isCallActive = true;

            if (connectionBadge) {
              connectionBadge.className = "badge badge-emerald";
              connectionBadge.textContent = "Live Voice Connected";
            }
            if (studioStateTitle) {
              studioStateTitle.textContent = "Interview in Progress";
            }
            if (studioStateSubtitle) {
              studioStateSubtitle.textContent =
                "Alex (AI Interviewer) is conducting your spoken interview. Speak clearly into your microphone.";
            }

            updateAudioStatus("Connected • Voice stream active", "#10b981");

            startBtn.style.display = "none";
            if (endBtn) {
              endBtn.style.display = "inline-flex";
            }

            startTimer();
          },
          onDisconnect: (details) => {
            console.log("ElevenLabs session disconnected:", details);
            isCallActive = false;
            if (!isFinalizing) {
              if (connectionBadge) {
                connectionBadge.className = "badge badge-gray";
                connectionBadge.textContent = "Call Ended";
              }
              if (voiceOrb) {
                voiceOrb.className = "pulsing-orb";
              }
              if (orbIcon) {
                orbIcon.textContent = "🎙️";
              }
              updateAudioStatus("Voice call disconnected", "#94a3b8");
            }
          },
          onModeChange: ({ mode }) => {
            if (mode === "speaking") {
              if (voiceOrb) voiceOrb.className = "pulsing-orb speaking";
              if (orbIcon) orbIcon.textContent = "🎙️";
              if (connectionBadge) {
                connectionBadge.className = "badge badge-indigo";
                connectionBadge.textContent = "Alex is Speaking";
              }
              updateAudioStatus("Alex is speaking...", "#6366f1");
            } else if (mode === "listening") {
              if (voiceOrb) voiceOrb.className = "pulsing-orb listening";
              if (orbIcon) orbIcon.textContent = "🗣️";
              if (connectionBadge) {
                connectionBadge.className = "badge badge-emerald";
                connectionBadge.textContent = "Listening to You";
              }
              updateAudioStatus("Listening • Speak into your microphone", "#10b981");
            }
          },
          onMessage: (messagePayload) => {
            const rawRole = messagePayload.role || (messagePayload.source === "user" ? "user" : "agent");
            const text = messagePayload.message || "";
            appendTranscriptTurn(rawRole, text);
          },
          onError: (message, context) => {
            console.error("ElevenLabs error:", message, context);
            if (connectionBadge) {
              connectionBadge.className = "badge badge-rose";
              connectionBadge.textContent = "Audio Stream Warning";
            }
            updateAudioStatus("Audio Notice: " + (message || "Connection event"), "#ef4444");
          },
          onStatusChange: ({ status }) => {
            if (status === "connecting") {
              if (connectionBadge) {
                connectionBadge.className = "badge badge-amber";
                connectionBadge.textContent = "Connecting to Voice...";
              }
            }
          }
        };

        if (creds.auth_mode === "signed_url") {
          sessionConfig.signedUrl = creds.signed_url;
        } else {
          sessionConfig.agentId = creds.agent_id || configuredAgentId;
        }

        conversationInstance = await Conversation.startSession(sessionConfig);

      } catch (err) {
        console.error("Call initialization failed:", err);
        alert("Could not start voice interview call: " + err.message);
        resetStartButton();
      }
    });
  }

  // =========================================================================
  // END CALL & FINALIZATION
  // =========================================================================

  if (endBtn) {
    endBtn.addEventListener("click", async () => {
      const candidateTurns = transcriptTurns.filter((t) => t.role === "candidate");
      if (candidateTurns.length === 0 && transcriptTurns.length < 2) {
        const proceed = confirm(
          "Notice: Alex and you haven't exchanged enough answers yet for a thorough evaluation.\n\n" +
          "Are you sure you want to conclude the session and generate the report now?"
        );
        if (!proceed) return;
      } else {
        const proceed = confirm(
          "Are you ready to conclude your interview session and generate the evaluation report?"
        );
        if (!proceed) return;
      }

      await finalizeAndRedirect("normal");
    });
  }

  async function finalizeAndRedirect(reason) {
    isCallActive = false;
    isFinalizing = true;
    stopTimer();
    if (liveVoiceMonitor) liveVoiceMonitor.style.display = "none";
    if (doneSpeakingBtn) doneSpeakingBtn.style.display = "none";

    // Clean up voice synthesis & recognition
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    stopSarvamAudio();
    cleanupSarvamVoice();
    stopGeminiRecognition();
    cleanupOpenAIRealtime();

    if (endBtn) endBtn.disabled = true;
    if (finalizingModal) finalizingModal.classList.add("active");

    // Close ElevenLabs conversation session gracefully if active
    if (conversationInstance) {
      try {
        await conversationInstance.endSession();
      } catch (endErr) {
        console.warn("Session end warning:", endErr);
      }
      conversationInstance = null;
    }

    try {
      // Step 1: Tell server call has concluded
      await fetch(`/api/interviews/${interviewId}/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: reason,
          conversation_id: conversationId
        })
      });

      // Step 2: Trigger report evaluation using interview's chosen LLM model
      const finalRes = await fetch(`/api/interviews/${interviewId}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          transcript: transcriptTurns
        })
      });

      const finalData = await finalRes.json();
      if (!finalRes.ok) {
        throw new Error(finalData.error || "Evaluation synthesis failed.");
      }

      // Success: redirect to candidate completion screen
      window.location.href = finalData.completed_url || `/interviews/${interviewId}/completed`;

    } catch (err) {
      console.error("Finalization error:", err);
      if (finalizingModal) finalizingModal.classList.remove("active");
      alert("Evaluation Notice: " + err.message);
      window.location.href = `/interviews/${interviewId}/completed`;
    }
  }

  // Handle window unload gracefully
  window.addEventListener("beforeunload", () => {
    if (isCallActive && !isFinalizing) {
      navigator.sendBeacon(
        `/api/interviews/${interviewId}/end`,
        JSON.stringify({ reason: "interrupted" })
      );
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      cleanupSarvamVoice();
      stopGeminiRecognition();
      cleanupOpenAIRealtime();
      if (conversationInstance) {
        try {
          conversationInstance.endSession();
        } catch (_) {}
      }
    }
  });
});
