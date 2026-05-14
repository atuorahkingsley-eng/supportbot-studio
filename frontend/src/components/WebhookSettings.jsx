import React, { useState, useEffect, useContext } from 'react'
import { ToastContext } from '../App.jsx'

const PLATFORMS = ['slack', 'discord', 'whatsapp', 'custom_https']
const NOTIFY_OPTIONS = [
  { value: 'escalation', label: 'Escalations only' },
  { value: 'all', label: 'All messages' },
  { value: 'daily_summary', label: 'Daily summary' },
]

// Granular event subscriptions for custom_https webhooks. Values MUST match
// the strings dispatch_webhook is called with on the backend — the UI is
// only labels; the wire value is what the dispatcher's events filter checks.
const EVENT_OPTIONS = [
  { value: 'escalation',         label: 'Escalation triggered' },
  { value: 'lead_captured',      label: 'Lead captured' },
  { value: 'conversation_ended', label: 'Conversation ended' },
]

const PLATFORM_LABEL = {
  slack: 'Slack',
  discord: 'Discord',
  whatsapp: 'WhatsApp',
  custom_https: 'Custom (n8n / Make / Activepieces)',
}

export default function WebhookSettings() {
  const addToast = useContext(ToastContext)
  const [webhooks, setWebhooks] = useState([])
  const [form, setForm] = useState({
    platform: 'slack',
    webhook_url: '',
    notify_on: 'escalation',
    enabled: true,
    secret: '',
    events: [],
  })
  const [testing, setTesting] = useState({})
  // One-time secret reveal — populated by POST/regenerate responses, then
  // cleared when the user dismisses the modal. Once cleared, the plaintext
  // is gone from the UI forever; only the masked form lives in `webhooks`.
  const [revealedSecret, setRevealedSecret] = useState(null) // { secret, webhookId, isRotation }
  const [secretCopied, setSecretCopied] = useState(false)
  const [regenerating, setRegenerating] = useState({})

  useEffect(() => {
    fetch('/api/webhooks', { credentials: 'include' }).then(r => r.json()).then(setWebhooks).catch(() => {})
  }, [])

  // Switching TO custom_https forces notify_on='all' so the per-event
  // checkboxes are the meaningful filter. Switching AWAY clears the secret
  // — the backend validator rejects `secret` on non-custom platforms.
  const onPlatformChange = (next) => {
    setForm(prev => ({
      ...prev,
      platform: next,
      notify_on: next === 'custom_https' ? 'all' : prev.notify_on,
      secret: next === 'custom_https' ? prev.secret : '',
      events: next === 'custom_https' ? prev.events : [],
    }))
  }

  const toggleEvent = (value) => {
    setForm(prev => ({
      ...prev,
      events: prev.events.includes(value)
        ? prev.events.filter(e => e !== value)
        : [...prev.events, value],
    }))
  }

  const addWebhook = async () => {
    if (!form.webhook_url.trim()) return
    // Build a clean payload — only include secret/events for custom_https,
    // since the backend validator rejects them on managed platforms.
    // Secret is optional for custom_https now: backend auto-generates one
    // via secrets.token_hex(32) when omitted, and surfaces it ONCE in the
    // response so we can show the user a one-time copy modal.
    const payload = {
      platform: form.platform,
      webhook_url: form.webhook_url,
      notify_on: form.notify_on,
      enabled: form.enabled,
    }
    if (form.platform === 'custom_https') {
      if (form.secret.trim()) payload.secret = form.secret
      // Empty list → null = no per-event filter (dispatcher fires every event).
      payload.events = form.events.length > 0 ? form.events : null
    }
    try {
      const r = await fetch('/api/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const wh = await r.json()
      if (!r.ok) {
        addToast(wh.detail || 'Failed to add webhook', 'error')
        return
      }
      // Capture the plaintext secret BEFORE storing the webhook in state —
      // we replace it with the masked form for the list so the cleartext
      // never lingers anywhere except inside the modal.
      const plaintext = wh.platform === 'custom_https' && wh.secret && !wh.secret.startsWith('\u2022')
        ? wh.secret
        : null
      const masked = { ...wh, secret: plaintext ? '\u2022'.repeat(28) + plaintext.slice(-4) : wh.secret }
      setWebhooks(prev => [...prev, masked])
      setForm({
        platform: 'slack', webhook_url: '', notify_on: 'escalation',
        enabled: true, secret: '', events: [],
      })
      if (plaintext) {
        setRevealedSecret({ secret: plaintext, webhookId: wh.id, isRotation: false })
        setSecretCopied(false)
      } else {
        addToast('Webhook added!', 'success')
      }
    } catch {
      addToast('Failed to add webhook', 'error')
    }
  }

  const regenerateSecret = async (wh) => {
    const ok = window.confirm(
      'This will invalidate the old secret. Any active integrations using it will break. Continue?'
    )
    if (!ok) return
    setRegenerating(prev => ({ ...prev, [wh.id]: true }))
    try {
      const r = await fetch(`/api/webhooks/${wh.id}/regenerate-secret`, {
        method: 'POST',
        credentials: 'include',
      })
      const updated = await r.json()
      if (!r.ok) {
        addToast(updated.detail || 'Failed to regenerate secret', 'error')
        return
      }
      const plaintext = updated.secret
      const masked = { ...updated, secret: '\u2022'.repeat(28) + plaintext.slice(-4) }
      setWebhooks(prev => prev.map(w => w.id === updated.id ? masked : w))
      setRevealedSecret({ secret: plaintext, webhookId: updated.id, isRotation: true })
      setSecretCopied(false)
    } catch {
      addToast('Failed to regenerate secret', 'error')
    } finally {
      setRegenerating(prev => ({ ...prev, [wh.id]: false }))
    }
  }

  const copyRevealedSecret = async () => {
    if (!revealedSecret) return
    try {
      await navigator.clipboard.writeText(revealedSecret.secret)
      setSecretCopied(true)
    } catch {
      addToast('Copy failed — select and copy manually', 'error')
    }
  }

  const dismissRevealedSecret = () => {
    setRevealedSecret(null)
    setSecretCopied(false)
  }

  const deleteWebhook = async (id) => {
    try {
      await fetch(`/api/webhooks/${id}`, { method: 'DELETE', credentials: 'include' })
      setWebhooks(prev => prev.filter(w => w.id !== id))
      addToast('Webhook removed', 'info')
    } catch {
      addToast('Failed to remove webhook', 'error')
    }
  }

  const testWebhook = async (id) => {
    setTesting(prev => ({ ...prev, [id]: true }))
    try {
      const r = await fetch(`/api/webhooks/${id}/test`, { method: 'POST', credentials: 'include' })
      const data = await r.json()
      if (data.ok) {
        addToast('Test message sent successfully!', 'success')
        setWebhooks(prev => prev.map(w => w.id === id ? { ...w, last_test_ok: true } : w))
      } else {
        addToast('Test failed — check your webhook URL', 'error')
        setWebhooks(prev => prev.map(w => w.id === id ? { ...w, last_test_ok: false } : w))
      }
    } catch {
      addToast('Test request failed', 'error')
    } finally {
      setTesting(prev => ({ ...prev, [id]: false }))
    }
  }

  const toggleEnabled = async (wh) => {
    try {
      const r = await fetch(`/api/webhooks/${wh.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ enabled: !wh.enabled }),
      })
      if (!r.ok) {
        addToast('Failed to update webhook', 'error')
        return
      }
      const updated = await r.json()
      setWebhooks(prev => prev.map(w => w.id === wh.id ? updated : w))
    } catch {
      addToast('Failed to update webhook', 'error')
    }
  }

  const platformIcon = { slack: '💬', discord: '🎮', whatsapp: '📱', custom_https: '🔗' }

  return (
    <div className="card">
      <h2 className="section-title">Webhooks</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
        Get notified on Slack, Discord, or WhatsApp when customers need support.
      </p>

      {/* Add Webhook Form */}
      <div style={{ background: 'var(--body-bg)', border: '1px solid var(--border)', borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 160px', gap: 10, marginBottom: 10 }}>
          <div>
            <label className="label">Platform</label>
            <select
              className="input"
              value={form.platform}
              onChange={e => onPlatformChange(e.target.value)}
            >
              {PLATFORMS.map(p => (
                <option key={p} value={p}>{platformIcon[p]} {PLATFORM_LABEL[p] || p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Webhook URL</label>
            <input
              className="input"
              value={form.webhook_url}
              onChange={e => setForm(prev => ({ ...prev, webhook_url: e.target.value }))}
              placeholder={form.platform === 'custom_https'
                ? 'https://your-n8n-or-make-webhook-url'
                : 'https://hooks.slack.com/services/...'}
            />
          </div>
          <div>
            <label className="label">Notify On</label>
            <select
              className="input"
              value={form.notify_on}
              onChange={e => setForm(prev => ({ ...prev, notify_on: e.target.value }))}
            >
              {NOTIFY_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
        {form.platform === 'custom_https' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 12 }}>
            <div>
              <label className="label">HMAC Secret</label>
              <input
                className="input"
                type="password"
                autoComplete="off"
                value={form.secret}
                onChange={e => setForm(prev => ({ ...prev, secret: e.target.value }))}
                placeholder="leave blank to auto-generate a 256-bit secret"
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 4 }}>
                Used to sign each request body — receivers verify via the X-SupportBot-Signature header.
                If you leave this blank, we'll generate one and show it to you once.
              </div>
            </div>
            <div>
              <label className="label">Subscribe to events</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                {EVENT_OPTIONS.map(ev => (
                  <label key={ev.value} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={form.events.includes(ev.value)}
                      onChange={() => toggleEvent(ev.value)}
                    />
                    <span>{ev.label}</span>
                    <code style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ev.value}</code>
                  </label>
                ))}
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 6 }}>
                Leave all unchecked to receive every event.
              </div>
            </div>
          </div>
        )}
        <button
          className="btn btn-primary"
          onClick={addWebhook}
          disabled={!form.webhook_url.trim()}
        >
          + Add Webhook
        </button>
      </div>

      {/* Webhook List */}
      {webhooks.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0', fontSize: 13 }}>
          No webhooks configured yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {webhooks.map(wh => (
            <div key={wh.id} style={{
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}>
              <span style={{ fontSize: 20 }}>{platformIcon[wh.platform]}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{PLATFORM_LABEL[wh.platform] || wh.platform}</span>
                  <span className={`badge ${wh.enabled ? 'badge-green' : 'badge-gray'}`}>
                    {wh.enabled ? 'Active' : 'Paused'}
                  </span>
                  {wh.last_test_ok === true && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--success)' }}>
                      <span className="status-dot status-dot-green" /> Connected
                    </span>
                  )}
                  {wh.last_test_ok === false && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--error)' }}>
                      <span className="status-dot status-dot-red" /> Failed
                    </span>
                  )}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {wh.webhook_url} · {NOTIFY_OPTIONS.find(o => o.value === wh.notify_on)?.label}
                </div>
                {wh.platform === 'custom_https' && wh.secret_generated && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, fontSize: 12 }}>
                    <span className="badge badge-green">Secret set</span>
                    <code style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {wh.secret}
                    </code>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: '4px 10px' }}
                  onClick={() => testWebhook(wh.id)}
                  disabled={testing[wh.id]}
                >
                  {testing[wh.id] ? 'Testing...' : 'Test'}
                </button>
                {wh.platform === 'custom_https' && (
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '4px 10px' }}
                    onClick={() => regenerateSecret(wh)}
                    disabled={regenerating[wh.id]}
                    title="Generate a new HMAC secret — old one stops working immediately"
                  >
                    {regenerating[wh.id] ? 'Rotating...' : 'Regenerate'}
                  </button>
                )}
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: '4px 10px' }}
                  onClick={() => toggleEnabled(wh)}
                >
                  {wh.enabled ? 'Pause' : 'Enable'}
                </button>
                <button
                  className="btn btn-danger"
                  style={{ fontSize: 12, padding: '4px 10px' }}
                  onClick={() => deleteWebhook(wh.id)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* One-time secret display modal — visible only after a fresh
          create/regenerate response carries a plaintext `secret`. The
          plaintext lives in component state for the lifetime of this
          modal and is dropped the moment it closes. */}
      {revealedSecret && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={dismissRevealedSecret}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 10, padding: 24, maxWidth: 540, width: '92%',
              boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
            }}
          >
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>
              {revealedSecret.isRotation ? 'New webhook secret' : 'Webhook secret generated'}
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
              Copy this secret now — <strong>this is the only time we'll show it.</strong>{' '}
              Use it on your receiver to verify the <code>X-SupportBot-Signature</code> header.
            </p>
            <div style={{
              background: 'var(--body-bg)', border: '1px solid var(--border)',
              borderRadius: 6, padding: 12, marginBottom: 12,
              fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all',
            }}>
              {revealedSecret.secret}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={copyRevealedSecret}>
                {secretCopied ? 'Copied \u2713' : 'Copy'}
              </button>
              <button className="btn btn-primary" onClick={dismissRevealedSecret}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
