import type { TransactionRecord } from "@/lib/api";

export function sumTransactionTotals(transactions: TransactionRecord[]) {
  let totalDebits = 0;
  let totalCredits = 0;

  for (const t of transactions) {
    totalDebits += Number(t.debit || 0);
    totalCredits += Number(t.credit || 0);
  }

  return {
    totalDebits,
    totalCredits,
    netFlow: totalCredits - totalDebits,
  };
}
