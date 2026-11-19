/* Отображает интерактивную карту области,
   экономические объекты,
   спрос и предложение,
   связи между объектами 
   и границы районов
*/

/* Импорты инструментов React:
    Fragment - позволяет сгруппировать несколько элементов без дополнительного HTML-контейнера
    useCallback - сохраняет функцию между рендерами, пока не меняются её зависимости
    useMemo - для мемоизации вычисленных значений
    useState - хранит состояние компонента
*/
import { Fragment, useCallback, useMemo, useState } from "react";

/* Импорт компонентов React Leaflet 
    MapContainer - Создаёт контейнер интерактивной карты
    TileLayer - Загружает фоновые картографические тайлы OpenStreetMap
    GeoJSON - слой для отображения GeoJSON-данных (например, границ районов)
    Polyline - слой для отображения линий (например, связей между объектами)
    CircleMarker - слой для отображения кругов (например, объектов и ролей)
    Tooltip - всплывающая подсказка при наведении на элементы карты
*/  
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip
} from "react-leaflet";

/*
  geoJSON - позволяет получить границы географических объектов
  latLngBounds - создаёт прямоугольную географическую область по координатам
  Feature - тип GeoJSON-объекта
  Layer, PathOptions - типы слоёв и стилей Leaflet
*/
import { geoJSON, latLngBounds } from "leaflet";
import type { Feature } from "geojson";
import type { Layer, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";

import { SubjectShape } from "./SVGShapes";
import { FitMapToRegion } from "./FitMapToRegion";
import MapLegend from "./MapLegend";

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
  type MetricsData,
  type MetricStats,
} from "../../layers";

import {
  roleColor,
  DOMAIN_LABELS,
  NO_DATA_COLOR,
  SELECTED_EDGE_COLOR,
  KIND_LABELS,
  getCapacityUnit,
  getDistrictDegreeColor,
} from "../../utils/mapStyles";

// Типизация входных параметров Props
type Props = {
  data: SubjectsData;
  edges: EdgesData;
  districts: DistrictsData;
  metrics: MetricsData;
  config: LayerConfig;
  visibleLayers: Record<LayerId, boolean>;
  selection: DomainSelection;
  availableDomains: Domain[];
};

// Основной компонент MapView
// Здесь компонент получает все параметры, объявленные в Props, 
// и использует их для подготовки данных и отображения
export default function MapView({
  data,
  edges,
  districts,
  metrics,
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

  // Создаём Map (справочник) для быстрого получения названия района по его ID
  // useMemo() — React-хук, который запоминает результат вычислений между рендерами компонента
  // Функция внутри useMemo будет выполняться заново только тогда, когда изменится зависимость districts
  const districtNameById = useMemo(() => {
    // Создаем пустую коллекцию Map, 
    // где ключ — ID района, а значение — его название
    const result = new Map<string, string>();

    // Проходим по каждому району в данных districts
    // и извлекаем его ID и название
    //
    // districts — загруженные данные о районах
    // features — массив географических объектов GeoJSON
    // feature — текущий район, который мы обрабатываем
    districts.features.forEach((feature) => {
      const id = feature.properties?.id;
      const name = feature.properties?.name;

      // Проверяем, что ID и название существуют и являются строками
      if (
        typeof id === "string" &&
        typeof name === "string" &&
        name.trim()
      ) {
        result.set(id, name);
      }
    });

    return result;
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

  // Получаем статистику каждого района для выбранного домена
  const districtStatsById = useMemo(() => {
    // Создаем Map, где ключ — ID района, а значение — статистика по выбранному домену
    const result = new Map<string, MetricStats | undefined>();

    // Проходим по каждому району и извлекаем статистику для выбранного домена
    metrics.districts.forEach((district) => {
      // Здесь выбирается статистика в зависимости от домена, 
      // который пользователь выбрал в интерфейсе
      const stats =
        selection === "all"
          ? district.all
          : district[selection];

      // Сохраняем статистику в Map с ключом ID района
      result.set(district.id, stats);
    });

    return result;  // Возвращаем Map с ID районов и их статистикой
  }, [metrics, selection]);  // Пересчитываем только при изменении метрик или выбранного домена

  // Определяем минимальную и максимальную среднюю степень
  // среди районов, у которых достаточно данных
  const districtDegreeRange = useMemo(() => {
    // Создаём массив средних степеней узлов для всех районов, у которых есть достоверные данные
    const values = Array.from(districtStatsById.values())
      // Фильтруем только те статистические данные, которые существуют, не имеют признака low_data
      // и имеют конечное значение средней степени узлов
      .filter(
        (stats): stats is MetricStats =>  // (stats): stats is MetricStats => (предикат типа) 
          stats !== undefined &&
          !stats.low_data &&
          Number.isFinite(stats.avg_degree),
      )
      .map((stats) => stats.avg_degree);  // извлекаем среднюю степень узлов для каждого района

    if (values.length === 0) return null;  // Если нет достоверных данных, возвращаем null

    // Возвращаем объект с минимальной и максимальной средней степенью узлов среди всех районов
    return {
      min: Math.min(...values),
      max: Math.max(...values),
    };
  }, [districtStatsById]);  // Пересчитываем только при изменении статистики районов

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
      
      // Фильтры:
      return (
        matchesDomain(domain, selection, availableDomains) &&  // Связь относится к выбранному домену
        edge.properties.distance_km <= radius &&  // Расстояние не превышает установленный радиус
        subjectIds.has(edge.properties.from_id) &&  // Начальный объект (спрос) присутствует среди отфильтрованных объектов
        subjectIds.has(edge.properties.to_id)  // Конечный объект (предложение) присутствует среди отфильтрованных объектов
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

  // Находим район, к которому относится выбранный объект
  const selectedDistrictName = useMemo(() => {
    const districtId = selectedSubject?.properties.district_id;

    if (!districtId) return null;

    // Если район найден — возвращаем его название
    // Если название не найдено, показываем его ID.
    return districtNameById.get(districtId) ?? districtId;
  }, [districts, selectedSubject]);

  // Получаем все связи выбранного объекта среди текущих отфильтрованных связей
  const selectedConnections = useMemo(() => {
    // Если объект не выбран, возвращаем пустой массив
    if (!selectedSubject) return [];

    // Получаем ID выбранного объекта
    const subjectId = selectedSubject.properties.id;

    // Находим все связи, в которых участвует выбранный объект
    return visibleEdges.filter(
      (edge) =>
        edge.properties.from_id === subjectId ||  // from_id — объект со стороны спроса
        edge.properties.to_id === subjectId,  // to_id — объект со стороны предложения
    );
  }, [visibleEdges, selectedSubject]);  // массив зависимостей: пересчитываем при изменении видимых связей или выбранного объекта

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

  // Раскрашиваем районы в зависимости от средней степени узлов
  // Если слой отключён, показываем только границы районов
  //
  // Использует 2 другие константы:
  //  districtStatsById — статистика каждого района
  //  districtDegreeRange — минимальная и максимальная средняя степень узлов
  //
  // useCallback — запоминает функцию между рендерами React, пока не изменяются её зависимости
  // feature?: Feature — функция получения GeoJSON-объект района
  const districtStyle = useCallback(
    (feature?: Feature): PathOptions => {
      // Получаем ID района из GeoJSON
      const districtId = feature?.properties?.id;

      // Получаем статистику соответствующего района
      const stats =
        typeof districtId === "string"
          ? districtStatsById.get(districtId)
          : undefined;

      // Проверяем, можно ли использовать показатель для раскраски
      const hasReliableData =
        stats !== undefined &&  // 	Статистика района найдена
        !stats.low_data &&  // Недостатка данных нет
        Number.isFinite(stats.avg_degree) &&  // Средняя степень является конечным числом
        districtDegreeRange !== null;  // Диапазон значений для раскраски определён (иначе, все будет покрашено в серый цвет ниже)

      // Проверяем, включена ли раскраска
      const coloringEnabled = visibleLayers.district_degree;

      // Определяем цвет заливки
      const fillColor = hasReliableData
        ? getDistrictDegreeColor(
          stats.avg_degree,  // Средняя степень узлов района
          districtDegreeRange.min,  // Минимальная средняя степень среди всех районов
          districtDegreeRange.max,  // Максимальная средняя степень среди всех районов
        )
        : NO_DATA_COLOR;

      // Возвращаем объект стиля для района
      return {
        color: "#64748b",
        weight: 1.5,
        opacity: 0.9,
        fillColor,
        fillOpacity: !coloringEnabled
          ? 0.07
          : hasReliableData
            ? 0.65
            : 0.2,
      };
    },
    // Пересчитываем функцию только при изменении статистики районов,
    // диапазона средней степени узлов или видимости слоя district_degree
    [districtStatsById, districtDegreeRange, visibleLayers.district_degree],
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
        {/* Цвет линии зависит от домена связи */}
        {/* Если выбран объект, то его связи становятся более заметными, 
            а остальные связи, не относящиеся к нему, становятся прозрачными */}
        {visibleLayers.edges && visibleEdges.map((edge) => {

          // Проверяем, относится ли связь к выбранному объекту
          const isSelectedConnection =
            // Если объект не выбран, то ни одна связь не выделена
            selectedSubject !== null &&
            (
              // Если выбранный объект является началом связи (спрос)
              // или концом связи (предложение)
              edge.properties.from_id === selectedSubject.properties.id ||
              edge.properties.to_id === selectedSubject.properties.id
            );

          // Вычисляем толщину линии в зависимости от веса связи
          const edgeWeight = 1 + edge.properties.weight * 5;

          return (
            <Polyline

              // Уникальный ключ для каждой линии связи
              key={edge.properties.id}

              // Leaflet использует координаты в формате [широта, долгота],
              // но в GeoJSON они представлены в формате [долгота, широта]
              // Координаты нужны для построения линии между объектами на карте
              positions={edge.geometry.coordinates.map(
                ([longitude, latitude]) =>
                  [latitude, longitude] as [number, number]
              )}

              // Настройки стиля линии связи
              pathOptions={{
                // Цвет связи
                // Если связь относится к выбранному объекту, используем специальный цвет SELECTED_EDGE_COLOR
                // Если связь не относится к выбранному объекту, используем цвет, соответствующий домену связи из DOMAIN_COLORS
                color: isSelectedConnection
                  ? SELECTED_EDGE_COLOR
                  : DOMAIN_COLORS[edge.properties.domain],

                // Увеличиваем толщину выделенных связей
                // Если связь относится к выбранному объекту, увеличиваем толщину линии до 5 пикселей
                weight: isSelectedConnection
                  ? Math.max(edgeWeight, 5)
                  : edgeWeight,

                // При выборе объекта остальные связи становятся прозрачнее
                // 0.8 — стандартная прозрачность для всех связей, когда объект не выбран
                // 0.18 — прозрачность для связей, не относящихся к выбранному объекту
                opacity: selectedSubject
                  ? isSelectedConnection
                    ? 1
                    : 0.18
                  : 0.8,
              }}
            >
              {/* Всплывающая подсказка для линии связи (Tooltip) */}
              <Tooltip>
                {/* Отображаем название домена связи и расстояние между объектами */}
                {config.domains.find(
                  (item) => item.id === edge.properties.domain
                )?.label ?? edge.properties.domain}:{" "}
                {edge.properties.distance_km.toFixed(1)} км
              </Tooltip>
            </Polyline>
          );
        })}

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
      <MapLegend
        visibleLayers={visibleLayers}
        selection={selection}
        availableDomains={availableDomains}
        config={config}
        hasSelectedSubject={selectedSubject !== null}
      />

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

                <p className="text-sm text-slate-500">
                  Район: {selectedDistrictName ?? "Не указан"}
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
                    // Определяем тип связи (по отношению к выбранному объекту):
                    // входящая (к выбранному объекту)
                    // или исходящая (от выбранного объекта)
                    const isOutgoing =
                      edge.properties.from_id ===
                      selectedSubject.properties.id;

                    // Определяем ID связанного объекта в зависимости от типа связи
                    const relatedId = isOutgoing
                      ? edge.properties.to_id  // Входящая связь: предложение
                      : edge.properties.from_id;  // Исходящая связь: спрос

                    // Находим связанный объект в данных data.features по его ID
                    // Это нужно для того, чтобы получить его ID и название
                    const relatedSubject = data.features.find(
                      (feature) =>
                        feature.properties.id === relatedId,
                    );

                    // Получаем ID района связанного объекта
                    const relatedDistrictId =
                      relatedSubject?.properties.district_id;

                    // Получаем название района
                    const relatedDistrictName = relatedDistrictId
                      ? districtNameById.get(relatedDistrictId) ?? relatedDistrictId
                      : "Не указан";

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
                            Район: {relatedDistrictName}
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
