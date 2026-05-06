import React, { useState, useEffect, useRef, useContext } from 'react'
import { ToastContext } from '../App.jsx'

// ── Phase 1: visitor cookie helpers ─────────────────────────────────────────
function getOrCreateVisitorId() {
  const key = 'supportbot_visitor_id'
  let id = null
  try {
    const match = document.cookie.match(new RegExp(`(?:^|; )${key}=([^;]*)`))
    id = match ? decodeURIComponent(match[1]) : null
    if (!id) {
      id = crypto.randomUUID()
      const exp = new Date(Date.now() + 365 * 24 * 3600 * 1000).toUTCString()
      document.cookie = `${key}=${encodeURIComponent(id)}; expires=${exp}; path=/; SameSite=Lax`
    }
  } catch {
    id = Math.random().toString(36).slice(2)
  }
  return id
}

// ── Phase 3: Sales Action Cards ───────────────────────────────────────────────
function DiscountCard({ action, accent }) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={{
      background: 'linear-gradient(135deg, #FFFBEB, #FEF3C7)',
      border: '1px solid #FCD34D',
      borderRadius: 10, padding: '12px 14px', margin: '4px 0',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#92400E', marginBottom: 6 }}>
        🏷️ {action.message}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <code style={{
          background: '#FEF3C7', border: '1px dashed #F59E0B', padding: '4px 10px',
          borderRadius: 6, fontWeight: 700, fontSize: 15, color: '#78350F', letterSpacing: 1,
        }}>{action.code}</code>
        <button
          onClick={() => { navigator.clipboard?.writeText(action.code); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
          style={{
            background: accent, color: '#fff', border: 'none', borderRadius: 6,
            padding: '4px 10px', fontSize: 12, cursor: 'pointer', fontWeight: 500,
          }}
        >
          {copied ? '✓ Copied!' : 'Copy'}
        </button>
      </div>
    </div>
  )
}

// Validate that an external URL is http(s) before rendering as <a href>.
// Anything else (javascript:, data:, file:, etc.) returns null so the
// caller drops the link silently — audit explicitly says no visible
// error. The booking_url is tenant-controlled (set in SalesConfig), so
// it crosses a trust boundary into customer browsers.
function safeHttpUrl(raw) {
  if (!raw || typeof raw !== 'string') return null
  try {
    const u = new URL(raw)
    return (u.protocol === 'http:' || u.protocol === 'https:') ? raw : null
  } catch {
    return null
  }
}

function DemoCard({ action, accent }) {
  const safeUrl = safeHttpUrl(action.booking_url)
  return (
    <div style={{
      background: 'linear-gradient(135deg, #EFF6FF, #DBEAFE)',
      border: '1px solid #93C5FD', borderRadius: 10, padding: '12px 14px', margin: '4px 0',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#1E40AF', marginBottom: 8 }}>
        📅 {action.message}
      </div>
      {safeUrl && (
        <a href={safeUrl} target="_blank" rel="noopener noreferrer"
          style={{
            display: 'inline-block', background: accent, color: '#fff', border: 'none',
            borderRadius: 6, padding: '6px 14px', fontSize: 13, cursor: 'pointer',
            fontWeight: 500, textDecoration: 'none',
          }}
        >
          Book a Demo →
        </a>
      )}
    </div>
  )
}

function LeadCaptureCard({ onCapture, accent }) {
  const [email, setEmail] = useState('')
  const [done, setDone] = useState(false)
  const handleSubmit = () => {
    if (!email.trim()) return
    onCapture(email)
    setDone(true)
  }
  if (done) return (
    <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 10, padding: '10px 14px', margin: '4px 0', fontSize: 13, color: '#15803D' }}>
      ✅ Got it! We'll send you more info.
    </div>
  )
  return (
    <div style={{
      background: 'linear-gradient(135deg, #F5F3FF, #EDE9FE)',
      border: '1px solid #C4B5FD', borderRadius: 10, padding: '12px 14px', margin: '4px 0',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#4C1D95', marginBottom: 8 }}>
        📧 Want a detailed comparison? Enter your email:
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          className="input"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={{ flex: 1, fontSize: 13 }}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        />
        <button
          onClick={handleSubmit}
          style={{
            background: accent, color: '#fff', border: 'none', borderRadius: 6,
            padding: '6px 12px', fontSize: 13, cursor: 'pointer', fontWeight: 500,
          }}
        >Send</button>
      </div>
    </div>
  )
}

// ── Language display names ────────────────────────────────────────────────────
const LANG_NAMES = {
  en: '🇬🇧 EN', fr: '🇫🇷 FR', es: '🇪🇸 ES', de: '🇩🇪 DE',
  pt: '🇧🇷 PT', it: '🇮🇹 IT', nl: '🇳🇱 NL', ar: '🇸🇦 AR',
  zh: '🇨🇳 ZH', ja: '🇯🇵 JA', ko: '🇰🇷 KO', hi: '🇮🇳 HI',
  sw: '🌍 SW', yo: '🌍 YO', pcm: '🇳🇬 PCM', ha: '🇳🇬 HA', ig: '🇳🇬 IG',
}

export default function ChatWidget({ config, botId }) {
  const addToast = useContext(ToastContext)

  // Core state
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showEscalate, setShowEscalate] = useState(false)
  const [escalateEmail, setEscalateEmail] = useState('')
  const [escalated, setEscalated] = useState(false)
  const [showRating, setShowRating] = useState(false)
  const [rated, setRated] = useState(false)

  // Phase 1: visitor memory
  const [visitorId] = useState(() => getOrCreateVisitorId())
  const [isReturning, setIsReturning] = useState(false)

  // Phase 2: language
  const [detectedLang, setDetectedLang] = useState(null)
  const browserLang = navigator.language?.split('-')[0] || 'en'

  // Phase 3: sales
  const [salesAction, setSalesAction] = useState(null)
  const [showProactive, setShowProactive] = useState(false)
  const [showExitIntent, setShowExitIntent] = useState(false)
  const [exitEmail, setExitEmail] = useState('')
  const [salesConfig, setSalesConfig] = useState(null)

  // Phase 4: voice
  const [isListening, setIsListening] = useState(false)
  const [voiceSupported, setVoiceSupported] = useState(false)
  const recognitionRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const inputMethodRef = useRef('text')

  const bottomRef = useRef()
  const accent = config?.brand_color || '#6366F1'
  const agentName = config?.agent_name || 'SupportBot'
  const welcomeMsg = config?.welcome_message || 'Hi! How can I help you today?'
  const voiceEnabled = config?.voice_enabled !== false

  // Load sales config
  useEffect(() => {
    fetch('/api/sales/config', { credentials: 'include' }).then(r => r.json()).then(setSalesConfig).catch(() => {})
  }, [])

  // Init welcome message
  useEffect(() => {
    setMessages([{ role: 'assistant', content: welcomeMsg, auto: false }])
  }, [welcomeMsg])

  // Scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Show rating after 4+ user messages
  useEffect(() => {
    const userMsgs = messages.filter(m => m.role === 'user').length
    if (userMsgs >= 4 && !rated) setShowRating(true)
  }, [messages, rated])

  // Phase 3: proactive popup
  useEffect(() => {
    if (!salesConfig?.enabled || !salesConfig?.greeting_delay_seconds) return
    const t = setTimeout(() => {
      if (messages.filter(m => m.role === 'user').length === 0) {
        setShowProactive(true)
      }
    }, (salesConfig.greeting_delay_seconds || 30) * 1000)
    return () => clearTimeout(t)
  }, [salesConfig])

  // Phase 3: exit intent
  useEffect(() => {
    if (!salesConfig?.exit_intent_enabled) return
    const handleMouseLeave = (e) => {
      if (e.clientY <= 0 && !showExitIntent && messages.filter(m => m.role === 'user').length > 0) {
        setShowExitIntent(true)
      }
    }
    document.addEventListener('mouseleave', handleMouseLeave)
    return () => document.removeEventListener('mouseleave', handleMouseLeave)
  }, [salesConfig, showExitIntent, messages])

  // Phase 4: Speech Recognition setup
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      setVoiceSupported(true)
      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.maxAlternatives = 1
      recognition.lang = navigator.language || 'en-US'

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(result => result[0].transcript)
          .join('')
        setInput(transcript)

        // Reset silence timer on every new word
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = setTimeout(() => {
          // 3 seconds of silence → auto stop and send
          recognition.stop()
          setIsListening(false)
          if (transcript.trim()) {
            inputMethodRef.current = 'voice'
            sendMessageWithText(transcript)
          }
        }, 3000)
      }

      recognition.onerror = (event) => {
        if (event.error !== 'no-speech') {
          console.error('Speech error:', event.error)
        }
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
        clearTimeout(silenceTimerRef.current)
      }

      recognitionRef.current = recognition
    }

    return () => clearTimeout(silenceTimerRef.current)
  }, [])

  // Phase 4: Toggle voice listening
  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      clearTimeout(silenceTimerRef.current)
      setIsListening(false)
      if (input.trim()) {
        inputMethodRef.current = 'voice'
        sendMessageWithText(input)
      }
    } else {
      setInput('')
      recognitionRef.current?.start()
      setIsListening(true)
    }
  }

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessageWithText = async (text) => {
    const userMsg = text.trim()
    if (!userMsg || loading) return
    setInput('')
    const method = inputMethodRef.current
    inputMethodRef.current = 'text'

    setMessages(prev => [...prev, {
      role: 'user', content: userMsg,
      voice: method === 'voice',
    }])
    setSalesAction(null)
    setShowProactive(false)
    setLoading(true)

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          visitor_id: visitorId,
          message: userMsg,
          browser_language: browserLang,
          input_method: method,
        }),
      })
      const data = await r.json()
      if (!sessionId) setSessionId(data.session_id)

      // Phase 1: memory
      if (data.is_returning && !isReturning) setIsReturning(true)
      // Phase 2: language
      if (data.detected_language) setDetectedLang(data.detected_language)
      // Phase 3: sales
      if (data.sales_action) setSalesAction(data.sales_action)

      setMessages(prev => [...prev, {
        role: 'assistant', content: data.reply, auto: data.was_auto_reply,
      }])

      if (data.needs_escalation) setTimeout(() => setShowEscalate(true), 800)
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant', content: 'Sorry, something went wrong. Please try again.', auto: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = () => sendMessageWithText(input)

  // ── Escalation ────────────────────────────────────────────────────────────
  const handleEscalate = async () => {
    if (!sessionId) return
    try {
      await fetch('/api/escalate', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, customer_email: escalateEmail }),
      })
      setEscalated(true)
      setShowEscalate(false)
      addToast('Escalation sent — a human will reach out soon!', 'success')
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `I've escalated your request to our team. ${escalateEmail ? `We'll reach you at ${escalateEmail}.` : 'Someone will be in touch soon.'}`,
        auto: false,
      }])
    } catch {
      addToast('Failed to escalate', 'error')
    }
  }

  // ── Rating ────────────────────────────────────────────────────────────────
  const rateConversation = async (rating) => {
    if (!sessionId || !botId) return
    try {
      await fetch('/api/chat/rate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ bot_id: botId, session_id: sessionId, rating }),
      })
      setRated(true)
      setShowRating(false)
      addToast('Thanks for your feedback!', 'success')
    } catch {}
  }

  // ── Lead capture ──────────────────────────────────────────────────────────
  const captureLeadFromAction = async (email) => {
    try {
      await fetch('/api/sales/leads/capture', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email, source: 'chat_capture', buying_signal_score: 4,
          visitor_id: visitorId, conversation_id: null,
          interest: messages.filter(m => m.role === 'user').slice(-1)[0]?.content || '',
        }),
      })
    } catch {}
  }

  const handleExitCapture = async () => {
    if (exitEmail.trim()) {
      await captureLeadFromAction(exitEmail)
      addToast('Thanks! Check your email soon.', 'success')
    }
    setShowExitIntent(false)
  }

  // ── Reset ─────────────────────────────────────────────────────────────────
  const resetChat = () => {
    setMessages([{ role: 'assistant', content: welcomeMsg, auto: false }])
    setSessionId(null)
    setEscalated(false)
    setShowEscalate(false)
    setRated(false)
    setShowRating(false)
    setSalesAction(null)
    setDetectedLang(null)
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
      {/* Phase 3: Exit Intent Overlay */}
      {showExitIntent && salesConfig && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, padding: 32, maxWidth: 400, width: '90%',
            textAlign: 'center', boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🛑</div>
            <h2 style={{ fontWeight: 700, marginBottom: 8 }}>{salesConfig.exit_intent_message}</h2>
            {salesConfig.discount_code && (
              <div style={{ marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
                Use code <strong style={{ color: accent }}>{salesConfig.discount_code}</strong> at checkout
              </div>
            )}
            <input
              className="input"
              type="email"
              placeholder="Enter your email for the discount"
              value={exitEmail}
              onChange={e => setExitEmail(e.target.value)}
              style={{ marginBottom: 12 }}
            />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button
                className="btn btn-primary"
                onClick={handleExitCapture}
                style={{ background: accent }}
              >Claim Offer</button>
              <button
                className="btn btn-secondary"
                onClick={() => setShowExitIntent(false)}
              >No thanks</button>
            </div>
          </div>
        </div>
      )}

      {/* Chat Window */}
      <div style={{ flex: 1, maxWidth: 480 }}>
        {/* Phase 3: Proactive popup */}
        {showProactive && salesConfig && (
          <div style={{
            background: '#fff', border: `2px solid ${accent}`, borderRadius: 12, padding: '12px 16px',
            marginBottom: 8, display: 'flex', gap: 12, alignItems: 'flex-start',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)', animation: 'slideUp 0.3s ease',
          }}>
            <div style={{ fontSize: 24 }}>💬</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{salesConfig.greeting_message}</div>
              <button
                className="btn btn-primary"
                style={{ background: accent, fontSize: 12, padding: '4px 12px' }}
                onClick={() => { setShowProactive(false); sendMessageWithText('Hi, I need help') }}
              >Start chatting</button>
            </div>
            <button onClick={() => setShowProactive(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>×</button>
          </div>
        )}

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {/* Chat Header */}
          <div style={{
            background: accent, color: '#fff', padding: '14px 18px',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'rgba(255,255,255,0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
            }}>🤖</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
                {agentName}
                {/* Phase 1: Welcome back badge */}
                {isReturning && (
                  <span style={{ fontSize: 11, background: 'rgba(255,255,255,0.25)', padding: '2px 8px', borderRadius: 999, fontWeight: 400 }}>
                    👋 Welcome back!
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, opacity: 0.85 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#4ADE80', display: 'inline-block' }} />
                Online now
                {/* Phase 2: Language indicator */}
                {detectedLang && (
                  <span style={{ marginLeft: 6, background: 'rgba(255,255,255,0.2)', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>
                    {LANG_NAMES[detectedLang] || detectedLang.toUpperCase()}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={resetChat}
              style={{ background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
            >Reset</button>
          </div>

          {/* Messages */}
          <div style={{
            height: 380, overflowY: 'auto', padding: '16px',
            display: 'flex', flexDirection: 'column', gap: 10, background: '#F8F8FA',
          }}>
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '80%', padding: '10px 14px',
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                  background: msg.role === 'user' ? accent : '#fff',
                  color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                  fontSize: 14, lineHeight: 1.5,
                  boxShadow: '0 1px 2px rgba(0,0,0,0.06)', whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3 }}>
                  {msg.auto && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>⚡ Instant reply</span>}
                  {msg.voice && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>🎤 Voice</span>}
                </div>
              </div>
            ))}

            {/* Phase 3: Sales Action Cards */}
            {salesAction && !loading && (
              <div style={{ alignSelf: 'flex-start', maxWidth: '90%' }}>
                {salesAction.type === 'discount' && <DiscountCard action={salesAction} accent={accent} />}
                {salesAction.type === 'demo' && <DemoCard action={salesAction} accent={accent} />}
                {salesAction.type === 'capture_lead' && <LeadCaptureCard onCapture={captureLeadFromAction} accent={accent} />}
              </div>
            )}

            {loading && (
              <div style={{ display: 'flex', gap: 4, padding: '8px 0' }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 8, height: 8, borderRadius: '50%', background: accent, opacity: 0.4,
                    animation: `bounce 1s ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Rating Bar */}
          {showRating && !rated && (
            <div style={{
              padding: '10px 16px', background: '#FFFBEB', borderTop: '1px solid #FEF3C7',
              display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            }}>
              <span style={{ fontSize: 13, color: '#92400E' }}>Rate this chat:</span>
              {['😞', '😕', '🙂', '😄'].map((emoji, i) => (
                <button
                  key={i}
                  onClick={() => rateConversation(i + 1)}
                  style={{
                    background: 'none', border: 'none', fontSize: 20, cursor: 'pointer',
                    padding: '2px 4px', transition: 'transform 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.3)'}
                  onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                >{emoji}</button>
              ))}
              <button onClick={() => setShowRating(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>×</button>
            </div>
          )}

          {/* Escalation Banner */}
          {showEscalate && !escalated && (
            <div style={{ padding: '12px 16px', background: '#FFF7ED', borderTop: '1px solid #FED7AA' }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#9A3412', marginBottom: 8 }}>
                🚨 Would you like to speak with a human?
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="input" placeholder="Your email (optional)" value={escalateEmail}
                  onChange={e => setEscalateEmail(e.target.value)} style={{ flex: 1, fontSize: 13 }} />
                <button className="btn btn-primary" style={{ background: '#EA580C', padding: '6px 12px', fontSize: 13 }} onClick={handleEscalate}>Escalate</button>
                <button onClick={() => setShowEscalate(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>×</button>
              </div>
            </div>
          )}

          {/* Input Area */}
          <div style={{
            padding: '12px 16px', borderTop: '1px solid var(--border)',
            display: 'flex', gap: 8, background: '#fff', alignItems: 'center',
          }}>
            {/* Phase 4: Mic Button */}
            {voiceEnabled && voiceSupported && (
              <button
                onClick={toggleListening}
                title={isListening ? 'Stop listening & send' : 'Speak your message'}
                style={{
                  width: 36, height: 36, borderRadius: '50%', border: 'none',
                  background: isListening ? '#EF4444' : 'var(--body-bg)',
                  color: isListening ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, flexShrink: 0,
                  animation: isListening ? 'micPulse 1s ease infinite' : 'none',
                  boxShadow: isListening ? '0 0 0 4px rgba(239,68,68,0.2)' : 'none',
                  transition: 'all 0.15s',
                }}
              >
                {isListening ? '🔴' : '🎤'}
              </button>
            )}
            <input
              className="input"
              placeholder={isListening ? '🎤 Listening... (click mic or wait 3s to send)' : 'Type a message...'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              disabled={loading}
              style={{ flex: 1 }}
            />
            <button
              className="btn btn-primary"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              style={{ padding: '8px 14px' }}
            >Send</button>
          </div>
        </div>

        {/* Escalate manually */}
        {!escalated && !showEscalate && sessionId && (
          <div style={{ marginTop: 12, textAlign: 'center' }}>
            <button className="btn btn-secondary" style={{ fontSize: 13 }} onClick={() => setShowEscalate(true)}>
              🙋 Request human support
            </button>
          </div>
        )}
      </div>

      {/* Info Panel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="card">
          <h3 style={{ fontWeight: 600, marginBottom: 12 }}>Chat Demo</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
            This is a live preview of your support bot. Messages are saved to the database and visible in the Analytics tab.
          </p>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              ['⚡', 'Instant replies', 'come from your FAQ knowledge base (no AI cost)'],
              ['🤖', 'AI replies', 'are generated by Claude when no FAQ matches'],
              ['🧠', 'Memory', 'returning visitors get personalized greetings'],
              ['🌍', 'Multi-language', 'bot responds in the customer\'s language automatically'],
              ['💰', 'Sales mode', 'detects buying intent and shows offers'],
              ['🎤', 'Voice input', 'customers can speak their messages'],
            ].map(([icon, label, desc]) => (
              <div key={label} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13 }}>
                <span>{icon}</span>
                <span><strong>{label}</strong> {desc}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 style={{ fontWeight: 600, marginBottom: 12 }}>Embed Code</h3>
          <pre style={{
            background: 'var(--header-bg)', color: '#86EFAC', padding: 12, borderRadius: 8,
            fontSize: 12, fontFamily: 'var(--font-mono)', overflow: 'auto', whiteSpace: 'pre-wrap',
          }}>{`<script src="https://your-domain/widget.js"\n  data-bot-id="default">\n</script>`}</pre>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }
        @keyframes micPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.05); }
        }
        @keyframes slideUp {
          from { transform: translateY(12px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
