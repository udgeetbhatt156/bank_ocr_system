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
import { sumTransactionTotals } from "@/lib/transaction-totals";
import type { DocumentResult } from "@/lib/api";
import {
  TrendingDown,
  TrendingUp,
  Activity,
  FileText,
  Upload,
  Building2,
  CreditCard,
  User,
  Wallet,
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

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

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

  const sources = useMemo(
    () => [...new Set(transactions.map((t) => t._filename))],
    [transactions]
  );

  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      if (search) {
        const q = search.toLowerCase();
        const matchesSearch =
          (t.description || "").toLowerCase().includes(q) ||
          (t.date || "").toLowerCase().includes(q) ||
          (t._filename || "").toLowerCase().includes(q);
        if (!matchesSearch) return false;
      }

      if (typeFilter === "credit" && !Number(t.credit)) return false;
      if (typeFilter === "debit" && !Number(t.debit)) return false;

      if (sourceFilter !== "all" && t._filename !== sourceFilter) return false;

      return true;
    });
  }, [transactions, search, typeFilter, sourceFilter]);

  const stats = useMemo(() => {
    const scopedTx =
      sourceFilter === "all"
        ? transactions
        : transactions.filter((t) => t._filename === sourceFilter);

    const totals = sumTransactionTotals(scopedTx);

    return {
      totalCredits: totals.totalCredits,
      totalDebits: totals.totalDebits,
      netFlow: totals.netFlow,
      totalTransactions: scopedTx.length,
      statementsProcessed: sourceFilter === "all" ? documents.length : 1,
    };
  }, [transactions, sourceFilter, documents.length]);

  const exportData = useMemo(
    () =>
      filtered.map((t) => ({
        Date: t.date || "",
        Description: t.description || "",
        Debit: t.debit ? String(t.debit) : "",
        Credit: t.credit ? String(t.credit) : "",
        Balance: t.balance ? String(t.balance) : "",
      })),
    [filtered]
  );

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
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Link href="/transactions/credits">
          <SummaryCard
            title="Total Credits"
            value={formatUSD(stats.totalCredits)}
            subtitle="All incoming amounts from statement"
            icon={<TrendingUp className="h-5 w-5" />}
            accentColor="bg-[var(--credit)]/10 text-[var(--credit)]"
          />
        </Link>
        <SummaryCard
          title="Total Debits"
          value={formatUSD(stats.totalDebits)}
          subtitle="All outgoing amounts from statement"
          icon={<TrendingDown className="h-5 w-5" />}
          accentColor="bg-[var(--debit)]/10 text-[var(--debit)]"
        />
        <SummaryCard
          title="Net Flow"
          value={formatUSD(stats.netFlow)}
          subtitle="Credits minus debits"
          icon={<Activity className="h-5 w-5" />}
          accentColor="bg-primary/10 text-primary"
        />
        <SummaryCard
          title="Transactions"
          value={String(stats.totalTransactions)}
          subtitle={
            sourceFilter === "all"
              ? `Across ${stats.statementsProcessed} statements`
              : "In this statement"
          }
          icon={<FileText className="h-5 w-5" />}
          accentColor="bg-[var(--chart-5)]/10 text-[var(--chart-5)]"
        />
      </div>

      {sourceFilter != "all" && (
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
            title="Customer Name"
            value={displayMeta(activeDocument?.customer_name)}
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
      )}

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
