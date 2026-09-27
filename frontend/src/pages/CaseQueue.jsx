import { useState, useEffect } from 'react';
import { Filter, ArrowUpDown, RefreshCw } from 'lucide-react';
import { getCases } from '../api';

export default function CaseQueue({ onSelectCase }) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [riskFilter, setRiskFilter] = useState(null);
  const [sortBy, setSortBy] = useState('svi');

  useEffect(() => {
    loadCases();
  }, [riskFilter, sortBy]);

  async function loadCases() {
    setLoading(true);
    try {
      const data = await getCases({
        risk: riskFilter,
        sort_by: sortBy,
        limit: 50,
      });
      setCases(data);
    } catch (err) {
      console.error('Failed to load cases:', err);
    } finally {
      setLoading(false);
    }
  }

  const riskFilters = [
    { value: null, label: 'All' },
    { value: 'critical', label: 'Critical' },
    { value: 'high', label: 'High' },
    { value: 'moderate', label: 'Moderate' },
    { value: 'low', label: 'Low' },
  ];

  return (
    <div>
      <div className="page-header">
        <h2>Case Triage Queue</h2>
        <p>Cases sorted by Stress Vulnerability Index — highest risk receives attention first</p>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <Filter size={14} style={{ color: 'var(--text-muted)' }} />
        {riskFilters.map((f) => (
          <button
            key={f.label}
            className={`filter-chip ${riskFilter === f.value ? `active ${f.value || ''}` : ''}`}
            onClick={() => setRiskFilter(f.value)}
          >
            {f.label}
            {f.value && (
              <span style={{ fontWeight: 700 }}>
                {cases.filter(c => c.risk_category === f.value).length || ''}
              </span>
            )}
          </button>
        ))}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setSortBy(sortBy === 'svi' ? 'date' : 'svi')}>
            <ArrowUpDown size={14} />
            {sortBy === 'svi' ? 'By SVI' : 'By Date'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={loadCases}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {/* Queue Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div className="loading-spinner"><div className="spinner" /></div>
        ) : cases.length === 0 ? (
          <div className="empty-state">
            <h3>No cases found</h3>
            <p>{riskFilter ? `No ${riskFilter} risk cases` : 'No cases in the system yet'}</p>
          </div>
        ) : (
          <table className="case-queue">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>SVI Score</th>
                <th>Risk Level</th>
                <th>Channel</th>
                <th>Language</th>
                <th>Assigned To</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} onClick={() => onSelectCase(c.id)}>
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
                      {c.hard_override && <span className="override-indicator">⚠ OVERRIDE </span>}
                      {c.risk_category || 'pending'}
                    </span>
                  </td>
                  <td><span className="case-channel">{c.channel}</span></td>
                  <td><span className="case-language">{langName(c.language_detected)}</span></td>
                  <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {c.assignee_name || <span style={{ color: 'var(--text-muted)' }}>Unassigned</span>}
                  </td>
                  <td style={{ fontSize: 12 }}>
                    <span style={{
                      padding: '3px 8px',
                      borderRadius: 6,
                      background: 'var(--bg-input)',
                      color: 'var(--text-secondary)',
                      fontSize: 11,
                      fontWeight: 500,
                    }}>
                      {c.status}
                    </span>
                  </td>
                  <td className="case-time">
                    {formatTime(c.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function langName(code) {
  const names = { en: 'EN', hi: 'HI', te: 'TE', ta: 'TA', mr: 'MR', bn: 'BN' };
  return names[code] || code || '—';
}

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
