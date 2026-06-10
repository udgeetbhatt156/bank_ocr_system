"use client";

import type { DocumentResult } from "@/lib/api";
import { formatUSD } from "@/lib/currency";
import { getRevenueStatus } from "@/lib/revenue-filter";
import { SummaryCard } from "@/components/summary-card";
import { TransactionTable } from "@/components/transaction-table";
import {
  Building2,
  CreditCard,
  User,
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
} from "lucide-react";

function displayMeta(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

interface StatementDetailViewProps {
  document: DocumentResult;
  subtitle?: string;
}

export function StatementDetailView({
  document: doc,
  subtitle,
}: StatementDetailViewProps) {
  const transactions = doc.transactions.map((t) => ({
    ...t,
    _filename: doc.filename,
  }));

  let totalCredits = 0;
  let totalDebits = 0;
  for (const t of doc.transactions) {
    const cVal = Number(t.credit || 0);
    if (cVal > 0 && getRevenueStatus(t.description || "", cVal) === "revenue") {
      totalCredits += cVal;
    }
    totalDebits += Number(t.debit || 0);
  }
  const netFlow = totalCredits - totalDebits;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Bank Name"
          value={displayMeta(doc.bank_name)}
          subtitle={subtitle}
          icon={<Building2 className="h-5 w-5" />}
          accentColor="bg-sky-500/10 text-sky-600 dark:text-sky-400"
        />
        <SummaryCard
          title="Account Number"
          value={displayMeta(doc.account_number)}
          subtitle="From statement"
          icon={<CreditCard className="h-5 w-5" />}
          accentColor="bg-violet-500/10 text-violet-600 dark:text-violet-400"
        />
        <SummaryCard
          title="Customer Name"
          value={displayMeta(doc.customer_name)}
          subtitle="From statement"
          icon={<User className="h-5 w-5" />}
          accentColor="bg-amber-500/10 text-amber-600 dark:text-amber-400"
        />
        <SummaryCard
          title="Current Balance"
          value={
            doc.current_balance != null
              ? formatUSD(doc.current_balance)
              : "—"
          }
          subtitle="Ending balance"
          icon={<Wallet className="h-5 w-5" />}
          accentColor="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          title="Total Credits"
          value={formatUSD(totalCredits)}
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor="bg-[var(--credit)]/10 text-[var(--credit)]"
        />
        <SummaryCard
          title="Total Debits"
          value={formatUSD(totalDebits)}
          icon={<TrendingDown className="h-5 w-5" />}
          accentColor="bg-[var(--debit)]/10 text-[var(--debit)]"
        />
        <SummaryCard
          title="Net Flow"
          value={formatUSD(netFlow)}
          subtitle={`${doc.transactions.length} transactions`}
          icon={<Activity className="h-5 w-5" />}
          accentColor="bg-primary/10 text-primary"
        />
      </div>

      <TransactionTable data={transactions} />
    </div>
  );
}
