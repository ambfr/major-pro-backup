import React, { useEffect, useState, useCallback, useRef } from "react";
import { Heart, MessageCircle, Play, Layers, X, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * ExplorePage
 * Instagram-style explore grid for MindGram.
 * GET /api/feed/explore?limit=&offset= (see routers/feed.py -> get_explore)
 *
 * - Infinite scroll via IntersectionObserver sentinel
 * - Skeleton tiles while loading (first page) instead of a spinner
 * - Deliberate wide-tile rhythm mimicking IG's explore algorithm feel
 * - Tapping a tile opens an in-place lightbox modal, with left/right
 *   navigation between loaded posts and Escape/backdrop to close
 *
 * Pagination: confirmed against routers/feed.py -> get_explore, which
 * takes limit/offset and returns a plain list[PostOut], ordered by
 * feed_score desc, likes_count desc, id desc (stable across pages).
 */

const PAGE_SIZE = 30;
const API_BASE = "/api/feed";

// Which grid positions (within each 15-tile cycle) get a 2x2 "wide" tile.
// An irregular repeat reads closer to IG's ranking-driven placement than
// a strict modulo would.
const WIDE_POSITIONS = new Set([3, 10]);

function useExplorePosts() {
  const [posts, setPosts] = useState([]);
  const [offset, setOffset] = useState(0); // pagination cursor (offset-based)
  const [hasMore, setHasMore] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  const fetchPage = useCallback(async (pageOffset, isInitial) => {
    if (isInitial) setInitialLoading(true);
    else setLoadingMore(true);
    setError(null);
    try {
      const token = localStorage.getItem("token");
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(pageOffset),
      });
      const res = await fetch(`${API_BASE}/explore?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Explore fetch failed: ${res.status}`);
      const items = await res.json(); // always a plain list[PostOut]

      setPosts((prev) => (isInitial ? items : [...prev, ...items]));
      setOffset(pageOffset + items.length);
      // A short page means we've hit the end of the 14-day / reel-excluded window
      setHasMore(items.length === PAGE_SIZE);
    } catch (err) {
      setError(err.message || "Failed to load explore feed");
    } finally {
      setInitialLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    fetchPage(0, true);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    fetchPage(offset, false);
  }, [offset, hasMore, loadingMore, fetchPage]);

  const retry = useCallback(() => fetchPage(0, true), [fetchPage]);

  return { posts, initialLoading, loadingMore, hasMore, error, loadMore, retry };
}

function formatCount(n) {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function SkeletonTile({ wide }) {
  return (
    <div
      className={`bg-neutral-900 animate-pulse ${wide ? "col-span-2 row-span-2" : ""}`}
      style={{ aspectRatio: "1 / 1" }}
    />
  );
}

function ExploreTile({ post, wide, onOpen }) {
  const [hovered, setHovered] = useState(false);
  const media = post.media?.[0];
  const isVideo = media?.media_type === "video" || post.is_reel;
  const thumbUrl = media?.thumbnail_url || media?.url || post.image_url;
  const multiImage = (post.media?.length || 0) > 1;

  return (
    <button
      type="button"
      onClick={() => onOpen(post)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`relative group overflow-hidden bg-neutral-900 focus:outline-none focus:ring-2 focus:ring-white/60 focus:ring-inset ${
        wide ? "col-span-2 row-span-2" : ""
      }`}
      style={{ aspectRatio: "1 / 1" }}
    >
      {thumbUrl ? (
        <img
          src={thumbUrl}
          alt={post.caption ? post.caption.slice(0, 60) : "Post"}
          loading="lazy"
          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-neutral-500 text-sm">
          No preview
        </div>
      )}

      {(isVideo || multiImage) && (
        <div className="absolute top-2 right-2 text-white drop-shadow-md">
          {isVideo ? <Play className="w-5 h-5 fill-white" /> : <Layers className="w-5 h-5 fill-white" />}
        </div>
      )}

      <div
        className={`absolute inset-0 bg-black/40 flex items-center justify-center gap-6 text-white font-semibold transition-opacity duration-150 ${
          hovered ? "opacity-100" : "opacity-0"
        }`}
      >
        <span className="flex items-center gap-1.5">
          <Heart className="w-5 h-5 fill-white" />
          {formatCount(post.likes_count)}
        </span>
        <span className="flex items-center gap-1.5">
          <MessageCircle className="w-5 h-5 fill-white" />
          {formatCount(post.comments_count)}
        </span>
      </div>
    </button>
  );
}

function PostLightbox({ posts, index, onClose, onNavigate }) {
  const post = posts[index];
  const media = post.media?.[0];
  const isVideo = media?.media_type === "video" || post.is_reel;
  const mediaUrl = media?.url || post.image_url;

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") onNavigate(-1);
      if (e.key === "ArrowRight") onNavigate(1);
    };
    window.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose, onNavigate]);

  if (!post) return null;

  const hasPrev = index > 0;
  const hasNext = index < posts.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 text-white/80 hover:text-white p-2 focus:outline-none focus:ring-2 focus:ring-white/60 rounded-full"
        aria-label="Close"
      >
        <X className="w-6 h-6" />
      </button>

      {hasPrev && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onNavigate(-1);
          }}
          className="absolute left-2 sm:left-4 text-white/70 hover:text-white p-2 focus:outline-none focus:ring-2 focus:ring-white/60 rounded-full"
          aria-label="Previous post"
        >
          <ChevronLeft className="w-8 h-8" />
        </button>
      )}

      {hasNext && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onNavigate(1);
          }}
          className="absolute right-2 sm:right-4 text-white/70 hover:text-white p-2 focus:outline-none focus:ring-2 focus:ring-white/60 rounded-full"
          aria-label="Next post"
        >
          <ChevronRight className="w-8 h-8" />
        </button>
      )}

      <div
        className="bg-neutral-950 max-w-4xl w-full mx-4 sm:mx-auto max-h-[90vh] flex flex-col sm:flex-row overflow-hidden rounded-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-black flex items-center justify-center sm:w-[60%] max-h-[60vh] sm:max-h-[90vh]">
          {mediaUrl ? (
            isVideo ? (
              <video src={mediaUrl} controls autoPlay className="max-h-[60vh] sm:max-h-[90vh] w-full" />
            ) : (
              <img src={mediaUrl} alt={post.caption || "Post"} className="max-h-[60vh] sm:max-h-[90vh] w-full object-contain" />
            )
          ) : (
            <div className="text-neutral-500 py-24">No preview</div>
          )}
        </div>

        <div className="sm:w-[40%] flex flex-col p-4 text-white overflow-y-auto">
          <div className="flex items-center gap-2 mb-3">
            {post.author?.avatar_url && (
              <img src={post.author.avatar_url} alt="" className="w-8 h-8 rounded-full object-cover" />
            )}
            <span className="font-semibold text-sm">{post.author?.username || "Unknown"}</span>
          </div>

          {post.caption && <p className="text-sm text-neutral-200 mb-4">{post.caption}</p>}

          <div className="mt-auto flex items-center gap-5 pt-3 border-t border-neutral-800 text-sm text-neutral-300">
            <span className="flex items-center gap-1.5">
              <Heart className="w-4 h-4" />
              {formatCount(post.likes_count)}
            </span>
            <span className="flex items-center gap-1.5">
              <MessageCircle className="w-4 h-4" />
              {formatCount(post.comments_count)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ExplorePage() {
  const { posts, initialLoading, loadingMore, hasMore, error, loadMore, retry } = useExplorePosts();
  const sentinelRef = useRef(null);
  const [lightboxIndex, setLightboxIndex] = useState(null);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: "600px 0px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore]);

  const openAt = (post) => {
    const idx = posts.findIndex((p) => p.id === post.id);
    setLightboxIndex(idx === -1 ? null : idx);
  };

  const navigate = (delta) => {
    setLightboxIndex((prev) => {
      if (prev === null) return prev;
      const next = prev + delta;
      if (next < 0 || next >= posts.length) return prev;
      // Load more when nearing the end while browsing the lightbox
      if (next >= posts.length - 3) loadMore();
      return next;
    });
  };

  return (
    <div className="max-w-5xl mx-auto px-2 sm:px-4 py-4">
      <h1 className="text-xl font-semibold mb-4 px-1 text-white">Explore</h1>

      {!initialLoading && error && posts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-neutral-400">
          <p className="mb-3">{error}</p>
          <button
            onClick={retry}
            className="px-4 py-2 rounded-md bg-neutral-800 text-white hover:bg-neutral-700"
          >
            Retry
          </button>
        </div>
      )}

      {!initialLoading && !error && posts.length === 0 && (
        <div className="flex items-center justify-center py-24 text-neutral-400">
          Nothing to explore yet.
        </div>
      )}

      {(initialLoading || posts.length > 0) && (
        <div className="grid grid-cols-3 gap-1 sm:gap-2" style={{ gridAutoFlow: "dense" }}>
          {initialLoading
            ? Array.from({ length: PAGE_SIZE }).map((_, idx) => (
                <SkeletonTile key={idx} wide={WIDE_POSITIONS.has(idx % 15)} />
              ))
            : posts.map((post, idx) => (
                <ExploreTile
                  key={post.id}
                  post={post}
                  wide={WIDE_POSITIONS.has(idx % 15)}
                  onOpen={openAt}
                />
              ))}

          {loadingMore &&
            Array.from({ length: 6 }).map((_, idx) => <SkeletonTile key={`more-${idx}`} wide={false} />)}
        </div>
      )}

      {!initialLoading && hasMore && <div ref={sentinelRef} className="h-1" />}

      {!hasMore && posts.length > 0 && (
        <p className="text-center text-neutral-500 text-sm py-8">You're all caught up</p>
      )}

      {lightboxIndex !== null && (
        <PostLightbox
          posts={posts}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={navigate}
        />
      )}
    </div>
  );
}