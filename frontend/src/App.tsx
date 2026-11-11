import { useEffect, useRef, useState } from 'react'
import { ArrowRight, AudioLines, Building2, ChevronRight, CircleHelp, MapPin, MessageSquare, Mic, Send, ShieldCheck, Square } from 'lucide-react'
import { request, type Health, type Message } from './api'
import { useVoice } from './useVoice'

const examples = [
  'Tell me about the villa plots',
  'How far is IGI Airport?',
  'Compare Project A and Project B',
  'Are the schools in Project B already open?',
]

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [language, setLanguage] = useState('en')
  const [consent, setConsent] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [activeProject, setActiveProject] = useState<'A' | 'B'>('A')
  const bottom = useRef<HTMLDivElement>(null)
  const lastVoiceRole = useRef<'user' | 'assistant' | null>(null)
  const voice = useVoice((role, text) => setMessages(previous => {
    if (lastVoiceRole.current === role && previous.length && previous[previous.length - 1].role === role) {
      const last = previous[previous.length - 1]
      return [...previous.slice(0, -1), { ...last, body: `${last.body} ${text}` }]
    }
    lastVoiceRole.current = role
    return [...previous, { role, body: text }]
  }), id => { lastVoiceRole.current = null; setConversationId(id) })

  useEffect(() => { request<Health>('/api/health').then(setHealth).catch(() => setHealth(null)) }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, pending])

  const send = async (text = draft) => {
    const trimmed = text.trim()
    if (!trimmed || pending) return
    lastVoiceRole.current = null
    setDraft(''); setError(''); setPending(true)
    setMessages(previous => [...previous, { role: 'user', body: trimmed }])
    try {
      const response = await request<{ conversation_id: string, answer: string }>('/api/chat', { method: 'POST', body: JSON.stringify({ conversation_id: conversationId, message: trimmed, language, consent_to_store: consent }) })
      setConversationId(response.conversation_id)
      setMessages(previous => [...previous, { role: 'assistant', body: response.answer }])
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to send message.'); setMessages(previous => previous.slice(0, -1)) }
    finally { setPending(false) }
  }

  const voiceActive = !['idle','disconnected','error'].includes(voice.state)
  const status = voiceActive ? voice.state : health?.voice_available ? 'Ready for voice' : health?.text_mode === 'local_reference' ? 'Local source mode · voice paused' : 'Gemini setup needed'

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark"><Building2 size={21} strokeWidth={1.9}/></span><span>Township <strong>Advisor</strong></span></div></header>

    <main>
      <section className="intro"><div><div className="eyebrow"><span className="eyebrow-line"/>YOUR TOWNSHIP VOICE ASSISTANT</div><h1>Find your place in<br/><em>the township.</em></h1><p>Ask about residential plots, facilities, connectivity, and what makes each project distinct. Speak naturally or start with a message.</p></div><div className="intro-stat"><span className="stat-number">8,250<span> acres</span></span><span className="stat-caption">INTEGRATED TOWNSHIP · APPROXIMATE</span><div className="stat-divider"/><span className="stat-number small">02<span> projects</span></span><span className="stat-caption">ONE CONNECTED COMMUNITY</span></div></section>

      <div className="content-grid"><section className="assistant-card" id="assistant" aria-label="Voice assistant">
        <div className="assistant-header"><div><div className="eyebrow">YOUR PERSONAL GUIDE</div><h2>Ask anything about the township.</h2></div><div className={`connection ${voiceActive ? 'connected' : ''}`}><span className="status-dot"/>{status}</div></div>
        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? <div className="empty-state"><span className="empty-icon"><MessageSquare size={26} strokeWidth={1.5}/></span><h3>Where would you like to begin?</h3><p>I'm here to help you understand the projects and the community around them.</p><div className="question-list">{examples.map(question => <button key={question} onClick={() => void send(question)}>{question}<ChevronRight size={16}/></button>)}</div></div> : <div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${index}-${message.role}`}><span className="message-label">{message.role === 'assistant' ? 'ADVISOR' : 'YOU'}</span><p>{message.body}</p></div>)}{pending && <div className="thinking"><span/><span/><span/> Thinking</div>}<div ref={bottom}/></div>}
        </div>
        <div className="assistant-controls">
          {(voice.error || error) && <div className="error-banner" role="alert"><CircleHelp size={17}/>{voice.error || error}</div>}
          <form className="composer" onSubmit={event => { event.preventDefault(); void send() }}>
            <input aria-label="Message" value={draft} onChange={event => setDraft(event.target.value)} placeholder={voiceActive ? "Voice connected · speak or type here…" : "Or type a question here…"} maxLength={4000}/>
            {voiceActive && (
              <div className="audio-meter active" aria-label="Audio activity">
                <i style={{ height: `${7 + voice.level * 18}px` }}/>
                <i style={{ height: `${10 + voice.level * 29}px` }}/>
                <i style={{ height: `${6 + voice.level * 22}px` }}/>
                <i style={{ height: `${9 + voice.level * 25}px` }}/>
              </div>
            )}
            <button
              type="button"
              className={`mic-button ${voiceActive ? 'active' : ''}`}
              aria-label={voiceActive ? 'Stop voice conversation' : 'Start voice conversation'}
              title={voiceActive ? 'Stop voice conversation' : 'Start voice conversation'}
              onClick={() => { lastVoiceRole.current = null; if (voiceActive) voice.stop(); else void voice.start(language, consent) }}
              disabled={!health?.voice_available}
            >
              {voiceActive ? <Square size={16} fill="currentColor"/> : <Mic size={18}/>}
            </button>
            <button aria-label="Send message" disabled={pending || !draft.trim()}><Send size={18}/></button>
          </form>
          <div className="controls-footer"><label className="inline-check"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}/> Allow contact details I share to be stored</label><select aria-label="Conversation language" value={language} onChange={event => setLanguage(event.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="hinglish">Hinglish</option></select></div>
        </div>
      </section>

      <aside className="sidebar"><div className="section-heading"><span className="eyebrow">TOWNSHIP AT A GLANCE</span><h2>A place built around possibility.</h2></div><div className="overview-card"><div className="overview-icon"><MapPin size={19}/></div><div><strong>Connected by design</strong><p>Walk-to-work planning across residential, commercial, industrial and social spaces.</p></div></div><div className="metric-row"><div><strong>2,400<span> acres</span></strong><span>Phase 1</span></div><div><strong>11</strong><span>sectors</span></div><div><strong>600<span>+</span></strong><span>companies</span></div></div>
        <div className="project-heading"><h3>Residential projects</h3><span>01 / 02</span></div><div className="project-tabs"><button className={activeProject === 'A' ? 'selected' : ''} onClick={() => setActiveProject('A')}>Project A</button><button className={activeProject === 'B' ? 'selected' : ''} onClick={() => setActiveProject('B')}>Project B</button></div><div className="project-card"><div className="project-icon"><Building2 size={22}/></div><span className="project-tag">{activeProject === 'A' ? 'PREMIUM VILLA PLOTS' : 'INTEGRATED MIXED-USE'}</span><h3>{activeProject === 'A' ? 'Space to build your own.' : 'Everything within reach.'}</h3><p>{activeProject === 'A' ? 'A gated development with more than 100 villa plots, from 267 to 597 square yards.' : 'Residential plots alongside commercial spaces, shared amenities and planned schools.'}</p><div className="project-facts"><div><span>DEVELOPMENT</span><strong>{activeProject === 'A' ? '~25 acres' : '~138.76 acres'}</strong></div><div><span>GREEN SPACE</span><strong>{activeProject === 'A' ? '~50% open landscape' : 'More than 5 acres'}</strong></div></div><button className="text-button" onClick={() => void send(activeProject === 'A' ? 'Tell me about Project A villa plots and amenities' : 'Tell me about Project B residential and commercial plots')}>Ask about this project <ArrowRight size={16}/></button></div>
        <div className="disclaimer"><ShieldCheck size={18}/><span>Current inventory and prices need confirmation from the sales team.</span></div>
      </aside></div>
    </main>
    <footer><span>Township Advisor</span><span>Distances and figures are approximate.</span><span><AudioLines size={15}/> Voice powered by Gemini when connected</span></footer>
  </div>
}
