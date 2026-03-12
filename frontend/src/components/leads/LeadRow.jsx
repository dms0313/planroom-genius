import React from 'react';
import {
  Brain, Trash2, FileText, Cloud, ExternalLink, Download,
  ChevronDown, ChevronUp, Circle, Minus, FolderOpen, Eye,
  EyeOff, CheckCircle, Building2,
} from 'lucide-react';
import { PREDEFINED_TAGS, tagColorClass, getSystemTags } from '../../lib/tags';
import TagsCell from './TagsCell';

// ── Utility helpers ──────────────────────────────────────────────────────────

const isExpired = (bidDate) => {
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

const formatDate = (dateStr) => {
  if (!dateStr || dateStr === 'N/A' || dateStr === 'TBD') return dateStr || 'N/A';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return dateStr;
  }
};

const isDueToday = (bidDate) => {
  if (!bidDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(bidDate);
  d.setHours(0, 0, 0, 0);
  return d.getTime() === today.getTime();
};

const isDueSoon = (bidDate) => {
  if (!bidDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(bidDate);
  d.setHours(0, 0, 0, 0);
  const diff = (d - today) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 3;
};

const getHighlightBg = (highlight) => {
  if (highlight === 'green') return 'bg-green-900/40 border-l-4 border-l-green-500';
  if (highlight === 'yellow') return 'bg-yellow-900/40 border-l-4 border-l-yellow-500';
  if (highlight === 'red') return 'bg-red-900/40 border-l-4 border-l-red-500';
  return '';
};

const getCommentColor = (highlight) => {
  if (highlight === 'green') return 'text-green-300/70';
  if (highlight === 'yellow') return 'text-yellow-300/70';
  if (highlight === 'red') return 'text-red-300/70';
  return 'text-slate-400';
};

const stripHtml = (html) => {
  if (!html) return '';
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
};

// ── Notion button SVG ────────────────────────────────────────────────────────
const NotionIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
    <path d="M4 4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H4zm0 2h16v12H4V6zm2 2v2h2V8H6zm4 0v2h2V8h-2zm4 0v2h2V8h-2zm-8 4v2h2v-2H6zm4 0v2h2v-2h-2zm4 0v2h2v-2h-2z" />
  </svg>
);

const SpinnerSvg = ({ size = 12 }) => (
  <svg
    className="animate-spin"
    style={{ width: size, height: size }}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
  </svg>
);

// ── Main LeadRow Component ───────────────────────────────────────────────────

/**
 * LeadRow renders one table row (plus optional expanded detail row).
 * All inline editing for company, contact, bid_date, location is handled
 * via editingCell state owned by the parent LeadTable.
 */
const LeadRow = ({
  lead,
  index,
  expanded,
  onToggleExpand,
  editingCell,
  setEditingCell,
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
  API_BASE,
  expandedThumbnail,
  tagPicker,
  onToggleTag,
  onOpenTagPicker,
  qaQuestion,
  setQaQuestion,
  qaLoading,
  onAskQuestion,
}) => {
  const expired = isExpired(lead.bid_date);
  const highlightClass = getHighlightBg(lead.highlight);
  const hiddenClass = lead.hidden ? 'opacity-30 grayscale' : '';

  // Bid date colour
  const bidExpired = isExpired(lead.bid_date);
  const bidToday = isDueToday(lead.bid_date);
  const bidSoon = isDueSoon(lead.bid_date);
  const bidDateClass = bidExpired
    ? 'text-red-400 line-through'
    : bidToday
    ? 'text-red-400 font-bold'
    : bidSoon
    ? 'text-amber-400'
    : 'text-slate-300';

  // Check if a given field is currently being edited for this lead
  const isEditing = (field) =>
    editingCell && editingCell.leadId === lead.id && editingCell.field === field;

  const commitEdit = (field, value) => {
    setEditingCell(null);
    const trimmed = typeof value === 'string' ? value.trim() : value;
    toggleLeadStyle(lead, field, trimmed);
  };

  const ns = notionStatus?.[lead.id];

  // ── Compact row for strikethrough (already sent) ─────────────────────────
  if (lead.strikethrough) {
    return (
      <React.Fragment>
        <tr className="transition group opacity-35 hover:opacity-60">
          {/* Status dots */}
          <td className="px-2 py-0.5">
            <div className="flex gap-0.5">
              <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'green' ? null : 'green')} className={`p-1 rounded ${lead.highlight === 'green' ? 'bg-green-600' : 'bg-slate-700 hover:bg-green-600'}`} title="Green"><Circle size={6} className="text-green-400" fill={lead.highlight === 'green' ? 'currentColor' : 'none'} /></button>
              <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'yellow' ? null : 'yellow')} className={`p-1 rounded ${lead.highlight === 'yellow' ? 'bg-yellow-600' : 'bg-slate-700 hover:bg-yellow-600'}`} title="Yellow"><Circle size={6} className="text-yellow-400" fill={lead.highlight === 'yellow' ? 'currentColor' : 'none'} /></button>
              <button onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'red' ? null : 'red')} className={`p-1 rounded ${lead.highlight === 'red' ? 'bg-red-600' : 'bg-slate-700 hover:bg-red-600'}`} title="Red"><Circle size={6} className="text-red-400" fill={lead.highlight === 'red' ? 'currentColor' : 'none'} /></button>
              <button onClick={() => toggleLeadStyle(lead, 'strikethrough', false)} className="p-1 rounded bg-slate-500 hover:bg-slate-600" title="Unmark"><Minus size={6} className="text-slate-300" /></button>
            </div>
          </td>
          {/* Name (strikethrough) */}
          <td className="px-4 py-0.5" colSpan={5}>
            <span className="text-xs text-slate-600 line-through">{lead.name}</span>
            {lead.company && <span className="text-xs text-slate-700 ml-2">— {lead.company}</span>}
          </td>
          {/* Bid date */}
          <td className="px-4 py-0.5 text-xs text-slate-700 text-right whitespace-nowrap">
            {lead.bid_date && lead.bid_date !== 'N/A' ? formatDate(lead.bid_date) : ''}
          </td>
          {/* Delete */}
          <td className="px-2 py-0.5 text-right">
            <button onClick={() => deleteLead(lead)} className="p-1 text-slate-700 hover:text-red-500 opacity-0 group-hover:opacity-100 transition rounded"><Trash2 size={12} /></button>
          </td>
        </tr>
      </React.Fragment>
    );
  }

  // ── Desktop table row ────────────────────────────────────────────────────
  return (
    <React.Fragment>
      <tr
        className={`hover:bg-slate-800/30 transition group cursor-pointer ${expired ? 'opacity-40' : ''} ${hiddenClass} ${highlightClass}`}
        onClick={(e) => {
          if (e.target.closest('button, input, a, select, textarea')) return;
          onToggleExpand();
        }}
      >
        {/* ── Col 1: Color / strikethrough dots ── */}
        <td className="px-2 py-1">
          <div className="flex gap-0.5">
            <button
              onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'green' ? null : 'green')}
              className={`p-1 rounded ${lead.highlight === 'green' ? 'bg-green-600' : 'bg-slate-700 hover:bg-green-600'}`}
              title="Green"
            >
              <Circle size={8} className="text-green-400" fill={lead.highlight === 'green' ? 'currentColor' : 'none'} />
            </button>
            <button
              onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'yellow' ? null : 'yellow')}
              className={`p-1 rounded ${lead.highlight === 'yellow' ? 'bg-yellow-600' : 'bg-slate-700 hover:bg-yellow-600'}`}
              title="Yellow"
            >
              <Circle size={8} className="text-yellow-400" fill={lead.highlight === 'yellow' ? 'currentColor' : 'none'} />
            </button>
            <button
              onClick={() => toggleLeadStyle(lead, 'highlight', lead.highlight === 'red' ? null : 'red')}
              className={`p-1 rounded ${lead.highlight === 'red' ? 'bg-red-600' : 'bg-slate-700 hover:bg-red-600'}`}
              title="Red"
            >
              <Circle size={8} className="text-red-400" fill={lead.highlight === 'red' ? 'currentColor' : 'none'} />
            </button>
            <button
              onClick={() => toggleLeadStyle(lead, 'strikethrough', !lead.strikethrough)}
              className={`p-1 rounded ${lead.strikethrough ? 'bg-slate-500' : 'bg-slate-700 hover:bg-slate-500'}`}
              title="Mark reviewed"
            >
              <Minus size={8} className="text-slate-300" />
            </button>
          </div>
        </td>

        {/* ── Col 2: Project name, site, scan badges, inline comment ── */}
        <td className="px-4 py-1 font-medium text-slate-200 group-hover:text-orange-400 transition-colors">
          {/* Name row */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onToggleExpand()}
              className="text-left hover:text-orange-400 transition-colors flex items-center gap-1.5 min-w-0"
              title="Click to expand"
            >
              {expanded
                ? <ChevronUp size={13} className="text-orange-400 flex-shrink-0" />
                : <ChevronDown size={13} className="text-slate-500 flex-shrink-0" />
              }
              <span className="truncate text-sm">{lead.name}</span>
            </button>
          </div>
          {/* Sub-row: source badge + scan badge + comment + folder buttons */}
          <div className="flex items-center gap-1.5 mt-0.5">
            {expired && (
              <span className="text-[10px] bg-red-900/30 text-red-400 px-1.5 py-0 rounded leading-4">EXPIRED</span>
            )}
            <span className="text-[10px] text-slate-600 flex-shrink-0">{lead.site}</span>
            {lead.takeoff_timestamp ? (
              <span title={`Deep scan: ${new Date(lead.takeoff_timestamp).toLocaleDateString()}`} className="flex items-center gap-0.5 text-[9px] text-violet-400 bg-violet-500/10 border border-violet-500/20 px-1 py-0 rounded leading-4 flex-shrink-0"><Brain size={8} />deep</span>
            ) : lead.knowledge_last_scanned ? (
              <span title={`AI scan: ${new Date(lead.knowledge_last_scanned).toLocaleDateString()}`} className="flex items-center gap-0.5 text-[9px] text-slate-500 bg-slate-700/40 border border-slate-600/30 px-1 py-0 rounded leading-4 flex-shrink-0"><Brain size={8} />scanned</span>
            ) : null}
            <input
              type="text"
              defaultValue={lead.short_comment || ''}
              onBlur={(e) => toggleLeadStyle(lead, 'short_comment', e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
              placeholder="Add comment..."
              className={`bg-transparent border-0 border-b border-transparent hover:border-slate-700 focus:border-orange-500 text-[10px] ${getCommentColor(lead.highlight)} placeholder-slate-700 flex-1 min-w-0 focus:outline-none transition-colors`}
            />
            {/* Folder quick-actions — inline, always present, fade in on hover */}
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <button onClick={(e) => { e.stopPropagation(); openPointToFile(lead.id); }} className="p-0.5 bg-slate-700/70 hover:bg-orange-600 text-slate-500 hover:text-white rounded transition-colors" title="Browse project files"><FolderOpen size={10} /></button>
              <button onClick={(e) => { e.stopPropagation(); openFolderBrowserForLead(lead.id); }} className="p-0.5 bg-slate-700/70 hover:bg-blue-500 text-slate-500 hover:text-white rounded transition-colors" title="Set GDrive folder"><FolderOpen size={10} className="opacity-60" /></button>
            </div>
          </div>
        </td>

        {/* ── Col 3: Tags ── */}
        <td className="px-2 py-1">
          <TagsCell
            lead={lead}
            onToggleTag={onToggleTag}
            onOpenTagPicker={onOpenTagPicker}
            tagPicker={tagPicker}
          />
        </td>

        {/* ── Col 4: Company + Contact (merged) ── */}
        <td className="px-2 py-1">
          <div className="flex flex-col gap-0.5">
            {/* Company row */}
            <div className="flex items-center gap-1 group/company">
              {isEditing('company') ? (
                <input
                  autoFocus
                  defaultValue={lead.company !== 'N/A' ? lead.company || '' : ''}
                  onBlur={(e) => commitEdit('company', e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.target.blur();
                    if (e.key === 'Escape') setEditingCell(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="bg-slate-800 border border-slate-600 focus:border-orange-500 text-slate-200 text-xs px-1.5 py-0.5 rounded w-full focus:outline-none"
                />
              ) : (
                <>
                  <button
                    onClick={(e) => { e.stopPropagation(); setContactPopup(lead); }}
                    className="text-slate-300 truncate max-w-[140px] hover:text-orange-400 transition-colors text-left text-xs"
                    title="Click for details"
                  >
                    {lead.company && lead.company !== 'N/A'
                      ? lead.company
                      : <span className="text-slate-600 italic">No Company</span>
                    }
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingCell({ leadId: lead.id, field: 'company' }); }}
                    className="opacity-0 group-hover/company:opacity-100 transition-opacity p-0.5 text-slate-600 hover:text-slate-300 rounded"
                    title="Edit company"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                  </button>
                </>
              )}
            </div>
            {/* Contact row */}
            <div className="flex items-center gap-1 group/contact">
              {isEditing('contact_name') ? (
                <input
                  autoFocus
                  defaultValue={lead.contact_name !== 'N/A' ? lead.contact_name || '' : ''}
                  onBlur={(e) => commitEdit('contact_name', e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.target.blur();
                    if (e.key === 'Escape') setEditingCell(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="bg-slate-800 border border-slate-600 focus:border-orange-500 text-slate-200 text-[10px] px-1.5 py-0.5 rounded w-full focus:outline-none"
                />
              ) : (
                <>
                  <span className="text-[10px] text-slate-500 truncate max-w-[140px]">
                    {lead.contact_name && lead.contact_name !== 'N/A'
                      ? lead.contact_name
                      : <span className="italic">-</span>
                    }
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingCell({ leadId: lead.id, field: 'contact_name' }); }}
                    className="opacity-0 group-hover/contact:opacity-100 transition-opacity p-0.5 text-slate-600 hover:text-slate-300 rounded"
                    title="Edit contact"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                  </button>
                </>
              )}
            </div>
            {/* GC sub-label */}
            {lead.gc && lead.gc !== 'N/A' && (
              <span className="text-[9px] text-slate-600 truncate max-w-[140px]">GC: {lead.gc}</span>
            )}
          </div>
        </td>

        {/* ── Col 5: Bid Date ── */}
        <td className="px-2 py-1">
          <div className="flex items-center gap-1 group/biddate">
            {isEditing('bid_date') ? (
              <input
                autoFocus
                type="date"
                defaultValue={lead.bid_date && lead.bid_date !== 'N/A' ? lead.bid_date : ''}
                onBlur={(e) => commitEdit('bid_date', e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') e.target.blur();
                  if (e.key === 'Escape') setEditingCell(null);
                }}
                onClick={(e) => e.stopPropagation()}
                className="bg-slate-800 border border-slate-600 focus:border-orange-500 text-slate-200 text-xs px-1.5 py-0.5 rounded w-full focus:outline-none"
              />
            ) : (
              <>
                <span className={`font-mono whitespace-nowrap text-xs ${bidDateClass}`}>
                  {formatDate(lead.bid_date)}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingCell({ leadId: lead.id, field: 'bid_date' }); }}
                  className="opacity-0 group-hover/biddate:opacity-100 transition-opacity p-0.5 text-slate-600 hover:text-slate-300 rounded"
                  title="Edit bid date"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
              </>
            )}
          </div>
        </td>

        {/* ── Col 6: Location ── */}
        <td className="px-2 py-1">
          <div className="flex items-center gap-1 group/location">
            {isEditing('location') ? (
              <input
                autoFocus
                defaultValue={lead.location || ''}
                onBlur={(e) => commitEdit('location', e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') e.target.blur();
                  if (e.key === 'Escape') setEditingCell(null);
                }}
                onClick={(e) => e.stopPropagation()}
                className="bg-slate-800 border border-slate-600 focus:border-orange-500 text-slate-200 text-xs px-1.5 py-0.5 rounded w-full focus:outline-none"
              />
            ) : (
              <>
                <span className="text-slate-400 truncate max-w-[100px] text-xs" title={lead.location}>
                  {lead.location || 'N/A'}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingCell({ leadId: lead.id, field: 'location' }); }}
                  className="opacity-0 group-hover/location:opacity-100 transition-opacity p-0.5 text-slate-600 hover:text-slate-300 rounded"
                  title="Edit location"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
              </>
            )}
          </div>
        </td>

        {/* ── Col 7: Files ── */}
        <td className="px-4 py-1 text-center">
          <div className="flex justify-center gap-1">
            {lead.gdrive_link ? (
              <a
                href={lead.gdrive_link}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 bg-blue-500 hover:bg-blue-400 text-white rounded transition-colors flex items-center gap-1"
                title="View on Google Drive"
                onClick={(e) => e.stopPropagation()}
              >
                <Cloud size={12} />
              </a>
            ) : lead.files_link ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  fetch(`${API_BASE}/open-folder`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: lead.files_link }),
                  });
                }}
                className="p-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded transition-colors"
                title={`Open Local Folder: ${lead.files_link}`}
              >
                <ExternalLink size={12} />
              </button>
            ) : lead.local_file_path ? (
              <a
                href={`${API_BASE}${lead.local_file_path}`}
                download
                className="p-1.5 bg-green-600 hover:bg-green-500 text-white rounded transition-colors"
                title="Download Local File"
                onClick={(e) => e.stopPropagation()}
              >
                <Download size={12} />
              </a>
            ) : (
              <span className="text-slate-600 text-[10px]">-</span>
            )}
          </div>
        </td>

        {/* ── Col 8: Actions ── */}
        <td className="px-2 py-1 text-center">
          <div className="flex justify-center gap-1 flex-wrap">
            {/* Brain: deep scan only */}
            <button
              onClick={(e) => { e.stopPropagation(); triggerDeepScan(lead.id); }}
              disabled={scanningIds.has(lead.id)}
              className={`p-1.5 rounded transition-colors disabled:opacity-70 disabled:cursor-not-allowed ${
                lead.takeoff_timestamp
                  ? 'bg-violet-600/30 text-violet-300 hover:bg-violet-600 hover:text-white'
                  : 'bg-slate-700 text-slate-400 hover:bg-violet-600 hover:text-white'
              }`}
              title="Deep scan"
            >
              {scanningIds.has(lead.id) ? <SpinnerSvg size={12} /> : <Brain size={12} />}
            </button>
            {/* Notes / View Details */}
            <button
              onClick={(e) => { e.stopPropagation(); setDescriptionPopup(lead); }}
              className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-400 hover:text-white rounded transition-colors"
              title="View project details"
            >
              <FileText size={12} />
            </button>
            {/* Delete */}
            <button
              onClick={(e) => { e.stopPropagation(); deleteLead(lead); }}
              className="p-1.5 bg-slate-700 hover:bg-red-600 text-slate-400 hover:text-white rounded transition-colors"
              title="Delete lead"
            >
              <Trash2 size={12} />
            </button>
            {/* Notion */}
            <button
              onClick={(e) => { e.stopPropagation(); sendToNotion(lead); }}
              disabled={ns === 'loading'}
              title="Add to Notion (Open Quotes)"
              className={`flex items-center gap-0.5 px-1.5 py-1.5 rounded transition-colors text-[10px] font-medium disabled:opacity-70 ${
                ns === 'success'
                  ? 'bg-green-700 text-green-200'
                  : ns === 'error'
                  ? 'bg-red-800 text-red-200'
                  : 'bg-slate-700 hover:bg-slate-500 text-slate-300 hover:text-white'
              }`}
            >
              {ns === 'loading' ? (
                <SpinnerSvg size={10} />
              ) : ns === 'success' ? (
                <CheckCircle size={10} className="text-green-400" />
              ) : (
                <NotionIcon />
              )}
              {ns === 'success' ? 'Sent' : ns === 'error' ? 'Err' : 'N'}
            </button>
          </div>
        </td>
      </tr>

      {/* ── Expanded detail row ── */}
      {expanded && (
        <tr className="bg-slate-800/40 border-l-4 border-orange-500 animate-in slide-in-from-left-2 duration-200">
          <td colSpan="8" className="px-6 py-4">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-3">
                {/* Thumbnail */}
                {expandedThumbnail && (
                  <div className="w-32 h-40 bg-slate-950 rounded-lg overflow-hidden flex-shrink-0 mr-4 border border-slate-700">
                    <img
                      src={`data:image/png;base64,${expandedThumbnail}`}
                      alt="Title page"
                      className="w-full h-full object-contain"
                    />
                  </div>
                )}

                {/* Summary */}
                <div className="flex-1">
                  <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                    {lead.name}
                    <span className="text-xs font-normal text-slate-500">Project Summary</span>
                  </h4>
                  <p className="text-xs text-slate-300 max-w-3xl leading-relaxed whitespace-pre-wrap">
                    {lead.knowledge_notes
                      ? lead.knowledge_notes
                      : lead.description
                      ? stripHtml(lead.description)
                      : <span className="text-slate-500 italic">No summary available. Run AI scan for details.</span>
                    }
                  </p>

                  {/* Manufacturers & Vendors */}
                  {((lead.knowledge_required_manufacturers?.length > 0) || (lead.knowledge_required_vendors?.length > 0)) && (
                    <div className="mt-2 flex flex-col gap-1">
                      {lead.knowledge_required_manufacturers?.length > 0 && (
                        <div className="flex items-start gap-1.5 text-xs">
                          <span className="text-slate-500 shrink-0">Manufacturer(s):</span>
                          <span className="text-amber-300 font-medium">{lead.knowledge_required_manufacturers.join(', ')}</span>
                        </div>
                      )}
                      {lead.knowledge_required_vendors?.length > 0 && (
                        <div className="flex items-start gap-1.5 text-xs">
                          <span className="text-slate-500 shrink-0">Required Vendor(s):</span>
                          <span className="text-orange-300 font-medium">{lead.knowledge_required_vendors.join(', ')}</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tags summary in expanded */}
                  <div className="flex gap-2 mt-3 flex-wrap">
                    {getSystemTags(lead).map((tagId, idx) => {
                      const pt = PREDEFINED_TAGS.find((t) => t.id === tagId);
                      return pt ? (
                        <span
                          key={`st-${idx}`}
                          className={`text-[10px] px-2 py-0.5 rounded-full border cursor-default ${tagColorClass(pt.color)}`}
                          title={pt.hint}
                        >
                          {pt.label}
                        </span>
                      ) : null;
                    })}
                    {(lead.tags || []).map((tag, idx) => (
                      <span
                        key={`ut-${idx}`}
                        className={`text-[10px] px-2 py-0.5 rounded-full border cursor-default ${tagColorClass(tag.color)}`}
                      >
                        {tag.label}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex flex-row flex-wrap gap-2">
                  <button
                    onClick={() => setDescriptionPopup(lead)}
                    className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2"
                  >
                    <Eye size={14} /> View Full Details
                  </button>
                  <button
                    onClick={() => openPointToFile(lead.id)}
                    className="px-4 py-2 bg-slate-700 hover:bg-orange-600 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2"
                  >
                    <FolderOpen size={14} /> Browse Files
                  </button>
                  <button
                    onClick={() => triggerDeepScan(lead.id)}
                    disabled={scanningIds.has(lead.id)}
                    className="px-4 py-2 bg-purple-700 hover:bg-purple-500 text-white rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Deep analysis with extended thinking"
                  >
                    {scanningIds.has(lead.id) ? (
                      <><SpinnerSvg size={14} /> Scanning...</>
                    ) : (
                      <><Brain size={14} /> Deep Scan</>
                    )}
                  </button>
                </div>
              </div>

              {/* Also Bidding */}
              {lead.also_listed_by && lead.also_listed_by.length > 0 && (
                <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg px-4 py-3">
                  <h4 className="text-xs font-semibold text-blue-400 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                    <Building2 size={12} /> Also Bidding
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {lead.company && lead.company !== 'N/A' && (
                      <span className="text-[11px] bg-blue-500/10 border border-blue-500/20 text-blue-300 px-2.5 py-1 rounded-full flex items-center gap-1">
                        <Building2 size={10} className="text-blue-400" />
                        {lead.company}
                        <span className="text-blue-500/60 text-[10px]">via {lead.site}</span>
                      </span>
                    )}
                    {lead.also_listed_by.map((entry, idx) => (
                      <span
                        key={idx}
                        className="text-[11px] bg-slate-700/50 border border-slate-600/50 text-slate-300 px-2.5 py-1 rounded-full flex items-center gap-1"
                      >
                        <Building2 size={10} className="text-slate-500" />
                        {entry.gc || 'Unknown'}
                        <span className="text-slate-500 text-[10px]">via {entry.site}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

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
                <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-widest mb-2">
                  Ask AI About This Project
                </h4>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={qaQuestion}
                    onChange={(e) => setQaQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !qaLoading) onAskQuestion(lead.id);
                    }}
                    placeholder="What is the specified fire alarm panel?"
                    disabled={qaLoading}
                    className="flex-1 bg-slate-900/50 border border-slate-700/50 rounded-lg px-3 py-2 text-xs text-slate-300 placeholder-slate-600 focus:ring-1 focus:ring-cyan-500 focus:outline-none disabled:opacity-50"
                  />
                  <button
                    onClick={() => onAskQuestion(lead.id)}
                    disabled={qaLoading || !qaQuestion.trim()}
                    className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                  >
                    {qaLoading ? (
                      <><SpinnerSvg size={12} /> Thinking...</>
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
      )}
    </React.Fragment>
  );
};

export default LeadRow;
