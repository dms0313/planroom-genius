import React from 'react';
import { X, ExternalLink, Building2, MapPin, Brain, Shield, FileText, AlertTriangle, CheckCircle2, ClipboardCopy, CheckCircle, Zap } from 'lucide-react';
import { PREDEFINED_TAGS, tagColorClass, getSystemTags } from '../../lib/tags';

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

const buildTakeoffHtml = (lead) => {
  const h = [];
  const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const li = (label, val) => `<li><strong>${esc(label)}:</strong> ${esc(val)}</li>`;
  const bullet = (text) => `<li>${esc(text)}</li>`;

  h.push(`<h1>${esc(lead.name || 'Project')} — FA Takeoff</h1>`);

  const snap = lead.takeoff_snapshot;
  if (snap) {
    h.push('<h2>Project Snapshot</h2>');
    if (snap.scope_summary) h.push(`<p>${esc(snap.scope_summary)}</p>`);
    const pd = snap.project_details || {};
    const fields = [
      ['Project', pd.project_name], ['Address', pd.project_address || pd.project_location],
      ['Type', pd.project_type], ['Building', pd.building_type || pd.occupancy_type],
      ['Codes', Array.isArray(pd.applicable_codes) ? pd.applicable_codes.join(', ') : pd.applicable_codes],
      ['Occupancy', pd.occupancy_classification],
    ].filter(([, v]) => v);
    if (fields.length) h.push('<ul>' + fields.map(([k, v]) => li(k, v)).join('') + '</ul>');
  }

  const fab = lead.takeoff_fa_briefing;
  if (fab) {
    h.push('<h2>Fire Alarm Briefing</h2>');
    const fa = fab.fire_alarm_details || {};
    const items = [
      ['Panel Status', fa.panel_status || fa.existing_system], ['Sprinkler', fa.sprinkler_status],
      ['Voice Evac', fa.voice_evac || fa.voice_required], ['CO Detection', fa.co_detection],
    ].filter(([, v]) => v);
    if (items.length) h.push('<ul>' + items.map(([k, v]) => li(k, v)).join('') + '</ul>');
    const sp = fab.specifications || {};
    const specItems = [
      ['Control Panel', sp.CONTROL_PANEL], ['System Type', sp.SYSTEM_TYPE],
      ['Wiring', sp.WIRING_CLASS], ['Monitoring', sp.MONITORING],
      ['Audio', sp.AUDIO_SYSTEM],
      ['Approved Mfrs', Array.isArray(sp.APPROVED_MANUFACTURERS) ? sp.APPROVED_MANUFACTURERS.join(', ') : sp.APPROVED_MANUFACTURERS],
    ].filter(([, v]) => v && v !== 'unknown' && String(v).toLowerCase() !== 'addressable');
    if (specItems.length) { h.push('<p><strong>Key Specs</strong></p>'); h.push('<ul>' + specItems.map(([k, v]) => li(k, v)).join('') + '</ul>'); }
  }

  const notes = lead.takeoff_fa_notes;
  if (notes && notes.length) {
    h.push('<h2>Fire Alarm Notes</h2><ul>');
    notes.forEach(n => { const page = n.page ? `[p${n.page}] ` : ''; h.push(bullet(page + (n.content || (typeof n === 'string' ? n : JSON.stringify(n))))); });
    h.push('</ul>');
  }

  const pitfalls = lead.takeoff_pitfalls;
  const estNotes = lead.takeoff_estimating_notes;
  if ((pitfalls && pitfalls.length) || (estNotes && estNotes.length)) {
    h.push('<h2>Conflicts, Pitfalls &amp; Advice</h2><ul>');
    (pitfalls || []).forEach(p => h.push(bullet(typeof p === 'string' ? p : p.content || JSON.stringify(p))));
    (estNotes || []).forEach(n => h.push(bullet(typeof n === 'string' ? n : n.content || JSON.stringify(n))));
    h.push('</ul>');
  }

  const adv = lead.takeoff_competitive_advantages;
  if (adv && adv.length) {
    h.push('<h2>Competitive Advantages</h2><ul>');
    adv.forEach(a => h.push(bullet(typeof a === 'string' ? a : a.content || JSON.stringify(a))));
    h.push('</ul>');
  }

  const tags = lead.takeoff_project_tags;
  if (tags && tags.length) h.push(`<p><strong>Tags:</strong> ${esc(tags.map(t => t.label).join(', '))}</p>`);
  h.push(`<p><em>Deep Scan: ${new Date(lead.takeoff_timestamp).toLocaleDateString()}</em></p>`);
  return h.join('');
};

const copyRichHtml = (html) => {
  const el = document.createElement('div');
  el.innerHTML = html;
  el.style.position = 'fixed'; el.style.left = '-9999px'; el.style.top = '0'; el.style.opacity = '0';
  document.body.appendChild(el);
  const range = document.createRange(); range.selectNodeContents(el);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  document.execCommand('copy'); sel.removeAllRanges(); document.body.removeChild(el);
};

export default function ProjectDetailModal({ lead, onClose, onDeepScan }) {
  const [descExpanded, setDescExpanded] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  if (!lead) return null;

  const descText = stripHtml(lead.description) || lead.full_address || 'No description available';
  const isLong = descText.length > 200;
  const systemTags = getSystemTags(lead);

  const handleCopyTakeoff = () => {
    copyRichHtml(buildTakeoffHtml(lead));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-3 sm:p-4 max-w-3xl w-full mx-2 sm:mx-4 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <FileText className="text-orange-500" size={20} />Project Details
          </h3>
          <div className="flex gap-2 flex-wrap justify-end">
            {lead.url && (
              <a href={lead.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-blue-300 px-3 py-1 rounded-full transition-colors">
                <ExternalLink size={12} /> Open Project
              </a>
            )}
            <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors"><X size={20} /></button>
          </div>
        </div>

        <div className="space-y-2">
          {/* Project name */}
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Project Name</div>
            <div className="text-base font-semibold text-white">{lead.name || 'N/A'}</div>
          </div>

          {/* Description */}
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Description / Full Address</div>
            <div className={`text-sm text-slate-300 whitespace-pre-wrap ${isLong && !descExpanded ? 'max-h-[4.5rem] overflow-hidden' : ''}`}>
              {descText}
            </div>
            {isLong && (
              <button onClick={() => setDescExpanded(e => !e)} className="text-[11px] text-blue-400 hover:text-blue-300 mt-1">
                {descExpanded ? 'Show less' : 'Show more'}
              </button>
            )}
          </div>

          {/* Location + Source row */}
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="bg-slate-800/50 rounded-lg p-3 flex-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1"><MapPin size={10} />Location</div>
              <div className="text-sm text-slate-300">{lead.location || 'N/A'}</div>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3 flex-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Source</div>
              <div className="text-sm text-slate-300">{lead.site || lead.source || 'N/A'}</div>
              {lead.url && (
                <a href={lead.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-400 hover:text-blue-300 underline underline-offset-2 break-all mt-1 block">
                  {lead.url}
                </a>
              )}
            </div>
          </div>

          {/* Also Bidding */}
          {lead.also_listed_by && lead.also_listed_by.length > 0 && (
            <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-3">
              <div className="text-[10px] text-blue-400 uppercase tracking-wide mb-2 flex items-center gap-1"><Building2 size={10} />Also Bidding</div>
              <ul className="space-y-1">
                {lead.also_listed_by.map((entry, idx) => (
                  <li key={idx} className="text-sm text-slate-300 flex items-center gap-2">
                    <Building2 size={12} className="text-slate-500" />
                    {entry.gc || 'Unknown'} <span className="text-slate-500 text-xs">(via {entry.site})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Contractors Bidding */}
          {lead.planhub_gcs && lead.planhub_gcs.length > 0 && (
            <div className="bg-slate-800/50 border border-slate-600/40 rounded-lg p-3">
              <div className="text-[10px] text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1">
                <Building2 size={10} />Contractors Bidding ({lead.planhub_gcs.length})
              </div>
              <ul className="space-y-2">
                {lead.planhub_gcs.map((gc, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <Building2 size={11} className="text-slate-500 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-sm text-slate-200 font-medium">{gc.company_name || 'Unknown'}</span>
                      {gc.user_name && <span className="text-slate-400 text-xs ml-1.5">· {gc.user_name}</span>}
                      {(gc.email_address || gc.phone_number) && (
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          {gc.email_address && <span>{gc.email_address}</span>}
                          {gc.email_address && gc.phone_number && <span className="mx-1">·</span>}
                          {gc.phone_number && <span>{gc.phone_number}</span>}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tags */}
          <div className="flex gap-2 flex-wrap">
            {lead.has_budget && <span className="text-[10px] bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full border border-green-500/30">Has Budget</span>}
            {systemTags.map((tagId, idx) => {
              const pt = PREDEFINED_TAGS.find(t => t.id === tagId);
              return pt ? <span key={`st-${idx}`} className={`text-[10px] px-2 py-0.5 rounded-full border cursor-default ${tagColorClass(pt.color)}`} title={pt.hint}>{pt.label}</span> : null;
            })}
            {lead.tags && lead.tags.map((tag, idx) => (
              <span key={idx} className={`text-[10px] px-2 py-0.5 rounded-full border cursor-default ${tagColorClass(tag.color)}`}>{tag.label}</span>
            ))}
          </div>

          {/* AI Analysis */}
          {lead.takeoff_timestamp ? (
            <div className="space-y-3 mt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Brain className="text-purple-400" size={18} />
                  <span className="text-sm font-semibold text-purple-300">Deep Scan Results</span>
                </div>
                <button onClick={handleCopyTakeoff} className="flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-3 py-1.5 rounded-lg transition-colors">
                  {copied ? <><CheckCircle size={13} className="text-green-400" /> Copied!</> : <><ClipboardCopy size={13} /> Copy for Notion</>}
                </button>
              </div>

              {lead.takeoff_snapshot && (
                <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4">
                  <div className="text-sm font-semibold text-purple-300 mb-2 flex items-center gap-1.5"><Brain size={16} className="text-purple-400" /> Project Snapshot</div>
                  {lead.takeoff_snapshot.scope_summary && <div className="text-sm text-slate-300 mb-3 leading-relaxed">{lead.takeoff_snapshot.scope_summary}</div>}
                  {(() => {
                    const pd = lead.takeoff_snapshot.project_details || {};
                    const fields = [
                      ['Project', pd.project_name], ['Address', pd.project_address || pd.project_location],
                      ['Type', pd.project_type], ['Building', pd.building_type || pd.occupancy_type],
                      ['Codes', Array.isArray(pd.applicable_codes) ? pd.applicable_codes.join(', ') : pd.applicable_codes],
                      ['Occupancy', pd.occupancy_classification],
                    ].filter(([, v]) => v);
                    return fields.length > 0 ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        {fields.map(([label, val]) => <div key={label}><span className="text-slate-500">{label}:</span> <span className="text-white">{val}</span></div>)}
                      </div>
                    ) : null;
                  })()}
                </div>
              )}

              {lead.takeoff_fa_briefing && (
                <div className="bg-red-900/15 border border-red-500/25 rounded-lg p-4">
                  <div className="text-sm font-semibold text-red-300 mb-2 flex items-center gap-1.5"><Shield size={16} className="text-red-400" /> Fire Alarm Briefing</div>
                  {(() => {
                    const fa = lead.takeoff_fa_briefing.fire_alarm_details || {};
                    const items = [
                      ['Panel Status', fa.panel_status || fa.existing_system], ['Sprinkler', fa.sprinkler_status],
                      ['Voice Evac', fa.voice_evac || fa.voice_required], ['CO Detection', fa.co_detection],
                    ].filter(([, v]) => v);
                    return items.length > 0 ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs mb-2">
                        {items.map(([label, val]) => <div key={label}><span className="text-slate-500">{label}:</span> <span className="text-white">{String(val)}</span></div>)}
                      </div>
                    ) : null;
                  })()}
                  {(() => {
                    const sp = lead.takeoff_fa_briefing.specifications || {};
                    const specItems = [
                      ['Control Panel', sp.CONTROL_PANEL], ['System Type', sp.SYSTEM_TYPE],
                      ['Wiring', sp.WIRING_CLASS], ['Monitoring', sp.MONITORING], ['Audio', sp.AUDIO_SYSTEM],
                      ['Approved Mfrs', Array.isArray(sp.APPROVED_MANUFACTURERS) ? sp.APPROVED_MANUFACTURERS.join(', ') : sp.APPROVED_MANUFACTURERS],
                    ].filter(([, v]) => v && v !== 'unknown' && String(v).toLowerCase() !== 'addressable');
                    return specItems.length > 0 ? (
                      <div className="mt-2 pt-2 border-t border-red-500/15">
                        <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Key Specs</div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
                          {specItems.map(([label, val]) => <div key={label}><span className="text-slate-500">{label}:</span> <span className="text-amber-200">{String(val)}</span></div>)}
                        </div>
                      </div>
                    ) : null;
                  })()}
                </div>
              )}

              {lead.takeoff_mechanical && Object.keys(lead.takeoff_mechanical).length > 0 && (
                <div className="bg-cyan-900/15 border border-cyan-500/25 rounded-lg p-4">
                  <div className="text-sm font-semibold text-cyan-300 mb-2 flex items-center gap-1.5"><Zap size={16} className="text-cyan-400" /> Mechanical Coordination</div>
                  {(() => {
                    const mech = lead.takeoff_mechanical;
                    const items = [
                      ['Duct Detectors/RTU', mech.duct_detectors_per_rtu || mech.duct_detectors],
                      ['Dampers', mech.dampers || mech.fire_smoke_dampers],
                      ['Access Doors', mech.access_control_doors || mech.access_doors],
                    ].filter(([, v]) => v);
                    return (
                      <>
                        {items.length > 0 && (
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mb-2">
                            {items.map(([label, val]) => <div key={label}><span className="text-slate-500">{label}:</span> <span className="text-white">{String(val)}</span></div>)}
                          </div>
                        )}
                        {Array.isArray(mech.equipment) && mech.equipment.length > 0 && (
                          <div className="space-y-1">
                            {mech.equipment.map((eq, idx) => (
                              <div key={idx} className="text-xs bg-slate-800/40 rounded p-2">
                                <span className="text-cyan-200">{eq.name || eq.type || `Unit ${idx + 1}`}</span>
                                {eq.cfm && <span className="text-slate-400 ml-1">({eq.cfm} CFM)</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}

              {lead.takeoff_fa_notes && lead.takeoff_fa_notes.length > 0 && (
                <div className="bg-amber-900/15 border border-amber-500/25 rounded-lg p-4">
                  <div className="text-sm font-semibold text-amber-300 mb-2 flex items-center gap-1.5"><FileText size={16} className="text-amber-400" /> Fire Alarm Notes</div>
                  <div className="space-y-1.5">
                    {lead.takeoff_fa_notes.map((note, idx) => (
                      <div key={idx} className="text-xs text-slate-300 leading-relaxed">
                        {note.page && <span className="text-amber-400/70 mr-1 font-medium">[p{note.page}]</span>}
                        {note.content || (typeof note === 'string' ? note : JSON.stringify(note))}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {((lead.takeoff_pitfalls && lead.takeoff_pitfalls.length > 0) || (lead.takeoff_estimating_notes && lead.takeoff_estimating_notes.length > 0)) && (
                <div className="bg-red-900/10 border border-red-500/20 rounded-lg p-4">
                  <div className="text-sm font-semibold text-red-300 mb-2 flex items-center gap-1.5"><AlertTriangle size={16} className="text-red-400" /> Conflicts, Pitfalls & Advice</div>
                  {(lead.takeoff_pitfalls || []).map((p, idx) => (
                    <div key={`p-${idx}`} className="text-xs text-red-200 flex items-start gap-1.5 leading-relaxed mb-1">
                      <span className="text-red-400 mt-0.5 shrink-0">•</span>
                      <span>{typeof p === 'string' ? p : p.content || JSON.stringify(p)}</span>
                    </div>
                  ))}
                  {(lead.takeoff_estimating_notes || []).map((n, idx) => (
                    <div key={`e-${idx}`} className="text-xs text-orange-200 flex items-start gap-1.5 leading-relaxed mb-1">
                      <span className="text-orange-400 mt-0.5 shrink-0">•</span>
                      <span>{typeof n === 'string' ? n : n.content || JSON.stringify(n)}</span>
                    </div>
                  ))}
                </div>
              )}

              {lead.takeoff_competitive_advantages && lead.takeoff_competitive_advantages.length > 0 && (
                <div className="bg-green-900/15 border border-green-500/25 rounded-lg p-4">
                  <div className="text-sm font-semibold text-green-300 mb-2 flex items-center gap-1.5"><CheckCircle2 size={16} className="text-green-400" /> Competitive Advantages</div>
                  <ul className="space-y-1.5">
                    {lead.takeoff_competitive_advantages.map((a, idx) => (
                      <li key={idx} className="text-xs text-green-200 flex items-start gap-1.5 leading-relaxed">
                        <span className="text-green-400 mt-0.5 shrink-0">•</span>
                        <span>{typeof a === 'string' ? a : a.content || JSON.stringify(a)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {lead.takeoff_project_tags && lead.takeoff_project_tags.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {lead.takeoff_project_tags.map((tag, idx) => (
                    <span key={idx} className={`text-xs px-2.5 py-1 rounded-full border ${tag.color || 'bg-slate-500/20 text-slate-300 border-slate-500/30'} cursor-default`}>{tag.label}</span>
                  ))}
                </div>
              )}

              <div className="text-xs text-slate-600 mt-1 flex justify-between">
                <span>Deep Scan: {new Date(lead.takeoff_timestamp).toLocaleDateString()}</span>
                {lead.knowledge_file_count && <span>Files: {lead.knowledge_file_count}</span>}
              </div>
            </div>
          ) : lead.knowledge_last_scanned ? (
            <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="text-purple-400" size={18} />
                <span className="text-sm font-semibold text-purple-300">AI Fire Alarm Analysis</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs mb-3">
                <div className="bg-slate-800/50 rounded p-2">
                  <span className="text-slate-500">System Type:</span>
                  <span className="ml-1 text-white capitalize">{lead.knowledge_system_type || 'Unknown'}</span>
                </div>
              </div>
              {lead.knowledge_required_vendors && lead.knowledge_required_vendors.length > 0 && (
                <div className="text-xs mb-2"><span className="text-slate-500">Required Vendors:</span><span className="ml-1 text-orange-300">{lead.knowledge_required_vendors.join(', ')}</span></div>
              )}
              {lead.knowledge_required_manufacturers && lead.knowledge_required_manufacturers.length > 0 && (
                <div className="text-xs mb-2"><span className="text-slate-500">Required Manufacturers:</span><span className="ml-1 text-amber-300">{lead.knowledge_required_manufacturers.join(', ')}</span></div>
              )}
              {lead.knowledge_required_codes && lead.knowledge_required_codes.length > 0 && (
                <div className="text-xs mb-2"><span className="text-slate-500">Code Requirements:</span><span className="ml-1 text-cyan-300">{lead.knowledge_required_codes.join(', ')}</span></div>
              )}
              {lead.knowledge_deal_breakers && lead.knowledge_deal_breakers.length > 0 && (
                <div className="text-xs mb-2"><span className="text-red-400">Deal Breakers:</span><span className="ml-1 text-red-300">{lead.knowledge_deal_breakers.join(', ')}</span></div>
              )}
              {lead.knowledge_evidence && (
                <div className="mt-3 pt-3 border-t border-purple-500/20">
                  <div className="text-xs text-slate-500 mb-2">Evidence (page + snippet)</div>
                  <div className="space-y-1 text-[11px]">
                    {Object.entries(lead.knowledge_evidence).map(([category, entries]) => {
                      if (!Array.isArray(entries) || entries.length === 0) return null;
                      return (
                        <div key={category} className="bg-slate-800/40 rounded p-2">
                          <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{category.replaceAll('_', ' ')}</div>
                          <ul className="space-y-1">
                            {entries.map((entry, idx) => (
                              <li key={idx} className="text-slate-300">
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
              {lead.knowledge_notes && (
                <div className="mt-3 pt-3 border-t border-purple-500/20">
                  <div className="text-xs text-slate-500 mb-1">Analysis Notes:</div>
                  <div className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-800/50 rounded p-2">{lead.knowledge_notes}</div>
                </div>
              )}
              {lead.knowledge_addendums && lead.knowledge_addendums.length > 0 && (
                <div className="mt-3 pt-3 border-t border-orange-500/20">
                  <div className="text-xs text-orange-400 font-semibold mb-2 flex items-center gap-1">
                    <AlertTriangle size={12} />Addendums / Revisions ({lead.knowledge_addendums.length})
                  </div>
                  <div className="space-y-1">
                    {lead.knowledge_addendums.map((add, idx) => (
                      <div key={idx} className="text-xs bg-orange-900/20 rounded p-2 flex justify-between items-center">
                        <span className="text-orange-200 truncate max-w-[250px]">{add.filename}</span>
                        {add.modified && <span className="text-[10px] text-orange-400/60">{new Date(add.modified).toLocaleDateString()}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-[10px] text-slate-600 mt-2 flex justify-between">
                <span>Scanned: {new Date(lead.knowledge_last_scanned).toLocaleDateString()}</span>
                {lead.knowledge_file_count && <span>Files: {lead.knowledge_file_count}</span>}
              </div>
            </div>
          ) : (
            <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 mt-4 text-center">
              <Brain className="text-slate-600 mx-auto mb-2" size={20} />
              <div className="text-xs text-slate-500">Not scanned by Knowledge Scanner yet</div>
              <div className="text-[10px] text-slate-600 mt-1">Run Knowledge Scan to see AI analysis</div>
            </div>
          )}
        </div>

        <button onClick={onClose} className="mt-6 w-full bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors">Close</button>
      </div>
    </div>
  );
}
