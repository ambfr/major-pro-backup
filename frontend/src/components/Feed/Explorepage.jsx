import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  Heart, MessageCircle, Play, Layers, X, ChevronLeft, ChevronRight,
  Bookmark, Search, Flame, UserPlus, Sparkles,
} from "lucide-react";

// ---- Mock data (stand-in for GET /api/feed/explore) ----------------------
const AVATAR = (seed) => `https://i.pravatar.cc/150?u=${seed}`;
const PHOTO = (seed, w = 600, h = 600) => `https://picsum.photos/seed/${seed}/${w}/${h}`;

const CATEGORIES = [
  { id: "for_you", label: "For You" },
  { id: "technology", label: "Technology" },
  { id: "fashion", label: "Fashion" },
  { id: "food", label: "Food" },
  { id: "sports", label: "Sports" },
  { id: "travel", label: "Travel" },
  { id: "music", label: "Music" },
  { id: "gaming", label: "Gaming" },
];

// Rough per-category emotional tone, used by the recommendation blender.
// Positive values = generally uplifting/calm content, negative = higher arousal/heavier content.
const CATEGORY_TONE = {
  technology: 0.1,
  fashion: 0.3,
  food: 0.5,
  sports: -0.1,
  travel: 0.6,
  music: 0.2,
  gaming: -0.2,
  for_you: 0,
};

const USERNAMES = [
  "wildframes", "citylightsco", "matcha.daily", "studio.forma", "trailmix_av",
  "paperandpine", "neon.archive", "quietcoast", "graincollective", "duskrunner",
  "clay.and.co", "farfieldstudio", "moonlitmesa", "saltandcedar", "afterglow.lab",
];

const HASHTAGS_BY_CATEGORY = {
  technology: ["#airesearch", "#gadgets", "#devtools", "#robotics"],
  fashion: ["#streetstyle", "#ootd", "#runway", "#thrifted"],
  food: ["#homecooking", "#foodie", "#bakingday", "#streetfood"],
  sports: ["#matchday", "#training", "#courtside", "#trailrun"],
  travel: ["#offthegrid", "#roadtrip", "#citywalks", "#slowtravel"],
  music: ["#studiosession", "#vinylclub", "#livesound", "#newrelease"],
  gaming: ["#speedrun", "#indiegames", "#patchnotes", "#coop"],
};

function makeMockPosts(count, offset = 0) {
  const categories = Object.keys(HASHTAGS_BY_CATEGORY);
  return Array.from({ length: count }).map((_, i) => {
    const n = offset + i;
    const isReel = n % 5 === 0;
    const isCarousel = !isReel && n % 7 === 0;
    const seed = `mg-${n}`;
    const category = categories[n % categories.length];
    const tags = HASHTAGS_BY_CATEGORY[category];
    // Deterministic pseudo-random signals so the mock behaves consistently across reloads.
    const rand = (k) => {
      const x = Math.sin(n * 999 + k) * 10000;
      return x - Math.floor(x);
    };
    return {
      id: n + 1,
      is_reel: isReel,
      category,
      hashtag: tags[n % tags.length],
      author: {
        username: USERNAMES[n % USERNAMES.length],
        avatar_url: AVATAR(seed),
      },
      caption: "Exploring textures and light on a slow afternoon.",
      likes_count: Math.floor(400 + rand(1) * 48000),
      comments_count: Math.floor(2 + rand(2) * 900),
      shares_count: Math.floor(rand(3) * 3000),
      // engagement_velocity approximates "likes gained in the last hour" for trending detection
      engagement_velocity: rand(4),
      // sentiment_score: -1 (heavy/negative) .. +1 (uplifting), as produced by the AI pipeline
      sentiment_score: Math.max(-1, Math.min(1, CATEGORY_TONE[category] + (rand(5) - 0.5) * 0.6)),
      media: isCarousel
        ? [
            { media_type: "image", url: PHOTO(seed + "-a", 900, 1125) },
            { media_type: "image", url: PHOTO(seed + "-b", 900, 1125) },
          ]
        : [
            {
              media_type: isReel ? "video" : "image",
              url: PHOTO(seed, 900, isReel ? 1600 : 1125),
              thumbnail_url: PHOTO(seed, 900, isReel ? 1600 : 1125),
            },
          ],
    };
  });
}

function makeSuggestedAccounts(count) {
  return Array.from({ length: count }).map((_, i) => {
    const username = USERNAMES[(i * 3) % USERNAMES.length];
    return {
      username,
      avatar_url: AVATAR(`acct-${username}-${i}`),
      mutuals: Math.floor(1 + Math.random() * 12),
      followed: false,
    };
  });
}

const WIDE_POSITIONS = new Set([3, 10]);
const PAGE_SIZE = 30;
const TRENDING_VELOCITY_THRESHOLD = 0.85;

function formatCount(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// ---------------------------------------------------------------------------
// Recommendation engine (mock of what a real backend endpoint would compute).
//
// score = interestMatch * 0.5 + engagement * 0.3 + trending * 0.2
// Then a "wellbeing" pass gently re-orders results so that a long run of
// heavy/negative-sentiment content doesn't stack up back-to-back — instead of
// hard-filtering anything, it interleaves calmer posts in to keep the shift
// in tone gradual rather than abrupt.
// ---------------------------------------------------------------------------
function scorePost(post, userInterests) {
  const interestWeight = userInterests[post.category] ?? 0.2;
  const engagement = Math.min(1, (post.likes_count + post.comments_count * 3) / 50000);
  const trending = post.engagement_velocity > TRENDING_VELOCITY_THRESHOLD ? 1 : post.engagement_velocity;
  return interestWeight * 0.5 + engagement * 0.3 + trending * 0.2;
}

function rankWithSentimentSmoothing(posts, userInterests, recentMoodTrend) {
  const scored = posts
    .map((p) => ({ post: p, score: scorePost(p, userInterests) }))
    .sort((a, b) => b.score - a.score);

  // recentMoodTrend: running average of sentiment_score already shown, -1..1.
  // If it's drifted heavy/negative, bias the next picks slightly toward calmer posts
  // instead of a hard cutoff, so the feed eases back rather than snapping.
  const result = [];
  let mood = recentMoodTrend;
  const pool = [...scored];

  while (pool.length) {
    let pickIdx = 0;
    if (mood < -0.15) {
      // find the best-scoring post among the calmer half of what's left
      const calmCandidates = pool
        .map((item, idx) => ({ idx, item }))
        .filter(({ item }) => item.post.sentiment_score >= -0.1)
        .sort((a, b) => b.item.score - a.item.score);
      if (calmCandidates.length) pickIdx = calmCandidates[0].idx;
    }
    const [chosen] = pool.splice(pickIdx, 1);
    result.push(chosen.post);
    mood = mood * 0.85 + chosen.post.sentiment_score * 0.15;
  }
  return result;
}

// ---------------------------------------------------------------------------
// UI pieces
// ---------------------------------------------------------------------------

function SearchBar({ value, onChange, suggestions, onPick }) {
  const [focused, setFocused] = useState(false);
  return (
    <div className="relative px-1 pt-1">
      <div className="flex items-center gap-2 bg-neutral-900 rounded-lg px-3 py-2">
        <Search className="w-4 h-4 text-neutral-400 shrink-0" />
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 120)}
          placeholder="Search accounts, hashtags, topics"
          className="bg-transparent outline-none text-sm text-white placeholder-neutral-500 w-full"
        />
        {value && (
          <button onClick={() => onChange("")} aria-label="Clear search" className="text-neutral-500 hover:text-neutral-300">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {focused && value && suggestions.length > 0 && (
        <div className="absolute z-20 left-1 right-1 mt-1 bg-neutral-900 border border-neutral-800 rounded-lg overflow-hidden">
          {suggestions.map((s) => (
            <button
              key={s.type + s.label}
              onMouseDown={() => onPick(s)}
              className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-neutral-200 hover:bg-neutral-800"
            >
              {s.type === "hashtag" ? (
                <span className="text-neutral-500">#</span>
              ) : (
                <img src={AVATAR(s.label)} alt="" className="w-5 h-5 rounded-full object-cover" />
              )}
              <span>{s.type === "hashtag" ? s.label.replace("#", "") : s.label}</span>
              <span className="ml-auto text-xs text-neutral-500">{s.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryChips({ categories, active, onSelect }) {
  return (
    <div className="flex gap-2 px-1 py-3 overflow-x-auto no-scrollbar">
      {categories.map((c) => (
        <button
          key={c.id}
          onClick={() => onSelect(c.id)}
          className={`shrink-0 px-3 py-1.5 rounded-full text-sm border transition-colors ${
            active === c.id
              ? "bg-white text-black border-white"
              : "bg-transparent text-neutral-300 border-neutral-700 hover:border-neutral-500"
          }`}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

function SuggestedAccountsRow({ accounts, onToggleFollow }) {
  if (!accounts.length) return null;
  return (
    <div className="px-1 pb-3">
      <div className="flex items-center gap-1.5 px-1 pb-2 text-sm text-neutral-300">
        <UserPlus className="w-3.5 h-3.5" />
        <span>Suggested for you</span>
      </div>
      <div className="flex gap-3 overflow-x-auto no-scrollbar px-1">
        {accounts.map((a) => (
          <div key={a.username} className="shrink-0 w-28 bg-neutral-900 rounded-lg p-3 flex flex-col items-center text-center">
            <img src={a.avatar_url} alt="" className="w-12 h-12 rounded-full object-cover mb-2" />
            <span className="text-xs text-white font-medium truncate w-full">{a.username}</span>
            <span className="text-[11px] text-neutral-500 mb-2">{a.mutuals} mutuals</span>
            <button
              onClick={() => onToggleFollow(a.username)}
              className={`text-xs w-full py-1 rounded-md font-medium ${
                a.followed ? "bg-neutral-800 text-neutral-300" : "bg-blue-600 text-white"
              }`}
            >
              {a.followed ? "Following" : "Follow"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendingHashtagsRow({ posts }) {
  const trending = useMemo(() => {
    const counts = {};
    posts.forEach((p) => {
      if (p.engagement_velocity > TRENDING_VELOCITY_THRESHOLD) {
        counts[p.hashtag] = (counts[p.hashtag] || 0) + 1;
      }
    });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([tag]) => tag);
  }, [posts]);

  if (!trending.length) return null;
  return (
    <div className="px-2 pb-3 flex items-center gap-2 flex-wrap">
      <span className="flex items-center gap-1 text-xs text-orange-400 font-medium">
        <Flame className="w-3.5 h-3.5" /> Trending
      </span>
      {trending.map((tag) => (
        <span key={tag} className="text-xs text-neutral-300 bg-neutral-900 px-2 py-1 rounded-full">
          {tag}
        </span>
      ))}
    </div>
  );
}

function ExploreTile({ post, wide, onOpen }) {
  const [hovered, setHovered] = useState(false);
  const media = post.media[0];
  const isVideo = media.media_type === "video" || post.is_reel;
  const multi = post.media.length > 1;
  const isTrending = post.engagement_velocity > TRENDING_VELOCITY_THRESHOLD;

  return (
    <button
      type="button"
      onClick={() => onOpen(post)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`relative overflow-hidden bg-neutral-900 ${wide ? "col-span-2 row-span-2" : ""}`}
      style={{ aspectRatio: "1 / 1" }}
    >
      <img
        src={media.thumbnail_url || media.url}
        alt=""
        loading="lazy"
        className="w-full h-full object-cover"
        style={{ transform: hovered ? "scale(1.03)" : "scale(1)", transition: "transform 200ms ease" }}
      />

      {isTrending && (
        <div className="absolute top-2 left-2 flex items-center gap-1 bg-black/60 text-orange-400 text-[11px] px-1.5 py-0.5 rounded">
          <Flame className="w-3 h-3" />
        </div>
      )}

      {(isVideo || multi) && (
        <div className="absolute top-2 right-2 text-white" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          {isVideo ? <Play className="w-4 h-4 fill-white" /> : <Layers className="w-4 h-4 fill-white" />}
        </div>
      )}

      <div
        className="absolute inset-0 flex items-center justify-center gap-6 text-white font-semibold"
        style={{
          background: "rgba(0,0,0,0.3)",
          opacity: hovered ? 1 : 0,
          transition: "opacity 120ms ease",
        }}
      >
        <span className="flex items-center gap-1.5 text-sm">
          <Heart className="w-4 h-4 fill-white" />
          {formatCount(post.likes_count)}
        </span>
        <span className="flex items-center gap-1.5 text-sm">
          <MessageCircle className="w-4 h-4 fill-white" />
          {formatCount(post.comments_count)}
        </span>
      </div>
    </button>
  );
}

function ReelsRow({ posts, onOpen }) {
  const reels = posts.filter((p) => p.is_reel).slice(0, 10);
  if (!reels.length) return null;
  return (
    <div className="px-1 pb-3">
      <div className="flex items-center gap-1.5 px-1 pb-2 text-sm text-neutral-300">
        <Play className="w-3.5 h-3.5 fill-neutral-300" />
        <span>Reels for you</span>
      </div>
      <div className="flex gap-2 overflow-x-auto no-scrollbar px-1">
        {reels.map((r) => (
          <button
            key={r.id}
            onClick={() => onOpen(r)}
            className="relative shrink-0 rounded-lg overflow-hidden bg-neutral-900"
            style={{ width: 110, aspectRatio: "9 / 16" }}
          >
            <img src={r.media[0].thumbnail_url} alt="" className="w-full h-full object-cover" />
            <div className="absolute bottom-1.5 left-1.5 flex items-center gap-1 text-white text-[11px]" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.6))" }}>
              <Play className="w-3 h-3 fill-white" />
              {formatCount(r.likes_count)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Lightbox({ posts, index, onClose, onNavigate }) {
  const post = posts[index];
  const media = post.media[0];
  const isVideo = media.media_type === "video" || post.is_reel;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") onNavigate(-1);
      if (e.key === "ArrowRight") onNavigate(1);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose, onNavigate]);

  const hasPrev = index > 0;
  const hasNext = index < posts.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.92)" }}
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/80 hover:text-white p-2"
        aria-label="Close"
      >
        <X className="w-6 h-6" />
      </button>

      {hasPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); onNavigate(-1); }}
          className="absolute left-2 sm:left-6 text-white/70 hover:text-white p-2"
          aria-label="Previous"
        >
          <ChevronLeft className="w-8 h-8" />
        </button>
      )}
      {hasNext && (
        <button
          onClick={(e) => { e.stopPropagation(); onNavigate(1); }}
          className="absolute right-2 sm:right-6 text-white/70 hover:text-white p-2"
          aria-label="Next"
        >
          <ChevronRight className="w-8 h-8" />
        </button>
      )}

      <div
        className="bg-black w-full max-w-4xl mx-4 max-h-[88vh] flex flex-col sm:flex-row overflow-hidden rounded-sm border border-neutral-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-black flex items-center justify-center sm:w-[62%] max-h-[50vh] sm:max-h-[88vh]">
          <img src={media.url} alt="" className="max-h-[50vh] sm:max-h-[88vh] w-full object-contain" />
        </div>

        <div className="sm:w-[38%] flex flex-col text-white">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-800">
            <img src={post.author.avatar_url} alt="" className="w-8 h-8 rounded-full object-cover" />
            <span className="font-semibold text-sm">{post.author.username}</span>
            <span className="ml-auto text-xs text-neutral-500">{post.hashtag}</span>
          </div>

          <div className="flex-1 px-4 py-3 overflow-y-auto">
            <div className="flex gap-3 text-sm">
              <img src={post.author.avatar_url} alt="" className="w-8 h-8 rounded-full object-cover shrink-0" />
              <p>
                <span className="font-semibold mr-1.5">{post.author.username}</span>
                {post.caption}
              </p>
            </div>
          </div>

          <div className="px-4 pt-3 pb-2 border-t border-neutral-800">
            <div className="flex items-center gap-4 mb-2">
              <Heart className="w-6 h-6" />
              <MessageCircle className="w-6 h-6" />
              <Bookmark className="w-6 h-6 ml-auto" />
            </div>
            <p className="text-sm font-semibold">{formatCount(post.likes_count)} likes</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InstagramExploreRecreation() {
  const [allPosts, setAllPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lightboxIndex, setLightboxIndex] = useState(null);
  const [activeCategory, setActiveCategory] = useState("for_you");
  const [query, setQuery] = useState("");
  const [suggestedAccounts, setSuggestedAccounts] = useState([]);
  const sentinelRef = useRef(null);
  const offsetRef = useRef(0);

  // Stand-in for the user's interest profile, as computed from likes / saves /
  // comments / accounts followed / watch history by the recommendation service.
  const [userInterests] = useState({
    technology: 0.9,
    music: 0.6,
    travel: 0.5,
    food: 0.4,
    fashion: 0.3,
    gaming: 0.3,
    sports: 0.2,
    for_you: 0.5,
  });
  // Running sentiment average of what's already been shown this session — feeds
  // the smoothing pass so a spike of heavier content doesn't compound.
  const moodTrendRef = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => {
      const initial = makeMockPosts(PAGE_SIZE, 0);
      offsetRef.current = PAGE_SIZE;
      setAllPosts(initial);
      setSuggestedAccounts(makeSuggestedAccounts(8));
      setLoading(false);
    }, 500);
    return () => clearTimeout(t);
  }, []);

  const loadMore = useCallback(() => {
    setAllPosts((prev) => {
      const next = makeMockPosts(12, offsetRef.current);
      offsetRef.current += 12;
      return [...prev, ...next];
    });
  }, []);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || loading) return;
    const observer = new IntersectionObserver(
      (entries) => entries[0].isIntersecting && loadMore(),
      { rootMargin: "600px 0px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loading, loadMore]);

  // Filter by category, then rank with the recommendation + sentiment-smoothing engine.
  const rankedPosts = useMemo(() => {
    const filtered =
      activeCategory === "for_you" ? allPosts : allPosts.filter((p) => p.category === activeCategory);
    const ranked = rankWithSentimentSmoothing(filtered, userInterests, moodTrendRef.current);
    if (ranked.length) {
      const recent = ranked.slice(0, 10);
      moodTrendRef.current = recent.reduce((s, p) => s + p.sentiment_score, 0) / recent.length;
    }
    return ranked;
  }, [allPosts, activeCategory, userInterests]);

  const searchSuggestions = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.trim().toLowerCase();
    const tagMatches = Array.from(
      new Set(allPosts.map((p) => p.hashtag).filter((h) => h.toLowerCase().includes(q)))
    )
      .slice(0, 4)
      .map((label) => ({ type: "hashtag", label }));
    const accountMatches = Array.from(new Set(allPosts.map((p) => p.author.username)))
      .filter((u) => u.toLowerCase().includes(q))
      .slice(0, 4)
      .map((label) => ({ type: "account", label }));
    return [...accountMatches, ...tagMatches];
  }, [query, allPosts]);

  const displayedPosts = useMemo(() => {
    if (!query.trim()) return rankedPosts;
    const q = query.trim().toLowerCase();
    return rankedPosts.filter(
      (p) => p.author.username.toLowerCase().includes(q) || p.hashtag.toLowerCase().includes(q)
    );
  }, [rankedPosts, query]);

  const openAt = (post) => {
    const idx = displayedPosts.findIndex((p) => p.id === post.id);
    if (idx !== -1) setLightboxIndex(idx);
  };

  const navigate = (delta) => {
    setLightboxIndex((prev) => {
      if (prev === null) return prev;
      const next = prev + delta;
      if (next < 0 || next >= displayedPosts.length) return prev;
      if (next >= displayedPosts.length - 3) loadMore();
      return next;
    });
  };

  const toggleFollow = (username) => {
    setSuggestedAccounts((prev) =>
      prev.map((a) => (a.username === username ? { ...a, followed: !a.followed } : a))
    );
  };

  return (
    <div className="min-h-screen" style={{ background: "#000" }}>
      <style>{`.no-scrollbar::-webkit-scrollbar{display:none}.no-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
      <div className="max-w-4xl mx-auto px-1 py-3">
        <SearchBar
          value={query}
          onChange={setQuery}
          suggestions={searchSuggestions}
          onPick={(s) => setQuery(s.type === "hashtag" ? s.label : s.label)}
        />

        <CategoryChips categories={CATEGORIES} active={activeCategory} onSelect={setActiveCategory} />

        {!loading && !query && (
          <>
            <TrendingHashtagsRow posts={rankedPosts} />
            <SuggestedAccountsRow accounts={suggestedAccounts} onToggleFollow={toggleFollow} />
            <ReelsRow posts={rankedPosts} onOpen={openAt} />
            <div className="flex items-center gap-1.5 px-2 pb-2 text-xs text-neutral-500">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Recommended for you, eased to your recent mood</span>
            </div>
          </>
        )}

        {loading ? (
          <div className="grid grid-cols-3 gap-1" style={{ gridAutoFlow: "dense" }}>
            {Array.from({ length: PAGE_SIZE }).map((_, i) => (
              <div
                key={i}
                className={`bg-neutral-900 animate-pulse ${WIDE_POSITIONS.has(i % 15) ? "col-span-2 row-span-2" : ""}`}
                style={{ aspectRatio: "1 / 1" }}
              />
            ))}
          </div>
        ) : displayedPosts.length === 0 ? (
          <div className="text-center text-neutral-500 text-sm py-16">No results for "{query}"</div>
        ) : (
          <div className="grid grid-cols-3 gap-1" style={{ gridAutoFlow: "dense" }}>
            {displayedPosts.map((post, idx) => (
              <ExploreTile key={post.id} post={post} wide={WIDE_POSITIONS.has(idx % 15)} onOpen={openAt} />
            ))}
          </div>
        )}
        <div ref={sentinelRef} className="h-1" />
      </div>

      {lightboxIndex !== null && (
        <Lightbox
          posts={displayedPosts}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={navigate}
        />
      )}
    </div>
  );
}