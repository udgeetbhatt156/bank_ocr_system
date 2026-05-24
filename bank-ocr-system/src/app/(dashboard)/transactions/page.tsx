"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useOcrStore } from "@/store/ocr-store";
import { TransactionTable } from "@/components/transaction-table";
import { TransactionFilters } from "@/components/transaction-filters";
import { ExportButton } from "@/components/export-button";
import { SummaryCard } from "@/components/summary-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  FileText,
  Upload,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";

function formatINR(value: number) {
  if (value === 0) return "₹0.00";
  return `₹${value.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function TransactionsPage() {
  const { documents, allTransactions, summaryStats } = useOcrStore();
  const transactions = allTransactions();
  const stats = summaryStats();

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  /* Unique source filenames */
  const sources = useMemo(
    () => [...new Set(transactions.map((t) => t._filename))],
    [transactions]
  );

  /* Filter logic */
  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      // Search
      if (search) {
        const q = search.toLowerCase();
        const matchesSearch =
          (t.description || "").toLowerCase().includes(q) ||
          (t.date || "").toLowerCase().includes(q) ||
          (t.reference || "").toLowerCase().includes(q) ||
          (t._filename || "").toLowerCase().includes(q);
        if (!matchesSearch) return false;
      }

      // Type
      if (typeFilter === "credit" && !Number(t.credit)) return false;
      if (typeFilter === "debit" && !Number(t.debit)) return false;

      // Source
      if (sourceFilter !== "all" && t._filename !== sourceFilter) return false;

      return true;
    });
  }, [transactions, search, typeFilter, sourceFilter]);

  /* Export data shape */
  const exportData = useMemo(
    () =>
      filtered.map((t) => ({
        Date: t.date || "",
        Description: t.description || "",
        Debit: t.debit ? String(t.debit) : "",
        Credit: t.credit ? String(t.credit) : "",
        Balance: t.balance ? String(t.balance) : "",
        Reference: t.reference || "",
        Source: t._filename || "",
      })),
    [filtered]
  );

  /* Per-document tabs */
  const tabItems = useMemo(() => {
    const items = [{ value: "all", label: "All Transactions" }];
    documents.forEach((doc, idx) => {
      // Use index-prefixed value so duplicate filenames never collide
      const tabValue = `doc-${idx}-${doc.filename}`;
      items.push({
        value: tabValue,
        label: doc.filename.length > 20
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
      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          title="Total Credits"
          value={formatINR(stats.totalCredits)}
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor="bg-[var(--credit)]/10 text-[var(--credit)]"
        />
        <SummaryCard
          title="Total Debits"
          value={formatINR(stats.totalDebits)}
          icon={<TrendingDown className="h-5 w-5" />}
          accentColor="bg-[var(--debit)]/10 text-[var(--debit)]"
        />
        <SummaryCard
          title="Net Flow"
          value={formatINR(stats.netFlow)}
          subtitle={`${stats.totalTransactions} transactions across ${stats.statementsProcessed} statements`}
          icon={<Activity className="h-5 w-5" />}
          accentColor="bg-primary/10 text-primary"
        />
      </div>

      {/* Tabs for per-document / all */}
      <Tabs
        defaultValue="all"
        onValueChange={(val) => {
          if (val === "all") {
            setSourceFilter("all");
          } else {
            // Strip the "doc-N-" prefix to get the actual filename
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

        {/* Filters */}
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

        {/* Table content — same table for all tabs, filtered by source */}
        <div className="mt-4">
          <TransactionTable data={filtered} />
        </div>
      </Tabs>
    </div>
  );
}
