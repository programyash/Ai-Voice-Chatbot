export type Role = 'user' | 'assistant'
export type Message = { role: Role, body: string, created_at?: string }
export type Health = { status: string, gemini_configured: boolean, voice_available: boolean, text_mode: 'gemini' | 'local_reference', knowledge_export_enabled: boolean, knowledge_chunks: number, embedded_chunks: number, chat_model: string, live_model: string }

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
  return data as T
}
