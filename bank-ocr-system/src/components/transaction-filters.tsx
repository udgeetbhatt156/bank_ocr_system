"use client";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search } from "lucide-react";

interface TransactionFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  typeFilter: string;
  onTypeFilterChange: (value: string) => void;
  sourceFilter: string;
  onBankTypeFilterChange: (value: string) => void;
  bankTypeFilter: string;
  onSourceFilterChange: (value: string) => void;
  sources: string[];

}

export function TransactionFilters({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  bankTypeFilter,
  onBankTypeFilterChange,
  sourceFilter,
  onSourceFilterChange,
  sources,
}: TransactionFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id="transaction-search"
          placeholder="Search transactions..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 h-9"
        />
      </div>

      {/* Type filter */}
      <Select value={typeFilter} onValueChange={onTypeFilterChange}>
        <SelectTrigger id="type-filter" className="w-[140px] h-9">
          <SelectValue placeholder="All Types" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Types</SelectItem>
          <SelectItem value="credit">Credits Only</SelectItem>
          <SelectItem value="debit">Debits Only</SelectItem>
        </SelectContent>
      </Select>
   
      {/* Source filter */}
      {/* onValueChange={onSourceFilterChange} */}
      {sources.length > 1 && (
        <Select value={sourceFilter} onValueChange={onSourceFilterChange}>
          <SelectTrigger id="source-filter" className="w-[180px] h-9">
            <SelectValue placeholder="All Sources" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {sources.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
