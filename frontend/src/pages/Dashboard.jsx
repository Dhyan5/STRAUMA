import { useState, useEffect } from 'react';
import {
  AlertTriangle, AlertOctagon, ShieldAlert, ShieldCheck,
  Users, Activity, TrendingUp, Clock
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid
} from 'recharts';
import { getDashboardStats, getCases } from '../api';

const RISK_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  moderate: '#eab308',
  low: '#22c55e',
};

export default function Dashboard({ onNavigate, onStatsLoad }) {
  const [stats, setStats] = useState(null);
  const [recentCases, setRecentCases] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [statsData, casesData] = await Promise.all([
        getDashboardStats(),
        getCases({ limit: 5, sort_by: 'svi' }),
      ]);
      setStats(statsData);
      setRecentCases(casesData);
      onStatsLoad(statsData);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="empty-state">
        <AlertTriangle size={48} />
        <h3>Unable to connect to backend</h3>
        <p>Make sure the FastAPI server is running on port 8000</p>
      </div>
    );
  }

  const pieData = stats.risk_distribution.filter(d => d.count > 0);

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Real-time overview of the Stress Vulnerability Index triage system</p>
      </div>

      {/* Stat Cards */}
      <div className="stats-grid">
        <div className="stat-card critical">
          <div className="stat-icon critical">
            <AlertOctagon size={22} />
          </div>
          <div className="stat-info">
            <h3 style={{ color: 'var(--risk-critical)' }}>{stats.critical_count}</h3>
            <p>Critical Cases</p>
          </div>
        </div>

        <div className="stat-card high">
          <div className="stat-icon high">
            <ShieldAlert size={22} />
          </div>
          <div className="stat-info">
            <h3 style={{ color: 'var(--risk-high)' }}>{stats.high_count}</h3>
            <p>High Risk</p>
          </div>
        </div>

        <div className="stat-card moderate">
          <div className="stat-icon moderate">
            <AlertTriangle size={22} />
          </div>
          <div className="stat-info">
            <h3 style={{ color: 'var(--risk-moderate)' }}>{stats.moderate_count}</h3>
            <p>Moderate Risk</p>
          </div>
        </div>

        <div className="stat-card low">
          <div className="stat-icon low">
            <ShieldCheck size={22} />
          </div>
          <div className="stat-info">
            <h3 style={{ color: 'var(--risk-low)' }}>{stats.low_count}</h3>
            <p>Low Risk</p>
          </div>
        </div>

        <div className="stat-card accent">
          <div className="stat-icon accent">
            <Activity size={22} />
          </div>
          <div className="stat-info">
            <h3>{stats.avg_svi.toFixed(1)}</h3>
            <p>Average SVI</p>
          </div>
        </div>

        <div className="stat-card accent">
          <div className="stat-icon accent">
            <Users size={22} />
          </div>
          <div className="stat-info">
            <h3>{stats.unassigned_count}</h3>
            <p>Unassigned</p>
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
        {/* Risk Distribution Pie */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Risk Distribution</div>
              <div className="card-subtitle">Current case breakdown by severity</div>
            </div>
          </div>
          <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={95}
                    paddingAngle={3}
                    dataKey="count"
                    nameKey="category"
                    stroke="none"
                  >
                    {pieData.map((entry) => (
                      <Cell
                        key={entry.category}
                        fill={RISK_COLORS[entry.category] || '#6b7280'}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: '#1a1f35',
                      border: '1px solid rgba(148,163,184,0.15)',
                      borderRadius: 10,
                      color: '#f1f5f9',
                      fontSize: 13,
                    }}
                    formatter={(value, name) => [value, name.charAt(0).toUpperCase() + name.slice(1)]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state"><p>No case data yet</p></div>
            )}
            {pieData.length > 0 && (
              <div style={{ position: 'absolute', textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)' }}>
                  {stats.total_cases}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Total</div>
              </div>
            )}
          </div>
          {/* Legend */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 8 }}>
            {Object.entries(RISK_COLORS).map(([label, color]) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
                {label.charAt(0).toUpperCase() + label.slice(1)}
              </div>
            ))}
          </div>
        </div>

        {/* Weekly Trend */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">7-Day Trend</div>
              <div className="card-subtitle">New cases received per day</div>
            </div>
          </div>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.recent_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d) => new Date(d).toLocaleDateString('en', { weekday: 'short' })}
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                />
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1a1f35',
                    border: '1px solid rgba(148,163,184,0.15)',
                    borderRadius: 10,
                    color: '#f1f5f9',
                    fontSize: 13,
                  }}
                />
                <Bar
                  dataKey="cases"
                  fill="url(#barGradient)"
                  radius={[6, 6, 0, 0]}
                  maxBarSize={40}
                />
                <defs>
                  <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#8b5cf6" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Critical Cases Alert */}
      <div className="card" style={{ marginBottom: 28 }}>
        <div className="card-header">
          <div>
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertOctagon size={16} color="var(--risk-critical)" />
              Highest Priority Cases
            </div>
            <div className="card-subtitle">Sorted by Stress Vulnerability Index — highest risk first</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => onNavigate('queue')}>
            View All →
          </button>
        </div>

        {recentCases.length > 0 ? (
          <table className="case-queue">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>SVI Score</th>
                <th>Risk</th>
                <th>Channel</th>
                <th>Language</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {recentCases.map((c) => (
                <tr key={c.id} onClick={() => onNavigate('case-detail', c.id)}>
                  <td><span className="case-id">{c.id.slice(0, 8)}</span></td>
                  <td>
                    <div className="svi-gauge">
                      <span className={`svi-score ${c.risk_category || ''}`}>
                        {c.svi_score != null ? c.svi_score.toFixed(1) : '—'}
                      </span>
                      <div className="svi-bar">
                        <div
                          className={`svi-bar-fill ${c.risk_category || ''}`}
                          style={{ width: `${c.svi_score || 0}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className={`risk-badge ${c.risk_category || ''}`}>
                      {c.hard_override && '⚠ '}
                      {c.risk_category || 'pending'}
                    </span>
                  </td>
                  <td><span className="case-channel">{c.channel}</span></td>
                  <td><span className="case-language">{c.language_detected}</span></td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{c.status}</td>
                  <td className="case-time">
                    {new Date(c.created_at).toLocaleString('en-IN', {
                      hour: '2-digit', minute: '2-digit',
                      day: 'numeric', month: 'short',
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <ShieldCheck size={40} />
            <h3>No cases yet</h3>
            <p>Use the chat widget to submit a case</p>
          </div>
        )}
      </div>
    </div>
  );
}
