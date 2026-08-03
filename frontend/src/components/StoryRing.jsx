import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function StoryRing({
  currentUserId,
  currentUser,
  followingIds = [],
  refreshKey = 0,
  onOpenViewer,      // (userId) => void
  onOpenUploader,    // () => void
}) {
  const { api } = useAuth();
  const [entries, setEntries] = useState([]); // [{ user, hasStory, seen }]
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const ids = [currentUserId, ...followingIds.filter((id) => id !== currentUserId)];

      const results = await Promise.all(
        ids.map(async (id) => {
          try {
            const res = await api.get(`/stories/user/${id}`);
            return { userId: id, stories: res.data || [] };
          } catch {
            return { userId: id, stories: [] };
          }
        })
      );

      if (!cancelled) {
        setEntries(results.filter((r) => r.stories.length > 0 || r.userId === currentUserId));
        setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [currentUserId, followingIds, refreshKey, api]);

  if (loading) {
    return (
      <div className="flex gap-4 overflow-x-auto px-3 py-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex flex-col items-center gap-1">
            <div className="h-16 w-16 animate-pulse rounded-full bg-neutral-200" />
            <div className="h-2 w-10 animate-pulse rounded bg-neutral-200" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-4 overflow-x-auto px-3 py-3 scrollbar-hide">
      {entries.map((entry) => (
        <StoryBubble
          key={entry.userId}
          entry={entry}
          isSelf={entry.userId === currentUserId}
          currentUser={currentUser}
          onClick={() => {
            if (entry.userId === currentUserId && entry.stories.length === 0) {
              onOpenUploader?.();
            } else {
              onOpenViewer?.(entry.userId);
            }
          }}
          onAddStory={entry.userId === currentUserId ? onOpenUploader : undefined}
        />
      ))}
    </div>
  );
}

function StoryBubble({ entry, isSelf, currentUser, onClick, onAddStory }) {
  const { stories } = entry;
  const hasStory = stories.length > 0;
  const allSeen = hasStory && stories.every((s) => s.viewed_by_me);
  const user = hasStory ? stories[0].author : (isSelf ? currentUser : entry.user);

  const avatarUrl = user?.avatar_url
    || entry.avatarUrl
    || (user?.username ? `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.username}` : "/default-avatar.png");
  const username = user?.username || entry.username || (isSelf ? "Your story" : "");

  return (
    <div className="relative flex w-16 shrink-0 flex-col items-center gap-1">
      <button
        type="button"
        onClick={onClick}
        className="flex w-16 flex-col items-center gap-1"
      >
        <div
          className={[
            "flex h-16 w-16 items-center justify-center rounded-full p-[2px]",
            !hasStory
              ? "bg-neutral-200"
              : allSeen
              ? "bg-neutral-300"
              : "bg-gradient-to-tr from-amber-400 via-pink-500 to-purple-600",
          ].join(" ")}
        >
          <div className="relative h-full w-full rounded-full bg-white p-[2px]">
            <img
              src={avatarUrl}
              alt={username}
              className="h-full w-full rounded-full object-cover"
            />
          </div>
        </div>
        <span className="w-full truncate text-center text-[11px] text-gray-400">
          {isSelf ? "Your story" : username}
        </span>
      </button>
      {isSelf && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onAddStory?.(); }}
          className="absolute left-[calc(50%+1.25rem)] top-[calc(4rem-0.625rem)] flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-xs text-white ring-2 ring-[#0a0a0a]"
          aria-label="Add to your story"
        >
          +
        </button>
      )}
    </div>
  );
}