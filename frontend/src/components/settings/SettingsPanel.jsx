import React, { useEffect, useRef } from 'react';
import { X, Settings, Cloud, CloudOff, Terminal, Brain, RefreshCw } from 'lucide-react';

const SCRAPERS = [
  { key: 'planhub',          label: 'PlanHub',            color: 'text-blue-400' },
  { key: 'bidplanroom',      label: 'BidPlanroom',        color: 'text-emerald-400' },
  { key: 'loydbuildsbetter', label: 'Loyd Builds Better', color: 'text-amber-400' },
  { key: 'buildingconnected',label: 'BuildingConnected',  color: 'text-purple-400' },
  { key: 'isqft',            label: 'iSqFt',              color: 'text-orange-400' },
];

const GEMINI_MODELS = [
  { value: 'gemini-3.1-pro-preview',   label: 'Gemini 3.1 Pro Preview' },
  { value: 'gemini-3-flash-preview',   label: 'Gemini 3 Flash Preview' },
  { value: 'gemini-pro-latest',        label: 'Gemini Pro Latest' },
];

function Toggle({ checked, onChange }) {
  return (
    <button
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${checked ? 'bg-blue-600' : 'bg-slate-600'}`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  );
}

export default function SettingsPanel({
  open,
  onClose,
  // Scraper settings
  scraperSettings,
  toggleSetting,
  saveSettings,
  triggerSingleScraper,
  triggerScan,
  syncing,
  stopScan,
  // Auto-scan toggle
  autoScanAfterScrape,
  setAutoScanAfterScrape,
  // Logs
  consoleLogs,
  scraperStatus,
  clearConsoleLogs,
  // Google Drive
  gdriveStatus,
  connectGdrive,
  connectingGdrive,
  // Utility actions
  deduplicateLeads,
  clearAllLeads,
  refreshAllLeads,
  deduplicating,
  clearing,
  refreshing,
  fetchLeads,
  loading,
}) {
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (logsEndRef.current && open) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [consoleLogs, open]);

  const tagColors = { '[BC]': 'text-cyan-400', '[PH]': 'text-violet-400', '[LBB]': 'text-amber-400', '[BPR]': 'text-emerald-400' };

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-full sm:w-[420px] z-50 flex flex-col transition-transform duration-300 ${open ? 'translate-x-0' : 'translate-x-full'}`}
        style={{ background: '#0a0f1a', borderLeft: '1px solid rgba(255,255,255,0.1)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Settings size={18} className="text-blue-400" /> Settings
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors p-1 rounded hover:bg-slate-800">
            <X size={20} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">

          {/* ── Scrapers ── */}
          <section>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Scrapers</h3>
            <div className="space-y-2">
              {SCRAPERS.map(s => (
                <div key={s.key} className="flex items-center justify-between p-3 bg-slate-800/60 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Toggle
                      checked={!!scraperSettings[s.key]}
                      onChange={() => toggleSetting(s.key)}
                    />
                    <span className={`text-sm font-medium ${s.color}`}>{s.label}</span>
                  </div>
                  <button
                    onClick={() => triggerSingleScraper(s.key)}
                    disabled={syncing}
                    className="px-3 py-1 rounded text-xs font-semibold bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition"
                  >
                    Run
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-3 flex gap-2">
              <button
                onClick={() => { triggerScan(); }}
                disabled={syncing}
                className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center justify-center gap-2"
              >
                {syncing ? (
                  <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Scanning...</>
                ) : 'Scan All Enabled'}
              </button>
              {syncing && (
                <button onClick={stopScan} className="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-semibold transition">
                  Stop
                </button>
              )}
            </div>

            {/* Auto quick-scan toggle */}
            <div className="flex items-center justify-between mt-3 p-3 bg-slate-800/60 rounded-lg">
              <div>
                <div className="text-sm font-medium text-slate-200">Auto Quick-Scan After Scrape</div>
                <div className="text-xs text-slate-500 mt-0.5">Run quick AI scan on new leads automatically</div>
              </div>
              <Toggle checked={!!autoScanAfterScrape} onChange={() => setAutoScanAfterScrape(v => !v)} />
            </div>
          </section>

          {/* ── AI Model ── */}
          <section>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">AI Model</h3>
            <div className="p-3 bg-slate-800/60 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain size={16} className="text-violet-400" />
                <div>
                  <div className="text-sm font-medium text-slate-200">Gemini Model</div>
                  <div className="text-xs text-slate-500">Used for AI / deep scans</div>
                </div>
              </div>
              <select
                value={scraperSettings.gemini_model || 'gemini-3.1-pro-preview'}
                onChange={e => saveSettings({ ...scraperSettings, gemini_model: e.target.value })}
                className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                {GEMINI_MODELS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
          </section>

          {/* ── Google Drive ── */}
          <section>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Google Drive</h3>
            <div className="p-3 bg-slate-800/60 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                {gdriveStatus?.status === 'connected'
                  ? <Cloud size={16} className="text-green-400" />
                  : <CloudOff size={16} className="text-slate-500" />}
                <div>
                  <div className="text-sm font-medium text-slate-200">Google Drive</div>
                  {gdriveStatus?.status === 'connected'
                    ? <div className="text-xs text-green-400">Connected</div>
                    : gdriveStatus?.status === 'not_authenticated'
                      ? <button onClick={connectGdrive} disabled={connectingGdrive} className="text-xs text-blue-400 hover:text-blue-300 transition">
                          {connectingGdrive ? 'Connecting...' : 'Click to connect'}
                        </button>
                      : <div className="text-xs text-slate-500">{gdriveStatus?.message || 'Not configured'}</div>
                  }
                </div>
              </div>
              <Toggle
                checked={!!scraperSettings.use_gdrive}
                onChange={() => toggleSetting('use_gdrive')}
              />
            </div>
          </section>

          {/* ── Data Management ── */}
          <section>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Data Management</h3>
            <div className="space-y-2">
              <button onClick={() => { fetchLeads(); }} disabled={loading} className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700/60 bg-slate-800/60 rounded-lg transition disabled:opacity-50 flex items-center gap-2">
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {loading ? 'Refreshing...' : 'Refresh Leads'}
              </button>
              <button onClick={deduplicateLeads} disabled={deduplicating} className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700/60 bg-slate-800/60 rounded-lg transition disabled:opacity-50">
                {deduplicating ? 'Cleaning...' : 'Remove Duplicates'}
              </button>
              <button onClick={refreshAllLeads} disabled={refreshing} className="w-full px-4 py-2.5 text-left text-sm text-purple-300 hover:bg-slate-700/60 bg-slate-800/60 rounded-lg transition disabled:opacity-50">
                {refreshing ? 'Refreshing...' : 'Clear & Rescan'}
              </button>
              <button onClick={clearAllLeads} disabled={clearing} className="w-full px-4 py-2.5 text-left text-sm text-yellow-300 hover:bg-slate-700/60 bg-slate-800/60 rounded-lg transition disabled:opacity-50">
                {clearing ? 'Clearing...' : 'Clear All Leads'}
              </button>
            </div>
          </section>

          {/* ── Scraper Logs ── */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <Terminal size={13} /> Scraper Logs
                {scraperStatus?.running && <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />}
              </h3>
              <button onClick={clearConsoleLogs} className="text-xs text-slate-500 hover:text-slate-300 transition">Clear</button>
            </div>
            {scraperStatus && (
              <div className="text-xs text-slate-500 mb-2 flex flex-wrap gap-3">
                {scraperStatus.running && scraperStatus.current_step && (
                  <span className="text-green-400">{scraperStatus.current_step}</span>
                )}
                {scraperStatus.last_status && !scraperStatus.running && (
                  <span>Last: {scraperStatus.last_status}</span>
                )}
                {scraperStatus.leads_found && (
                  <span>BC: {scraperStatus.leads_found.buildingconnected} | PH: {scraperStatus.leads_found.planhub} | iSqFt: {scraperStatus.leads_found.isqft ?? 0}</span>
                )}
              </div>
            )}
            <div className="bg-slate-950 rounded-xl p-3 h-52 overflow-y-auto font-mono text-xs">
              {consoleLogs.length === 0 ? (
                <div className="text-slate-600 italic">No logs yet. Run a scraper to see output...</div>
              ) : consoleLogs.map((log, i) => {
                const tagMatch = log.match(/^\[(?:BC|PH|LBB|BPR)\]/);
                const lineColor = log.includes('ERROR') ? 'text-red-400'
                  : log.includes('TIMEOUT') ? 'text-yellow-400'
                  : log.includes('OK') || log.includes('Complete') ? 'text-green-400'
                  : log.includes('LOGIN') ? 'text-orange-400 font-bold'
                  : log.includes('Found') ? 'text-blue-400'
                  : 'text-slate-300';
                return (
                  <div key={i} className={`py-0.5 ${lineColor}`}>
                    {tagMatch
                      ? <><span className={`${tagColors[tagMatch[0]]} font-bold`}>{tagMatch[0]}</span>{log.slice(tagMatch[0].length)}</>
                      : log}
                  </div>
                );
              })}
              <div ref={logsEndRef} />
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
