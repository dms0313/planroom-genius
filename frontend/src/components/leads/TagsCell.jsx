import React from 'react';
import { PREDEFINED_TAGS, tagColorClass, getSystemTags, getTagHoverText } from '../../lib/tags';

/**
 * TagsCell — compact fixed-width tag display with overflow cap.
 * Shows first 3 tags, then "+N more" if there are additional tags.
 */
const TagsCell = ({ lead, onToggleTag, onOpenTagPicker, tagPicker }) => {
  // Build full list: budget pill + user tags + system tags
  const allTags = [];

  if (lead.has_budget) {
    allTags.push({ id: '__budget__', label: 'BUDGET', color: 'green', isBudget: true });
  }

  (lead.tags || []).forEach((tag) => {
    allTags.push({ ...tag, isUser: true });
  });

  getSystemTags(lead).forEach((tagId) => {
    const pt = PREDEFINED_TAGS.find((t) => t.id === tagId);
    if (pt) allTags.push({ ...pt, isSystem: true });
  });

  const VISIBLE_LIMIT = 3;
  const visibleTags = allTags.slice(0, VISIBLE_LIMIT);
  const hiddenCount = allTags.length - visibleTags.length;

  return (
    <div
      className="flex flex-nowrap gap-1 items-center overflow-hidden"
      style={{ maxWidth: '240px' }}
    >
      {visibleTags.map((tag, idx) => {
        if (tag.isBudget) {
          return (
            <span
              key="budget"
              className="relative group/tag text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30 cursor-default whitespace-nowrap flex-shrink-0"
            >
              BUDGET
              <span className="absolute bottom-full left-0 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 max-w-[200px] opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50 whitespace-normal">
                Project has budget / cost estimate info
              </span>
            </span>
          );
        }

        if (tag.isUser) {
          const hoverText = getTagHoverText(tag.label, lead);
          return (
            <span
              key={`u-${idx}`}
              className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-pointer transition-opacity hover:opacity-70 whitespace-nowrap flex-shrink-0 ${tagColorClass(tag.color)}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleTag && onToggleTag(lead, tag.label);
              }}
            >
              {tag.label}
              <span className="absolute bottom-full left-0 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 max-w-[220px] opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50 whitespace-normal leading-relaxed">
                {hoverText}
                <br />
                <span className="text-slate-500 text-[9px]">click to remove</span>
              </span>
            </span>
          );
        }

        if (tag.isSystem) {
          const hoverText = getTagHoverText(tag.id, lead);
          return (
            <span
              key={`s-${idx}`}
              className={`relative group/tag text-[10px] px-1.5 py-0.5 rounded border cursor-default whitespace-nowrap flex-shrink-0 ${tagColorClass(tag.color)}`}
            >
              {tag.label}
              <span className="absolute bottom-full left-0 mb-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-[10px] text-slate-200 max-w-[220px] opacity-0 group-hover/tag:opacity-100 pointer-events-none transition-opacity z-50 whitespace-normal leading-relaxed">
                {hoverText}
              </span>
            </span>
          );
        }

        return null;
      })}

      {hiddenCount > 0 && (
        <span
          className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700/50 bg-slate-800/60 text-slate-500 cursor-default"
          title={`${hiddenCount} more tag${hiddenCount > 1 ? 's' : ''}`}
        >
          +{hiddenCount} more
        </span>
      )}

      {/* Tag picker toggle */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onOpenTagPicker && onOpenTagPicker(lead.id, e);
        }}
        className={`text-[10px] px-1.5 py-0.5 rounded border border-dashed transition-all ${
          tagPicker?.leadId === lead.id
            ? 'border-orange-500 text-orange-400'
            : 'border-slate-700 text-slate-600 hover:border-slate-500 hover:text-slate-400'
        }`}
        title="Add / remove tags"
      >
        +
      </button>
    </div>
  );
};

export default TagsCell;
