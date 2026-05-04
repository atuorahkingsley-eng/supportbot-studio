import React, { useState, useEffect, useContext } from 'react'
import { ToastContext } from '../App.jsx'

const PLATFORMS = ['slack', 'discord', 'whatsapp']
const NOTIFY_OPTIONS = [
  { value: 'escalation', label: 'Escalations only' },
  { value: 'all', label: 'All messages' },
  { value: 'daily_summary', label: 'Daily summary' },
]

export default function WebhookSettings() {
  const addToast = useContext(ToastContext)
  const [webhooks, setWebhooks] = useState([])
  const [form, setForm] = useState({ platform: 'slack', webhook_url: '', notify_on: 'escalation', enabled: true })
  const [testing, setTesting] = useState({})

  useEffect(() => {
    fetch('/api/webhooks', { credentials: 'include' }).then(r => r.json()).then(setWebhooks).catch(() => {})
  }, [])

  const addWebhook = async () => {
    if (!form.webhook_url.trim()) return
    try {
      const r = await fetch('/api/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(form),
      })
      const wh = await r.json()
      setWebhooks(prev => [...prev, wh])
      setForm({ platform: 'slack', webhook_url: '', notify_on: 'escalation', enabled: true })
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

  const platformIcon = { slack: '💬', discord: '🎮', whatsapp: '📱' }

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
              onChange={e => setForm(prev => ({ ...prev, platform: e.target.value }))}
            >
              {PLATFORMS.map(p => (
                <option key={p} value={p}>{platformIcon[p]} {p.charAt(0).toUpperCase() + p.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Webhook URL</label>
            <input
              className="input"
              value={form.webhook_url}
              onChange={e => setForm(prev => ({ ...prev, webhook_url: e.target.value }))}
              placeholder="https://hooks.slack.com/services/..."
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
                  <span>{wh.platform.charAt(0).toUpperCase() + wh.platform.slice(1)}</span>
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
