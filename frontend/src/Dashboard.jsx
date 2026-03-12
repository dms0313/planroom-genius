import React, { useState, useRef, useCallback } from 'react';
import { X, FolderOpen, ChevronLeft } from 'lucide-react';

import { useLeads } from './hooks/useLeads';
import { useScanner } from './hooks/useScanner';
import { useStats } from './hooks/useStats';

import TopNav from './components/layout/TopNav';
import StatsRow from './components/layout/StatsRow';

import LeadTable from './components/leads/LeadTable';
import ContactPopup from './components/leads/ContactPopup';

import AddLeadModal from './components/modals/AddLeadModal';
import ProjectDetailModal from './components/modals/ProjectDetailModal';
import FileBrowserModal from './components/modals/FileBrowserModal';

import SettingsPanel from './components/settings/SettingsPanel';

const API_BASE = `http://${window.location.hostname}:8000`;

export default function LeadDashboard() {
  // ── UI state ──────────────────────────────────────────────────────────────
  const [companyPopup, setCompanyPopup] = useState(null);
  const [descriptionPopup, setDescriptionPopup] = useState(null);
  const [addModal, setAddModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // File browser modal (local knowledge files)
  const [pointToFileModal, setPointToFileModal] = useState(null);

  // Folder browser (GDrive folder path assignment)
  const [folderBrowserModal, setFolderBrowserModal] = useState(false);
  const [folderBrowserPath, setFolderBrowserPath] = useState('');
  const [folderBrowserItems, setFolderBrowserItems] = useState([]);
  const [folderBrowserLoading, setFolderBrowserLoading] = useState(false);
  const [folderBrowserTarget, setFolderBrowserTarget] = useState(null);

  // External files link to inject into AddLeadModal
  const [externalFilesLink, setExternalFilesLink] = useState('');

  // ── Circular-dep ref for onScraperComplete ───────────────────────────────
  const onScraperCompleteRef = useRef(null);

  // ── Hooks ─────────────────────────────────────────────────────────────────
  const {
    leads, loading, fetchLeads, addLead, updateLead, deleteLead,
    toggleLeadStyle, sendToNotion, notionStatus,
    deduplicateLeads, clearAllLeads, refreshAllLeads,
    deduplicating, clearing, refreshing,
    showToast, toasts,
  } = useLeads();

  const {
    syncing, scraperSettings, fetchSettings, saveSettings, toggleSetting,
    triggerScan, triggerSingleScraper, triggerDeepScan, triggerQuickScan,
    stopScan, scanningIds, consoleLogs, scraperStatus, fetchConsoleLogs,
    clearConsoleLogs, gdriveStatus, connectingGdrive, connectGdrive,
    knowledgeStatus, knowledgeScanning, triggerKnowledgeScan,
    autoScanAfterScrape, setAutoScanAfterScrape,
  } = useScanner({
    onScraperComplete: (ids) => onScraperCompleteRef.current?.(ids),
    showToast,
    leads,
  });

  // Wire up the ref now that triggerQuickScan is available
  onScraperCompleteRef.current = useCallback((newLeadIds) => {
    if (!newLeadIds?.length) return;
    newLeadIds.forEach(id => triggerQuickScan(id));
  }, [triggerQuickScan]);

  const { activeLeads, verifiedManufacturer, dueToday, dueIn3Days } = useStats(leads);

  // ── File browser (knowledge files) ───────────────────────────────────────
  const handleFilesClick = useCallback(async (lead) => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/files/${lead.id}`);
      const data = await res.json();
      setPointToFileModal({ lead_id: lead.id, files: data.files });
    } catch (e) {
      console.error('Failed to fetch files', e);
      setPointToFileModal({ lead_id: lead.id, files: [], error: 'Failed to load files' });
    }
  }, []);

  // ── Folder browser (GDrive) ───────────────────────────────────────────────
  const browseTo = useCallback(async (path) => {
    setFolderBrowserLoading(true);
    try {
      const res = await fetch(`${API_BASE}/gdrive/browse?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      setFolderBrowserPath(data.current ?? path);
      setFolderBrowserItems(data.items || []);
    } catch (e) {
      console.error('Folder browse failed', e);
      showToast('Failed to browse folder', 'error');
    }
    setFolderBrowserLoading(false);
  }, [showToast]);

  const handleFolderBrowserOpen = useCallback(async (lead) => {
    setFolderBrowserTarget(lead.id);
    setFolderBrowserPath('');
    setFolderBrowserModal(true);
    await browseTo('');
  }, [browseTo]);

  const handleGoUp = useCallback(() => {
    if (!folderBrowserPath) { browseTo(''); return; }
    const parts = folderBrowserPath.split(/[/\\]/).filter(Boolean);
    if (parts.length <= 1) {
      browseTo('');
    } else {
      parts.pop();
      const isWin = folderBrowserPath.includes('\\');
      browseTo(parts.join(isWin ? '\\' : '/') || '/');
    }
  }, [folderBrowserPath, browseTo]);

  const handleSelectFolder = useCallback(async () => {
    if (folderBrowserPath) {
      if (folderBrowserTarget) {
        // Quick-assign mode: save directly to lead
        try {
          await fetch(`${API_BASE}/leads/${folderBrowserTarget}/files-link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files_link: folderBrowserPath }),
          });
          fetchLeads(true);
        } catch (e) {
          console.error('Failed to save folder:', e);
          showToast('Failed to assign folder', 'error');
        }
        setFolderBrowserTarget(null);
      } else {
        // Add-lead modal mode: inject via externalFilesLink
        setExternalFilesLink(folderBrowserPath);
      }
    }
    setFolderBrowserModal(false);
  }, [folderBrowserPath, folderBrowserTarget, fetchLeads, showToast]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0e1117] text-white">
      <TopNav
        onAddLead={() => setAddModal(true)}
        onSettings={() => setShowSettings(true)}
      />

      <div className="max-w-screen-2xl mx-auto px-4 py-4 space-y-4">
        <StatsRow
          activeLeads={activeLeads}
          verifiedManufacturer={verifiedManufacturer}
          dueToday={dueToday}
          dueIn3Days={dueIn3Days}
        />

        <LeadTable
          leads={leads}
          loading={loading}
          onCompanyClick={setCompanyPopup}
          onDescriptionClick={setDescriptionPopup}
          onFilesClick={handleFilesClick}
          onFolderBrowserOpen={handleFolderBrowserOpen}
          triggerDeepScan={triggerDeepScan}
          triggerQuickScan={triggerQuickScan}
          scanningIds={scanningIds}
          updateLead={updateLead}
          deleteLead={deleteLead}
          toggleLeadStyle={toggleLeadStyle}
          sendToNotion={sendToNotion}
          notionStatus={notionStatus}
          knowledgeStatus={knowledgeStatus}
          triggerKnowledgeScan={triggerKnowledgeScan}
          showToast={showToast}
        />
      </div>

      {/* Contact popup */}
      <ContactPopup lead={companyPopup} onClose={() => setCompanyPopup(null)} />

      {/* Project detail modal */}
      {descriptionPopup && (
        <ProjectDetailModal
          lead={descriptionPopup}
          onClose={() => setDescriptionPopup(null)}
          triggerDeepScan={triggerDeepScan}
          scanningIds={scanningIds}
        />
      )}

      {/* Knowledge file browser modal */}
      <FileBrowserModal
        modal={pointToFileModal}
        onClose={() => setPointToFileModal(null)}
        onRescan={(leadId) => triggerKnowledgeScan(leadId)}
        API_BASE={API_BASE}
      />

      {/* Add lead modal */}
      <AddLeadModal
        open={addModal}
        onClose={() => { setAddModal(false); setExternalFilesLink(''); }}
        onAdd={async (formData) => {
          const ok = await addLead(formData);
          if (ok) setAddModal(false);
          return ok;
        }}
        externalFilesLink={externalFilesLink}
        onBrowseFolderServer={() => {
          setFolderBrowserTarget(null);
          setFolderBrowserPath('');
          setFolderBrowserModal(true);
          browseTo('');
        }}
      />

      {/* Settings panel */}
      <SettingsPanel
        open={showSettings}
        onClose={() => setShowSettings(false)}
        scraperSettings={scraperSettings}
        toggleSetting={toggleSetting}
        saveSettings={saveSettings}
        triggerSingleScraper={triggerSingleScraper}
        triggerScan={triggerScan}
        syncing={syncing}
        stopScan={stopScan}
        autoScanAfterScrape={autoScanAfterScrape}
        setAutoScanAfterScrape={setAutoScanAfterScrape}
        consoleLogs={consoleLogs}
        scraperStatus={scraperStatus}
        clearConsoleLogs={clearConsoleLogs}
        gdriveStatus={gdriveStatus}
        connectGdrive={connectGdrive}
        connectingGdrive={connectingGdrive}
        deduplicateLeads={deduplicateLeads}
        clearAllLeads={clearAllLeads}
        refreshAllLeads={refreshAllLeads}
        deduplicating={deduplicating}
        clearing={clearing}
        refreshing={refreshing}
        fetchLeads={fetchLeads}
        loading={loading}
      />

      {/* Folder browser modal (GDrive path assignment) */}
      {folderBrowserModal && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setFolderBrowserModal(false)}
        >
          <div
            className="bg-slate-800 rounded-xl shadow-2xl w-full max-w-lg p-6 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-white font-bold text-lg flex items-center gap-2">
                <FolderOpen size={20} className="text-blue-400" />
                Select Folder
              </h2>
              <button onClick={() => setFolderBrowserModal(false)} className="text-slate-400 hover:text-white">
                <X size={24} />
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleGoUp}
                disabled={!folderBrowserPath}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white px-3 py-1 rounded transition-colors flex items-center gap-1"
              >
                <ChevronLeft size={16} /> Up
              </button>
              <span className="text-slate-300 text-sm truncate flex-1 bg-slate-700/50 rounded px-3 py-1">
                {folderBrowserPath || '(Root)'}
              </span>
            </div>

            <div className="bg-slate-900 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
              {folderBrowserLoading ? (
                <p className="text-slate-400 text-sm p-4 text-center">Loading…</p>
              ) : folderBrowserItems.length === 0 ? (
                <p className="text-slate-500 text-sm p-4 text-center">No folders found</p>
              ) : (
                folderBrowserItems.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => browseTo(item.path)}
                    className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-700 text-left text-white transition-colors border-b border-slate-700 last:border-0"
                  >
                    <FolderOpen size={16} className="text-yellow-400 shrink-0" />
                    <span className="truncate">{item.name}</span>
                  </button>
                ))
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setFolderBrowserModal(false)}
                className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-bold py-2 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSelectFolder}
                disabled={!folderBrowserPath}
                className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold py-2 rounded-lg transition-colors"
              >
                Select This Folder
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast notifications */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium max-w-sm
              ${toast.type === 'success' ? 'bg-green-600' :
                toast.type === 'error' ? 'bg-red-600' : 'bg-slate-600'}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}
