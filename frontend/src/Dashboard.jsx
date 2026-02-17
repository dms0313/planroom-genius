import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Download, Mail, ChevronLeft, ChevronRight, FileText, ExternalLink, Building2, User, MapPin, Calendar, AlertCircle, Plus, Pencil, Trash2, X, Settings, FileText as Description, Terminal, Minimize2, Maximize2, Cloud, CloudOff, Brain, ArrowUpDown, RefreshCw, Eye, EyeOff, ChevronDown, ChevronUp, Search, Zap, Shield, AlertTriangle, CheckCircle2, Circle, Minus, FolderOpen } from 'lucide-react';
import TakeoffPanel from './TakeoffPanel';

// Utility functions moved outside to prevent re-creation
const isExpired = (bidDate) => {
  if (!bidDate || bidDate === 'N/A' || bidDate === 'TBD') return false;
  try { const d = new Date(bidDate); const t = new Date(); t.setHours(0, 0, 0, 0); return d < t; } catch { return false; }
};

const badgeColor = (badge) => {
  if (badge === 'NO FA') return 'bg-red-500/20 text-red-400 border-red-500/30';
  if (badge === 'DEAL BREAKER') return 'bg-red-600/20 text-red-300 border-red-600/30';
  if (badge === 'COMPATIBLE MFR' || badge === 'COMPAT MFR') return 'bg-green-500/20 text-green-400 border-green-500/30';
  if (badge === 'INCOMPATIBLE MFR' || badge === 'INCOMPAT MFR') return 'bg-red-500/20 text-red-400 border-red-500/30';
  if (badge === 'EXISTING') return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
  if (badge === 'NEW SYSTEM') return 'bg-green-500/20 text-green-400 border-green-500/30';
  if (badge === 'MODIFICATION' || badge === 'MOD') return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
  if (badge === 'VOICE') return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
  if (badge === 'MONITORING') return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
  if (badge === 'ACCESS CTRL') return 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30';
  if (badge === 'NON-SPRINKLED') return 'bg-amber-600/20 text-amber-400 border-amber-600/30';
  if (badge.includes('REQ')) return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
  return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
};

const badgeHover = (badge, lead) => {
  if (badge === 'NO FA') return 'No fire alarm scope found in project documents — likely not a FA job';
  if (badge === 'EXISTING') {
    const mfrs = lead?.knowledge_required_manufacturers;
    return mfrs?.length > 0
      ? `Existing system — panel: ${mfrs.join(', ')}`
      : 'Existing fire alarm system — check plans for panel manufacturer';
  }
  if (badge === 'NEW SYSTEM') return 'New fire alarm system installation — full scope';
  if (badge === 'MODIFICATION' || badge === 'MOD') return 'Modification/retrofit to existing fire alarm system';
  if (badge === 'REQ MFR') {
    const mfrs = lead?.knowledge_required_manufacturers;
    return mfrs?.length > 0 ? `Required: ${mfrs.join(', ')}` : 'Manufacturer specified in specs';
  }
  if (badge === 'REQ VENDOR') {
    const vendors = lead?.knowledge_required_vendors;
    return vendors?.length > 0 ? `Required: ${vendors.join(', ')}` : 'Vendor specified in specs';
  }
  if (badge === 'COMPATIBLE MFR' || badge === 'COMPAT MFR') {
    const mfrs = lead?.knowledge_required_manufacturers;
    return mfrs?.length > 0 ? `Compatible — ${mfrs.join(', ')}` : 'Specified manufacturer is compatible with our products';
  }
  if (badge === 'INCOMPATIBLE MFR' || badge === 'INCOMPAT MFR') {
    const mfrs = lead?.knowledge_required_manufacturers;
    return mfrs?.length > 0 ? `NOT compatible — ${mfrs.join(', ')}` : 'Specified manufacturer is NOT compatible';
  }
  if (badge === 'DEAL BREAKER') {
    const reasons = lead?.knowledge_deal_breakers;
    return reasons?.length > 0 ? reasons.join(' · ') : 'Deal breaker identified — review details';
  }
  if (badge === 'VOICE') return 'Voice evacuation / mass notification system required';
  if (badge === 'MONITORING') return 'Monitoring services included in scope';
  if (badge === 'ACCESS CTRL') return 'Access control interface / integration required';
  if (badge === 'NON-SPRINKLED') return 'Building is NOT sprinklered — may need more detection';
  return badge;
};

// Detect project type tags from name/description for at-a-glance info
const detectProjectTags = (lead) => {
  const tags = [];
  const text = `${lead.name || ''} ${lead.description || ''} ${lead.knowledge_notes || ''}`.toLowerCase();
  const name = (lead.name || '').toLowerCase();
  // Building types that affect fire alarm scope/complexity
  if (/\bapartment|\bmulti.?family|\bresidential\b|\bcondo/.test(text)) tags.push({ label: 'RESIDENTIAL', color: 'bg-pink-500/20 text-pink-400 border-pink-500/30', hover: 'Apartments / multi-family — typically needs individual unit detection' });
  if (/\bhospital|\bmedical|\bhealthcare|\bclinic|\bsurgical/.test(text)) tags.push({ label: 'HEALTHCARE', color: 'bg-rose-500/20 text-rose-400 border-rose-500/30', hover: 'Healthcare facility — stringent code requirements' });
  if (/\bschool|\buniversity|\bcollege|\beducation|\bcampus/.test(text)) tags.push({ label: 'EDUCATION', color: 'bg-sky-500/20 text-sky-400 border-sky-500/30', hover: 'Educational facility — mass notification may apply' });
  if (/\bhigh.?rise|\b\d{2,}\s*stor(y|ies)/.test(text)) tags.push({ label: 'HIGH-RISE', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30', hover: 'High-rise building — complex zoning & voice evac likely' });
  if (/\bwarehouse|\bstorage|\bdistribution/.test(text)) tags.push({ label: 'WAREHOUSE', color: 'bg-stone-500/20 text-stone-400 border-stone-500/30', hover: 'Warehouse / storage — large open areas, high ceilings' });
  if (/\bhotel|\bhospitality|\bresort|\blodg/.test(text)) tags.push({ label: 'HOTEL', color: 'bg-violet-500/20 text-violet-400 border-violet-500/30', hover: 'Hotel / hospitality — individual room detection' });
  if (/\bchurch|\bworship|\btemple|\bmosque/.test(text)) tags.push({ label: 'WORSHIP', color: 'bg-fuchsia-500/20 text-fuchsia-400 border-fuchsia-500/30', hover: 'Place of worship — large assembly space' });
  if (/\bparking\s*(garage|structure|deck)/.test(text)) tags.push({ label: 'PARKING', color: 'bg-neutral-500/20 text-neutral-400 border-neutral-500/30', hover: 'Parking structure — CO detection may apply' });
  if (/\bdata\s*center|\bserver/.test(name)) tags.push({ label: 'DATA CTR', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', hover: 'Data center — clean agent / early detection' });
  return tags;
};

const classColor = (cls) => {
  if (cls === 'plan') return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
  if (cls === 'spec') return 'bg-green-500/20 text-green-400 border-green-500/40';
  if (cls === 'ignore') return 'bg-red-500/20 text-red-400 border-red-500/40';
  return 'bg-slate-500/20 text-slate-400 border-slate-500/40';
};

const getHighlightBg = (highlight) => {
  if (highlight === 'green') return 'bg-green-500/10 border-l-2 border-green-500';
  if (highlight === 'yellow') return 'bg-yellow-500/10 border-l-2 border-yellow-500';
  if (highlight === 'red') return 'bg-red-500/10 border-l-2 border-red-500';
  return '';
};

const getCommentColor = (highlight) => {
  if (highlight === 'green') return 'text-green-400 focus:text-green-400';
  if (highlight === 'yellow') return 'text-yellow-400 focus:text-yellow-400';
  if (highlight === 'red') return 'text-red-400 focus:text-red-400';
  return 'text-purple-400 focus:text-purple-400';
};

const formatDate = (dateStr) => {
  if (!dateStr || dateStr === 'N/A' || dateStr === 'TBD') return dateStr || 'N/A';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return dateStr; }
};

const stripHtml = (html) => {
  if (!html || typeof html !== 'string') return html || '';
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(?:div|p|li|tr|h[1-6])>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
};

export default function LeadDashboard() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [deduplicating, setDeduplicating] = useState(false);
  const [companyPopup, setCompanyPopup] = useState(null);
  const [descriptionPopup, setDescriptionPopup] = useState(null);
  const [editModal, setEditModal] = useState(null);
  const [addModal, setAddModal] = useState(false);
  const [showUtilityMenu, setShowUtilityMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [scraperSettings, setScraperSettings] = useState({
    planhub: true,
    bidplanroom: true,
    loydbuildsbetter: true,
    buildingconnected: true,
    use_gdrive: true
  });

  // Console monitor state
  const [showConsole, setShowConsole] = useState(false);
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [scraperStatus, setScraperStatus] = useState(null);
  const [consoleMinimized, setConsoleMinimized] = useState(false);
  const consoleEndRef = useRef(null);

  // Google Drive state
  const [gdriveStatus, setGdriveStatus] = useState(null);
  const [connectingGdrive, setConnectingGdrive] = useState(false);
  const [activeTab, setActiveTab] = useState('bid');
  const [siteFilter, setSiteFilter] = useState('all');

  // Knowledge scan state
  const [knowledgeStatus, setKnowledgeStatus] = useState(null);
  const [knowledgeScanning, setKnowledgeScanning] = useState(false);
  const [knowledgeFilter, setKnowledgeFilter] = useState('all'); // all, scanned, unscanned
  const [showHidden, setShowHidden] = useState(false);
  const [sortConfig, setSortConfig] = useState({ key: 'bid_date', direction: 'asc' });
  const [searchQuery, setSearchQuery] = useState('');
  const [pointToFileModal, setPointToFileModal] = useState(null); // {lead_id, files}
  const [pointToFileLoading, setPointToFileLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null); // rel_path of selected file
  const [viewerPage, setViewerPage] = useState(0);
  const [viewerPageCount, setViewerPageCount] = useState(0);
  const [viewerImageUrl, setViewerImageUrl] = useState(null);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [scanningIds, setScanningIds] = useState(new Set());
  const [folderBrowserModal, setFolderBrowserModal] = useState(false);
  const [folderBrowserPath, setFolderBrowserPath] = useState('');
  const [folderBrowserItems, setFolderBrowserItems] = useState([]);
  const [folderBrowserLoading, setFolderBrowserLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);


  // Form state for add/edit
  const emptyForm = {
    name: '',
    company: '',
    gc: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    location: '',
    full_address: '',
    bid_date: '',
    description: '',
    files_link: '',
    download_link: '',
    site: 'Manual Entry',
    sprinklered: false,
    has_budget: false
  };
  const [formData, setFormData] = useState(emptyForm);

  // Filter and search logic
  const uniqueSites = useMemo(() => {
    const sites = leads.map(l => l.site).filter(Boolean);
    return [...new Set(sites)].sort();
  }, [leads]);

  const filteredLeads = useMemo(() => {
    let result = leads;

    // Knowledge filter
    if (knowledgeFilter === 'scanned') result = result.filter(l => l.knowledge_last_scanned != null);
    else if (knowledgeFilter === 'unscanned') result = result.filter(l => l.knowledge_last_scanned == null);

    // Site filter
    if (siteFilter !== 'all') result = result.filter(l => l.site === siteFilter);

    // Hidden filter
    if (!showHidden) result = result.filter(l => !l.hidden);

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(l =>
        l.name?.toLowerCase().includes(q) ||
        l.company?.toLowerCase().includes(q) ||
        l.gc?.toLowerCase().includes(q) ||
        l.description?.toLowerCase().includes(q) ||
        l.tags?.some(t => t.label.toLowerCase().includes(q))
      );
    }

    // Sorting
    result.sort((a, b) => {
      let aVal = a[sortConfig.key];
      let bVal = b[sortConfig.key];

      // Handle nulls
      if (aVal === null || aVal === undefined) aVal = '';
      if (bVal === null || bVal === undefined) bVal = '';

      // Special handling for dates
      if (sortConfig.key === 'bid_date') {
        const da = new Date(aVal === 'TBD' || aVal === 'N/A' || !aVal ? '2099-12-31' : aVal);
        const db = new Date(bVal === 'TBD' || bVal === 'N/A' || !bVal ? '2099-12-31' : bVal);
        return sortConfig.direction === 'asc' ? da - db : db - da;
      }

      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });

    return result;
  }, [leads, knowledgeFilter, siteFilter, searchQuery, showHidden, sortConfig]);

  const API_BASE = `http://${window.location.hostname}:8000`;

  useEffect(() => {
    fetchLeads();
    fetchGdriveStatus();
    fetchKnowledgeStatus();
    fetchSettings();

    // Poll for updates every 10 seconds
    const interval = setInterval(() => {
      fetchLeads(true);
      fetchKnowledgeStatus(); // Also poll knowledge status
      // Check scraper status to keep syncing state accurate
      fetchScraperStatus().then(status => {
        if (status?.running) setSyncing(true);
        else if (syncing) setSyncing(false); // Auto-turn off if finished
      });
    }, 10000);

    // Initial check
    fetchScraperStatus().then(status => {
      if (status?.running) setSyncing(true);
    });

    return () => clearInterval(interval);
  }, []);

  // Fetch Google Drive status
  const fetchGdriveStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/gdrive/status`);
      const data = await res.json();
      setGdriveStatus(data);
    } catch (e) {
      console.error("Failed to fetch Google Drive status", e);
      setGdriveStatus({ status: 'error', message: 'Failed to check status' });
    }
  };

  const connectGdrive = async () => {
    setConnectingGdrive(true);
    try {
      const res = await fetch(`${API_BASE}/gdrive/connect`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        alert('Google Drive connected successfully!');
        fetchGdriveStatus();
      } else {
        alert(`Connection failed: ${data.detail || data.message}`);
      }
    } catch (e) {
      alert("Failed to connect to Google Drive.");
    }
    setConnectingGdrive(false);
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/scrapers`);
      if (res.ok) {
        const data = await res.json();
        setScraperSettings(data);
      }
    } catch (e) {
      console.error("Failed to fetch settings", e);
    }
  };

  const saveSettings = async (newSettings) => {
    try {
      await fetch(`${API_BASE}/settings/scrapers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings)
      });
      setScraperSettings(newSettings);
    } catch (e) {
      console.error("Failed to save settings", e);
      alert("Failed to save settings");
    }
  };

  const toggleSetting = (key) => {
    const newSettings = { ...scraperSettings, [key]: !scraperSettings[key] };
    saveSettings(newSettings);
  };

  const fetchKnowledgeStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/status`);
      const data = await res.json();
      setKnowledgeStatus(data);
    } catch (e) {
      console.error("Failed to fetch knowledge status", e);
    }
  };

  const triggerKnowledgeScan = async () => {
    setKnowledgeScanning(true);
    try {
      const res = await fetch(`${API_BASE}/knowledge/scan`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        alert(data.detail || 'Failed to start Knowledge scan');
      }
      // Start polling for status
      const poll = setInterval(async () => {
        const s = await fetchKnowledgeStatus();
        await fetchLeads();
        if (!knowledgeStatus?.running) {
          clearInterval(poll);
          setKnowledgeScanning(false);
        }
      }, 3000);
    } catch (e) {
      console.error("Failed to start knowledge scan", e);
      setKnowledgeScanning(false);
    }
  };

  const triggerSingleScan = async (leadId, thinking = false) => {
    setScanningIds(prev => new Set(prev).add(leadId));
    try {
      const url = thinking
        ? `${API_BASE}/knowledge/scan/${leadId}?thinking=true`
        : `${API_BASE}/knowledge/scan/${leadId}`;
      await fetch(url, { method: 'POST' });
      // Poll — thinking scans take longer
      const pollDelay = thinking ? 15000 : 5000;
      const doneDelay = thinking ? 45000 : 12000;
      setTimeout(() => fetchLeads(), pollDelay);
      setTimeout(() => {
        fetchLeads();
        setScanningIds(prev => {
          const next = new Set(prev);
          next.delete(leadId);
          return next;
        });
      }, doneDelay);
    } catch (e) {
      console.error("Failed to trigger single scan", e);
      setScanningIds(prev => {
        const next = new Set(prev);
        next.delete(leadId);
        return next;
      });
    }
  };

  const fetchLeads = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/leads`);
      const data = await res.json();
      setLeads(data.leads || []);
    } catch (e) {
      console.error("Failed to fetch leads", e);
    }
    if (!silent) setLoading(false);
  };

  const stopScan = async () => {
    if (!window.confirm("Are you sure you want to STOP the current scan?")) return;
    try {
      const res = await fetch(`${API_BASE}/stop-scan`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        alert(data.message);
        setSyncing(false);
      } else {
        alert("Failed to stop scan: " + data.message);
      }
    } catch (e) {
      console.error("Stop scan failed", e);
      alert("Failed to send stop request");
    }
  };

  const triggerScan = async (e) => {
    if (e) e.preventDefault();
    setSyncing(true);
    try {
      await fetch(`${API_BASE}/sync-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scraperSettings)
      });
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        if (elapsed >= 180000) { clearInterval(pollInterval); setSyncing(false); }
      }, 5000);
    } catch (e) {
      console.error("Agent trigger failed", e);
      setSyncing(false);
    }
  };

  const triggerSingleScraper = async (scraperName) => {
    setSyncing(true);
    setShowConsole(true);
    clearConsoleLogs();
    const singleSettings = {
      planhub: false,
      bidplanroom: false,
      loydbuildsbetter: false,
      buildingconnected: false,
      use_gdrive: scraperSettings.use_gdrive,
      [scraperName]: true,
    };
    try {
      await fetch(`${API_BASE}/sync-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(singleSettings),
      });
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        if (elapsed >= 180000) { clearInterval(pollInterval); setSyncing(false); }
      }, 5000);
    } catch (e) {
      console.error("Single scraper trigger failed", e);
      setSyncing(false);
    }
  };

  const clearAllLeads = async () => {
    if (!window.confirm('Are you sure you want to clear ALL leads? This will create a backup first.')) return;
    setClearing(true);
    try {
      const res = await fetch(`${API_BASE}/clear-leads`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const data = await res.json();
      await fetchLeads();
      alert(`Successfully cleared ${data.count} leads (backup created)`);
    } catch (e) {
      alert("Failed to clear leads.");
    }
    setClearing(false);
  };

  const refreshAllLeads = async () => {
    if (!window.confirm('Clear all existing leads and start a fresh scan?')) return;
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/refresh-leads`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const data = await res.json();
      setLeads([]);
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        if (elapsed >= 180000) { clearInterval(pollInterval); setRefreshing(false); }
      }, 5000);
      alert(`Cleared ${data.cleared_count} leads. Fresh scan started!`);
    } catch (e) {
      alert("Failed to refresh.");
      setRefreshing(false);
    }
  };

  const deduplicateLeads = async () => {
    if (!window.confirm('Remove duplicate leads by merging their information?')) return;
    setDeduplicating(true);
    try {
      const res = await fetch(`${API_BASE}/deduplicate-leads`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const data = await res.json();
      await fetchLeads();
      alert(`Removed ${data.removed_count} duplicate leads!\nBefore: ${data.original_count} | After: ${data.deduplicated_count}`);
    } catch (e) {
      alert("Failed to deduplicate.");
    }
    setDeduplicating(false);
  };

  const addLead = async () => {
    try {
      const res = await fetch(`${API_BASE}/leads`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) });
      if (res.ok) { await fetchLeads(); setAddModal(false); setFormData(emptyForm); }
      else alert('Failed to add lead');
    } catch (e) { alert("Failed to add lead."); }
  };

  const updateLead = async () => {
    try {
      const res = await fetch(`${API_BASE}/leads/${editModal.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) });
      if (res.ok) { await fetchLeads(); setEditModal(null); setFormData(emptyForm); }
      else alert('Failed to update lead');
    } catch (e) { alert("Failed to update lead."); }
  };

  const deleteLead = async (lead) => {
    if (!window.confirm(`Delete "${lead.name}"?`)) return;
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}`, { method: 'DELETE' });
      if (res.ok) await fetchLeads();
    } catch (e) { alert("Failed to delete lead."); }
  };

  // Toggle highlight color or strikethrough for a lead
  const toggleLeadStyle = async (lead, field, value) => {
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value })
      });
      if (res.ok) fetchLeads(true);
    } catch (e) { console.error(`Failed to toggle ${field}:`, e); }
  };

  // Get highlight background class
  const getHighlightBg = (highlight) => {
    switch (highlight) {
      case 'green': return 'bg-green-900/40 border-l-4 border-l-green-500';
      case 'yellow': return 'bg-yellow-900/40 border-l-4 border-l-yellow-500';
      case 'red': return 'bg-red-900/40 border-l-4 border-l-red-500';
      default: return '';
    }
  };

  const openEditModal = (lead) => {
    setFormData({
      name: lead.name || '', company: lead.company || '', gc: lead.gc || '',
      contact_name: lead.contact_name || '', contact_email: lead.contact_email || '',
      contact_phone: lead.contact_phone || '', location: lead.location || '',
      full_address: lead.full_address || '', bid_date: lead.bid_date || '',
      description: lead.description || '', files_link: lead.files_link || '',
      download_link: lead.download_link || '', site: lead.site || 'Manual Entry',
      sprinklered: lead.sprinklered || false, has_budget: lead.has_budget || false
    });
    setEditModal(lead);
  };

  const openAddModal = () => { setFormData(emptyForm); setAddModal(true); };

  // Console
  const fetchConsoleLogs = async () => {
    try { const res = await fetch(`${API_BASE}/console-logs?lines=200`); const data = await res.json(); setConsoleLogs(data.logs || []); } catch (e) { }
  };
  const fetchScraperStatus = async () => {
    try { const res = await fetch(`${API_BASE}/scraper-status`); const data = await res.json(); setScraperStatus(data); return data; } catch (e) { return null; }
  };
  const clearConsoleLogs = async () => {
    try { await fetch(`${API_BASE}/console-logs`, { method: 'DELETE' }); setConsoleLogs([]); } catch (e) { }
  };

  // Point-to-File / File Browser
  const openPointToFile = async (leadId) => {
    setPointToFileLoading(true);
    setSelectedFile(null);
    setViewerPage(0);
    setViewerPageCount(0);
    setViewerImageUrl(null);
    try {
      const res = await fetch(`${API_BASE}/knowledge/files/${leadId}`);
      const data = await res.json();
      setPointToFileModal({ lead_id: leadId, files: data.files || [], error: data.error });
    } catch (e) {
      setPointToFileModal({ lead_id: leadId, files: [], error: 'Failed to load files' });
    }
    setPointToFileLoading(false);
  };

  const selectFileForViewing = async (leadId, relPath) => {
    setSelectedFile(relPath);
    setViewerPage(0);
    setViewerLoading(true);
    setViewerImageUrl(null);
    try {
      const pcRes = await fetch(`${API_BASE}/knowledge/files/${leadId}/pagecount/${encodeURIComponent(relPath)}`);
      const pcData = await pcRes.json();
      setViewerPageCount(pcData.pages || 0);
    } catch { setViewerPageCount(0); }
    setViewerImageUrl(`${API_BASE}/knowledge/files/${leadId}/view/${encodeURIComponent(relPath)}?page=0&dpi=150`);
    setViewerLoading(false);
  };

  const navigateViewerPage = (leadId, relPath, newPage) => {
    if (newPage < 0 || newPage >= viewerPageCount) return;
    setViewerPage(newPage);
    setViewerImageUrl(`${API_BASE}/knowledge/files/${leadId}/view/${encodeURIComponent(relPath)}?page=${newPage}&dpi=150`);
  };

  const setFileClassification = async (leadId, relPath, classification) => {
    try {
      await fetch(`${API_BASE}/knowledge/files/${leadId}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path: relPath, classification })
      });
      // Refresh the file list
      openPointToFile(leadId);
    } catch (e) {
      alert('Failed to set classification');
    }
  };

  const setBatchClassification = async (leadId, classification) => {
    try {
      const files = pointToFileModal?.files || [];
      if (files.length === 0) return;
      const overrides = {};
      files.forEach(f => { overrides[f.rel_path] = classification; });
      await fetch(`${API_BASE}/knowledge/files/${leadId}/override-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overrides })
      });
      openPointToFile(leadId);
    } catch (e) {
      alert('Failed to batch classify');
    }
  };

  const triggerFolderPicker = async () => {
    try {
      const res = await fetch(`${API_BASE}/system/pick-folder`, { method: 'POST' });
      const data = await res.json();
      if (data.path) {
        setFormData(prev => ({ ...prev, files_link: data.path }));
      }
    } catch (e) {
      console.error("Failed to pick folder", e);
    }
  };

  const openFolderBrowser = async () => {
    setFolderBrowserModal(true); setFolderBrowserLoading(true);
    try {
      const r = await fetch(API_BASE + '/browse-directory', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '' })
      });
      const d = await r.json();
      setFolderBrowserPath(d.current || ''); setFolderBrowserItems(d.items || []);
    } catch (e) { console.error('Fail:', e); }
    setFolderBrowserLoading(false);
  };
  const browseTo = async (p) => {
    setFolderBrowserLoading(true);
    try {
      const r = await fetch(API_BASE + '/browse-directory', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: p })
      });
      const d = await r.json();
      setFolderBrowserPath(d.current || ''); setFolderBrowserItems(d.items || []);
    } catch (e) { console.error('Fail:', e); alert('Access denied'); }
    setFolderBrowserLoading(false);
  };
  const selectFolder = () => {
    if (folderBrowserPath) setFormData(prev => ({ ...prev, files_link: folderBrowserPath }));
    setFolderBrowserModal(false);
  };
  const goUpDirectory = () => {
    if (!folderBrowserPath) { browseTo(''); return; }
    const ps = folderBrowserPath.split(/[\\\/]/).filter(Boolean);
    if (ps.length <= 1) browseTo('');
    else { ps.pop(); const isWin = folderBrowserPath.includes(String.fromCharCode(92)); browseTo(ps.join(isWin ? String.fromCharCode(92) : '/') || '/'); }
  };
  // Poll logs
  useEffect(() => {
    let interval;
    if (showConsole || syncing) {
      fetchConsoleLogs(); fetchScraperStatus();
      interval = setInterval(() => { fetchConsoleLogs(); fetchScraperStatus(); }, 2000);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [showConsole, syncing]);

  useEffect(() => {
    if (consoleEndRef.current && !consoleMinimized) consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [consoleLogs, consoleMinimized]);

  // Poll knowledge status while scanning
  useEffect(() => {
    let interval;
    if (knowledgeScanning) {
      interval = setInterval(async () => {
        await fetchKnowledgeStatus();
        await fetchLeads();
      }, 3000);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [knowledgeScanning]);

  // Check if scanning stopped
  useEffect(() => {
    if (knowledgeStatus && !knowledgeStatus.running && knowledgeScanning) {
      setKnowledgeScanning(false);
    }
  }, [knowledgeStatus]);


  return (
    <div className={`min-h-screen bg-slate-950 text-slate-100 p-8 font-sans ${showConsole && !consoleMinimized ? 'pb-96' : ''}`}>
      <div className="max-w-[95vw] mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between bg-slate-900 border border-slate-800 rounded-2xl p-3">
          <div className="flex items-center gap-4">
            <img src="/logo.png" alt="Marmic Fire & Safety" className="h-14 w-auto" />
            <h1 className="text-sm font-bold tracking-widest text-slate-500 uppercase">
              Planroom<span className="text-[#ed2028]">Genius</span> v2.0
            </h1>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2 items-center">
              <button onClick={openAddModal} className="px-3 py-2 rounded-lg bg-green-600 text-white text-sm font-semibold hover:bg-green-500 transition flex items-center gap-1.5"><Plus size={16} />Add Lead</button>
              <button onClick={() => { triggerScan(); setShowConsole(true); clearConsoleLogs(); }} disabled={syncing} className={`bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-5 rounded-lg transition-all shadow-lg shadow-blue-900/20 flex items-center gap-2 text-sm ${syncing ? 'opacity-50 cursor-not-allowed' : ''}`}>
                {syncing ? (<><svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Scanning...</>) : "Scan"}
              </button>
              {syncing && (
                <button onClick={stopScan} className="bg-red-600 hover:bg-red-500 text-white font-bold py-2 px-3 rounded-lg transition-all shadow-lg shadow-red-900/20 text-sm flex items-center gap-1" title="Stop Scan">
                  <X size={16} />Stop
                </button>
              )}
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                disabled={syncing}
                className="px-3 py-2 rounded-lg bg-slate-800 text-slate-400 text-sm hover:bg-slate-700 transition flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronDown size={14} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                Advanced
              </button>
              <div className="relative">
                <button onClick={() => setShowUtilityMenu(!showUtilityMenu)} className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300 transition" title="More options"><Settings size={18} /></button>
                {showUtilityMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowUtilityMenu(false)} />
                    <div className="absolute right-0 mt-2 w-56 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
                      <div className="px-4 py-2.5 border-b border-slate-700">
                        <div className="flex items-center gap-2 text-xs text-slate-400 mb-1">
                          {gdriveStatus?.status === 'connected' ? <Cloud size={14} className="text-green-400" /> : <CloudOff size={14} className="text-slate-500" />}
                          Google Drive
                        </div>
                        {gdriveStatus?.status === 'connected' ? (
                          <span className="text-xs text-green-400">Connected</span>
                        ) : gdriveStatus?.status === 'not_authenticated' ? (
                          <button onClick={connectGdrive} disabled={connectingGdrive} className="text-xs text-blue-400 hover:text-blue-300 transition">{connectingGdrive ? 'Connecting...' : 'Click to connect'}</button>
                        ) : (
                          <span className="text-xs text-slate-500">{gdriveStatus?.message || 'Not configured'}</span>
                        )}
                      </div>
                      <button onClick={() => { setShowConsole(!showConsole); if (!showConsole) fetchConsoleLogs(); setShowUtilityMenu(false); }} className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700 transition flex items-center gap-2">
                        <Terminal size={14} />{showConsole ? 'Hide Console' : 'Show Console'}{syncing && <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>}
                      </button>
                      <button onClick={() => { fetchLeads(); setShowUtilityMenu(false); }} disabled={loading} className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700 transition disabled:opacity-50">{loading ? 'Refreshing...' : 'Refresh Leads'}</button>
                      <button onClick={() => { deduplicateLeads(); setShowUtilityMenu(false); }} disabled={deduplicating} className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700 transition disabled:opacity-50">{deduplicating ? 'Cleaning...' : 'Remove Duplicates'}</button>
                      <button onClick={() => { refreshAllLeads(); setShowUtilityMenu(false); }} disabled={refreshing} className="w-full px-4 py-2.5 text-left text-sm text-purple-300 hover:bg-slate-700 transition disabled:opacity-50">{refreshing ? 'Refreshing...' : 'Clear & Rescan'}</button>
                      <button onClick={() => { clearAllLeads(); setShowUtilityMenu(false); }} disabled={clearing} className="w-full px-4 py-2.5 text-left text-sm text-yellow-300 hover:bg-slate-700 transition disabled:opacity-50">{clearing ? 'Clearing...' : 'Clear All Leads'}</button>
                    </div>
                  </>
                )}
              </div>
            </div>
            {showAdvanced && (
              <div className="flex items-center gap-2 flex-wrap justify-end">
                <span className="text-xs text-slate-500">Run individually:</span>
                {[
                  { key: 'planhub', label: 'PlanHub', bg: 'bg-blue-600/20', bgHover: 'hover:bg-blue-600/30', text: 'text-blue-400' },
                  { key: 'bidplanroom', label: 'Bidplanroom', bg: 'bg-emerald-600/20', bgHover: 'hover:bg-emerald-600/30', text: 'text-emerald-400' },
                  { key: 'loydbuildsbetter', label: 'Loyd Builds Better', bg: 'bg-amber-600/20', bgHover: 'hover:bg-amber-600/30', text: 'text-amber-400' },
                  { key: 'buildingconnected', label: 'BuildingConnected', bg: 'bg-purple-600/20', bgHover: 'hover:bg-purple-600/30', text: 'text-purple-400' },
                ].map(s => (
                  <button
                    key={s.key}
                    onClick={() => triggerSingleScraper(s.key)}
                    disabled={syncing}
                    className={`px-3 py-1.5 rounded-lg ${s.bg} ${s.text} ${s.bgHover} text-xs font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6 flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-2xl p-2">
          <button onClick={() => setActiveTab('bid')} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition ${activeTab === 'bid' ? 'bg-[#ed2028] text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}>
            <Building2 size={16} />Bid Board
          </button>
          <button onClick={() => setActiveTab('takeoff')} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition ${activeTab === 'takeoff' ? 'bg-red-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}>
            <Zap size={16} />Takeoff
          </button>
        </div>

        {/* =================== BID BOARD TAB =================== */}
        <div className={activeTab === 'bid' ? '' : 'hidden'}>
          <LeadTable
            title="All Active Opportunities"
            data={filteredLeads}
            showSiteFilter={true}
            uniqueSites={uniqueSites}
            siteFilter={siteFilter}
            setSiteFilter={setSiteFilter}
            sortConfig={sortConfig}
            setSortConfig={setSortConfig}
            triggerKnowledgeScan={triggerKnowledgeScan}
            knowledgeScanning={knowledgeScanning}
            triggerSingleScan={triggerSingleScan}
            scanningIds={scanningIds}
            toggleLeadStyle={toggleLeadStyle}
            openEditModal={openEditModal}
            deleteLead={deleteLead}
            setCompanyPopup={setCompanyPopup}
            setDescriptionPopup={setDescriptionPopup}
            API_BASE={API_BASE}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            showHidden={showHidden}
            setShowHidden={setShowHidden}
            openPointToFile={openPointToFile}
          />
        </div>

        {/* =================== TAKEOFF TAB =================== */}
        <div className={activeTab === 'takeoff' ? '' : 'hidden'}>
          {activeTab === 'takeoff' && <TakeoffPanel />}
        </div>

        {/* =================== FILE BROWSER MODAL =================== */}
        {pointToFileModal && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => { setPointToFileModal(null); setSelectedFile(null); }}>
            <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-6 max-w-7xl w-full mx-4 shadow-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-xl font-bold text-white flex items-center gap-2"><FolderOpen className="text-blue-400" size={20} />File Browser</h3>
                  <p className="text-xs text-slate-500 mt-1">Click a file to preview. Use classification buttons to tag files.</p>
                </div>
                <button onClick={() => { setPointToFileModal(null); setSelectedFile(null); }} className="text-slate-400 hover:text-white transition-colors"><X size={24} /></button>
              </div>

              {pointToFileModal.error && <div className="text-red-400 text-sm mb-3">{pointToFileModal.error}</div>}

              {/* Two-panel layout */}
              <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
                {/* Left panel - File list */}
                <div className="w-80 flex-shrink-0 overflow-y-auto border border-slate-700 rounded-xl bg-slate-800/50 p-3">
                  {pointToFileModal.files?.length === 0 ? (
                    <div className="text-center py-12 text-slate-600 italic text-sm">No PDF files found. Make sure files have been downloaded.</div>
                  ) : (
                    <>
                      {/* Batch action bar */}
                      <div className="flex gap-1 mb-3 pb-2 border-b border-slate-700/50">
                        <span className="text-[9px] text-slate-500 font-medium self-center mr-1">All:</span>
                        {[['plan', 'Plans'], ['spec', 'Specs'], ['other', 'Other'], ['ignore', 'Ignore']].map(([cls, label]) => (
                          <button
                            key={cls}
                            onClick={() => setBatchClassification(pointToFileModal.lead_id, cls)}
                            className={`px-2 py-1 rounded text-[9px] font-semibold border transition ${classColor(cls)} hover:brightness-125`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {['plan', 'spec', 'other', 'ignore'].map(group => {
                        const groupFiles = pointToFileModal.files?.filter(f => f.classification === group) || [];
                        if (groupFiles.length === 0) return null;
                        return (
                          <div key={group} className="mb-4">
                            <div className={`text-[10px] font-bold uppercase tracking-widest mb-2 px-1 ${group === 'plan' ? 'text-blue-400' : group === 'spec' ? 'text-green-400' : group === 'ignore' ? 'text-red-400' : 'text-slate-400'}`}>
                              {group === 'plan' ? 'Plans' : group === 'spec' ? 'Specs' : group === 'ignore' ? 'Ignored' : 'Other'} ({groupFiles.length})
                            </div>
                            {groupFiles.map((file, idx) => (
                              <div
                                key={`${group}-${idx}`}
                                onClick={() => selectFileForViewing(pointToFileModal.lead_id, file.rel_path)}
                                className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer mb-1 transition-all ${file.classification === 'ignore' ? 'opacity-50' : ''} ${selectedFile === file.rel_path ? 'bg-blue-600/20 border border-blue-500/40 ring-1 ring-blue-500/30' : 'hover:bg-slate-700/50 border border-transparent'}`}
                              >
                                <div className="w-8 h-10 bg-slate-950 rounded flex-shrink-0 flex items-center justify-center">
                                  <FileText size={14} className={`${file.classification === 'plan' ? 'text-blue-500' : file.classification === 'spec' ? 'text-green-500' : file.classification === 'ignore' ? 'text-red-500' : 'text-slate-600'}`} />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className={`text-[11px] font-medium truncate ${file.classification === 'ignore' ? 'text-slate-500 line-through' : 'text-white'}`} title={file.filename}>{file.filename}</div>
                                  <div className="text-[10px] text-slate-500">{file.size_kb > 1024 ? `${(file.size_kb / 1024).toFixed(1)} MB` : `${file.size_kb} KB`}</div>
                                  {/* Classification buttons */}
                                  <div className="flex gap-1 mt-1">
                                    {['plan', 'spec', 'other', 'ignore'].map(cls => (
                                      <button
                                        key={cls}
                                        onClick={(e) => { e.stopPropagation(); setFileClassification(pointToFileModal.lead_id, file.rel_path, cls); }}
                                        className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border transition ${file.classification === cls ? classColor(cls) + ' ring-1 ring-white/20' : 'bg-slate-700/50 text-slate-600 border-slate-600/50 hover:text-white hover:bg-slate-600'}`}
                                      >
                                        {cls === 'ignore' ? 'Ign' : cls.charAt(0).toUpperCase() + cls.slice(1)}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </>
                  )}
                </div>

                {/* Right panel - Page viewer */}
                <div className="flex-1 min-w-0 flex flex-col border border-slate-700 rounded-xl bg-slate-950/50 overflow-hidden">
                  {selectedFile ? (
                    <>
                      {/* Page navigation */}
                      <div className="flex items-center justify-between px-4 py-2 bg-slate-800/80 border-b border-slate-700">
                        <button
                          onClick={() => navigateViewerPage(pointToFileModal.lead_id, selectedFile, viewerPage - 1)}
                          disabled={viewerPage <= 0}
                          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors flex items-center gap-1"
                        >
                          <ChevronLeft size={14} /> Prev
                        </button>
                        <span className="text-xs text-slate-300 font-medium">
                          Page {viewerPage + 1} of {viewerPageCount || '?'}
                        </span>
                        <button
                          onClick={() => navigateViewerPage(pointToFileModal.lead_id, selectedFile, viewerPage + 1)}
                          disabled={viewerPage >= viewerPageCount - 1}
                          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors flex items-center gap-1"
                        >
                          Next <ChevronRight size={14} />
                        </button>
                      </div>
                      {/* Page image */}
                      <div className="flex-1 overflow-auto flex items-start justify-center p-2">
                        {viewerImageUrl ? (
                          <img
                            src={viewerImageUrl}
                            alt={`Page ${viewerPage + 1}`}
                            className="max-w-full h-auto"
                            onLoad={() => setViewerLoading(false)}
                            onError={() => setViewerLoading(false)}
                          />
                        ) : (
                          <div className="text-slate-600 text-sm mt-20">Loading...</div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-slate-600">
                      <div className="text-center">
                        <FileText size={48} className="mx-auto mb-3 opacity-30" />
                        <p className="text-sm">Select a file to preview</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Bottom bar */}
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-700/50">
                <div className="text-[11px] text-slate-500">
                  {(() => {
                    const files = pointToFileModal.files || [];
                    const plans = files.filter(f => f.classification === 'plan').length;
                    const specs = files.filter(f => f.classification === 'spec').length;
                    const other = files.filter(f => f.classification === 'other').length;
                    const ignored = files.filter(f => f.classification === 'ignore').length;
                    return `${plans} Plan${plans !== 1 ? 's' : ''}, ${specs} Spec${specs !== 1 ? 's' : ''}, ${other} Other${ignored ? `, ${ignored} Ignored` : ''}`;
                  })()}
                </div>
                <div className="flex gap-3">
                  <button onClick={() => { setPointToFileModal(null); setSelectedFile(null); }} className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg transition-colors text-sm">Close</button>
                  <button onClick={() => { triggerSingleScan(pointToFileModal.lead_id); setPointToFileModal(null); setSelectedFile(null); }} className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded-lg transition-colors flex items-center gap-2 text-sm"><RefreshCw size={14} />Rescan with Changes</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* =================== COMPANY POPUP =================== */}
        {companyPopup && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setCompanyPopup(null)}>
            <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-8 max-w-md w-full mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-2xl font-bold text-white flex items-center gap-2"><Building2 className="text-orange-500" size={24} />Company Details</h3>
                <button onClick={() => setCompanyPopup(null)} className="text-slate-400 hover:text-white transition-colors"><X size={24} /></button>
              </div>
              <div className="space-y-4">
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Company</div>
                  <div className="text-lg font-semibold text-white">{companyPopup.company !== "N/A" ? companyPopup.company : <span className="text-slate-600 italic">No Company</span>}</div>
                  {companyPopup.gc && companyPopup.gc !== "N/A" && <div className="text-sm text-slate-400 mt-1">GC: {companyPopup.gc}</div>}
                </div>
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1"><User size={12} />Contact Name</div>
                  <div className="text-lg font-medium text-white">{companyPopup.contact_name !== "N/A" ? companyPopup.contact_name : <span className="text-slate-600 italic">No Contact</span>}</div>
                </div>
                {companyPopup.contact_email && (
                  <div className="bg-slate-800/50 rounded-lg p-4">
                    <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1"><Mail size={12} />Email</div>
                    <a href={`mailto:${companyPopup.contact_email}`} className="text-lg text-orange-400 hover:text-orange-300 transition-colors break-all">{companyPopup.contact_email}</a>
                  </div>
                )}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Project Info</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2 text-slate-300"><MapPin size={14} className="text-slate-500" />{companyPopup.location || "N/A"}</div>
                    <div className="flex items-center gap-2 text-slate-300"><Calendar size={14} className="text-slate-500" />Bid Date: {formatDate(companyPopup.bid_date)}</div>
                  </div>
                </div>
              </div>
              {companyPopup.also_listed_by && companyPopup.also_listed_by.length > 0 && (
                <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4 mt-4">
                  <div className="text-xs text-blue-400 uppercase tracking-wide mb-2 flex items-center gap-1">
                    <Building2 size={12} />Also Listed By
                  </div>
                  <ul className="space-y-1">
                    {companyPopup.also_listed_by.map((entry, idx) => (
                      <li key={idx} className="text-sm text-slate-300 flex items-center gap-2">
                        <Building2 size={12} className="text-slate-500" />
                        {entry.gc || 'Unknown'} <span className="text-slate-500 text-xs">(via {entry.site})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <button onClick={() => setCompanyPopup(null)} className="mt-6 w-full bg-[#ed2028] hover:bg-red-600 text-white font-bold py-3 rounded-lg transition-colors">Close</button>
            </div>
          </div>
        )}

        {/* =================== DESCRIPTION POPUP =================== */}
        {descriptionPopup && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setDescriptionPopup(null)}>
            <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-4 max-w-3xl w-full mx-4 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-between items-start mb-4">
                <h3 className="text-xl font-bold text-white flex items-center gap-2"><Description className="text-orange-500" size={20} />Project Details</h3>
                <div className="flex gap-2">
                  {descriptionPopup.url && (
                    <a href={descriptionPopup.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-blue-300 px-3 py-1 rounded-full transition-colors">
                      <ExternalLink size={12} /> Open Project
                    </a>
                  )}
                  <button onClick={() => { setActiveTab('takeoff'); setDescriptionPopup(null); }} className="flex items-center gap-1 text-xs bg-slate-700 hover:bg-red-600 text-slate-300 hover:text-white px-3 py-1 rounded-full transition-colors">
                    <Zap size={12} /> Run Takeoff
                  </button>
                  <button onClick={() => setDescriptionPopup(null)} className="text-slate-400 hover:text-white transition-colors"><X size={20} /></button>
                </div>
              </div>
              <div className="space-y-2">
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Project Name</div>
                  <div className="text-base font-semibold text-white">{descriptionPopup.name || 'N/A'}</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Description / Full Address</div>
                  <div className="text-sm text-slate-300 whitespace-pre-wrap">{stripHtml(descriptionPopup.description) || descriptionPopup.full_address || 'No description available'}</div>
                </div>
                <div className="flex gap-2">
                  <div className="bg-slate-800/50 rounded-lg p-3 flex-1">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1"><MapPin size={10} />Location</div>
                    <div className="text-sm text-slate-300">{descriptionPopup.location || 'N/A'}</div>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-3 flex-1">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Source</div>
                    <div className="text-sm text-slate-300">{descriptionPopup.site || descriptionPopup.source || 'N/A'}</div>
                    {descriptionPopup.url && (
                      <a href={descriptionPopup.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-400 hover:text-blue-300 underline underline-offset-2 break-all mt-1 block">
                        {descriptionPopup.url}
                      </a>
                    )}
                  </div>
                </div>
                {descriptionPopup.also_listed_by && descriptionPopup.also_listed_by.length > 0 && (
                  <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-3">
                    <div className="text-[10px] text-blue-400 uppercase tracking-wide mb-2 flex items-center gap-1"><Building2 size={10} />Also Bidding</div>
                    <ul className="space-y-1">
                      {descriptionPopup.also_listed_by.map((entry, idx) => (
                        <li key={idx} className="text-sm text-slate-300 flex items-center gap-2">
                          <Building2 size={12} className="text-slate-500" />
                          {entry.gc || 'Unknown'} <span className="text-slate-500 text-xs">(via {entry.site})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex gap-2 flex-wrap">
                  {descriptionPopup.has_budget && <span className="text-[10px] bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full border border-green-500/30">Has Budget</span>}
                  {descriptionPopup.knowledge_badges && descriptionPopup.knowledge_badges.map((b, idx) => (
                    <span key={idx} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border ${badgeColor(b)} cursor-default`}>
                      {b}
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                        {badgeHover(b, descriptionPopup)}
                      </span>
                    </span>
                  ))}
                  {descriptionPopup.knowledge_last_scanned && !descriptionPopup.sprinklered && (
                    <span className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default ${badgeColor('NON-SPRINKLED')}`}>
                      NON-SPRINKLED
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                        {badgeHover('NON-SPRINKLED', descriptionPopup)}
                      </span>
                    </span>
                  )}
                  {detectProjectTags(descriptionPopup).map((pt, idx) => (
                    <span key={`pt-${idx}`} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default ${pt.color}`}>
                      {pt.label}
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                        {pt.hover}
                      </span>
                    </span>
                  ))}
                  {descriptionPopup.knowledge_bid_risk_flags && descriptionPopup.knowledge_bid_risk_flags.map((flag, idx) => (
                    <span key={`rf-${idx}`} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default bg-red-500/10 text-red-400 border-red-500/20`}>
                      {flag}
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-red-300 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                        Bid risk: {flag}
                      </span>
                    </span>
                  ))}
                </div>

                {/* AI Analysis Section */}
                {descriptionPopup.knowledge_last_scanned && (
                  <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 mt-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Brain className="text-purple-400" size={18} />
                      <span className="text-sm font-semibold text-purple-300">AI Fire Alarm Analysis</span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs mb-3">
                      <div className="bg-slate-800/50 rounded p-2">
                        <span className="text-slate-500">System Type:</span>
                        <span className="ml-1 text-white capitalize">{descriptionPopup.knowledge_system_type || 'Unknown'}</span>
                      </div>

                    </div>

                    {descriptionPopup.knowledge_required_vendors && descriptionPopup.knowledge_required_vendors.length > 0 && (
                      <div className="text-xs mb-2">
                        <span className="text-slate-500">Required Vendors:</span>
                        <span className="ml-1 text-orange-300">{descriptionPopup.knowledge_required_vendors.join(', ')}</span>
                      </div>
                    )}

                    {descriptionPopup.knowledge_required_manufacturers && descriptionPopup.knowledge_required_manufacturers.length > 0 && (
                      <div className="text-xs mb-2">
                        <span className="text-slate-500">Required Manufacturers:</span>
                        <span className="ml-1 text-amber-300">{descriptionPopup.knowledge_required_manufacturers.join(', ')}</span>
                      </div>
                    )}

                    {descriptionPopup.knowledge_required_codes && descriptionPopup.knowledge_required_codes.length > 0 && (
                      <div className="text-xs mb-2">
                        <span className="text-slate-500">Code Requirements:</span>
                        <span className="ml-1 text-cyan-300">{descriptionPopup.knowledge_required_codes.join(', ')}</span>
                      </div>
                    )}

                    {descriptionPopup.knowledge_deal_breakers && descriptionPopup.knowledge_deal_breakers.length > 0 && (
                      <div className="text-xs mb-2">
                        <span className="text-red-400">⚠️ Deal Breakers:</span>
                        <span className="ml-1 text-red-300">{descriptionPopup.knowledge_deal_breakers.join(', ')}</span>
                      </div>
                    )}

                    {descriptionPopup.knowledge_evidence && (
                      <div className="mt-3 pt-3 border-t border-purple-500/20">
                        <div className="text-xs text-slate-500 mb-2">Evidence (page + snippet)</div>
                        <div className="space-y-1 text-[11px]">
                          {Object.entries(descriptionPopup.knowledge_evidence).map(([category, entries]) => {
                            if (!Array.isArray(entries) || entries.length === 0) return null;
                            return (
                              <div key={category} className="bg-slate-800/40 rounded p-2">
                                <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{category.replaceAll('_', ' ')}</div>
                                <ul className="space-y-1">
                                  {entries.map((entry, idx) => (
                                    <li key={`${category}-${idx}`} className="text-slate-300">
                                      <span className="text-purple-300 font-medium">{entry.claim || 'Claim'}</span>
                                      <span className="text-slate-400"> — Pg {entry.page}: </span>
                                      <span>{entry.quote || 'No quote provided'}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {descriptionPopup.knowledge_validation_warnings && descriptionPopup.knowledge_validation_warnings.length > 0 && (
                      <div className="mt-2 text-[11px] bg-yellow-900/20 border border-yellow-500/30 rounded p-2 text-yellow-200">
                        <div className="font-semibold mb-1">Evidence validation warnings</div>
                        <ul className="list-disc list-inside space-y-0.5">
                          {descriptionPopup.knowledge_validation_warnings.map((warning, idx) => (
                            <li key={idx}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {descriptionPopup.knowledge_notes && (
                      <div className="mt-3 pt-3 border-t border-purple-500/20">
                        <div className="text-xs text-slate-500 mb-1">Analysis Notes:</div>
                        <div className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-800/50 rounded p-2">
                          {descriptionPopup.knowledge_notes}
                        </div>
                      </div>
                    )}

                    {descriptionPopup.knowledge_addendums && descriptionPopup.knowledge_addendums.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-orange-500/20">
                        <div className="text-xs text-orange-400 font-semibold mb-2 flex items-center gap-1">
                          <AlertTriangle size={12} />
                          Addendums / Revisions ({descriptionPopup.knowledge_addendums.length})
                        </div>
                        <div className="space-y-1">
                          {descriptionPopup.knowledge_addendums.map((add, idx) => (
                            <div key={idx} className="text-xs bg-orange-900/20 rounded p-2 flex justify-between items-center">
                              <span className="text-orange-200 truncate max-w-[250px]">{add.filename}</span>
                              {add.modified && (
                                <span className="text-[10px] text-orange-400/60">{new Date(add.modified).toLocaleDateString()}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-[10px] text-slate-600 mt-2 flex justify-between">
                      <span>Scanned: {new Date(descriptionPopup.knowledge_last_scanned).toLocaleDateString()}</span>
                      {descriptionPopup.knowledge_file_count && (
                        <span>Files: {descriptionPopup.knowledge_file_count}</span>
                      )}
                    </div>
                  </div>
                )}

                {!descriptionPopup.knowledge_last_scanned && (
                  <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 mt-4 text-center">
                    <Brain className="text-slate-600 mx-auto mb-2" size={20} />
                    <div className="text-xs text-slate-500">Not scanned by Knowledge Scanner yet</div>
                    <div className="text-[10px] text-slate-600 mt-1">Run Knowledge Scan to see AI analysis</div>
                  </div>
                )}
              </div>
              <button onClick={() => setDescriptionPopup(null)} className="mt-6 w-full bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors">Close</button>
            </div>
          </div>
        )}

        {/* Settings Modal */}
        {showSettings && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 animate-fade-in">
            <div className="bg-gray-800 rounded-xl shadow-2xl max-w-md w-full border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-900/50">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <Settings size={20} className="text-blue-400" />
                  Scraper Settings
                </h2>
                <button
                  onClick={() => setShowSettings(false)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Enabled Planrooms</h3>
                  <div className="space-y-3">
                    {[
                      { key: 'planhub', label: 'PlanHub' },
                      { key: 'bidplanroom', label: 'BidPlanroom' },
                      { key: 'loydbuildsbetter', label: 'Loyd Builds Better' },
                      { key: 'buildingconnected', label: 'BuildingConnected' }
                    ].map(({ key, label }) => (
                      <div key={key} className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors">
                        <span className="text-gray-200 font-medium">{label}</span>
                        <button
                          onClick={() => toggleSetting(key)}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 ${scraperSettings[key] ? 'bg-blue-600' : 'bg-gray-600'
                            }`}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${scraperSettings[key] ? 'translate-x-6' : 'translate-x-1'
                              }`}
                          />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-700">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Integrations</h3>
                  <div className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors">
                    <span className="text-gray-200 font-medium">Upload to Google Drive</span>
                    <button
                      onClick={() => toggleSetting('use_gdrive')}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 ${scraperSettings['use_gdrive'] ? 'bg-green-600' : 'bg-gray-600'
                        }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${scraperSettings['use_gdrive'] ? 'translate-x-6' : 'translate-x-1'
                          }`}
                      />
                    </button>
                  </div>
                </div>
              </div>

              <div className="p-4 border-t border-gray-700 bg-gray-900/30 flex justify-end">
                <button
                  onClick={() => setShowSettings(false)}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors font-medium"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        )}

        {/* =================== CONSOLE PANEL =================== */}
        {showConsole && (
          <div className={`fixed bottom-0 left-0 right-0 bg-slate-900 border-t-2 border-slate-700 shadow-2xl z-40 transition-all ${consoleMinimized ? 'h-12' : 'h-80'}`}>
            <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700">
              <div className="flex items-center gap-3">
                <Terminal size={16} className="text-green-400" />
                <span className="text-sm font-semibold text-white">Scraper Console</span>
                {scraperStatus?.running && <span className="flex items-center gap-2 text-xs text-green-400"><span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>{scraperStatus.current_step || 'Running...'}</span>}
                {scraperStatus && !scraperStatus.running && scraperStatus.last_status && <span className="text-xs text-slate-400">Last: {scraperStatus.last_status}</span>}
              </div>
              <div className="flex items-center gap-2">
                {scraperStatus?.leads_found && <span className="text-xs text-slate-400">BC: {scraperStatus.leads_found.buildingconnected} | PH: {scraperStatus.leads_found.planhub}</span>}
                <button onClick={clearConsoleLogs} className="px-2 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition">Clear</button>
                <button onClick={() => setConsoleMinimized(!consoleMinimized)} className="p-1 text-slate-400 hover:text-white transition">{consoleMinimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}</button>
                <button onClick={() => setShowConsole(false)} className="p-1 text-slate-400 hover:text-white transition"><X size={14} /></button>
              </div>
            </div>
            {!consoleMinimized && (
              <div className="h-[calc(100%-40px)] overflow-y-auto p-3 font-mono text-xs">
                {consoleLogs.length === 0 ? (
                  <div className="text-slate-500 italic">No logs yet. Click "Scan" to start scraping...</div>
                ) : consoleLogs.map((log, i) => {
                  const tagColors = { '[BC]': 'text-cyan-400', '[PH]': 'text-violet-400', '[LBB]': 'text-amber-400', '[BPR]': 'text-emerald-400' };
                  const tagMatch = log.match(/^\[(?:BC|PH|LBB|BPR)\]/);
                  const lineColor = log.includes('ERROR') ? 'text-red-400' : log.includes('TIMEOUT') ? 'text-yellow-400' : log.includes('OK') || log.includes('Complete') ? 'text-green-400' : log.includes('LOGIN') ? 'text-orange-400 font-bold' : log.includes('Found') ? 'text-blue-400' : 'text-slate-300';
                  return (
                    <div key={i} className={`py-0.5 ${lineColor}`}>
                      {tagMatch ? <><span className={`${tagColors[tagMatch[0]]} font-bold`}>{tagMatch[0]}</span>{log.slice(tagMatch[0].length)}</> : log}
                    </div>
                  );
                })}
                <div ref={consoleEndRef} />
              </div>
            )}
          </div>
        )}

        {/* =================== ADD/EDIT MODAL =================== */}
        {(addModal || editModal) && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }}>
            <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-6 max-w-2xl w-full mx-4 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  {editModal ? (<><Pencil className="text-blue-500" size={20} />Edit Lead</>) : (<><Plus className="text-green-500" size={20} />Add New Lead</>)}
                </h3>
                <button onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }} className="text-slate-400 hover:text-white transition-colors"><X size={24} /></button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2"><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Project Name *</label><input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="Enter project name" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Company</label><input type="text" value={formData.company} onChange={(e) => setFormData({ ...formData, company: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="Company name" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">General Contractor</label><input type="text" value={formData.gc} onChange={(e) => setFormData({ ...formData, gc: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="GC name" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Name</label><input type="text" value={formData.contact_name} onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="Contact person" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Email</label><input type="email" value={formData.contact_email} onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="email@example.com" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Phone</label><input type="tel" value={formData.contact_phone} onChange={(e) => setFormData({ ...formData, contact_phone: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="(555) 123-4567" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Bid Date</label><input type="text" value={formData.bid_date} onChange={(e) => setFormData({ ...formData, bid_date: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="MM/DD/YYYY or TBD" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Location</label><input type="text" value={formData.location} onChange={(e) => setFormData({ ...formData, location: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="City, State" /></div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Full Address</label><input type="text" value={formData.full_address} onChange={(e) => setFormData({ ...formData, full_address: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="123 Main St, City, State ZIP" /></div>
                <div className="col-span-2"><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Description</label><textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none h-20 resize-none" placeholder="Project description..." /></div>
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Files Link</label>
                  <div className="flex gap-2">
                    <input type="text" value={formData.files_link} onChange={(e) => setFormData({ ...formData, files_link: e.target.value })} className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="https://... or C:\..." />
                    <button onClick={triggerFolderPicker} className="bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-3 rounded-lg transition-colors" title="Native Folder Picker">
                      <FolderOpen size={18} />
                    </button>
                    <button onClick={openFolderBrowser} className="bg-blue-700 hover:bg-blue-600 text-slate-300 hover:text-white px-3 rounded-lg transition-colors" title="Browse Server Folders">
                      <Search size={18} />
                    </button>
                  </div>
                </div>
                <div><label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Download Link</label><input type="url" value={formData.download_link} onChange={(e) => setFormData({ ...formData, download_link: e.target.value })} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none" placeholder="https://..." /></div>
                <div className="col-span-2 flex gap-6">
                  <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={formData.sprinklered} onChange={(e) => setFormData({ ...formData, sprinklered: e.target.checked })} className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500" /><span className="text-sm text-slate-300">Sprinklered</span></label>
                  <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={formData.has_budget} onChange={(e) => setFormData({ ...formData, has_budget: e.target.checked })} className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500" /><span className="text-sm text-slate-300">Has Budget</span></label>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors">Cancel</button>
                <button onClick={editModal ? updateLead : addLead} disabled={!formData.name} className="flex-1 bg-[#ed2028] hover:bg-red-600 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold py-3 rounded-lg transition-colors">{editModal ? 'Update Lead' : 'Add Lead'}</button>
              </div>
            </div>
          </div>
        )}

        {/* =================== FOLDER BROWSER MODAL =================== */}
        {folderBrowserModal && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setFolderBrowserModal(false)}>
            <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-6 w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <FolderOpen className="text-blue-500" size={20} />Browse Folders
                </h3>
                <button onClick={() => setFolderBrowserModal(false)} className="text-slate-400 hover:text-white"><X size={24} /></button>
              </div>
              <div className="bg-slate-800 rounded-lg p-2 mb-4 flex items-center gap-2">
                <button onClick={goUpDirectory} disabled={!folderBrowserPath} className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white px-3 py-1 rounded transition-colors">
                  <ChevronUp size={18} />
                </button>
                <span className="text-slate-300 text-sm truncate flex-1">{folderBrowserPath || '(Root)'}</span>
              </div>
              <div className="bg-slate-800 rounded-lg max-h-64 overflow-y-auto">
                {folderBrowserLoading ? (
                  <div className="text-center py-8 text-slate-400">Loading...</div>
                ) : folderBrowserItems.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">No folders found</div>
                ) : (
                  folderBrowserItems.map((item, i) => (
                    <button key={i} onClick={() => browseTo(item.path)} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-700 text-left text-white transition-colors border-b border-slate-700 last:border-0">
                      <FolderOpen size={16} className="text-yellow-500" />
                      <span className="truncate">{item.name}</span>
                    </button>
                  ))
                )}
              </div>
              <div className="flex gap-3 mt-4">
                <button onClick={() => setFolderBrowserModal(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-bold py-2 rounded-lg transition-colors">Cancel</button>
                <button onClick={selectFolder} disabled={!folderBrowserPath} className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold py-2 rounded-lg transition-colors">Select This Folder</button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// LeadTable moved outside to persist state (expandedLeadId, currentPage) across parent re-renders/refreshes
const LeadTable = ({
  title, data, showSiteFilter, uniqueSites, siteFilter, setSiteFilter,
  triggerKnowledgeScan, knowledgeScanning, triggerSingleScan, scanningIds,
  toggleLeadStyle, openEditModal, deleteLead, setCompanyPopup,
  setDescriptionPopup, API_BASE, sortConfig, setSortConfig,
  searchQuery, setSearchQuery, showHidden, setShowHidden, openPointToFile
}) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedLeadId, setExpandedLeadId] = useState(null);
  const [expandedThumbnail, setExpandedThumbnail] = useState(null);
  const [qaQuestion, setQaQuestion] = useState('');
  const [qaLoading, setQaLoading] = useState(false);
  const itemsPerPage = 50;
  const totalPages = Math.ceil(data.length / itemsPerPage);

  useEffect(() => {
    if (!expandedLeadId) { setExpandedThumbnail(null); return; }
    const lead = data.find(l => l.id === expandedLeadId);
    if (!lead || (!lead.local_file_path && !lead.files_link && !lead.gdrive_link)) {
      setExpandedThumbnail(null);
      return;
    }
    fetch(`${API_BASE}/knowledge/thumbnail/${expandedLeadId}`)
      .then(r => r.json())
      .then(d => setExpandedThumbnail(d.thumbnail))
      .catch(() => setExpandedThumbnail(null));
  }, [expandedLeadId]);

  const askProjectQuestion = async (leadId) => {
    const q = qaQuestion.trim();
    if (!q) return;
    setQaLoading(true);
    try {
      const res = await fetch(`${API_BASE}/leads/${leadId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) {
        alert(resData.detail || 'Failed to get answer');
        return;
      }
      setQaQuestion('');
      // Update lead with new qa_history via PUT to trigger parent refresh
      toggleLeadStyle({ id: leadId }, 'qa_history', resData.qa_history);
    } catch (e) {
      console.error('Q&A failed:', e);
      alert('Failed to ask question. Please try again.');
    } finally {
      setQaLoading(false);
    }
  };

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const SortHeader = ({ label, sortKey, className }) => (
    <th className={`px-4 py-3 cursor-pointer hover:text-slate-300 transition-colors select-none ${className}`} onClick={() => handleSort(sortKey)}>
      <div className={`flex items-center gap-1 ${className?.includes('text-center') ? 'justify-center' : ''}`}>
        {label}
        {sortConfig.key === sortKey && (
          <ArrowUpDown size={12} className={sortConfig.direction === 'asc' ? 'text-orange-400 rotate-180' : 'text-orange-400'} />
        )}
      </div>
    </th>
  );

  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) setCurrentPage(totalPages);
  }, [data.length, totalPages, currentPage]);

  const paginatedData = data.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);
  const handlePageChange = (p) => { if (p >= 1 && p <= totalPages) setCurrentPage(p); };

  return (
    <div className="mb-8 bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col">
      <div className="p-4 border-b border-slate-800 flex flex-col gap-3 bg-slate-900/50 backdrop-blur">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-bold text-white flex items-center gap-3">
            {title}
            <span className="bg-slate-800 text-slate-400 text-xs px-2 py-1 rounded-full">{data.length}</span>
          </h2>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-500" size={14} />
              <input
                type="text"
                placeholder="Search leads..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-800 text-slate-200 pl-9 pr-4 py-1.5 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-slate-600 w-52"
              />
            </div>
            <button onClick={() => setShowHidden(!showHidden)} className={`p-1.5 rounded-lg transition ${showHidden ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'}`} title={showHidden ? 'Hide Hidden' : 'Show Hidden'}>
              {showHidden ? <Eye size={16} /> : <EyeOff size={16} />}
            </button>
            <button onClick={triggerKnowledgeScan} disabled={knowledgeScanning} className="flex items-center gap-1.5 px-3 py-1 bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 border border-purple-600/30 rounded-lg text-xs font-semibold transition">
              {knowledgeScanning ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />}
              {knowledgeScanning ? 'Scanning...' : 'AI Scan All'}
            </button>
            {totalPages > 1 && (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span>Page {currentPage} of {totalPages}</span>
                <div className="flex gap-1">
                  <button onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1} className="p-1 rounded hover:bg-slate-800 disabled:opacity-30"><ChevronLeft size={16} /></button>
                  <button onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages} className="p-1 rounded hover:bg-slate-800 disabled:opacity-30"><ChevronRight size={16} /></button>
                </div>
              </div>
            )}
          </div>
        </div>
        {showSiteFilter && uniqueSites.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-500 uppercase tracking-wide">Planroom:</span>
            <button onClick={() => setSiteFilter('all')} className={`px-3 py-1 rounded text-xs font-semibold transition ${siteFilter === 'all' ? 'bg-[#ed2028] text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>All</button>
            {uniqueSites.map(site => (
              <button key={site} onClick={() => setSiteFilter(site)} className={`px-3 py-1 rounded text-xs font-semibold transition ${siteFilter === site ? 'bg-[#ed2028] text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>{site}</button>
            ))}
          </div>
        )}
      </div>
      <div className="overflow-x-auto flex-grow">
        <table className="w-full table-fixed text-left text-xs text-slate-400">
          <colgroup>
            <col className="w-[70px]" />
            <col className="w-[22%]" />
            <col className="w-[200px]" />
            <col className="w-[14%]" />
            <col className="w-[13%]" />
            <col className="w-[12%]" />
            <col className="w-[90px]" />
            <col className="w-[70px]" />
            <col className="w-[140px]" />
          </colgroup>
          <thead className="bg-slate-950/50 text-xs uppercase font-semibold text-slate-500 sticky top-0">
            <tr>
              <th className="px-2 py-3 whitespace-nowrap"></th>
              <SortHeader label="Project" sortKey="name" />
              <th className="px-2 py-3 whitespace-nowrap">Tags</th>
              <SortHeader label="Company / GC" sortKey="company" />
              <SortHeader label="Contact" sortKey="contact_name" />
              <SortHeader label="Location" sortKey="location" />
              <SortHeader label="Bid Date" sortKey="bid_date" className="whitespace-nowrap" />
              <th className="px-4 py-3 text-center whitespace-nowrap">Files</th>
              <th className="px-4 py-3 text-center whitespace-nowrap">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {paginatedData.map((lead, i) => {
              const expired = isExpired(lead.bid_date);
              const highlightClass = getHighlightBg(lead.highlight);
              const strikeClass = lead.strikethrough ? 'opacity-50' : '';
              const hiddenClass = lead.hidden ? 'opacity-30 grayscale' : '';
              return (
                <React.Fragment key={lead.id || i}>
                  <tr className={`hover:bg-slate-800/30 transition group ${expired ? 'opacity-40' : ''} ${hiddenClass} ${highlightClass} ${strikeClass}`}>
                    <td className="px-2 py-2">
                      <div className="flex gap-0.5">
                        <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'green' ? null : 'green')} className={`p-1 rounded ${lead.highlight === 'green' ? 'bg-green-600' : 'bg-slate-700 hover:bg-green-600'}`} title="Green"><Circle size={8} className="text-green-400" fill={lead.highlight === 'green' ? 'currentColor' : 'none'} /></button>
                        <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'yellow' ? null : 'yellow')} className={`p-1 rounded ${lead.highlight === 'yellow' ? 'bg-yellow-600' : 'bg-slate-700 hover:bg-yellow-600'}`} title="Yellow"><Circle size={8} className="text-yellow-400" fill={lead.highlight === 'yellow' ? 'currentColor' : 'none'} /></button>
                        <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'red' ? null : 'red')} className={`p-1 rounded ${lead.highlight === 'red' ? 'bg-red-600' : 'bg-slate-700 hover:bg-red-600'}`} title="Red"><Circle size={8} className="text-red-400" fill={lead.highlight === 'red' ? 'currentColor' : 'none'} /></button>
                        <button onClick={() => toggleLeadStyle(lead, 'strikethrough', !lead.strikethrough)} className={`p-1 rounded ${lead.strikethrough ? 'bg-slate-500' : 'bg-slate-700 hover:bg-slate-500'}`} title="Mark reviewed"><Minus size={8} className="text-slate-300" /></button>
                      </div>
                    </td>
                    <td className="px-4 py-2 font-medium text-slate-200 group-hover:text-orange-400 transition-colors">
                      <button onClick={() => setExpandedLeadId(expandedLeadId === lead.id ? null : lead.id)} className="text-left hover:text-orange-400 transition-colors flex items-center gap-2" title="Click to expand">
                        {expandedLeadId === lead.id ? <ChevronUp size={14} className="text-orange-400" /> : <ChevronDown size={14} className="text-slate-500" />}
                        <div className="truncate text-sm">{lead.name}</div>
                      </button>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {expired && <span className="text-[10px] bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded">EXPIRED</span>}
                        <span className="text-[10px] text-slate-600">{lead.site}</span>
                      </div>
                      {/* Short In-line Comment */}
                      <div className="mt-1">
                        <input
                          type="text"
                          defaultValue={lead.short_comment || ''}
                          onBlur={(e) => toggleLeadStyle(lead, 'short_comment', e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                          placeholder="Add comment..."
                          className={`bg-transparent border-0 border-b border-transparent hover:border-slate-700 focus:border-orange-500 text-[10px] ${getCommentColor(lead.highlight)} placeholder-slate-700 w-full focus:outline-none transition-colors`}
                        />
                      </div>
                    </td>
                    {/* Tags column */}
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        {lead.has_budget && <span className="relative group/tag text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30 cursor-default">BUDGET<span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">Project has budget info</span></span>}
                        {/* User tags */}
                        {lead.tags && lead.tags.map((tag, idx) => (
                          <span key={idx} className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default ${tag.color === 'green' ? 'bg-green-500/10 text-green-400 border-green-500/20' :
                            tag.color === 'red' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                              tag.color === 'blue' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                tag.color === 'orange' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' :
                                  tag.color === 'purple' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                    tag.color === 'yellow' ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' :
                                      tag.color === 'teal' ? 'bg-teal-500/10 text-teal-400 border-teal-500/20' :
                                        'bg-slate-700 text-slate-300 border-slate-600'
                            }`}>
                            {tag.label}
                            {tag.hover && <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">{tag.hover}</span>}
                          </span>
                        ))}
                        {/* Knowledge Badges */}
                        {lead.knowledge_badges && lead.knowledge_badges.map((b, idx) => (
                          <span key={`kb-${idx}`} className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default ${badgeColor(b)}`}>
                            {b}
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">{badgeHover(b, lead)}</span>
                          </span>
                        ))}
                        {lead.knowledge_last_scanned && !lead.sprinklered && (
                          <span className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default ${badgeColor('NON-SPRINKLED')}`}>
                            NO SPRINK
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">{badgeHover('NON-SPRINKLED', lead)}</span>
                          </span>
                        )}
                        {/* Project type tags */}
                        {detectProjectTags(lead).map((pt, idx) => (
                          <span key={`pt-${idx}`} className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default ${pt.color}`}>
                            {pt.label}
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">{pt.hover}</span>
                          </span>
                        ))}
                        {/* Bid risk flags */}
                        {lead.knowledge_bid_risk_flags && lead.knowledge_bid_risk_flags.map((flag, idx) => (
                          <span key={`rf-${idx}`} className="relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default bg-red-500/10 text-red-400 border-red-500/20">
                            {flag.split(/[\s\-\/]+/).slice(0, 2).join(' ').toUpperCase()}
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-red-300 whitespace-nowrap opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50">{flag}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <button onClick={() => setCompanyPopup(lead)} className="flex flex-col text-left hover:bg-slate-800/50 p-1 rounded transition-colors w-full" title="Click for details">
                        <span className="text-slate-300 truncate max-w-[220px] hover:text-orange-400 transition-colors">{lead.company !== "N/A" ? lead.company : <span className="text-slate-600 italic">No Company</span>}</span>
                        <span className="text-[10px] text-slate-500 truncate max-w-[220px]">{lead.gc !== "N/A" ? `GC: ${lead.gc}` : ""}</span>
                      </button>
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-slate-300 truncate max-w-[200px]">{lead.contact_name !== "N/A" ? lead.contact_name : <span className="text-slate-600 italic">-</span>}</span>
                        {lead.contact_email && (
                          <a href={`mailto:${lead.contact_email}`} className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-orange-400 transition-colors">
                            <Mail size={10} /><span className="truncate max-w-[200px]">{lead.contact_email}</span>
                          </a>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-slate-400 truncate max-w-[200px]" title={lead.location}>{lead.location || "N/A"}</td>
                    <td className={`px-4 py-2 font-mono whitespace-nowrap ${expired ? 'text-red-400 line-through' : 'text-slate-300'}`}>{formatDate(lead.bid_date)}</td>
                    <td className="px-4 py-2 text-center">
                      <div className="flex justify-center gap-1">
                        {lead.gdrive_link ? (
                          <a href={lead.gdrive_link} target="_blank" rel="noopener noreferrer" className="p-1.5 bg-blue-500 hover:bg-blue-400 text-white rounded transition-colors flex items-center gap-1" title="View on Google Drive"><Cloud size={12} /></a>
                        ) : lead.files_link ? (
                          <button onClick={() => fetch(`${API_BASE}/open-folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: lead.files_link }) })} className="p-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded transition-colors" title={`Open Local Folder: ${lead.files_link}`}><ExternalLink size={12} /></button>
                        ) : lead.local_file_path ? (
                          <a href={`${API_BASE}${lead.local_file_path}`} download className="p-1.5 bg-green-600 hover:bg-green-500 text-white rounded transition-colors" title="Download Local File"><Download size={12} /></a>
                        ) : (
                          <span className="text-slate-600 text-[10px]">-</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-center">
                      <div className="flex justify-center gap-1">
                        <button onClick={() => triggerSingleScan(lead.id)} disabled={scanningIds.has(lead.id)} className="p-1.5 bg-slate-700 hover:bg-violet-600 text-slate-400 hover:text-white rounded transition-colors disabled:opacity-70 disabled:cursor-not-allowed" title="Force Knowledge Scan">
                          {scanningIds.has(lead.id) ? (
                            <svg className="animate-spin h-3 w-3 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                          ) : (
                            <Brain size={12} />
                          )}
                        </button>
                        <button onClick={() => openPointToFile(lead.id)} className="p-1.5 bg-slate-700 hover:bg-orange-600 text-slate-400 hover:text-white rounded transition-colors" title="Browse Files"><FolderOpen size={12} /></button>
                        <button onClick={() => openEditModal(lead)} className="p-1.5 bg-slate-700 hover:bg-blue-600 text-slate-400 hover:text-white rounded transition-colors" title="Edit"><Pencil size={12} /></button>
                        <button onClick={() => toggleLeadStyle(lead, 'hidden', !lead.hidden)} className={`p-1.5 rounded transition-colors ${lead.hidden ? 'bg-slate-600 text-slate-300 hover:bg-slate-500' : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-white'}`} title={lead.hidden ? "Unhide" : "Hide"}>
                          {lead.hidden ? <Eye size={12} /> : <EyeOff size={12} />}
                        </button>
                        <button onClick={() => deleteLead(lead)} className="p-1.5 bg-slate-700 hover:bg-red-600 text-slate-400 hover:text-white rounded transition-colors" title="Delete"><Trash2 size={12} /></button>
                      </div>
                    </td>
                  </tr>
                  {expandedLeadId === lead.id && (
                    <tr key={`expanded-${lead.id}`} className="bg-slate-800/40 border-l-4 border-orange-500 animate-in slide-in-from-left-2 duration-200">
                      <td colSpan="9" className="px-6 py-4">
                        <div className="flex flex-col gap-4">
                          <div className="flex justify-between items-start">
                            {expandedThumbnail && (
                              <div className="w-32 h-40 bg-slate-950 rounded-lg overflow-hidden flex-shrink-0 mr-4 border border-slate-700">
                                <img src={`data:image/png;base64,${expandedThumbnail}`} alt="Title page" className="w-full h-full object-contain" />
                              </div>
                            )}
                            <div className="flex-1">
                              <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                                {lead.name}
                                <span className="text-xs font-normal text-slate-500">Project Summary</span>
                              </h4>
                              <p className="text-xs text-slate-300 max-w-3xl leading-relaxed whitespace-pre-wrap">
                                {lead.knowledge_notes ? (
                                  lead.knowledge_notes
                                ) : lead.description ? (
                                  stripHtml(lead.description)
                                ) : <span className="text-slate-500 italic">No summary available. Run AI scan for details.</span>}
                              </p>
                              <div className="flex gap-2 mt-3 flex-wrap">
                                {lead.knowledge_badges && lead.knowledge_badges.map((b, idx) => (
                                  <span key={idx} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border ${badgeColor(b)} cursor-default`}>
                                    {b}
                                    <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                                      {badgeHover(b, lead)}
                                    </span>
                                  </span>
                                ))}
                                {lead.knowledge_last_scanned && !lead.sprinklered && (
                                  <span className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default ${badgeColor('NON-SPRINKLED')}`}>
                                    NON-SPRINKLED
                                    <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                                      {badgeHover('NON-SPRINKLED', lead)}
                                    </span>
                                  </span>
                                )}
                                {detectProjectTags(lead).map((pt, idx) => (
                                  <span key={`pt-${idx}`} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default ${pt.color}`}>
                                    {pt.label}
                                    <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                                      {pt.hover}
                                    </span>
                                  </span>
                                ))}
                                {lead.knowledge_bid_risk_flags && lead.knowledge_bid_risk_flags.map((flag, idx) => (
                                  <span key={`rf-${idx}`} className={`relative group/kb text-[10px] px-2 py-0.5 rounded-full border cursor-default bg-red-500/10 text-red-400 border-red-500/20`}>
                                    {flag}
                                    <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-red-300 whitespace-nowrap opacity-0 group-hover/kb:opacity-100 pointer-events-none transition-opacity z-50">
                                      Bid risk: {flag}
                                    </span>
                                  </span>
                                ))}
                              </div>
                            </div>

                            <div className="flex flex-col gap-2">
                              <button onClick={() => setDescriptionPopup(lead)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2">
                                <Eye size={14} /> View Full Details
                              </button>
                              <button onClick={() => openPointToFile(lead.id)} className="px-4 py-2 bg-slate-700 hover:bg-orange-600 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2">
                                <FolderOpen size={14} /> Browse Files
                              </button>
                              <button
                                onClick={() => triggerSingleScan(lead.id, true)}
                                disabled={scanningIds.has(lead.id)}
                                className="px-4 py-2 bg-purple-700 hover:bg-purple-500 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Deep analysis with extended thinking"
                              >
                                {scanningIds.has(lead.id) ? (
                                  <><svg className="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Scanning...</>
                                ) : (
                                  <><Brain size={14} /> Deep Scan</>
                                )}
                              </button>
                            </div>
                          </div>

                          {/* Internal Comments */}
                          <div className="mt-2">
                            <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-widest mb-1">Internal Comments</h4>
                            <textarea
                              defaultValue={lead.comments || ''}
                              onBlur={(e) => toggleLeadStyle(lead, 'comments', e.target.value)}
                              placeholder="Add internal notes about this project (autosaves on blur)..."
                              className="w-full bg-slate-900/50 border border-slate-700/50 rounded-lg p-3 text-xs text-slate-300 placeholder-slate-600 focus:ring-1 focus:ring-blue-500 focus:outline-none resize-y min-h-[60px]"
                            />
                          </div>

                          {/* Ask AI About This Project */}
                          <div className="mt-3">
                            <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-widest mb-2">Ask AI About This Project</h4>
                            <div className="flex gap-2 mb-3">
                              <input
                                type="text"
                                value={qaQuestion}
                                onChange={(e) => setQaQuestion(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter' && !qaLoading) askProjectQuestion(lead.id); }}
                                placeholder="What is the specified fire alarm panel?"
                                disabled={qaLoading}
                                className="flex-1 bg-slate-900/50 border border-slate-700/50 rounded-lg px-3 py-2 text-xs text-slate-300 placeholder-slate-600 focus:ring-1 focus:ring-cyan-500 focus:outline-none disabled:opacity-50"
                              />
                              <button
                                onClick={() => askProjectQuestion(lead.id)}
                                disabled={qaLoading || !qaQuestion.trim()}
                                className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                              >
                                {qaLoading ? (
                                  <><svg className="animate-spin h-3 w-3 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Thinking...</>
                                ) : 'Ask'}
                              </button>
                            </div>
                            {lead.qa_history && lead.qa_history.length > 0 && (
                              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                                {lead.qa_history.map((qa, idx) => (
                                  <div key={idx} className="bg-slate-900/60 border border-slate-700/40 rounded-lg p-3">
                                    <div className="text-xs font-semibold text-cyan-400 mb-1">Q: {qa.question}</div>
                                    <div className="text-xs text-slate-300 whitespace-pre-wrap">A: {qa.answer}</div>
                                    {qa.timestamp && (
                                      <div className="text-[10px] text-slate-600 mt-1.5">
                                        {new Date(qa.timestamp).toLocaleString()}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                  }
                </React.Fragment>
              );
            })}
            {data.length === 0 && (
              <tr><td colSpan="9" className="px-6 py-12 text-center text-slate-600 italic">No active leads found in this category.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {
        totalPages > 1 && (
          <div className="p-3 border-t border-slate-800 bg-slate-900/50 flex justify-between items-center text-xs text-slate-400">
            <span>Showing {paginatedData.length} of {data.length} leads</span>
            <div className="flex gap-2">
              <button onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1} className="px-2 py-1 bg-slate-800 rounded hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">Previous</button>
              <span className="flex items-center px-2">Page {currentPage} of {totalPages}</span>
              <button onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages} className="px-2 py-1 bg-slate-800 rounded hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">Next</button>
            </div>
          </div>
        )
      }
    </div >
  );
};
