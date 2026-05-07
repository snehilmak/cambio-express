import { Route, Routes } from "react-router-dom";

import Home from "./routes/Home";
import NotFound from "./routes/NotFound";

// Top-level routing for the SPA. Each new screen registers here.
// Initial scaffold: just a Home placeholder + a 404 fallback. As we
// migrate Jinja screens (login, dashboard, transfers list, etc.)
// each lands as its own <Route />.
export default function App() {
  return (
    <Routes>
      <Route index element={<Home />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
