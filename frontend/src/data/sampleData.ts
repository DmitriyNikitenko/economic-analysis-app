import type { FeatureCollection, Point } from "geojson";

export const entitiesGeoJSON: FeatureCollection<
  Point,
  { name: string; type: string; capacity: number }
> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "bank-1",
      geometry: {
        type: "Point",
        coordinates: [2.3522, 48.8566],
      },
      properties: {
        name: "Sample Bank",
        type: "bank",
        capacity: 5000000,
      },
    },
    {
      type: "Feature",
      id: "company-1",
      geometry: {
        type: "Point",
        coordinates: [2.3622, 48.8616],
      },
      properties: {
        name: "Sample Company",
        type: "company",
        capacity: 120,
      },
    },
    {
      type: "Feature",
      id: "settlement-1",
      geometry: {
        type: "Point",
        coordinates: [2.3422, 48.8516],
      },
      properties: {
        name: "Sample Settlement",
        type: "population",
        capacity: 8000,
      },
    },
  ],
};