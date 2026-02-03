import React, { useState, useEffect } from 'react';

const LeadCard = ({ lead }) => (
  <div className="p-4 border-l-4 border-blue-500 bg-white shadow-sm rounded-r-lg mb-4">
    <div className="flex justify-between items-start">
      <h3 className="font-bold text-lg text-slate-800">{lead.projectName}</h3>
      <span className="text-xs font-semibold bg-blue-100 text-blue-700 px-2 py-1 rounded">
        Bid Date: {lead.bidDate}
      </span>
    </div>
    <p className="text-sm text-slate-600 mt-1">GC: {lead.generalContractor}</p>
    <div className="mt-3 flex gap-2">
      {lead.isSprinklered && <span className="text-[10px] bg-green-100 text-green-700 p-1 rounded">Sprinklered</span>}
      <span className="text-[10px] bg-gray-100 text-gray-700 p-1 rounded">Low Voltage DC</span>
    </div>
  </div>
);

export default function Dashboard() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchLeads = async () => {
    setLoading(true);
    // Calling our Agentic Backend
    const response = await fetch('http://localhost:8000/leads');
    const data = await response.json();
    setLeads(mergeLeads(data.leads || []));
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <header className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Planroom Genius — Leads</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchLeads}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            {loading ? 'Refreshing...' : 'Refresh Leads'}
          </button>
          <span className="text-sm text-slate-600">{leads.length} leads</span>
        </div>
      </header>

      <div className="overflow-x-auto bg-white rounded shadow">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">ID</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Name</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Company</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Bid Date</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Expected Start</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Location</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Contact</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Contact Email</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Files</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Source</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Extracted At</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Link</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {leads.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-sm text-gray-500">No leads found</td>
              </tr>
            )}
            {leads.map((lead, idx) => (
              <tr key={idx} className="hover:bg-gray-50">
                <td className="px-3 py-2 text-xs text-gray-800">{lead.id || '—'}</td>
                <td className="px-3 py-2 text-xs text-gray-800 truncate max-w-xs">{lead.name || lead.projectName || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800 truncate max-w-xs">{lead.company || lead.gc || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.bid_date || lead.due_date || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.expected_start || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800 truncate max-w-xs">{lead.location || `${lead.city || ''}${lead.state ? ', ' + lead.state : ''}` || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.contact_name || lead.contact || 'N/A'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.contact_email || '—'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.files_count ?? (lead.has_new_files ? 'New' : lead.files_link ? 'Yes' : 'No')}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.site || lead.source || 'BuildingConnected'}</td>
                <td className="px-3 py-2 text-xs text-gray-800">{lead.extracted_at ? new Date(lead.extracted_at).toLocaleString() : '—'}</td>
                <td className="px-3 py-2 text-xs text-blue-600">
                  {(lead.merged_count && lead.merged_count > 1) && <span className="inline-block text-[10px] bg-yellow-100 text-yellow-800 px-2 py-1 rounded mr-2">Merged x{lead.merged_count}</span>}
                  {lead.url && lead.url !== 'N/A' ? (
                    <a href={lead.url} target="_blank" rel="noreferrer">Open</a>
                  ) : lead.files_link ? (
                    <a href={lead.files_link} target="_blank" rel="noreferrer">Files</a>
                  ) : lead.download_link ? (
                    <a href={lead.download_link} target="_blank" rel="noreferrer">Download</a>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}