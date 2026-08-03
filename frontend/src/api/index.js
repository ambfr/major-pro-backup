import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Posts
export const createPost = (data) => api.post('/posts', data)
export const getUserPosts = (userId, limit = 20) => api.get(`/posts/user/${userId}?limit=${limit}`)
export const getPost = (postId) => api.get(`/posts/${postId}`)

// Feed
export const getFeed = (userId, limit = 20) => api.get(`/feed/${userId}?limit=${limit}`)

// Messages
export const sendMessage = (data) => api.post('/messages', data)
export const getThread = (a, b) => api.get(`/messages/thread/${a}/${b}`)
export const getUserMessages = (userId) => api.get(`/messages/${userId}`)

// Interactions
export const recordInteraction = (data) => api.post('/interactions', data)
export const addComment = (data) => api.post('/interactions/comment', data)
export const getComments = (postId) => api.get(`/interactions/comments/${postId}`)
export const reportPost = (data) => api.post('/interactions/report', data)
export const recordImpression = (data) => api.post('/interactions/impression', data)

// Analytics
export const getAnalytics = (userId, limit = 50) => api.get(`/analytics/${userId}?limit=${limit}`)
export const getRisk = (userId) => api.get(`/analytics/${userId}/risk`)
export const getSuggestions = (userId) => api.get(`/analytics/${userId}/suggestions`)

// Agents
export const getAgentStatus = (userId) => api.get(`/agents/status/${userId}`)
export const getAgentHistory = (userId) => api.get(`/agents/history/${userId}`)

export default api
