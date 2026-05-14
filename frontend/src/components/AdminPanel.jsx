import React, { useState, useEffect, useContext, useRef } from 'react'
import { ToastContext } from '../App.jsx'

export default function AdminPanel({ config, setConfig }) {
  const addToast = useContext(ToastContext)
  const [form, setForm] = useState(config)
  const [faqs, setFaqs] = useState([])
  const [newQ, setNewQ] = useState('')
  const [newA, setNewA] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [botUsername, setBotUsername] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  // ── Brand Voice DNA ─────────────────────────────────────────────────────
  const [voiceSamples, setVoiceSamples] = useState('')
  const [voiceProfile, setVoiceProfile] = useState(null)   // null when no profile saved
  const [analyzingVoice, setAnalyzingVoice] = useState(false)

  // ── Change Password ─────────────────────────────────────────────────────
  // Server enforces an 8-char min on new_password. We mirror that here so
  // the user gets immediate feedback instead of a round-trip to find out.
  const [pwCurrent, setPwCurrent] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [changingPw, setChangingPw] = useState(false)

  useEffect(() => { setForm(config) }, [config])

  useEffect(() => {
    fetch('/api/knowledge', { credentials: 'include' })
      .then(r => r.json())
      .then(setFaqs)
      .catch(() => addToast('Failed to load knowledge base', 'error'))
  }, [])

  // Fetch existing brand voice on mount — 404 is the empty state, not an error.
  useEffect(() => {
    fetch('/api/brand-voice', { credentials: 'include' }).then(r => {
      if (r.status === 404) return null
      if (!r.ok) throw new Error('fetch failed')
      return r.json()
    }).then(data => {
      if (data) setVoiceProfile(data)
    }).catch(() => {})
  }, [])

  // Fetch bot username for Connect Telegram button
  useEffect(() => {
    fetch('/api/config/bot-username')
      .then(r => r.ok ? r.json() : { username: '' })
      .then(d => setBotUsername(d.username || ''))
      .catch(() => {})
  }, [])

  const saveConfig = async () => {
    try {
      const r = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(form),
      })
      const data = await r.json()
      setConfig(data)
      addToast('Configuration saved!', 'success')
    } catch {
      addToast('Failed to save config', 'error')
    }
  }

  const addFaq = async () => {
    if (!newQ.trim() || !newA.trim()) return
    try {
      const r = await fetch('/api/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ question: newQ, answer: newA }),
      })
      const faq = await r.json()
      setFaqs(prev => [faq, ...prev])
      setNewQ('')
      setNewA('')
      addToast('FAQ added!', 'success')
    } catch {
      addToast('Failed to add FAQ', 'error')
    }
  }

  const deleteFaq = async (id) => {
    try {
      await fetch(`/api/knowledge/${id}`, { method: 'DELETE', credentials: 'include' })
      setFaqs(prev => prev.filter(f => f.id !== id))
      addToast('FAQ removed', 'info')
    } catch {
      addToast('Failed to delete FAQ', 'error')
    }
  }

  // ── Brand Voice DNA handlers ───────────────────────────────────────────
  const analyzeBrandVoice = async () => {
    if (voiceSamples.trim().length < 20) {
      addToast('Paste at least 20 characters of your brand copy first', 'error')
      return
    }
    setAnalyzingVoice(true)
    try {
      const r = await fetch('/api/brand-voice/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ samples: voiceSamples }),
      })
      if (r.status === 429) {
        addToast('Rate limit hit — only 5 analyses per hour. Try again later.', 'error')
        return
      }
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || 'Analysis failed')
      }
      const data = await r.json()
      setVoiceProfile(data)
      addToast('Brand voice extracted! Review it, then toggle Active.', 'success')
    } catch (e) {
      addToast(e.message || 'Failed to analyze brand voice', 'error')
    } finally {
      setAnalyzingVoice(false)
    }
  }

  const toggleBrandVoiceActive = async () => {
    if (!voiceProfile) return
    try {
      const r = await fetch('/api/brand-voice', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ is_active: !voiceProfile.is_active }),
      })
      if (!r.ok) throw new Error('toggle failed')
      const data = await r.json()
      setVoiceProfile(data)
      addToast(data.is_active ? 'Brand voice activated' : 'Brand voice paused', 'success')
    } catch {
      addToast('Failed to toggle brand voice', 'error')
    }
  }

  const deleteBrandVoice = async () => {
    if (!voiceProfile) return
    if (!confirm('Delete the saved brand voice profile? You can always re-analyze later.')) return
    try {
      const r = await fetch('/api/brand-voice', { method: 'DELETE', credentials: 'include' })
      if (!r.ok) throw new Error('delete failed')
      setVoiceProfile(null)
      setVoiceSamples('')
      addToast('Brand voice profile removed', 'info')
    } catch {
      addToast('Failed to delete brand voice', 'error')
    }
  }

  // ── Change Password handler ────────────────────────────────────────────
  const changePassword = async () => {
    if (pwNew.length < 8) {
      addToast('New password must be at least 8 characters', 'error')
      return
    }
    if (pwNew !== pwConfirm) {
      addToast('New passwords do not match', 'error')
      return
    }
    setChangingPw(true)
    try {
      const r = await fetch('/api/auth/change-password', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ current_password: pwCurrent, new_password: pwNew }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || 'Password change failed')
      }
      setPwCurrent('')
      setPwNew('')
      setPwConfirm('')
      addToast('Password updated', 'success')
    } catch (e) {
      addToast(e.message || 'Failed to change password', 'error')
    } finally {
      setChangingPw(false)
    }
  }

  const handleUpload = async (file) => {
    if (!file) return
    const allowed = ['.pdf', '.docx', '.csv', '.txt']
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!allowed.includes(ext)) {
      addToast('Unsupported file type. Use PDF, DOCX, CSV, or TXT', 'error')
      return
    }
    setUploading(true)
    setUploadResult(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch('/api/knowledge/upload', { method: 'POST', credentials: 'include', body: fd })
      const data = await r.json()
      setUploadResult(data)
      fetch('/api/knowledge', { credentials: 'include' })
        .then(r => r.json())
        .then(setFaqs)
        .catch(() => {})
      addToast(`Extracted ${data.added} Q&A pairs from ${file.name}`, 'success')
    } catch {
      addToast('Upload failed', 'error')
    } finally {
      setUploading(false)
    }
  }

  const field = (label, key, type = 'text', extra = {}) => (
    <div style={{ marginBottom: 16 }}>
      <label className="label">{label}</label>
      <input
        className="input"
        type={type}
        value={form[key] || ''}
        onChange={e => setForm(prev => ({ ...prev, [key]: e.target.value }))}
        {...extra}
      />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Bot Configuration */}
      <div className="card">
        <h2 className="section-title">Bot Configuration</h2>
        <div className="grid-2">
          {field('Business Name', 'business_name', 'text', { placeholder: 'Acme Corp' })}
          {field('Agent Name', 'agent_name', 'text', { placeholder: 'SupportBot' })}
        </div>
        <div className="grid-2">
          <div style={{ marginBottom: 16 }}>
            <label className="label">Brand Color</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="color"
                value={form.brand_color || '#6366F1'}
                onChange={e => setForm(prev => ({ ...prev, brand_color: e.target.value }))}
                style={{ width: 40, height: 36, border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer', padding: 2 }}
              />
              <input
                className="input"
                value={form.brand_color || ''}
                onChange={e => setForm(prev => ({ ...prev, brand_color: e.target.value }))}
                placeholder="#6366F1"
                style={{ flex: 1 }}
              />
            </div>
          </div>
          {field('Escalation Email', 'escalation_email', 'email', { placeholder: 'support@yourcompany.com' })}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label className="label">Welcome Message</label>
          <textarea
            className="input"
            rows={2}
            value={form.welcome_message || ''}
            onChange={e => setForm(prev => ({ ...prev, welcome_message: e.target.value }))}
            placeholder="Hi! How can I help you today?"
            style={{ resize: 'vertical' }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label className="label">Greeting Message</label>
          <input
            className="input"
            value={form.greeting_message || ''}
            onChange={e => setForm(prev => ({ ...prev, greeting_message: e.target.value }))}
            placeholder="Hi! Need help?"
          />
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Shown as a tooltip above the chat bubble 5 seconds after your widget loads.
          </div>
        </div>
        {/* Phase 4: Voice toggle */}
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <div style={{ position: 'relative', width: 40, height: 22 }}>
              <input
                type="checkbox"
                checked={form.voice_enabled !== false}
                onChange={e => setForm(prev => ({ ...prev, voice_enabled: e.target.checked }))}
                style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
              />
              <div style={{
                position: 'absolute', inset: 0,
                background: form.voice_enabled !== false ? 'var(--color-cta)' : 'var(--border)',
                borderRadius: 999, transition: 'background 0.2s',
              }} />
              <div style={{
                position: 'absolute', top: 3,
                left: form.voice_enabled !== false ? 20 : 3,
                width: 16, height: 16,
                background: '#fff', borderRadius: '50%',
                transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              }} />
            </div>
            <span style={{ fontSize: 14, fontWeight: 500 }}>🎤 Enable Voice Input</span>
          </label>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Customers can speak their messages using the browser mic
          </span>
        </div>
        {/* Per-tenant Telegram chat target. Optional. Sent IN ADDITION TO
            the platform-wide chat — never instead of it. */}
        <div style={{ marginBottom: 16 }}>
          <label className="label">Telegram Handle (optional)</label>
          <input
            className="input"
            value={form.telegram_handle || ''}
            onChange={e => setForm(prev => ({ ...prev, telegram_handle: e.target.value }))}
            placeholder="@your_handle  or  123456789"
          />
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Get an extra Telegram ping for every escalation. Numeric chat ID works directly;
            <code> @username</code> only works after you've sent a message to the bot first.
            Leave blank to disable.
          </div>
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {botUsername && (
              <a
                href={`https://t.me/${botUsername}?start=botid_${(form.bot_id || config?.bot_id || '')}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'inline-block', background: '#E8F5E9', color: '#2E7D32', border: '1px solid #A5D6A7', borderRadius: 6, padding: '6px 14px', fontSize: 13, fontWeight: 600, textDecoration: 'none', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.background = '#C8E6C9'}
                onMouseLeave={e => e.currentTarget.style.background = '#E8F5E9'}
              >
                🔗 Connect Telegram for alerts
              </a>
            )}
            {form.telegram_handle && (
              <span style={{ fontSize: 12, color: '#6B7280' }}>
                ✅ ID: {form.telegram_handle}
              </span>
            )}
          </div>
        </div>
        <button className="btn btn-primary" onClick={saveConfig}>Save Configuration</button>
      </div>

      {/* Brand Voice DNA */}
      <div className="card">
        <h2 className="section-title">Brand Voice DNA</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
          Paste samples of your existing copy — marketing pages, support emails, blog posts.
          Claude extracts your brand's tone, vocabulary, and personality, then writes replies in that voice.
        </p>

        <div style={{ marginBottom: 12 }}>
          <label className="label">Brand copy samples</label>
          <textarea
            className="input"
            rows={6}
            value={voiceSamples}
            onChange={e => setVoiceSamples(e.target.value)}
            placeholder="Paste a few paragraphs from your homepage, support docs, or recent emails..."
            style={{ resize: 'vertical', fontFamily: 'inherit' }}
          />
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            {voiceSamples.length} characters · 8000 max · limit 5 analyses per hour
          </div>
        </div>

        <button
          className="btn btn-primary"
          onClick={analyzeBrandVoice}
          disabled={analyzingVoice || voiceSamples.trim().length < 20}
        >
          {analyzingVoice ? 'Analyzing with Claude...' : (voiceProfile ? 'Re-analyze' : 'Analyze Brand Voice')}
        </button>

        {voiceProfile && (
          <div style={{
            marginTop: 20,
            padding: 16,
            background: 'var(--body-bg)',
            border: '1px solid var(--border)',
            borderRadius: 8,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <strong>Extracted profile</strong>
              <span className={`badge ${voiceProfile.is_active ? 'badge-green' : 'badge-blue'}`}>
                {voiceProfile.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>

            {voiceProfile.tone && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Tone</div>
                <div style={{ fontSize: 14 }}>{voiceProfile.tone}</div>
              </div>
            )}

            {voiceProfile.vocabulary && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Vocabulary</div>
                <div style={{ fontSize: 14 }}>{voiceProfile.vocabulary}</div>
              </div>
            )}

            {voiceProfile.personality_traits && voiceProfile.personality_traits.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Personality</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                  {voiceProfile.personality_traits.map((t, i) => (
                    <span key={i} className="badge badge-blue">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {voiceProfile.avoid && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Avoid</div>
                <div style={{ fontSize: 14 }}>{voiceProfile.avoid}</div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              <button className="btn btn-secondary" onClick={toggleBrandVoiceActive}>
                {voiceProfile.is_active ? 'Pause' : 'Activate'}
              </button>
              <button className="btn btn-danger" onClick={deleteBrandVoice}>
                Delete profile
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Document Upload */}
      <div className="card">
        <h2 className="section-title">Upload Knowledge Document</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
          Upload a PDF, DOCX, CSV, or TXT file — the bot will automatically extract FAQ pairs from it.
        </p>
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault()
            setDragOver(false)
            handleUpload(e.dataTransfer.files[0])
          }}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? 'var(--color-cta)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)',
            padding: '32px',
            textAlign: 'center',
            cursor: 'pointer',
            background: dragOver ? 'var(--color-cta-light)' : 'var(--body-bg)',
            transition: 'background 150ms ease, border-color 150ms ease',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>
            {uploading ? 'Processing...' : 'Drop file here or click to browse'}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>PDF · DOCX · CSV · TXT</div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.csv,.txt"
            style={{ display: 'none' }}
            onChange={e => handleUpload(e.target.files[0])}
          />
        </div>

        {uploading && (
          <div style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
            ⏳ Extracting Q&A pairs with AI...
          </div>
        )}

        {uploadResult && !uploading && (
          <div style={{ marginTop: 12, padding: '12px 16px', background: '#F0FDF4', borderRadius: 8, border: '1px solid #BBF7D0' }}>
            <strong style={{ color: '#16A34A' }}>✅ Upload complete!</strong>
            <div style={{ fontSize: 13, color: '#166534', marginTop: 4 }}>
              Extracted {uploadResult.extracted} pairs · Added {uploadResult.added} to knowledge base from <em>{uploadResult.filename}</em>
            </div>
          </div>
        )}
      </div>

      {/* Knowledge Base */}
      <div className="card">
        <h2 className="section-title">Knowledge Base ({faqs.length} entries)</h2>

        {/* Add FAQ */}
        <div style={{ background: 'var(--body-bg)', borderRadius: 8, padding: 16, marginBottom: 20, border: '1px solid var(--border)' }}>
          <div style={{ marginBottom: 10 }}>
            <label className="label">Question</label>
            <input
              className="input"
              value={newQ}
              onChange={e => setNewQ(e.target.value)}
              placeholder="How do I reset my password?"
              onKeyDown={e => e.key === 'Enter' && addFaq()}
            />
          </div>
          <div style={{ marginBottom: 10 }}>
            <label className="label">Answer</label>
            <textarea
              className="input"
              rows={2}
              value={newA}
              onChange={e => setNewA(e.target.value)}
              placeholder="To reset your password, click..."
              style={{ resize: 'vertical' }}
            />
          </div>
          <button className="btn btn-primary" onClick={addFaq} disabled={!newQ.trim() || !newA.trim()}>
            + Add FAQ
          </button>
        </div>

        {/* FAQ List */}
        {faqs.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0', fontSize: 13 }}>
            No FAQs yet. Add one above or upload a document.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {faqs.map(faq => (
              <div key={faq.id} style={{
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '12px 14px',
                display: 'flex',
                gap: 12,
                alignItems: 'flex-start',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, marginBottom: 4 }}>{faq.question}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{faq.answer}</div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
                    <span className={`badge ${faq.source === 'manual' ? 'badge-blue' : 'badge-green'}`}>
                      {faq.source === 'manual' ? 'Manual' : `📄 ${faq.source_filename || 'Uploaded'}`}
                    </span>
                  </div>
                </div>
                <button
                  className="btn btn-danger"
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  onClick={() => deleteFaq(faq.id)}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Change Password — tenant self-service.
          Server enforces 8-char min; we mirror that here. */}
      <div className="card">
        <h2 className="section-title">Change Password</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
          Update the password you use to sign in to this dashboard. Minimum 8 characters.
        </p>
        <div style={{ marginBottom: 12 }}>
          <label className="label">Current password</label>
          <input
            className="input"
            type="password"
            value={pwCurrent}
            onChange={e => setPwCurrent(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label className="label">New password</label>
          <input
            className="input"
            type="password"
            value={pwNew}
            onChange={e => setPwNew(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label className="label">Confirm new password</label>
          <input
            className="input"
            type="password"
            value={pwConfirm}
            onChange={e => setPwConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={changePassword}
          disabled={changingPw || !pwCurrent || !pwNew || !pwConfirm}
        >
          {changingPw ? 'Updating...' : 'Update Password'}
        </button>
      </div>
    </div>
  )
}
