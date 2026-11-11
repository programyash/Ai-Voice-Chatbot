import { useCallback, useEffect, useRef, useState } from 'react'
import type { Role } from './api'

export type VoiceState = 'idle' | 'connecting' | 'listening' | 'processing' | 'speaking' | 'interrupted' | 'disconnected' | 'error'

export function useVoice(onTranscript: (role: Role, text: string) => void, onSession: (id: string) => void) {
  const [state, setState] = useState<VoiceState>('idle')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState('')
  const socket = useRef<WebSocket | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const captureContext = useRef<AudioContext | null>(null)
  const playbackContext = useRef<AudioContext | null>(null)
  const captureNode = useRef<AudioWorkletNode | null>(null)
  const playbackNodes = useRef<AudioBufferSourceNode[]>([])
  const nextPlayback = useRef(0)
  const intentionalStop = useRef(false)
  const retryTimer = useRef<number | null>(null)
  const transcriptRef = useRef(onTranscript)
  const sessionRef = useRef(onSession)
  transcriptRef.current = onTranscript
  sessionRef.current = onSession

  const stopPlayback = useCallback(() => {
    playbackNodes.current.forEach(node => { try { node.stop() } catch { /* already stopped */ } })
    playbackNodes.current = []
    nextPlayback.current = 0
  }, [])

  const cleanup = useCallback(() => {
    if (retryTimer.current !== null) window.clearTimeout(retryTimer.current)
    retryTimer.current = null
    socket.current?.close()
    socket.current = null
    captureNode.current?.disconnect()
    captureNode.current = null
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
    void captureContext.current?.close()
    captureContext.current = null
    stopPlayback()
    void playbackContext.current?.close()
    playbackContext.current = null
    setLevel(0)
  }, [stopPlayback])

  const stop = useCallback(() => {
    intentionalStop.current = true
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: 'stop' }))
    cleanup()
    setState('idle')
  }, [cleanup])

  useEffect(() => () => { intentionalStop.current = true; cleanup() }, [cleanup])

  const playPcm = useCallback(async (base64: string) => {
    const context = playbackContext.current
    if (!context) return
    if (context.state === 'suspended') await context.resume()
    const raw = atob(base64)
    const pcm = new Int16Array(raw.length / 2)
    for (let i = 0; i < pcm.length; i++) pcm[i] = (raw.charCodeAt(i * 2) | raw.charCodeAt(i * 2 + 1) << 8) << 16 >> 16
    const buffer = context.createBuffer(1, pcm.length, 24000)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)
    const startAt = Math.max(context.currentTime + 0.04, nextPlayback.current)
    source.start(startAt)
    nextPlayback.current = startAt + buffer.duration
    playbackNodes.current.push(source)
    source.onended = () => { playbackNodes.current = playbackNodes.current.filter(item => item !== source) }
  }, [])

  const start = useCallback(async (language: string, consentToStore: boolean) => {
    if (state !== 'idle' && state !== 'disconnected' && state !== 'error') return
    intentionalStop.current = false
    setError('')
    setState('connecting')
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error('This browser does not support live microphone audio. You can still use text chat.')
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false })
      captureContext.current = new AudioContext()
      playbackContext.current = new AudioContext()
      await Promise.all([captureContext.current.resume(), playbackContext.current.resume(), captureContext.current.audioWorklet.addModule('/pcm-worklet.js')])
      const source = captureContext.current.createMediaStreamSource(stream.current)
      const node = new AudioWorkletNode(captureContext.current, 'pcm-capture')
      const silent = captureContext.current.createGain()
      silent.gain.value = 0
      source.connect(node).connect(silent).connect(captureContext.current.destination)
      captureNode.current = node
      node.port.onmessage = event => {
        if (event.data.type === 'level') {
          setLevel(event.data.value)
          if (event.data.value > 0.2 && playbackNodes.current.length) stopPlayback()
        }
        if (event.data.type === 'pcm' && socket.current?.readyState === WebSocket.OPEN) {
          const bytes = new Uint8Array(event.data.buffer as ArrayBuffer)
          socket.current.send(JSON.stringify({ type: 'audio', data: btoa(String.fromCharCode(...bytes)) }))
        }
      }
      const connect = (attempt: number) => {
        if (intentionalStop.current) return
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${location.host}/ws/live`)
        socket.current = ws
        ws.onopen = () => ws.send(JSON.stringify({ type: 'start', language, consent_to_store: consentToStore }))
        ws.onmessage = event => {
          let data: Record<string, unknown>
          try { data = JSON.parse(event.data) } catch { return }
          if (data.type === 'session' && typeof data.conversation_id === 'string') sessionRef.current(data.conversation_id)
          if (data.type === 'status' && typeof data.value === 'string') setState(data.value as VoiceState)
          if (data.type === 'transcript' && typeof data.text === 'string' && (data.role === 'user' || data.role === 'assistant')) transcriptRef.current(data.role, data.text)
          if (data.type === 'audio' && typeof data.data === 'string') void playPcm(data.data)
          if (data.type === 'interrupted') { stopPlayback(); setState('interrupted') }
          if (data.type === 'error') { intentionalStop.current = true; setError(String(data.message)); cleanup(); setState('error') }
        }
        ws.onerror = () => setError('Voice connection failed. Check the server and try again.')
        ws.onclose = () => {
          if (intentionalStop.current) return
          stopPlayback()
          setState('disconnected')
          if (attempt < 2 && stream.current?.active) {
            setState('connecting')
            retryTimer.current = window.setTimeout(() => connect(attempt + 1), 1000 * (attempt + 1))
          } else {
            cleanup()
            setError(current => current || 'Voice disconnected. Press the microphone to reconnect.')
          }
        }
      }
      connect(0)
    } catch (cause) {
      cleanup()
      const message = cause instanceof Error ? cause.message : 'Microphone could not start.'
      setError(message.includes('Permission denied') || message.includes('NotAllowedError') ? 'Microphone access was denied. Allow it in your browser settings, or use text chat.' : message)
      setState('error')
    }
  }, [state, cleanup, playPcm, stopPlayback])

  return { state, level, error, start, stop }
}
