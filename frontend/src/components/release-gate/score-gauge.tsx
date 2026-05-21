"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";

interface ScoreGaugeProps {
  score: number; // 0-1
  label?: string;
}

function getScoreColor(score: number): string {
  if (score < 0.5) return "#ef4444"; // red-500
  if (score < 0.7) return "#f59e0b"; // amber-500
  if (score < 0.8) return "#eab308"; // yellow-500
  return "#22c55e"; // green-500
}

function getScoreGradient(score: number): string {
  if (score < 0.5) return "from-red-500 to-red-600";
  if (score < 0.7) return "from-amber-400 to-amber-500";
  if (score < 0.8) return "from-yellow-400 to-yellow-500";
  return "from-green-400 to-green-500";
}

export function ScoreGauge({ score, label = "Release Score" }: ScoreGaugeProps) {
  const [displayScore, setDisplayScore] = useState(0);

  useEffect(() => {
    setDisplayScore(score);
  }, [score]);

  // SVG arc geometry for a semicircle
  const radius = 80;
  const strokeWidth = 14;
  const cx = 110;
  const cy = 110;
  // Full arc circumference for the semicircle
  const circumference = Math.PI * radius; // half circle

  // Convert score (0-1) to stroke-dashoffset
  const fillLength = displayScore * circumference;
  const dashOffset = circumference - fillLength;

  const trackColor = "#e5e7eb"; // gray-200
  const fillColor = getScoreColor(displayScore);

  // Semicircle going from 180° to 360° (i.e., 180°→0° the long way clockwise through top)
  // Let's define the arc from 180 to 0 (clockwise through top = 180 degree sweep)
  const sStart = 180; // degrees from top = left point
  const sEnd = 360;   // = 0, right point

  function arcPoint(deg: number, r: number) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  const pStart = arcPoint(sStart, radius);
  const pEnd = arcPoint(sEnd, radius);

  const semicirclePath = `M ${pStart.x} ${pStart.y} A ${radius} ${radius} 0 1 1 ${pEnd.x} ${pEnd.y}`;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: 220, height: 130 }}>
        <svg
          width={220}
          height={130}
          viewBox="0 0 220 130"
          style={{ overflow: "visible" }}
        >
          {/* Track (gray background arc) */}
          <path
            d={semicirclePath}
            fill="none"
            stroke={trackColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
          {/* Animated fill arc */}
          <motion.path
            d={semicirclePath}
            fill="none"
            stroke={fillColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          />
        </svg>

        {/* Score number centered in the semicircle */}
        <div
          className="absolute inset-0 flex flex-col items-center justify-end pb-1"
        >
          <motion.span
            className={`text-3xl font-bold bg-gradient-to-br ${getScoreGradient(displayScore)} bg-clip-text text-transparent`}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.4, ease: "backOut" }}
          >
            {(displayScore * 100).toFixed(0)}
          </motion.span>
          <span className="text-xs text-muted-foreground font-medium">/ 100</span>
        </div>
      </div>

      <p className="text-sm font-medium text-muted-foreground">{label}</p>
    </div>
  );
}
