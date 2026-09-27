import { useState, useRef, useEffect } from 'react';
import { Send, Shield, CheckCircle, AlertTriangle, Mic } from 'lucide-react';
import { createCase, assessCase } from '../api';

const CONSENT_TEXT = {
  en: {
    title: 'Before We Begin',
    subtitle: 'Your safety and privacy matter to us',
    intro: 'This assessment tool helps us understand your situation so we can connect you with the right support faster. Here\'s what you should know:',
    points: [
      'Your conversation will be analyzed to assess the urgency of your situation',
      'The analysis looks at the nature and severity of what you describe',
      'Your identity is protected — only your case ID is used in the assessment',
      'A trained counsellor will review your case based on the assessment',
      'Audio recordings (if provided) are automatically deleted after 30 days',
      'You can opt out at any time — your complaint can still be filed normally',
    ],
    consent_label: 'I understand and consent to the assessment',
    proceed: 'Begin Assessment',
    skip: 'File complaint without assessment',
  },
  hi: {
    title: 'शुरू करने से पहले',
    subtitle: 'आपकी सुरक्षा और गोपनीयता हमारे लिए महत्वपूर्ण है',
    intro: 'यह मूल्यांकन उपकरण हमें आपकी स्थिति को समझने में मदद करता है ताकि हम आपको सही सहायता से तेज़ी से जोड़ सकें।',
    points: [
      'आपकी बातचीत का विश्लेषण आपकी स्थिति की तात्कालिकता का आकलन करने के लिए किया जाएगा',
      'विश्लेषण आपके द्वारा बताई गई बात की प्रकृति और गंभीरता को देखता है',
      'आपकी पहचान सुरक्षित है — मूल्यांकन में केवल आपका केस आईडी उपयोग किया जाता है',
      'एक प्रशिक्षित परामर्शदाता मूल्यांकन के आधार पर आपके मामले की समीक्षा करेगा',
      'ऑडियो रिकॉर्डिंग 30 दिनों के बाद स्वचालित रूप से हटा दी जाती है',
      'आप किसी भी समय ऑप्ट आउट कर सकते हैं',
    ],
    consent_label: 'मैं समझता/समझती हूं और मूल्यांकन के लिए सहमत हूं',
    proceed: 'मूल्यांकन शुरू करें',
    skip: 'मूल्यांकन के बिना शिकायत दर्ज करें',
  },
};

export default function ChatWidget({ onCaseCreated }) {
  const [phase, setPhase] = useState('consent'); // consent | chat | assessed
  const [consentGiven, setConsentGiven] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [assessmentResult, setAssessmentResult] = useState(null);
  const [caseId, setCaseId] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleConsent() {
    if (!consentGiven) return;
    setPhase('chat');
    setMessages([
      {
        type: 'system',
        text: 'Thank you. You can now describe your situation in your own words, in any language you\'re comfortable with. Take your time.',
      },
      {
        type: 'system',
        text: 'आप अपनी भाषा में बात कर सकते हैं — हिंदी, तेलुगु, तमिल, मराठी, बंगाली, या अंग्रेज़ी।',
      },
    ]);
  }

  async function handleSend() {
    if (!input.trim() || loading) return;

    const userText = input.trim();
    setInput('');
    setMessages(prev => [...prev, { type: 'user', text: userText }]);
    setLoading(true);

    try {
      // Create case
      const caseRes = await createCase({
        text: userText,
        channel: 'chat',
        consent_given: true,
      });

      setCaseId(caseRes.case_id);

      setMessages(prev => [...prev, {
        type: 'system',
        text: `Case registered (ID: ${caseRes.case_id.slice(0, 8)}). Language detected: ${langFull(caseRes.language_detected)}. Running assessment...`,
      }]);

      // Run assessment
      const assessRes = await assessCase(caseRes.case_id);
      setAssessmentResult(assessRes);

      // Show result message
      const riskMessages = {
        critical: '🚨 Your case has been flagged as CRITICAL priority. A counsellor and emergency services are being notified immediately. If you are in immediate danger, please call 112.',
        high: '⚠️ Your case has been marked as HIGH priority. A counsellor will be assigned to you shortly. Legal aid and medical referral information will be shared.',
        moderate: 'Your case has been recorded with MODERATE priority. A counsellor will call you back within 24 hours. We are sending you legal aid information.',
        low: 'Your case has been logged. A follow-up call will be scheduled within 48 hours. Thank you for reaching out.',
      };

      setMessages(prev => [
        ...prev,
        {
          type: assessRes.risk_category === 'critical' ? 'alert' : 'system',
          text: riskMessages[assessRes.risk_category] || 'Assessment complete.',
        },
      ]);

      if (assessRes.risk_category === 'critical' || assessRes.risk_category === 'high') {
        setMessages(prev => [...prev, {
          type: 'system',
          text: `Emergency Helplines:\n• National Emergency: 112\n• Women Helpline: 181\n• SC/ST Helpline: 14566\n• Police: 100`,
        }]);
      }

      setPhase('assessed');
    } catch (err) {
      setMessages(prev => [...prev, {
        type: 'system',
        text: `Error: ${err.message}. Please try again or call 14566 directly.`,
      }]);
    } finally {
      setLoading(false);
    }
  }

  // ─── Consent Phase ─────────────────────────────────────────────────────────
  if (phase === 'consent') {
    const t = CONSENT_TEXT.en;
    return (
      <div className="chat-container">
        <div className="page-header">
          <h2>Report an Incident</h2>
          <p>Describe your situation — we'll connect you with the right help</p>
        </div>

        <div className="consent-card">
          <Shield size={40} color="var(--accent-primary)" style={{ marginBottom: 16 }} />
          <h3>{t.title}</h3>
          <p style={{ fontWeight: 500, marginBottom: 4 }}>{t.subtitle}</p>
          <p>{t.intro}</p>

          <ul className="consent-points">
            {t.points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>

          {/* Hindi translation */}
          <div style={{
            textAlign: 'left', padding: 16, background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-md)', marginBottom: 20,
            fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.8,
          }}>
            <strong style={{ color: 'var(--text-secondary)' }}>हिंदी में:</strong><br />
            {CONSENT_TEXT.hi.intro}
          </div>

          <label style={{
            display: 'flex', alignItems: 'center', gap: 10,
            cursor: 'pointer', padding: '12px 16px',
            background: consentGiven ? 'var(--accent-primary-glow)' : 'var(--bg-input)',
            borderRadius: 'var(--radius-md)',
            border: `1px solid ${consentGiven ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
            transition: 'all 0.2s',
            marginBottom: 20,
          }}>
            <input
              type="checkbox"
              checked={consentGiven}
              onChange={(e) => setConsentGiven(e.target.checked)}
              style={{ width: 18, height: 18, accentColor: 'var(--accent-primary)' }}
            />
            <span style={{ fontSize: 13, fontWeight: 500 }}>{t.consent_label}</span>
          </label>

          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <button
              className="btn btn-primary btn-lg"
              disabled={!consentGiven}
              onClick={handleConsent}
            >
              <CheckCircle size={18} />
              {t.proceed}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ─── Chat Phase ────────────────────────────────────────────────────────────
  return (
    <div className="chat-container">
      <div className="page-header">
        <h2>Describe Your Situation</h2>
        <p>Type in any language — your message will be analyzed to prioritize your case</p>
      </div>

      <div className="card">
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.type}`}>
              {msg.text}
            </div>
          ))}
          {loading && (
            <div className="chat-bubble system" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              Analyzing your message...
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {phase === 'chat' && (
          <div className="chat-input-area">
            <textarea
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Describe what happened... अपनी बात बताइए..."
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={2}
            />
            <button
              className="btn btn-primary"
              onClick={handleSend}
              disabled={!input.trim() || loading}
              style={{ alignSelf: 'flex-end' }}
            >
              <Send size={18} />
            </button>
          </div>
        )}

        {phase === 'assessed' && assessmentResult && (
          <div style={{ padding: '16px 0', borderTop: '1px solid var(--border-subtle)', textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
              Assessment complete — SVI: {assessmentResult.svi_score.toFixed(1)} | Risk: {assessmentResult.risk_category.toUpperCase()}
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button className="btn btn-primary btn-sm" onClick={() => onCaseCreated(caseId)}>
                View Case Details
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => {
                setPhase('chat');
                setAssessmentResult(null);
                setMessages(prev => [...prev, { type: 'system', text: 'You can provide additional information if needed.' }]);
              }}>
                Add More Information
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function langFull(code) {
  const names = { en: 'English', hi: 'Hindi', te: 'Telugu', ta: 'Tamil', mr: 'Marathi', bn: 'Bengali' };
  return names[code] || code || 'Auto';
}
