import MapView from "./components/map_view/MapView";
import GraphView from "./components/graph_view/GraphView";
import AnalyticsChart from "./components/analytics_chart/AnalyticsChart";
import { entitiesGeoJSON } from "./data/sampleData";

export default function App() {
  return (
    <main>
      <h1>Economic Graph Prototype</h1>

      <section>
        <h2>Geographic data</h2>
        <MapView data={entitiesGeoJSON} />
      </section>

      <section>
        <h2>Economic network</h2>
        <GraphView />
      </section>

      <section>
        <h2>Analytics</h2>
        <AnalyticsChart />
      </section>
    </main>
  );
}