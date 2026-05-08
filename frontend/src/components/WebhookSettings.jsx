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
    if (form.platform === 'custom_https' && !form.secret.trim()) {
      addToast('Custom webhooks require an HMAC secret', 'error')
      return
    }
    // Build a clean payload — only include secret/events for custom_https,
    // since the backend validator rejects them on managed platforms.
    const payload = {
      platform: form.platform,
      webhook_url: form.webhook_url,
      notify_on: form.notify_on,
      enabled: form.enabled,
    }
    if (form.platform === 'custom_https') {
      payload.secret = form.secret
      // Empty list → null = no per-event filter (dispatcher fires every event).
      payload.events = form.events.length > 0 ? JSON.stringify(form.events) : null
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
      setWebhooks(prev => [...prev, wh])
      setForm({
        platform: 'slack', webhook_url: '', notify_on: 'escalation',
        enabled: true, secret: '', events: [],
      })
      addToast('Webhook added!', 'success')
    } catch {
      addToast('Failed to add webhook', 'error')
    }
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
                placeholder="optional secret key (required for custom HTTPS)"
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 4 }}>
                Used to sign each request body — receivers verify via the X-SupportBot-Signature header.
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
          disabled={!form.webhook_url.trim() || (form.platform === 'custom_https' && !form.secret.trim())}
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
    </div>
  )
}
