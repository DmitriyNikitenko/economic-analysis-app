/* Типы данных, настройки слоёв и логика экономических доменов */

/* Подключение типов GeoJSON */
import type { 
  FeatureCollection,  /* Коллекция географических объектов */
  LineString,  /* Линия из последовательности точек */
  MultiPolygon,  /* Район из нескольких раздельных территорий */
  Point,  /* Точка с координатами */
  Polygon  /* Район с одной территорией */
} from "geojson";

/* Основные типы экономической модели */
export type Domain = "money" | "labor" | "goods";  /* Экономические домены: деньги, труд, товары и услуги */
export type Role = "supply" | "demand";  /* Роль объекта: спрос или предложение */
export type LayerId = "objects" | "roles" | "edges";  /* Идентификаторы слоёв карты: объекты, роли, связи */
export type DomainSelection = Domain | "all";  /* Выбор домена для отображения: конкретный домен или все доступные */

/* Свойства экономического объекта */
export type SubjectProperties = {
  id: string;
  name: string;
  kind: "settlement" | "bank" | "employer" | "shop";  /* Тип объекта: населённый пункт, банк, работодатель, магазин */
  district_id: string;
  address?: string | null;
  domains: Partial<Record<Domain, { role: Role; capacity: number }>>;
};

/* Свойства экономической связи */
export type EdgeProperties = {
  id: string;
  domain: Domain;
  from_id: string;  /* Идентификатор исходного объекта */
  to_id: string;  /* Идентификатор конечного объекта */
  distance_km: number;
  weight: number;
};

/* Свойства района */
export type DistrictProperties = {
  id: string;
  name: string;
  synthetic_geometry?: boolean;
};

/* Типы данных для коллекций объектов, связей и районов */
export type SubjectsData = FeatureCollection<Point, SubjectProperties>;
export type EdgesData = FeatureCollection<LineString, EdgeProperties>;
export type DistrictsData = FeatureCollection<Polygon | MultiPolygon, DistrictProperties>;

/* Конфигурация слоёв карты и доменов */
export type LayerConfig = {
  layers: { id: LayerId; label: string; enabled: boolean }[];
  domains: { id: Domain; label: string; enabled: boolean; radius_km: number }[];
  show_all_domains_option: boolean;
};

/* Настройки по умолчанию для слоёв и доменов */
export const DEFAULT_CONFIG: LayerConfig = {
  layers: [
    { id: "objects", label: "Объекты", enabled: true },
    { id: "roles", label: "Спрос и предложение", enabled: true },
    { id: "edges", label: "Связи", enabled: true },
  ],
  domains: [
    { id: "money", label: "Деньги", enabled: true, radius_km: 12 },
    { id: "labor", label: "Труд", enabled: true, radius_km: 15 },
    { id: "goods", label: "Товары и услуги", enabled: false, radius_km: 8.5 },
  ],
  show_all_domains_option: true,
};

/* Функция для получения доступных доменов на основе данных объектов, связей и конфигурации */
export function getAvailableDomains(
  subjects: SubjectsData,  /* Коллекция экономических объектов */
  edges: EdgesData,  /* Коллекция экономических связей */
  config: LayerConfig,  /* Конфигурация слоёв и доменов */
): Domain[] {
  const present = new Set<Domain>();  /* Создание множества доменов */

  /* Поиск доменов в объектах */
  subjects.features.forEach(({ properties }) => {
    (Object.keys(properties.domains ?? {}) as Domain[]).forEach((domain) => {
      if (properties.domains?.[domain]) present.add(domain);
    });
  });
  /* Поиск доменов в связях */
  edges.features.forEach(({ properties }) => present.add(properties.domain));

  /* Возврат списка доступных доменов, которые включены в конфигурации и присутствуют в данных */
  return config.domains
    .filter((domain) => domain.enabled && present.has(domain.id))
    .map((domain) => domain.id);  /* Преобразует найденные записи в массив идентификаторов доменов */
}

/* Функция для проверки, соответствует ли домен текущему выбору и доступным доменам */
export function matchesDomain(
  domain: Domain,  /* Домен проверяемого элемента */
  selection: DomainSelection,  /* Выбранный пользователем домен */
  available: Domain[],  /* Список доступных доменов */
): boolean {
  return selection === "all"
    ? available.includes(domain)
    : domain === selection && available.includes(domain);
}

// Единые цвета связей для карты и графа.
export const DOMAIN_COLORS: Record<Domain, string> = {
  money: "#ec4899",
  labor: "#8b5cf6",
  goods: "#f59e0b",
};