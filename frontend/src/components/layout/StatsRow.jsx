const cards = [
  {
    key: 'activeLeads',
    label: 'Active Leads',
    subLabel: 'in pipeline',
    accent: '#60a5fa',
  },
  {
    key: 'verifiedManufacturer',
    label: 'Compatible Mfr',
    subLabel: 'verified leads',
    accent: '#4ade80',
  },
  {
    key: 'dueToday',
    label: 'Due Today',
    subLabel: 'bid deadlines',
    accent: '#fbbf24',
  },
  {
    key: 'dueIn3Days',
    label: 'Due in 3 Days',
    subLabel: 'including today',
    accent: '#fb923c',
  },
];

export default function StatsRow({
  activeLeads,
  verifiedManufacturer,
  dueToday,
  dueIn3Days,
}) {
  const values = { activeLeads, verifiedManufacturer, dueToday, dueIn3Days };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '12px',
        padding: '16px',
      }}
    >
      {cards.map(({ key, label, subLabel, accent }) => (
        <div
          key={key}
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '12px',
            padding: '18px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <span
            style={{
              fontSize: '30px',
              fontWeight: 700,
              color: accent,
              lineHeight: 1.1,
              letterSpacing: '-0.02em',
            }}
          >
            {values[key] ?? 0}
          </span>
          <span
            style={{
              fontSize: '13px',
              fontWeight: 500,
              color: '#e2e8f0',
              marginTop: '2px',
            }}
          >
            {label}
          </span>
          <span
            style={{
              fontSize: '11px',
              color: '#64748b',
              letterSpacing: '0.02em',
              textTransform: 'uppercase',
            }}
          >
            {subLabel}
          </span>
        </div>
      ))}
    </div>
  );
}
