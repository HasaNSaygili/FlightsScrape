import React from "react";

type FlightStatus =
    | "scheduled"
    | "boarding"
    | "departed"
    | "arrived"
    | "landed"
    | "delayed"
    | "cancelled"
    | "on_time"
    | "diverted"
    | "unknown"
    | string;

interface StatusBadgeProps {
    status: FlightStatus;
    originalText?: string | null;
}

export default function StatusBadge({ status, originalText }: StatusBadgeProps) {
    const s = status?.toLowerCase() || "unknown";

    let classes = "text-indigo-400 bg-indigo-400/20 border border-indigo-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
    let label = (originalText || status || "PLANLANDI").toUpperCase();

    if (s === "landed" || s === "arrived") {
        classes = "text-emerald-400 bg-emerald-400/20 border border-emerald-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px] shadow-[0_0_10px_rgba(52,211,153,0.1)]";
        label = "İNDİ / ARRIVED";
    } else if (s === "on_time") {
        classes = "text-emerald-400 bg-emerald-400/20 border border-emerald-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "ZAMANINDA";
    } else if (s === "delayed") {
        classes = "text-amber-400 bg-amber-400/20 border border-amber-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = originalText ? originalText.toUpperCase() : "GECİKMELİ";
    } else if (s === "cancelled") {
        classes = "text-rose-400 bg-rose-400/20 border border-rose-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "İPTAL / CANCELLED";
    } else if (s === "departed") {
        classes = "text-sky-400 bg-sky-400/20 border border-sky-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "KALKTI / DEPARTED";
    } else if (s === "boarding") {
        classes = "text-sky-400 bg-sky-400/20 border border-sky-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "BOARDING";
    } else if (s === "scheduled") {
        classes = "text-indigo-400 bg-indigo-400/20 border border-indigo-400/30 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "PLANLANDI";
    } else if (s === "unknown") {
        classes = "text-slate-300 bg-slate-700/40 border border-slate-600/50 px-3 py-1.5 rounded-md inline-block font-bold min-w-[120px]";
        label = "BİLİNMİYOR";
    }

    return (
        <span className={`${classes} whitespace-nowrap text-center text-[10px] sm:text-xs tracking-wider ring-1 ring-inset`}>
            {label}
        </span>
    );
}
