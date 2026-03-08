"use client";

import React from "react";
import { format } from "date-fns";
import { motion, AnimatePresence } from "framer-motion";
import StatusBadge from "./StatusBadge";

interface Flight {
    id: string;
    flight_number: string;
    flight_date: string;
    direction: string;
    airport_code: string;
    airport_name: string;
    airline_code: string;
    airline_name: string;
    origin_city: string;
    destination_city: string;
    scheduled_time: string;
    estimated_time: string | null;
    status: string;
    status_detail: string | null;
    gate: string | null;
    terminal: string | null;
    belt: string | null;
    check_in_counter: string | null;
}

interface FlightTableProps {
    flights: Flight[];
    direction: "arrival" | "departure";
    isLoading: boolean;
}

// Separate component for rows to allow for memoization if needed, 
// and to reduce the overhead of re-rendering the whole table.
const FlightRow = React.memo(({ flight, isArrival, tableRowClass }: { flight: Flight; isArrival: boolean; tableRowClass: string }) => {
    const dateFormat = format(new Date(flight.scheduled_time), "dd.MM");
    const timeFormat = format(new Date(flight.scheduled_time), "HH:mm");
    const estTimeFormat = flight.estimated_time ? format(new Date(flight.estimated_time), "HH:mm") : null;

    const locInfo = isArrival
        ? (flight.belt || flight.terminal || "-")
        : (flight.gate || flight.check_in_counter || flight.terminal || "-");

    return (
        <motion.tr
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            className={tableRowClass}
        >
            <td className="py-2.5 px-6 font-mono text-sm font-bold text-slate-400 sticky left-0 bg-slate-900/90 backdrop-blur-md z-10 border-r border-slate-700/50">
                {dateFormat}
            </td>
            <td className="py-2.5 px-6 font-mono text-lg font-bold text-sky-100">
                {timeFormat}
                {estTimeFormat && (
                    <div className="text-[10px] font-sans font-medium text-amber-400 mt-0.5">
                        Tahmini: {estTimeFormat}
                    </div>
                )}
            </td>
            <td className="py-2.5 px-6 font-medium text-slate-300 hidden md:table-cell">
                {flight.airline_name || flight.airline_code || "Bilinmiyor"}
            </td>
            <td className="py-2.5 px-6 font-bold text-sky-200">
                {flight.flight_number}
            </td>
            <td className="py-2.5 px-6 text-base font-semibold text-white">
                {flight.origin_city}
            </td>
            <td className="py-2.5 px-6 text-base font-semibold text-sky-100/90">
                {flight.destination_city}
            </td>
            <td className="py-2.5 px-6 text-slate-400 hidden lg:table-cell">
                {flight.airport_name || flight.airport_code}
            </td>
            <td className="py-2.5 px-6 text-center font-bold text-slate-200 hidden sm:table-cell">
                <div className="bg-slate-800/80 rounded px-2 py-0.5 inline-block border border-slate-700 text-xs">
                    {locInfo}
                </div>
            </td>
            <td className="py-2.5 px-6 text-center">
                <StatusBadge
                    status={flight.status}
                    originalText={flight.status_detail}
                />
            </td>
        </motion.tr>
    );
});

FlightRow.displayName = "FlightRow";

export default function FlightTable({ flights, direction, isLoading }: FlightTableProps) {
    const isArrival = direction === "arrival";

    const glassPanelClass = "bg-slate-900/60 backdrop-blur-md border border-slate-700/50 shadow-xl";
    const headerRowClass = "bg-slate-800/80 text-slate-300 uppercase text-xs tracking-wider sticky top-0 z-10 backdrop-blur-sm border-b border-slate-700/50";
    const tableRowClass = "hover:bg-slate-800/40 transition-colors border-b border-slate-700/30 text-sm md:text-base group contain-intrinsic-size";

    if (isLoading) {
        return (
            <div className="flex justify-center items-center py-20 text-sky-400">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-400 shadow-[0_0_15px_rgba(56,189,248,0.4)]"></div>
            </div>
        );
    }

    if (flights.length === 0) {
        return (
            <div className={`${glassPanelClass} rounded-2xl p-12 text-center text-slate-400 mt-4`}>
                <span className="text-4xl mb-4 block">✈️</span>
                <p className="text-xl">Bu kriterlere uygun güncel uçuş bulunamadı.</p>
            </div>
        );
    }

    return (
        <div className={`${glassPanelClass} rounded-2xl overflow-hidden shadow-2xl backdrop-blur-xl bg-slate-900/40 transform-gpu`}>
            <div className="overflow-x-auto no-scrollbar">
                <table className="w-full text-left border-collapse table-fixed lg:table-auto">
                    <thead className={headerRowClass}>
                        <tr>
                            <th className="py-3 px-6 font-semibold w-[100px] sticky left-0 bg-slate-800 z-20 shadow-[2px_0_5px_rgba(0,0,0,0.3)]">TARİH</th>
                            <th className="py-3 px-6 font-semibold w-24">SAAT</th>
                            <th className="py-3 px-6 font-semibold hidden md:table-cell">HAVAYOLU</th>
                            <th className="py-3 px-6 font-semibold">UÇUŞ</th>
                            <th className="py-3 px-6 font-semibold">KALKIŞ</th>
                            <th className="py-3 px-6 font-semibold">VARIŞ</th>
                            <th className="py-3 px-6 font-semibold hidden lg:table-cell">HAVALİMANI</th>
                            <th className="py-3 px-6 font-semibold text-center hidden sm:table-cell w-28">KAPI / BAGAJ</th>
                            <th className="py-3 px-6 font-semibold text-center w-40">DURUM</th>
                        </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-700/30">
                        {flights.map((flight) => (
                            <FlightRow
                                key={flight.id}
                                flight={flight}
                                isArrival={isArrival}
                                tableRowClass={tableRowClass}
                            />
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
