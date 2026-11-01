// Импорты
import { useEffect, useState } from "react";
import { CircleMarker, Polygon, useMap } from "react-leaflet";
import type { LatLng } from "leaflet";  // тип координат Leaflet, содержащий широту и долготу
import type { SubjectProperties } from "../../layers";  // тип объекта из layers.ts, в котором описаны свойства экономических объектов (нам нужен kind)

// Создаем типы для kind и PixelOffset, чтобы использовать их в дальнейшем
// Берём тип свойства kind из SubjectProperties, 
// поэтому SubjectKind автоматически становится объединением четырёх допустимых строк
type SubjectKind = SubjectProperties["kind"];
type PixelOffset = [number, number];  // смещение по X, смещение по Y

// Задаём геометрию каждой фигуры через координаты её вершин относительно центра объекта
// Record<SubjectKind, PixelOffset[]> означает:
//  для каждого допустимого типа объекта должна быть запись 
// в виде массива смещений вершин фигуры
const SHAPE_OFFSETS: Record<SubjectKind, PixelOffset[]> = {
    // населенный пункт: ●
    // Мы не создаем многоугольник для населенного пункта, 
    // а используем CircleMarker, поэтому массив смещений пустой
    settlement: [],  

    // банк: ■
    // 4 точки образуют квадрат:
    // (-4, -4) ●  ● (4, -4)
    // (-4, 4)  ●  ● (4, 4)
    bank: [
        [-4, -4],
        [4, -4],
        [4, 4],
        [-4, 4],
    ],

    // работодатель: ▲
    employer: [
        [0, -5],
        [5, 4],
        [-5, 4],
    ],

    // магазин: ◆
    shop: [
        [0, -5],
        [5, 0],
        [0, 5],
        [-5, 0],
    ],
};

// Стили фигур
const shapeStyle = {
    color: "#ffffff",
    weight: 1.5,  // толщина контура в пикселях
    fillColor: "#457b9d",
    fillOpacity: 1,  // непрозрчность заливки (1 - полностью непрозрачная, 0 - полностью прозрачная)
};

// Интерфейс компонента SubjectShape, который принимает координаты и тип объекта
type SubjectShapeProps = {
    latitude: number;
    longitude: number;
    kind: SubjectKind;
    onSelect: () => void;
};

// React компонент SubjectShape, который рисует фигуру на карте в зависимости от типа объекта
export function SubjectShape({
    latitude,
    longitude,
    kind,
    onSelect,
}: SubjectShapeProps) {
    const map = useMap();  // получаем экземпляр карты Leaflet

    // Хранение координат вершин фигуры в состоянии компонента
    //  positions — текущие координаты вершин фигуры
    //  setPositions — функция, которая обновляет эти координаты
    //  useState<LatLng[]>([]) — изначально массив пустой
    const [positions, setPositions] = useState<LatLng[]>([]);

    // В зависимости от типа объекта выбираем нужный массив координат
    const offsets = SHAPE_OFFSETS[kind];

    // Расчёт координат вершин фигуры при изменении масштаба карты или перемещении карты
    useEffect(() => {
        // Функция для обновления координат вершин фигуры
        const updatePositions = () => {
            // Преобразуем широту и долготу объекта в экранные координаты (в пикселях)
            const center = map.latLngToLayerPoint([
                latitude,
                longitude,
            ]);

            // 1. offsets.map() проходит по всем вершинам фигуры
            // 2. ([dx, dy]) получает горизонтальное и вертикальное смещение
            // 3. center.x + dx и center.y + dy вычисляют экранные координаты вершины
            // 4. layerPointToLatLng() преобразует полученные пиксельные координаты обратно в географические (широта, долгота)
            // 5. Результат сохраняется в nextPositions
            const nextPositions: LatLng[] = offsets.map(([dx, dy]) =>
                map.layerPointToLatLng([
                    center.x + dx,
                    center.y + dy,
                ])
            );

            // Обновляем состояние React
            // Компонент SubjectShape перерисуется с новыми координатами
            setPositions(nextPositions);
        };

        // Обновляем координаты вершин фигуры при перемещении и масштабировании карты
        updatePositions();  // рассчитывает координаты вершин фигуры при первом рендере компонента
        map.on("zoomend moveend", updatePositions);  // zoomend — пользователь закончил масштабирование, moveend — пользователь закончил перемещение карты

        // Функция очистки эффекта useEffect
        // Она удаляет обработчик событий карты, когда компонент удаляется или эффект запускается заново
        // Без очистки могут оставаться лишние обработчики, которые будут вызывать обновление уже неактуальных компонентов
        return () => {
            map.off("zoomend moveend", updatePositions);
        };
    // Массив зависимостей
    // useEffect повторно выполнится, если изменится хотя бы одно из значений:
    //  map — экземпляр карты Leaflet
    //  latitude — широта объекта
    //  longitude — долгота объекта
    //  offsets — координаты вершин выбранной фигуры
    }, [map, latitude, longitude, offsets]); 

    // Если объект — населенный пункт, рисуем CircleMarker вместо многоугольника
    if (kind === "settlement") {
        return (
            <CircleMarker
                center={[latitude, longitude]}
                radius={4}
                pathOptions={shapeStyle}
                interactive={true}
                eventHandlers={{
                    click: onSelect,
                }}
            />
        );
    }

    // При первом рендеринге positions ещё пустой
    // Координаты появятся после выполнения useEffect
    // Если координаты вершин ещё не рассчитаны, React ничего не рисует
    if (positions.length === 0) {
        return null;
    }

    // Отрисовка многоугольника с рассчитанными координатами вершин
    return (
        <Polygon
            positions={positions}
            pathOptions={shapeStyle}
            interactive={true}
            eventHandlers={{
                click: onSelect,
            }}
        />
    );
}
