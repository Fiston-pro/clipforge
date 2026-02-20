"use client";

import { useCallback, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Single source-of-truth for the character limit.
// Change this constant and the UI updates automatically.
// ---------------------------------------------------------------------------
const MAX_CHARS = 2200;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type AppState = "idle" | "pending" | "processing" | "done" | "error";

interface PollResponse {
  status: "pending" | "processing" | "done" | "error";
  progress: number;
  message?: string;
  url?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function Home() {
  const [script, setScript] = useState("");
  const [appState, setAppState] = useState<AppState>("idle");
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---- Polling ------------------------------------------------------------

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollStatus = useCallback(
    async (jobId: string) => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        if (!res.ok) return; // transient error — keep polling

        const data: PollResponse = await res.json();
        setProgress(data.progress ?? 0);
        if (data.message) setStatusMessage(data.message);

        if (data.status === "done") {
          stopPolling();
          setAppState("done");
          setVideoUrl(data.url ?? null);
        } else if (data.status === "error") {
          stopPolling();
          setAppState("error");
          setErrorMsg(data.error ?? "An unknown error occurred.");
        }
      } catch {
        // network hiccup — keep polling
      }
    },
    [stopPolling]
  );

  // ---- Generate -----------------------------------------------------------

  const handleGenerate = async () => {
    if (!script.trim() || isProcessing || charCount > MAX_CHARS) return;

    stopPolling();
    setAppState("pending");
    setErrorMsg(null);
    setVideoUrl(null);
    setProgress(0);
    setStatusMessage("Submitting job...");

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: script }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(
          data?.detail ?? data?.error ?? `Server error ${res.status}`
        );
      }

      const { jobId } = data as { jobId: string };
      setAppState("processing");
      setStatusMessage("Generating voiceover...");

      // Poll every 2 seconds
      pollRef.current = setInterval(() => pollStatus(jobId), 2000);
    } catch (err) {
      setAppState("error");
      setErrorMsg(err instanceof Error ? err.message : "Failed to start job.");
    }
  };

  // ---- Download -----------------------------------------------------------

  const handleDownload = async () => {
    if (!videoUrl) return;
    try {
      const res = await fetch(videoUrl);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = "clipforge-video.mp4";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(blobUrl);
    } catch {
      alert("Download failed. Try right-clicking the video and saving it.");
    }
  };

  // ---- Reset --------------------------------------------------------------

  const handleReset = () => {
    stopPolling();
    setAppState("idle");
    setProgress(0);
    setStatusMessage("");
    setVideoUrl(null);
    setErrorMsg(null);
  };

  // ---- Derived state ------------------------------------------------------

  const isProcessing = appState === "pending" || appState === "processing";
  const charCount = script.length;
  const isOverLimit = charCount > MAX_CHARS;
  const canGenerate = script.trim().length > 0 && !isProcessing && !isOverLimit;

  // ---- Render -------------------------------------------------------------

  return (
    <main className="min-h-screen bg-[#0a0a0a] text-white flex flex-col items-center justify-start px-4 py-16">
      <div className="w-full max-w-2xl space-y-6">

        {/* ── Header ── */}
        <div className="text-center space-y-2 pb-2">
          <h1 className="text-6xl font-black tracking-tight bg-gradient-to-r from-[#ee1d52] to-[#7000ff] bg-clip-text text-transparent select-none">
            CLIPFORGE
          </h1>
          <p className="text-[#666] text-sm tracking-wide uppercase">
            Script → AI Voiceover → TikTok Video
          </p>
        </div>

        {/* ── Script Textarea ── */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-[#555] uppercase tracking-widest">
            Your Script
          </label>
          <textarea
            className={[
              "w-full h-52 bg-[#111] rounded-xl px-4 py-3",
              "text-white placeholder-[#333] text-sm leading-relaxed resize-none",
              "border transition-colors duration-150 focus:outline-none font-mono",
              isOverLimit
                ? "border-red-600 focus:border-red-500"
                : "border-[#1e1e1e] focus:border-[#ee1d52]",
              isProcessing ? "opacity-50 cursor-not-allowed" : "",
            ].join(" ")}
            placeholder="Paste your script here...&#10;&#10;Example: Did you know that the Great Wall of China is actually not visible from space? This myth has been debunked by multiple astronauts who confirmed that the wall is simply too narrow to see from orbit..."
            value={script}
            onChange={(e) => setScript(e.target.value)}
            disabled={isProcessing}
            spellCheck
          />

          {/* Character counter */}
          <div className="flex justify-end items-center gap-2">
            {isOverLimit && (
              <span className="text-xs text-red-500">
                {charCount - MAX_CHARS} over limit
              </span>
            )}
            <span
              className={`text-xs tabular-nums ${
                isOverLimit ? "text-red-500" : charCount > MAX_CHARS * 0.9 ? "text-yellow-500" : "text-[#444]"
              }`}
            >
              {charCount.toLocaleString()} / {MAX_CHARS.toLocaleString()}
            </span>
          </div>
        </div>

        {/* ── Generate Button ── */}
        <button
          onClick={handleGenerate}
          disabled={!canGenerate}
          className={[
            "w-full py-4 rounded-xl font-bold text-base tracking-wide transition-all duration-150",
            "bg-gradient-to-r from-[#ee1d52] to-[#7000ff]",
            canGenerate
              ? "hover:opacity-90 active:scale-[0.99] cursor-pointer"
              : "opacity-30 cursor-not-allowed",
          ].join(" ")}
        >
          {isProcessing ? (
            <span className="flex items-center justify-center gap-2">
              <Spinner />
              Generating...
            </span>
          ) : (
            "Generate Video"
          )}
        </button>

        {/* ── Progress Bar ── */}
        {isProcessing && (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5 space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-[#999]">
                {statusMessage || "Processing..."}
              </span>
              <span className="text-xs text-[#444] tabular-nums">{progress}%</span>
            </div>
            <div className="w-full bg-[#1a1a1a] rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[#ee1d52] to-[#7000ff] rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <ProgressSteps progress={progress} />
          </div>
        )}

        {/* ── Error State ── */}
        {appState === "error" && errorMsg && (
          <div className="bg-red-950/20 border border-red-900/40 rounded-xl p-5 space-y-3">
            <div className="flex items-start gap-3">
              <span className="text-red-500 text-lg leading-none">✕</span>
              <div className="space-y-1 flex-1">
                <p className="text-sm font-medium text-red-400">
                  Something went wrong
                </p>
                <p className="text-xs text-red-700 font-mono break-all">
                  {errorMsg}
                </p>
              </div>
            </div>
            <button
              onClick={handleReset}
              className="text-xs text-[#555] hover:text-white transition-colors"
            >
              ← Try again
            </button>
          </div>
        )}

        {/* ── Video Preview ── */}
        {appState === "done" && videoUrl && (
          <div className="space-y-4">
            {/* Portrait video container */}
            <div className="relative rounded-xl overflow-hidden border border-[#1e1e1e] bg-black mx-auto"
              style={{ aspectRatio: "9/16", maxHeight: "65vh" }}>
              <video
                key={videoUrl}
                src={videoUrl}
                controls
                autoPlay
                loop
                playsInline
                className="w-full h-full object-contain"
              />
            </div>

            {/* Action buttons */}
            <div className="flex gap-3">
              <button
                onClick={handleDownload}
                className="flex-1 py-3 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#ee1d52] to-[#7000ff] hover:opacity-90 active:scale-[0.99] transition-all"
              >
                ↓ Download MP4
              </button>
              <button
                onClick={handleReset}
                className="px-6 py-3 rounded-xl font-semibold text-sm bg-[#111] border border-[#1e1e1e] hover:bg-[#1a1a1a] hover:border-[#2a2a2a] transition-all text-[#666] hover:text-white"
              >
                New Video
              </button>
            </div>
          </div>
        )}

        {/* ── Footer ── */}
        <p className="text-center text-[#2a2a2a] text-xs pt-4">
          Powered by OpenAI TTS · FFmpeg · Next.js
        </p>

      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-white"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8H4z"
      />
    </svg>
  );
}

const STEPS = [
  { label: "Voiceover", threshold: 30 },
  { label: "Analysis", threshold: 45 },
  { label: "Subtitles", threshold: 55 },
  { label: "Rendering", threshold: 90 },
  { label: "Done", threshold: 100 },
];

function ProgressSteps({ progress }: { progress: number }) {
  return (
    <div className="flex justify-between mt-1">
      {STEPS.map((step) => {
        const done = progress >= step.threshold;
        const active =
          progress < step.threshold &&
          progress >= (STEPS[STEPS.indexOf(step) - 1]?.threshold ?? 0);
        return (
          <div key={step.label} className="flex flex-col items-center gap-1">
            <div
              className={[
                "w-1.5 h-1.5 rounded-full transition-colors duration-500",
                done
                  ? "bg-gradient-to-r from-[#ee1d52] to-[#7000ff]"
                  : active
                  ? "bg-[#555]"
                  : "bg-[#2a2a2a]",
              ].join(" ")}
            />
            <span
              className={`text-[10px] ${
                done ? "text-[#666]" : active ? "text-[#555]" : "text-[#333]"
              }`}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
