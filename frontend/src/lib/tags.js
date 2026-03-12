export const PREDEFINED_TAGS = [
  // ── SCOPE ──────────────────────────────────────────────────────────────────
  { id: 'NEW SYSTEM',    label: 'NEW SYSTEM',    color: 'green',    hint: 'New fire alarm system installation',                              group: 'scope' },
  { id: 'MODIFY',        label: 'MODIFY',        color: 'yellow',   hint: 'Existing system to remain / modify',                             group: 'scope' },
  { id: 'NO FA',         label: 'NO FA',         color: 'red',      hint: 'No fire alarm scope in this project',                            group: 'scope' },
  { id: 'VOICE',         label: 'VOICE',         color: 'yellow',   hint: 'Voice evacuation / mass notification required',                  group: 'scope' },
  { id: 'BDA ERRC',      label: 'BDA ERRC',      color: 'orange',   hint: 'BDA / ERRC system required',                                     group: 'scope' },
  { id: 'NO SPRNK',      label: 'NO SPRNK',      color: 'red',      hint: 'No sprinkler per code definitions page',                         group: 'scope' },
  { id: 'NETWORK',       label: 'NETWORK',       color: 'yellow',   hint: 'System to be connected to a network',                            group: 'scope' },
  { id: 'COMP MFG',      label: 'COMP MFG',      color: 'green',    hint: 'Compatible manufacturer on file (Gamewell-FCI / FireLite / SK)', group: 'scope' },
  { id: 'INCOMPAT MFG',  label: 'INCOMPAT MFG',  color: 'glow-red', hint: 'Incompatible manufacturer — existing system we cannot service',   group: 'scope' },
  { id: 'REQ MFR',       label: 'REQ MFR',       color: 'red',      hint: 'Required manufacturer specified in specs',                       group: 'scope' },
  { id: 'REQ VENDOR',    label: 'REQ VENDOR',    color: 'glow-red', hint: 'Required vendor / sole-source specified in specs',               group: 'scope' },
  // ── FLAGS ──────────────────────────────────────────────────────────────────
  { id: 'DEAL BREAKER',  label: 'DEAL BREAKER',  color: 'red',      hint: 'Deal breaker — review before bidding',                           group: 'flags' },
  { id: 'DISCREPENCY',   label: 'DISCREPENCY',   color: 'red',      hint: 'Plan discrepancy found — needs clarification',                   group: 'flags' },
  { id: 'HIGH LABOR',    label: 'HIGH LABOR',    color: 'red',      hint: 'High labor content / difficult install',                         group: 'flags' },
  { id: 'NEED DOCS',     label: 'NEED DOCS',     color: 'red',      hint: 'Waiting for plans or bid documents',                             group: 'flags' },
  { id: 'BABA',          label: 'BABA',          color: 'orange',   hint: 'Buy American Build American required',                           group: 'flags' },
  { id: 'DAVIS BACON',   label: 'DAVIS BACON',   color: 'orange',   hint: 'Prevailing wage / Davis-Bacon required',                         group: 'flags' },
  { id: 'BID BOND',      label: 'BID BOND',      color: 'orange',   hint: 'Bid bond required',                                              group: 'flags' },
  { id: 'NICET',         label: 'NICET',         color: 'orange',   hint: 'NICET certification required',                                   group: 'flags' },
  { id: 'TAX EXEMPT',    label: 'TAX EXEMPT',    color: 'yellow',   hint: 'Tax exempt project',                                             group: 'flags' },
  { id: 'PHASED',        label: 'PHASED',        color: 'yellow',   hint: 'Phased construction schedule',                                   group: 'flags' },
  { id: 'DESIGN BUILD',  label: 'DESIGN BUILD',  color: 'yellow',   hint: 'Design-build / delegated design delivery',                       group: 'flags' },
  // ── CONSTRUCTION TYPE ──────────────────────────────────────────────────────
  { id: 'NEW CONST',     label: 'NEW CONST',     color: 'green',    hint: 'New construction build',                                         group: 'construction' },
  { id: 'TI',            label: 'TI',            color: 'yellow',   hint: 'Tenant improvement / renovation',                                group: 'construction' },
  { id: 'REMODEL',       label: 'REMODEL',       color: 'yellow',   hint: 'Remodel or renovation of existing space',                        group: 'construction' },
  { id: 'NEW PANEL',     label: 'NEW PANEL',     color: 'orange',   hint: 'New fire panel only — parts & smarts',                           group: 'construction' },
  // ── PROJECT TYPE ──────────────────────────────────────────────────────────
  { id: 'INSTALL',       label: 'INSTALL',       color: 'green',    hint: 'Full labor & material installation',                             group: 'projtype' },
  { id: 'PARTS SMARTS',  label: 'PARTS & SMARTS',color: 'yellow',   hint: 'Parts & smarts — supply only, no install labor',                group: 'projtype' },
  // ── BUILDING TYPE ─────────────────────────────────────────────────────────
  { id: 'WAREHOUSE',     label: 'WAREHOUSE',     color: 'location', hint: 'Warehouse / distribution facility',                              group: 'location' },
  { id: 'INDUSTRIAL',    label: 'INDUSTRIAL',    color: 'location', hint: 'Industrial / manufacturing facility',                            group: 'location' },
  { id: 'EDUCATION',     label: 'EDUCATION',     color: 'location', hint: 'School / university / educational facility',                     group: 'location' },
  { id: 'HOTEL',         label: 'HOTEL',         color: 'location', hint: 'Hotel / hospitality',                                            group: 'location' },
  { id: 'APARTMENTS',    label: 'APARTMENTS',    color: 'location', hint: 'Residential apartments / multi-family',                          group: 'location' },
  { id: 'ASST LIVING',   label: 'ASST LIVING',   color: 'location', hint: 'Assisted living / senior care facility',                         group: 'location' },
  { id: 'HOSPITAL',      label: 'HOSPITAL',      color: 'location', hint: 'Hospital / medical center',                                      group: 'location' },
  { id: 'CLINIC',        label: 'CLINIC',        color: 'location', hint: 'Medical or dental clinic',                                       group: 'location' },
  { id: 'OFFICE',        label: 'OFFICE',        color: 'location', hint: 'Office building',                                                group: 'location' },
  { id: 'RETAIL',        label: 'RETAIL',        color: 'location', hint: 'Retail store / shopping center',                                 group: 'location' },
  { id: 'GOVT',          label: 'GOVT',          color: 'location', hint: 'Government / municipal / public building',                       group: 'location' },
  { id: 'CHURCH',        label: 'CHURCH',        color: 'location', hint: 'Church / religious facility',                                    group: 'location' },
  // ── WORKFLOW ──────────────────────────────────────────────────────────────
  { id: 'QUOTING',       label: 'QUOTING',       color: 'green',    hint: 'Currently being priced / quoted',                                group: 'workflow' },
  { id: 'FOLLOW UP',     label: 'FOLLOW UP',     color: 'yellow',   hint: 'Needs follow-up with GC or owner',                               group: 'workflow' },
  { id: 'PASS',          label: 'PASS',          color: 'red',      hint: 'Decided to pass — not bidding',                                  group: 'workflow' },
];

export const tagColorClass = (color) => {
  if (color === 'red')      return 'bg-red-500/10 text-red-400 border-red-500/20';
  if (color === 'green')    return 'bg-green-500/10 text-green-400 border-green-500/20';
  if (color === 'orange')   return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
  if (color === 'yellow')   return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
  if (color === 'location') return 'bg-sky-500/10 text-sky-400 border-sky-500/20';
  if (color === 'glow-red') return 'bg-red-500/15 text-red-400 border-red-500/50 shadow-[0_0_6px_2px_rgba(239,68,68,0.35)]';
  return 'bg-slate-700/50 text-slate-300 border-slate-600';
};

export const badgeColor = (badge) => {
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

export const normalizeBadge = (badge) => {
  const b = badge.toUpperCase().trim();
  if (b === 'MOD' || b === 'MODIFICATION' || b === 'EXISTING' || b === 'EXISTING SYSTEM') return 'MODIFY';
  if (b === 'NEW SYSTEM' || b === 'NEW FA' || b === 'NEW FIRE ALARM') return 'NEW SYSTEM';
  if (b === 'NO SPRINK' || b === 'NON-SPRINKLED' || b === 'NO SPRNK' || b === 'NOT SPRINKLERED') return 'NO SPRNK';
  if (b === 'COMPAT MFR' || b === 'COMPATIBLE MFR' || b === 'COMP MFG') return 'COMP MFG';
  if (b === 'INCOMPAT MFR' || b === 'INCOMPATIBLE MFR' || b === 'INCOMPAT MFG') return 'INCOMPAT MFG';
  if (b === 'REQ MFR' || b === 'REQUIRED MFR' || b === 'REQUIRED MANUFACTURER') return 'REQ MFR';
  if (b === 'REQ VENDOR' || b === 'REQUIRED VENDOR' || b === 'SOLE SOURCE') return 'REQ VENDOR';
  if (b === 'BDA' || b === 'ERRC' || b === 'BDA/ERRC') return 'BDA ERRC';
  if (b === 'INCOMPAT MFR' || b === 'INCOMPATIBLE MFR' || b === 'MONITORING' || b === 'ACCESS CTRL') return null;
  if (b === 'DEAL-BREAKER' || b === 'DEALBREAKER') return 'DEAL BREAKER';
  if (b === 'DESIGN-BUILD' || b === 'DELEGATED DESIGN') return 'DESIGN BUILD';
  if (b === 'PREVAILING WAGE' || b === 'DAVIS-BACON') return 'DAVIS BACON';
  if (b === 'NEW CONSTRUCTION' || b === 'GROUND UP' || b === 'NEW BUILD') return 'NEW CONST';
  if (b === 'TENANT IMPROVEMENT' || b === 'TENANT IMPROVEMENTS' || b === 'T.I.' || b === 'T.I') return 'TI';
  if (b === 'RENOVATION' || b === 'RENO') return 'REMODEL';
  if (b === 'NEW FIRE PANEL' || b === 'PANEL REPLACEMENT' || b === 'PANEL ONLY') return 'NEW PANEL';
  const valid = PREDEFINED_TAGS.find(t => t.id === b);
  return valid ? valid.id : null;
};

export const mapRiskFlagToTag = (flag) => {
  const f = flag.toLowerCase();
  if (/davis.?bacon|prevailing.?wage/.test(f)) return 'DAVIS BACON';
  if (/buy.?american|baba\b|build.?america|\bais\b/.test(f)) return 'BABA';
  if (/\bbda\b|\berrc\b/.test(f)) return 'BDA ERRC';
  if (/nicet/.test(f)) return 'NICET';
  if (/bid.?bond/.test(f)) return 'BID BOND';
  if (/tax.?exempt/.test(f)) return 'TAX EXEMPT';
  if (/design.?build|delegated.?design/.test(f)) return 'DESIGN BUILD';
  if (/discrepan/.test(f)) return 'DISCREPENCY';
  if (/high.?labor/.test(f)) return 'HIGH LABOR';
  if (/phased/.test(f)) return 'PHASED';
  if (/voice.?evac/.test(f)) return 'VOICE';
  if (/\bnetwork\b/.test(f)) return 'NETWORK';
  if (/no.?fa\b|no fire alarm/.test(f)) return 'NO FA';
  if (/sole.?source|required.?vendor/.test(f)) return 'REQ VENDOR';
  if (/required.?mfr|required.?manufacturer|sole.?brand/.test(f)) return 'REQ MFR';
  if (/new.?const|ground.?up|new.?build/.test(f)) return 'NEW CONST';
  if (/tenant.?improv|\bT\.?I\b/.test(f)) return 'TI';
  if (/remodel|renovati/.test(f)) return 'REMODEL';
  if (/need.?doc|missing.?plan|no.?plan/.test(f)) return 'NEED DOCS';
  return null;
};

export const getSystemTags = (lead) => {
  const seen = new Set();
  const add = (id) => { if (id && PREDEFINED_TAGS.some(t => t.id === id)) seen.add(id); };
  (lead.knowledge_badges || []).forEach(b => add(normalizeBadge(b)));
  (lead.knowledge_bid_risk_flags || []).forEach(f => add(mapRiskFlagToTag(f)));
  return [...seen];
};

export const getTagHoverText = (tagId, lead) => {
  const mfrs = lead?.knowledge_required_manufacturers;
  const vendors = lead?.knowledge_required_vendors;
  const mfrList = mfrs?.length ? mfrs.join(', ') : null;
  const vendorList = vendors?.length ? vendors.join(', ') : null;
  if (tagId === 'REQ MFR')      return mfrList ? `Required manufacturer: ${mfrList}` : 'Manufacturer specified in specs';
  if (tagId === 'COMP MFG')     return mfrList ? `Compatible: ${mfrList}` : 'Compatible manufacturer on file';
  if (tagId === 'INCOMPAT MFG') return mfrList ? `NOT compatible: ${mfrList}` : 'Incompatible manufacturer — cannot service';
  if (tagId === 'REQ VENDOR')   return vendorList ? `Required vendor: ${vendorList}` : 'Sole-source vendor specified in specs';
  if (tagId === 'DEAL BREAKER') {
    const reasons = lead?.knowledge_deal_breakers;
    return reasons?.length ? reasons.join(' · ') : 'Deal breaker identified — review details';
  }
  const pt = PREDEFINED_TAGS.find(t => t.id === tagId);
  return pt?.hint || tagId;
};
