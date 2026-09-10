import { NavLink, Route, Routes } from "react-router"
import { BranchesPage } from "./pages/BranchesPage"
import { GatesPage } from "./pages/GatesPage"
import { OverviewPage } from "./pages/OverviewPage"
import { ReposPage } from "./pages/ReposPage"
import { RunsPage } from "./pages/RunsPage"
import { SessionsPage } from "./pages/SessionsPage"

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/runs", label: "Runs" },
  { to: "/sessions", label: "Sessions" },
  { to: "/repos", label: "Repos" },
  { to: "/branches", label: "Branches" },
  { to: "/gates", label: "Gates" },
]

export function App() {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <nav aria-label="Agent gates" className="flex w-48 shrink-0 flex-col gap-1 border-r border-border bg-surface p-3">
        <span className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-muted">
          Agent gates
        </span>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `rounded-md px-2 py-1.5 text-sm ${isActive ? "bg-accent-soft font-medium text-accent-soft-foreground" : "text-foreground hover:bg-surface-secondary"}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="min-w-0 flex-1 p-6">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/repos" element={<ReposPage />} />
          <Route path="/branches" element={<BranchesPage />} />
          <Route path="/gates" element={<GatesPage />} />
          <Route path="*" element={<OverviewPage />} />
        </Routes>
      </main>
    </div>
  )
}
