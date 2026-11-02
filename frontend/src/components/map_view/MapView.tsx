/* Отображает интерактивную карту области,
   экономические объекты,
   спрос и предложение,
   связи между объектами 
   и границы районов
*/

/* Импорты инструментов React:
    Fragment - позволяет сгруппировать несколько элементов без дополнительного HTML-контейнера
    useCallback - сохраняет функцию между рендерами, пока не меняются её зависимости
    useEffect - выполняет действия при изменении зависимостей
    useMemo - для мемоизации вычисленных значений
*/
import { Fragment, useCallback, useEffect, useMemo } from "react";

/* Импорт компонентов React Leaflet 
    MapContainer - Создаёт контейнер интерактивной карты
    TileLayer - Загружает фоновые картографические тайлы OpenStreetMap
    GeoJSON - слой для отображения GeoJSON-данных (например, границ районов)
    Polyline - слой для отображения линий (например, связей между объектами)
    CircleMarker - слой для отображения кругов (например, объектов и ролей)
    Tooltip - всплывающая подсказка при наведении на элементы карты
    useMap - Даёт доступ к экземпляру карты Leaflet
*/  
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";

/*
  geoJSON - позволяет получить границы географических объектов
  latLngBounds - создаёт прямоугольную географическую область по координатам
  Feature - тип GeoJSON-объекта
  Layer, LatLngBounds, PathOptions - типы слоёв, границ и стилей Leaflet
*/
import { geoJSON, latLngBounds } from "leaflet";
import type { Feature } from "geojson";
import type { Layer, LatLngBounds, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  DOMAIN_COLORS,
  matchesDomain,
  type Domain,
  type DomainSelection,
  type DistrictsData,
  type EdgesData,
  type LayerConfig,
  type LayerId,
  type SubjectsData,
} from "../../layers";

// Типизация входных параметров Props
type Props = {
  data: SubjectsData;
  edges: EdgesData;
  districts: DistrictsData;
  config: LayerConfig;
  visibleLayers: Record<LayerId, boolean>;
  selection: DomainSelection;
  availableDomains: Domain[];
};

// Цвет спроса и предложения
function roleColor(role?: "supply" | "demand") {
  if (role === "demand") return "#e45756";
  if (role === "supply") return "#2a9d8f";
  return "#457b9d";
}

// Настройка границ карты (ограничение области просмотра) на основе геометрии районов (целой области)
function FitMapToRegion({ bounds }: { bounds: LatLngBounds }) {
  const map = useMap();

  useEffect(() => {
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [12, 12], maxZoom: 9, animate: false });
      map.setMaxBounds(bounds);
    }
  }, [bounds, map]);

  return null;
}

// Основной компонент MapView
// Здесь компонент получает все параметры, объявленные в Props, 
// и использует их для подготовки данных и отображения
export default function MapView({
  data,
  edges,
  districts,
  config,
  visibleLayers,
  selection,
  availableDomains,
}: Props) {
  // Код определяет область, в пределах которой будет отображаться карта
  // используя геометрию районов из GeoJSON. 
  // Если данные о районах недоступны, используются резервные координаты.
  const regionBounds = useMemo(() => {
    const bounds = geoJSON(districts).getBounds();
    // Резервные координаты нужны только если файл районов пуст или повреждён.
    return bounds.isValid() ? bounds.pad(0.06) : latLngBounds([56.8, 38.0], [59.0, 40.8]);
  }, [districts]);

  // Фильтрация экономических объектов
  // Показываем только узлы, участвующие в активном домене/наборе доступных доменов.
  const subjects = useMemo(
    () =>
      data.features.filter((feature) =>
        availableDomains.some(
          (domain) =>
            (selection === "all" || domain === selection) &&
            Boolean(feature.properties.domains?.[domain]),
        ),
      ),
    [data, availableDomains, selection],
  );

  // Фильтрация связей между объектами
  const visibleEdges = useMemo(() => {
    const subjectIds = new Set(subjects.map((feature) => feature.properties.id));

    return edges.features.filter((edge) => {
      const domain = edge.properties.domain;
      const radius = config.domains.find((item) => item.id === domain)?.radius_km ?? 0;
      return (
        matchesDomain(domain, selection, availableDomains) &&
        edge.properties.distance_km <= radius &&
        subjectIds.has(edge.properties.from_id) &&
        subjectIds.has(edge.properties.to_id)
      );
    });
  }, [edges, config, selection, availableDomains, subjects]);

  // Стиль границ районов
  const districtStyle = useCallback(
    (): PathOptions => ({
      color: "#64748b",
      weight: 1.5,
      opacity: 0.9,
      fillColor: "#cbd5e1",
      fillOpacity: 0.07,
    }),
    [],
  );

  // Подписи районов на карте
  const bindDistrictLabel = useCallback((feature: Feature, layer: Layer) => {
    const name = feature.properties?.name;
    if (typeof name === "string" && name.trim()) {
      layer.bindTooltip(name, {
        permanent: true,
        direction: "center",
        className: "district-label",
        opacity: 0.95,
        interactive: false,
      });
    }
  }, []);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      
      {/* Создание карты */}
      <MapContainer
        center={regionBounds.isValid() ? regionBounds.getCenter() : [57.8, 39.0]}
        zoom={7}
        minZoom={7}
        maxZoom={12}
        maxBounds={regionBounds}
        maxBoundsViscosity={1}
        style={{ height: "560px", width: "100%" }}
      >
        <FitMapToRegion bounds={regionBounds} />
        
        {/* Фоновая карта */}
        {/* TileLayer загружает фон OpenStreetMap, на котором отображаются районы и экономические данные */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Границы районов */}
        <GeoJSON data={districts} style={districtStyle} onEachFeature={bindDistrictLabel} />

        {/* Отображение экономических связей */}
        {visibleLayers.edges && visibleEdges.map((edge) => (
          <Polyline
            key={edge.properties.id}
            positions={edge.geometry.coordinates.map(([longitude, latitude]) => [latitude, longitude] as [number, number])}
            pathOptions={{
              color: DOMAIN_COLORS[edge.properties.domain],
              weight: 2,
              opacity: 0.8,
            }}
          >
            {/* Подсказка при наведении на связь, показывающая домен и расстояние */}
            <Tooltip>
              {config.domains.find((item) => item.id === edge.properties.domain)?.label ?? edge.properties.domain}: {edge.properties.distance_km.toFixed(1)} км
            </Tooltip>
          </Polyline>
        ))}

        {/* Отображение экономических объектов и их ролей */}
        {(visibleLayers.objects || visibleLayers.roles) && subjects.map((feature) => {
          const props = feature.properties;
          const [longitude, latitude] = feature.geometry.coordinates;
          
          {/* Определение релевантных доменов (выбор пользователя + доступные домены) для текущего объекта */}
          const relevantDomains = availableDomains.filter(
            (domain) =>
              (selection === "all" || selection === domain) &&
              Boolean(props.domains?.[domain]),
          );

          {/* Кольцо роли (спрос/предложение) рисуется вокруг основного круга объекта */}
          {/* При выборе домена "Все" отдельные кольца позволяют показать роли в разных доменах */}
          const roleRings = relevantDomains
            .map((domain) => ({ domain, role: props.domains[domain]?.role }))
            .filter((item) => item.role !== undefined)
            .reverse();

          return (
            <Fragment key={props.id}>

              {/* Отрисовка колец ролей (спрос/предложение) вокруг объекта, если слой ролей включен */}
              {visibleLayers.roles && roleRings.map(({ domain, role }, index) => {
                const color = roleColor(role);
                return (
                  <CircleMarker
                    key={`${props.id}-role-${domain}`}
                    center={[latitude, longitude]}
                    radius={9 + index * 3}
                    interactive={false}
                    pathOptions={{
                      color,
                      weight: 2,
                      fillColor: color,
                      fillOpacity: 0.12,
                      opacity: 0.95,
                    }}
                  />
                );
              })}

              {/* Отрисовка основного круга объекта, если слой объектов включен */}
              {visibleLayers.objects && (
                <CircleMarker
                  key={`${props.id}-object`}
                  center={[latitude, longitude]}
                  radius={4}
                  interactive={false}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 1.5,
                    fillColor: "#457b9d",
                    fillOpacity: 1,
                  }}
                />
              )}
            </Fragment>
          );
        })}
      </MapContainer>

      {/* Легенда карты */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-200 bg-white p-3 text-sm text-slate-600">
        {visibleLayers.objects && <span><span style={{ color: "#457b9d" }}>●</span> Объект</span>}
        {visibleLayers.roles && (
          <>
            <span><span style={{ color: "#e45756" }}>⭘</span> Спрос</span>
            <span><span style={{ color: "#2a9d8f" }}>⭘</span> Предложение</span>
          </>
        )}
        {visibleLayers.edges && (
          <>
            <span className="inline-flex items-center gap-2">
              <span
                style={{
                  display: "inline-block",
                  width: 28,
                  borderTop: `3px solid ${DOMAIN_COLORS.money}`,
                }}
              />
              Деньги — финансовые связи
            </span>

            <span className="inline-flex items-center gap-2">
              <span
                style={{
                  display: "inline-block",
                  width: 28,
                  borderTop: `3px solid ${DOMAIN_COLORS.labor}`,
                }}
              />
              Труд — связи рынка труда
            </span>
          </>
        )}
      </div>
    </div>
  );
}
