"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useOcrStore } from "@/store/ocr-store";
import { TransactionTable } from "@/components/transaction-table";
import { TransactionFilters } from "@/components/transaction-filters";
import { ExportButton } from "@/components/export-button";
import { SummaryCard } from "@/components/summary-card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { formatUSD } from "@/lib/currency";
import { getRevenueSnapshot } from "@/lib/revenue-filter";
import type { DocumentResult } from "@/lib/api";
import {
  TrendingDown,
  Activity,
  FileText,
  Upload,
  Building2,
  CreditCard,
  User,
  Wallet,
  CircleDollarSign,
  MinusCircle,
} from "lucide-react";
import Link from "next/link";

function displayMeta(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function resolveActiveDocument(
  documents: DocumentResult[],
  sourceFilter: string
): DocumentResult | undefined {
  if (sourceFilter !== "all") {
    return documents.find((d) => d.filename === sourceFilter);
  }
  if (documents.length === 1) return documents[0];
  return documents[documents.length - 1];
}

export default function TransactionsPage() {
  const { documents, allTransactions } = useOcrStore();
  const transactions = allTransactions();

  // console.log("transactions:", transactions, "documents:", documents);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  // console.log("udgeeet Bhatt", "sourceFilter:", sourceFilter);
  const activeDocument = useMemo(
    () => resolveActiveDocument(documents, sourceFilter),
    [documents, sourceFilter]
  );

  const accountMetaSubtitle =
    sourceFilter === "all" && documents.length > 1
      ? `From ${activeDocument?.filename ?? "latest statement"} (${documents.length} statements)`
      : activeDocument?.filename
        ? `From ${activeDocument.filename}`
        : undefined;

  /* Unique source filenames */
  const sources = useMemo(
    () => [...new Set(transactions.map((t) => t._filename))],
    [transactions]
  );

  // console.log("source source", sources, "activeDocument:", activeDocument);

  /* Filter logic */
  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      if (search) {
        const q = search.toLowerCase();
        const matchesSearch =
          (t.description || "").toLowerCase().includes(q) ||
          (t.date || "").toLowerCase().includes(q) ||
          (t.reference || "").toLowerCase().includes(q) ||
          (t._filename || "").toLowerCase().includes(q);
        if (!matchesSearch) return false;
      }

      if (typeFilter === "credit" && !Number(t.credit)) return false;
      if (typeFilter === "debit" && !Number(t.debit)) return false;

      if (sourceFilter !== "all" && t._filename !== sourceFilter) return false;

      return true;
    });
  }, [transactions, search, typeFilter, sourceFilter]);

  /* Compute stats from the currently visible (source-filtered) transactions.
     When "All Transactions" tab is active → global stats.
     When a specific PDF is selected → per-PDF stats. */
  const stats = useMemo(() => {
    // Use source-filtered transactions (ignore text search & type filter
    // so that summary cards always reflect the full scope of the selected source)
    const scopedTx = sourceFilter === "all"
      ? transactions
      : transactions.filter((t) => t._filename === sourceFilter);

    const snapshot = getRevenueSnapshot(scopedTx);

    return {
      totalCredits: snapshot.rawCredits,
      adjustedRevenue: snapshot.adjustedRevenue,
      revenueDeductions: snapshot.revenueDeductions,
      totalDebits: snapshot.totalDebits,
      netFlow: snapshot.netFlow,
      totalTransactions: scopedTx.length,
      statementsProcessed: sourceFilter === "all" ? documents.length : 1,
    };
  }, [transactions, sourceFilter, documents.length]);

  /* Export data shape */
  const exportData = useMemo(
    () =>
      filtered.map((t) => ({
        Date: t.date || "",
        Description: t.description || "",
        Debit: t.debit ? String(t.debit) : "",
        Credit: t.credit ? String(t.credit) : "",
        "Revenue Status": t.revenue_status || "",
        "Deduction Reason": t.revenue_deduction_reason || "",
        "Adjusted Revenue": t.adjusted_revenue_amount
          ? String(t.adjusted_revenue_amount)
          : "",
        Balance: t.balance ? String(t.balance) : "",
        // Reference: t.reference || "",
        // Source: t._filename || "",
      })),
    [filtered]
  );
  // console.log("exportData,",exportData)

  /* Per-document tabs */
  const tabItems = useMemo(() => {
    const items = [{ value: "all", label: "All Transactions" }];
    documents.forEach((doc, idx) => {
      const tabValue = `doc-${idx}-${doc.filename}`;
      items.push({
        value: tabValue,
        label:
          doc.filename.length > 20
            ? doc.filename.slice(0, 18) + "…"
            : doc.filename,
      });
    });
    return items;
  }, [documents]);

  /* No data state */
  if (!transactions.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center text-center"
        >
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
            <FileText className="h-8 w-8 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">
            No transactions yet
          </h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Upload and process bank statements to see extracted transactions
            here.
          </p>
          <Link href="/upload">
            <Button className="mt-5 gap-2">
              <Upload className="h-4 w-4" /> Upload Statements
            </Button>
          </Link>
        </motion.div>
      </div>
    );
  }



  return (
    <div className="space-y-6">
      {/* Flow summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Raw Credits"
          value={formatUSD(stats.totalCredits)}
          subtitle="All incoming deposits before filtering"
          icon={<CircleDollarSign className="h-5 w-5" />}
          accentColor="bg-[var(--credit)]/10 text-[var(--credit)]"
        />
        <SummaryCard
          title="Adjusted Revenue"
          value={formatUSD(stats.adjustedRevenue)}
          subtitle={`Variance ${formatUSD(stats.revenueDeductions)} removed`}
          icon={<Activity className="h-5 w-5" />}
          accentColor="bg-primary/10 text-primary"
        />
        <SummaryCard
          title="Total Debits"
          value={formatUSD(stats.totalDebits)}
          icon={<TrendingDown className="h-5 w-5" />}
          accentColor="bg-[var(--debit)]/10 text-[var(--debit)]"
        />
        <SummaryCard
          title="Deductions"
          value={formatUSD(stats.revenueDeductions)}
          subtitle={
            sourceFilter === "all"
              ? `${stats.totalTransactions} transactions across ${stats.statementsProcessed} statements`
              : `${stats.totalTransactions} transactions in this statement`
          }
          icon={<MinusCircle className="h-5 w-5" />}
          accentColor="bg-amber-500/10 text-amber-600 dark:text-amber-400"
        />
      </div>
      {/* Account metadata from OCR */}
      {
        sourceFilter != "all" && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              title="Bank Name"
              value={displayMeta(activeDocument?.bank_name)}
              subtitle={accountMetaSubtitle}
              icon={<Building2 className="h-5 w-5" />}
              accentColor="bg-sky-500/10 text-sky-600 dark:text-sky-400"
            />
            <SummaryCard
              title="Account Number"
              value={displayMeta(activeDocument?.account_number)}
              subtitle="Extracted from statement"
              icon={<CreditCard className="h-5 w-5" />}
              accentColor="bg-violet-500/10 text-violet-600 dark:text-violet-400"
            />
            <SummaryCard
              title="Customer Number"
              value={displayMeta(activeDocument?.customer_number)}
              subtitle="Extracted from statement"
              icon={<User className="h-5 w-5" />}
              accentColor="bg-amber-500/10 text-amber-600 dark:text-amber-400"
            />
            <SummaryCard
              title="Current Balance"
              value={
                activeDocument?.current_balance != null
                  ? formatUSD(activeDocument.current_balance)
                  : "—"
              }
              subtitle="Ending balance from OCR"
              icon={<Wallet className="h-5 w-5" />}
              accentColor="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            />
          </div>
        )
      }


      {/* Tabs for per-document / all */}
      <Tabs
        defaultValue="all"
        onValueChange={(val) => {
          if (val === "all") {
            setSourceFilter("all");
          } else {
            const filename = val.replace(/^doc-\d+-/, "");
            setSourceFilter(filename);
          }
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList className="h-9">
            {tabItems.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} className="text-xs">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <ExportButton data={exportData} filename="bank_transactions" />
        </div>

        <div className="mt-4">
          <TransactionFilters
            search={search}
            onSearchChange={setSearch}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            sourceFilter={sourceFilter}
            onSourceFilterChange={setSourceFilter}
            sources={sources}
          />
        </div>

        <div className="mt-4">
          <TransactionTable data={filtered} typeFilter={typeFilter} />
        </div>
      </Tabs>
    </div>
  );
}
