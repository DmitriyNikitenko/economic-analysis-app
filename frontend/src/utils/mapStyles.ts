// Функции и константы, которые отвечают за цвета, подписи и стили объектов на карте в MapView.tsx

import type { Domain, SubjectProperties } from "../layers";

// Цвет спроса и предложения
export function roleColor(role?: "supply" | "demand") {
    if (role === "demand") return "#e45756";
    if (role === "supply") return "#2a9d8f";
    return "#457b9d";
}

// Названия доменов
export const DOMAIN_LABELS: Record<Domain, string> = {
    money: "Деньги",
    labor: "Труд",
    goods: "Товары и услуги",
};

// Цветовая шкала средней степени узлов.
// Чем выше значение, тем темнее цвет.
export const DISTRICT_DEGREE_COLORS = [
    "#e0f7fa",
    "#b2ebf2",
    "#80deea",
    "#4dd0e1",
    "#00acc1",
];

// Цвет районов с недостаточным количеством данных
export const NO_DATA_COLOR = "#cbd5e1";

// Цвет связей выбранного объекта
export const SELECTED_EDGE_COLOR = "#00BFFF";

// Подписи для типов экономических объектов
export const KIND_LABELS: Record<SubjectProperties["kind"], string> = {
    settlement: "Населённый пункт",
    bank: "Банк",
    employer: "Работодатель",
    shop: "Магазин",
};

// Определяем единицу измерения ёмкости в зависимости от типа объекта и домена
export function getCapacityUnit(
    kind: SubjectProperties["kind"],
    domain: Domain,
): string {
    // Ёмкость: население, которое потенциально нуждается в финансовых услугах
    if (domain === "money" && kind === "settlement") {
        return "человек";  // единица измерения
    }

    // Ёмкость: условная мощность банка — способность обслуживать финансовые потребности населения
    if (domain === "money" && kind === "bank") {
        return "усл. ед.";
    }
    // Ёмкость: Трудоспособное население — потенциальная рабочая сила, которая может быть доступна работодателям
    if (domain === "labor" && kind === "settlement") {
        return "человек";
    }

    // Ёмкость: Количество работников, которых работодатель хочет нанять (число открытых вакансий)
    if (domain === "labor" && kind === "employer") {
        return "вакансий";
    }

    return "—";
}

// Определяем цвет района по средней степени узлов
// Функция получает 3 значения
export function getDistrictDegreeColor(
    value: number,  // средняя степень конкретного района
    min: number,  // минимальная средняя степень среди всех районов
    max: number,  // максимальная средняя степень среди всех районов
): string {
    // Если все значения одинаковые, используем средний цвет шкалы
    if (min === max) {
        return DISTRICT_DEGREE_COLORS[
            Math.floor(DISTRICT_DEGREE_COLORS.length / 2)
        ];
    }

    // Нормализуем значение в диапазон от 0 до 1
    // Чтобы распределить значения по цветовой шкале DISTRICT_DEGREE_COLORS
    const normalized = (value - min) / (max - min);

    // Определяем индекс цвета в палитре
    // Math.max(0, ...) в определение индекса цвета, 
    // чтобы защититься от отрицательного индекса массива
    const index = Math.max(
        0,
        Math.min(
            DISTRICT_DEGREE_COLORS.length - 1,
            Math.floor(normalized * DISTRICT_DEGREE_COLORS.length),
        ),
    );

    return DISTRICT_DEGREE_COLORS[index];
}