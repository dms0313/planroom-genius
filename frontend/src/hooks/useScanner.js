import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = `http://${window.location.hostname}:8000`;

/**
 * useScanner({ onScraperComplete, showToast, leads })
 *
 * onScraperComplete(newLeadIds) — called after scraper finishes if autoScanAfterScrape is true
 * showToast — from useLeads
 * leads — current leads array (used to detect new leads after scrape)
 */
export function useScanner({ onScraperComplete, showToast, leads } = {}) {
  const [syncing, setSyncing] = useState(false);
  const [scraperSettings, setScraperSettings] = useState({
    planhub: true,
    bidplanroom: true,
    loydbuildsbetter: true,
    buildingconnected: true,
    use_gdrive: true,
    gemini_model: 'gemini-3.1-pro-preview',
  });
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [scraperStatus, setScraperStatus] = useState(null);
  const [gdriveStatus, setGdriveStatus] = useState(null);
  const [connectingGdrive, setConnectingGdrive] = useState(false);
  const [knowledgeStatus, setKnowledgeStatus] = useState(null);
  const [knowledgeScanning, setKnowledgeScanning] = useState(false);
  const [scanningIds, setScanningIds] = useState(new Set());
  const [autoScanAfterScrape, setAutoScanAfterScrape] = useState(false);

  // Keep a ref to the leads array to compare before/after for new lead detection
  const leadsRef = useRef(leads || []);
  useEffect(() => {
    leadsRef.current = leads || [];
  }, [leads]);

  // Keep a ref to syncing state for use inside intervals/callbacks
  const syncingRef = useRef(syncing);
  useEffect(() => {
    syncingRef.current = syncing;
  }, [syncing]);

  // ── Settings ──────────────────────────────────────────────────────────────

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/scrapers`);
      if (res.ok) {
        const data = await res.json();
        setScraperSettings(data);
      }
    } catch (e) {
      console.error('Failed to fetch settings', e);
    }
  }, []);

  const saveSettings = useCallback(async (newSettings) => {
    try {
      await fetch(`${API_BASE}/settings/scrapers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings),
      });
      setScraperSettings(newSettings);
    } catch (e) {
      console.error('Failed to save settings', e);
      alert('Failed to save settings');
    }
  }, []);

  const toggleSetting = useCallback((key) => {
    setScraperSettings(prev => {
      const newSettings = { ...prev, [key]: !prev[key] };
      saveSettings(newSettings);
      return newSettings;
    });
  }, [saveSettings]);

  // ── Console / Scraper Status ───────────────────────────────────────────────

  const fetchConsoleLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/console-logs?lines=200`);
      const data = await res.json();
      setConsoleLogs(data.logs || []);
    } catch (e) {
      // silently ignore
    }
  }, []);

  const fetchScraperStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/scraper-status`);
      const data = await res.json();
      setScraperStatus(data);
      return data;
    } catch (e) {
      return null;
    }
  }, []);

  const clearConsoleLogs = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/console-logs`, { method: 'DELETE' });
      setConsoleLogs([]);
    } catch (e) {
      // silently ignore
    }
  }, []);

  // ── GDrive ────────────────────────────────────────────────────────────────

  const fetchGdriveStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/gdrive/status`);
      const data = await res.json();
      setGdriveStatus(data);
    } catch (e) {
      console.error('Failed to fetch Google Drive status', e);
      setGdriveStatus({ status: 'error', message: 'Failed to check status' });
    }
  }, []);

  const connectGdrive = useCallback(async () => {
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
      alert('Failed to connect to Google Drive.');
    }
    setConnectingGdrive(false);
  }, [fetchGdriveStatus]);

  // ── Knowledge scan ────────────────────────────────────────────────────────

  const fetchKnowledgeStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/status`);
      const data = await res.json();
      setKnowledgeStatus(data);
      return data;
    } catch (e) {
      console.error('Failed to fetch knowledge status', e);
      return null;
    }
  }, []);

  const triggerKnowledgeScan = useCallback(async () => {
    setKnowledgeScanning(true);
    try {
      const res = await fetch(`${API_BASE}/knowledge/scan`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        alert(data.detail || 'Failed to start Knowledge scan');
      }
      const poll = setInterval(async () => {
        const s = await fetchKnowledgeStatus();
        if (!s?.running) {
          clearInterval(poll);
          setKnowledgeScanning(false);
        }
      }, 3000);
    } catch (e) {
      console.error('Failed to start knowledge scan', e);
      setKnowledgeScanning(false);
    }
  }, [fetchKnowledgeStatus]);

  const triggerDeepScan = useCallback(async (leadId) => {
    setScanningIds(prev => new Set(prev).add(leadId));
    try {
      const url = `${API_BASE}/knowledge/scan/${leadId}?thinking=true`;
      await fetch(url, { method: 'POST' });
      if (showToast) showToast('Deep scan started', 'info');
      setTimeout(async () => {
        // mid-poll
      }, 20000);
      setTimeout(() => {
        setScanningIds(prev => {
          const next = new Set(prev);
          next.delete(leadId);
          return next;
        });
        if (showToast) showToast('Deep scan complete', 'success');
      }, 90000);
    } catch (e) {
      console.error('Failed to trigger deep scan', e);
      setScanningIds(prev => {
        const next = new Set(prev);
        next.delete(leadId);
        return next;
      });
      if (showToast) showToast('Scan failed', 'error');
    }
  }, [showToast]);

  const triggerQuickScan = useCallback(async (leadId) => {
    setScanningIds(prev => new Set(prev).add(leadId));
    try {
      const url = `${API_BASE}/knowledge/scan/${leadId}`;
      await fetch(url, { method: 'POST' });
      if (showToast) showToast('Quick scan started', 'info');
      setTimeout(() => {
        setScanningIds(prev => {
          const next = new Set(prev);
          next.delete(leadId);
          return next;
        });
        if (showToast) showToast('Quick scan complete', 'success');
      }, 12000);
    } catch (e) {
      console.error('Failed to trigger quick scan', e);
      setScanningIds(prev => {
        const next = new Set(prev);
        next.delete(leadId);
        return next;
      });
      if (showToast) showToast('Scan failed', 'error');
    }
  }, [showToast]);

  // ── Scraper triggers ──────────────────────────────────────────────────────

  // After a scraper run completes, detect new lead IDs and optionally auto-scan them
  const handleScraperComplete = useCallback((leadIdsBefore) => {
    if (autoScanAfterScrape && onScraperComplete) {
      // The caller (Dashboard orchestrator) passes in updated leads via the leads prop
      // We compare leadsRef.current (updated by the time the polling finishes) to before
      const currentIds = new Set(leadsRef.current.map(l => l.id));
      const newIds = [...currentIds].filter(id => !leadIdsBefore.has(id));
      if (newIds.length > 0) {
        onScraperComplete(newIds);
      }
    }
  }, [autoScanAfterScrape, onScraperComplete]);

  const stopScan = useCallback(async () => {
    if (!window.confirm('Are you sure you want to STOP the current scan?')) return;
    try {
      const res = await fetch(`${API_BASE}/stop-scan`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        alert(data.message);
        setSyncing(false);
      } else {
        alert('Failed to stop scan: ' + data.message);
      }
    } catch (e) {
      console.error('Stop scan failed', e);
      alert('Failed to send stop request');
    }
  }, []);

  const triggerScan = useCallback(async (e) => {
    if (e) e.preventDefault();
    setSyncing(true);
    const leadIdsBefore = new Set(leadsRef.current.map(l => l.id));
    try {
      await fetch(`${API_BASE}/sync-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scraperSettings),
      });
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        elapsed += 5000;
        if (elapsed >= 180000) {
          clearInterval(pollInterval);
          setSyncing(false);
          handleScraperComplete(leadIdsBefore);
        }
      }, 5000);
    } catch (e) {
      console.error('Agent trigger failed', e);
      setSyncing(false);
    }
  }, [scraperSettings, handleScraperComplete]);

  const triggerSingleScraper = useCallback(async (scraperName) => {
    setSyncing(true);
    clearConsoleLogs();
    const leadIdsBefore = new Set(leadsRef.current.map(l => l.id));
    const singleSettings = {
      planhub: false,
      bidplanroom: false,
      loydbuildsbetter: false,
      buildingconnected: false,
      isqft: false,
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
        elapsed += 5000;
        if (elapsed >= 180000) {
          clearInterval(pollInterval);
          setSyncing(false);
          handleScraperComplete(leadIdsBefore);
        }
      }, 5000);
    } catch (e) {
      console.error('Single scraper trigger failed', e);
      setSyncing(false);
    }
  }, [scraperSettings, clearConsoleLogs, handleScraperComplete]);

  // ── Polling: console logs + scraper status when syncing ───────────────────

  useEffect(() => {
    if (!syncing) return;
    fetchConsoleLogs();
    fetchScraperStatus();
    const interval = setInterval(() => {
      fetchConsoleLogs();
      fetchScraperStatus();
    }, 2000);
    return () => clearInterval(interval);
  }, [syncing, fetchConsoleLogs, fetchScraperStatus]);

  // ── Knowledge scanning poll ───────────────────────────────────────────────

  useEffect(() => {
    if (!knowledgeScanning) return;
    const interval = setInterval(async () => {
      await fetchKnowledgeStatus();
    }, 3000);
    return () => clearInterval(interval);
  }, [knowledgeScanning, fetchKnowledgeStatus]);

  // Auto-stop knowledgeScanning when status says not running
  useEffect(() => {
    if (knowledgeStatus && !knowledgeStatus.running && knowledgeScanning) {
      setKnowledgeScanning(false);
    }
  }, [knowledgeStatus, knowledgeScanning]);

  // ── Mount: fetch settings + gdrive status ─────────────────────────────────

  useEffect(() => {
    fetchSettings();
    fetchGdriveStatus();
  }, [fetchSettings, fetchGdriveStatus]);

  return {
    syncing,
    scraperSettings,
    fetchSettings,
    saveSettings,
    toggleSetting,
    triggerScan,
    triggerSingleScraper,
    triggerDeepScan,
    triggerQuickScan,
    stopScan,
    scanningIds,
    consoleLogs,
    scraperStatus,
    fetchConsoleLogs,
    clearConsoleLogs,
    gdriveStatus,
    connectingGdrive,
    connectGdrive,
    knowledgeStatus,
    knowledgeScanning,
    triggerKnowledgeScan,
    autoScanAfterScrape,
    setAutoScanAfterScrape,
  };
}
