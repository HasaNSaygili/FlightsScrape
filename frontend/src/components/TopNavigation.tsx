"use client";

import React from "react";
import { PlaneLanding, PlaneTakeoff, Search } from "lucide-react";

interface TopNavigationProps {
    direction: "arrival" | "departure";
    setDirection: (dir: "arrival" | "departure") => void;
    searchQuery: string;
    setSearchQuery: (q: string) => void;
    selectedAirport: string;
    setSelectedAirport: (code: string) => void;
}

// Türkiye'deki majör havalimanları listesi
const AIRPORTS = [
    { code: "ALL", name: "Tüm Türkiye" },
    { code: "IST", name: "İstanbul Hvl. (IST)" },
    { code: "SAW", name: "Sabiha Gökçen (SAW)" },
    { code: "ESB", name: "Ankara Esenboğa (ESB)" },
    { code: "ADB", name: "İzmir Adnan Menderes (ADB)" },
    { code: "AYT", name: "Antalya Hvl. (AYT)" },
    { code: "DLM", name: "Dalaman (DLM)" },
    { code: "BJV", name: "Bodrum Milas (BJV)" },
    { code: "COV", name: "Çukurova (COV)" },
    { code: "KZR", name: "Zafer (KZR)" },
    { code: "ONQ", name: "Zonguldak Çaycuma (ONQ)" },
    { code: "AOE", name: "Eskişehir H. Polatkan (AOE)" },
];

export default function TopNavigation({
    direction,
    setDirection,
    searchQuery,
    setSearchQuery,
    selectedAirport,
    setSelectedAirport,
}: TopNavigationProps) {
    return (
        <div className="bg-slate-900/60 backdrop-blur-md border border-slate-700/50 shadow-xl rounded-2xl p-4 mb-6 flex flex-col lg:flex-row gap-4 justify-between items-center w-full">

            {/* Direction Toggle */}
            <div className="flex bg-slate-950/50 p-1 rounded-xl border border-slate-700/50 w-full lg:w-auto">
                <button
                    onClick={() => setDirection("arrival")}
                    className={`flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all duration-300 ${direction === "arrival"
                        ? "bg-sky-500/20 text-sky-400 shadow-[0_0_15px_rgba(14,165,233,0.3)]"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                        }`}
                >
                    <PlaneLanding className="w-5 h-5" />
                    Gelişler
                </button>
                <button
                    onClick={() => setDirection("departure")}
                    className={`flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all duration-300 ${direction === "departure"
                        ? "bg-amber-500/20 text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                        }`}
                >
                    <PlaneTakeoff className="w-5 h-5" />
                    Gidişler
                </button>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 w-full lg:w-auto flex-1 justify-end">
                {/* Airport Selector */}
                <select
                    value={selectedAirport}
                    onChange={(e) => setSelectedAirport(e.target.value)}
                    className="bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-sky-500/50 transition-all font-medium appearance-none min-w-[220px]"
                >
                    {AIRPORTS.map((apt) => (
                        <option key={apt.code} value={apt.code}>
                            {apt.name}
                        </option>
                    ))}
                </select>

                {/* Search Box */}
                <div className="relative w-full sm:max-w-xs">
                    <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                        <Search className="h-5 w-5 text-slate-400" />
                    </div>
                    <input
                        type="text"
                        placeholder="Uçuş no, Şehir veya Havayolu"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="bg-slate-800 border border-slate-700 text-slate-200 rounded-xl w-full pl-11 pr-4 py-3 outline-none focus:ring-2 focus:ring-sky-500/50 transition-all font-medium placeholder:text-slate-500"
                    />
                </div>
            </div>
        </div>
    );
}
