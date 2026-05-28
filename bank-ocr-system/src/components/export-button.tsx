"use client";

import { useCallback } from "react";
import { saveAs } from "file-saver";
import * as XLSX from "xlsx";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Download, FileSpreadsheet, FileText } from "lucide-react";

interface ExportRow {
  Date: string;
  Description: string;
  Debit: string;
  Credit: string;
  Balance: string;
  // Reference: string;
  // Source: string;
}

interface ExportButtonProps {
  data: ExportRow[];
  filename?: string;
}

export function ExportButton({ data, filename = "transactions" }: ExportButtonProps) {
  const exportCSV = useCallback(() => {
    if (!data.length) return;
    const headers = Object.keys(data[0]);
    const csv = [
      headers.join(","),
      ...data.map((row) =>
        headers
          .map((h) => {
            const val = String(row[h as keyof ExportRow] || "");
            return val.includes(",") ? `"${val}"` : val;
          })
          .join(",")
      ),
    ].join("\n");

    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    saveAs(blob, `${filename}.csv`);
  }, [data, filename]);
  // console.log('new exported data:',data)
  const exportExcel = useCallback(() => {
    if (!data.length) return;
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Transactions");

    /* Style header row */
    const range = XLSX.utils.decode_range(ws["!ref"] || "A1");
    for (let c = range.s.c; c <= range.e.c; c++) {
      const addr = XLSX.utils.encode_cell({ r: 0, c });
      if (ws[addr]) ws[addr].s = { font: { bold: true } };
    }

    /* Set column widths */
    ws["!cols"] = [
      { wch: 12 }, // Date
      { wch: 40 }, // Description
      { wch: 14 }, // Debit
      { wch: 14 }, // Credit
      { wch: 14 }, // Balance
      { wch: 20 }, // Reference
      { wch: 20 }, // Source
    ];

    const buf = XLSX.write(wb, { bookType: "xlsx", type: "array" });
    const blob = new Blob([buf], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    saveAs(blob, `${filename}.xlsx`);
  }, [data, filename]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={exportCSV} className="gap-2">
          <FileText className="h-4 w-4" />
          Export as CSV
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportExcel} className="gap-2">
          <FileSpreadsheet className="h-4 w-4" />
          Export as Excel
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
