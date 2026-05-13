/**
 * EmbedChat — Renders inside the widget.js iframe.
 * Route: /embed/:botId
 * Uses public endpoints: /api/config/public/:botId and /api/chat/public
 * No authentication required.
 */
import React, { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'

const LANG_NAMES = { en: '🇬🇧', es: '🇪🇸', fr: '🇫🇷', de: '🇩🇪', pt: '🇧🇷', ar: '🇸🇦', zh: '🇨🇳', ja: '🇯🇵', ko: '🇰🇷', hi: '🇮🇳', sw: '🇰🇪', nl: '🇳🇱', it: '🇮🇹', ru: '🇷🇺' }

// Must match ChatWidget.jsx exactly
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
];

function detectEscalationIntent(text) {
  const lower = text.toLowerCase().trim();
  return ESCALATION_PHRASES.some(phrase =>
    lower.includes(phrase)
  );
}

// Cookie helpers
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

export default function EmbedChat() {
  const { botId } = useParams()
  const [config, setConfig] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(() => 'sess_' + Math.random().toString(36).substring(2))
  const [visitorId] = useState(() => getOrCreateVisitorId())
  const [isReturning, setIsReturning] = useState(false)
  const [detectedLang, setDetectedLang] = useState(null)
  const [salesAction, setSalesAction] = useState(null)
  const [leadEmail, setLeadEmail] = useState('')
  const [leadCapturing, setLeadCapturing] = useState(false)
  const [escalated, setEscalated] = useState(false)
  const [escalateFormShown, setEscalateFormShown] = useState(false)
  const [showEscalateForm, setShowEscalateForm] = useState(false)
  const [escalationShown, setEscalationShown] = useState(false)
  const [lastUserMessage, setLastUserMessage] = useState('')
  const [escName, setEscName] = useState('')
  const [escEmail, setEscEmail] = useState('')
  const [escPhone, setEscPhone] = useState('')
  const [escReason, setEscReason] = useState('')
  const [voiceAvailable, setVoiceAvailable] = useState(false)
  const [listening, setListening] = useState(false)
  const [inputMethod, setInputMethod] = useState('text')
  const messagesEndRef = useRef(null)
  const recognitionRef = useRef(null)
  const silenceTimerRef = useRef(null)

  const browserLang = navigator.language?.split('-')[0] || 'en'

  // Load public config
  useEffect(() => {
    fetch(`/api/config/public/${botId}`)
      .then(r => r.json())
      .then(cfg => {
        setConfig(cfg)
        // Apply brand color to iframe body
        document.documentElement.style.setProperty('--embed-accent', cfg.brand_color || '#6366F1')
      })
      .catch(() => {})
  }, [botId])

  // Voice setup
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SR) setVoiceAvailable(true)
  }, [])

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Send welcome message after config loads
  useEffect(() => {
    if (config && messages.length === 0) {
      const welcome = config.welcome_message || 'Hi! How can I help?'
      setMessages([{ role: 'assistant', content: welcome }])
    }
  }, [config])

  const sendMessage = async (text, method = 'text') => {
    if (!text.trim() || loading) return
    const userMsg = text.trim()
    setInput('')

    // Phrase detection — show escalation form immediately, skip chat endpoint
    if (detectEscalationIntent(userMsg) && !escalationShown) {
      setEscalationShown(true)
      setLastUserMessage(userMsg)
      setMessages(prev => [...prev, { role: 'user', content: userMsg }, { role: 'assistant', content: 'Of course! Let me get someone for you right away.' }])
      setTimeout(() => setShowEscalateForm(true), 200)
      return
    }

    setLastUserMessage(userMsg)
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)
    setSalesAction(null)

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
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
      if (data.is_returning) setIsReturning(true)
      if (data.detected_language) setDetectedLang(data.detected_language)
      if (data.sales_action) setSalesAction(data.sales_action)

      if (data.needs_escalation && !escalated && !escalateFormShown && !escalationShown) {
        setEscalationShown(true)
        setEscalateFormShown(true)
        setTimeout(() => setShowEscalateForm(true), 800)
      }

      // Notify parent to show badge if widget is closed
      if (window.parent !== window) {
        window.parent.postMessage('supportbot:notify', '*')
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' }])
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
        if (transcript.trim()) sendMessage(transcript, 'voice')
      }, 3000)
    }

    rec.onend = () => { setListening(false); clearTimeout(silenceTimerRef.current) }
    rec.onerror = () => { setListening(false); clearTimeout(silenceTimerRef.current) }

    rec.start()
    setListening(true)
    setInputMethod('voice')
  }

  const captureLeadSubmit = async (e) => {
    e.preventDefault()
    if (!leadEmail.trim()) return
    setLeadCapturing(true)
    try {
      await fetch('/api/sales/leads/capture/public', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          email: leadEmail,
          source: 'chat_capture',
          buying_signal_score: 4,
          visitor_id: visitorId,
        }),
      })
      setSalesAction(null)
      setMessages(prev => [...prev, { role: 'assistant', content: `Thanks! We'll reach out to ${leadEmail} shortly.` }])
    } catch { /* silently fail */ }
    finally { setLeadCapturing(false) }
  }

  const handleEscalateSubmit = async (e) => {
    e.preventDefault()
    setEscalated(true)
    setShowEscalateForm(false)
    try {
      await fetch('/api/escalate/public', {
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
          reason: 'customer_requested',
        }),
      })
    } catch { /* escalation queued fallback */ }
    setMessages(prev => [...prev, { role: 'assistant', content: 'We\'ve notified our team. Someone will get back to you shortly.' }])
  }

  const handleEscalateSkip = async () => {
    setEscalated(true)
    setShowEscalateForm(false)
    try {
      await fetch('/api/escalate/public', {
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
          reason: 'customer_requested',
        }),
      })
    } catch { /* escalation queued fallback */ }
  }

  if (!config) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'sans-serif', color: '#6B7280' }}>
        Loading…
      </div>
    )
  }

  const accent = config.brand_color || '#6366F1'
  const safeBookingUrl = salesAction?.booking_url &&
    (salesAction.booking_url.startsWith('https://') ||
     salesAction.booking_url.startsWith('http://'))
    ? salesAction.booking_url
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', background: '#F9FAFB', '--accent': accent }}>
      {/* Header */}
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

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
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

        {showEscalateForm && !escalated && (
          <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 12, padding: '14px', margin: '4px 0' }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: '#C2410C' }}>Talk to a human</div>
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

        {!escalated && !showEscalateForm && !escalationShown && messages.length >= 2 && (
          <div style={{ textAlign: 'center', margin: '6px 0' }}>
            <button onClick={() => { setEscalationShown(true); setShowEscalateForm(true); }} style={{ background: 'transparent', border: '1px solid #D1D5DB', borderRadius: 16, padding: '5px 14px', cursor: 'pointer', fontSize: 12, color: '#6B7280', transition: 'all 0.2s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = accent}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#D1D5DB'}
            >Request human support</button>
          </div>
        )}

        {/* Sales Action Cards */}
        {salesAction && (
          <div style={{ margin: '4px 0' }}>
            {salesAction.type === 'discount' && (
              <div style={{ background: '#FEF9C3', border: '1px solid #FDE047', borderRadius: 12, padding: '12px 14px', fontSize: 13 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>🎁 {salesAction.message}</div>
                <code style={{ background: '#fff', padding: '2px 8px', borderRadius: 4, border: '1px solid #FDE047', fontSize: 14, fontWeight: 700 }}>{salesAction.code}</code>
              </div>
            )}
            {salesAction.type === 'demo' && (
              <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 12, padding: '12px 14px', fontSize: 13 }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>📅 {salesAction.message}</div>
                {safeBookingUrl && (
                  <a href={safeBookingUrl} target="_blank" rel="noopener noreferrer" style={{ display: 'inline-block', background: accent, color: '#fff', padding: '6px 14px', borderRadius: 8, textDecoration: 'none', fontSize: 13, fontWeight: 600 }}>Book Demo →</a>
                )}
              </div>
            )}
            {salesAction.type === 'capture_lead' && (
              <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 12, padding: '12px 14px', fontSize: 13 }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>✉️ {salesAction.message}</div>
                <form onSubmit={captureLeadSubmit} style={{ display: 'flex', gap: 6 }}>
                  <input type="email" placeholder="your@email.com" value={leadEmail} onChange={e => setLeadEmail(e.target.value)} required style={{ flex: 1, padding: '6px 10px', border: '1px solid #BBF7D0', borderRadius: 6, fontSize: 13 }} />
                  <button type="submit" disabled={leadCapturing} style={{ background: accent, color: '#fff', border: 'none', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>
                    {leadCapturing ? '…' : 'Send'}
                  </button>
                </form>
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
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

      {/* Powered by footer */}
      <div style={{ textAlign: 'center', padding: '4px 0 6px', background: '#fff', fontSize: 10, color: '#9CA3AF', borderTop: '1px solid #F3F4F6', flexShrink: 0 }}>
        Powered by <strong>SupportBot</strong>
      </div>

      <style>{`
        @keyframes bounce { 0%, 100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
      `}</style>
    </div>
  )
}
