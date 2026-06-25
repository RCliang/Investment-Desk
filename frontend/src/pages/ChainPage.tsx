import ChainKbPage from '../chainkb/ChainKbPage';

/**
 * ChainPage is now a thin wrapper around the sketch-aesthetic ChainKbPage
 * dashboard. The dark Ant Design theme continues to govern DataPage /
 * ReportPage / PlanPage; ChainKbPage scopes its own paper / hand-drawn
 * theme under `.chainkb-root`.
 *
 * See `src/chainkb/ChainKbPage.tsx` and `docs/superpowers/specs/` for
 * architecture details.
 */
export default function ChainPage() {
  return <ChainKbPage />;
}
