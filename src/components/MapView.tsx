import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { FeatureCollection, Point } from "geojson";
import L from "leaflet";

type Props = {
  data: FeatureCollection<
    Point,
    { name: string; type: string; capacity: number }
  >;
};

export default function MapView({ data }: Props) {
  return (
    <MapContainer
      center={[48.8566, 2.3522]}
      zoom={13}
      style={{ height: "400px", width: "100%" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <GeoJSON
        key={JSON.stringify(data)}
        data={data}
        pointToLayer={(_feature, latlng) =>
          L.circleMarker(latlng, {
            radius: 7,
            color: "#2563eb",
            fillOpacity: 0.8,
          })
        }
        onEachFeature={(feature, layer) => {
          const { name, type, capacity } = feature.properties;

          layer.bindPopup(
            `<strong>${name}</strong><br/>Type: ${type}<br/>Capacity: ${capacity}`
          );
        }}
      />
    </MapContainer>
  );
}