"use client";

import React, { useState, useEffect, useMemo } from "react";
import TopNavigation from "@/components/TopNavigation";
import FlightTable from "@/components/FlightTable";
import { supabase } from "@/lib/supabase";
import { ChevronLeft, ChevronRight } from "lucide-react";

export default function Home() {
  const [direction, setDirection] = useState<"arrival" | "departure">("departure");
  const [airportCode, setAirportCode] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [flights, setFlights] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 20;
  const refreshTimeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const fetchFlights = async (showLoading = true) => {
    if (showLoading) setIsLoading(true);

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 2);

    let query = supabase
      .from("flights")
      .select("*")
      .eq("direction", direction)
      .gte("scheduled_time", today.toISOString())
      .lte("scheduled_time", tomorrow.toISOString())
      .order("scheduled_time", { ascending: true })
      .order("estimated_time", { ascending: true, nullsFirst: true })
      .limit(300);

    if (airportCode !== "ALL") {
      query = query.eq("airport_code", airportCode);
    }

    const { data, error } = await query;

    if (error) {
      console.error("Error fetching flights:", error);
    } else {
      setFlights(data || []);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    // Initial fetch for filter/direction change (immediate)
    fetchFlights(true);

    // Debounced refresh for real-time updates
    const debouncedRefresh = () => {
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = setTimeout(() => {
        fetchFlights(false); // Background update, no spinner
      }, 5000); // 5 second buffer to batch scraper updates
    };

    const channel = supabase
      .channel(`fids_realtime_${direction}_${airportCode}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "flights" },
        () => {
          debouncedRefresh();
        }
      )
      .subscribe();

    return () => {
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current);
      supabase.removeChannel(channel);
    };
  }, [direction, airportCode]);

  // Client-side text filtering logic
  const filteredFlights = useMemo(() => {
    let result = flights;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((f) =>
        (f.flight_number && f.flight_number.toLowerCase().includes(q)) ||
        (f.origin_city && f.origin_city.toLowerCase().includes(q)) ||
        (f.destination_city && f.destination_city.toLowerCase().includes(q)) ||
        (f.airline_name && f.airline_name.toLowerCase().includes(q))
      );
    }
    return result;
  }, [flights, searchQuery]);

  // Pagination logic
  const totalPages = Math.ceil(filteredFlights.length / itemsPerPage);
  const currentFlights = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredFlights.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredFlights, currentPage]);

  useEffect(() => {
    setCurrentPage(1); // Reset to page 1 when filters change
  }, [direction, airportCode, searchQuery]);

  return (
    <div className="flex flex-col gap-2 relative">
      <div className="mb-4">
        <h1 className="text-4xl md:text-5xl font-black bg-gradient-to-r from-sky-400 to-indigo-400 text-transparent bg-clip-text drop-shadow-[0_0_15px_rgba(56,189,248,0.4)]">
          Live FIDS Turkey
        </h1>
        <p className="text-slate-400 font-medium tracking-wide mt-2">
          Gerçek Zamanlı Uçuş Bilgi Sistemi
        </p>
      </div>

      <TopNavigation
        direction={direction}
        setDirection={setDirection}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        selectedAirport={airportCode}
        setSelectedAirport={setAirportCode}
      />

      <FlightTable
        flights={currentFlights}
        direction={direction}
        isLoading={isLoading}
      />

      {/* Pagination Controls */}
      {!isLoading && totalPages > 1 && (
        <div className="flex justify-center items-center gap-4 mt-6">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-3 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>

          <span className="text-slate-400 font-bold">
            Sayfa <span className="text-sky-400">{currentPage}</span> / {totalPages}
          </span>

          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="p-3 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <ChevronRight className="w-6 h-6" />
          </button>
        </div>
      )}
    </div>
  );
}
