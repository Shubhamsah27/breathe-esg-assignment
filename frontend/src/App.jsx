import React, { useState, useEffect } from 'react';

// Common global API base
let tempApiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1';
if (tempApiBase && !tempApiBase.startsWith('http://') && !tempApiBase.startsWith('https://')) {
  tempApiBase = `https://${tempApiBase}/api/v1`;
}
const API_BASE = tempApiBase;

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [seeded, setSeeded] = useState(false);
  const [orgId, setOrgId] = useState(null);
  const [sourceMap, setSourceMap] = useState({});
  const [loading, setLoading] = useState(false);

  // Data States
  const [analytics, setAnalytics] = useState({
    total_co2e_kg: 0,
    total_records: 0,
    scopes: { 'Scope 1': 0, 'Scope 2': 0, 'Scope 3': 0 },
    activities: {},
    statuses: {},
    monthly_emissions: []
  });
  const [records, setRecords] = useState([]);
  const [selectedRecordIds, setSelectedRecordIds] = useState([]);
  
  // Filters
  const [filterScope, setFilterScope] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Drawer/Modal States
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [correctionQty, setCorrectionQty] = useState('');
  const [correctionComment, setCorrectionComment] = useState('');
  const [suspiciousReasonInput, setSuspiciousReasonInput] = useState('');
  const [showSuspiciousForm, setShowSuspiciousForm] = useState(false);

  // JSON Input console state
  const [jsonInput, setJsonInput] = useState(JSON.stringify(sampleTravelPayload, null, 2));

  // File Upload states
  const [sapFile, setSapFile] = useState(null);
  const [utilityFile, setUtilityFile] = useState(null);
  const [uploadMessage, setUploadMessage] = useState({ text: '', isError: false });

  // Optimization States
  const [failedRecords, setFailedRecords] = useState([]);
  const [selectedFailedRecord, setSelectedFailedRecord] = useState(null);
  const [failedRecordCorrectionData, setFailedRecordCorrectionData] = useState({});
  const [showPlantRegisterForm, setShowPlantRegisterForm] = useState(false);
  const [newPlantName, setNewPlantName] = useState('');
  const [newPlantRegion, setNewPlantRegion] = useState('DE');
  const [plantCodeToRegister, setPlantCodeToRegister] = useState('');


  // Initial Seed check
  useEffect(() => {
    // Attempt auto-connect and seed if first start
    autoSeed();
  }, []);

  useEffect(() => {
    if (seeded && orgId) {
      refreshData();
    }
  }, [seeded, orgId, filterScope, filterStatus]);

  const autoSeed = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/organizations/`);
      if (res.ok) {
        const orgs = await res.json();
        if (orgs.length > 0) {
          // Already have seeded data, let's bind
          setOrgId(orgs[0].id);
          // Fetch sources
          const srcRes = await fetch(`${API_BASE}/sources/?organization=${orgs[0].id}`);
          if (srcRes.ok) {
            const sources = await srcRes.json();
            const map = {};
            sources.forEach(s => { map[s.source_type] = s.id; });
            setSourceMap(map);
            setSeeded(true);
          }
        }
      }
      setLoading(false);
    } catch (e) {
      console.log("Could not auto-connect to backend yet. Wait for server to start.", e);
      setLoading(false);
    }
  };

  const handleSeed = async () => {
    try {
      setLoading(true);
      setUploadMessage({ text: '', isError: false });
      const res = await fetch(`${API_BASE}/seed/`, { method: 'POST' });
      if (!res.ok) throw new Error("Seeding endpoint failed");
      const data = await res.json();
      setOrgId(data.organization_id);
      setSourceMap(data.sources);
      setSeeded(true);
      setUploadMessage({ text: "Database seeded and lookup tables created successfully!", isError: false });
      setLoading(false);
    } catch (e) {
      setUploadMessage({ text: `Failed to seed database: ${e.message}. Ensure Django backend is running!`, isError: true });
      setLoading(false);
    }
  };

  const refreshData = async () => {
    if (!orgId) return;
    try {
      // 1. Fetch Analytics
      const analyRes = await fetch(`${API_BASE}/analytics/?organization=${orgId}`);
      if (analyRes.ok) {
        const data = await analyRes.json();
        setAnalytics(data);
      }
      // 2. Fetch Records
      let url = `${API_BASE}/records/?organization=${orgId}`;
      if (filterScope) url += `&scope=${filterScope}`;
      if (filterStatus) url += `&status=${filterStatus}`;
      
      const recRes = await fetch(url);
      if (recRes.ok) {
        const recs = await recRes.json();
        setRecords(recs);
      }
      // 3. Fetch Sandboxed Ingest Errors
      const rawRes = await fetch(`${API_BASE}/raw-records/?organization=${orgId}&status=FAILED_VALIDATION`);
      if (rawRes.ok) {
        const raws = await rawRes.json();
        setFailedRecords(raws);
      }
    } catch (e) {
      console.error("Error refreshing dashboard data", e);
    }
  };

  // Upload SAP file
  const handleUploadSAP = async (e) => {
    e.preventDefault();
    if (!sapFile) return;
    setLoading(true);
    setUploadMessage({ text: '', isError: false });
    
    const formData = new FormData();
    formData.append('file', sapFile);
    formData.append('source_id', sourceMap.SAP);
    formData.append('organization_id', orgId);
    
    try {
      const res = await fetch(`${API_BASE}/upload-file/`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed uploading file");
      
      setUploadMessage({ text: `SAP Export ingested! Records created: ${data.batch.summary.normalized}, Warnings: ${data.batch.summary.suspicious}, Failed validation: ${data.batch.summary.failed}`, isError: false });
      setSapFile(null);
      refreshData();
    } catch (err) {
      setUploadMessage({ text: err.message, isError: true });
    } finally {
      setLoading(false);
    }
  };

  // Upload Utility file
  const handleUploadUtility = async (e) => {
    e.preventDefault();
    if (!utilityFile) return;
    setLoading(true);
    setUploadMessage({ text: '', isError: false });
    
    const formData = new FormData();
    formData.append('file', utilityFile);
    formData.append('source_id', sourceMap.UTILITY);
    formData.append('organization_id', orgId);
    
    try {
      const res = await fetch(`${API_BASE}/upload-file/`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed uploading file");
      
      setUploadMessage({ text: `Utility billing ingested! Records split & calendar prorated. Normal entries: ${data.batch.summary.normalized}, Suspicious entries: ${data.batch.summary.suspicious}`, isError: false });
      setUtilityFile(null);
      refreshData();
    } catch (err) {
      setUploadMessage({ text: err.message, isError: true });
    } finally {
      setLoading(false);
    }
  };

  // Submit Travel JSON Payload
  const handleSubmitTravel = async () => {
    try {
      setLoading(true);
      setUploadMessage({ text: '', isError: false });
      const parsed = JSON.parse(jsonInput);
      
      const res = await fetch(`${API_BASE}/submit-travel/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: sourceMap.TRAVEL,
          organization_id: orgId,
          payload: parsed
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to submit JSON");
      
      setUploadMessage({ text: `Travel API pull simulated! Successfully ingested: ${data.batch.summary.normalized} travel records. Warnings: ${data.batch.summary.suspicious}`, isError: false });
      refreshData();
    } catch (err) {
      setUploadMessage({ text: `Ingestion Error: ${err.message}`, isError: true });
    } finally {
      setLoading(false);
    }
  };

  // Row selection handler
  const toggleRecordSelection = (id) => {
    if (selectedRecordIds.includes(id)) {
      setSelectedRecordIds(selectedRecordIds.filter(x => x !== id));
    } else {
      setSelectedRecordIds([...selectedRecordIds, id]);
    }
  };

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedRecordIds(records.map(r => r.id));
    } else {
      setSelectedRecordIds([]);
    }
  };

  // Actions
  const handleApproveSingle = async (rec) => {
    try {
      const res = await fetch(`${API_BASE}/records/${rec.id}/approve/`, { method: 'POST' });
      if (res.ok) {
        const updated = await res.json();
        setRecords(records.map(r => r.id === updated.id ? updated : r));
        if (selectedRecord && selectedRecord.id === updated.id) {
          setSelectedRecord(updated);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleFlagSuspiciousSingle = async (rec) => {
    if (!suspiciousReasonInput.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/records/${rec.id}/flag_suspicious/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: suspiciousReasonInput })
      });
      if (res.ok) {
        const updated = await res.json();
        setRecords(records.map(r => r.id === updated.id ? updated : r));
        setSelectedRecord(updated);
        setSuspiciousReasonInput('');
        setShowSuspiciousForm(false);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleBulkApprove = async () => {
    if (selectedRecordIds.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/records/bulk_approve/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_ids: selectedRecordIds, organization: orgId })
      });
      if (res.ok) {
        refreshData();
        setSelectedRecordIds([]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleBulkLock = async () => {
    if (selectedRecordIds.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/records/bulk_lock/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_ids: selectedRecordIds })
      });
      if (res.ok) {
        refreshData();
        setSelectedRecordIds([]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Submit Correction / Edit Record
  const handleCorrectionSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRecord || !correctionQty.trim() || !correctionComment.trim()) return;
    
    try {
      const res = await fetch(`${API_BASE}/records/${selectedRecord.id}/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_quantity: parseFloat(correctionQty),
          comment: correctionComment
        })
      });
      const updated = await res.json();
      if (!res.ok) throw new Error(updated.error || "Correction failed");
      
      setRecords(records.map(r => r.id === updated.id ? updated : r));
      setSelectedRecord(updated);
      setCorrectionQty('');
      setCorrectionComment('');
      refreshData();
    } catch (err) {
      alert(`Failed to save correction: ${err.message}`);
    }
  };

  // Register Plant Lookup and trigger Bulk Recalculation
  const handleRegisterPlantSubmit = async (e) => {
    e.preventDefault();
    if (!plantCodeToRegister.trim() || !newPlantName.trim() || !newPlantRegion.trim()) return;

    try {
      setLoading(true);
      // 1. Create the PlantLookup
      const plantRes = await fetch(`${API_BASE}/plants/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          organization: orgId,
          plant_code: plantCodeToRegister.trim(),
          name: newPlantName.trim(),
          region: newPlantRegion.trim()
        })
      });
      const plantData = await plantRes.json();
      if (!plantRes.ok) {
        throw new Error(JSON.stringify(plantData) || "Failed to create plant lookup");
      }

      // 2. Trigger bulk retroactive recalculation for matching records
      const recalcRes = await fetch(`${API_BASE}/records/recalculate_for_plant/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          organization: orgId,
          plant_code: plantCodeToRegister.trim()
        })
      });
      const recalcData = await recalcRes.json();
      if (!recalcRes.ok) throw new Error(recalcData.error || "Failed to trigger retroactive emissions recalculation");

      alert(`Plant registered successfully! ${recalcData.message}`);
      setShowPlantRegisterForm(false);
      setNewPlantName('');
      closeDrawer();
      refreshData();
    } catch (err) {
      alert(`Registration/Recalculation error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Correct Malformed Ingestion Row Sandbox
  const handleRetrySandboxSubmit = async (e) => {
    e.preventDefault();
    if (!selectedFailedRecord) return;

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/raw-records/${selectedFailedRecord.id}/retry_ingest/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_data: failedRecordCorrectionData
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Sandbox retry ingestion failed");

      alert("Correction applied and row successfully processed!");
      setSelectedFailedRecord(null);
      setFailedRecordCorrectionData({});
      refreshData();
    } catch (err) {
      alert(`Validation error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };


  const openDrawer = (rec) => {
    setSelectedRecord(rec);
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedRecord(null);
    setShowSuspiciousForm(false);
  };

  // Search filter implementation
  const filteredRecords = records.filter(r => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;
    return r.description.toLowerCase().includes(q) || 
           r.activity_type.toLowerCase().includes(q) ||
           (r.suspicious_reason && r.suspicious_reason.toLowerCase().includes(q));
  });

  const totalRecs = records.length;
  const auditedCount = records.filter(r => r.status === 'AUDITED').length;
  const approvedCount = records.filter(r => r.status === 'APPROVED').length;
  const draftCount = records.filter(r => r.status === 'DRAFT').length;
  const suspiciousCount = records.filter(r => r.status === 'SUSPICIOUS').length;
  
  const rawScore = totalRecs > 0 
    ? (auditedCount * 100 + approvedCount * 80 + draftCount * 50 - suspiciousCount * 20) / totalRecs
    : 100;
  const dataQualityScore = Math.max(0, Math.min(100, Math.round(rawScore)));

  return (
    <div style={{ display: 'flex', width: '100%' }}>
      {/* Sidebar Navigation */}
      <aside className="app-sidebar">
        <div className="brand-container">
          <div className="brand-logo">B</div>
          <div className="brand-name">Breathe ESG</div>
        </div>
        
        <nav className="sidebar-nav">
          <a className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
            <span>📊</span> Dashboard
          </a>
          <a className={`nav-item ${activeTab === 'ingest' ? 'active' : ''}`} onClick={() => setActiveTab('ingest')}>
            <span>📥</span> Ingest Center
          </a>
          <a className={`nav-item ${activeTab === 'review' ? 'active' : ''}`} onClick={() => setActiveTab('review')}>
            <span>🔍</span> Audit & Review
          </a>
        </nav>

        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="user-avatar">LA</div>
            <div className="user-info">
              <div className="username">Lead Analyst</div>
              <div className="role">Breathe ESG Core</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Panel Content */}
      <main className="main-content">
        <header className="content-header">
          <div className="header-title">
            <h1>Carbon Accounting & Review Engine</h1>
            <p>Data Ingestion, Proration, and Auditor Review Portal</p>
          </div>
          <div className="header-actions">
            {!seeded ? (
              <button className="btn btn-primary" onClick={handleSeed} disabled={loading}>
                {loading ? "Bootstrapping..." : "🚀 Bootstrap & Seed DB"}
              </button>
            ) : (
              <button className="btn btn-secondary" onClick={refreshData} disabled={loading}>
                🔄 Refresh Dashboard
              </button>
            )}
          </div>
        </header>

        {/* Global Ingestion Message */}
        {uploadMessage.text && (
          <div className="seed-banner" style={{ borderLeft: `4px solid ${uploadMessage.isError ? 'var(--status-suspicious)' : 'var(--status-approved)'}` }}>
            <div className="seed-banner-text">
              {uploadMessage.isError ? '⚠️' : '✅'} <strong>Ingestion pipeline alert:</strong> {uploadMessage.text}
            </div>
            <button className="close-btn" style={{ fontSize: '14px' }} onClick={() => setUploadMessage({ text: '', isError: false })}>✕</button>
          </div>
        )}

        {!seeded && (
          <div className="empty-state" style={{ border: '1px dashed var(--border-subtle)', borderRadius: '16px' }}>
            <div className="empty-state-icon">⚡</div>
            <h2>Platform Needs Seeding</h2>
            <p style={{ maxWidth: '450px', textAlign: 'center', fontSize: '15px' }}>
              Welcome to the Breathe ESG carbon review system! Click the <strong>Bootstrap & Seed DB</strong> button above to populate the global coordinate database (Haversine airport distances), standard plant mappings, and register multi-tenant ingestion sources.
            </p>
          </div>
        )}

        {seeded && (
          <>
            {/* TAB: DASHBOARD */}
            {activeTab === 'dashboard' && (
              <>
                {/* Metrics Cards */}
                <div className="metrics-grid">
                  <div className="metric-card total">
                    <div className="metric-header">
                      <span className="metric-label">Total Footprint</span>
                      <span className="metric-icon">🌍</span>
                    </div>
                    <div className="metric-value">
                      {Math.round(analytics.total_co2e_kg).toLocaleString()} <span className="metric-unit">kg CO₂e</span>
                    </div>
                    <div className="metric-trend">
                      {analytics.total_records} active activity transactions prorated
                    </div>
                  </div>

                  <div className="metric-card scope1">
                    <div className="metric-header">
                      <span className="metric-label">Scope 1 (Direct)</span>
                      <span className="metric-icon">🔥</span>
                    </div>
                    <div className="metric-value">
                      {Math.round(analytics.scopes['Scope 1'] || 0).toLocaleString()} <span className="metric-unit">kg CO₂e</span>
                    </div>
                    <div className="metric-trend">
                      Fuel procurement, heating gas, plants
                    </div>
                  </div>

                  <div className="metric-card scope2">
                    <div className="metric-header">
                      <span className="metric-label">Scope 2 (Grid)</span>
                      <span className="metric-icon">⚡</span>
                    </div>
                    <div className="metric-value">
                      {Math.round(analytics.scopes['Scope 2'] || 0).toLocaleString()} <span className="metric-unit">kg CO₂e</span>
                    </div>
                    <div className="metric-trend">
                      Purchased electricity, calendar prorated
                    </div>
                  </div>

                  <div className="metric-card scope3">
                    <div className="metric-header">
                      <span className="metric-label">Scope 3 (Travel)</span>
                      <span className="metric-icon">✈️</span>
                    </div>
                    <div className="metric-value">
                      {Math.round(analytics.scopes['Scope 3'] || 0).toLocaleString()} <span className="metric-unit">kg CO₂e</span>
                    </div>
                    <div className="metric-trend">
                      Flights (Haversine), hotels, ground
                    </div>
                  </div>

                  <div className="metric-card" style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', border: '1px solid rgba(16, 185, 129, 0.2)', minWidth: '240px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <span className="metric-label" style={{ color: 'var(--status-approved)' }}>Ledger Integrity</span>
                      <div className="metric-value" style={{ fontSize: '28px', color: 'var(--text-primary)' }}>
                        {dataQualityScore}%
                      </div>
                      <div className="metric-trend" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                        Based on audits, overrides & anomalies
                      </div>
                    </div>
                    <div className="scorecard-circle" style={{ background: `conic-gradient(var(--status-approved) ${dataQualityScore}%, var(--border-subtle) 0)` }}>
                      <span className="scorecard-value">{dataQualityScore}%</span>
                    </div>
                  </div>
                </div>

                {/* Dashboard Charts */}
                <div className="charts-grid">
                  {/* Monthly Bar Chart */}
                  <div className="chart-card">
                    <div className="chart-title">
                      <h2>Prorated Calendar Emissions</h2>
                      <p>Aggregated carbon footprint split and normalized into calendar months (kg CO₂e)</p>
                    </div>
                    <div className="chart-body">
                      {analytics.monthly_emissions.length === 0 ? (
                        <div className="empty-state" style={{ width: '100%', height: '100%', padding: 0 }}>
                          <p>No activity data parsed yet. Go to the Ingest Center!</p>
                        </div>
                      ) : (
                        <div className="chart-container-bar">
                          {analytics.monthly_emissions.map((item, idx) => {
                            const maxVal = Math.max(...analytics.monthly_emissions.map(m => m.total), 1);
                            const h1 = (item['Scope 1'] / maxVal) * 100;
                            const h2 = (item['Scope 2'] / maxVal) * 100;
                            const h3 = (item['Scope 3'] / maxVal) * 100;
                            
                            return (
                              <div className="bar-column" key={idx}>
                                <div className="bar-wrapper" style={{ height: '200px' }}>
                                  <div className="bar-segment bar-scope3" style={{ height: `${h3}%` }} title={`Scope 3: ${Math.round(item['Scope 3'])} kg`} />
                                  <div className="bar-segment bar-scope2" style={{ height: `${h2}%` }} title={`Scope 2: ${Math.round(item['Scope 2'])} kg`} />
                                  <div className="bar-segment bar-scope1" style={{ height: `${h1}%` }} title={`Scope 1: ${Math.round(item['Scope 1'])} kg`} />
                                </div>
                                <span className="bar-label">{item.month}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    <div className="chart-legend">
                      <div className="legend-item">
                        <div className="legend-color" style={{ backgroundColor: 'var(--scope1)' }} />
                        <span>Scope 1 (Fuels)</span>
                      </div>
                      <div className="legend-item">
                        <div className="legend-color" style={{ backgroundColor: 'var(--scope2)' }} />
                        <span>Scope 2 (Electricity)</span>
                      </div>
                      <div className="legend-item">
                        <div className="legend-color" style={{ backgroundColor: 'var(--scope3)' }} />
                        <span>Scope 3 (Travel)</span>
                      </div>
                    </div>
                  </div>

                  {/* Distribution Card */}
                  <div className="chart-card">
                    <div className="chart-title">
                      <h2>System Review Status</h2>
                      <p>Anomaly screening and validation ratios</p>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', justifyContent: 'center', height: '100%' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                          <span style={{ color: 'var(--status-approved)', fontWeight: '600' }}>Approved for Audit</span>
                          <span style={{ color: 'var(--text-primary)' }}>{analytics.statuses.APPROVED || 0} rows</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-subtle)', borderRadius: '9999px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', backgroundColor: 'var(--status-approved)', width: `${(analytics.statuses.APPROVED || 0) / (analytics.total_records || 1) * 100}%` }} />
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                          <span style={{ color: 'var(--status-suspicious)', fontWeight: '600' }}>Suspicious (Flagged)</span>
                          <span style={{ color: 'var(--text-primary)' }}>{analytics.statuses.SUSPICIOUS || 0} rows</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-subtle)', borderRadius: '9999px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', backgroundColor: 'var(--status-suspicious)', width: `${(analytics.statuses.SUSPICIOUS || 0) / (analytics.total_records || 1) * 100}%` }} />
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                          <span style={{ color: 'var(--status-draft)', fontWeight: '600' }}>Pending Review</span>
                          <span style={{ color: 'var(--text-primary)' }}>{analytics.statuses.DRAFT || 0} rows</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-subtle)', borderRadius: '9999px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', backgroundColor: 'var(--status-draft)', width: `${(analytics.statuses.DRAFT || 0) / (analytics.total_records || 1) * 100}%` }} />
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                          <span style={{ color: 'var(--status-audited)', fontWeight: '600' }}>Locked (Audited)</span>
                          <span style={{ color: 'var(--text-primary)' }}>{analytics.statuses.AUDITED || 0} rows</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-subtle)', borderRadius: '9999px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', backgroundColor: 'var(--status-audited)', width: `${(analytics.statuses.AUDITED || 0) / (analytics.total_records || 1) * 100}%` }} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* TAB: INGEST CENTER */}
            {activeTab === 'ingest' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', width: '100%' }}>
                <div className="ingestion-panel">
                  {/* SAP File & Utility File Uploader */}
                  <div className="upload-card">
                    <div className="chart-title">
                      <h2>CSV File Ingestion Pipeline</h2>
                      <p>Ingest raw SAP Procurement materials or Utility Portal bill CSVs</p>
                    </div>
                    
                    <div className="card-instructions">
                      Ingested records are automatically passed through raw validation parsers, resolving plant locations and splitting multi-month utility bill periods proportionally into individual calendar months.
                    </div>

                    {/* SAP uploader */}
                    <form onSubmit={handleUploadSAP} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ fontSize: '13px', fontWeight: '600', color: 'var(--scope1)' }}>SOURCE A: SAP FUEL & PROCUREMENT EXPORT</div>
                      <div className="dropzone" style={{ position: 'relative' }}>
                        <input 
                          type="file" 
                          accept=".csv"
                          onChange={(e) => setSapFile(e.target.files[0])}
                          style={{ position: 'absolute', opacity: 0, width: '100%', height: '100%', cursor: 'pointer' }}
                        />
                        <span className="dropzone-icon">📁</span>
                        <div className="dropzone-text">{sapFile ? sapFile.name : "Select or drag SAP CSV export file"}</div>
                        <div className="dropzone-subtext">Must contain plant WERKS, posting date BUDAT, description TXT50, quantity MENGE</div>
                      </div>
                      {sapFile && <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>Process SAP Export</button>}
                    </form>

                    {/* Utility uploader */}
                    <form onSubmit={handleUploadUtility} style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                      <div style={{ fontSize: '13px', fontWeight: '600', color: 'var(--scope2)' }}>SOURCE B: ELECTRICITY UTILITY BILL CSV</div>
                      <div className="dropzone" style={{ position: 'relative' }}>
                        <input 
                          type="file" 
                          accept=".csv"
                          onChange={(e) => setUtilityFile(e.target.files[0])}
                          style={{ position: 'absolute', opacity: 0, width: '100%', height: '100%', cursor: 'pointer' }}
                        />
                        <span className="dropzone-icon">⚡</span>
                        <div className="dropzone-text">{utilityFile ? utilityFile.name : "Select or drag Utility Billing CSV file"}</div>
                        <div className="dropzone-subtext">Must contain Bill Start Date, Bill End Date, Consumption, Account Number</div>
                      </div>
                      {utilityFile && <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>Process Utility Bill</button>}
                    </form>

                    {/* Sample content generator */}
                    <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div className="detail-label">Need Test Files?</div>
                      <div className="sample-downloader">
                        <span>SAP Fuel Sample Export (with anomalies)</span>
                        <a href="#" className="link-action" onClick={(e) => { e.preventDefault(); downloadCSV('sap'); }}>Download CSV</a>
                      </div>
                      <div className="sample-downloader">
                        <span>Utility billing calendar-spanning sample</span>
                        <a href="#" className="link-action" onClick={(e) => { e.preventDefault(); downloadCSV('utility'); }}>Download CSV</a>
                      </div>
                    </div>
                  </div>

                  {/* API Console Simulator */}
                  <div className="upload-card">
                    <div className="chart-title">
                      <h2>Corporate Travel API Simulator</h2>
                      <p>Copy-paste JSON expense records for Concur or Navan API ingestion</p>
                    </div>
                    
                    <div className="card-instructions">
                      Travel platform items map flights, hotel stays, and ground transport. Flight distances are dynamically calculated using **Haversine formula coordinate math** for airport codes.
                    </div>

                    <div className="console-container">
                      <textarea 
                        className="console-editor"
                        value={jsonInput}
                        onChange={(e) => setJsonInput(e.target.value)}
                      />
                      <div className="console-presets">
                        <button className="preset-btn" onClick={() => setJsonInput(JSON.stringify(sampleTravelPayload, null, 2))}>Preset 1: Standard Trip</button>
                        <button className="preset-btn" onClick={() => setJsonInput(JSON.stringify(sampleTravelPayloadAnomalies, null, 2))}>Preset 2: Travel with Anomaly</button>
                      </div>
                    </div>

                    <button className="btn btn-accent" style={{ marginTop: 'auto' }} onClick={handleSubmitTravel} disabled={loading}>
                      📥 Push JSON to Travel Ingestion API
                    </button>
                  </div>
                </div>

                {/* Staging Sandbox & Diagnostics */}
                <div className="upload-card" style={{ maxWidth: '100%' }}>
                  <div className="chart-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h2>Ingestion Sandbox & Validation Diagnostics</h2>
                      <p>Staging area for malformed raw rows that failed ingestion schema constraints</p>
                    </div>
                    <span className="sandbox-badge" style={{ backgroundColor: failedRecords.length > 0 ? 'var(--status-suspicious-bg)' : 'var(--status-approved-bg)', color: failedRecords.length > 0 ? 'var(--status-suspicious)' : 'var(--status-approved)' }}>
                      {failedRecords.length} Sandboxed Rows
                    </span>
                  </div>

                  <div className="card-instructions">
                    Correct data constraints errors (such as text instead of numeric consumption, empty dates, or bad layout formats) directly below. Hit <strong>"Retry Normalization"</strong> to safely parse and ingest correct items.
                  </div>

                  {failedRecords.length === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px', gap: '12px', border: '1px dashed var(--border-subtle)', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.01)' }}>
                      <span style={{ fontSize: '24px' }}>🛡️</span>
                      <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>All Ingestion flows clean. No sandbox errors flagged!</span>
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: selectedFailedRecord ? '1fr 1fr' : '1fr', gap: '24px' }}>
                      {/* Sandbox List */}
                      <div className="sandbox-grid">
                        {failedRecords.map(raw => (
                          <div 
                            key={raw.id} 
                            className="sandbox-row" 
                            style={{ 
                              cursor: 'pointer', 
                              border: selectedFailedRecord?.id === raw.id ? '1px solid var(--status-suspicious)' : '1px solid var(--border-subtle)',
                              backgroundColor: selectedFailedRecord?.id === raw.id ? 'rgba(244, 63, 94, 0.03)' : 'var(--bg-surface-elevated)'
                            }}
                            onClick={() => {
                              setSelectedFailedRecord(raw);
                              setFailedRecordCorrectionData(raw.raw_data);
                            }}
                          >
                            <div style={{ flexGrow: 1 }}>
                              <div style={{ fontWeight: '600', fontSize: '14px' }}>Row #{raw.row_index} in Batch #{raw.batch} ({raw.raw_data.TXT50 || raw.raw_data['Utility Account'] || "Raw Ingest Record"})</div>
                              <div className="sandbox-error-text">❌ {raw.validation_errors.join('; ')}</div>
                            </div>
                            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '12px' }}>Click to Fix ➔</span>
                          </div>
                        ))}
                      </div>

                      {/* Inline Form */}
                      {selectedFailedRecord && (
                        <form onSubmit={handleRetrySandboxSubmit} className="sandbox-form">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span className="form-title" style={{ color: 'var(--status-suspicious)', fontWeight: '600' }}>✏️ Correct Sandbox Line (Row #{selectedFailedRecord.row_index})</span>
                            <button type="button" className="close-btn" style={{ fontSize: '16px' }} onClick={() => setSelectedFailedRecord(null)}>✕</button>
                          </div>
                          
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', maxHeight: '250px', overflowY: 'auto', paddingRight: '4px' }}>
                            {Object.keys(selectedFailedRecord.raw_data).map(key => (
                              <div className="form-group" key={key}>
                                <label className="form-label">{key}</label>
                                <input 
                                  type="text" 
                                  className="form-input" 
                                  value={failedRecordCorrectionData[key] || ''}
                                  onChange={(e) => {
                                    setFailedRecordCorrectionData({
                                      ...failedRecordCorrectionData,
                                      [key]: e.target.value
                                    });
                                  }}
                                  required
                                />
                              </div>
                            ))}
                          </div>

                          <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
                            <button type="submit" className="btn btn-primary" style={{ flexGrow: 1, backgroundColor: 'var(--status-suspicious)', borderColor: 'var(--status-suspicious)' }} disabled={loading}>
                              {loading ? "Re-processing..." : "⚡ Retry Normalization"}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={() => setSelectedFailedRecord(null)}>
                              Cancel
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB: AUDIT & REVIEW GRID */}
            {activeTab === 'review' && (
              <>
                {/* Control bar */}
                <div className="grid-controls">
                  <div className="filter-group">
                    <div className="filter-label">Scope</div>
                    <select className="filter-select" value={filterScope} onChange={(e) => setFilterScope(e.target.value)}>
                      <option value="">All Scopes</option>
                      <option value="Scope 1">Scope 1 (Direct)</option>
                      <option value="Scope 2">Scope 2 (Indirect Grid)</option>
                      <option value="Scope 3">Scope 3 (Travel)</option>
                    </select>

                    <div className="filter-label" style={{ marginLeft: '12px' }}>Status</div>
                    <select className="filter-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                      <option value="">All Statuses</option>
                      <option value="DRAFT">Pending Review (Draft)</option>
                      <option value="SUSPICIOUS">Suspicious (Flagged)</option>
                      <option value="APPROVED">Approved</option>
                      <option value="AUDITED">Locked (Audited)</option>
                    </select>
                  </div>

                  <div className="search-wrapper">
                    <span className="search-icon">🔍</span>
                    <input 
                      type="text" 
                      className="search-input" 
                      placeholder="Search descriptions, plants..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>

                  {selectedRecordIds.length > 0 && (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="btn btn-primary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={handleBulkApprove}>Bulk Approve ({selectedRecordIds.length})</button>
                      <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', borderColor: 'rgba(59, 130, 246, 0.4)', color: 'var(--status-audited)' }} onClick={handleBulkLock}>Bulk Lock ({selectedRecordIds.length})</button>
                    </div>
                  )}
                </div>

                {/* Review table */}
                <div className="table-container">
                  <table className="review-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>
                          <input 
                            type="checkbox" 
                            className="checkbox-custom"
                            onChange={handleSelectAll}
                            checked={records.length > 0 && selectedRecordIds.length === records.length}
                          />
                        </th>
                        <th>Scope / Category</th>
                        <th>Activity Date</th>
                        <th>Transaction Description</th>
                        <th>Ingested Original</th>
                        <th>Normalized footprint</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRecords.length === 0 ? (
                        <tr>
                          <td colSpan="7" style={{ textAlign: 'center', padding: '40px' }}>
                            <div className="empty-state">
                              <span style={{ fontSize: '24px' }}>📭</span>
                              <p>No activity records match filters. Check Ingest Center to populate!</p>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        filteredRecords.map(r => (
                          <tr 
                            key={r.id} 
                            onClick={() => openDrawer(r)}
                            className={`${r.status === 'SUSPICIOUS' ? 'row-suspicious' : ''} ${selectedRecordIds.includes(r.id) ? 'selected' : ''}`}
                          >
                            <td onClick={(e) => { e.stopPropagation(); toggleRecordSelection(r.id); }}>
                              <input 
                                type="checkbox" 
                                className="checkbox-custom"
                                checked={selectedRecordIds.includes(r.id)}
                                readOnly
                              />
                            </td>
                            <td>
                              <span className={`badge badge-${r.scope.replace(' ', '').toLowerCase()}`}>{r.scope}</span>
                              <div className="cell-meta" style={{ fontSize: '11px' }}>{r.category}</div>
                            </td>
                            <td>{r.activity_date}</td>
                            <td>
                              <div style={{ fontWeight: '500', color: 'var(--text-primary)' }}>{r.description}</div>
                              <div className="cell-meta">Batch ID: {r.batch_detail?.id} ({r.batch_detail?.filename})</div>
                            </td>
                            <td>
                              {Math.round(r.raw_quantity).toLocaleString()} {r.raw_unit}
                            </td>
                            <td>
                              <div className="cell-co2e">{Math.round(r.co2e_kg).toLocaleString()} kg</div>
                              <div className="cell-meta" style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(r.normalized_quantity)} {r.normalized_unit}</div>
                            </td>
                            <td>
                              <span className={`badge badge-${r.status.toLowerCase()}`}>
                                {r.status === 'SUSPICIOUS' ? '⚠️ ' : r.status === 'APPROVED' ? '✓ ' : r.status === 'AUDITED' ? '🔒 ' : ''}
                                {r.status}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </main>

      {/* Slideout Review & Audit Log Drawer */}
      <div className={`drawer-overlay ${drawerOpen ? 'open' : ''}`} onClick={closeDrawer}>
        <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
          <div className="drawer-header">
            <h2>Activity Audit & Correction Panel</h2>
            <button className="close-btn" onClick={closeDrawer}>✕</button>
          </div>

          {selectedRecord && (
            <div className="drawer-body">
              {/* Scope & Status Badges */}
              <div style={{ display: 'flex', gap: '8px' }}>
                <span className={`badge badge-${selectedRecord.scope.replace(' ', '').toLowerCase()}`}>{selectedRecord.scope}</span>
                <span className={`badge badge-${selectedRecord.status.toLowerCase()}`}>{selectedRecord.status}</span>
              </div>

              {/* Description */}
              <div className="detail-section">
                <span className="detail-label">Activity Detail</span>
                <span className="detail-value" style={{ fontSize: '18px', fontWeight: '600' }}>{selectedRecord.description}</span>
              </div>

              {/* Ingestion Source Tracker (Source-of-truth tracking) */}
              <div className="detail-section" style={{ backgroundColor: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-subtle)', padding: '12px', borderRadius: '8px' }}>
                <span className="detail-label" style={{ fontSize: '10px' }}>Ingestion Batch Lineage</span>
                <span className="detail-value" style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  File: <strong>{selectedRecord.batch_detail?.filename}</strong><br/>
                  Batch Status: {selectedRecord.batch_detail?.status} ({selectedRecord.batch_detail?.created_at.substring(0,10)})
                </span>
              </div>

              {/* Anomaly warning box */}
              {selectedRecord.status === 'SUSPICIOUS' && (
                <div className="suspicious-box">
                  <span className="suspicious-box-title">Validation Warning / Anomaly Flags</span>
                  <span className="suspicious-box-desc">{selectedRecord.suspicious_reason}</span>
                  {selectedRecord.suspicious_reason.includes("Unknown Plant Code") && !showPlantRegisterForm && (
                    <button 
                      className="btn btn-accent" 
                      style={{ marginTop: '12px', width: '100%', fontSize: '12px', padding: '6px 12px' }}
                      onClick={() => {
                        const match = selectedRecord.suspicious_reason.match(/Unknown Plant Code '([^']+)'/);
                        const plantCode = match ? match[1] : "";
                        setPlantCodeToRegister(plantCode);
                        setShowPlantRegisterForm(true);
                      }}
                    >
                      🚀 Register Plant Mappings & Re-calculate
                    </button>
                  )}
                </div>
              )}

              {/* Plant Registration Wizard form */}
              {showPlantRegisterForm && (
                <form onSubmit={handleRegisterPlantSubmit} className="correction-form" style={{ border: '1px solid var(--status-approved)' }}>
                  <div className="form-title" style={{ color: 'var(--status-approved)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>🌱 Register Facility Mappings</span>
                    <button type="button" className="close-btn" style={{ fontSize: '16px' }} onClick={() => setShowPlantRegisterForm(false)}>✕</button>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Plant Code (WERKS)</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      value={plantCodeToRegister}
                      onChange={(e) => setPlantCodeToRegister(e.target.value)}
                      readOnly
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Resolve Facility Name</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. Munich Hub Center"
                      value={newPlantName}
                      onChange={(e) => setNewPlantName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Regional Electricity Grid (Factor Country)</label>
                    <select 
                      className="form-input"
                      style={{ width: '100%' }}
                      value={newPlantRegion}
                      onChange={(e) => setNewPlantRegion(e.target.value)}
                    >
                      <option value="DE">Germany (DE) - 0.38 kg/kWh</option>
                      <option value="US">United States (US) - 0.37 kg/kWh</option>
                      <option value="IN">India (IN) - 0.71 kg/kWh</option>
                      <option value="UK">United Kingdom (UK) - 0.21 kg/kWh</option>
                      <option value="DEFAULT">Global Average - 0.40 kg/kWh</option>
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary" style={{ backgroundColor: 'var(--status-approved)', width: '100%' }} disabled={loading}>
                    {loading ? "Processing..." : "💾 Register & Retroactive Sync"}
                  </button>
                </form>
              )}


              {/* Emissions Math */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="detail-section" style={{ borderLeft: '3px solid var(--primary)', paddingLeft: '12px' }}>
                  <span className="detail-label">Total Footprint</span>
                  <span className="detail-value" style={{ fontSize: '24px', fontWeight: '700', color: 'var(--text-primary)' }}>
                    {Math.round(selectedRecord.co2e_kg).toLocaleString()} <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>kg CO₂e</span>
                  </span>
                </div>

                <div className="detail-section" style={{ borderLeft: '3px solid var(--scope3)', paddingLeft: '12px' }}>
                  <span className="detail-label">Normalized Quantity</span>
                  <span className="detail-value" style={{ fontSize: '20px', fontWeight: '600', color: 'var(--text-secondary)' }}>
                    {Math.round(selectedRecord.normalized_quantity).toLocaleString()} <span style={{ fontSize: '13px' }}>{selectedRecord.normalized_unit}</span>
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              {!selectedRecord.audit_locked && (
                <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                  <button className="btn btn-primary" style={{ flexGrow: 1 }} onClick={() => handleApproveSingle(selectedRecord)}>
                    ✓ Approve Record
                  </button>
                  <button className="btn btn-secondary" onClick={() => setShowSuspiciousForm(!showSuspiciousForm)}>
                    ⚠️ Flag Anomaly
                  </button>
                </div>
              )}

              {/* Anomaly Flag Form */}
              {showSuspiciousForm && (
                <div className="correction-form">
                  <span className="form-title">Enter Anomaly Details</span>
                  <div className="form-group">
                    <label className="form-label">Flagging Reason</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. Inconsistent billing period or duplicate record"
                      value={suspiciousReasonInput}
                      onChange={(e) => setSuspiciousReasonInput(e.target.value)}
                    />
                  </div>
                  <button className="btn btn-primary" onClick={() => handleFlagSuspiciousSingle(selectedRecord)}>
                    Flag Suspicious
                  </button>
                </div>
              )}

              {/* Manual Correction Form */}
              {!selectedRecord.audit_locked ? (
                <form onSubmit={handleCorrectionSubmit} className="correction-form">
                  <span className="form-title">Propose Manual Value Correction</span>
                  <div className="form-group">
                    <label className="form-label">New Original Quantity ({selectedRecord.raw_unit})</label>
                    <input 
                      type="number" 
                      step="any"
                      className="form-input" 
                      placeholder={`Current: ${selectedRecord.raw_quantity}`}
                      value={correctionQty}
                      onChange={(e) => setCorrectionQty(e.target.value)}
                      required
                    />
                  </div>
                  
                  <div className="form-group">
                    <label className="form-label">Justification / Audit Comment</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. Typos corrected in procurement voucher quantity."
                      value={correctionComment}
                      onChange={(e) => setCorrectionComment(e.target.value)}
                      required
                    />
                  </div>
                  <button type="submit" className="btn btn-accent">💾 Save & Recalculate Emissions</button>
                </form>
              ) : (
                <div className="suspicious-box" style={{ backgroundColor: 'var(--status-audited-bg)', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                  <span className="suspicious-box-title" style={{ color: 'var(--status-audited)' }}>🔒 Auditor Locked</span>
                  <span className="suspicious-box-desc" style={{ fontSize: '13px' }}>
                    This transaction was frozen and locked for audit. Edits, status changes, and corrections are permanently blocked for security.
                  </span>
                </div>
              )}

              {/* Audit history logs */}
              <div className="detail-section">
                <span className="detail-label">Audit Trail Ledger</span>
                <div className="timeline">
                  {selectedRecord.audit_history && selectedRecord.audit_history.length > 0 ? (
                    selectedRecord.audit_history.map((h, i) => (
                      <div className="timeline-item" key={i}>
                        <div className={`timeline-node node-${h.action.toLowerCase()}`} />
                        <div className="timeline-content">
                          <span className="timeline-action">{h.action} Action by {h.user_detail ? h.user_detail.username : "System"}</span>
                          <span className="timeline-time">{h.timestamp.substring(11, 16)} {h.timestamp.substring(0, 10)}</span>
                          {h.comment && <span className="timeline-comment">"{h.comment}"</span>}
                          {h.changes && Object.keys(h.changes).length > 0 && (
                            <div className="timeline-changes" style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontFamily: 'var(--font-sans)', fontSize: '12px', marginTop: '6px' }}>
                              {Object.keys(h.changes).map(field => {
                                const change = h.changes[field];
                                if (!change || change.old === undefined || change.new === undefined) return null;
                                return (
                                  <div key={field} style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                    <span style={{ fontWeight: '600', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{field.replace('_', ' ')}:</span>
                                    <span className="diff-tag-del">{typeof change.old === 'number' ? Math.round(change.old).toLocaleString() : String(change.old)}</span>
                                    <span style={{ color: 'var(--text-muted)' }}>→</span>
                                    <span className="diff-tag-ins">{typeof change.new === 'number' ? Math.round(change.new).toLocaleString() : String(change.new)}</span>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No audit actions logged yet.</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Fabricated test data files
const sampleTravelPayload = [
  {
    "booking_id": "TRV-90182",
    "date": "2026-04-10",
    "category": "flight",
    "details": {
      "origin": "JFK",
      "destination": "LHR",
      "class": "business"
    }
  },
  {
    "booking_id": "TRV-90183",
    "date": "2026-04-12",
    "category": "hotel",
    "details": {
      "country": "UK",
      "nights": 4
    }
  },
  {
    "booking_id": "TRV-90184",
    "date": "2026-04-16",
    "category": "ground",
    "details": {
      "type": "train",
      "distance_km": 120.0
    }
  }
];

const sampleTravelPayloadAnomalies = [
  {
    "booking_id": "TRV-88220",
    "date": "2026-05-01",
    "category": "flight",
    "details": {
      "origin": "DEL",
      "destination": "SFO",
      "class": "super_first"
    }
  },
  {
    "booking_id": "TRV-88221",
    "date": "2026-05-08",
    "category": "hotel",
    "details": {
      "country": "XY",
      "nights": 45
    }
  }
];

// Helper to trigger dummy CSV downloads for quick testing
function downloadCSV(type) {
  let content = "";
  let filename = "";
  
  if (type === 'sap') {
    filename = "sap_procurement_export.csv";
    content = "WERKS,BUDAT,MATNR,MENGE,MEINS,TXT50,WRBTR,WAERS\n" +
              "1000,20260420,108892,2500,L,HEIZOEL LEICHT,3750,EUR\n" +
              "1200,22.04.2026,108892,1200,L,DIESELKRAFTSTOFF,1920,EUR\n" +
              "2000,2026-04-28,209930,45000,TO,HEATING OIL OUTLIER,56000,USD\n" + // Anomaly: 45000 Tons is massive
              "9999,20260430,108892,950,L,DIESEL PLANT ERROR,1300,EUR\n"; // Anomaly: Plant 9999 is unknown
  } else {
    filename = "utility_electricity_export.csv";
    content = "Utility Account,Meter Number,Bill Start Date,Bill End Date,Consumption,Unit,Tariff / Rate Class,Region\n" +
              "90918-202,MTR-881,2026-04-15,2026-05-15,3000,kWh,E-19,US\n" + // Spans 30 days (15 April, 15 May)
              "90918-202,MTR-881,2026-05-15,2026-07-15,12000,kWh,E-19,US\n" + // Spans 61 days (Anomaly: abnormally long)
              "77221-100,MTR-990,2026-04-01,2026-04-30,4500,MWh,TOU-A,DE\n"; // Inconsistent unit MWh -> kWh
  }
  
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
