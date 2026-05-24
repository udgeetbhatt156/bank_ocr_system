"use client";

import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import type { TransactionRecord } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ArrowUpDown,
} from "lucide-react";

type TxRow = TransactionRecord & { _filename: string };

interface TransactionTableProps {
  data: TxRow[];
}

function formatAmount(v: number | string | null, type: "credit" | "debit") {
  if (v === null || v === undefined) return "—";
  const num = Number(v);
  if (isNaN(num) || num === 0) return "—";
  return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const columns: ColumnDef<TxRow>[] = [
  {
    accessorKey: "date",
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 gap-1 text-xs font-semibold uppercase"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Date <ArrowUpDown className="h-3 w-3" />
      </Button>
    ),
    cell: ({ getValue }) => (
      <span className="whitespace-nowrap text-sm">
        {(getValue() as string) || "—"}
      </span>
    ),
  },
  {
    accessorKey: "description",
    header: () => (
      <span className="text-xs font-semibold uppercase">Description</span>
    ),
    cell: ({ getValue }) => (
      <span
        className="block max-w-[280px] truncate text-sm"
        title={getValue() as string}
      >
        {(getValue() as string) || "—"}
      </span>
    ),
  },
  {
    accessorKey: "debit",
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 gap-1 text-xs font-semibold uppercase"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Debit <ArrowUpDown className="h-3 w-3" />
      </Button>
    ),
    cell: ({ getValue }) => {
      const val = getValue() as number | null;
      const display = formatAmount(val, "debit");
      return (
        <span
          className={`whitespace-nowrap text-sm font-medium ${
            display !== "—" ? "text-[var(--debit)]" : "text-muted-foreground"
          }`}
        >
          {display}
        </span>
      );
    },
  },
  {
    accessorKey: "credit",
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 gap-1 text-xs font-semibold uppercase"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Credit <ArrowUpDown className="h-3 w-3" />
      </Button>
    ),
    cell: ({ getValue }) => {
      const val = getValue() as number | null;
      const display = formatAmount(val, "credit");
      return (
        <span
          className={`whitespace-nowrap text-sm font-medium ${
            display !== "—" ? "text-[var(--credit)]" : "text-muted-foreground"
          }`}
        >
          {display}
        </span>
      );
    },
  },
  {
    accessorKey: "balance",
    header: () => (
      <span className="text-xs font-semibold uppercase">Balance</span>
    ),
    cell: ({ getValue }) => {
      const val = getValue() as number | null;
      if (val === null || val === undefined) return <span className="text-sm text-muted-foreground">—</span>;
      return (
        <span className="whitespace-nowrap text-sm text-foreground">
          ₹{Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      );
    },
  },
  {
    accessorKey: "reference",
    header: () => (
      <span className="text-xs font-semibold uppercase">Reference</span>
    ),
    cell: ({ getValue }) => {
      const val = getValue() as string | null;
      if (!val) return <span className="text-sm text-muted-foreground">—</span>;
      return (
        <Badge variant="secondary" className="text-xs font-mono">
          {val}
        </Badge>
      );
    },
  },
  {
    accessorKey: "_filename",
    header: () => (
      <span className="text-xs font-semibold uppercase">Source</span>
    ),
    cell: ({ getValue }) => (
      <span className="block max-w-[160px] truncate text-xs text-muted-foreground">
        {getValue() as string}
      </span>
    ),
  },
];

export function TransactionTable({ data }: TransactionTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: { pageSize: 15 },
    },
  });

  const pageIndex = table.getState().pagination.pageIndex;
  const pageCount = table.getPageCount();

  /* Totals row */
  const totals = useMemo(() => {
    let debit = 0;
    let credit = 0;
    for (const row of data) {
      debit += Number(row.debit || 0);
      credit += Number(row.credit || 0);
    }
    return { debit, credit };
  }, [data]);

  if (!data.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No transactions to display. Upload statements first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((header) => (
                  <TableHead key={header.id} className="h-10">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} className="group">
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className="py-2.5">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}

            {/* Totals row */}
            <TableRow className="bg-muted/30 font-semibold hover:bg-muted/40">
              <TableCell className="py-2.5 text-sm">Total</TableCell>
              <TableCell />
              <TableCell className="py-2.5 text-sm text-[var(--debit)]">
                ₹{totals.debit.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </TableCell>
              <TableCell className="py-2.5 text-sm text-[var(--credit)]">
                ₹{totals.credit.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </TableCell>
              <TableCell />
              <TableCell />
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-1">
        <p className="text-xs text-muted-foreground">
          Showing {table.getRowModel().rows.length} of {data.length}{" "}
          transactions
        </p>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="flex h-8 items-center px-3 text-xs text-muted-foreground">
            {pageIndex + 1} / {pageCount || 1}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
          >
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
