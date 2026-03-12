import { Plus, Settings } from 'lucide-react';
import clsx from 'clsx';

export default function TopNav({ onAddLead, onSettings }) {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        height: '52px',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        paddingLeft: '16px',
        paddingRight: '16px',
        gap: '16px',
      }}
    >
      {/* Logo area */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        <img
          src="/logo.png"
          alt="Marmic Fire & Safety"
          style={{ height: '32px', width: 'auto' }}
        />
        <span
          style={{
            fontSize: '15px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '-0.01em',
          }}
        >
          Planroom<span style={{ color: '#ed2028' }}>Genius</span>
        </span>
      </div>

      {/* Nav pills (center) */}
      <nav style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
        <button
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            paddingLeft: '16px',
            paddingRight: '16px',
            height: '32px',
            borderRadius: '9999px',
            background: '#ed2028',
            color: '#ffffff',
            fontSize: '13px',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            letterSpacing: '0.01em',
          }}
        >
          Bid Board
        </button>
      </nav>

      {/* Right actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        <button
          onClick={onAddLead}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            paddingLeft: '14px',
            paddingRight: '14px',
            height: '34px',
            borderRadius: '8px',
            background: '#16a34a',
            color: '#ffffff',
            fontSize: '13px',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            letterSpacing: '0.01em',
            transition: 'background 0.15s ease',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = '#15803d')}
          onMouseLeave={e => (e.currentTarget.style.background = '#16a34a')}
        >
          <Plus size={15} strokeWidth={2.5} />
          Add Lead
        </button>

        <button
          onClick={onSettings}
          title="Settings"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '34px',
            height: '34px',
            borderRadius: '8px',
            background: 'rgba(100,116,139,0.15)',
            color: '#94a3b8',
            border: '1px solid rgba(255,255,255,0.08)',
            cursor: 'pointer',
            transition: 'background 0.15s ease, color 0.15s ease',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(100,116,139,0.28)';
            e.currentTarget.style.color = '#cbd5e1';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'rgba(100,116,139,0.15)';
            e.currentTarget.style.color = '#94a3b8';
          }}
        >
          <Settings size={16} strokeWidth={2} />
        </button>
      </div>
    </header>
  );
}
