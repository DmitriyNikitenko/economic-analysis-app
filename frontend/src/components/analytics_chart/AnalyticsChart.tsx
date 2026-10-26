import { useEffect, useRef } from "react";
import {
  Chart,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from "chart.js";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend
);

export default function AnalyticsChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const chart = new Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: ["Bank", "Company", "Population"],
        datasets: [
          {
            label: "Illustrative centrality",
            data: [0.8, 0.65, 0.35],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            max: 1,
          },
        },
      },
    });

    return () => chart.destroy();
  }, []);

  return (
    <div style={{ height: 300, position: "relative" }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
