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
import type { ColumnVisibility, TransactionRecord } from "@/lib/api";
import { formatUSD } from "@/lib/currency";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
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
  typeFilter?: string;
}

function formatAmount(v: number | string | null) {
  if (v === null || v === undefined) return "—";
  const num = Number(v);
  if (isNaN(num) || num === 0) return "—";
  return formatUSD(num);
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
        className="block min-w-[260px] max-w-[520px] whitespace-normal break-words text-sm"
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
      const display = formatAmount(val);
      return (
        <span
          className={`whitespace-nowrap text-sm font-medium ${display !== "—" ? "text-[var(--debit)]" : "text-muted-foreground"
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
      const display = formatAmount(val);
      return (
        <span
          className={`whitespace-nowrap text-sm font-medium ${display !== "—" ? "text-[var(--credit)]" : "text-muted-foreground"
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
          {formatUSD(Number(val))}
        </span>
      );
    },
  },
  // {
  //   accessorKey: "_filename",
  //   header: () => (
  //     <span className="text-xs font-semibold uppercase">Source</span>
  //   ),
  //   cell: ({ getValue }) => (
  //     <span className="block max-w-[160px] truncate text-xs text-muted-foreground">
  //       {getValue() as string}
  //     </span>
  //   ),
  // },
];

export function TransactionTable({ data, typeFilter = "all" }: TransactionTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

  /* Hide debit column when filtering credits-only, and vice versa */
  const columnVisibility: ColumnVisibility = useMemo(() => {
    if (typeFilter === "credit") return { debit: false };
    if (typeFilter === "debit") return { credit: false };
    return {};
  }, [typeFilter]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility },
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
  // console.log('Datatatat', data[0])
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

            {/* Totals row — adapts to visible columns */}
            <TableRow className="bg-muted/30 font-semibold hover:bg-muted/40">
              <TableCell className="py-2.5 text-sm">Total</TableCell>
              <TableCell />
              {typeFilter !== "credit" && (
                <TableCell className="py-2.5 text-sm text-[var(--debit)]">
                  {formatUSD(totals.debit)}
                </TableCell>
              )}
              {typeFilter !== "debit" && (
                <TableCell className="py-2.5 text-sm text-[var(--credit)]">
                  {formatUSD(totals.credit)}
                </TableCell>
              )}
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
