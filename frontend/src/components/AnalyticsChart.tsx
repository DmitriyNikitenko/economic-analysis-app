/*
  Компонент отображает таблицу статистических показателей районов
  Получает данные из metrics.json через App.tsx
*/

import type {
    DomainSelection,
    LayerConfig,
    MetricStats,
    MetricsData,
} from "../layers";

// Параметры компонента
type Props = {
    metrics: MetricsData;
    selection: DomainSelection;
    config: LayerConfig;
};

// Компонент аналитики
export default function AnalyticsChart({
    metrics,
    selection,
    config,
}: Props) {
    
    // Получаем название выбранного домена
    const selectedDomainLabel =
        selection === "all"
            ? "Все домены"
            : config.domains.find(
                (domain) => domain.id === selection,
            )?.label ?? selection;

    // Получаем статистику всего региона для выбранного домена
    const regionStats: MetricStats | undefined =
        selection === "all"
            ? metrics.region.all
            : metrics.region[selection];

    return (
        <section
            aria-labelledby="analytics-heading"
            className="rounded-xl border border-slate-200 bg-white p-4"
        >
            <h2
                id="analytics-heading"
                className="mb-2 text-xl font-semibold text-slate-800"
            >
                Аналитика по районам
            </h2>

            <p className="mb-4 text-sm text-slate-500">
                Показатели: {selectedDomainLabel}
            </p>

            {/* Таблица статистики районов */}
            <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">

                    <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-600">

                            <th className="p-3 font-medium">
                                Район
                            </th>

                            <th className="p-3 font-medium">
                                Количество узлов
                            </th>

                            <th className="p-3 font-medium">
                                Средняя степень узла
                            </th>

                            <th className="p-3 font-medium">
                                Надёжность показателя
                            </th>

                        </tr>
                    </thead>


                    <tbody>
                        {/* Строка для всего региона */}
                        <tr className="border-b-2 border-slate-300 bg-slate-100">

                            {/* Название региона */}
                            <td className="p-3 font-bold text-slate-900">
                                {metrics.region.name}
                            </td>

                            {/* Количество узлов */}
                            <td className="p-3 font-bold text-slate-900">
                                {regionStats
                                    ? regionStats.node_count.toLocaleString("ru-RU")
                                    : "—"}
                            </td>

                            {/* Средняя степень узла */}
                            <td className="p-3 font-bold text-slate-900">
                                {regionStats
                                    ? regionStats.avg_degree.toLocaleString("ru-RU", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })
                                    : "—"}
                            </td>

                            {/* Надёжность показателя */}
                            <td className="p-3">
                                {!regionStats ? (
                                    <span className="text-slate-400">Нет данных</span>
                                ) : regionStats.low_data ? (
                                    <span className="font-medium text-amber-700">
                                        Мало данных
                                    </span>
                                ) : (
                                    <span className="text-slate-500">
                                        Достаточно данных
                                    </span>
                                )}
                            </td>

                        </tr>

                        {/* Строки для отдельных районов */}
                        {metrics.districts.map((district) => {
                            const stats: MetricStats | undefined =
                                selection === "all"
                                    ? district.all
                                    : district[selection];

                            return (
                                <tr
                                    key={district.id}
                                    className="border-b border-slate-100 hover:bg-slate-50"
                                >
                                    {/* Название района */}
                                    <td className="p-3 font-medium text-slate-800">
                                        {district.name}
                                    </td>

                                    {/* Количество узлов */}
                                    <td className="p-3 text-slate-700">
                                        {stats
                                            ? stats.node_count.toLocaleString("ru-RU")
                                            : "—"}
                                    </td>

                                    {/* Средняя степень узла */}
                                    <td className="p-3 text-slate-700">
                                        {stats
                                            ? stats.avg_degree.toLocaleString("ru-RU", {
                                                minimumFractionDigits: 2,
                                                maximumFractionDigits: 2,
                                            })
                                            : "—"}
                                    </td>

                                    {/* Надёжность показателя */}
                                    <td className="p-3">
                                        {!stats ? (
                                            <span className="text-slate-400">
                                                Нет данных
                                            </span>
                                        ) : stats.low_data ? (
                                            <span className="font-medium text-amber-700">
                                                Мало данных
                                            </span>
                                        ) : (
                                            <span className="text-slate-500">
                                                Достаточно данных
                                            </span>
                                        )}
                                    </td>
                                    
                                </tr>
                            );
                        })}
                    </tbody>


                </table>
            </div>

        </section>
    );
}
