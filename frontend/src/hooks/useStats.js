import { useMemo } from 'react';
import { getSystemTags } from '../lib/tags';

/**
 * useStats(leads)
 *
 * Returns derived statistics from the leads array.
 * Uses useMemo for performance.
 */
export function useStats(leads) {
  return useMemo(() => {
    // Normalize today to midnight for date comparisons
    const now = new Date();
    const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const in3DaysMidnight = new Date(todayMidnight);
    in3DaysMidnight.setDate(todayMidnight.getDate() + 3);

    const todayStr = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0'),
    ].join('-');

    let activeLeads = 0;
    let verifiedManufacturer = 0;
    let dueToday = 0;
    let dueIn3Days = 0;

    for (const lead of leads) {
      // activeLeads: not hidden and not strikethrough
      if (!lead.hidden && !lead.strikethrough) {
        activeLeads++;
      }

      // verifiedManufacturer: has COMP MFG in user tags or system tags
      const userTagIds = (lead.tags || []).map(t => t.id);
      const systemTagIds = getSystemTags(lead);
      if (userTagIds.includes('COMP MFG') || systemTagIds.includes('COMP MFG')) {
        verifiedManufacturer++;
      }

      // dueToday / dueIn3Days
      const bidDate = lead.bid_date;
      if (bidDate && bidDate !== 'N/A' && bidDate !== 'TBD') {
        try {
          // Parse as local date by treating YYYY-MM-DD as local midnight
          const parts = bidDate.split('-');
          if (parts.length === 3) {
            const bidMidnight = new Date(
              parseInt(parts[0], 10),
              parseInt(parts[1], 10) - 1,
              parseInt(parts[2], 10)
            );
            if (!isNaN(bidMidnight.getTime())) {
              // dueToday: bid_date === today (YYYY-MM-DD)
              if (bidDate === todayStr) {
                dueToday++;
              }
              // dueIn3Days: bid_date is within next 3 days (including today)
              if (bidMidnight >= todayMidnight && bidMidnight < in3DaysMidnight) {
                dueIn3Days++;
              }
            }
          }
        } catch {
          // skip unparseable dates
        }
      }
    }

    return { activeLeads, verifiedManufacturer, dueToday, dueIn3Days };
  }, [leads]);
}
