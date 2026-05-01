import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { NewProjectPage } from "@/pages/NewProjectPage";
import { NewProjectFromCDCPage } from "@/pages/NewProjectFromCDCPage";
import { OSINTDashboardPage } from "@/pages/OSINTDashboardPage";
import { ProgressPage } from "@/pages/ProgressPage";
import { ResultsPage } from "@/pages/ResultsPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { CeoPage } from "@/pages/CeoPage";
import { AhmedInboxPage } from "@/pages/AhmedInboxPage";
import { AutomationPage } from "@/pages/AutomationPage";
import { FleetPage } from "@/pages/FleetPage";
import { ObservabilityPage } from "@/pages/ObservabilityPage";
import { CognitionPage } from "@/pages/CognitionPage";
import { TruthPage } from "@/pages/TruthPage";
import { DomainsPage } from "@/pages/DomainsPage";
import { AppShell } from "@/components/layout/AppShell";
import { ClientShell } from "@/components/layout/ClientShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { ClientDashboardPage } from "@/pages/client/ClientDashboardPage";
import { ClientDeliverablesPage } from "@/pages/client/ClientDeliverablesPage";
import { ClientPaymentsPage } from "@/pages/client/ClientPaymentsPage";
import { ClientProfilePage } from "@/pages/client/ClientProfilePage";
import { StyleguidePage } from "@/pages/StyleguidePage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AuthGuard />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="ceo" element={<CeoPage />} />
            <Route path="ahmed_inbox" element={<AhmedInboxPage />} />
            <Route path="automation" element={<AutomationPage />} />
            <Route path="fleet" element={<FleetPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="cognition" element={<CognitionPage />} />
            <Route path="truth" element={<TruthPage />} />
            <Route path="domains" element={<DomainsPage />} />
            <Route path="new" element={<NewProjectPage />} />
            <Route path="ceo/new-project" element={<NewProjectFromCDCPage />} />
            <Route path="osint" element={<OSINTDashboardPage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="tasks/:id" element={<ProgressPage />} />
            <Route path="tasks/:id/results" element={<ResultsPage />} />
            <Route path="styleguide" element={<StyleguidePage />} />
          </Route>
          <Route path="client" element={<ClientShell />}>
            <Route index element={<ClientDashboardPage />} />
            <Route path="deliverables" element={<ClientDeliverablesPage />} />
            <Route path="payments" element={<ClientPaymentsPage />} />
            <Route path="profile" element={<ClientProfilePage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
