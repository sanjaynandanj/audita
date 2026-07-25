import { Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import NewRecon from "./pages/NewRecon";
import ReportPage from "./pages/Report";
import BankRecon, { BankReportPage } from "./pages/BankRecon";
import Invoices from "./pages/Invoices";
import Books from "./pages/Books";
import Close from "./pages/Close";
import Operations from "./pages/Operations";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<NewRecon />} />
      <Route path="/app/r/:token" element={<ReportPage />} />
      <Route path="/app/bank" element={<BankRecon />} />
      <Route path="/app/bank/r/:token" element={<BankReportPage />} />
      <Route path="/app/invoices" element={<Invoices />} />
      <Route path="/app/books" element={<Books />} />
      <Route path="/app/close" element={<Close />} />
      <Route path="/app/ops" element={<Operations />} />
    </Routes>
  );
}
