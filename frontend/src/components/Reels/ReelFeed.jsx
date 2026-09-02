// frontend/src/components/Reels/ReelFeed.jsx
//
// ASSUMPTIONS:
//   - You have an axios instance at `src/api/axios.js` exported as `api`
//     with an auth header interceptor already attached.
//   - You have `react-router-dom` for profile navigation.
//   - Tailwind is configured (per your README).
//   - lucide-react is available (npm i lucide-react) for icons.
//
// Usage: <ReelFeed /> — drop this as a full route, e.g. /reels
import ReelFeed from "./components/Reels/ReelFeed";
<Route path="/reels" element={<ReelFeed />} />
import React, { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Heart, MessageCircle, Send, Bookmark, MoreHorizontal,
  Music2, X, Volume2, VolumeX,
} from "lucide-react";
import api from "../../api/axios";

export default function ReelFeed() {
  const [reels, setReels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const [muted, setMuted] = useState(true);
  const [activeComments, setActiveComments] = useState(null); // reel id or null
  const containerRef = useRef(null);
  const seenIdsRef = useRef(new Set());

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    try {
      const excludeIds = Array.from(seenIdsRef.current).join(",");
      const { data } = await api.get("/api/reels/feed", {
        params: { limit: 10, exclude_ids: excludeIds || undefined },
      });
      data.reels.forEach((r) => seenIdsRef.current.add(r.id));
      setReels((prev) => [...prev, ...data.reels]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  // Load more when nearing the end
  useEffect(() => {
    if (reels.length > 0 && activeIndex >= reels.length - 3) {
      fetchFeed();
    }
  }, [activeIndex, reels.length, fetchFeed]);

  return (
    <div
      ref={containerRef}
      className="h-screen w-full bg-black overflow-y-scroll snap-y snap-mandatory scrollbar-hide"
      style={{ scrollbarWidth: "none" }}
    >
      {reels.map((reel, i) => (
        <ReelCard
          key={reel.id}
          reel={reel}
          isActive={i === activeIndex}
          muted={muted}
          setMuted={setMuted}
          onBecomeActive={() => setActiveIndex(i)}
          onOpenComments={() => setActiveComments(reel.id)}
          onUpdateReel={(patch) =>
            setReels((prev) => prev.map((r) => (r.id === reel.id ? { ...r, ...patch } : r)))
          }
        />
      ))}
      {loading && (
        <div className="h-screen w-full flex items-center justify-center text-white/60 text-sm snap-start">
          Loading more reels…
        </div>
      )}
      {activeComments && (
        <CommentsSheet
          reelId={activeComments}
          onClose={() => setActiveComments(null)}
        />
      )}
    </div>
  );
}

function ReelCard({ reel, isActive, muted, setMuted, onBecomeActive, onOpenComments, onUpdateReel }) {
  const videoRef = useRef(null);
  const cardRef = useRef(null);
  const navigate = useNavigate();
  const watchStartRef = useRef(null);
  const maxWatchedRef = useRef(0);

  // Autoplay-on-view via IntersectionObserver
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio > 0.6) {
            onBecomeActive();
            videoRef.current?.play().catch(() => {});
            watchStartRef.current = Date.now();
          } else {
            videoRef.current?.pause();
            logView();
          }
        });
      },
      { threshold: [0, 0.6, 1] }
    );
    observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const logView = () => {
    if (!watchStartRef.current) return;
    const watched = (Date.now() - watchStartRef.current) / 1000;
    watchStartRef.current = null;
    const total = maxWatchedRef.current || watched;
    api.post(`/api/reels/${reel.id}/view`, {
      watch_seconds: Math.min(watched, total),
      reel_duration: reel.duration_seconds,
      completed: reel.duration_seconds ? watched >= reel.duration_seconds * 0.9 : false,
    }).catch(() => {});
  };

  useEffect(() => {
    if (!isActive) videoRef.current?.pause();
  }, [isActive]);

  const handleLike = async () => {
    onUpdateReel({
      is_liked: !reel.is_liked,
      like_count: reel.is_liked ? reel.like_count - 1 : reel.like_count + 1,
    });
    try {
      await api.post(`/api/reels/${reel.id}/like`);
    } catch {
      onUpdateReel({ is_liked: reel.is_liked, like_count: reel.like_count });
    }
  };

  const handleSave = async () => {
    onUpdateReel({ is_saved: !reel.is_saved });
    try {
      await api.post(`/api/reels/${reel.id}/save`);
    } catch {
      onUpdateReel({ is_saved: reel.is_saved });
    }
  };

  const handleFollow = async () => {
    onUpdateReel({ creator: { ...reel.creator, is_following: !reel.creator.is_following } });
    try {
      await api.post(`/api/reels/follow/${reel.creator.id}`);
    } catch {
      onUpdateReel({ creator: { ...reel.creator, is_following: reel.creator.is_following } });
    }
  };

  const handleShare = async () => {
    const url = `${window.location.origin}/reels/${reel.id}`;
    if (navigator.share) {
      navigator.share({ url, title: reel.caption || "Check out this reel" }).catch(() => {});
    } else {
      navigator.clipboard.writeText(url);
    }
    api.post(`/api/reels/${reel.id}/share`, { method: "link" }).catch(() => {});
    onUpdateReel({ share_count: reel.share_count + 1 });
  };

  const handleNotInterested = async () => {
    await api.post(`/api/reels/${reel.id}/not-interested`, {});
  };

  const renderCaption = (text) => {
    if (!text) return null;
    const parts = text.split(/(\s+)/);
    return parts.map((part, i) => {
      if (part.startsWith("#")) {
        return <span key={i} className="text-blue-300 font-medium">{part}</span>;
      }
      if (part.startsWith("@")) {
        return <span key={i} className="text-blue-300 font-medium">{part}</span>;
      }
      return part;
    });
  };

  return (
    <div ref={cardRef} className="relative h-screen w-full snap-start flex items-center justify-center bg-black">
      <video
        ref={videoRef}
        src={reel.video_url}
        poster={reel.thumbnail_url}
        loop
        muted={muted}
        playsInline
        className="h-full w-full object-contain"
        onClick={() => (videoRef.current.paused ? videoRef.current.play() : videoRef.current.pause())}
        onTimeUpdate={(e) => { maxWatchedRef.current = e.target.currentTime; }}
      />

      {/* mute toggle */}
      <button
        onClick={() => setMuted((m) => !m)}
        className="absolute top-4 right-4 bg-black/40 rounded-full p-2 text-white"
      >
        {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
      </button>

      {/* bottom-left: creator + caption + audio */}
      <div className="absolute bottom-6 left-3 right-16 text-white">
        <div className="flex items-center gap-2 mb-2">
          <img
            src={reel.creator.profile_picture_url || "/default-avatar.png"}
            alt={reel.creator.username}
            className="w-9 h-9 rounded-full border border-white/40 object-cover cursor-pointer"
            onClick={() => navigate(`/profile/${reel.creator.username}`)}
          />
          <span
            className="font-semibold text-sm cursor-pointer"
            onClick={() => navigate(`/profile/${reel.creator.username}`)}
          >
            {reel.creator.username}
          </span>
          {!reel.creator.is_following && (
            <button onClick={handleFollow} className="ml-2 text-xs border border-white/70 rounded px-2 py-0.5">
              Follow
            </button>
          )}
        </div>

        {reel.caption && (
          <p className="text-sm leading-snug mb-2 line-clamp-2">{renderCaption(reel.caption)}</p>
        )}

        {reel.audio && (
          <div className="flex items-center gap-1.5 text-xs text-white/90">
            <Music2 size={13} />
            <span className="truncate max-w-[200px]">{reel.audio.title}{reel.audio.artist ? ` · ${reel.audio.artist}` : ""}</span>
          </div>
        )}

        {reel.rank_reason && (
          <p className="text-[11px] text-white/50 mt-1 italic">{reel.rank_reason}</p>
        )}
      </div>

      {/* right action rail */}
      <div className="absolute bottom-6 right-3 flex flex-col items-center gap-5 text-white">
        <button onClick={handleLike} className="flex flex-col items-center gap-1">
          <Heart size={28} fill={reel.is_liked ? "#ef4444" : "none"} color={reel.is_liked ? "#ef4444" : "white"} />
          <span className="text-xs">{formatCount(reel.like_count)}</span>
        </button>

        <button onClick={onOpenComments} className="flex flex-col items-center gap-1">
          <MessageCircle size={26} />
          <span className="text-xs">{formatCount(reel.comment_count)}</span>
        </button>

        <button onClick={handleShare} className="flex flex-col items-center gap-1">
          <Send size={24} />
          <span className="text-xs">{formatCount(reel.share_count)}</span>
        </button>

        <button onClick={handleSave} className="flex flex-col items-center gap-1">
          <Bookmark size={24} fill={reel.is_saved ? "white" : "none"} />
        </button>

        <ReelMenu onNotInterested={handleNotInterested} reelId={reel.id} />
      </div>
    </div>
  );
}

function ReelMenu({ reelId, onNotInterested }) {
  const [open, setOpen] = useState(false);
  const report = async (reason) => {
    await api.post(`/api/reels/${reelId}/report`, { reason });
    setOpen(false);
  };
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}>
        <MoreHorizontal size={24} />
      </button>
      {open && (
        <div className="absolute bottom-8 right-0 bg-neutral-900 text-white text-sm rounded-lg shadow-lg w-44 py-1 z-10">
          <button onClick={() => { onNotInterested(); setOpen(false); }} className="w-full text-left px-3 py-2 hover:bg-neutral-800">
            Not interested
          </button>
          <button onClick={() => report("spam")} className="w-full text-left px-3 py-2 hover:bg-neutral-800">
            Report: Spam
          </button>
          <button onClick={() => report("harassment")} className="w-full text-left px-3 py-2 hover:bg-neutral-800">
            Report: Harassment
          </button>
          <button onClick={() => report("other")} className="w-full text-left px-3 py-2 hover:bg-neutral-800">
            Report: Other
          </button>
        </div>
      )}
    </div>
  );
}

function CommentsSheet({ reelId, onClose }) {
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/api/reels/${reelId}/comments`).then(({ data }) => {
      setComments(data);
      setLoading(false);
    });
  }, [reelId]);

  const submit = async () => {
    if (!text.trim()) return;
    const { data } = await api.post(`/api/reels/${reelId}/comments`, { text });
    setComments((prev) => [...prev, data]);
    setText("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white w-full max-w-md rounded-t-2xl h-[65vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <span className="font-semibold">Comments</span>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading && <p className="text-sm text-gray-400">Loading…</p>}
          {comments.map((c) => (
            <div key={c.id} className="flex gap-2">
              <img src={c.user.profile_picture_url || "/default-avatar.png"} className="w-8 h-8 rounded-full object-cover" alt="" />
              <div>
                <span className="font-medium text-sm mr-1">{c.user.username}</span>
                <span className="text-sm">{c.text}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="p-3 border-t flex gap-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Add a comment…"
            className="flex-1 border rounded-full px-4 py-2 text-sm outline-none"
          />
          <button onClick={submit} className="text-blue-500 font-semibold text-sm px-2">Post</button>
        </div>
      </div>
    </div>
  );
}

function formatCount(n) {
  if (!n) return "0";
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}