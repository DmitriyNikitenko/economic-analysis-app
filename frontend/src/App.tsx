// Загружает данные, хранит настройки интерфейса, обрабатывает действия пользователя и передаёт данные компоненту MapView, который отображает карту */

// Импорт библиотек и компонентов */
import { useEffect, useMemo, useState } from "react";
import MapView from "./components/map_view/MapView";

// Импорт типов и функций из layers.ts */
/* Они нужны, чтобы использовать настройки слоёв,
   определять доступные экономические направления
   и проверять типы загружаемых данных */
import {
  DEFAULT_CONFIG,
  getAvailableDomains,
  type Domain,
  type DomainSelection,
  type LayerConfig,
  type LayerId,
  type SubjectsData,
  type EdgesData,
  type DistrictsData,
} from "./layers";

// Типы данных приложения
type AppData = {
  subjects: SubjectsData;
  edges: EdgesData;
  districts: DistrictsData;
};

type DomainConfig = LayerConfig["domains"][number];

// Функция получает файл по указанному адресу,
// проверяет успешность HTTP-запроса и преобразует ответ в JSON 
async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Ошибка загрузки ${url}: HTTP ${response.status}`);
  }

  return (await response.json()) as T;
}

// Функция читает настройки слоёв из конфигурации и создаёт объект, который показывает, какие слои включены
function getInitialVisibleLayers(config: LayerConfig): Record<LayerId, boolean> {
  const configured = Object.fromEntries(
    config.layers.map((layer) => [layer.id, layer.enabled]),
  ) as Partial<Record<LayerId, boolean>>;

  return {
    objects: configured.objects ?? true,
    roles: configured.roles ?? true,
    edges: configured.edges ?? true,
  };
}

// Настройка радиуса досягаемости для одного экономического домена
// Ползунок и текстовое поле синхронизированы
function RadiusControl({
  domain,
  onChange,
}: {
  domain: DomainConfig;
  onChange: (domain: Domain, radiusKm: number) => void;
}) {
  // Храним временное значение радиуса в текстовом поле, чтобы пользователь мог вводить число вручную
  const [draft, setDraft] = useState(String(domain.radius_km)); 

  // Если радиус изменился ползунком или внешней настройкой, обновляем текстовое поле
  useEffect(() => {
    setDraft(String(domain.radius_km));
  }, [domain.radius_km]);

  // Проверяем введённое значение, нормализуем его и вызываем onChange, если оно корректно
  function commitDraft() {
    const normalized = draft.trim().replace(",", ".");
    const parsed = Number(normalized);

    if (!normalized || !Number.isFinite(parsed)) {
      setDraft(String(domain.radius_km));
      return;
    }

    // Ограничиваем значение диапазоном ползунка (0-250 км) и округляем к шагу 0.5 км.
    const radius = Math.round(Math.min(250, Math.max(0, parsed)) * 2) / 2;
    setDraft(String(radius));
    onChange(domain.id, radius);
  }

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <label htmlFor={`radius-${domain.id}`} className="font-medium">
          {domain.label}
        </label>
        <div className="flex items-center gap-2">
          {/* Текстовое поле для ввода радиуса в километрах */}
          <input
            id={`radius-${domain.id}`}
            type="text"
            inputMode="decimal"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commitDraft}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                commitDraft();
                event.currentTarget.blur();
              }
              if (event.key === "Escape") {
                setDraft(String(domain.radius_km));
                event.currentTarget.blur();
              }
            }}
            aria-label={`Радиус связей: ${domain.label}, километры`}
            className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-right tabular-nums"
          />

          <span className="text-sm text-slate-500">км</span>
        </div>
      </div>

      {/* Текстовое поле и ползунок синхронизированы: изменение одного обновляет другое. */}
      <input
        type="range"
        min={0}
        max={250}
        step={0.5}
        value={domain.radius_km}
        onChange={(event) => {
          const radius = Number(event.target.value);
          setDraft(String(radius));
          onChange(domain.id, radius);
        }}
        aria-label={`Ползунок радиуса: ${domain.label}`}
        className="w-full cursor-pointer accent-sky-700"
      />

      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>0 км</span>
        <span>250 км</span>
      </div>
    </div>
  );
}

// Главный компонент приложения
export default function App() {
  /*
  Храним состояние приложения: 
    данные (загруженные объекты, связи и границы районов) (data),
    настройки слоёв и радиусов (config), 
    видимость слоёв (visibleLayers), 
    выбранный домен (selection), 
    состояние загрузки и ошибки (loading, error).
  */

  const [data, setData] = useState<AppData | null>(null);
  const [config, setConfig] = useState<LayerConfig>(DEFAULT_CONFIG);
  const [visibleLayers, setVisibleLayers] = useState<Record<LayerId, boolean>>(
    () => getInitialVisibleLayers(DEFAULT_CONFIG),
  );
  const [selection, setSelection] = useState<DomainSelection>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Загружаем геоданные и конфиг параллельно при открытии страницы
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      try {
        // Promise.all() параллельно (одновременно) загружает все файлы
        const [subjects, edges, districts, loadedConfig] = await Promise.all([
          fetchJson<SubjectsData>("/data/subjects.geojson"),
          fetchJson<EdgesData>("/data/edges.geojson"),
          fetchJson<DistrictsData>("/data/districts.geojson"),
          fetchJson<LayerConfig>("/data/layers.config.json"),
        ]);

        /* Когда файлы загружены, приложение:
            1) Проверяет, какие экономические направления действительно представлены в данных
            2) Сохраняет загруженные геоданные 
            3) Применяет конфигурацию из JSON 
            4) Устанавливает видимость слоёв по умолчанию из конфигурации
            5) Выбирает начальный домен
        */
        if (cancelled) return;

        const domains = getAvailableDomains(subjects, edges, loadedConfig);
        setData({ subjects, edges, districts });
        setConfig(loadedConfig);
        setVisibleLayers(getInitialVisibleLayers(loadedConfig));
        setSelection(
          loadedConfig.show_all_domains_option || domains.length === 0
            ? "all"
            : (domains[0] ?? "all"),
        );
      
      // Если загрузка данных не удалась, сохраняем сообщение об ошибке в error
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Неизвестная ошибка загрузки данных.");
        }
      // В любом случае завершаем состояние загрузки
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadData();
    return () => {
      cancelled = true;
    };
  }, []);

  // Получение доступных экономических доменов из загруженных данных и конфигурации
  const availableDomains = useMemo<Domain[]>(() => {
    if (!data) return [];
    return getAvailableDomains(data.subjects, data.edges, config);
  }, [data, config]);

  // Функции изменения настроек

  // Переключение слоев
  function toggleLayer(layerId: LayerId, enabled: boolean) {
    setVisibleLayers((current) => ({ ...current, [layerId]: enabled }));
  }

  // Изменение радиуса
  function updateRadius(domainId: Domain, radiusKm: number) {
    if (!Number.isFinite(radiusKm) || radiusKm < 0) return;

    // Меняем только клиентский фильтр существующих рёбер, не пересчитывая модель
    setConfig((current) => ({
      ...current,
      domains: current.domains.map((domain) =>
        domain.id === domainId ? { ...domain, radius_km: radiusKm } : domain,
      ),
    }));
  }

  /* Проверки перед отображением интерфейса: 
      если данные ещё загружаются, показываем сообщение о загрузке; 
      если произошла ошибка, показываем сообщение об ошибке; 
      если данных нет, показываем сообщение об отсутствии данных
  */
  if (loading) return <p className="p-4">Загрузка карты и графа…</p>;
  if (error) return <p className="p-4" role="alert">Ошибка: {error}</p>;
  if (!data) return <p className="p-4">Данные отсутствуют.</p>;

  // Проверяем, есть ли данные для выбранного домена
  const selectedDomainHasData = selection === "all" || availableDomains.includes(selection);

  // Отображение интерфейса приложения
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 p-4">
      <header>
        <h1 className="text-2xl font-semibold">Экономическая активность Ярославской области</h1>
      </header>

      {/* Настройки отображения графа: слои, домен и радиус досягаемости связей */}
      <section aria-labelledby="layer-controls-heading" className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 id="layer-controls-heading" className="mb-3 text-lg font-semibold">Настройки отображения графа</h2>

        <fieldset className="mb-5">
          <legend className="mb-2 font-medium">Слои</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {/* Переключатели видимости слоёв: объекты, роли и рёбра */}
            {config.layers.map((layer) => (
              <label key={layer.id} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={visibleLayers[layer.id]}
                  onChange={(event) => toggleLayer(layer.id, event.target.checked)}
                  className="accent-sky-700"
                />
                {layer.label}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="mb-5">
          <legend className="mb-2 font-medium">Домен</legend>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Выбор экономического домена">
            {/* Выбор экономического домена */}
            {config.show_all_domains_option && (
              <button
                type="button"
                aria-pressed={selection === "all"}
                onClick={() => setSelection("all")}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${selection === "all" ? "border-sky-800 bg-sky-800 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}
              >
                Все
              </button>
            )}
  
            {/* Кнопки выбора домена */}
            {config.domains.map((domain) => {
              const hasData = availableDomains.includes(domain.id);
              const active = selection === domain.id;
              return (
                <button
                  key={domain.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSelection(domain.id)}
                  className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${active ? "border-sky-800 bg-sky-800 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}
                >
                  {domain.label}
                  {!hasData && <span className={`ml-2 text-xs ${active ? "text-sky-100" : "text-slate-400"}`}>(нет данных)</span>}
                </button>
              );
            })}
          </div>

          {/* Сообщение о том, что для выбранного домена нет данных */}
          {/* Оно появляется, когда выбранное направление отсутствует среди доступных доменов */}
          {!selectedDomainHasData && (
            <p className="mt-2 text-sm text-amber-800">
              Для домена «{config.domains.find((domain) => domain.id === selection)?.label ?? selection}» пока нет данных.
            </p>
          )}
        </fieldset>

        <fieldset>
          <legend className="mb-2 font-medium">Радиус досягаемости связей</legend>
          {/* Настройки радиуса */}
          <div className="grid gap-3 md:grid-cols-3">
            {config.domains.map((domain) => (
              <RadiusControl key={domain.id} domain={domain} onChange={updateRadius} />
            ))}
          </div>
        </fieldset>
      </section>

      {/* Отображение карты через MapView */}
      <section aria-labelledby="map-heading">
        <h2 id="map-heading" className="mb-2 text-xl font-semibold">Карта районов</h2>
        <MapView
          data={data.subjects}  /* Экономические объекты */
          edges={data.edges}  /* Связи между объектами */
          districts={data.districts}  /* Границы районов */
          config={config}  /*Настройки доменов и радиусов */
          visibleLayers={visibleLayers}  /* Какие слои отображать */
          selection={selection}  /* Выбранный домен */
          availableDomains={availableDomains}  /* Домены, для которых есть данные для отображения */
        />
      </section>

      {/* Заглушка аналитики: файл компонента не импортируется и не выполняется. */}
      <section aria-labelledby="analytics-heading" className="rounded-xl border border-dashed border-slate-300 p-4">
        <h2 id="analytics-heading" className="text-lg font-semibold">Аналитика</h2>
        <p className="text-sm text-slate-600">Раздел аналитики пока не реализован.</p>
      </section>
    </main>
  );
}
