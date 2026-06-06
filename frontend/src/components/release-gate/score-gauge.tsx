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

  // Top-semicircle gauge geometry. The arc goes from the left point
  // (cx - r, cy) clockwise through the top apex (cx, cy - r) to the right
  // point (cx + r, cy). With cy = radius + strokeWidth/2 the arc just fits
  // inside the SVG box, so the previous overflow into sibling cards is gone.
  const radius = 80;
  const strokeWidth = 14;
  const cx = 110;
  const cy = radius + strokeWidth / 2; // = 87 — arc bottom edge at y=cy
  const svgWidth = 220;
  const svgHeight = cy + strokeWidth / 2 + 8; // = 102, plus tiny visual pad

  const circumference = Math.PI * radius; // half-circle arc length
  const fillLength = displayScore * circumference;
  const dashOffset = circumference - fillLength;

  const trackColor = "#e5e7eb"; // gray-200
  const fillColor = getScoreColor(displayScore);

  // SVG sweep-flag=1 with y-down means visual clockwise → goes through TOP
  const semicirclePath = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="relative"
        style={{ width: svgWidth, height: svgHeight }}
      >
        <svg
          width={svgWidth}
          height={svgHeight}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
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

        {/* Score number tucked under the arc apex */}
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center pb-1">
          <motion.span
            className={`text-3xl font-bold bg-gradient-to-br ${getScoreGradient(displayScore)} bg-clip-text text-transparent leading-none`}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.4, ease: "backOut" }}
          >
            {(displayScore * 100).toFixed(0)}
          </motion.span>
          <span className="text-[10px] text-muted-foreground font-medium mt-0.5">
            / 100
          </span>
        </div>
      </div>

      <p className="text-sm font-medium text-muted-foreground">{label}</p>
    </div>
  );
}
