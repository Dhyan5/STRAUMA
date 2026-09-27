import { useState, useEffect } from 'react';
import {
  ArrowLeft, AlertOctagon, Brain, MessageSquare, Mic, Activity,
  Clock, FileText, Shield, CheckCircle, Eye
} from 'lucide-react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer
} from 'recharts';
import { getCaseDetail, getCaseAudit } from '../api';

const CRITICAL_CATEGORIES = new Set(['self_harm', 'immediate_threat']);

export default function CaseDetailPage({ caseId, onBack }) {
  const [caseData, setCaseData] = useState(null);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    if (caseId) loadCase();
  }, [caseId]);

  async function loadCase() {
    setLoading(true);
    try {
      const [detail, auditLog] = await Promise.all([
        getCaseDetail(caseId),
        getCaseAudit(caseId).catch(() => []),
      ]);
      setCaseData(detail);
      setAudit(auditLog);
    } catch (err) {
      console.error('Failed to load case:', err);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div className="loading-spinner"><div className="spinner" /></div>;
  }

  if (!caseData) {
    return (
      <div className="empty-state">
        <h3>Case not found</h3>
        <button className="btn btn-ghost" onClick={onBack}>← Back to Queue</button>
      </div>
    );
  }

  const assessment = caseData.assessments?.[0];
  const riskClass = caseData.risk_category || '';

  // Radar chart data for sub-scores
  const radarData = assessment ? [
    { metric: 'Text Sentiment', value: (assessment.text_sentiment_score * 100).toFixed(0), fullMark: 100 },
    { metric: 'Keyword Density', value: (assessment.keyword_density_score * 100).toFixed(0), fullMark: 100 },
    { metric: 'Voice Prosody', value: ((assessment.voice_prosody_score || 0) * 100).toFixed(0), fullMark: 100 },
    { metric: 'Interaction', value: (assessment.interaction_pattern_score * 100).toFixed(0), fullMark: 100 },
  ] : [];

  // Highlight keywords in transcript
  function highlightText(text) {
    if (!text || !assessment?.triggered_keywords?.length) return text;

    const keywords = assessment.triggered_keywords.map(kw => kw.term);
    // Sort by length (longest first) to avoid partial matches
    keywords.sort((a, b) => b.length - a.length);

    let result = text;
    keywords.forEach(kw => {
      const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escaped})`, 'gi');
      const kwData = assessment.triggered_keywords.find(k => k.term === kw);
      const cls = kwData?.is_critical_override ? 'text-highlight' :
                  CRITICAL_CATEGORIES.has(kwData?.category) ? 'text-highlight' :
                  'text-highlight warning';
      result = result.replace(regex, `<span class="${cls}" title="${kwData?.category}">$1</span>`);
    });

    return result;
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700 }}>Case {caseData.id.slice(0, 8)}</h2>
            <span className={`risk-badge ${riskClass}`}>
              {caseData.hard_override && '⚠ OVERRIDE — '}
              {riskClass.toUpperCase() || 'PENDING'}
            </span>
            <span className="case-channel">{caseData.channel}</span>
            <span className="case-language">{langFull(caseData.language_detected)}</span>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Created {new Date(caseData.created_at).toLocaleString('en-IN')}
            {caseData.assignee_name && ` · Assigned to ${caseData.assignee_name}`}
          </p>
        </div>
      </div>

      {/* Override Alert */}
      {caseData.hard_override && assessment?.override_reason && (
        <div style={{
          background: 'var(--risk-critical-bg)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          marginBottom: 20,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 12,
        }}>
          <AlertOctagon size={20} color="var(--risk-critical)" style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--risk-critical)', marginBottom: 4 }}>
              CRITICAL SAFETY OVERRIDE ACTIVE
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {assessment.override_reason}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        {['overview', 'transcript', 'audit'].map(tab => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'overview' && <><Brain size={14} style={{ marginRight: 6 }} />Assessment</>}
            {tab === 'transcript' && <><FileText size={14} style={{ marginRight: 6 }} />Transcript</>}
            {tab === 'audit' && <><Eye size={14} style={{ marginRight: 6 }} />Audit Log</>}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div className="case-detail-grid">
          <div>
            {/* SVI Score Hero */}
            <div className="card" style={{ marginBottom: 20, textAlign: 'center', padding: 32 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
                Stress Vulnerability Index
              </div>
              <div className={`svi-score ${riskClass}`} style={{ fontSize: 56, fontWeight: 900 }}>
                {caseData.svi_score != null ? caseData.svi_score.toFixed(1) : '—'}
              </div>
              <div style={{ marginTop: 12, width: '100%', height: 8, background: 'var(--bg-input)', borderRadius: 4, overflow: 'hidden' }}>
                <div
                  className={`svi-bar-fill ${riskClass}`}
                  style={{ width: `${caseData.svi_score || 0}%`, height: '100%' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
                <span>0 — Low</span>
                <span>30 — Moderate</span>
                <span>55 — High</span>
                <span>80 — Critical</span>
              </div>
            </div>

            {/* Sub-Scores */}
            <div className="card" style={{ marginBottom: 20 }}>
              <div className="card-header">
                <div className="card-title">Score Breakdown</div>
                <div className="card-subtitle">Each component contributing to the SVI</div>
              </div>
              <div className="sub-scores-grid">
                <SubScoreCard
                  icon={<MessageSquare size={16} />}
                  label="Text Sentiment"
                  score={assessment?.text_sentiment_score || 0}
                  weight="30%"
                  color="var(--accent-primary)"
                />
                <SubScoreCard
                  icon={<Shield size={16} />}
                  label="Keyword Density"
                  score={assessment?.keyword_density_score || 0}
                  weight="30%"
                  color="var(--risk-high)"
                />
                <SubScoreCard
                  icon={<Mic size={16} />}
                  label="Voice Prosody"
                  score={assessment?.voice_prosody_score}
                  weight="25%"
                  color="var(--accent-secondary)"
                  noAudio={assessment?.voice_prosody_score == null}
                />
                <SubScoreCard
                  icon={<Activity size={16} />}
                  label="Interaction Pattern"
                  score={assessment?.interaction_pattern_score || 0}
                  weight="15%"
                  color="var(--risk-moderate)"
                />
              </div>
            </div>

            {/* Triggered Keywords */}
            {assessment?.triggered_keywords?.length > 0 && (
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <div className="card-title">Triggered Keywords</div>
                  <div className="card-subtitle">
                    {assessment.triggered_keywords.length} keyword(s) detected across {
                      new Set(assessment.triggered_keywords.map(k => k.category)).size
                    } categories
                  </div>
                </div>
                <div className="keyword-tags">
                  {assessment.triggered_keywords.map((kw, i) => (
                    <span
                      key={i}
                      className={`keyword-tag ${
                        kw.is_critical_override ? 'critical-kw' :
                        CRITICAL_CATEGORIES.has(kw.category) ? 'critical-kw' :
                        'warning-kw'
                      }`}
                      title={`Category: ${kw.category} | Language: ${kw.language}`}
                    >
                      {kw.is_critical_override && '⚠ '}
                      {kw.term}
                      <span style={{ opacity: 0.7, fontSize: 10 }}>({kw.category})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Sidebar */}
          <div>
            {/* Radar Chart */}
            {assessment && (
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-title" style={{ marginBottom: 16 }}>Distress Profile</div>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                      <PolarGrid stroke="rgba(148,163,184,0.1)" />
                      <PolarAngleAxis
                        dataKey="metric"
                        tick={{ fill: '#94a3b8', fontSize: 10 }}
                      />
                      <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={{ fill: '#64748b', fontSize: 9 }}
                      />
                      <Radar
                        dataKey="value"
                        stroke="#6366f1"
                        fill="#6366f1"
                        fillOpacity={0.25}
                        strokeWidth={2}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Recommendations */}
            {caseData.recommendations?.length > 0 && (
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <div className="card-title">Recommended Actions</div>
                </div>
                <ul className="recommendation-list">
                  {caseData.recommendations.map((action, i) => (
                    <li
                      key={i}
                      className={`recommendation-item ${action.includes('EMERGENCY') || action.includes('Real-time') ? 'urgent' : ''}`}
                    >
                      <div className="recommendation-bullet" />
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Case Info */}
            <div className="card">
              <div className="card-title" style={{ marginBottom: 16 }}>Case Information</div>
              <InfoRow label="Case ID" value={caseData.id} mono />
              <InfoRow label="Channel" value={caseData.channel} />
              <InfoRow label="Language" value={langFull(caseData.language_detected)} />
              <InfoRow label="Status" value={caseData.status} />
              <InfoRow label="Consent" value={caseData.consent_given ? '✓ Given' : '✗ Not given'} />
              <InfoRow label="Assigned" value={caseData.assignee_name || 'Unassigned'} />
              <InfoRow label="Created" value={new Date(caseData.created_at).toLocaleString('en-IN')} />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'transcript' && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Victim Statement / Transcript</div>
            <div className="card-subtitle">
              Keywords highlighted — hover for category
            </div>
          </div>
          <div
            className="transcript-viewer"
            dangerouslySetInnerHTML={{
              __html: highlightText(caseData.raw_text || caseData.transcript || 'No text content available')
            }}
          />
        </div>
      )}

      {activeTab === 'audit' && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Audit Trail</div>
            <div className="card-subtitle">Complete log of all actions on this case</div>
          </div>
          {audit.length > 0 ? (
            <div className="audit-timeline">
              {audit.map((entry) => (
                <div className="audit-entry" key={entry.id}>
                  <div className="audit-action">{formatAuditAction(entry.action)}</div>
                  <div className="audit-time">
                    {new Date(entry.timestamp).toLocaleString('en-IN')}
                    {entry.user_id && ` · User ${entry.user_id.slice(0, 8)}`}
                  </div>
                  {entry.details && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {Object.entries(entry.details).map(([k, v]) => (
                        <span key={k} style={{ marginRight: 12 }}>
                          {k}: <strong>{String(v)}</strong>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state"><p>No audit entries</p></div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SubScoreCard({ icon, label, score, weight, color, noAudio }) {
  const displayScore = noAudio ? null : score;
  const percentage = displayScore != null ? (displayScore * 100).toFixed(0) : null;

  return (
    <div className="sub-score-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="sub-score-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {icon} {label}
        </div>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>wt: {weight}</span>
      </div>
      <div className="sub-score-value" style={{ color }}>
        {percentage != null ? `${percentage}%` : 'N/A'}
      </div>
      {noAudio && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
          No audio input provided
        </div>
      )}
      {percentage != null && (
        <div className="sub-score-bar">
          <div className="sub-score-bar-fill" style={{ width: `${percentage}%`, background: color }} />
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value, mono }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '8px 0', borderBottom: '1px solid var(--border-subtle)',
      fontSize: 12,
    }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{
        color: 'var(--text-secondary)',
        fontFamily: mono ? "'SF Mono', 'Fira Code', monospace" : 'inherit',
        fontSize: mono ? 11 : 12,
        maxWidth: 200,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}>
        {value}
      </span>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function langFull(code) {
  const names = { en: 'English', hi: 'Hindi', te: 'Telugu', ta: 'Tamil', mr: 'Marathi', bn: 'Bengali' };
  return names[code] || code || '—';
}

function formatAuditAction(action) {
  const map = {
    CASE_CREATED: '📋 Case Created',
    ASSESSMENT_COMPLETED: '🧠 Assessment Completed',
    CASE_VIEWED: '👁 Case Viewed',
    STATUS_CHANGED: '🔄 Status Changed',
    RECOMMENDATION_UPDATED: '📝 Recommendation Updated',
  };
  return map[action] || action;
}
