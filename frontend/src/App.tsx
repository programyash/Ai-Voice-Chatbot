import { useEffect, useRef, useState } from 'react'
import { ArrowRight, AudioLines, Building2, Check, ChevronRight, CircleHelp, MapPin, Menu, MessageSquare, Mic, Send, ShieldCheck, Square, X } from 'lucide-react'
import { request, type Health, type Message } from './api'
import { useVoice } from './useVoice'

const examples = [
  'Tell me about the villa plots',
  'How far is IGI Airport?',
  'Compare Project A and Project B',
  'Are the schools in Project B already open?',
]

type InquiryKind = 'lead' | 'visit' | 'callback'

function Inquiry({ close }: { close: () => void }) {
  const [kind, setKind] = useState<InquiryKind>('lead')
  const [form, setForm] = useState({ name: '', mobile: '', email: '', project: '', interest: '', budget: '', contact_time: '', requirements: '', preferred_date: '', preferred_time: '', note: '', consent: false })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  const update = (key: keyof typeof form, value: string | boolean) => setForm(previous => ({ ...previous, [key]: value }))
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(''); setBusy(true)
    try {
      const endpoint = kind === 'lead' ? '/api/leads' : kind === 'visit' ? '/api/visits' : '/api/callbacks'
      const data = await request<{ status: string }>(endpoint, { method: 'POST', body: JSON.stringify(form) })
      setResult(kind === 'visit' ? 'Your visit request is pending confirmation. A team member needs to confirm it.' : kind === 'callback' ? 'Your callback request has been recorded. No callback time is confirmed yet.' : `Your inquiry has been ${data.status}.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not submit. Please retry.') }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) close() }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="inquiry-title">
      <button className="icon-button close" aria-label="Close inquiry" onClick={close}><X size={20}/></button>
      <div className="eyebrow">PERSONAL ASSISTANCE</div><h2 id="inquiry-title">Let us follow up</h2>
      <p className="muted">Share only what you are comfortable with. Your request will be stored for a human team member.</p>
      {result ? <div className="success-panel"><Check size={22}/><p>{result}</p><button className="text-button" onClick={close}>Done <ArrowRight size={16}/></button></div> : <form onSubmit={submit}>
        <div className="segmented" role="group" aria-label="Inquiry type">
          {(['lead','visit','callback'] as const).map(item => <button type="button" className={kind === item ? 'selected' : ''} key={item} onClick={() => setKind(item)}>{item === 'lead' ? 'Inquiry' : item === 'visit' ? 'Site visit' : 'Callback'}</button>)}
        </div>
        <div className="form-grid">
          <label>Full name<input required value={form.name} onChange={event => update('name', event.target.value)} autoComplete="name"/></label>
          <label>Mobile<input value={form.mobile} onChange={event => update('mobile', event.target.value)} autoComplete="tel" placeholder="or provide email"/></label>
          <label>Email<input type="email" value={form.email} onChange={event => update('email', event.target.value)} autoComplete="email" placeholder="or provide mobile"/></label>
          {kind !== 'callback' && <label>Project<select value={form.project} onChange={event => update('project', event.target.value)}><option value="">No preference</option><option value="A">Project A · Villa plots</option><option value="B">Project B · Mixed-use</option></select></label>}
          {kind === 'lead' && <><label>Interest<input value={form.interest} onChange={event => update('interest', event.target.value)} placeholder="e.g. residential plot"/></label><label>Budget (optional)<input value={form.budget} onChange={event => update('budget', event.target.value)}/></label><label className="wide">Requirements<textarea value={form.requirements} onChange={event => update('requirements', event.target.value)} rows={2}/></label></>}
          {kind === 'visit' && <><label>Preferred date<input required type="date" value={form.preferred_date} onChange={event => update('preferred_date', event.target.value)} min={new Date().toISOString().slice(0,10)}/></label><label>Preferred time<input type="time" value={form.preferred_time} onChange={event => update('preferred_time', event.target.value)}/></label></>}
          {kind === 'callback' && <label className="wide">What would you like help with?<textarea value={form.note} onChange={event => update('note', event.target.value)} rows={2}/></label>}
        </div>
        <label className="check-row"><input required type="checkbox" checked={form.consent} onChange={event => update('consent', event.target.checked)}/><span>I agree to store these details so the team can contact me about this request.</span></label>
        {error && <p className="error-text" role="alert">{error}</p>}
        <button className="primary-button submit" disabled={busy}>{busy ? 'Submitting…' : 'Submit request'} <ArrowRight size={17}/></button>
      </form>}
    </section>
  </div>
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [language, setLanguage] = useState('en')
  const [consent, setConsent] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [inquiry, setInquiry] = useState(false)
  const [activeProject, setActiveProject] = useState<'A' | 'B'>('A')
  const [mobileMenu, setMobileMenu] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const voice = useVoice((role, text) => setMessages(previous => [...previous, { role, body: text }]), setConversationId)

  useEffect(() => { request<Health>('/api/health').then(setHealth).catch(() => setHealth(null)) }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, pending])

  const send = async (text = draft) => {
    const trimmed = text.trim()
    if (!trimmed || pending) return
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
    <header className="topbar"><div className="brand"><span className="brand-mark"><Building2 size={21} strokeWidth={1.9}/></span><span>Township <strong>Advisor</strong></span></div>
      <nav className={mobileMenu ? 'top-nav open' : 'top-nav'} aria-label="Primary"><a href="#explore" onClick={() => setMobileMenu(false)}>Explore</a><a href="#assistant" onClick={() => setMobileMenu(false)}>Assistant</a><button onClick={() => { setInquiry(true); setMobileMenu(false) }}>Request a call <ArrowRight size={15}/></button></nav>
      <button className="icon-button menu-toggle" aria-label="Open menu" onClick={() => setMobileMenu(!mobileMenu)}><Menu size={22}/></button>
    </header>

    <main>
      <section className="intro"><div><div className="eyebrow"><span className="eyebrow-line"/>A MORE INFORMED WAY TO EXPLORE</div><h1>Find your place in<br/><em>the township.</em></h1><p>Ask about residential plots, facilities, connectivity, and what makes each project distinct. Speak naturally or start with a message.</p></div><div className="intro-stat"><span className="stat-number">8,250<span> acres</span></span><span className="stat-caption">INTEGRATED TOWNSHIP · APPROXIMATE</span><div className="stat-divider"/><span className="stat-number small">02<span> projects</span></span><span className="stat-caption">ONE CONNECTED COMMUNITY</span></div></section>

      <div className="content-grid"><section className="assistant-card" id="assistant" aria-label="Voice assistant">
        <div className="assistant-header"><div><div className="eyebrow">YOUR PERSONAL GUIDE</div><h2>Ask anything about the township.</h2></div><div className={`connection ${voiceActive ? 'connected' : ''}`}><span className="status-dot"/>{status}</div></div>
        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? <div className="empty-state"><span className="empty-icon"><MessageSquare size={26} strokeWidth={1.5}/></span><h3>Where would you like to begin?</h3><p>I'm here to help you understand the projects and the community around them.</p><div className="question-list">{examples.map(question => <button key={question} onClick={() => void send(question)}>{question}<ChevronRight size={16}/></button>)}</div></div> : <div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${index}-${message.role}`}><span className="message-label">{message.role === 'assistant' ? 'ADVISOR' : 'YOU'}</span><p>{message.body}</p></div>)}{pending && <div className="thinking"><span/><span/><span/> Thinking</div>}<div ref={bottom}/></div>}
        </div>
        <div className="assistant-controls"><div className="voice-controls"><button className={`mic-button ${voiceActive ? 'active' : ''}`} aria-label={voiceActive ? 'Stop voice conversation' : 'Start voice conversation'} onClick={() => voiceActive ? voice.stop() : void voice.start(language, consent)} disabled={!health?.voice_available}>{voiceActive ? <Square size={20} fill="currentColor"/> : <Mic size={25}/>}</button><div><strong>{voiceActive ? voice.state === 'connecting' ? 'Connecting…' : voice.state === 'speaking' ? 'Advisor is speaking' : voice.state === 'interrupted' ? 'Interrupted' : 'Listening to you' : 'Talk with your advisor'}</strong><span>{voiceActive ? 'Tap to end conversation' : 'Tap the microphone to begin'}</span></div><div className="audio-meter" aria-label="Audio activity"><i style={{ height: `${7 + voice.level * 18}px` }}/><i style={{ height: `${10 + voice.level * 29}px` }}/><i style={{ height: `${6 + voice.level * 22}px` }}/><i style={{ height: `${9 + voice.level * 25}px` }}/></div></div>
          {(voice.error || error) && <div className="error-banner" role="alert"><CircleHelp size={17}/>{voice.error || error}</div>}
          <form className="composer" onSubmit={event => { event.preventDefault(); void send() }}><input aria-label="Message" value={draft} onChange={event => setDraft(event.target.value)} placeholder="Or type a question here…" maxLength={4000}/><button aria-label="Send message" disabled={pending || !draft.trim()}><Send size={18}/></button></form>
          <div className="controls-footer"><label className="inline-check"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}/> Allow contact details I share to be stored</label><select aria-label="Conversation language" value={language} onChange={event => setLanguage(event.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="hinglish">Hinglish</option></select></div>
        </div>
      </section>

      <aside className="sidebar" id="explore"><div className="section-heading"><span className="eyebrow">EXPLORE THE TOWNSHIP</span><h2>A place built around possibility.</h2></div><div className="overview-card"><div className="overview-icon"><MapPin size={19}/></div><div><strong>Connected by design</strong><p>Walk-to-work planning across residential, commercial, industrial and social spaces.</p></div></div><div className="metric-row"><div><strong>2,400<span> acres</span></strong><span>Phase 1</span></div><div><strong>11</strong><span>sectors</span></div><div><strong>600<span>+</span></strong><span>companies</span></div></div>
        <div className="project-heading"><h3>Residential projects</h3><span>01 / 02</span></div><div className="project-tabs"><button className={activeProject === 'A' ? 'selected' : ''} onClick={() => setActiveProject('A')}>Project A</button><button className={activeProject === 'B' ? 'selected' : ''} onClick={() => setActiveProject('B')}>Project B</button></div><div className="project-card"><div className="project-icon"><Building2 size={22}/></div><span className="project-tag">{activeProject === 'A' ? 'PREMIUM VILLA PLOTS' : 'INTEGRATED MIXED-USE'}</span><h3>{activeProject === 'A' ? 'Space to build your own.' : 'Everything within reach.'}</h3><p>{activeProject === 'A' ? 'A gated development with more than 100 villa plots, from 267 to 597 square yards.' : 'Residential plots alongside commercial spaces, shared amenities and planned schools.'}</p><div className="project-facts"><div><span>DEVELOPMENT</span><strong>{activeProject === 'A' ? '~25 acres' : '~138.76 acres'}</strong></div><div><span>GREEN SPACE</span><strong>{activeProject === 'A' ? '~50% open landscape' : 'More than 5 acres'}</strong></div></div><button className="text-button" onClick={() => void send(activeProject === 'A' ? 'Tell me about Project A villa plots and amenities' : 'Tell me about Project B residential and commercial plots')}>Ask about this project <ArrowRight size={16}/></button></div>
        <div className="disclaimer"><ShieldCheck size={18}/><span>Answers use the supplied assignment facts. Current inventory and prices need confirmation from the sales team.</span></div>
      </aside></div>
      <section className="footer-cta"><div><div className="eyebrow">READY TO TAKE THE NEXT STEP?</div><h2>Continue the conversation.</h2><p>Share your requirements or request a site visit. Visits are confirmed by a human team member.</p></div><button className="primary-button" onClick={() => setInquiry(true)}>Make an inquiry <ArrowRight size={17}/></button></section>
    </main>
    <footer><span>Township Advisor</span><span>Information is approximate and based on the supplied assignment.</span><span><AudioLines size={15}/> Voice powered by Gemini when connected</span></footer>
    {inquiry && <Inquiry close={() => setInquiry(false)}/>}
  </div>
}
