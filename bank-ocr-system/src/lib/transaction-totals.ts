import type { TransactionRecord } from "@/lib/api";
import { getRevenueStatus } from "@/lib/revenue-filter";

export function sumTransactionTotals(transactions: TransactionRecord[]) {
  let totalDebits = 0;
  let totalCredits = 0;

  for (const t of transactions) {
    totalDebits += Number(t.debit || 0);
    const cVal = Number(t.credit || 0);
    if (cVal > 0) {
      if (getRevenueStatus(t.description, cVal) === "revenue") {
        totalCredits += cVal;
      }
    }
  }

  return {
    totalDebits,
    totalCredits,
    netFlow: totalCredits - totalDebits,
  };
}
