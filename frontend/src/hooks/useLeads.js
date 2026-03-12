import { useState, useEffect, useCallback } from 'react';

const API_BASE = `http://${window.location.hostname}:8000`;

export function useLeads() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notionStatus, setNotionStatus] = useState({});
  const [toasts, setToasts] = useState([]);
  const [deduplicating, setDeduplicating] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const showToast = useCallback((message, type = 'info', duration = 4000) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
  }, []);

  const fetchLeads = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/leads`);
      const data = await res.json();
      setLeads(data.leads || []);
    } catch (e) {
      console.error('Failed to fetch leads', e);
    }
    if (!silent) setLoading(false);
  }, []);

  const addLead = useCallback(async (formData) => {
    try {
      const res = await fetch(`${API_BASE}/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      if (res.ok) {
        await fetchLeads();
        return true;
      } else {
        alert('Failed to add lead');
        return false;
      }
    } catch (e) {
      alert('Failed to add lead.');
      return false;
    }
  }, [fetchLeads]);

  const updateLead = useCallback(async (id, formData) => {
    try {
      const res = await fetch(`${API_BASE}/leads/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      if (res.ok) {
        await fetchLeads();
        return true;
      } else {
        alert('Failed to update lead');
        return false;
      }
    } catch (e) {
      alert('Failed to update lead.');
      return false;
    }
  }, [fetchLeads]);

  const deleteLead = useCallback(async (lead) => {
    if (!window.confirm(`Delete "${lead.name}"?`)) return;
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}`, { method: 'DELETE' });
      if (res.ok) await fetchLeads();
    } catch (e) {
      alert('Failed to delete lead.');
    }
  }, [fetchLeads]);

  const toggleLeadStyle = useCallback(async (lead, field, value) => {
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      });
      if (res.ok) fetchLeads(true);
    } catch (e) {
      console.error(`Failed to toggle ${field}:`, e);
    }
  }, [fetchLeads]);

  const sendToNotion = useCallback(async (lead) => {
    setNotionStatus(s => ({ ...s, [lead.id]: 'loading' }));
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}/notion`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setNotionStatus(s => ({ ...s, [lead.id]: 'success' }));
        setTimeout(() => setNotionStatus(s => ({ ...s, [lead.id]: null })), 4000);
      } else {
        setNotionStatus(s => ({ ...s, [lead.id]: 'error' }));
        alert(`Notion error: ${data.detail || 'Unknown error'}`);
        setTimeout(() => setNotionStatus(s => ({ ...s, [lead.id]: null })), 4000);
      }
    } catch (e) {
      setNotionStatus(s => ({ ...s, [lead.id]: 'error' }));
      alert('Failed to send to Notion.');
      setTimeout(() => setNotionStatus(s => ({ ...s, [lead.id]: null })), 4000);
    }
  }, []);

  const deduplicateLeads = useCallback(async () => {
    if (!window.confirm('Remove duplicate leads by merging their information?')) return;
    setDeduplicating(true);
    try {
      const res = await fetch(`${API_BASE}/deduplicate-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      await fetchLeads();
      alert(`Removed ${data.removed_count} duplicate leads!\nBefore: ${data.original_count} | After: ${data.deduplicated_count}`);
    } catch (e) {
      alert('Failed to deduplicate.');
    }
    setDeduplicating(false);
  }, [fetchLeads]);

  const clearAllLeads = useCallback(async () => {
    if (!window.confirm('Are you sure you want to clear ALL leads? This will create a backup first.')) return;
    setClearing(true);
    try {
      const res = await fetch(`${API_BASE}/clear-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      await fetchLeads();
      alert(`Successfully cleared ${data.count} leads (backup created)`);
    } catch (e) {
      alert('Failed to clear leads.');
    }
    setClearing(false);
  }, [fetchLeads]);

  const refreshAllLeads = useCallback(async () => {
    if (!window.confirm('Clear all existing leads and start a fresh scan?')) return;
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/refresh-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      setLeads([]);
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        if (elapsed >= 180000) {
          clearInterval(pollInterval);
          setRefreshing(false);
        }
      }, 5000);
      alert(`Cleared ${data.cleared_count} leads. Fresh scan started!`);
    } catch (e) {
      alert('Failed to refresh.');
      setRefreshing(false);
    }
  }, [fetchLeads]);

  // Start 10-second polling interval on mount
  useEffect(() => {
    fetchLeads();
    const interval = setInterval(() => {
      fetchLeads(true);
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchLeads]);

  return {
    leads,
    loading,
    fetchLeads,
    addLead,
    updateLead,
    deleteLead,
    toggleLeadStyle,
    sendToNotion,
    notionStatus,
    deduplicateLeads,
    clearAllLeads,
    refreshAllLeads,
    deduplicating,
    clearing,
    refreshing,
    showToast,
    toasts,
  };
}
