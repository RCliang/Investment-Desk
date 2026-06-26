import ChainPage from './pages/ChainPage';

/**
 * Single-page entry. The dark Ant Design ConfigProvider and BrowserRouter
 * have been removed; ChainKbPage owns the full viewport with its own
 * `.chainkb-root` paper theme.
 *
 * To revive routing: reinstall react-router-dom, wrap this return value
 * in <BrowserRouter><Routes>...</Routes></BrowserRouter>, and add routes.
 * ChainPage is preserved at src/pages/ChainPage.tsx as the /chain target.
 */
export default function App() {
  return <ChainPage />;
}
