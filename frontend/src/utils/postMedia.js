const imageExt = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif']
const videoExt = ['.mp4', '.webm', '.ogg']

function isImageUrl(url) {
  if (!url || typeof url !== 'string') return false
  const lower = url.split('?')[0].toLowerCase()
  return imageExt.some(ext => lower.endsWith(ext))
}

function isVideoUrl(url) {
  if (!url || typeof url !== 'string') return false
  const lower = url.split('?')[0].toLowerCase()
  return videoExt.some(ext => lower.endsWith(ext))
}

export function getPostMedia(post) {
  if (!post) return []

  // Common shapes: post.media as array of URLs, post.media as JSON string, post.attachments
  let raw = []

  if (Array.isArray(post.media) && post.media.length) raw = post.media
  else if (typeof post.media === 'string') {
    try {
      const parsed = JSON.parse(post.media)
      if (Array.isArray(parsed)) raw = parsed
      else if (typeof parsed === 'string') raw = [parsed]
    } catch {
      // fallback to treating as single URL
      raw = post.media ? [post.media] : []
    }
  } else if (Array.isArray(post.attachments) && post.attachments.length) {
    raw = post.attachments
  } else if (post.attachment) {
    raw = [post.attachment]
  }

  // Normalize to objects: { url, type }
  const normalized = raw.map(item => {
    const url = typeof item === 'string' ? item : item?.url || item?.file
    if (!url) return null
    const type = isImageUrl(url) ? 'image' : isVideoUrl(url) ? 'video' : 'image'
    return { url, type }
  }).filter(Boolean)

  return normalized
}

export function getPostThumbnail(post) {
  const media = getPostMedia(post)
  if (media.length) return media[0]
  if (post.thumbnail) return (typeof post.thumbnail === 'string') ? { url: post.thumbnail, type: isVideoUrl(post.thumbnail) ? 'video' : 'image' } : null
  return null
}

export default { getPostMedia, getPostThumbnail }
