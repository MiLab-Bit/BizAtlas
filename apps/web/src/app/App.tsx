import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { IntakePage } from "../pages/IntakePage";
import { InvestigationPage } from "../pages/InvestigationPage";
import { LoginPage } from "../pages/LoginPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";
import { ReportsPage } from "../pages/ReportsPage";
import { RulesPage } from "../pages/RulesPage";
import { WorkbenchPage } from "../pages/WorkbenchPage";
import { EngineeringPage } from "../pages/EngineeringPage";
import { ModelConfigPage } from "../pages/ModelConfigPage";
import { CreditDecisionPage } from "../pages/CreditDecisionPage";
import { ValidationPage } from "../pages/ValidationPage";
import { Shell } from "./Shell";

export function App() {
  return (
    <BrowserRouter basename="/bizatlas">
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<IntakePage />} />
          <Route path="workbench" element={<WorkbenchPage />} />
          <Route path="investigation" element={<InvestigationPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="engineering" element={<EngineeringPage />} />
          <Route path="credit-decision" element={<CreditDecisionPage />} />
          <Route path="validation" element={<ValidationPage />} />
          <Route path="model-config" element={<ModelConfigPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Routes>
    </BrowserRouter>
  );
}
