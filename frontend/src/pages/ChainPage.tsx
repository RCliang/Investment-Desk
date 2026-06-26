import ChainKbPage from '../chainkb/ChainKbPage';

/**
 * ChainPage is a thin wrapper around the sketch-aesthetic ChainKbPage
 * dashboard. It is the sole landing page of the app (see App.tsx);
 * ChainKbPage scopes its own paper / hand-drawn theme under
 * `.chainkb-root`.
 *
 * See `src/chainkb/ChainKbPage.tsx` and `docs/superpowers/specs/` for
 * architecture details.
 */
export default function ChainPage() {
  return <ChainKbPage />;
}
