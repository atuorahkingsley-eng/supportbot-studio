import React, { useState, useEffect, useContext } from 'react'
import { ToastContext } from '../App.jsx'

export default function SalesPanel() {
  const addToast = useContext(ToastContext)
  const [config, setConfig] = useState(null)
  const [leads, setLeads] = useState([])
  const [stats, setStats] = useState(null)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState('config')

  useEffect(() => {
    fetch('/api/sales/config').then(r => r.json()).then(setConfig).catch(() => {})
    fetch('/api/sales/leads').then(r => r.json()).then(setLeads).catch(() => {})
    fetch('/api/sales/leads/stats').then(r => r.json()).then(setStats).catch(() => {})
  }, [])

  const saveConfig = async () => {
    setSaving(true)
    try {
      const r = await fetch('/api/sales/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await r.json()
      setConfig(data)
      addToast('Sales configuration saved!', 'success')
    } catch {
      addToast('Failed to save', 'error')
    } finally {
      setSaving(false)
    }
  }

  const markFollowedUp = async (id) => {
    try {
      await fetch(`/api/sales/leads/${id}/follow-up`, { method: 'PUT' })
      setLeads(prev => prev.map(l => l.id === id ? { ...l, followed_up: true } : l))
      addToast('Marked as followed up', 'success')
    } catch {
      addToast('Failed to update', 'error')
    }
  }

  const exportLeads = () => {
    const csv = [
      ['ID', 'Email', 'Name', 'Interest', 'Source', 'Score', 'Date', 'Followed Up'].join(','),
      ...leads.map(l => [l.id, l.email, l.name || '', l.interest || '', l.source, l.buying_signal_score,
        new Date(l.created_at).toLocaleDateString(), l.followed_up].join(','))
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'leads.csv'
    a.click()
  }

  const scoreColor = (s) => {
    if (s >= 4) return '#16A34A'
    if (s >= 3) return '#D97706'
    return '#6B7280'
  }

  if (!config) return <div style={{ color: 'var(--text-muted)', padding: 24 }}>Loading...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Stats Row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {[
            { label: 'Total Leads', value: stats.total, icon: '🎯' },
            { label: 'This Week', value: stats.this_week, icon: '📅' },
            { label: 'This Month', value: stats.this_month, icon: '📆' },
            { label: 'Pending Follow-up', value: stats.pending_follow_up, icon: '⏳' },
          ].map(({ label, value, icon }) => (
            <div key={label} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
                <span style={{ fontSize: 20 }}>{icon}</span>
              </div>
              <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid var(--border)', paddingBottom: 0 }}>
        {[['config', '⚙️ Configuration'], ['leads', '🎯 Lead Board']].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer',
              fontWeight: 500, fontSize: 14,
              color: tab === id ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: `2px solid ${tab === id ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -2,
            }}
          >{label}</button>
        ))}
      </div>

      {/* Configuration Tab */}
      {tab === 'config' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h2 className="section-title" style={{ margin: 0 }}>Sales Agent Settings</h2>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <div style={{ position: 'relative', width: 40, height: 22 }}>
                <input type="checkbox" checked={config.enabled}
                  onChange={e => setConfig(p => ({ ...p, enabled: e.target.checked }))}
                  style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }} />
                <div style={{ position: 'absolute', inset: 0, background: config.enabled ? 'var(--accent)' : 'var(--border)', borderRadius: 999, transition: 'background 0.2s' }} />
                <div style={{ position: 'absolute', top: 3, left: config.enabled ? 20 : 3, width: 16, height: 16, background: '#fff', borderRadius: '50%', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }} />
              </div>
              <span style={{ fontWeight: 500 }}>{config.enabled ? 'Sales Mode Active' : 'Sales Mode Off'}</span>
            </label>
          </div>

          <div className="grid-2">
            <div>
              <label className="label">Greeting Delay (seconds)</label>
              <input className="input" type="number" value={config.greeting_delay_seconds}
                onChange={e => setConfig(p => ({ ...p, greeting_delay_seconds: Number(e.target.value) }))} />
            </div>
            <div>
              <label className="label">Discount Code (optional)</label>
              <input className="input" value={config.discount_code || ''} placeholder="SAVE10"
                onChange={e => setConfig(p => ({ ...p, discount_code: e.target.value }))} />
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label className="label">Greeting Message</label>
            <input className="input" value={config.greeting_message}
              onChange={e => setConfig(p => ({ ...p, greeting_message: e.target.value }))} />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label className="label">Discount Message</label>
            <input className="input" value={config.discount_message || ''} placeholder="Use this code for 10% off!"
              onChange={e => setConfig(p => ({ ...p, discount_message: e.target.value }))} />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label className="label">Demo Booking URL</label>
            <input className="input" type="url" value={config.demo_booking_url || ''} placeholder="https://calendly.com/yourcompany/demo"
              onChange={e => setConfig(p => ({ ...p, demo_booking_url: e.target.value }))} />
          </div>

          <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={config.exit_intent_enabled}
                onChange={e => setConfig(p => ({ ...p, exit_intent_enabled: e.target.checked }))} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>Enable Exit Intent Popup</span>
            </label>
          </div>

          {config.exit_intent_enabled && (
            <div style={{ marginBottom: 16 }}>
              <label className="label">Exit Intent Message</label>
              <input className="input" value={config.exit_intent_message}
                onChange={e => setConfig(p => ({ ...p, exit_intent_message: e.target.value }))} />
            </div>
          )}

          <button className="btn btn-primary" onClick={saveConfig} disabled={saving}>
            {saving ? 'Saving...' : 'Save Sales Config'}
          </button>
        </div>
      )}

      {/* Lead Board Tab */}
      {tab === 'leads' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 className="section-title" style={{ margin: 0 }}>Lead Board ({leads.length})</h2>
            <button className="btn btn-secondary" onClick={exportLeads} style={{ fontSize: 13 }}>⬇ Export CSV</button>
          </div>

          {leads.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0', fontSize: 13 }}>
              No leads yet. Enable sales mode and start chatting!
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border)' }}>
                    {['Email', 'Interest', 'Source', 'Score', 'Date', 'Status'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leads.map(l => (
                    <tr key={l.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 500 }}>{l.email}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {l.interest || '—'}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span className={`badge ${l.source === 'exit_intent' ? 'badge-amber' : l.source === 'proactive' ? 'badge-blue' : 'badge-gray'}`}>
                          {l.source}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{ color: scoreColor(l.buying_signal_score), fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                          {'★'.repeat(l.buying_signal_score)}{'☆'.repeat(5 - l.buying_signal_score)}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                        {new Date(l.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        {l.followed_up
                          ? <span className="badge badge-green">✓ Done</span>
                          : <button
                              className="btn btn-secondary"
                              style={{ padding: '3px 8px', fontSize: 12 }}
                              onClick={() => markFollowedUp(l.id)}
                            >Follow up</button>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
