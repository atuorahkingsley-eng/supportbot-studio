import React, { useState, useEffect, useRef, useContext } from 'react'
import { ToastContext } from '../App.jsx'

export default function ChatWidget({ config }) {
  const addToast = useContext(ToastContext)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showEscalate, setShowEscalate] = useState(false)
  const [escalateEmail, setEscalateEmail] = useState('')
  const [escalated, setEscalated] = useState(false)
  const [showRating, setShowRating] = useState(false)
  const [rated, setRated] = useState(false)
  const bottomRef = useRef()

  const accent = config?.brand_color || '#6366F1'
  const agentName = config?.agent_name || 'SupportBot'
  const welcomeMsg = config?.welcome_message || 'Hi! How can I help you today?'

  useEffect(() => {
    setMessages([{ role: 'assistant', content: welcomeMsg, auto: false }])
  }, [welcomeMsg])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const userMsgs = messages.filter(m => m.role === 'user').length
    if (userMsgs >= 4 && !rated) setShowRating(true)
  }, [messages, rated])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: userMsg }),
      })
      const data = await r.json()
      if (!sessionId) setSessionId(data.session_id)

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.reply,
        auto: data.was_auto_reply,
      }])

      if (data.needs_escalation) {
        setTimeout(() => setShowEscalate(true), 800)
      }
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        auto: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleEscalate = async () => {
    if (!sessionId) return
    try {
      await fetch('/api/escalate', {
        method: 'POST',
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

  const rateConversation = async (rating) => {
    if (!sessionId) return
    try {
      await fetch(`/api/chat/rate?session_id=${sessionId}&rating=${rating}`, { method: 'POST' })
      setRated(true)
      setShowRating(false)
      addToast('Thanks for your feedback!', 'success')
    } catch {}
  }

  const resetChat = () => {
    setMessages([{ role: 'assistant', content: welcomeMsg, auto: false }])
    setSessionId(null)
    setEscalated(false)
    setShowEscalate(false)
    setRated(false)
    setShowRating(false)
  }

  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
      {/* Chat Window */}
      <div style={{ flex: 1, maxWidth: 480 }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {/* Chat Header */}
          <div style={{
            background: accent,
            color: '#fff',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'rgba(255,255,255,0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
            }}>🤖</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{agentName}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, opacity: 0.85 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#4ADE80', display: 'inline-block' }} />
                Online now
              </div>
            </div>
            <button
              onClick={resetChat}
              style={{ marginLeft: 'auto', background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
            >
              Reset
            </button>
          </div>

          {/* Messages */}
          <div style={{
            height: 380,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            background: '#F8F8FA',
          }}>
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '80%',
                  padding: '10px 14px',
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                  background: msg.role === 'user' ? accent : '#fff',
                  color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                  fontSize: 14,
                  lineHeight: 1.5,
                  boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
                {msg.auto && (
                  <div style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    marginTop: 3,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}>
                    ⚡ Instant reply
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div style={{ display: 'flex', gap: 4, padding: '8px 0' }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: accent, opacity: 0.4,
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
              padding: '10px 16px',
              background: '#FFFBEB',
              borderTop: '1px solid #FEF3C7',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
            }}>
              <span style={{ fontSize: 13, color: '#92400E' }}>Rate this chat:</span>
              {['😞', '😕', '🙂', '😄'].map((emoji, i) => (
                <button
                  key={i}
                  onClick={() => rateConversation(i + 1)}
                  style={{
                    background: 'none', border: 'none', fontSize: 20,
                    cursor: 'pointer', padding: '2px 4px',
                    transform: 'scale(1)',
                    transition: 'transform 0.1s',
                  }}
                  onMouseEnter={e => e.target.style.transform = 'scale(1.3)'}
                  onMouseLeave={e => e.target.style.transform = 'scale(1)'}
                >
                  {emoji}
                </button>
              ))}
              <button onClick={() => setShowRating(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>×</button>
            </div>
          )}

          {/* Escalation Banner */}
          {showEscalate && !escalated && (
            <div style={{
              padding: '12px 16px',
              background: '#FFF7ED',
              borderTop: '1px solid #FED7AA',
            }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#9A3412', marginBottom: 8 }}>
                🚨 Would you like to speak with a human?
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="input"
                  placeholder="Your email (optional)"
                  value={escalateEmail}
                  onChange={e => setEscalateEmail(e.target.value)}
                  style={{ flex: 1, fontSize: 13 }}
                />
                <button
                  className="btn btn-primary"
                  style={{ background: '#EA580C', padding: '6px 12px', fontSize: 13 }}
                  onClick={handleEscalate}
                >
                  Escalate
                </button>
                <button
                  onClick={() => setShowEscalate(false)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}
                >×</button>
              </div>
            </div>
          )}

          {/* Input */}
          <div style={{
            padding: '12px 16px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            gap: 8,
            background: '#fff',
          }}>
            <input
              className="input"
              placeholder="Type a message..."
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
            >
              Send
            </button>
          </div>
        </div>

        {/* Escalate manually */}
        {!escalated && !showEscalate && sessionId && (
          <div style={{ marginTop: 12, textAlign: 'center' }}>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 13 }}
              onClick={() => setShowEscalate(true)}
            >
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span>⚡</span>
              <span><strong>Instant replies</strong> come from your FAQ knowledge base (no AI cost)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span>🤖</span>
              <span><strong>AI replies</strong> are generated by Claude when no FAQ matches</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span>🚨</span>
              <span><strong>Escalation</strong> notifies your team via Telegram, email, and webhooks</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 style={{ fontWeight: 600, marginBottom: 12 }}>Embed Code</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 10 }}>
            Add this to your website to embed the chat widget:
          </p>
          <pre style={{
            background: 'var(--header-bg)',
            color: '#86EFAC',
            padding: 12,
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
          }}>
{`<script src="https://your-domain/widget.js"
  data-bot-id="default">
</script>`}
          </pre>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }
      `}</style>
    </div>
  )
}
