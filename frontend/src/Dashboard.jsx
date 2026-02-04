import React, { useState, useEffect } from 'react';
import { Download, Mail, ChevronLeft, ChevronRight, FileText, ExternalLink, Building2, User, MapPin, Calendar, AlertCircle, Plus, Pencil, Trash2, X, Settings, FileText as Description } from 'lucide-react';

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

  // Initial load
  // Dynamic API Base URL to allow access from other devices
  const API_BASE = `http://${window.location.hostname}:8000`;

  useEffect(() => {
    fetchLeads();
  }, []);

  const fetchLeads = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/leads`);
      const data = await res.json();
      setLeads(data.leads || []);
    } catch (e) {
      console.error("Failed to fetch leads", e);
    }
    setLoading(false);
  };

  const triggerScan = async (e) => {
    if (e) e.preventDefault();
    console.log("🖱️ Triggering Scan (POST)...");
    setSyncing(true);
    try {
      // Trigger background sync
      const res = await fetch(`${API_BASE}/sync-leads`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      console.log("✅ Scan Trigger Response:", res.status);

      // Start polling for results
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        console.log(`⏳ Polling ${elapsed / 1000}s...`);

        // Stop polling after 3 minutes (180000ms)
        if (elapsed >= 180000) {
          clearInterval(pollInterval);
          setSyncing(false);
        }
      }, 5000);

    } catch (e) {
      console.error("Agent trigger failed", e);
      setSyncing(false);
    }
  };

  const clearAllLeads = async () => {
    if (!window.confirm('Are you sure you want to clear ALL leads? This will create a backup first.')) {
      return;
    }

    setClearing(true);
    try {
      const res = await fetch(`${API_BASE}/clear-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      console.log(`✅ Cleared ${data.count} leads`);

      // Refresh the display
      await fetchLeads();
      alert(`Successfully cleared ${data.count} leads (backup created)`);
    } catch (e) {
      console.error("Failed to clear leads", e);
      alert("Failed to clear leads. Check console for details.");
    }
    setClearing(false);
  };

  const refreshAllLeads = async () => {
    if (!window.confirm('Clear all existing leads and start a fresh scan?')) {
      return;
    }

    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/refresh-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      console.log(`✅ Cleared ${data.cleared_count} leads, starting fresh scan`);

      // Clear UI immediately
      setLeads([]);

      // Start polling for new results
      let elapsed = 0;
      const pollInterval = setInterval(() => {
        fetchLeads();
        elapsed += 5000;
        console.log(`⏳ Polling for fresh data ${elapsed / 1000}s...`);

        if (elapsed >= 180000) {
          clearInterval(pollInterval);
          setRefreshing(false);
        }
      }, 5000);

      alert(`Cleared ${data.cleared_count} leads. Fresh scan started!`);
    } catch (e) {
      console.error("Failed to refresh leads", e);
      alert("Failed to refresh. Check console for details.");
      setRefreshing(false);
    }
  };

  const deduplicateLeads = async () => {
    if (!window.confirm('Remove duplicate leads by merging their information?')) {
      return;
    }

    setDeduplicating(true);
    try {
      const res = await fetch(`${API_BASE}/deduplicate-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      console.log(`✅ Removed ${data.removed_count} duplicates`);

      // Refresh the display
      await fetchLeads();
      alert(`Removed ${data.removed_count} duplicate leads!\nBefore: ${data.original_count} | After: ${data.deduplicated_count}`);
    } catch (e) {
      console.error("Failed to deduplicate leads", e);
      alert("Failed to deduplicate. Check console for details.");
    }
    setDeduplicating(false);
  };

  // Add new lead
  const addLead = async () => {
    try {
      const res = await fetch(`${API_BASE}/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        await fetchLeads();
        setAddModal(false);
        setFormData(emptyForm);
      } else {
        alert('Failed to add lead');
      }
    } catch (e) {
      console.error("Failed to add lead", e);
      alert("Failed to add lead. Check console for details.");
    }
  };

  // Update existing lead
  const updateLead = async () => {
    try {
      const res = await fetch(`${API_BASE}/leads/${editModal.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        await fetchLeads();
        setEditModal(null);
        setFormData(emptyForm);
      } else {
        alert('Failed to update lead');
      }
    } catch (e) {
      console.error("Failed to update lead", e);
      alert("Failed to update lead. Check console for details.");
    }
  };

  // Delete lead
  const deleteLead = async (lead) => {
    if (!window.confirm(`Delete "${lead.name}"?`)) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/leads/${lead.id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        await fetchLeads();
      } else {
        alert('Failed to delete lead');
      }
    } catch (e) {
      console.error("Failed to delete lead", e);
      alert("Failed to delete lead. Check console for details.");
    }
  };

  // Open edit modal
  const openEditModal = (lead) => {
    setFormData({
      name: lead.name || '',
      company: lead.company || '',
      gc: lead.gc || '',
      contact_name: lead.contact_name || '',
      contact_email: lead.contact_email || '',
      contact_phone: lead.contact_phone || '',
      location: lead.location || '',
      full_address: lead.full_address || '',
      bid_date: lead.bid_date || '',
      description: lead.description || '',
      files_link: lead.files_link || '',
      download_link: lead.download_link || '',
      site: lead.site || 'Manual Entry',
      sprinklered: lead.sprinklered || false,
      has_budget: lead.has_budget || false
    });
    setEditModal(lead);
  };

  // Open add modal
  const openAddModal = () => {
    setFormData(emptyForm);
    setAddModal(true);
  };

  // Helper to check if project is expired
  const isExpired = (bidDate) => {
    if (!bidDate || bidDate === 'N/A' || bidDate === 'TBD') return false;
    try {
      const date = new Date(bidDate);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return date < today;
    } catch {
      return false;
    }
  };

  // Filter groups
  const bcLeads = leads.filter(l => l.site?.toLowerCase().includes("building"));
  const phLeads = leads.filter(l => l.site?.toLowerCase().includes("planhub"));

  const LeadTable = ({ title, data }) => {
    const [currentPage, setCurrentPage] = useState(1);
    const itemsPerPage = 10;
    const totalPages = Math.ceil(data.length / itemsPerPage);

    // Reset to page 1 when data changes (e.g. filter or refresh)
    useEffect(() => {
      setCurrentPage(1);
    }, [data.length]);

    const paginatedData = data.slice(
      (currentPage - 1) * itemsPerPage,
      currentPage * itemsPerPage
    );

    const handlePageChange = (newPage) => {
      if (newPage >= 1 && newPage <= totalPages) {
        setCurrentPage(newPage);
      }
    };

    return (
      <div className="mb-8 bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50 backdrop-blur">
          <h2 className="text-lg font-bold text-white flex items-center gap-3">
            {title}
            <span className="bg-slate-800 text-slate-400 text-xs px-2 py-1 rounded-full">{data.length}</span>
          </h2>

          {/* Pagination Controls (Top) */}
          {totalPages > 1 && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>Page {currentPage} of {totalPages}</span>
              <div className="flex gap-1">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="overflow-x-auto flex-grow">
          <table className="w-full text-left text-xs text-slate-400">
            <thead className="bg-slate-950/50 text-xs uppercase font-semibold text-slate-500 sticky top-0">
              <tr>
                <th className="px-4 py-3">Project</th>
                <th className="px-4 py-3">Company / GC</th>
                <th className="px-4 py-3">Contact</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3 w-24">Bid Date</th>
                <th className="px-4 py-3 text-center w-20">Links</th>
                <th className="px-4 py-3 text-center w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {paginatedData.map((lead, i) => {
                const expired = isExpired(lead.bid_date);
                return (
                  <tr key={lead.id || i} className={`hover:bg-slate-800/30 transition group ${expired ? 'opacity-40' : ''}`}>

                    {/* Project Name - Click for Description */}
                    <td className="px-4 py-2 font-medium text-slate-200 group-hover:text-orange-400 transition-colors max-w-xs">
                      <button
                        onClick={() => setDescriptionPopup(lead)}
                        className="text-left hover:text-orange-400 transition-colors"
                        title="Click for description"
                      >
                        <div className="truncate max-w-[200px]">{lead.name}</div>
                      </button>
                      <div className="flex items-center gap-2 mt-0.5">
                        {expired && <span className="text-[10px] bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded">EXPIRED</span>}
                        {lead.has_budget && <span className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30">BUDGET</span>}
                        {lead.sprinklered && <span className="text-[10px] bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded border border-red-500/20">SPRINKLERED</span>}
                        <span className="text-[10px] text-slate-600">{lead.site}</span>
                      </div>
                    </td>

                    {/* Company & GC - Clickable */}
                    <td className="px-4 py-2">
                      <button
                        onClick={() => setCompanyPopup(lead)}
                        className="flex flex-col text-left hover:bg-slate-800/50 p-1 rounded transition-colors w-full"
                        title="Click for details"
                      >
                        <span className="text-slate-300 truncate max-w-[150px] hover:text-orange-400 transition-colors" title={lead.company}>{lead.company !== "N/A" ? lead.company : <span className="text-slate-600 italic">No Company</span>}</span>
                        <span className="text-[10px] text-slate-500 truncate max-w-[150px]" title={lead.gc}>{lead.gc !== "N/A" ? `GC: ${lead.gc}` : ""}</span>
                      </button>
                    </td>

                    {/* Contact Info */}
                    <td className="px-4 py-2">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-slate-300 truncate max-w-[150px]">{lead.contact_name !== "N/A" ? lead.contact_name : <span className="text-slate-600 italic">-</span>}</span>
                        {lead.contact_email && (
                          <a href={`mailto:${lead.contact_email}`} className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-orange-400 transition-colors">
                            <Mail size={10} />
                            <span className="truncate max-w-[140px]">{lead.contact_email}</span>
                          </a>
                        )}
                      </div>
                    </td>

                    {/* Location */}
                    <td className="px-4 py-2 text-slate-400 truncate max-w-[120px]" title={lead.location}>
                      {lead.location || "N/A"}
                    </td>

                    {/* Bid Date */}
                    <td className={`px-4 py-2 font-mono whitespace-nowrap ${expired ? 'text-red-400 line-through' : 'text-slate-300'}`}>
                      {lead.bid_date}
                    </td>

                    {/* Links Column */}
                    <td className="px-4 py-2 text-center">
                      <div className="flex justify-center gap-1">
                        {/* Local downloaded file (highest priority) */}
                        {lead.local_file_path && (
                          <a
                            href={`${API_BASE}${lead.local_file_path}`}
                            download
                            className="p-1.5 bg-green-600 hover:bg-green-500 text-white rounded transition-colors"
                            title="Download Local File"
                          >
                            <Download size={12} />
                          </a>
                        )}
                        {/* Direct download link */}
                        {lead.download_link && (
                          <a
                            href={lead.download_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
                            title="Direct Download"
                          >
                            <Download size={12} />
                          </a>
                        )}
                        {/* Files/external link */}
                        {lead.files_link && (
                          <a
                            href={lead.files_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 bg-orange-600 hover:bg-orange-500 text-white rounded transition-colors"
                            title="View Files"
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                        {/* Project URL */}
                        {lead.url && lead.url !== 'N/A' && (
                          <a
                            href={lead.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                            title="View Project Page"
                          >
                            <FileText size={12} />
                          </a>
                        )}
                        {/* No links indicator */}
                        {!lead.local_file_path && !lead.download_link && !lead.files_link && !lead.url && (
                          <span className="text-slate-600 text-[10px]">-</span>
                        )}
                      </div>
                    </td>

                    {/* Actions Column */}
                    <td className="px-4 py-2 text-center">
                      <div className="flex justify-center gap-1">
                        <button
                          onClick={() => openEditModal(lead)}
                          className="p-1.5 bg-slate-700 hover:bg-blue-600 text-slate-400 hover:text-white rounded transition-colors"
                          title="Edit"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          onClick={() => deleteLead(lead)}
                          className="p-1.5 bg-slate-700 hover:bg-red-600 text-slate-400 hover:text-white rounded transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {data.length === 0 && (
                <tr>
                  <td colSpan="7" className="px-6 py-12 text-center text-slate-600 italic">
                    No active leads found in this category.
                  </td>
                </tr>
              )}

              {/* Empty rows filler to maintain height if needed, OR just leave as is */}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls (Bottom) */}
        {totalPages > 1 && (
          <div className="p-3 border-t border-slate-800 bg-slate-900/50 flex justify-between items-center text-xs text-slate-400">
            <span>Showing {paginatedData.length} of {data.length} leads</span>
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
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8 font-sans">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-end mb-12 border-b border-slate-800/50 pb-8">
          <div>
            <h1 className="text-5xl font-black tracking-tighter text-white mb-2">
              PLANROOM<span className="text-orange-500">GENIUS v2.0</span>
            </h1>
            <p className="text-slate-500 text-lg">AI-Powered Construction Lead Intelligence</p>
          </div>
          <div className="flex gap-2 items-center">
            {/* Add Lead Button */}
            <button
              onClick={openAddModal}
              className="px-3 py-2 rounded-lg bg-green-600 text-white text-sm font-semibold hover:bg-green-500 transition flex items-center gap-1.5"
            >
              <Plus size={16} />
              Add Lead
            </button>

            {/* Refresh View */}
            <button
              onClick={fetchLeads}
              disabled={loading}
              className="px-3 py-2 rounded-lg bg-slate-800 text-slate-400 text-sm font-semibold hover:bg-slate-700 transition"
            >
              {loading ? '...' : 'Refresh'}
            </button>

            {/* Scan Button */}
            <button
              onClick={triggerScan}
              disabled={syncing}
              className={`bg-red-600 hover:bg-red-500 text-white font-bold py-2 px-5 rounded-lg transition-all shadow-lg shadow-red-900/20 flex items-center gap-2 text-sm ${syncing ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {syncing ? (
                <>
                  <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Scanning...
                </>
              ) : "Scan"}
            </button>

            {/* Utility Menu (dropdown) */}
            <div className="relative">
              <button
                onClick={() => setShowUtilityMenu(!showUtilityMenu)}
                className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300 transition"
                title="More options"
              >
                <Settings size={18} />
              </button>

              {showUtilityMenu && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setShowUtilityMenu(false)}
                  />
                  <div className="absolute right-0 mt-2 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
                    <button
                      onClick={() => { deduplicateLeads(); setShowUtilityMenu(false); }}
                      disabled={deduplicating}
                      className="w-full px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700 transition flex items-center gap-2 disabled:opacity-50"
                    >
                      {deduplicating ? 'Cleaning...' : 'Remove Duplicates'}
                    </button>
                    <button
                      onClick={() => { refreshAllLeads(); setShowUtilityMenu(false); }}
                      disabled={refreshing}
                      className="w-full px-4 py-2.5 text-left text-sm text-purple-300 hover:bg-slate-700 transition flex items-center gap-2 disabled:opacity-50"
                    >
                      {refreshing ? 'Refreshing...' : 'Clear & Rescan'}
                    </button>
                    <button
                      onClick={() => { clearAllLeads(); setShowUtilityMenu(false); }}
                      disabled={clearing}
                      className="w-full px-4 py-2.5 text-left text-sm text-yellow-300 hover:bg-slate-700 transition flex items-center gap-2 disabled:opacity-50"
                    >
                      {clearing ? 'Clearing...' : 'Clear All Leads'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Main Aggregated Table */}
        <LeadTable title="🔥 All Active Opportunities" data={leads} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* BuildingConnected Table */}
          <LeadTable title="BuildingConnected" data={bcLeads} />

          {/* PlanHub Table */}
          <LeadTable title="PlanHub" data={phLeads} />
        </div>

        {/* Company Popup Modal */}
        {companyPopup && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setCompanyPopup(null)}
          >
            <div
              className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-8 max-w-md w-full mx-4 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-2xl font-bold text-white flex items-center gap-2">
                  <Building2 className="text-orange-500" size={24} />
                  Company Details
                </h3>
                <button
                  onClick={() => setCompanyPopup(null)}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                {/* Company Name */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Company</div>
                  <div className="text-lg font-semibold text-white">
                    {companyPopup.company !== "N/A" ? companyPopup.company : <span className="text-slate-600 italic">No Company</span>}
                  </div>
                  {companyPopup.gc && companyPopup.gc !== "N/A" && (
                    <div className="text-sm text-slate-400 mt-1">GC: {companyPopup.gc}</div>
                  )}
                </div>

                {/* Contact Name */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                    <User size={12} />
                    Contact Name
                  </div>
                  <div className="text-lg font-medium text-white">
                    {companyPopup.contact_name !== "N/A" ? companyPopup.contact_name : <span className="text-slate-600 italic">No Contact</span>}
                  </div>
                </div>

                {/* Email */}
                {companyPopup.contact_email && (
                  <div className="bg-slate-800/50 rounded-lg p-4">
                    <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                      <Mail size={12} />
                      Email
                    </div>
                    <a
                      href={`mailto:${companyPopup.contact_email}`}
                      className="text-lg text-orange-400 hover:text-orange-300 transition-colors break-all"
                    >
                      {companyPopup.contact_email}
                    </a>
                  </div>
                )}

                {/* Additional Info */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Project Info</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2 text-slate-300">
                      <MapPin size={14} className="text-slate-500" />
                      {companyPopup.location || "N/A"}
                    </div>
                    <div className="flex items-center gap-2 text-slate-300">
                      <Calendar size={14} className="text-slate-500" />
                      Bid Date: {companyPopup.bid_date || "N/A"}
                    </div>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setCompanyPopup(null)}
                className="mt-6 w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* Description Popup Modal */}
        {descriptionPopup && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setDescriptionPopup(null)}
          >
            <div
              className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-8 max-w-lg w-full mx-4 shadow-2xl max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-2xl font-bold text-white flex items-center gap-2">
                  <Description className="text-orange-500" size={24} />
                  Project Details
                </h3>
                <button
                  onClick={() => setDescriptionPopup(null)}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="space-y-4">
                {/* Project Name */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Project Name</div>
                  <div className="text-lg font-semibold text-white">{descriptionPopup.name || 'N/A'}</div>
                </div>

                {/* Description / Full Address */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Description / Full Address</div>
                  <div className="text-slate-300 whitespace-pre-wrap">
                    {descriptionPopup.description || descriptionPopup.full_address || 'No description available'}
                  </div>
                </div>

                {/* Location */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                    <MapPin size={12} />
                    Location
                  </div>
                  <div className="text-slate-300">{descriptionPopup.location || 'N/A'}</div>
                </div>

                {/* Source */}
                <div className="bg-slate-800/50 rounded-lg p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Source</div>
                  <div className="text-slate-300">{descriptionPopup.site || descriptionPopup.source || 'N/A'}</div>
                </div>

                {/* Flags */}
                <div className="flex gap-2 flex-wrap">
                  {descriptionPopup.sprinklered && (
                    <span className="text-xs bg-red-500/20 text-red-400 px-3 py-1 rounded-full border border-red-500/30">
                      Sprinklered
                    </span>
                  )}
                  {descriptionPopup.has_budget && (
                    <span className="text-xs bg-green-500/20 text-green-400 px-3 py-1 rounded-full border border-green-500/30">
                      Has Budget
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={() => setDescriptionPopup(null)}
                className="mt-6 w-full bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* Add/Edit Lead Modal */}
        {(addModal || editModal) && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }}
          >
            <div
              className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-6 max-w-2xl w-full mx-4 shadow-2xl max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  {editModal ? (
                    <>
                      <Pencil className="text-blue-500" size={20} />
                      Edit Lead
                    </>
                  ) : (
                    <>
                      <Plus className="text-green-500" size={20} />
                      Add New Lead
                    </>
                  )}
                </h3>
                <button
                  onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* Project Name */}
                <div className="col-span-2">
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Project Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="Enter project name"
                  />
                </div>

                {/* Company */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Company</label>
                  <input
                    type="text"
                    value={formData.company}
                    onChange={(e) => setFormData({...formData, company: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="Company name"
                  />
                </div>

                {/* GC */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">General Contractor</label>
                  <input
                    type="text"
                    value={formData.gc}
                    onChange={(e) => setFormData({...formData, gc: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="GC name"
                  />
                </div>

                {/* Contact Name */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Name</label>
                  <input
                    type="text"
                    value={formData.contact_name}
                    onChange={(e) => setFormData({...formData, contact_name: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="Contact person"
                  />
                </div>

                {/* Contact Email */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Email</label>
                  <input
                    type="email"
                    value={formData.contact_email}
                    onChange={(e) => setFormData({...formData, contact_email: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="email@example.com"
                  />
                </div>

                {/* Contact Phone */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Contact Phone</label>
                  <input
                    type="tel"
                    value={formData.contact_phone}
                    onChange={(e) => setFormData({...formData, contact_phone: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="(555) 123-4567"
                  />
                </div>

                {/* Bid Date */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Bid Date</label>
                  <input
                    type="text"
                    value={formData.bid_date}
                    onChange={(e) => setFormData({...formData, bid_date: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="MM/DD/YYYY or TBD"
                  />
                </div>

                {/* Location */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Location</label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => setFormData({...formData, location: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="City, State"
                  />
                </div>

                {/* Full Address */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Full Address</label>
                  <input
                    type="text"
                    value={formData.full_address}
                    onChange={(e) => setFormData({...formData, full_address: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="123 Main St, City, State ZIP"
                  />
                </div>

                {/* Description */}
                <div className="col-span-2">
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({...formData, description: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none h-20 resize-none"
                    placeholder="Project description..."
                  />
                </div>

                {/* Files Link */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Files Link</label>
                  <input
                    type="url"
                    value={formData.files_link}
                    onChange={(e) => setFormData({...formData, files_link: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="https://..."
                  />
                </div>

                {/* Download Link */}
                <div>
                  <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">Download Link</label>
                  <input
                    type="url"
                    value={formData.download_link}
                    onChange={(e) => setFormData({...formData, download_link: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                    placeholder="https://..."
                  />
                </div>

                {/* Flags */}
                <div className="col-span-2 flex gap-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.sprinklered}
                      onChange={(e) => setFormData({...formData, sprinklered: e.target.checked})}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500"
                    />
                    <span className="text-sm text-slate-300">Sprinklered</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.has_budget}
                      onChange={(e) => setFormData({...formData, has_budget: e.target.checked})}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500"
                    />
                    <span className="text-sm text-slate-300">Has Budget</span>
                  </label>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => { setAddModal(false); setEditModal(null); setFormData(emptyForm); }}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={editModal ? updateLead : addLead}
                  disabled={!formData.name}
                  className="flex-1 bg-orange-600 hover:bg-orange-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold py-3 rounded-lg transition-colors"
                >
                  {editModal ? 'Update Lead' : 'Add Lead'}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
