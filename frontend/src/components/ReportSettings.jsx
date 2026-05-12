import React, { useState, useEffect, useContext } from 'react'
import { ToastContext } from '../App.jsx'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function ReportSettings() {
  const addToast = useContext(ToastContext)
  const [schedule, setSchedule] = useState({
    frequency: 'daily',
    send_via: 'telegram',
    send_at_hour: 8,
    send_on_day: null,
    enabled: true,
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/reports', { credentials: 'include' }).then(async r => {
      if (!r.ok) {
        console.error('Failed to load report settings')
        return
      }
      setSchedule(await r.json())
    }).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const r = await fetch('/api/reports', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(schedule),
      })
      const data = await r.json()
      setSchedule(data)
      addToast('Report schedule saved!', 'success')
    } catch {
      addToast('Failed to save schedule', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h2 className="section-title" style={{ margin: 0 }}>Scheduled Reports</h2>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <div style={{ position: 'relative', width: 40, height: 22 }}>
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={e => setSchedule(prev => ({ ...prev, enabled: e.target.checked }))}
              style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
            />
            <div style={{
              position: 'absolute', inset: 0,
              background: schedule.enabled ? 'var(--color-cta)' : 'var(--border)',
              borderRadius: 999,
              transition: 'background 0.2s',
            }} />
            <div style={{
              position: 'absolute',
              top: 3, left: schedule.enabled ? 20 : 3,
              width: 16, height: 16,
              background: '#fff',
              borderRadius: '50%',
              transition: 'left 0.2s',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 500 }}>{schedule.enabled ? 'Enabled' : 'Disabled'}</span>
        </label>
      </div>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
        Automatically send performance summaries to your team via Telegram or email.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Frequency */}
        <div>
          <label className="label">Frequency</label>
          <select
            className="input"
            value={schedule.frequency}
            onChange={e => setSchedule(prev => ({ ...prev, frequency: e.target.value }))}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>

        {/* Send at hour */}
        <div>
          <label className="label">Send At (UTC hour)</label>
          <select
            className="input"
            value={schedule.send_at_hour}
            onChange={e => setSchedule(prev => ({ ...prev, send_at_hour: Number(e.target.value) }))}
          >
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>{String(h).padStart(2, '0')}:00 UTC</option>
            ))}
          </select>
        </div>

        {/* Send via */}
        <div>
          <label className="label">Deliver Via</label>
          <select
            className="input"
            value={schedule.send_via}
            onChange={e => setSchedule(prev => ({ ...prev, send_via: e.target.value }))}
          >
            <option value="telegram">📱 Telegram</option>
            <option value="email">📧 Email</option>
            <option value="both">Both</option>
          </select>
        </div>
      </div>

      {/* Weekly day picker */}
      {schedule.frequency === 'weekly' && (
        <div style={{ marginBottom: 16 }}>
          <label className="label">Send on Day</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {DAYS.map((day, i) => (
              <button
                key={i}
                onClick={() => setSchedule(prev => ({ ...prev, send_on_day: i }))}
                style={{
                  padding: '6px 12px',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  background: schedule.send_on_day === i ? 'var(--color-cta)' : 'var(--body-bg)',
                  color: schedule.send_on_day === i ? '#fff' : 'var(--text-primary)',
                  fontSize: 13,
                  cursor: 'pointer',
                  fontWeight: 500,
                  transition: 'background 150ms ease, color 150ms ease',
                }}
              >
                {day.slice(0, 3)}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Report Preview */}
      <div style={{
        background: 'var(--header-bg)',
        color: '#E4E4E7',
        borderRadius: 8,
        padding: '14px 16px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        lineHeight: 1.8,
        marginBottom: 16,
      }}>
        <div style={{ color: '#86EFAC' }}>📊 SupportBot Daily Report — Your Business</div>
        <div>Date: {new Date().toISOString().slice(0, 10)}</div>
        <div style={{ marginTop: 8 }}>Conversations: 42</div>
        <div>Messages: 187</div>
        <div>Auto-replies: 134 (71.7% — saved $0.40)</div>
        <div>Escalations: 3</div>
        <div>Avg Rating: 3.8/4</div>
        <div style={{ marginTop: 8 }}>Top 5 Questions:</div>
        <div>1. How do I reset my password? — 12x</div>
        <div>2. What are your business hours? — 8x</div>
        <div style={{ color: '#71717A' }}>...</div>
        <div style={{ marginTop: 8 }}>Resolution Rate: 92.9%</div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save Schedule'}
        </button>
        {schedule.last_sent_at && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Last sent: {new Date(schedule.last_sent_at).toLocaleString()}
          </span>
        )}
      </div>
    </div>
  )
}
