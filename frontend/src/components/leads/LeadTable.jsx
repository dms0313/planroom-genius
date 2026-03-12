import React, { useState, useEffect, useMemo } from 'react';
import {
  Search, Eye, EyeOff, Zap, ArrowUpDown,
  ChevronLeft, ChevronRight, RefreshCw, X,
  Brain, Trash2, Cloud, ExternalLink, Download, FolderOpen,
} from 'lucide-react';
import { PREDEFINED_TAGS, tagColorClass, getSystemTags } from '../../lib/tags';
import LeadRow from './LeadRow';

// ── Utility helpers (also exported for re-use) ───────────────────────────────

export const isExpired = (bidDate) => {
  if (!bidDate || bidDate === 'N/A' || bidDate === 'TBD') return false;
  try {
    const d = new Date(bidDate);
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return d < t;
  } catch {
    return false;
  }
};

export const formatDate = (dateStr) => {
  if (!dateStr || dateStr === 'N/A' || dateStr === 'TBD') return dateStr || 'N/A';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return dateStr;
  }
};

export const isDueToday = (bidDate) => {
  if (!bidDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(bidDate);
  d.setHours(0, 0, 0, 0);
  return d.getTime() === today.getTime();
};

export const isDueSoon = (bidDate) => {
  if (!bidDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(bidDate);
  d.setHours(0, 0, 0, 0);
  const diff = (d - today) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 3;
};

// ── LeadTable ────────────────────────────────────────────────────────────────

/**
 * LeadTable — table shell with toolbar, filters, pagination, and per-row expansion.
 *
 * Props are passed through from the parent Dashboard/page orchestrator.
 * `leads` should already be filtered+sorted by the parent.
 */
const LeadTable = ({
  leads = [],
  uniqueSites = [],
  siteFilter,
  setSiteFilter,
  sortConfig,
  setSortConfig,
  searchQuery,
  setSearchQuery,
  showHidden,
  setShowHidden,
  showExpired,
  setShowExpired,
  knowledgeScanning,
  triggerKnowledgeScan,
  scanningIds,
  toggleLeadStyle,
  deleteLead,
  setContactPopup,
  setDescriptionPopup,
  openPointToFile,
  openFolderBrowserForLead,
  notionStatus,
  sendToNotion,
  triggerDeepScan,
  triggerQuickScan,
  API_BASE,
}) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedLeadId, setExpandedLeadId] = useState(null);
  const [expandedThumbnail, setExpandedThumbnail] = useState(null);
  const [tagPicker, setTagPicker] = useState(null); // { leadId, top, left }
  const [activeTagFilters, setActiveTagFilters] = useState([]);
  const [tagFiltersExpanded, setTagFiltersExpanded] = useState(false);
  const [editingCell, setEditingCell] = useState(null); // { leadId, field }
  const [qaQuestion, setQaQuestion] = useState('');
  const [qaLoading, setQaLoading] = useState(false);

  const ITEMS_PER_PAGE = 50;

  // ── Tag-filtered data ──────────────────────────────────────────────────────
  const visibleData = useMemo(() => {
    if (activeTagFilters.length === 0) return leads;
    return leads.filter((lead) => {
      const systemTags = getSystemTags(lead);
      return activeTagFilters.some(
        (tagId) =>
          lead.tags?.some((t) => t.label === tagId) || systemTags.includes(tagId)
      );
    });
  }, [leads, activeTagFilters]);

  const totalPages = Math.ceil(visibleData.length / ITEMS_PER_PAGE);

  // Clamp page when data shrinks
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) setCurrentPage(totalPages);
  }, [visibleData.length, totalPages, currentPage]);

  const paginatedData = visibleData.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  const handlePageChange = (p) => {
    if (p >= 1 && p <= totalPages) setCurrentPage(p);
  };

  // ── Thumbnail fetch when row expands ──────────────────────────────────────
  useEffect(() => {
    if (!expandedLeadId) { setExpandedThumbnail(null); return; }
    const lead = leads.find((l) => l.id === expandedLeadId);
    if (!lead || (!lead.local_file_path && !lead.files_link && !lead.gdrive_link)) {
      setExpandedThumbnail(null);
      return;
    }
    fetch(`${API_BASE}/knowledge/thumbnail/${expandedLeadId}`)
      .then((r) => r.json())
      .then((d) => setExpandedThumbnail(d.thumbnail))
      .catch(() => setExpandedThumbnail(null));
  }, [expandedLeadId, API_BASE]);

  // ── Tag picker close-on-outside-click ─────────────────────────────────────
  useEffect(() => {
    if (!tagPicker) return;
    const close = () => setTagPicker(null);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [tagPicker]);

  // ── Sorting ───────────────────────────────────────────────────────────────
  const handleSort = (key) => {
    const direction =
      sortConfig?.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc';
    setSortConfig({ key, direction });
  };

  // ── Tag helpers ───────────────────────────────────────────────────────────
  const toggleLeadTag = async (lead, tagId) => {
    const predefined = PREDEFINED_TAGS.find((t) => t.id === tagId);
    if (!predefined) return;
    const currentTags = lead.tags || [];
    const hasTag = currentTags.some((t) => t.label === tagId);
    const newTags = hasTag
      ? currentTags.filter((t) => t.label !== tagId)
      : [...currentTags, { label: predefined.label, color: predefined.color, hover: predefined.hint }];
    await toggleLeadStyle(lead, 'tags', newTags);
  };

  const openTagPicker = (leadId, event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setTagPicker(
      tagPicker?.leadId === leadId ? null : { leadId, top: rect.bottom + 6, left: rect.left }
    );
  };

  // ── Q&A helper ────────────────────────────────────────────────────────────
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
      toggleLeadStyle({ id: leadId }, 'qa_history', resData.qa_history);
    } catch (e) {
      console.error('Q&A failed:', e);
      alert('Failed to ask question. Please try again.');
    } finally {
      setQaLoading(false);
    }
  };

  // ── SortHeader sub-component ──────────────────────────────────────────────
  const SortHeader = ({ label, sortKey, className = '' }) => (
    <th
      className={`px-4 py-3 cursor-pointer hover:text-slate-300 transition-colors select-none ${className}`}
      onClick={() => handleSort(sortKey)}
    >
      <div className={`flex items-center gap-1 ${className.includes('text-center') ? 'justify-center' : ''}`}>
        {label}
        {sortConfig?.key === sortKey && (
          <ArrowUpDown
            size={12}
            className={sortConfig.direction === 'asc' ? 'text-orange-400 rotate-180' : 'text-orange-400'}
          />
        )}
      </div>
    </th>
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="mb-8 bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col">
        {/* ── Toolbar ── */}
        <div className="p-3 md:p-4 border-b border-slate-800 flex flex-col gap-2 md:gap-3 bg-slate-900/50 backdrop-blur">
          {/* Row 1: title + controls */}
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2">
            <h2 className="text-lg font-bold text-white flex items-center gap-3">
              Leads
              <span className="bg-slate-800 text-slate-400 text-xs px-2 py-1 rounded-full">
                {leads.length}
              </span>
            </h2>
            <div className="flex items-center gap-2 flex-wrap">
              {/* Search */}
              <div className="relative flex-1 sm:flex-none">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
                <input
                  type="text"
                  placeholder="Search leads..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-slate-800 text-slate-200 pl-9 pr-4 py-1.5 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-slate-600 w-full sm:w-52"
                />
              </div>
              {/* Show/hide expired */}
              <button
                onClick={() => setShowExpired(!showExpired)}
                className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium transition ${
                  showExpired
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
                }`}
                title={showExpired ? 'Hide expired' : 'Show expired'}
              >
                <Eye size={13} />
                Expired
              </button>
              {/* Show/hide manually hidden */}
              <button
                onClick={() => setShowHidden(!showHidden)}
                className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium transition ${
                  showHidden
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
                }`}
                title={showHidden ? 'Hide hidden' : 'Show hidden'}
              >
                <Eye size={13} />
                Hidden
              </button>
              {/* AI Scan All */}
              <button
                onClick={triggerKnowledgeScan}
                disabled={knowledgeScanning}
                className="flex items-center gap-1.5 px-3 py-1 bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 border border-purple-600/30 rounded-lg text-xs font-semibold transition"
              >
                {knowledgeScanning
                  ? <RefreshCw size={12} className="animate-spin" />
                  : <Zap size={12} />
                }
                {knowledgeScanning ? 'Scanning...' : 'AI Scan All'}
              </button>
              {/* Pagination controls in toolbar */}
              {totalPages > 1 && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span>Page {currentPage} of {totalPages}</span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => handlePageChange(currentPage - 1)}
                      disabled={currentPage === 1}
                      className="p-1 rounded hover:bg-slate-800 disabled:opacity-30"
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <button
                      onClick={() => handlePageChange(currentPage + 1)}
                      disabled={currentPage === totalPages}
                      className="p-1 rounded hover:bg-slate-800 disabled:opacity-30"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Row 2: Source filter */}
          {uniqueSites.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-slate-500 uppercase tracking-wide">Planroom:</span>
              <button
                onClick={() => setSiteFilter('all')}
                className={`px-3 py-1 rounded text-xs font-semibold transition ${
                  siteFilter === 'all'
                    ? 'bg-[#ed2028] text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                All
              </button>
              {uniqueSites.map((site) => (
                <button
                  key={site}
                  onClick={() => setSiteFilter(site)}
                  className={`px-3 py-1 rounded text-xs font-semibold transition ${
                    siteFilter === site
                      ? 'bg-[#ed2028] text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {site}
                </button>
              ))}
            </div>
          )}

          {/* Row 3: Tag filter bar */}
          {(() => {
            const allGroups = ['scope', 'flags', 'construction', 'projtype', 'location', 'workflow'];
            const visibleGroups = tagFiltersExpanded ? allGroups : allGroups.slice(0, 1);
            return (
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0 font-semibold mr-0.5">
                  Filter:
                </span>
                {visibleGroups.map((grp, gi) => {
                  const tags = PREDEFINED_TAGS.filter((t) => t.group === grp);
                  return (
                    <React.Fragment key={grp}>
                      {gi > 0 && <span className="text-[10px] text-slate-700 px-0.5">|</span>}
                      {tags.map((tag) => (
                        <button
                          key={tag.id}
                          onClick={() =>
                            setActiveTagFilters((prev) =>
                              prev.includes(tag.id)
                                ? prev.filter((t) => t !== tag.id)
                                : [...prev, tag.id]
                            )
                          }
                          title={tag.hint}
                          className={`text-[10px] px-2 py-0.5 rounded border transition-all ${
                            activeTagFilters.includes(tag.id)
                              ? tagColorClass(tag.color)
                              : 'bg-transparent text-slate-600 border-slate-700/50 hover:border-slate-500 hover:text-slate-400'
                          }`}
                        >
                          {tag.label}
                        </button>
                      ))}
                    </React.Fragment>
                  );
                })}
                <button
                  onClick={() => setTagFiltersExpanded((v) => !v)}
                  className="text-[10px] px-2 py-0.5 rounded border border-slate-700/50 text-slate-500 hover:text-slate-300 hover:border-slate-500 transition-all ml-0.5"
                >
                  {tagFiltersExpanded ? '▲ Less' : '▼ More'}
                </button>
                {activeTagFilters.length > 0 && (
                  <>
                    <button
                      onClick={() => setActiveTagFilters([])}
                      className="text-[10px] px-1.5 py-0.5 text-slate-500 hover:text-red-400 transition-colors ml-1"
                    >
                      × clear
                    </button>
                    <span className="text-[10px] text-slate-500 ml-1">
                      — showing {visibleData.length} of {leads.length}
                    </span>
                  </>
                )}
              </div>
            );
          })()}
        </div>

        {/* ── Desktop table ── */}
        <div className="hidden md:block overflow-x-auto flex-grow">
          <table className="w-full table-fixed text-left text-xs text-slate-400">
            <colgroup>
              <col className="w-[70px]" />
              <col className="w-[22%]" />
              <col className="w-[280px]" />
              <col className="w-[11%]" />
              <col className="w-[10%]" />
              <col className="w-[9%]" />
              <col className="w-[75px]" />
              <col className="w-[90px]" />
            </colgroup>
            <thead className="bg-slate-950/50 text-xs uppercase font-semibold text-slate-500 sticky top-0">
              <tr>
                <th className="px-2 py-3 whitespace-nowrap"></th>
                <SortHeader label="Project" sortKey="name" />
                <th className="px-2 py-3 whitespace-nowrap">Tags</th>
                <SortHeader label="Company / Contact" sortKey="company" />
                <SortHeader label="Bid Date" sortKey="bid_date" className="whitespace-nowrap" />
                <SortHeader label="Location" sortKey="location" />
                <th className="px-4 py-3 text-center whitespace-nowrap">Files</th>
                <th className="px-4 py-3 text-center whitespace-nowrap">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {paginatedData.map((lead, i) => (
                <LeadRow
                  key={lead.id || i}
                  lead={lead}
                  index={i}
                  expanded={expandedLeadId === lead.id}
                  onToggleExpand={() =>
                    setExpandedLeadId(expandedLeadId === lead.id ? null : lead.id)
                  }
                  editingCell={editingCell}
                  setEditingCell={setEditingCell}
                  scanningIds={scanningIds}
                  toggleLeadStyle={toggleLeadStyle}
                  deleteLead={deleteLead}
                  setContactPopup={setContactPopup}
                  setDescriptionPopup={setDescriptionPopup}
                  openPointToFile={openPointToFile}
                  openFolderBrowserForLead={openFolderBrowserForLead}
                  notionStatus={notionStatus}
                  sendToNotion={sendToNotion}
                  triggerDeepScan={triggerDeepScan}
                  API_BASE={API_BASE}
                  expandedThumbnail={expandedLeadId === lead.id ? expandedThumbnail : null}
                  tagPicker={tagPicker}
                  onToggleTag={toggleLeadTag}
                  onOpenTagPicker={openTagPicker}
                  qaQuestion={qaQuestion}
                  setQaQuestion={setQaQuestion}
                  qaLoading={qaLoading}
                  onAskQuestion={askProjectQuestion}
                />
              ))}
              {leads.length === 0 && (
                <tr>
                  <td colSpan="8" className="px-6 py-12 text-center text-slate-600 italic">
                    No active leads found in this category.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* ── Mobile card list ── */}
        <div className="md:hidden divide-y divide-slate-800/50">
          {paginatedData.map((lead, i) => {
            const expired = isExpired(lead.bid_date);
            const isCardExpanded = expandedLeadId === lead.id;
            const highlightBg = (() => {
              if (lead.highlight === 'green') return 'bg-green-900/40 border-l-4 border-l-green-500';
              if (lead.highlight === 'yellow') return 'bg-yellow-900/40 border-l-4 border-l-yellow-500';
              if (lead.highlight === 'red') return 'bg-red-900/40 border-l-4 border-l-red-500';
              return '';
            })();
            return (
              <div
                key={lead.id || i}
                className={`p-3 transition ${expired ? 'opacity-40' : ''} ${lead.hidden ? 'opacity-30 grayscale' : ''} ${highlightBg} ${lead.strikethrough ? 'opacity-50' : ''}`}
              >
                <div className="flex items-start gap-2">
                  <div className="flex gap-0.5 pt-1 flex-shrink-0">
                    <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'green' ? null : 'green')} className={`p-1 rounded ${lead.highlight === 'green' ? 'bg-green-600' : 'bg-slate-700'}`}><span className="w-2 h-2 rounded-full bg-green-400 block" /></button>
                    <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'yellow' ? null : 'yellow')} className={`p-1 rounded ${lead.highlight === 'yellow' ? 'bg-yellow-600' : 'bg-slate-700'}`}><span className="w-2 h-2 rounded-full bg-yellow-400 block" /></button>
                    <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'red' ? null : 'red')} className={`p-1 rounded ${lead.highlight === 'red' ? 'bg-red-600' : 'bg-slate-700'}`}><span className="w-2 h-2 rounded-full bg-red-400 block" /></button>
                    <button onClick={() => toggleLeadStyle(lead, 'strikethrough', !lead.strikethrough)} className={`p-1 rounded ${lead.strikethrough ? 'bg-slate-500' : 'bg-slate-700'}`}><span className="w-2 h-0.5 bg-slate-300 block" /></button>
                  </div>
                  <div className="flex-1 min-w-0">
                    <button
                      onClick={() => setExpandedLeadId(isCardExpanded ? null : lead.id)}
                      className="flex items-start gap-1.5 text-left w-full"
                    >
                      {isCardExpanded
                        ? <ChevronLeft size={14} className="text-orange-400 mt-0.5 flex-shrink-0 rotate-90" />
                        : <ChevronRight size={14} className="text-slate-500 mt-0.5 flex-shrink-0 -rotate-90" />
                      }
                      <div className="min-w-0">
                        <div className={`text-sm font-medium leading-tight ${isCardExpanded ? 'text-orange-400' : 'text-slate-200'}`}>
                          {lead.name}
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          {expired && <span className="text-[10px] bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded">EXPIRED</span>}
                          <span className="text-[10px] text-slate-600">{lead.site}</span>
                        </div>
                      </div>
                    </button>
                    <input
                      type="text"
                      defaultValue={lead.short_comment || ''}
                      onBlur={(e) => toggleLeadStyle(lead, 'short_comment', e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                      placeholder="Add comment..."
                      className="bg-transparent border-0 border-b border-transparent hover:border-slate-700 focus:border-orange-500 text-[10px] text-slate-400 placeholder-slate-700 w-full focus:outline-none transition-colors mt-1"
                    />
                  </div>
                </div>
                <div className="mt-2 pl-9 text-xs space-y-0.5">
                  {lead.company && lead.company !== 'N/A' && (
                    <div><span className="text-slate-500">Co: </span>
                      <button onClick={() => setContactPopup(lead)} className="text-slate-300 hover:text-orange-400 transition-colors">{lead.company}</button>
                    </div>
                  )}
                  {lead.contact_name && lead.contact_name !== 'N/A' && (
                    <div><span className="text-slate-500">Contact: </span><span className="text-slate-300">{lead.contact_name}</span></div>
                  )}
                  <div className="flex gap-4 flex-wrap">
                    <div><span className="text-slate-500">Bid: </span><span className={`font-mono ${expired ? 'text-red-400 line-through' : 'text-slate-300'}`}>{formatDate(lead.bid_date)}</span></div>
                    {lead.location && lead.location !== 'N/A' && <div><span className="text-slate-500">Loc: </span><span className="text-slate-300">{lead.location}</span></div>}
                  </div>
                </div>
                <div className="flex gap-1 mt-2 pl-9 flex-wrap items-center">
                  {lead.gdrive_link ? <a href={lead.gdrive_link} target="_blank" rel="noopener noreferrer" className="p-1.5 bg-blue-500 text-white rounded" onClick={(e) => e.stopPropagation()}><Cloud size={12} /></a>
                   : lead.files_link ? <button onClick={() => fetch(`${API_BASE}/open-folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: lead.files_link }) })} className="p-1.5 bg-yellow-600 text-white rounded"><ExternalLink size={12} /></button>
                   : lead.local_file_path ? <a href={`${API_BASE}${lead.local_file_path}`} download className="p-1.5 bg-green-600 text-white rounded"><Download size={12} /></a>
                   : null}
                  <button onClick={() => triggerDeepScan(lead.id)} disabled={scanningIds.has(lead.id)} className="p-1.5 bg-slate-700 hover:bg-violet-600 text-slate-400 hover:text-white rounded disabled:opacity-70"><Brain size={12} /></button>
                  <button onClick={() => setDescriptionPopup(lead)} className="flex items-center gap-1 px-2 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[10px] font-medium"><Eye size={10} /> Details</button>
                  <button onClick={() => deleteLead(lead)} className="p-1.5 bg-slate-700 hover:bg-red-600 text-slate-400 hover:text-white rounded"><Trash2 size={12} /></button>
                </div>
                {isCardExpanded && (
                  <div className="mt-3 pl-9 border-t border-slate-700/50 pt-3 space-y-3">
                    <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                      {lead.knowledge_notes || (lead.description ? lead.description.replace(/<[^>]+>/g, ' ').trim() : <span className="text-slate-500 italic">No summary available.</span>)}
                    </p>
                    <div>
                      <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-widest mb-1">Internal Comments</h4>
                      <textarea
                        defaultValue={lead.comments || ''}
                        onBlur={(e) => toggleLeadStyle(lead, 'comments', e.target.value)}
                        placeholder="Add internal notes..."
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-lg p-3 text-xs text-slate-300 placeholder-slate-600 focus:ring-1 focus:ring-blue-500 focus:outline-none resize-y min-h-[60px]"
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => setDescriptionPopup(lead)} className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-bold flex items-center gap-2"><Eye size={14} /> View Full Details</button>
                      <button onClick={() => openPointToFile(lead.id)} className="px-3 py-2 bg-slate-700 hover:bg-orange-600 text-white rounded-lg text-xs font-bold flex items-center gap-2"><FolderOpen size={14} /> Browse Files</button>
                      <button onClick={() => triggerDeepScan(lead.id)} disabled={scanningIds.has(lead.id)} className="px-3 py-2 bg-purple-700 hover:bg-purple-500 text-white rounded-lg text-xs font-bold flex items-center gap-2 disabled:opacity-50"><Brain size={14} /> Deep Scan</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {leads.length === 0 && (
            <div className="px-6 py-12 text-center text-slate-600 italic">
              No active leads found in this category.
            </div>
          )}
        </div>

        {/* ── Bottom pagination bar ── */}
        {totalPages > 1 && (
          <div className="p-3 border-t border-slate-800 bg-slate-900/50 flex justify-between items-center text-xs text-slate-400">
            <span>
              Showing {paginatedData.length} of {visibleData.length} leads
              {activeTagFilters.length > 0 ? ` (filtered from ${leads.length})` : ''}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="px-2 py-1 bg-slate-800 rounded hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <span className="flex items-center px-2">Page {currentPage} of {totalPages}</span>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                className="px-2 py-1 bg-slate-800 rounded hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Fixed-position tag picker (rendered outside overflow container) ── */}
      {tagPicker && (() => {
        const pickerLead =
          visibleData.find((l) => l.id === tagPicker.leadId) ||
          leads.find((l) => l.id === tagPicker.leadId);
        if (!pickerLead) return null;

        const TagGroup = ({ label, group }) => {
          const tags = PREDEFINED_TAGS.filter((t) => t.group === group);
          if (!tags.length) return null;
          return (
            <div className="mb-2.5">
              <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">{label}</div>
              <div className="flex flex-wrap gap-1">
                {tags.map((tag) => {
                  const active = pickerLead.tags?.some((t) => t.label === tag.id);
                  return (
                    <button
                      key={tag.id}
                      onClick={async () => { await toggleLeadTag(pickerLead, tag.id); }}
                      title={tag.hint}
                      className={`text-[10px] px-2 py-0.5 rounded border transition-all ${
                        active
                          ? tagColorClass(tag.color) + ' font-semibold'
                          : 'bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-500 hover:text-slate-200'
                      }`}
                    >
                      {active ? '✓ ' : ''}{tag.label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        };

        return (
          <div
            style={{ position: 'fixed', top: tagPicker.top, left: tagPicker.left, zIndex: 9999 }}
            className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-3 w-80 max-h-[80vh] overflow-y-auto"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-3">
              <span className="text-[11px] text-slate-300 font-semibold">Assign Tags</span>
              <button
                onClick={() => setTagPicker(null)}
                className="text-slate-600 hover:text-slate-300 transition-colors"
              >
                <X size={12} />
              </button>
            </div>
            <TagGroup label="Scope" group="scope" />
            <TagGroup label="Flags / Requirements" group="flags" />
            <TagGroup label="Construction Type" group="construction" />
            <TagGroup label="Project Type" group="projtype" />
            <TagGroup label="Building Type" group="location" />
            <TagGroup label="Workflow" group="workflow" />
          </div>
        );
      })()}
    </>
  );
};

export default LeadTable;
