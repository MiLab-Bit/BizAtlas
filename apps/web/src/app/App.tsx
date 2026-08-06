import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { IntakePage } from "../pages/IntakePage";
import { ReportsPage } from "../pages/ReportsPage";
import { RulesPage } from "../pages/RulesPage";
import { WorkbenchPage } from "../pages/WorkbenchPage";
import { Shell } from "./Shell";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<IntakePage />} />
          <Route path="workbench" element={<WorkbenchPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
