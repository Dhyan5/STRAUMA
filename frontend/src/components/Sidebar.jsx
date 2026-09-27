import { Shield, LayoutDashboard, ListOrdered, MessageSquare, Settings, FileText } from 'lucide-react';

export default function Sidebar({ currentPage, onNavigate, criticalCount }) {
  const navItems = [
    {
      section: 'Overview',
      items: [
        { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { id: 'queue', label: 'Case Queue', icon: ListOrdered, badge: criticalCount > 0 ? criticalCount : null },
      ],
    },
    {
      section: 'Interact',
      items: [
        { id: 'chat', label: 'Victim Chat', icon: MessageSquare },
      ],
    },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <Shield size={22} color="white" />
          </div>
          <div className="sidebar-logo-text">
            <h1>NHAA STRAUMA</h1>
            <p>Assessment Module</p>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((section) => (
          <div key={section.section}>
            <div className="nav-section-label">{section.section}</div>
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.id}
                  className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
                  onClick={() => onNavigate(item.id)}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                  {item.badge && <span className="nav-badge">{item.badge}</span>}
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      <div style={{
        padding: '16px 20px',
        borderTop: '1px solid var(--border-subtle)',
        fontSize: '11px',
        color: 'var(--text-muted)',
        lineHeight: 1.5
      }}>
        <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
          NHAA Helpline 14566
        </div>
        <div>SC/ST Prevention of Atrocities</div>
        <div style={{ marginTop: 8, opacity: 0.6 }}>Prototype v1.0</div>
      </div>
    </aside>
  );
}
