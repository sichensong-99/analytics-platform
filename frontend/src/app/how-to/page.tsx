import Link from 'next/link';

export default function HowToPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3">
        <Link href="/dashboards" className="text-sm text-blue-600 hover:underline">
          Back to Dashboards
        </Link>
      </nav>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        <header>
          <h1 className="text-2xl font-bold text-gray-900">How to use this portal</h1>
          <p className="text-gray-600 mt-2">
            This is the 32 Degrees internal analytics portal. It replaces the legacy
            Panoply / Power BI reports with governed, self-service dashboards for the
            merchandising, planning, and leadership teams. Every number traces back to a
            documented definition in the Metrics Catalog.
          </p>
        </header>

        {/* Getting started */}
        <section className="bg-white p-5 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Getting started</h2>
          <ol className="list-decimal list-inside text-sm text-gray-700 space-y-1">
            <li>Sign in with your work email and password.</li>
            <li>You land on <span className="font-medium">Dashboards</span>, the hub for every report.</li>
            <li>Most users have a <span className="font-medium">viewer</span> role. The admin manages accounts.</li>
            <li>Need an account or a password reset? Contact the portal admin (Sia).</li>
          </ol>
        </section>

        {/* Core workflows */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Core workflows</h2>

          <Workflow
            title="1 · Style × Channel × Week — Quantity"
            purpose="See how many units each style sold, by marketing channel, per week."
            steps={[
              'Open Dashboards → Style × Channel × Week — Quantity.',
              'Set the Start Date and End Date for the period you care about.',
              'Optional: filter by Channel, Season, or Style. Each filter has a search box — type to find an option in long lists. Leave a filter empty to include everything.',
              'Read the line chart (units by channel over the weeks) and the Style × Channel matrix below it.',
              'Click Download CSV to export every matching row (not just the page you are viewing).',
            ]}
          />

          <Workflow
            title="2 · Amazon FBA Inbound — Receiving by SKU"
            purpose="Track inbound FBA shipments and spot receiving gaps for planning."
            steps={[
              'Open Dashboards → Amazon FBA Inbound — Receiving by SKU.',
              'Optional: filter by Shipment Status and/or Destination FC. Empty = all.',
              'Read the KPI cards (Shipments, SKUs, Units Shipped, Receiving Gap).',
              'In the table, the highlighted Gap column shows units shipped but not yet received.',
              'Click Download CSV to export the full dataset.',
            ]}
          />

          <Workflow
            title="3 · Customer Cohort & Repurchase"
            purpose="Understand whether we are turning first-time buyers into repeat customers."
            steps={[
              'Open Dashboards → Customer Cohort & Repurchase.',
              'Read the new-vs-returning split to see how much volume comes from repeat customers over time.',
              'Read the retention heatmap: rows are first-purchase-month cohorts, columns are months since acquisition, and each cell is the share that came back.',
            ]}
          />

          <Workflow
            title="4 · Metrics Catalog (data dictionary)"
            purpose="Look up exactly what any number, filter, or metric means."
            steps={[
              'Open Dashboards → Metrics Catalog (or go to /catalog).',
              'Search by metric name, or expand a metric to see its definition, source system, grain, time coverage, inclusions/exclusions, attribution model, reconciliation note, and version history.',
              'When in doubt about a figure on any dashboard, check its entry here first.',
            ]}
          />
        </section>

        {/* Understanding the numbers */}
        <section className="bg-white p-5 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Understanding the numbers</h2>
          <p className="text-sm text-gray-700">
            Every metric and filter is documented in the{' '}
            <Link href="/catalog" className="text-blue-600 hover:underline">Metrics Catalog</Link>{' '}
            — source system, grain, time coverage, what is included/excluded, attribution model,
            and reconciliation notes. The catalog is the single source of truth for definitions and
            is versioned alongside the product.
          </p>
        </section>

        {/* Known limitations */}
        <section className="bg-white p-5 rounded-lg border border-amber-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Known limitations &amp; caveats</h2>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1.5">
            <li><span className="font-medium">Coverage:</span> sales data is available from <span className="font-medium">July 2025</span>.</li>
            <li><span className="font-medium">Channel attribution</span> is reliable from <span className="font-medium">September 2025</span> (Triple Whale coverage start).</li>
            <li><span className="font-medium">Excluded from sales:</span> replacement orders, EXC orders, and refunded line items are removed (refunds are netted at the line-item level).</li>
            <li><span className="font-medium">Replacement-order exclusion</span> is reliable from <span className="font-medium">May 2026</span> onward (Shopify order-metafield coverage start). Earlier periods may still include a small number of replacement orders — the impact is well under 0.1%.</li>
            <li><span className="font-medium">Amazon</span> data is a weekly snapshot from Amazon’s SP-API.</li>
            <li><span className="font-medium">Reconciliation:</span> Style × Channel quantities reconcile to within ~1.5% of the legacy Panoply report (last validated baseline; Panoply has since been retired).</li>
          </ul>
        </section>

        {/* FAQ */}
        <section className="bg-white p-5 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">FAQ</h2>
          <div className="space-y-3 text-sm">
            <Faq q="Why don’t the numbers exactly match the old Panoply report?"
                 a="They reconcile to within ~1.5%. The platform nets refunds at the line-item level and excludes replacement / EXC orders — a data-quality improvement over the legacy logic. See the Metrics Catalog for each metric’s exact rules." />
            <Faq q="Why is a dashboard slow the very first time I open it?"
                 a="The data warehouse may be cold-starting after a period of inactivity. Give it a minute and refresh — subsequent loads are fast." />
            <Faq q="Can I get the underlying data out?"
                 a="Yes. Each dashboard has a Download CSV button that exports all rows matching your current filters, not just the visible page." />
            <Faq q="What does a specific metric or filter mean?"
                 a="Open the Metrics Catalog and expand the metric. Definitions, sources, grain, exclusions, and reconciliation notes are all there." />
            <Faq q="How do I get access or a new account?"
                 a="Contact the portal admin (Sia)." />
          </div>
        </section>

        <p className="text-xs text-gray-400">
          This guide ships and versions with the product. If something here doesn’t match what you
          see, the discrepancy is a flag — please report it to the admin.
        </p>
      </main>
    </div>
  );
}

function Workflow({ title, purpose, steps }: { title: string; purpose: string; steps: string[] }) {
  return (
    <div className="bg-white p-5 rounded-lg border border-gray-200">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="text-sm text-gray-500 mt-0.5 mb-2">{purpose}</p>
      <ol className="list-decimal list-inside text-sm text-gray-700 space-y-1">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
    </div>
  );
}

function Faq({ q, a }: { q: string; a: string }) {
  return (
    <div>
      <p className="font-medium text-gray-800">{q}</p>
      <p className="text-gray-600 mt-0.5">{a}</p>
    </div>
  );
}