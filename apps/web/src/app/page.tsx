import { AskCopilot } from "@/components/ask-copilot";
import { DocumentManagement } from "@/components/document-management";
import { CognitoSignIn } from "@/components/cognito-sign-in";

const services = [
  {
    name: "checkout",
    owner: "Checkout Team",
    status: "Investigating",
    color: "bg-amber-400",
  },
  {
    name: "catalog",
    owner: "Catalog Team",
    status: "Healthy",
    color: "bg-emerald-400",
  },
  {
    name: "orders",
    owner: "Orders Team",
    status: "Healthy",
    color: "bg-emerald-400",
  },
  {
    name: "payments",
    owner: "Payments Team",
    status: "Monitoring",
    color: "bg-sky-400",
  },
];

const activity = [
  "Checkout 2.4.0 deployed - 21:00 UTC",
  "Checkout p95 latency increased to 1,450 ms - 21:12 UTC",
  "Runbook matched: Checkout Latency Investigation",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-sm font-semibold tracking-[0.2em] text-cyan-400">
              SECURECLOUDOPS
            </p>
            <h1 className="mt-1 text-xl font-bold">Incident Copilot</h1>
          </div>

          <div className="flex items-center gap-3">
            <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-sm font-medium text-emerald-300">
              System operational
            </span>
            <CognitoSignIn />
            <a className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
                href="#knowledge-documents"
              >
              Manage knowledge
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-6 px-6 py-8 lg:grid-cols-[1.5fr_1fr]">
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl shadow-slate-950/30">
          <p className="text-sm font-medium text-cyan-300">
            Active investigation
          </p>
          <h2 className="mt-2 text-2xl font-bold">
            Checkout latency after deployment
          </h2>
          <p className="mt-3 max-w-2xl leading-7 text-slate-300">
            Checkout p95 latency rose from 620 ms to 1,450 ms shortly after
            version 2.4.0 was deployed. Ask the copilot to investigate using
            indexed runbooks and deployment history.
          </p>

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <Metric
              label="Current p95 latency"
              value="1,450 ms"
              tone="text-amber-300"
            />
            <Metric
              label="SLO target"
              value="< 800 ms"
              tone="text-emerald-300"
            />
            <Metric
              label="Error rate"
              value="0.6%"
              tone="text-emerald-300"
            />
          </div>

          {/* Interactive client component; it calls the guarded FastAPI RAG endpoint. */}
          <AskCopilot />
        </section>

        <aside className="space-y-6">
          <DocumentManagement />
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-bold">Service health</h2>
            <div className="mt-5 space-y-4">
              {services.map((service) => (
                <div
                  key={service.name}
                  className="flex items-center justify-between border-b border-slate-800 pb-4 last:border-0 last:pb-0"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${service.color}`}
                    />
                    <div>
                      <p className="font-medium">{service.name}</p>
                      <p className="text-sm text-slate-400">{service.owner}</p>
                    </div>
                  </div>
                  <span className="text-sm text-slate-300">
                    {service.status}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-bold">Recent activity</h2>
            <ol className="mt-5 space-y-4">
              {activity.map((item, index) => (
                <li
                  key={item}
                  className="flex gap-3 text-sm leading-6 text-slate-300"
                >
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-cyan-300">
                    {index + 1}
                  </span>
                  {item}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </main>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`mt-2 text-2xl font-bold ${tone}`}>{value}</p>
    </div>
  );
}