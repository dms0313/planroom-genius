import { useState } from 'react';
import {
  X,
  Mail,
  Phone,
  MapPin,
  ClipboardCopy,
  Check,
  Building2,
} from 'lucide-react';

/**
 * ContactPopup — frosted-glass modal for lead contact details.
 *
 * Props:
 *   lead     {object|null}  Lead data object; null = modal closed.
 *   onClose  {() => void}   Called when the user dismisses the modal.
 */
export default function ContactPopup({ lead, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!lead) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(lead.contact_email);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Close when clicking the backdrop but not the card itself
  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  const hasAlsoListedBy =
    Array.isArray(lead.also_listed_by) && lead.also_listed_by.length > 0;

  return (
    <div
      onClick={handleBackdropClick}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '16px',
      }}
    >
      <div
        style={{
          background: '#0a0f1a',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '16px',
          padding: '32px',
          maxWidth: '440px',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        {/* Header row: company name + close button */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Building2
              size={20}
              style={{ color: '#fb923c', flexShrink: 0 }}
            />
            <h2
              style={{
                fontSize: '1.25rem',
                fontWeight: 700,
                color: '#ffffff',
                margin: 0,
                lineHeight: '1.3',
              }}
            >
              {lead.company && lead.company !== 'N/A' ? lead.company : lead.gc}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px',
              padding: '6px',
              cursor: 'pointer',
              color: '#94a3b8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')
            }
          >
            <X size={16} />
          </button>
        </div>

        {/* Contact name + title section */}
        {lead.contact_name && (
          <InfoRow>
            <Label>Contact</Label>
            <Value>{lead.contact_name}</Value>
          </InfoRow>
        )}

        {/* EMAIL — hero element */}
        {lead.contact_email && (
          <div
            style={{
              background: 'rgba(251,146,60,0.08)',
              border: '1px solid rgba(251,146,60,0.25)',
              borderRadius: '8px',
              padding: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
              <Mail size={18} style={{ color: '#fb923c', flexShrink: 0 }} />
              <span
                style={{
                  color: '#fb923c',
                  fontSize: '18px',
                  fontWeight: 600,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {lead.contact_email}
              </span>
            </div>
            <button
              onClick={handleCopy}
              aria-label={copied ? 'Copied' : 'Copy email'}
              style={{
                background: copied
                  ? 'rgba(34,197,94,0.15)'
                  : 'rgba(251,146,60,0.15)',
                border: `1px solid ${copied ? 'rgba(34,197,94,0.4)' : 'rgba(251,146,60,0.4)'}`,
                borderRadius: '6px',
                padding: '6px 10px',
                cursor: 'pointer',
                color: copied ? '#4ade80' : '#fb923c',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '13px',
                fontWeight: 500,
                whiteSpace: 'nowrap',
                flexShrink: 0,
                transition: 'background 0.15s, border-color 0.15s, color 0.15s',
              }}
            >
              {copied ? (
                <>
                  <Check size={13} />
                  Copied!
                </>
              ) : (
                <>
                  <ClipboardCopy size={13} />
                  Copy
                </>
              )}
            </button>
          </div>
        )}

        {/* Phone */}
        {lead.contact_phone && (
          <InfoRow>
            <Label>
              <Phone size={13} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
              Phone
            </Label>
            <Value>{lead.contact_phone}</Value>
          </InfoRow>
        )}

        {/* Location */}
        {lead.location && (
          <InfoRow>
            <Label>
              <MapPin size={13} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
              Location
            </Label>
            <Value>{lead.location}</Value>
          </InfoRow>
        )}

        {/* Source */}
        <InfoRow>
          <Label>Source</Label>
          <Value>{lead.site}</Value>
        </InfoRow>

        {/* Project name */}
        <InfoRow>
          <Label>Project</Label>
          <Value>{lead.name}</Value>
        </InfoRow>

        {/* Also Listed By */}
        {hasAlsoListedBy && (
          <div
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: '8px',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <Label>Also Listed By</Label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {lead.also_listed_by.map((entry, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <span
                    style={{
                      color: '#e2e8f0',
                      fontSize: '14px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {entry.gc}
                  </span>
                  <span
                    style={{
                      color: '#64748b',
                      fontSize: '12px',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {entry.site}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Small helper sub-components ────────────────────────────────────── */

function InfoRow({ children }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        borderRadius: '8px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
      }}
    >
      {children}
    </div>
  );
}

function Label({ children }) {
  return (
    <span
      style={{
        color: '#64748b',
        fontSize: '11px',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}

function Value({ children }) {
  return (
    <span
      style={{
        color: '#e2e8f0',
        fontSize: '14px',
      }}
    >
      {children}
    </span>
  );
}
