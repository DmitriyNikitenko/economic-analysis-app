/**
 * Легенда карты:
 * - типы экономических объектов;
 * - спрос и предложение;
 * - экономические связи;
 * - раскраска районов по средней степени узлов.
 */

import type {
    Domain,
    DomainSelection,
    LayerConfig,
    LayerId,
} from "../../layers";

import { DOMAIN_COLORS } from "../../layers";

import {
    DISTRICT_DEGREE_COLORS,
    NO_DATA_COLOR,
} from "../../utils/mapStyles";

// Параметры компонента
type Props = {
    visibleLayers: Record<LayerId, boolean>;
    selection: DomainSelection;
    availableDomains: Domain[];
    config: LayerConfig;
};

// Компонент легенды карты
export default function MapLegend({
    visibleLayers,
    selection,
    availableDomains,
    config,
}: Props) {
    // Получаем название выбранного домена
    const selectedDomainLabel =
        selection === "all"
            ? "Все домены"
            : config.domains.find(
                (domain) => domain.id === selection,
            )?.label ?? selection;

    return (
        <>
            {/* Легенда карты */}
            <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-200 bg-white p-3 text-sm text-slate-600">
                {/* Типы экономических объектов */}
                {visibleLayers.objects && (
                    <>
                        <span>
                            <span style={{ color: "#457b9d" }}>●</span>{" "}
                            Населенный пункт
                        </span>

                        <span>
                            <span style={{ color: "#457b9d" }}>■</span>{" "}
                            Банк
                        </span>

                        <span>
                            <span style={{ color: "#457b9d" }}>▲</span>{" "}
                            Работодатель
                        </span>

                        <span>
                            <span style={{ color: "#457b9d" }}>◆</span>{" "}
                            Магазин
                        </span>
                    </>
                )}

                {/* Спрос и предложение */}
                {visibleLayers.roles && (
                    <>
                        <span>
                            <span style={{ color: "#e45756" }}>⭘</span>{" "}
                            Спрос
                        </span>

                        <span>
                            <span style={{ color: "#2a9d8f" }}>⭘</span>{" "}
                            Предложение
                        </span>
                    </>
                )}

                {/* Экономические связи */}
                {visibleLayers.edges && (
                    <>
                        {availableDomains.map((domain) => {
                            const label =
                                config.domains.find(
                                    (item) => item.id === domain,
                                )?.label ?? domain;

                            return (
                                <span
                                    key={domain}
                                    className="inline-flex items-center gap-2"
                                >
                                    <span
                                        className="inline-block w-7"
                                        style={{
                                            borderTop: `3px solid ${DOMAIN_COLORS[domain]}`,
                                        }}
                                    />
                                    {label}
                                </span>
                            );
                        })}

                        <span className="inline-flex items-center gap-2">
                            Размер круга: ёмкость
                        </span>

                        <span className="inline-flex items-center gap-2">
                            Толщина линии: вес связи
                        </span>
                    </>
                )}
            </div>

            {/* Легенда раскраски районов по средней степени */}
            {visibleLayers.district_degree && (
                <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-2 border-t border-slate-200 bg-white px-3 py-3">
                    <div className="w-full">
                        <p className="font-medium text-slate-700">
                            Среднее число связей на один узел
                        </p>

                        <p className="text-xs text-slate-500">
                            Домен: {selectedDomainLabel}
                        </p>
                    </div>

                    <span className="text-xs text-slate-500">
                        Меньше
                    </span>

                    {DISTRICT_DEGREE_COLORS.map((color) => (
                        <span
                            key={color}
                            className="inline-block h-5 w-5 rounded-sm border border-slate-300"
                            style={{ backgroundColor: color }}
                        />
                    ))}

                    <span className="text-xs text-slate-500">
                        Больше
                    </span>

                    <span className="ml-2 inline-flex items-center gap-1 text-xs text-slate-500">
                        <span
                            className="inline-block h-4 w-4 rounded-sm border border-slate-300"
                            style={{ backgroundColor: NO_DATA_COLOR }}
                        />
                        Мало данных / нет данных
                    </span>
                </div>
            )}
        </>
    );
}