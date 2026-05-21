"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SupportTicket, TicketCategory, PaginatedData } from "@/lib/types";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface ScenarioSelectorProps {
  onSelect: (ticket: SupportTicket) => void;
  disabled?: boolean;
}

const CATEGORY_LABELS: Record<TicketCategory, string> = {
  refund: "Refund",
  billing: "Billing",
  admin_access: "Admin Access",
  data_export: "Data Export",
  privacy: "Privacy",
  legal: "Legal",
  outage_credit: "Outage Credit",
  ambiguous: "Ambiguous",
};

const CATEGORY_COLORS: Record<TicketCategory, string> = {
  refund: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  billing: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  admin_access: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  data_export: "bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300",
  privacy: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  legal: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  outage_credit: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  ambiguous: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
};

export function ScenarioSelector({ onSelect, disabled }: ScenarioSelectorProps) {
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    api.tickets.list().then((res) => {
      if (cancelled) return;
      if (res.ok && res.data) {
        const data = res.data as PaginatedData<SupportTicket> | SupportTicket[];
        const items = Array.isArray(data) ? data : (data as PaginatedData<SupportTicket>).items ?? [];
        setTickets(items);
      }
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const grouped = tickets.reduce<Record<string, SupportTicket[]>>((acc, ticket) => {
    const cat = ticket.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(ticket);
    return acc;
  }, {});

  const handleChange = (value: string) => {
    setSelectedId(value);
    const ticket = tickets.find((t) => t.ticket_id === value);
    if (ticket) onSelect(ticket);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <Select
        value={selectedId}
        onValueChange={handleChange}
        disabled={disabled || tickets.length === 0}
      >
        <SelectTrigger className="w-[420px]">
          <SelectValue
            placeholder={
              tickets.length === 0
                ? "No tickets available — seed demo data first"
                : "Select a support ticket scenario..."
            }
          />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(grouped).map(([category, items]) => (
            <SelectGroup key={category}>
              <SelectLabel className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs font-medium border-transparent",
                    CATEGORY_COLORS[category as TicketCategory]
                  )}
                >
                  {CATEGORY_LABELS[category as TicketCategory] ?? category}
                </Badge>
              </SelectLabel>
              {items.map((ticket) => (
                <SelectItem key={ticket.ticket_id} value={ticket.ticket_id}>
                  <span className="truncate">{ticket.subject}</span>
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>

      {selectedId && (
        <Badge
          variant="outline"
          className={cn(
            "shrink-0 text-xs border-transparent",
            CATEGORY_COLORS[
              tickets.find((t) => t.ticket_id === selectedId)
                ?.category as TicketCategory
            ] ?? ""
          )}
        >
          {CATEGORY_LABELS[
            tickets.find((t) => t.ticket_id === selectedId)
              ?.category as TicketCategory
          ] ?? ""}
        </Badge>
      )}
    </div>
  );
}
