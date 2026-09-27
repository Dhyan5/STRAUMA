import { useState } from 'react';
import './App.css';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import CaseQueue from './pages/CaseQueue';
import CaseDetailPage from './pages/CaseDetailPage';
import ChatWidget from './pages/ChatWidget';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [criticalCount, setCriticalCount] = useState(0);

  const navigateTo = (page, data) => {
    if (page === 'case-detail' && data) {
      setSelectedCaseId(data);
    }
    setCurrentPage(page);
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return (
          <Dashboard
            onNavigate={navigateTo}
            onStatsLoad={(stats) => setCriticalCount(stats.critical_count)}
          />
        );
      case 'queue':
        return <CaseQueue onSelectCase={(id) => navigateTo('case-detail', id)} />;
      case 'case-detail':
        return (
          <CaseDetailPage
            caseId={selectedCaseId}
            onBack={() => navigateTo('queue')}
          />
        );
      case 'chat':
        return <ChatWidget onCaseCreated={(id) => navigateTo('case-detail', id)} />;
      default:
        return <Dashboard onNavigate={navigateTo} onStatsLoad={() => {}} />;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar
        currentPage={currentPage}
        onNavigate={navigateTo}
        criticalCount={criticalCount}
      />
      <main className="main-content">
        {renderPage()}
      </main>
    </div>
  );
}

export default App;
