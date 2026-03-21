import React, { useState, useEffect } from 'react'

function StatCard({ label, value, sub, icon, accent }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{label}</span>
        <span style={{ fontSize: 22 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

function HourlyChart({ data }) {
  if (!data || data.length === 0) return null
  const max = Math.max(...data.map(d => d.count), 1)

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80 }}>
      {data.map(({ hour, count }) => (
        <div key={hour} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, gap: 2 }}>
          <div
            title={`${hour}:00 — ${count} messages`}
            style={{
              width: '100%',
              height: Math.max(4, (count / max) * 72),
              background: 'var(--accent, #6366F1)',
              borderRadius: '3px 3px 0 0',
              opacity: count > 0 ? 1 : 0.15,
              transition: 'height 0.3s',
              cursor: 'default',
            }}
          />
          {hour % 6 === 0 && (
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{hour}</div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function AnalyticsDashboard() {
  const [summary, setSummary] = useState(null)
  const [convos, setConvos] = useState([])
  const [topQ, setTopQ] = useState([])
  const [hourly, setHourly] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([
      fetch('/api/analytics/summary').then(r => r.json()),
      fetch('/api/analytics/conversations?per_page=20').then(r => r.json()),
      fetch('/api/analytics/top-questions').then(r => r.json()),
      fetch('/api/analytics/hourly').then(r => r.json()),
    ]).then(([s, c, q, h]) => {
      setSummary(s)
      setConvos(c.conversations || [])
      setTopQ(q)
      setHourly(h)
    }).catch(() => {}).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const exportCsv = () => {
    window.open('/api/analytics/export', '_blank')
  }

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
      Loading analytics...
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Stat Cards */}
      <div className="grid-4">
        <StatCard
          label="Conversations"
          value={summary?.total_conversations}
          icon="💬"
        />
        <StatCard
          label="Messages"
          value={summary?.total_messages}
          icon="📨"
        />
        <StatCard
          label="Auto-Reply Rate"
          value={summary ? `${summary.auto_reply_rate}%` : null}
          sub={summary ? `${summary.auto_reply_count} instant replies` : null}
          icon="⚡"
          accent="#16A34A"
        />
        <StatCard
          label="Avg Rating"
          value={summary?.avg_rating ? `${summary.avg_rating}/4` : 'N/A'}
          sub={`Resolution rate: ${summary?.resolution_rate ?? 0}%`}
          icon="⭐"
          accent="#D97706"
        />
      </div>

      {/* Savings Banner */}
      {summary?.estimated_savings > 0 && (
        <div style={{
          background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
          border: '1px solid #BBF7D0',
          borderRadius: 'var(--radius)',
          padding: '16px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}>
          <div style={{ fontSize: 32 }}>💰</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 18, color: '#15803D' }}>
              ~${summary.estimated_savings} saved this month
            </div>
            <div style={{ color: '#166534', fontSize: 13 }}>
              Auto-replies handled {summary.auto_reply_count} messages without AI API calls.
              At $0.003/message, that's ${summary.estimated_savings} in savings.
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Hourly Chart */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 className="section-title" style={{ margin: 0 }}>Hourly Activity</h3>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>UTC hours</span>
          </div>
          <HourlyChart data={hourly} />
        </div>

        {/* Top Questions */}
        <div className="card">
          <h3 className="section-title">Top Questions</h3>
          {topQ.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No questions yet</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {topQ.slice(0, 8).map((q, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    color: 'var(--text-muted)',
                    width: 20,
                    textAlign: 'right',
                    flexShrink: 0,
                  }}>#{i + 1}</span>
                  <div style={{
                    flex: 1,
                    fontSize: 13,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>{q.question}</div>
                  <span className="badge badge-gray" style={{ flexShrink: 0 }}>{q.count}x</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Conversation Log */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="section-title" style={{ margin: 0 }}>Conversation Log</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" onClick={load} style={{ fontSize: 13 }}>↻ Refresh</button>
            <button className="btn btn-secondary" onClick={exportCsv} style={{ fontSize: 13 }}>⬇ Export CSV</button>
          </div>
        </div>

        {convos.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0', fontSize: 13 }}>
            No conversations yet — start chatting in the Chat Demo tab!
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)' }}>
                  {['Session', 'Started', 'Messages', 'Customer', 'Rating', 'Status'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {convos.map(c => (
                  <tr key={c.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                      {c.session_id?.slice(0, 8)}...
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                      {c.started_at ? new Date(c.started_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>{c.message_count}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                      {c.customer_email || '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {c.rating ? ['😞','😕','🙂','😄'][c.rating - 1] : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {c.escalated
                        ? <span className="badge badge-red">🚨 Escalated</span>
                        : <span className="badge badge-green">✓ Resolved</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
