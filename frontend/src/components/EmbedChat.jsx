import React, { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'

const LANG_NAMES = { en: '🇬🇧', es: '🇪🇸', fr: '🇫🇷', de: '🇩🇪', pt: '🇧🇷', ar: '🇸🇦', zh: '🇨🇳', ja: '🇯🇵', ko: '🇰🇷', hi: '🇮🇳', sw: '🇰🇪', nl: '🇳🇱', it: '🇮🇹', ru: '🇷🇺' }

const ESCALATION_PHRASES = [
  'speak to a human',
  'talk to a person',
  'real person',
  'human agent',
  'customer service',
  'speak to someone',
  'escalate',
  'transfer me',
  'live agent',
  'support team',
  'talk to support',
]

function detectEscalationIntent(text) {
  const lower = text.toLowerCase().trim()
  return ESCALATION_PHRASES.some(phrase => lower.includes(phrase))
}

function getCookie(name) {
  const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return m ? m[2] : null
}
function setCookie(name, value, days) {
  const exp = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${value};expires=${exp};path=/;SameSite=None;Secure`
}
function getOrCreateVisitorId() {
  let vid = getCookie('supportbot_visitor_id')
  if (!vid) {
    vid = 'v_' + Math.random().toString(36).substring(2) + Date.now().toString(36)
    setCookie('supportbot_visitor_id', vid, 365)
  }
  return vid
}

// Per-tab session continuity. Without persistence, every page reload starts a
// new server-side Conversation and the `already_escalated` flag from the
// previous round is never observed (BUG 2 would resurface after reload). Scoped
// to sessionStorage on purpose: a new tab = a new conversation, but reloading
// the embed inside the same tab keeps the thread. Falls back to a fresh ID if
// sessionStorage is unavailable (some iframe sandboxes block it).
function getOrCreateSessionId() {
  try {
    const existing = sessionStorage.getItem('supportbot_session_id')
    if (existing) return existing
    const fresh = 'sess_' + Math.random().toString(36).substring(2)
    sessionStorage.setItem('supportbot_session_id', fresh)
    return fresh
  } catch {
    return 'sess_' + Math.random().toString(36).substring(2)
  }
}

export default function EmbedChat() {
  const { botId } = useParams()
  const [config, setConfig] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(getOrCreateSessionId)
  const [visitorId] = useState(() => getOrCreateVisitorId())
  const [isReturning, setIsReturning] = useState(false)
  const [detectedLang, setDetectedLang] = useState(null)
  const [escalated, setEscalated] = useState(false)
  const [contactFormMode, setContactFormMode] = useState(null)  // null | 'escalation_urgent' | 'escalation_soft'
  const [escalationShown, setEscalationShown] = useState(false)
  const [lastUserMessage, setLastUserMessage] = useState('')
  const [escName, setEscName] = useState('')
  const [escEmail, setEscEmail] = useState('')
  const [escPhone, setEscPhone] = useState('')
  const [escReason, setEscReason] = useState('')
  // AI-trigger-detail reason captured from the most recent chat response when
  // the server flagged needs_escalation=true (one of ai_chat.VALID_ESCALATION_REASONS:
  // explicit_request | frustration | urgency | sensitive_topic | unresolved_loop |
  // no_faq_answer). Forwarded on the escalate POST body so the backend persists
  // it on Lead.escalation_reason. Null when the visitor clicked the escalate
  // button without an AI signal (e.g. typed "speak to a human" — caught by
  // detectEscalationIntent above) — backend defaults to "customer_requested".
  const [aiEscalationReason, setAiEscalationReason] = useState(null)
  const [voiceAvailable, setVoiceAvailable] = useState(false)
  const [listening, setListening] = useState(false)
  const [inputMethod, setInputMethod] = useState('text')
  const messagesEndRef = useRef(null)
  const recognitionRef = useRef(null)
  const silenceTimerRef = useRef(null)
  // Initialised to null because `sendMessage` is declared further down — reading
  // it here would be a TDZ access (white page on /embed/:botId). The effect
  // below populates the ref after every render, so by the time `rec.onresult`
  // fires it always holds the current closure.
  const sendMessageRef = useRef(null)

  // Intentionally no dependency array: an explicit `[sendMessage]` array would
  // be constructed at this line, which is *also* a TDZ access. Running on every
  // render is fine — the body is a single ref assignment, cheap and idempotent.
  useEffect(() => { sendMessageRef.current = sendMessage })

  const browserLang = navigator.language?.split('-')[0] || 'en'

  useEffect(() => {
    fetch(`/api/config/public/${botId}`)
      .then(r => r.json())
      .then(cfg => {
        setConfig(cfg)
        document.documentElement.style.setProperty('--embed-accent', cfg.brand_color || '#6366F1')
      })
      .catch(() => {})
  }, [botId])

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SR) setVoiceAvailable(true)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (config && messages.length === 0) {
      const welcome = config.welcome_message || 'Hi! How can I help?'
      setMessages([{ role: 'assistant', content: welcome }])
    }
  }, [config])

  /*
   * PRICING KNOWLEDGE BASE REQUIREMENT
   * Bot answers pricing questions from FAQs before showing any contact form.
   * Ensure these FAQs exist in the tenant knowledge base:
   *
   * - What are your pricing plans?
   * - What is included in Starter/Growth/Pro/Agency/Enterprise?
   * - Is there a free trial?
   * - What is the setup/onboarding fee for?
   * - What happens at the message limit?
   * - Do you offer annual billing?
   * - Can I upgrade my plan?
   *
   * Without these FAQs, Claude hits needs_escalation too early.
   */
  const sendMessage = async (text, method = 'text') => {
    if (loading) return
    setLoading(true)
    const userMsg = text.trim()
    if (!userMsg) { setLoading(false); return }
    setInput('')

    if (detectEscalationIntent(userMsg) && !escalationShown) {
      setEscalationShown(true)
      setLastUserMessage(userMsg)
      setMessages(prev => [...prev, { role: 'user', content: userMsg, _id: Date.now() + Math.random() }, { role: 'assistant', content: 'Of course! Let me get someone for you right away.', _id: Date.now() + Math.random() }])
      setTimeout(() => setContactFormMode('escalation_urgent'), 200)
      setLoading(false)
      return
    }

    setLastUserMessage(userMsg)
    setMessages(prev => [...prev, { role: 'user', content: userMsg, _id: Date.now() + Math.random() }])

    try {
      const r = await fetch('/api/chat/public', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          session_id: sessionId,
          visitor_id: visitorId,
          message: userMsg,
          browser_language: browserLang,
          input_method: method,
        }),
      })
      const data = await r.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply, _id: Date.now() + Math.random() }])
      if (data.is_returning) setIsReturning(true)
      if (data.detected_language) setDetectedLang(data.detected_language)

      // BUG 2 fix: server is the source of truth for "already escalated in this
      // conversation". On reload / iframe re-mount, local React state resets to
      // false — without this sync, the form would re-pop even after the visitor
      // already submitted their details. The server suppresses needs_escalation
      // when already_escalated is true, but we also reflect it locally so the
      // keyword-trigger path (detectEscalationIntent above) stays suppressed too.
      if (data.already_escalated) {
        setEscalated(true)
        setEscalationShown(true)
        setContactFormMode(null)
      } else if (data.needs_escalation && !escalated && !escalationShown) {
        setEscalationShown(true)
        setContactFormMode('escalation_soft')
        // Capture the AI-trigger-detail reason for forwarding on the
        // escalate POST below. Server only emits this when needs_escalation
        // is true; falsy values stay null so the backend default kicks in.
        if (data.escalation_reason) {
          setAiEscalationReason(data.escalation_reason)
        }
      }

      if (window.parent !== window) {
      if (!data.was_auto_reply) {
        window.parent.postMessage('supportbot:notify', window.location.origin)
      }
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, something went wrong. Please try again.', _id: Date.now() + Math.random() }])
    } finally {
      setLoading(false)
      setInputMethod('text')
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    sendMessage(input, inputMethod)
  }

  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return

    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      clearTimeout(silenceTimerRef.current)
      if (input.trim()) sendMessage(input, 'voice')
      return
    }

    const rec = new SR()
    recognitionRef.current = rec
    rec.lang = navigator.language || 'en-US'
    rec.continuous = true
    rec.interimResults = true

    rec.onresult = (event) => {
      const transcript = Array.from(event.results).map(r => r[0].transcript).join('')
      setInput(transcript)
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = setTimeout(() => {
        rec.stop()
        setListening(false)
        if (transcript.trim()) sendMessageRef.current(transcript, 'voice')
      }, 3000)
    }

    rec.onend = () => { setListening(false); clearTimeout(silenceTimerRef.current) }
    rec.onerror = () => { setListening(false); clearTimeout(silenceTimerRef.current) }

    rec.start()
    setListening(true)
    setInputMethod('voice')
  }

  const handleEscalateSubmit = async (e) => {
    e.preventDefault()
    if (!sessionId) return
    setEscalated(true)
    setContactFormMode(null)
    try {
      const r = await fetch('/api/escalate/public', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          session_id: sessionId,
          visitor_id: visitorId,
          message: lastUserMessage,
          name: escName || null,
          email: escEmail || null,
          phone: escPhone || null,
          reason: contactFormMode || 'customer_requested',
          visitor_reason: escReason || null,
          // AI-trigger-detail reason from the chat response (when present).
          // Backend validates against VALID_ESCALATION_REASONS and falls back
          // to "customer_requested" when null/invalid — see escalate.py.
          escalation_reason: aiEscalationReason,
        }),
      })
      if (r.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: 'We\'ve notified our team. Someone will get back to you shortly.', _id: Date.now() + Math.random() }])
      }
    } catch { /* escalation queued fallback */ }
    setEscReason('')
  }

  const handleEscalateSkip = async () => {
    if (!sessionId) return
    setEscalated(true)
    setContactFormMode(null)
    try {
      const r = await fetch('/api/escalate/public', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          session_id: sessionId,
          visitor_id: visitorId,
          message: lastUserMessage,
          name: null,
          email: null,
          phone: null,
          reason: contactFormMode || 'customer_requested',
          visitor_reason: escReason || null,
          // See handleEscalateSubmit — same field, same validation contract.
          escalation_reason: aiEscalationReason,
        }),
      })
      if (!r.ok) return
    } catch { /* escalation queued fallback */ }
    setEscReason('')
  }

  if (!config) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'sans-serif', color: '#6B7280' }}>
        Loading…
      </div>
    )
  }

  const accent = config.brand_color || '#6366F1'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', background: '#F9FAFB', '--accent': accent }}>
      <div style={{ background: accent, color: '#fff', padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>🤖</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>
            {config.agent_name || 'SupportBot'}
            {isReturning && <span style={{ marginLeft: 8, fontSize: 11, background: 'rgba(255,255,255,0.2)', padding: '1px 6px', borderRadius: 8 }}>👋 Welcome back!</span>}
          </div>
          <div style={{ fontSize: 11, opacity: 0.8, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ADE80', display: 'inline-block' }} />
            Online · {config.business_name}
            {detectedLang && <span style={{ marginLeft: 4 }}>{LANG_NAMES[detectedLang] || detectedLang}</span>}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.map((msg, i) => (
          <div key={msg._id || i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '82%',
              padding: '9px 13px',
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
              background: msg.role === 'user' ? accent : '#fff',
              color: msg.role === 'user' ? '#fff' : '#1F2937',
              fontSize: 14,
              lineHeight: 1.5,
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', gap: 4, padding: '8px 14px', background: '#fff', borderRadius: '16px 16px 16px 4px', maxWidth: 60, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#9CA3AF', animation: `bounce 1s ${i * 0.15}s infinite` }} />
            ))}
          </div>
        )}

        {contactFormMode && !escalated && (
          <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 12, padding: '14px', margin: '4px 0' }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: '#C2410C' }}>
              {contactFormMode === 'escalation_urgent' ? 'Talk to a human' : 'Want to talk to our team?'}
            </div>
            <form onSubmit={handleEscalateSubmit}>
              <input value={escName} onChange={e => setEscName(e.target.value)} placeholder="Your name" style={{ width: '100%', marginBottom: 6, padding: '7px 10px', border: '1px solid #FED7AA', borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }} />
              <input value={escEmail} onChange={e => setEscEmail(e.target.value)} placeholder="your@email.com" type="email" required style={{ width: '100%', marginBottom: 6, padding: '7px 10px', border: '1px solid #FED7AA', borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }} />
              <input value={escPhone} onChange={e => setEscPhone(e.target.value)} placeholder="Phone (optional)" type="tel" style={{ width: '100%', marginBottom: 6, padding: '7px 10px', border: '1px solid #FED7AA', borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }} />
              <textarea value={escReason} onChange={e => setEscReason(e.target.value)} placeholder="What do you need help with?" rows={2} style={{ width: '100%', marginBottom: 8, padding: '7px 10px', border: '1px solid #FED7AA', borderRadius: 6, fontSize: 13, boxSizing: 'border-box', resize: 'none' }} />
              <div style={{ display: 'flex', gap: 6 }}>
                <button type="submit" style={{ flex: 1, background: accent, color: '#fff', border: 'none', padding: '7px 0', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>Send</button>
                <button type="button" onClick={handleEscalateSkip} style={{ background: 'transparent', color: '#6B7280', border: '1px solid #D1D5DB', padding: '7px 0', borderRadius: 6, cursor: 'pointer', fontSize: 13, flex: 1 }}>Skip</button>
              </div>
            </form>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} style={{ padding: '10px 12px', background: '#fff', borderTop: '1px solid #E5E7EB', display: 'flex', gap: 8, flexShrink: 0 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={listening ? '🎤 Listening… (click mic or wait 3s)' : 'Type a message…'}
          style={{ flex: 1, border: '1px solid #E5E7EB', borderRadius: 20, padding: '8px 14px', fontSize: 14, outline: 'none', background: '#F9FAFB' }}
          disabled={loading}
        />
        {config.voice_enabled && voiceAvailable && (
          <button type="button" onClick={toggleVoice} style={{ width: 38, height: 38, borderRadius: '50%', border: 'none', background: listening ? '#EF4444' : '#F3F4F6', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>
            {listening ? '⏹' : '🎤'}
          </button>
        )}
        <button type="submit" disabled={loading || !input.trim()} style={{ width: 38, height: 38, borderRadius: '50%', border: 'none', background: (loading || !input.trim()) ? '#E5E7EB' : accent, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill={loading || !input.trim() ? '#9CA3AF' : '#fff'}><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </form>

      <div style={{ textAlign: 'center', padding: '4px 0 6px', background: '#fff', fontSize: 10, color: '#9CA3AF', borderTop: '1px solid #F3F4F6', flexShrink: 0 }}>
        Powered by <strong>SupportBot</strong>
      </div>

      <style>{`
        @keyframes bounce { 0%, 100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
      `}</style>
    </div>
  )
}
