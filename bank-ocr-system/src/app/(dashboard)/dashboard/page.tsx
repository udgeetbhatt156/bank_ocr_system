"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { useOcrStore } from "@/store/ocr-store";
import { SummaryCard } from "@/components/summary-card";
import { InflowOutflowChart } from "@/components/charts/inflow-outflow-chart";
import { MonthlyTrendChart } from "@/components/charts/monthly-trend-chart";
import { OcrHealth } from "@/components/ocr-health";
import {
  FileText,
  TrendingUp,
  TrendingDown,
  Activity,
  Upload,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { formatUSD } from "@/lib/currency";

/* ── Demo / placeholder data when no real data exists ── */
const DEMO_BAR_DATA = [
  { name: "Jan", credits: 85000, debits: 42000 },
  { name: "Feb", credits: 72000, debits: 38000 },
  { name: "Mar", credits: 96000, debits: 51000 },
  { name: "Apr", credits: 64000, debits: 47000 },
  { name: "May", credits: 88000, debits: 55000 },
  { name: "Jun", credits: 102000, debits: 61000 },
];

const DEMO_TREND_DATA = [
  { name: "Jan", amount: 43000 },
  { name: "Feb", amount: 34000 },
  { name: "Mar", amount: 45000 },
  { name: "Apr", amount: 17000 },
  { name: "May", amount: 33000 },
  { name: "Jun", amount: 41000 },
];

export default function DashboardPage() {
  const { documents, summaryStats, allTransactions } = useOcrStore();
  const stats = summaryStats();
  const transactions = allTransactions();
  const hasData = documents.length > 0;

  /* Build chart data from real transactions when available */
  const barData = useMemo(() => {
    if (!hasData) return DEMO_BAR_DATA;
    const byMonth: Record<string, { credits: number; debits: number }> = {};
    for (const t of transactions) {
      const month = t.date
        ? new Date(t.date).toLocaleString("en", { month: "short" })
        : "Unknown";
      if (!byMonth[month]) byMonth[month] = { credits: 0, debits: 0 };
      byMonth[month].credits += Number(t.credit || 0);
      byMonth[month].debits += Number(t.debit || 0);
    }
    return Object.entries(byMonth).map(([name, v]) => ({ name, ...v }));
  }, [hasData, transactions]);

  const trendData = useMemo(() => {
    if (!hasData) return DEMO_TREND_DATA;
    const byMonth: Record<string, number> = {};
    for (const t of transactions) {
      const month = t.date
        ? new Date(t.date).toLocaleString("en", { month: "short" })
        : "Unknown";
      byMonth[month] =
        (byMonth[month] || 0) + Number(t.credit || 0) - Number(t.debit || 0);
    }
    return Object.entries(byMonth).map(([name, amount]) => ({ name, amount }));
  }, [hasData, transactions]);

  /* Recent transactions (last 8) */
  const recent = transactions.slice(-8).reverse();

  return (
    <div className="space-y-6">
      {/* ── Summary Cards ── */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Statements Processed"
          value={hasData ? String(stats.statementsProcessed) : "0"}
          subtitle="Total documents scanned"
          icon={<FileText className="h-5 w-5" />}
          accentColor="bg-primary/10 text-primary"
        />
        <SummaryCard
          title="Total Credits"
          value={hasData ? formatUSD(stats.totalCredits) : "—"}
          subtitle="All inflows combined"
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor="bg-[var(--credit)]/10 text-[var(--credit)]"
        />
        <SummaryCard
          title="Total Debits"
          value={hasData ? formatUSD(stats.totalDebits) : "—"}
          subtitle="All outflows combined"
          icon={<TrendingDown className="h-5 w-5" />}
          accentColor="bg-[var(--debit)]/10 text-[var(--debit)]"
        />
        <SummaryCard
          title="Net Flow"
          value={hasData ? formatUSD(stats.netFlow) : "—"}
          subtitle={`${hasData ? stats.totalTransactions : 0} transactions`}
          icon={<Activity className="h-5 w-5" />}
          accentColor="bg-[var(--chart-5)]/10 text-[var(--chart-5)]"
        />
      </div>

      {/* ── OCR Health Dashboard ── */}
      <OcrHealth />

      {/* ── Empty state CTA ── */}
      {!hasData && (
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border bg-card/50 px-6 py-14 text-center"
        >
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
            <Upload className="h-7 w-7 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">
            No statements processed yet
          </h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Upload your bank statements to see extracted transactions, analytics,
            and consolidated tables here.
          </p>
          <Link href="/upload">
            <Button className="mt-5 gap-2" size="lg">
              Upload Statements <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </motion.div>
      )}

      {/* ── Charts ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <InflowOutflowChart data={barData} />
        <MonthlyTrendChart data={trendData} />
      </div>

      {/* ── Recent Transactions ── */}
      {recent.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                Recent Transactions
              </h3>
              <p className="text-xs text-muted-foreground">
                Latest extracted entries
              </p>
            </div>
            <Link href="/transactions">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                View all <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                  <th className="py-2 pr-4 text-left font-medium">Date</th>
                  <th className="py-2 pr-4 text-left font-medium">
                    Description
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">Debit</th>
                  <th className="py-2 pr-4 text-right font-medium">Credit</th>
                  <th className="py-2 text-right font-medium">Balance</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((t, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/50 last:border-0"
                  >
                    <td className="py-2.5 pr-4 text-foreground whitespace-nowrap">
                      {t.date || "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-foreground max-w-[240px] truncate">
                      {t.description || "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-medium whitespace-nowrap text-[var(--debit)]">
                      {t.debit ? formatUSD(Number(t.debit)) : "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-medium whitespace-nowrap text-[var(--credit)]">
                      {t.credit ? formatUSD(Number(t.credit)) : "—"}
                    </td>
                    <td className="py-2.5 text-right text-muted-foreground whitespace-nowrap">
                      {t.balance ? formatUSD(Number(t.balance)) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
