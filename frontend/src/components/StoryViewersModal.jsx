import { useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";

const STORY_DURATION_MS = 5000; // image duration; video stories use their own length

export default function StoryViewer({ userId, onClose, onShowViewers }) {
  const { api, user } = useAuth();
  const [stories, setStories] = useState([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0); // 0–1 for current story

  const rafRef = useRef(null);
  const startRef = useRef(null);
  const elapsedRef = useRef(0);
  const videoRef = useRef(null);
  const viewedRef = useRef(new Set());

  const current = stories[index];

  // Load the user's active stories
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await api.get(`/stories/user/${userId}`);
        const data = res.data || [];
        if (!cancelled) {
          if (data.length === 0) {
            onClose?.();
          } else {
            setStories(data);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.detail || err.message || "Could not load stories");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, api, onClose]);

  const goNext = useCallback(() => {
    setIndex((i) => {
      if (i + 1 >= stories.length) {
        onClose?.();
        return i;
      }
      return i + 1;
    });
  }, [stories.length, onClose]);

  const goPrev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  // Record view once per story
  useEffect(() => {
    if (!current) return;
    if (viewedRef.current.has(current.id)) return;
    viewedRef.current.add(current.id);
    api.post(`/stories/${current.id}/view`).catch(() => {});
  }, [current, api]);

  // Progress/timer loop — images use fixed duration, videos drive their own duration
  useEffect(() => {
    if (!current || paused) return;
    if (current.video_url) return; // video timing handled by onTimeUpdate/onEnded below

    setProgress(0);
    elapsedRef.current = 0;
    startRef.current = performance.now();

    function tick(now) {
      const elapsed = elapsedRef.current + (now - startRef.current);
      const pct = Math.min(elapsed / STORY_DURATION_MS, 1);
      setProgress(pct);
      if (pct >= 1) {
        goNext();
      } else {
        rafRef.current = requestAnimationFrame(tick);
      }
    }
    rafRef.current = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(rafRef.current);
  }, [current, paused, goNext]);

  // Pause/resume bookkeeping for image timer
  function handlePauseStart() {
    if (current?.video_url) {
      videoRef.current?.pause();
    } else {
      cancelAnimationFrame(rafRef.current);
      elapsedRef.current += performance.now() - startRef.current;
    }
    setPaused(true);
  }

  function handlePauseEnd() {
    if (current?.video_url) {
      videoRef.current?.play();
    } else {
      startRef.current = performance.now();
    }
    setPaused(false);
  }

  function handleVideoTimeUpdate(e) {
    const v = e.target;
    if (v.duration) setProgress(v.currentTime / v.duration);
  }

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black">
        <p className="text-sm text-white/60">Loading story...</p>
      </div>
    );
  }

  if (error || !current) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black">
        <p className="text-sm text-white/60">{error || "No story to show."}</p>
        <button onClick={onClose} className="text-sm text-white underline">Close</button>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex select-none items-center justify-center bg-black">
      {/* Progress bars */}
      <div className="absolute left-2 right-2 top-2 z-20 flex gap-1">
        {stories.map((s, i) => (
          <div key={s.id} className="h-0.5 flex-1 overflow-hidden rounded-full bg-white/30">
            <div
              className="h-full bg-white"
              style={{
                width: i < index ? "100%" : i === index ? `${progress * 100}%` : "0%",
                transition: i === index && !paused ? "width 80ms linear" : "none",
              }}
            />
          </div>
        ))}
      </div>

      {/* Header */}
      <div className="absolute left-3 right-3 top-6 z-20 flex items-center justify-between">
        <span className="text-xs text-white/80">{timeAgo(current.created_at)}</span>
        <button onClick={onClose} className="text-lg text-white/90 hover:text-white">✕</button>
      </div>

      {/* Media */}
      <div className="relative h-full max-h-[100dvh] w-full max-w-md">
        {current.video_url ? (
          <video
            ref={videoRef}
            src={current.video_url}
            autoPlay
            playsInline
            className="h-full w-full object-contain"
            onTimeUpdate={handleVideoTimeUpdate}
            onEnded={goNext}
          />
        ) : current.image_url ? (
          <img src={current.image_url} alt="" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-neutral-900 px-8">
            <p className="text-center text-lg text-white">{current.text}</p>
          </div>
        )}

        {current.text && (current.image_url || current.video_url) && (
          <p className="absolute bottom-24 left-0 right-0 px-6 text-center text-sm text-white drop-shadow">
            {current.text}
          </p>
        )}

        {/* Tap zones for prev/next, hold-to-pause */}
        <div className="absolute inset-0 flex">
          <button
            className="h-full w-1/3"
            onClick={goPrev}
            onMouseDown={handlePauseStart}
            onMouseUp={handlePauseEnd}
            onTouchStart={handlePauseStart}
            onTouchEnd={handlePauseEnd}
            aria-label="Previous story"
          />
          <div
            className="h-full w-1/3"
            onMouseDown={handlePauseStart}
            onMouseUp={handlePauseEnd}
            onTouchStart={handlePauseStart}
            onTouchEnd={handlePauseEnd}
          />
          <button
            className="h-full w-1/3"
            onClick={goNext}
            onMouseDown={handlePauseStart}
            onMouseUp={handlePauseEnd}
            onTouchStart={handlePauseStart}
            onTouchEnd={handlePauseEnd}
            aria-label="Next story"
          />
        </div>
      </div>

      {/* Views count — only shown to the story author */}
      {user?.id === userId && (
        <button
          onClick={() => onShowViewers?.(current.id)}
          className="absolute bottom-6 left-1/2 z-20 -translate-x-1/2 text-xs text-white/70 hover:text-white"
        >
          👁 {current.views} {current.views === 1 ? "view" : "views"}
        </button>
      )}
    </div>
  );
}

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const hrs = Math.floor(diffMs / 3600000);
  if (hrs < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m`;
  return `${hrs}h`;
}