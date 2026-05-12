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
          <div title={`${hour}:00 — ${count} messages`} style={{
            width: '100%', height: Math.max(4, (count / max) * 72),
            background: 'var(--color-cta)', borderRadius: '3px 3px 0 0',
            opacity: count > 0 ? 1 : 0.15, transition: 'height 0.3s', cursor: 'default',
          }} />
          {hour % 6 === 0 && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{hour}</div>}
        </div>
      ))}
    </div>
  )
}

// Phase 2: Language mini pie/bar chart
function LanguageChart({ data }) {
  if (!data || data.length === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No language data yet</div>
  )
  const colors = [
    'var(--color-cta)',
    'var(--color-success)',
    'var(--color-warning)',
    'var(--color-danger)',
    'var(--color-secondary)',
    'var(--color-cta-hover)',
    'var(--color-muted)',
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.slice(0, 6).map(({ language, count, pct }, i) => (
        <div key={language} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ width: 70, fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', textAlign: 'right', flexShrink: 0 }}>
            {language?.toUpperCase() || '??'}
          </div>
          <div style={{ flex: 1, height: 14, background: 'var(--body-bg)', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: colors[i % colors.length], borderRadius: 999, transition: 'width 0.5s' }} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', width: 50, textAlign: 'right', flexShrink: 0 }}>
            {pct}% ({count})
          </div>
        </div>
      ))}
    </div>
  )
}

// Phase 1: Customers section
function CustomersSection() {
  const [visitors, setVisitors] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [history, setHistory] = useState(null)

  useEffect(() => {
    const params = filter === 'has_email' ? '?has_email=true' : filter === 'returning' ? '' : ''
    fetch(`/api/visitors${params}`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (filter === 'returning') {
          setVisitors(data.filter(v => v.visit_count > 1))
        } else {
          setVisitors(data)
        }
      })
      .catch(() => setVisitors([]))
      .finally(() => setLoading(false))
  }, [filter])

  const loadHistory = async (visitor) => {
    setSelected(visitor)
    setHistory(null)
    const r = await fetch(`/api/visitors/${visitor.visitor_id}/history`, { credentials: 'include' })
    const data = await r.json()
    setHistory(data)
  }

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      {/* Visitor list */}
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          {[['all', 'All'], ['returning', 'Returning'], ['has_email', 'Has Email']].map(([id, label]) => (
            <button
              key={id}
              onClick={() => { setFilter(id); setSelected(null) }}
              style={{
                padding: '4px 12px', borderRadius: 6, border: '1px solid var(--border)', cursor: 'pointer',
                background: filter === id ? 'var(--color-cta)' : 'var(--body-bg)',
                color: filter === id ? '#fff' : 'var(--text-secondary)',
                fontSize: 12, fontWeight: 500,
                transition: 'background 150ms ease, color 150ms ease',
              }}
            >{label}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading visitors...</div>
        ) : visitors.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '16px 0' }}>No visitors yet</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {visitors.slice(0, 15).map(v => (
              <div
                key={v.visitor_id}
                onClick={() => loadHistory(v)}
                style={{
                  padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                  border: `1px solid ${selected?.visitor_id === v.visitor_id ? 'var(--color-cta)' : 'var(--border)'}`,
                  background: selected?.visitor_id === v.visitor_id ? 'var(--color-cta-light)' : 'var(--color-surface)',
                  display: 'flex', gap: 10, alignItems: 'center',
                  transition: 'background 150ms ease, border-color 150ms ease',
                }}
              >
                <div style={{ fontSize: 22 }}>{v.visit_count > 1 ? '🔄' : '👤'}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>
                    {v.email || v.name || `Visitor #${v.visitor_id.slice(0, 8)}`}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {v.visit_count} visit{v.visit_count !== 1 ? 's' : ''} · Last: {new Date(v.last_seen).toLocaleDateString()}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {v.tags?.slice(0, 2).map(tag => (
                    <span key={tag} className="badge badge-blue" style={{ fontSize: 10 }}>{tag}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Visitor detail */}
      {selected && (
        <div style={{ flex: 1, borderLeft: '1px solid var(--border)', paddingLeft: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>
            {selected.email || `Visitor ${selected.visitor_id.slice(0, 8)}`}
          </div>
          {history ? (
            <>
              {history.notes && (
                <div style={{ background: 'var(--color-cta-light)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 12px', marginBottom: 12, fontSize: 13, color: 'var(--color-cta)' }}>
                  🧠 {history.notes}
                </div>
              )}
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                {history.conversations?.length || 0} conversation{history.conversations?.length !== 1 ? 's' : ''}
              </div>
              {history.conversations?.slice(0, 5).map((c, i) => (
                <div key={c.id} style={{ borderRadius: 8, border: '1px solid var(--border)', marginBottom: 8, overflow: 'hidden', fontSize: 12 }}>
                  <div style={{ background: 'var(--body-bg)', padding: '6px 10px', fontWeight: 500, display: 'flex', justifyContent: 'space-between' }}>
                    <span>Conversation #{i + 1}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{new Date(c.started_at).toLocaleDateString()}</span>
                  </div>
                  <div style={{ padding: '8px 10px', maxHeight: 100, overflow: 'auto' }}>
                    {c.messages?.slice(0, 4).map((m, j) => (
                      <div key={j} style={{ marginBottom: 4, color: m.role === 'user' ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        <strong>{m.role === 'user' ? '👤' : '🤖'}</strong> {m.content.slice(0, 80)}{m.content.length > 80 ? '...' : ''}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading history...</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AnalyticsDashboard() {
  const [summary, setSummary] = useState(null)
  const [convos, setConvos] = useState([])
  const [topQ, setTopQ] = useState([])
  const [hourly, setHourly] = useState([])
  const [languages, setLanguages] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeSection, setActiveSection] = useState('overview')

  const load = () => {
    setLoading(true)
    const opts = { credentials: 'include' }
    Promise.all([
      fetch('/api/analytics/summary', opts).then(r => r.json()),
      fetch('/api/analytics/conversations?per_page=20', opts).then(r => r.json()),
      fetch('/api/analytics/top-questions', opts).then(r => r.json()),
      fetch('/api/analytics/hourly', opts).then(r => r.json()),
      fetch('/api/analytics/languages', opts).then(r => r.json()),
    ]).then(([s, c, q, h, l]) => {
      setSummary(s)
      setConvos(c.conversations || [])
      setTopQ(q)
      setHourly(h)
      setLanguages(l)
    }).catch(() => {}).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const exportCsv = () => window.open('/api/analytics/export', '_blank')

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
      Loading analytics...
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Conversations" value={summary?.total_conversations} icon="💬" />
        <StatCard label="Messages" value={summary?.total_messages} icon="📨" />
        <StatCard
          label="Auto-Reply Rate" icon="⚡"
          value={summary ? `${summary.auto_reply_rate}%` : null}
          sub={summary ? `${summary.auto_reply_count} instant replies` : null}
          accent="var(--color-success)"
        />
        <StatCard
          label="Avg Rating" icon="⭐"
          value={summary?.avg_rating ? `${summary.avg_rating}/4` : 'N/A'}
          sub={`Resolution: ${summary?.resolution_rate ?? 0}%`}
          accent="var(--color-warning)"
        />
      </div>

      {/* Phase 1+3+4 extra stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <StatCard
          label="Returning Visitors" icon="🧠"
          value={summary?.returning_visitors ?? 0}
          sub={`of ${summary?.total_visitors ?? 0} total visitors`}
          accent="var(--color-cta)"
        />
        <StatCard
          label="Leads Captured" icon="🎯"
          value={summary?.total_leads ?? 0}
          sub="from sales agent"
          accent="var(--color-warning)"
        />
        <StatCard
          label="Voice Messages" icon="🎤"
          value={summary?.voice_messages ?? 0}
          sub={summary?.voice_rate ? `${summary.voice_rate}% of messages` : null}
          accent="var(--color-cta-hover)"
        />
      </div>

      {/* Savings Banner */}
      {summary?.estimated_savings > 0 && (
        <div style={{
          background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
          border: '1px solid #BBF7D0', borderRadius: 'var(--radius)', padding: '16px 20px',
          display: 'flex', alignItems: 'center', gap: 16,
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

      {/* Section nav */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid var(--border)', paddingBottom: 0 }}>
        {[['overview', '📊 Overview'], ['customers', '🧠 Customers'], ['languages', '🌍 Languages']].map(([id, label]) => (
          <button key={id} onClick={() => setActiveSection(id)} style={{
            padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer',
            fontWeight: 500, fontSize: 14,
            color: activeSection === id ? 'var(--color-cta)' : 'var(--text-secondary)',
            borderBottom: `2px solid ${activeSection === id ? 'var(--color-cta)' : 'transparent'}`,
            marginBottom: -2,
            transition: 'color 150ms ease, border-color 150ms ease',
          }}>{label}</button>
        ))}
      </div>

      {/* Overview Section */}
      {activeSection === 'overview' && (
        <>
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
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', width: 20, textAlign: 'right', flexShrink: 0 }}>#{i + 1}</span>
                      <div style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.question}</div>
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
                        <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{c.session_id?.slice(0, 8)}...</td>
                        <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>{c.started_at ? new Date(c.started_at).toLocaleString() : '—'}</td>
                        <td style={{ padding: '10px 12px' }}>{c.message_count}</td>
                        <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>{c.customer_email || '—'}</td>
                        <td style={{ padding: '10px 12px' }}>{c.rating ? ['😞','😕','🙂','😄'][c.rating - 1] : '—'}</td>
                        <td style={{ padding: '10px 12px' }}>
                          {c.escalated
                            ? <span className="badge badge-red">🚨 Escalated</span>
                            : <span className="badge badge-green">✓ Resolved</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Phase 1: Customers Section */}
      {activeSection === 'customers' && (
        <div className="card">
          <h3 className="section-title">Customer Memory</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
            Click a visitor to see their full conversation history and AI-generated interest summary.
          </p>
          <CustomersSection />
        </div>
      )}

      {/* Phase 2: Languages Section */}
      {activeSection === 'languages' && (
        <div className="card">
          <h3 className="section-title">Language Distribution</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
            Languages detected in customer messages. One chatbot — every language, automatically.
          </p>
          <LanguageChart data={languages} />
          {languages.length > 0 && (
            <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>
              {languages.length} language{languages.length !== 1 ? 's' : ''} detected across all conversations
            </div>
          )}
        </div>
      )}
    </div>
  )
}
