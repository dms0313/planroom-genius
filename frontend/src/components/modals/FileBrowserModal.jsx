import React, { useState } from 'react';
import { X, FolderOpen, FileText, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';

const classColor = (cls) => {
  if (cls === 'plan')   return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
  if (cls === 'spec')   return 'bg-green-500/20 text-green-400 border-green-500/40';
  if (cls === 'ignore') return 'bg-red-500/20 text-red-400 border-red-500/40';
  return 'bg-slate-500/20 text-slate-400 border-slate-500/40';
};

export default function FileBrowserModal({ modal, onClose, onRescan, API_BASE }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [viewerPage, setViewerPage] = useState(0);
  const [viewerPageCount, setViewerPageCount] = useState(0);
  const [viewerImageUrl, setViewerImageUrl] = useState(null);

  if (!modal) return null;

  const selectFileForViewing = async (relPath) => {
    setSelectedFile(relPath);
    setViewerPage(0);
    setViewerImageUrl(null);
    try {
      const pcRes = await fetch(`${API_BASE}/knowledge/files/${modal.lead_id}/pagecount/${encodeURIComponent(relPath)}`);
      const pcData = await pcRes.json();
      setViewerPageCount(pcData.pages || 0);
    } catch { setViewerPageCount(0); }
    setViewerImageUrl(`${API_BASE}/knowledge/files/${modal.lead_id}/view/${encodeURIComponent(relPath)}?page=0&dpi=150`);
  };

  const navigatePage = (newPage) => {
    if (newPage < 0 || newPage >= viewerPageCount) return;
    setViewerPage(newPage);
    setViewerImageUrl(`${API_BASE}/knowledge/files/${modal.lead_id}/view/${encodeURIComponent(selectedFile)}?page=${newPage}&dpi=150`);
  };

  const setFileClassification = async (relPath, classification) => {
    try {
      await fetch(`${API_BASE}/knowledge/files/${modal.lead_id}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path: relPath, classification }),
      });
      // reload files by calling onRescan equivalent — parent must refresh
    } catch (e) { alert('Failed to set classification'); }
  };

  const setBatchClassification = async (classification) => {
    try {
      const files = modal.files || [];
      if (!files.length) return;
      const overrides = {};
      files.forEach(f => { overrides[f.rel_path] = classification; });
      await fetch(`${API_BASE}/knowledge/files/${modal.lead_id}/override-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overrides }),
      });
    } catch (e) { alert('Failed to batch classify'); }
  };

  const files = modal.files || [];
  const planFiles = files.filter(f => f.classification === 'plan');
  const specFiles = files.filter(f => f.classification === 'spec');
  const otherFiles = files.filter(f => f.classification === 'other');
  const ignoreFiles = files.filter(f => f.classification === 'ignore');

  const plans = planFiles.length, specs = specFiles.length,
    other = otherFiles.length, ignored = ignoreFiles.length;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-6 max-w-7xl w-full mx-4 shadow-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-xl font-bold text-white flex items-center gap-2"><FolderOpen className="text-blue-400" size={20} />File Browser</h3>
            <p className="text-xs text-slate-500 mt-1">Click a file to preview. Use classification buttons to tag files.</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors"><X size={24} /></button>
        </div>

        {modal.error && <div className="text-red-400 text-sm mb-3">{modal.error}</div>}

        {/* Two-panel layout */}
        <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0 overflow-hidden">
          {/* Left — file list */}
          <div className="w-full md:w-80 flex-shrink-0 overflow-y-auto border border-slate-700 rounded-xl bg-slate-800/50 p-3 max-h-52 md:max-h-none">
            {files.length === 0 ? (
              <div className="text-center py-12 text-slate-600 italic text-sm">No PDF files found. Make sure files have been downloaded.</div>
            ) : (
              <>
                {/* Batch actions */}
                <div className="flex gap-1 mb-3 pb-2 border-b border-slate-700/50">
                  <span className="text-[9px] text-slate-500 font-medium self-center mr-1">All:</span>
                  {[['plan', 'Plans'], ['spec', 'Specs'], ['other', 'Other'], ['ignore', 'Ignore']].map(([cls, label]) => (
                    <button key={cls} onClick={() => setBatchClassification(cls)}
                      className={`px-2 py-1 rounded text-[9px] font-semibold border transition ${classColor(cls)} hover:brightness-125`}>
                      {label}
                    </button>
                  ))}
                </div>

                {[['plan', 'Plans', planFiles], ['spec', 'Specs', specFiles], ['other', 'Other', otherFiles], ['ignore', 'Ignored', ignoreFiles]].map(([group, groupLabel, groupFiles]) => {
                  if (!groupFiles.length) return null;
                  return (
                    <div key={group} className="mb-4">
                      <div className={`text-[10px] font-bold uppercase tracking-widest mb-2 px-1 ${group === 'plan' ? 'text-blue-400' : group === 'spec' ? 'text-green-400' : group === 'ignore' ? 'text-red-400' : 'text-slate-400'}`}>
                        {groupLabel} ({groupFiles.length})
                      </div>
                      {groupFiles.map((file, idx) => (
                        <div key={`${group}-${idx}`}
                          onClick={() => selectFileForViewing(file.rel_path)}
                          className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer mb-1 transition-all ${file.classification === 'ignore' ? 'opacity-50' : ''} ${selectedFile === file.rel_path ? 'bg-blue-600/20 border border-blue-500/40 ring-1 ring-blue-500/30' : 'hover:bg-slate-700/50 border border-transparent'}`}>
                          <div className="w-8 h-10 bg-slate-950 rounded flex-shrink-0 flex items-center justify-center">
                            <FileText size={14} className={file.classification === 'plan' ? 'text-blue-500' : file.classification === 'spec' ? 'text-green-500' : file.classification === 'ignore' ? 'text-red-500' : 'text-slate-600'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={`text-[11px] font-medium truncate ${file.classification === 'ignore' ? 'text-slate-500 line-through' : 'text-white'}`} title={file.filename}>{file.filename}</div>
                            <div className="text-[10px] text-slate-500">{file.size_kb > 1024 ? `${(file.size_kb / 1024).toFixed(1)} MB` : `${file.size_kb} KB`}</div>
                            <div className="flex gap-1 mt-1">
                              {['plan', 'spec', 'other', 'ignore'].map(cls => (
                                <button key={cls} onClick={e => { e.stopPropagation(); setFileClassification(file.rel_path, cls); }}
                                  className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border transition ${file.classification === cls ? classColor(cls) + ' ring-1 ring-white/20' : 'bg-slate-700/50 text-slate-600 border-slate-600/50 hover:text-white hover:bg-slate-600'}`}>
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

          {/* Right — page viewer */}
          <div className="flex-1 min-h-48 md:min-h-0 min-w-0 flex flex-col border border-slate-700 rounded-xl bg-slate-950/50 overflow-hidden">
            {selectedFile ? (
              <>
                <div className="flex items-center justify-between px-4 py-2 bg-slate-800/80 border-b border-slate-700">
                  <button onClick={() => navigatePage(viewerPage - 1)} disabled={viewerPage <= 0}
                    className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors flex items-center gap-1">
                    <ChevronLeft size={14} /> Prev
                  </button>
                  <span className="text-xs text-slate-300 font-medium">Page {viewerPage + 1} of {viewerPageCount || '?'}</span>
                  <button onClick={() => navigatePage(viewerPage + 1)} disabled={viewerPage >= viewerPageCount - 1}
                    className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors flex items-center gap-1">
                    Next <ChevronRight size={14} />
                  </button>
                </div>
                <div className="flex-1 overflow-auto flex items-start justify-center p-2">
                  {viewerImageUrl
                    ? <img src={viewerImageUrl} alt={`Page ${viewerPage + 1}`} className="max-w-full h-auto" />
                    : <div className="text-slate-600 text-sm mt-20">Loading...</div>}
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
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mt-4 pt-3 border-t border-slate-700/50">
          <div className="text-[11px] text-slate-500">
            {plans} Plan{plans !== 1 ? 's' : ''}, {specs} Spec{specs !== 1 ? 's' : ''}, {other} Other{ignored ? `, ${ignored} Ignored` : ''}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg transition-colors text-sm">Close</button>
            <button onClick={() => { onRescan(modal.lead_id); onClose(); }}
              className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded-lg transition-colors flex items-center gap-2 text-sm">
              <RefreshCw size={14} />Rescan with Changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
