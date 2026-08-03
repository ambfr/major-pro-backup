import { useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'

export default function StoryUploader({ onClose, onUploaded }) {
  const { api } = useAuth()
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileType, setFileType] = useState(null) // 'image' | 'video'
  const [posting, setPosting] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef()

  const handleFile = (e) => {
    const selected = e.target.files?.[0]
    if (!selected) return

    const isVideo = selected.type.startsWith('video/')
    const isImage = selected.type.startsWith('image/')
    if (!isVideo && !isImage) {
      setError('Please choose an image or video file.')
      return
    }

    setError('')
    setFile(selected)
    setFileType(isVideo ? 'video' : 'image')
    setPreviewUrl(URL.createObjectURL(selected))
  }

  const clearFile = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(null)
    setFileType(null)
    setPreviewUrl(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleSubmit = async () => {
    if (!text.trim() && !file) {
      setError('Add a photo, video, or some text first.')
      return
    }

    setPosting(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('text', text.trim())
      // Field name must match the backend exactly — 'image' for images,
      // 'video' for videos (same convention as ComposePost's post upload).
      if (file) {
        formData.append(fileType === 'video' ? 'video' : 'image', file)
      }

      const res = await api.post('/stories', formData)
      onUploaded?.(res.data)
      onClose?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to post story.')
    } finally {
      setPosting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card w-full max-w-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-base text-white">Add to your story</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-white/10"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {previewUrl ? (
          <div className="relative mb-3 rounded-xl overflow-hidden bg-black">
            {fileType === 'video' ? (
              <video src={previewUrl} className="max-h-80 w-full object-contain" controls />
            ) : (
              <img src={previewUrl} alt="Story preview" className="max-h-80 w-full object-contain" />
            )}
            <button
              onClick={clearFile}
              className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 text-white
                         flex items-center justify-center text-xs hover:bg-black/80"
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => fileRef.current?.click()}
            className="mb-3 flex h-40 w-full flex-col items-center justify-center gap-1
                       rounded-xl border-2 border-dashed border-white/15 text-gray-400
                       hover:border-brand-500/50 hover:text-brand-300 transition-all"
          >
            <span className="text-2xl">+</span>
            <span className="text-sm">Add photo or video</span>
          </button>
        )}

        <input
          ref={fileRef}
          type="file"
          accept="image/*,video/*"
          onChange={handleFile}
          className="hidden"
        />

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Say something..."
          rows={2}
          className="input-field resize-none text-sm w-full mb-3"
        />

        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={posting}
          className="btn-primary w-full py-2 text-sm disabled:opacity-40"
        >
          {posting ? 'Posting...' : 'Share to Story'}
        </button>
      </div>
    </div>
  )
}