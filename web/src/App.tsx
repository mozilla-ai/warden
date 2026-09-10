import { Route, Routes, useLocation, useNavigate } from "react-router"
import { Tab, TabRow } from "./components/TabRow"
import { GatesPage } from "./pages/GatesPage"
import { OverviewPage } from "./pages/OverviewPage"
import { RunsPage } from "./pages/RunsPage"

const TABS = [
  { to: "/", label: "Overview" },
  { to: "/runs", label: "Runs" },
  { to: "/gates", label: "Gates" },
]

function activeTab(pathname: string): string {
  const match = TABS.find((tab) => tab.to !== "/" && pathname.startsWith(tab.to))
  return match?.to ?? "/"
}

// The dashboard frames this page under its own "Agent gates" title, so the
// page carries no title of its own: a row of tabs, then the surface. <main>
// is the scroll container and the column inside it repeats the dashboard's
// own content column, so a band that bleeds measures the same width here.
export function App() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const current = activeTab(pathname)
  return (
    <main className="h-full overflow-y-auto bg-background text-foreground">
      <div className="mx-auto flex min-h-full max-w-[112.5rem] flex-col gap-6 px-4 py-5 md:px-6 md:py-6">
        <TabRow>
          {TABS.map((tab) => (
            <Tab key={tab.to} isActive={current === tab.to} onPress={() => void navigate(tab.to)}>
              {tab.label}
            </Tab>
          ))}
        </TabRow>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/gates" element={<GatesPage />} />
          <Route path="*" element={<OverviewPage />} />
        </Routes>
      </div>
    </main>
  )
}
