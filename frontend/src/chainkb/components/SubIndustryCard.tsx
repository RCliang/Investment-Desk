import type { SubIndustry } from '../../types/chainkb';

interface SubIndustryCardProps {
  sub: SubIndustry;
  onClick: (groupId: string) => void;
}

/**
 * Clickable sub-industry tile. Shows name (zh) + group_id mono code +
 * company count in a hand-drawn Caveat numeral.
 */
export default function SubIndustryCard({ sub, onClick }: SubIndustryCardProps) {
  return (
    <div
      className="sub-card"
      onClick={() => onClick(sub.group_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(sub.group_id);
        }
      }}
    >
      <div className="sub-card-name">{sub.name_zh}</div>
      <div className="sub-card-meta">
        <span>{sub.group_id}</span>
        <span className="sub-card-count">{sub.company_count}</span>
      </div>
    </div>
  );
}
