import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./lib/auth";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Members from "./pages/Members";
import NewRecon from "./pages/NewRecon";
import ReportPage from "./pages/Report";
import BankRecon, { BankReportPage } from "./pages/BankRecon";
import Invoices from "./pages/Invoices";
import Books from "./pages/Books";
import Review from "./pages/Review";
import Workspace from "./pages/Workspace";
import Close from "./pages/Close";
import Operations from "./pages/Operations";

function RequireAuth({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <div className="min-h-screen bg-paper" />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(pathname)}`} replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      {/* Signed report links stay viewable without an account. */}
      <Route path="/app/r/:token" element={<ReportPage />} />
      <Route path="/app/bank/r/:token" element={<BankReportPage />} />
      <Route path="/app" element={<RequireAuth><Workspace /></RequireAuth>} />
      <Route path="/app/recon" element={<RequireAuth><NewRecon /></RequireAuth>} />
      <Route path="/app/bank" element={<RequireAuth><BankRecon /></RequireAuth>} />
      <Route path="/app/invoices" element={<RequireAuth><Invoices /></RequireAuth>} />
      <Route path="/app/books" element={<RequireAuth><Books /></RequireAuth>} />
      <Route path="/app/review" element={<RequireAuth><Review /></RequireAuth>} />
      <Route path="/app/close" element={<RequireAuth><Close /></RequireAuth>} />
      <Route path="/app/ops" element={<RequireAuth><Operations /></RequireAuth>} />
      <Route path="/app/members" element={<RequireAuth><Members /></RequireAuth>} />
    </Routes>
  );
}
