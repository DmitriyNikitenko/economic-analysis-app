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
    useState - хранит состояние компонента
*/
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

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
import { SubjectShape } from "./SVGShapes";

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
  type SubjectProperties,
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

const DOMAIN_LABELS: Record<Domain, string> = {
  money: "Деньги",
  labor: "Труд",
  goods: "Товары и услуги",
};

const KIND_LABELS: Record<SubjectProperties["kind"], string> = {
  settlement: "Населённый пункт",
  bank: "Банк",
  employer: "Работодатель",
  shop: "Магазин",
};

function getCapacityUnit(
  kind: SubjectProperties["kind"],
  domain: Domain,
) {
  if (domain === "money" && kind === "bank") {
    return "усл. ед.";
  }

  if (domain === "labor" && kind === "employer") {
    return "вакансий";
  }

  return "человек";
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
  // ID объекта, который пользователь выбрал на карте
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);

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

  // Получаем диапазон ёмкостей объектов отдельно для каждого домена
  const capacityRanges = useMemo(() => {
    const ranges = new Map<Domain, { min: number; max: number }>();

    availableDomains.forEach((domain) => {
      const capacities = subjects
        .map((feature) => feature.properties.domains?.[domain]?.capacity)
        .filter(
          (capacity): capacity is number =>
            typeof capacity === "number" &&
            Number.isFinite(capacity) &&
            capacity > 0,
        );

      if (capacities.length === 0) return;

      ranges.set(domain, {
        min: Math.min(...capacities),
        max: Math.max(...capacities),
      });
    });

    return ranges;
  }, [subjects, availableDomains]);

  // Масштабируем размер маркера в зависимости от ёмкости объекта
  const MIN_MARKER_RADIUS = 10;
  const MAX_MARKER_RADIUS = 30;

  function getMarkerRadius(capacity: number, domain: Domain) {
    const range = capacityRanges.get(domain);

    if (!range || range.min === range.max) {
      return (MIN_MARKER_RADIUS + MAX_MARKER_RADIUS) / 2;
    }

    const normalized = (capacity - range.min) / (range.max - range.min);

    return (
      MIN_MARKER_RADIUS +
      Math.max(0, Math.min(1, normalized)) *
      (MAX_MARKER_RADIUS - MIN_MARKER_RADIUS)
    );
  }

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

  // Получаем полные данные выбранного объекта:
  // 1. Если пользователь ещё ничего не выбрал, возвращаем null
  // 2. Если ID есть, ищем объект в data.features
  // 3. Если объект найден, сохраняем всю GeoJSON Feature
  // 4. Если объект не найден, возвращаем null
  const selectedSubject = useMemo(
    () =>
      selectedSubjectId === null
        ? null
        : data.features.find(
          (feature) => feature.properties.id === selectedSubjectId,
        ) ?? null,
    [data, selectedSubjectId],
  );

  // Получаем все связи выбранного объекта среди текущих отфильтрованных связей
  const selectedConnections = useMemo(() => {
    if (!selectedSubject) return [];

    const subjectId = selectedSubject.properties.id;

    return visibleEdges.filter(
      (edge) =>
        edge.properties.from_id === subjectId ||  // from_id — объект со стороны спроса
        edge.properties.to_id === subjectId,  // to_id — объект со стороны предложения
    );
  }, [visibleEdges, selectedSubject]);

  // Сортируем связи по весу и оставляем пять наиболее сильных
  const strongestConnections = useMemo(
    () =>
      [...selectedConnections]
        .sort(
          (a, b) =>
            b.properties.weight - a.properties.weight,
        )
        .slice(0, 5),
    [selectedConnections],
  );

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
        {/* Толщина линий зависит от веса ребра */}
        {visibleLayers.edges && visibleEdges.map((edge) => (
          <Polyline
            key={edge.properties.id}
            positions={edge.geometry.coordinates.map(([longitude, latitude]) => [latitude, longitude] as [number, number])}
            pathOptions={{
              color: DOMAIN_COLORS[edge.properties.domain],
              weight: 1 + edge.properties.weight * 5,
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
              {/* Масштабирование колец в зависимости от емкости */}
              {visibleLayers.roles && roleRings.map(({ domain, role }) => {
                const color = roleColor(role);
                const capacity = props.domains[domain]?.capacity ?? 1;

                return (
                  <CircleMarker
                    key={`${props.id}-role-${domain}`}
                    center={[latitude, longitude]}
                    radius={getMarkerRadius(capacity, domain)}
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
                <SubjectShape
                  latitude={latitude}
                  longitude={longitude}
                  kind={props.kind}
                  onSelect={() => setSelectedSubjectId(props.id)}
                />
              )}
              
            </Fragment>
          );
        })}
      </MapContainer>

      {/* Легенда карты */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-200 bg-white p-3 text-sm text-slate-600">
        {visibleLayers.objects && (
          <>
            <span><span style={{ color: "#457b9d" }}>●</span> Населенный пункт</span>
            <span><span style={{ color: "#457b9d" }}>■</span> Банк</span>
            <span><span style={{ color: "#457b9d" }}>▲</span> Работодатель</span>
            <span><span style={{ color: "#457b9d" }}>◆</span> Магазин</span>
          </>
        )}
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

            <span className="inline-flex items-center gap-2">
              Размер круга: ёмкость
            </span>
            
            <span className="inline-flex items-center gap-2">
              Толщина линии: вес связи
            </span>
          </>
        )}
      </div>


      {/* Карточка выбранного объекта */}
      <section className="border-t border-slate-200 bg-white p-4">

        {selectedSubject ? (
          <>
            {/* Заголовок карточки */}
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-800">
                  {selectedSubject.properties.name}
                </h3>

                <p className="text-sm text-slate-500">
                  {KIND_LABELS[selectedSubject.properties.kind]}
                  {" · "}
                  ID: {selectedSubject.properties.id}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setSelectedSubjectId(null)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Сбросить выбор
              </button>
            </div>

            {/* Основная информация */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">

              {/* Ёмкость */}
              <div className="rounded-lg bg-slate-50 p-3">
                <h4 className="mb-3 font-medium text-slate-700">
                  Ёмкость по доменам
                </h4>

                {availableDomains.map((domain) => {
                  const info =
                    selectedSubject.properties.domains?.[domain];

                  if (!info) return null;

                  return (
                    <div
                      key={domain}
                      className="mb-2 flex items-center justify-between gap-2 text-sm"
                    >
                      <div>
                        <span className="text-slate-700">
                          {DOMAIN_LABELS[domain]}
                        </span>

                        <span className="ml-2 text-slate-400">
                          {info.role === "demand"
                            ? "Спрос"
                            : "Предложение"}
                        </span>
                      </div>

                      <span className="font-semibold text-slate-800">
                        {info.capacity.toLocaleString("ru-RU", {
                          maximumFractionDigits: 2,
                        })}{" "}
                        {getCapacityUnit(
                          selectedSubject.properties.kind,
                          domain,
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Количество связей */}
              <div className="rounded-lg bg-slate-50 p-3">
                <h4 className="mb-2 font-medium text-slate-700">
                  Количество связей
                </h4>

                <p className="text-3xl font-bold text-slate-800">
                  {selectedConnections.length}
                </p>

                <p className="mt-1 text-sm text-slate-500">
                  В текущем наборе отфильтрованных связей
                </p>
              </div>
            </div>

            {/* Самые сильные связи */}
            <div className="mt-4">
              <h4 className="mb-3 font-medium text-slate-700">
                Самые сильные связи
              </h4>

              {strongestConnections.length > 0 ? (
                <div className="space-y-2">
                  {strongestConnections.map((edge) => {
                    const isOutgoing =
                      edge.properties.from_id ===
                      selectedSubject.properties.id;

                    const relatedId = isOutgoing
                      ? edge.properties.to_id
                      : edge.properties.from_id;

                    const relatedSubject = data.features.find(
                      (feature) =>
                        feature.properties.id === relatedId,
                    );

                    return (
                      <div
                        key={edge.properties.id}
                        className="flex flex-col justify-between gap-2 rounded-lg border border-slate-200 p-3 sm:flex-row sm:items-center"
                      >
                        <div>
                          <p className="font-medium text-slate-800">
                            {relatedSubject?.properties.name ??
                              relatedId}
                          </p>

                          <p className="text-xs text-slate-500">
                            {isOutgoing
                              ? "Исходящая связь"
                              : "Входящая связь"}
                            {" · "}
                            {DOMAIN_LABELS[
                              edge.properties.domain
                            ]}
                          </p>
                        </div>

                        <div className="text-sm text-slate-600">
                          <p>
                            Вес:{" "}
                            <strong>
                              {edge.properties.weight.toFixed(2)}
                            </strong>
                            {" "}
                            ({Math.round(
                              edge.properties.weight * 100,
                            )}%)
                          </p>

                          <p>
                            Расстояние:{" "}
                            {edge.properties.distance_km.toFixed(1)}
                            {" км"}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  У объекта нет связей в текущем наборе данных.
                </p>
              )}
            </div>

            {/* GeoJSON выбранного объекта */}
            <details className="mt-4 rounded-lg border border-slate-200">
              <summary className="cursor-pointer px-3 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50">
                Показать исходный GeoJSON
              </summary>

              <pre className="max-h-80 overflow-auto border-t border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                {JSON.stringify(selectedSubject, null, 2)}
              </pre>
            </details>
          </>
        ) : (
          /* Карточка до выбора объекта */
          <div className="py-5 text-center">
            <h3 className="font-semibold text-slate-700">
              Объект не выбран
            </h3>

            <p className="mt-2 text-sm text-slate-500">
              Нажмите на объект на карте: появятся ёмкость,
              число связей, самые сильные связи и фрагмент
              GeoJSON, из которого он нарисован.
            </p>
          </div>
        )}
      </section>


    </div>
  );
}
