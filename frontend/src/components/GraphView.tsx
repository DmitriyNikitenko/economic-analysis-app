import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

export default function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,

      elements: [
        {
          data: {
            id: "bank-1",
            label: "Bank",
            type: "bank",
          },
        },
        {
          data: {
            id: "company-1",
            label: "Company",
            type: "company",
          },
        },
        {
          data: {
            id: "population-1",
            label: "Population",
            type: "population",
          },
        },
        {
          data: {
            id: "money-edge",
            source: "bank-1",
            target: "company-1",
            label: "Money",
          },
        },
        {
          data: {
            id: "labor-edge",
            source: "population-1",
            target: "company-1",
            label: "Labor",
          },
        },
      ],

      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#2563eb",
            color: "#222",
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 30,
            height: 30,
          },
        },
        {
          selector: 'node[type = "bank"]',
          style: { "background-color": "#16a34a" },
        },
        {
          selector: 'node[type = "population"]',
          style: { "background-color": "#d97706" },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
      ],

      layout: {
        name: "cose",
        animate: false,
      },
    });

    cy.on("tap", "node", (event) => {
      console.log("Selected graph node:", event.target.data());
    });

    return () => cy.destroy();
  }, []);

  return <div ref={containerRef} style={{ height: 400, width: "100%" }} />;
}