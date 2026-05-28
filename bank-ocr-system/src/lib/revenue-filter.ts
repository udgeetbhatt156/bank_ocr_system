import type { TransactionRecord } from "@/lib/api";

export type RevenueStatus = "revenue" | "deduction";

export type RevenueClassification = {
  transaction_type: "credit" | "debit" | "unknown";
  revenue_status: RevenueStatus | null;
  revenue_deduction_reason: string | null;
  revenue_rule: string | null;
  adjusted_revenue_amount: number | null;
};

const deductionRules: Array<{ reason: string; patterns: RegExp[] }> = [
  {
    reason: "Financing & Loans",
    patterns: [
      /\badvances?\b/i,
      /\b(?:loc|line\s+of\s+credit|olb|occ)\b/i,
      /\bloan\b/i,
      /\blender\b/i,
      /\bequipment\s+finance\b/i,
      /\bnextgear\b/i,
      /\bcashflow\s+funding\b/i,
      /\basset\s+lease\b/i,
      /\bpersonal\s+loans?\b/i,
      /\boverdraft\b/i,
      /\bod\b/i,
      /\bprovisional\s+credit\b/i,
      /\btemporary\s+credit\b/i,
    ],
  },
  {
    reason: "Internal Transfers & Linked Accounts",
    patterns: [
      /\ba2a\b/i,
      /\baccount\s+to\s+account\b/i,
      /\bcash\s*m(?:ana)?g?m?nt\b/i,
      /\bcol\s+xfer\b/i,
      /\bdeposit\s+transfer\b/i,
      /\bfrom\s+(?:acct|account)\s*(?:x+|\*+)?\d{3,}\b/i,
      /\b(?:acct|account)\s*(?:x+|\*+)?\d{3,}\b/i,
      /\bpayroll\s+account\b/i,
      /\bfunds?\s+transfers?\b/i,
      /\btransfer(?:s|red)?\b/i,
      /\bxfr\b/i,
      /\bxfer\b/i,
      /\bmobile\s+banking\s+transfer\b/i,
      /\bonline\s+banking\s+transfer\b/i,
      /\bonline\s+xfer\b/i,
      /\bonline\s+transfer\b/i,
      /\bfrom\s+(?:chk|checking|savings|mma|payroll)\b/i,
      /\bpc\s+transfer\b/i,
      /\btelephone\s+transfer\b/i,
      /\btele\s+transfer\b/i,
      /\bacorns\b/i,
      /\bmoney\s+transfer\b/i,
    ],
  },
  {
    reason: "Banking Corrections, Reversals & Perks",
    patterns: [
      /\bcredit\s+adjust(?:ment)?\b/i,
      /\bwithdrawal\s+adjustment\b/i,
      /\bdebit\s+card\s+credit\s+voucher\b/i,
      /\bdeposit\s+correction\b/i,
      /\bshare\s+draft\s+correction\b/i,
      /\berror\s+deposit\b/i,
      /\bmisposted\b/i,
      /\bnsf\b/i,
      /\breturns?\b/i,
      /\brtn\b/i,
      /\bret\b/i,
      /\bcash\s*back\b/i,
      /\brewards?\b/i,
      /\brebates?\b/i,
      /\brbt\b/i,
      /\bdividends?\b/i,
      /\binterest\b/i,
      /\brefunds?\b/i,
      /\btreas(?:ury)?\b/i,
      /\bvouchers?\b/i,
      /\bfees?\b/i,
      /\bfee\s+reversal\b/i,
      /\btrial\s+deposit\b/i,
      /\bverify\s+deposit\b/i,
    ],
  },
];

const wireDeductionPatterns = [
  /\bmerchant\b/i,
  /\bloc\b/i,
  /\bline\s+of\s+credit\b/i,
  /\blender\b/i,
  /\bloan\b/i,
  /\bfunding\b/i,
  /\bfinance\b/i,
];

export function classifyTransactionRevenue(
  transaction: Pick<
    TransactionRecord,
    | "description"
    | "credit"
    | "debit"
    | "revenue_status"
    | "revenue_deduction_reason"
    | "revenue_rule"
    | "adjusted_revenue_amount"
  >
): RevenueClassification {
  const credit = Number(transaction.credit || 0);
  const debit = Number(transaction.debit || 0);

  if (credit <= 0) {
    return {
      transaction_type: debit > 0 ? "debit" : "unknown",
      revenue_status: null,
      revenue_deduction_reason: null,
      revenue_rule: null,
      adjusted_revenue_amount: null,
    };
  }

  if (transaction.revenue_status) {
    const status = transaction.revenue_status;
    return {
      transaction_type: "credit",
      revenue_status: status,
      revenue_deduction_reason: transaction.revenue_deduction_reason ?? null,
      revenue_rule: transaction.revenue_rule ?? null,
      adjusted_revenue_amount:
        transaction.adjusted_revenue_amount ?? (status === "revenue" ? credit : 0),
    };
  }

  const description = (transaction.description || "").toLowerCase();

  if (/\bwire\b/i.test(description)) {
    const matched = wireDeductionPatterns.find((pattern) =>
      pattern.test(description)
    );
    if (matched) {
      return {
        transaction_type: "credit",
        revenue_status: "deduction",
        revenue_deduction_reason: "Special Conditional Rule: Wire Deposits",
        revenue_rule: matched.source,
        adjusted_revenue_amount: 0,
      };
    }

    return {
      transaction_type: "credit",
      revenue_status: "revenue",
      revenue_deduction_reason: null,
      revenue_rule: "standard business wire kept as revenue",
      adjusted_revenue_amount: credit,
    };
  }

  for (const rule of deductionRules) {
    const matched = rule.patterns.find((pattern) => pattern.test(description));
    if (matched) {
      return {
        transaction_type: "credit",
        revenue_status: "deduction",
        revenue_deduction_reason: rule.reason,
        revenue_rule: matched.source,
        adjusted_revenue_amount: 0,
      };
    }
  }

  return {
    transaction_type: "credit",
    revenue_status: "revenue",
    revenue_deduction_reason: null,
    revenue_rule: null,
    adjusted_revenue_amount: credit,
  };
}

export function getRevenueSnapshot(transactions: TransactionRecord[]) {
  let rawCredits = 0;
  let adjustedRevenue = 0;
  let revenueDeductions = 0;
  let totalDebits = 0;

  for (const transaction of transactions) {
    const credit = Number(transaction.credit || 0);
    const debit = Number(transaction.debit || 0);
    totalDebits += debit;

    if (credit > 0) {
      rawCredits += credit;
      const classification = classifyTransactionRevenue(transaction);
      if (classification.revenue_status === "deduction") {
        revenueDeductions += credit;
      } else {
        adjustedRevenue += credit;
      }
    }
  }

  return {
    rawCredits,
    adjustedRevenue,
    revenueDeductions,
    totalDebits,
    netFlow: adjustedRevenue - totalDebits,
  };
}
