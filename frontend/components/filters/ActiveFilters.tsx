import type { AnalysisFilter } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";

type ActiveFiltersProps = {
  filters: AnalysisFilter[];
  onRemove: (field: string) => void;
};

export function ActiveFilters({ filters, onRemove }: ActiveFiltersProps) {
  if (filters.length === 0) return null;

  return (
    <section className="active-filters" aria-label="Active filters">
      <div className="filter-heading">
        <span>ACTIVE FILTERS</span>
        <span className="filter-count">{filters.length}</span>
      </div>
      <div className="filter-chip-list">
        {filters.map((filter) => {
          const label = filter.label ?? filter.field;
          return (
            <span className="filter-chip" key={`${filter.field}:${filter.value}`}>
              <span>{label}: <strong>{filter.value}</strong></span>
              <button
                className="remove-filter-button"
                type="button"
                onClick={() => onRemove(filter.field)}
                aria-label={`Remove ${label} filter ${filter.value}`}
              >
                <Icon name="close" size={13} />
              </button>
            </span>
          );
        })}
      </div>
    </section>
  );
}
