import React, { useState, useEffect } from 'react';
import { Plus, X, FolderOpen, Search } from 'lucide-react';

const EMPTY_FORM = {
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
  has_budget: false,
};

/**
 * AddLeadModal
 *
 * Props:
 *   open              — boolean
 *   onClose           — () => void
 *   onAdd             — (formData) => Promise<boolean>  (true on success)
 *   externalFilesLink — string | undefined  — when this changes to non-empty,
 *                       the modal sets formData.files_link to this value.
 *                       Used by the parent's folder browser / picker flows.
 *   onBrowseFolderPicker — () => void  — trigger native folder picker
 *   onBrowseFolderServer — () => void  — open server folder browser modal
 */
export default function AddLeadModal({
  open,
  onClose,
  onAdd,
  externalFilesLink,
  onBrowseFolderPicker,
  onBrowseFolderServer,
}) {
  const [formData, setFormData] = useState(EMPTY_FORM);

  // Sync external files link selection into the form
  useEffect(() => {
    if (externalFilesLink) {
      setFormData((prev) => ({ ...prev, files_link: externalFilesLink }));
    }
  }, [externalFilesLink]);

  const handleCancel = () => {
    setFormData(EMPTY_FORM);
    onClose();
  };

  const handleSubmit = async () => {
    const success = await onAdd(formData);
    if (success) {
      setFormData(EMPTY_FORM);
    }
  };

  const set = (field) => (e) =>
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));

  const setCheck = (field) => (e) =>
    setFormData((prev) => ({ ...prev, [field]: e.target.checked }));

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
      onClick={handleCancel}
    >
      <div
        className="bg-slate-900 border-2 border-slate-700 rounded-2xl p-4 sm:p-6 max-w-2xl w-full mx-2 sm:mx-4 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-start mb-4 sm:mb-6">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Plus className="text-green-500" size={20} />
            Add New Lead
          </h3>
          <button
            onClick={handleCancel}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Form grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Project Name */}
          <div className="sm:col-span-2">
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Project Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={set('name')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="Enter project name"
            />
          </div>

          {/* Company */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Company
            </label>
            <input
              type="text"
              value={formData.company}
              onChange={set('company')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="Company name"
            />
          </div>

          {/* General Contractor */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              General Contractor
            </label>
            <input
              type="text"
              value={formData.gc}
              onChange={set('gc')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="GC name"
            />
          </div>

          {/* Contact Name */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Contact Name
            </label>
            <input
              type="text"
              value={formData.contact_name}
              onChange={set('contact_name')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="Contact person"
            />
          </div>

          {/* Contact Email */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Contact Email
            </label>
            <input
              type="email"
              value={formData.contact_email}
              onChange={set('contact_email')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="email@example.com"
            />
          </div>

          {/* Contact Phone */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Contact Phone
            </label>
            <input
              type="tel"
              value={formData.contact_phone}
              onChange={set('contact_phone')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="(555) 123-4567"
            />
          </div>

          {/* Bid Date */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Bid Date
            </label>
            <input
              type="text"
              value={formData.bid_date}
              onChange={set('bid_date')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="MM/DD/YYYY or TBD"
            />
          </div>

          {/* Location */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Location
            </label>
            <input
              type="text"
              value={formData.location}
              onChange={set('location')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="City, State"
            />
          </div>

          {/* Full Address */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Full Address
            </label>
            <input
              type="text"
              value={formData.full_address}
              onChange={set('full_address')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="123 Main St, City, State ZIP"
            />
          </div>

          {/* Description */}
          <div className="sm:col-span-2">
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={set('description')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none h-20 resize-none"
              placeholder="Project description..."
            />
          </div>

          {/* Files Link */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Files Link
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={formData.files_link}
                onChange={set('files_link')}
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
                placeholder="https://... or C:\..."
              />
              <button
                onClick={onBrowseFolderPicker}
                className="bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-3 rounded-lg transition-colors"
                title="Native Folder Picker"
              >
                <FolderOpen size={18} />
              </button>
              <button
                onClick={onBrowseFolderServer}
                className="bg-blue-700 hover:bg-blue-600 text-slate-300 hover:text-white px-3 rounded-lg transition-colors"
                title="Browse Server Folders"
              >
                <Search size={18} />
              </button>
            </div>
          </div>

          {/* Download Link */}
          <div>
            <label className="block text-xs text-slate-500 uppercase tracking-wide mb-1">
              Download Link
            </label>
            <input
              type="url"
              value={formData.download_link}
              onChange={set('download_link')}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-orange-500 focus:outline-none"
              placeholder="https://..."
            />
          </div>

          {/* Checkboxes */}
          <div className="sm:col-span-2 flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.sprinklered}
                onChange={setCheck('sprinklered')}
                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500"
              />
              <span className="text-sm text-slate-300">Sprinklered</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.has_budget}
                onChange={setCheck('has_budget')}
                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-orange-500 focus:ring-orange-500"
              />
              <span className="text-sm text-slate-300">Has Budget</span>
            </label>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <button
            onClick={handleCancel}
            className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!formData.name}
            className="flex-1 bg-[#ed2028] hover:bg-red-600 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold py-3 rounded-lg transition-colors"
          >
            Add Lead
          </button>
        </div>
      </div>
    </div>
  );
}
